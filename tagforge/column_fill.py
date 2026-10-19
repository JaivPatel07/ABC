"""Fill spreadsheet columns with abbreviations from one shared company list.

This is the "column filler" mode of TagForge.  It is different from the tag
generator in :mod:`tagforge.taggen`:

* the user picks **several columns** of the main file and each one gets a new
  column with its abbreviation right next to it,
* **one** abbreviation list is used for every column,
* only the abbreviation is written - words that are not in the list are
  **never copied into the new column**; the cell is left empty instead,
* the source column is never modified.

Three matching rules are available (chosen by the user):

``MATCH_ANY``
    The longest phrase found anywhere in the cell wins.  "Cooling Tower No 2"
    -> ``CT``.  The rest of the cell is ignored.
``MATCH_EXACT``
    The whole cell must be a phrase from the list.  "Cooling Tower" -> ``CT``
    but "Cooling Tower No 2" -> empty.
``MATCH_ALL_WORDS``
    Every word of the cell must be in the list and the abbreviations are joined
    with a separator.  "Boiler Feed Water Pump" -> ``BFW_PMP``; one unknown
    word makes the whole cell empty.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from .abbreviations import DROP_MARKER, AbbreviationTable
from .config import CASE_LOWER, CASE_PRESERVE, CASE_UPPER
from .text_utils import to_text, tokenize

__all__ = [
    "MATCH_ANY",
    "MATCH_EXACT",
    "MATCH_ALL_WORDS",
    "MATCH_MODES",
    "CASE_OPTIONS",
    "NOT_FOUND_BLANK",
    "NOT_FOUND_KEEP",
    "NOT_FOUND_OPTIONS",
    "STATUS_FILLED",
    "STATUS_NOT_FOUND",
    "STATUS_EMPTY",
    "STATUS_KEPT",
    "FillMapping",
    "FillConfig",
    "MatchResult",
    "CellFill",
    "FilledColumn",
    "FillResult",
    "find_match",
    "apply_case",
    "unique_column_name",
    "run_column_fill",
    "build_fill_summary_frame",
    "build_fill_not_found_frame",
]

# ---------------------------------------------------------------------------
# matching rules
# ---------------------------------------------------------------------------
MATCH_ANY = "Any match in the cell (longest phrase)"
MATCH_EXACT = "Whole cell must match exactly"
MATCH_ALL_WORDS = "Every word must match"
MATCH_MODES: Tuple[str, ...] = (MATCH_ANY, MATCH_EXACT, MATCH_ALL_WORDS)

CASE_OPTIONS: Tuple[str, ...] = (CASE_PRESERVE, CASE_UPPER, CASE_LOWER)

# what to do with cells that cannot be matched
NOT_FOUND_BLANK = "Leave the cell empty"
NOT_FOUND_KEEP = "Keep the original text"
NOT_FOUND_OPTIONS: Tuple[str, ...] = (NOT_FOUND_BLANK, NOT_FOUND_KEEP)

# per-cell status values (also used in the report tables)
STATUS_FILLED = "Filled"
STATUS_NOT_FOUND = "Not found"
STATUS_EMPTY = "Empty source cell"
STATUS_KEPT = "Original kept"

_ABBREVIATION_FALLBACK = "Abbreviation"


# ---------------------------------------------------------------------------
# configuration objects
# ---------------------------------------------------------------------------
@dataclass
class FillMapping:
    """One "source column -> new abbreviation column" instruction.

    ``output`` may be empty - :func:`run_column_fill` then builds a name from
    the source column plus :attr:`FillConfig.output_suffix`.
    ``match_mode`` may be empty - the global :attr:`FillConfig.match_mode` is
    used in that case.
    """

    source: str
    output: str = ""
    match_mode: str = ""

    def resolved_mode(self, config: "FillConfig") -> str:
        mode = self.match_mode or config.match_mode
        return mode if mode in MATCH_MODES else config.match_mode


@dataclass
class FillConfig:
    """Settings shared by every column of one fill run."""

    match_mode: str = MATCH_ANY
    case: str = CASE_PRESERVE
    separator: str = "_"  # only used by MATCH_ALL_WORDS
    allow_plural_matching: bool = False
    keep_numbers: bool = True  # only used by MATCH_ALL_WORDS
    when_not_found: str = NOT_FOUND_BLANK
    output_suffix: str = " Abbr"

    def effective_mode(self) -> str:
        return self.match_mode if self.match_mode in MATCH_MODES else MATCH_ANY

    def to_dict(self) -> Dict[str, object]:
        return asdict(self)

    def fingerprint(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, default=str)

    def issues(self) -> List[str]:
        problems: List[str] = []
        if self.match_mode not in MATCH_MODES:
            problems.append("The selected matching rule is not known - 'Any match' will be used.")
        if self.case not in CASE_OPTIONS:
            problems.append("The selected letter case is not known - the abbreviation is kept as listed.")
        if self.match_mode == MATCH_ALL_WORDS and not (self.separator or "").strip():
            problems.append(
                "The separator is empty, so abbreviations of several words would run together (BFWPMP)."
            )
        if self.when_not_found not in NOT_FOUND_OPTIONS:
            problems.append("Unknown 'when no abbreviation is found' option - cells will be left empty.")
        return problems


# ---------------------------------------------------------------------------
# results
# ---------------------------------------------------------------------------
@dataclass
class MatchResult:
    """One successful lookup inside a cell."""

    phrase: str
    abbreviation: str
    start: int = 0
    size: int = 1


@dataclass
class CellFill:
    """What happened to one cell of one source column."""

    row_id: int
    original: str
    abbreviation: str = ""
    matched_phrase: str = ""
    status: str = STATUS_NOT_FOUND
    note: str = ""

    @property
    def is_filled(self) -> bool:
        return self.status == STATUS_FILLED and bool(self.abbreviation)


@dataclass
class FilledColumn:
    """All cells of one mapped column, plus the resolved output column name."""

    mapping: FillMapping
    output_name: str
    match_mode: str
    cells: List[CellFill] = field(default_factory=list)

    @property
    def values(self) -> List[str]:
        return [cell.abbreviation for cell in self.cells]

    @property
    def filled(self) -> int:
        return sum(1 for cell in self.cells if cell.status == STATUS_FILLED)

    @property
    def not_found(self) -> int:
        return sum(1 for cell in self.cells if cell.status == STATUS_NOT_FOUND)

    @property
    def empty(self) -> int:
        return sum(1 for cell in self.cells if cell.status == STATUS_EMPTY)

    @property
    def kept(self) -> int:
        return sum(1 for cell in self.cells if cell.status == STATUS_KEPT)


@dataclass
class FillResult:
    """Everything the UI needs to preview, report and export a fill run."""

    source_frame: pd.DataFrame
    output_frame: pd.DataFrame
    columns: List[FilledColumn]
    table: AbbreviationTable
    config: FillConfig

    @property
    def rows(self) -> int:
        return len(self.source_frame)

    @property
    def filled_cells(self) -> int:
        return sum(column.filled for column in self.columns)

    @property
    def not_found_cells(self) -> int:
        return sum(column.not_found for column in self.columns)

    @property
    def empty_cells(self) -> int:
        return sum(column.empty for column in self.columns)

    @property
    def kept_cells(self) -> int:
        return sum(column.kept for column in self.columns)

    def column(self, source: str) -> Optional[FilledColumn]:
        return next((column for column in self.columns if column.mapping.source == source), None)


# ---------------------------------------------------------------------------
# lookups
# ---------------------------------------------------------------------------
def apply_case(text: str, case: str) -> str:
    """Apply the chosen letter case to an abbreviation."""
    text = to_text(text)
    if case == CASE_UPPER:
        return text.upper()
    if case == CASE_LOWER:
        return text.lower()
    return text


def find_match(
    table: AbbreviationTable,
    value: object,
    mode: str = MATCH_ANY,
    allow_plural_matching: bool = False,
    separator: str = "_",
    keep_numbers: bool = True,
) -> Optional[MatchResult]:
    """Find the abbreviation for one cell.  ``None`` means "no match".

    The rule is chosen by the caller; this function never guesses and never
    creates an abbreviation that is not in ``table``.
    """
    text = to_text(value)
    if not text or not len(table):
        return None

    if mode == MATCH_EXACT:
        entry = table.get(text)
        if entry is None or entry.abbr == DROP_MARKER:
            return None
        return MatchResult(entry.phrase, entry.abbr, 0, len(tokenize(text)))

    tokens = tokenize(text)
    keys = [token.key for token in tokens]
    if not keys:
        return None

    if mode == MATCH_ALL_WORDS:
        abbreviations: List[str] = []
        phrases: List[str] = []
        index = 0
        while index < len(keys):
            hit = table.lookup(keys, index, allow_plurals=allow_plural_matching)
            if hit is None:
                # numbers ("No 2") are not abbreviations; like the tag
                # generator, they can be kept as typed.
                if keep_numbers and tokens[index].kind == "number":
                    abbreviations.append(tokens[index].text)
                    index += 1
                    continue
                return None  # one unknown word -> the whole cell stays empty
            size, abbreviation, phrase = hit
            if abbreviation != DROP_MARKER:
                abbreviations.append(abbreviation)
                phrases.append(phrase)
            index += size
        if not abbreviations:
            return None
        joined = separator.join(abbreviations)
        return MatchResult(" ".join(phrases), joined, 0, len(keys))

    # MATCH_ANY: the longest phrase anywhere in the cell wins; on a tie the
    # earliest phrase wins ("first / longest").
    best: Optional[MatchResult] = None
    for start in range(len(keys)):
        hit = table.lookup(keys, start, allow_plurals=allow_plural_matching)
        if hit is None:
            continue
        size, abbreviation, phrase = hit
        if abbreviation == DROP_MARKER:
            # the list explicitly says "ignore this word" - do not fall back to
            # a shorter phrase, the user's instruction wins.
            if best is None or size > best.size:
                best = MatchResult(phrase, "", start, size)
            continue
        if best is None or size > best.size:
            best = MatchResult(phrase, abbreviation, start, size)

    if best is None or not best.abbreviation:
        return None
    return best


# ---------------------------------------------------------------------------
# output column names
# ---------------------------------------------------------------------------
def unique_column_name(existing: Sequence[object], wanted: str, fallback: str = _ABBREVIATION_FALLBACK) -> str:
    """A column name that does not clash with ``existing`` (case-insensitive).

    Excel treats headers case-insensitively, so "Abbr" and "abbr" are the same
    column.  Clashes get `` (2)``, `` (3)`` ... appended - an existing column is
    never overwritten.
    """
    taken = {str(name).strip().lower() for name in existing}
    base = to_text(wanted) or fallback
    if base.strip().lower() not in taken:
        return base
    index = 2
    while f"{base} ({index})".lower() in taken:
        index += 1
    return f"{base} ({index})"


# ---------------------------------------------------------------------------
# the whole run
# ---------------------------------------------------------------------------
def run_column_fill(
    frame: pd.DataFrame,
    table: AbbreviationTable,
    mappings: Sequence[FillMapping],
    config: Optional[FillConfig] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> FillResult:
    """Fill every mapped column and return the new frame plus a report.

    The source ``frame`` is never modified.  New columns are inserted directly
    after their source column; all other columns and rows are preserved in
    their original order.
    """
    if frame is None:
        raise ValueError("No data to fill - upload the main Excel file first.")

    config = config or FillConfig()
    table = table if table is not None else AbbreviationTable()
    mappings = list(mappings or [])

    available = [str(column) for column in frame.columns]
    for mapping in mappings:
        if mapping.source not in available:
            raise KeyError(
                f"Column '{mapping.source}' was not found in the data file. "
                f"Available columns: {', '.join(available) or 'none'}."
            )

    # Resolve the output names against the columns that already exist *and*
    # the names chosen earlier in this run, so nothing is ever overwritten.
    used_names: List[str] = list(available)
    resolved: List[Tuple[FillMapping, str, str]] = []
    for mapping in mappings:
        wanted = mapping.output.strip() or f"{mapping.source}{config.output_suffix}"
        output_name = unique_column_name(used_names, wanted)
        used_names.append(output_name)
        resolved.append((mapping, output_name, mapping.resolved_mode(config)))

    filled_columns: List[FilledColumn] = []
    total = len(resolved) * len(frame)
    done = 0
    for mapping, output_name, mode in resolved:
        values = frame[mapping.source].tolist()
        cells: List[CellFill] = []
        for row_id, value in enumerate(values):
            original = to_text(value)
            if not original:
                cells.append(
                    CellFill(
                        row_id=row_id,
                        original="",
                        abbreviation="",
                        status=STATUS_EMPTY,
                        note="the source cell is empty",
                    )
                )
            else:
                match = find_match(
                    table,
                    original,
                    mode=mode,
                    allow_plural_matching=config.allow_plural_matching,
                    separator=config.separator,
                    keep_numbers=config.keep_numbers,
                )
                if match is not None:
                    cells.append(
                        CellFill(
                            row_id=row_id,
                            original=original,
                            abbreviation=apply_case(match.abbreviation, config.case),
                            matched_phrase=match.phrase,
                            status=STATUS_FILLED,
                        )
                    )
                elif config.when_not_found == NOT_FOUND_KEEP:
                    cells.append(
                        CellFill(
                            row_id=row_id,
                            original=original,
                            abbreviation=original,
                            status=STATUS_KEPT,
                            note="no abbreviation found - original text kept as requested",
                        )
                    )
                else:
                    cells.append(
                        CellFill(
                            row_id=row_id,
                            original=original,
                            abbreviation="",
                            status=STATUS_NOT_FOUND,
                            note="no abbreviation in the list - cell left empty",
                        )
                    )
            done += 1
            if progress_callback and (done % max(1, total // 100) == 0 or done == total):
                progress_callback(done, total)

        filled_columns.append(
            FilledColumn(
                mapping=mapping,
                output_name=output_name,
                match_mode=mode,
                cells=cells,
            )
        )

    output = _build_output_frame(frame, filled_columns)
    return FillResult(
        source_frame=frame,
        output_frame=output,
        columns=filled_columns,
        table=table,
        config=config,
    )


def _build_output_frame(frame: pd.DataFrame, filled_columns: Sequence[FilledColumn]) -> pd.DataFrame:
    """Insert each new column right after its source column."""
    if not filled_columns:
        return frame.copy()

    new_data = {column.output_name: pd.Series(column.values, index=frame.index, dtype="object")
                for column in filled_columns}

    after: Dict[str, List[str]] = {}
    for column in filled_columns:
        after.setdefault(column.mapping.source, []).append(column.output_name)

    order: List[str] = []
    for name in frame.columns:
        order.append(name)
        order.extend(after.get(str(name), []))

    # Any output whose source was not an original column cannot happen because
    # the source is validated above, but keep the guard for safety.
    for name in new_data:
        if name not in order:
            order.append(name)

    combined = pd.concat([frame, pd.DataFrame(new_data, index=frame.index)], axis=1)
    return combined.loc[:, order]


# ---------------------------------------------------------------------------
# report tables
# ---------------------------------------------------------------------------
def build_fill_summary_frame(result: FillResult) -> pd.DataFrame:
    """One row per mapped column: how many cells were filled / left empty."""
    rows = []
    for column in result.columns:
        rows.append(
            {
                "Source column": column.mapping.source,
                "New column": column.output_name,
                "Match rule": column.match_mode,
                "Rows": len(column.cells),
                "Filled": column.filled,
                "Left empty (no abbreviation)": column.not_found,
                "Empty source cell": column.empty,
                "Original kept": column.kept,
            }
        )
    columns = [
        "Source column",
        "New column",
        "Match rule",
        "Rows",
        "Filled",
        "Left empty (no abbreviation)",
        "Empty source cell",
        "Original kept",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def build_fill_not_found_frame(result: FillResult) -> pd.DataFrame:
    """Every distinct value that had no abbreviation, with its count."""
    rows: List[Dict[str, object]] = []
    for column in result.columns:
        grouped: Dict[str, Dict[str, object]] = {}
        for cell in column.cells:
            if cell.status != STATUS_NOT_FOUND:
                continue
            key = cell.original.lower()
            group = grouped.get(key)
            if group is None:
                grouped[key] = {
                    "Source column": column.mapping.source,
                    "Value with no abbreviation": cell.original,
                    "Occurrences": 1,
                    "First row": cell.row_id + 1,
                }
            else:
                group["Occurrences"] = int(group["Occurrences"]) + 1

        for group in sorted(grouped.values(), key=lambda item: (-int(item["Occurrences"]), str(item["Value with no abbreviation"]).lower())):
            rows.append(group)

    columns = ["Source column", "Value with no abbreviation", "Occurrences", "First row"]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)
