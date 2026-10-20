"""Fill spreadsheet columns with abbreviations from one shared company list.

This is the "column filler" mode of TagForge.  It is different from the tag
generator in :mod:`tagforge.taggen`:

* the user maps **source column -> target column** pairs manually, e.g.
  ``Equipment Description -> Equipment Description Abbr``.  The target
  column normally **already exists in the file** (usually empty) and the
  filler writes into it.  A mapping can also ask for a **new column**, which
  is appended at the end of the file,
* any number of pairs can be filled in one run,
* **one** abbreviation list is used for every pair,
* only the abbreviation is written - words that are not in the list are
  **never copied into the target column**; the cell is left empty instead,
* the source column and the uploaded frame are never modified; the result
  is a copy with the same columns in the same order.

Four matching rules are available (chosen by the user):

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
``MATCH_WORDWISE``
    Every phrase is replaced by its abbreviation and the sentence is rebuilt.
    "Cooling Tower No 2" -> ``CT NO 2`` (or ``CT_NO_2`` depending on the
    separator).  Unknown words can be kept, dropped or make the cell empty.
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
    "MATCH_WORDWISE",
    "MATCH_MODES",
    "CASE_OPTIONS",
    "NOT_FOUND_BLANK",
    "NOT_FOUND_KEEP",
    "NOT_FOUND_OPTIONS",
    "WORDWISE_KEEP",
    "WORDWISE_DROP",
    "WORDWISE_EMPTY",
    "WORDWISE_UNKNOWN_OPTIONS",
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
MATCH_WORDWISE = "Abbreviate each word/phrase (rebuild sentence)"
MATCH_MODES: Tuple[str, ...] = (MATCH_ANY, MATCH_EXACT, MATCH_ALL_WORDS, MATCH_WORDWISE)

CASE_OPTIONS: Tuple[str, ...] = (CASE_PRESERVE, CASE_UPPER, CASE_LOWER)

# what to do with cells that cannot be matched
NOT_FOUND_BLANK = "Leave the cell empty"
NOT_FOUND_KEEP = "Keep the original text"
NOT_FOUND_OPTIONS: Tuple[str, ...] = (NOT_FOUND_BLANK, NOT_FOUND_KEEP)

# how to handle unknown words in WORDWISE mode
WORDWISE_KEEP = "Keep original word"
WORDWISE_DROP = "Drop unknown words"
WORDWISE_EMPTY = "Leave cell empty if any word is unknown"
WORDWISE_UNKNOWN_OPTIONS: Tuple[str, ...] = (WORDWISE_KEEP, WORDWISE_DROP, WORDWISE_EMPTY)

# per-cell status values (also used in the report tables)
STATUS_FILLED = "Filled"
STATUS_NOT_FOUND = "Not found"
STATUS_EMPTY = "Empty source cell"
STATUS_KEPT = "Original kept"

_ABBREVIATION_FALLBACK = "Abbreviation"


# ---------------------------------------------------------------------------
# configuration objects
# ---------------------------------------------------------------------------
@dataclass(init=False)
class FillMapping:
    """One "source column -> target column" instruction.

    By default ``target`` is a column that **already exists** in the frame
    (usually an empty ``… Abbr`` column supplied by the user) and the
    abbreviation is written into it.

    Set ``new_column=True`` to **create** ``target`` when it does not exist.
    The new column is appended at the end of the output frame; the uploaded
    source frame is still never modified.  ``target`` may be empty as a
    shortcut when filling an existing column: :func:`run_column_fill` then
    looks for a column named ``source + FillConfig.output_suffix`` and fails
    if there is none.

    ``output`` is accepted as a backwards-compatible alias of ``target``.
    ``match_mode`` may be empty - the global :attr:`FillConfig.match_mode`
    is used in that case.
    """

    source: str
    target: str = ""
    match_mode: str = ""
    new_column: bool = False

    def __init__(
        self,
        source: str = "",
        target: str = "",
        match_mode: str = "",
        *,
        output: str = "",
        new_column: bool = False,
    ) -> None:
        self.source = source
        self.target = target or output
        self.match_mode = match_mode
        self.new_column = bool(new_column)

    @property
    def output(self) -> str:  # backwards-compatible alias of ``target``
        return self.target

    @output.setter
    def output(self, value: str) -> None:
        self.target = value

    def resolved_target(self, config: "FillConfig") -> str:
        """The column to write into (created at the end when ``new_column``)."""
        return (self.target or "").strip() or f"{self.source}{config.output_suffix}"

    def resolved_mode(self, config: "FillConfig") -> str:
        mode = self.match_mode or config.match_mode
        return mode if mode in MATCH_MODES else config.match_mode


@dataclass
class FillConfig:
    """Settings shared by every column of one fill run."""

    match_mode: str = MATCH_WORDWISE
    case: str = CASE_PRESERVE
    separator: str = " "  # used by MATCH_ALL_WORDS and MATCH_WORDWISE
    allow_plural_matching: bool = False
    keep_numbers: bool = True  # used by MATCH_ALL_WORDS and MATCH_WORDWISE
    when_not_found: str = NOT_FOUND_BLANK
    # Only used to *find* an existing target column when a mapping does not
    # name one ("Equipment" -> existing "Equipment Abbr").  Never used to
    # create a column.
    output_suffix: str = " Abbr"
    wordwise_unknown: str = WORDWISE_KEEP  # only used by MATCH_WORDWISE

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
        if self.match_mode in (MATCH_ALL_WORDS, MATCH_WORDWISE) and not (self.separator or "").strip():
            # allow single space as valid separator, so check stripped length
            if self.separator == "":
                problems.append(
                    "The separator is empty, so abbreviations of several words would run together (BFWPMP)."
                )
        if self.when_not_found not in NOT_FOUND_OPTIONS:
            problems.append("Unknown 'when no abbreviation is found' option - cells will be left empty.")
        if self.match_mode == MATCH_WORDWISE and self.wordwise_unknown not in WORDWISE_UNKNOWN_OPTIONS:
            problems.append("Unknown 'unknown word' option - original words will be kept.")
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
    """All cells of one mapped pair, plus the resolved target column name."""

    mapping: FillMapping
    target_name: str
    match_mode: str
    cells: List[CellFill] = field(default_factory=list)

    @property
    def output_name(self) -> str:  # backwards-compatible alias
        return self.target_name

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

    @property
    def new_columns(self) -> List[str]:
        """Target columns that were created (they did not exist in the source)."""
        existing = {str(column) for column in self.source_frame.columns}
        return [
            column.target_name
            for column in self.columns
            if column.target_name not in existing
        ]

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
    wordwise_unknown: str = WORDWISE_KEEP,
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

    if mode == MATCH_WORDWISE:
        # Greedy longest-phrase walk: every token/phrase that has an
        # abbreviation is replaced, the rest is handled by the unknown-word
        # setting.  Pieces are joined with *separator* to rebuild a sentence.
        # This fixes the bug where "Cooling Tower No 2" only returned "CT".
        out_parts: List[str] = []
        phrases: List[str] = []
        has_abbreviation = False
        has_unknown = False
        index = 0
        while index < len(keys):
            hit = table.lookup(keys, index, allow_plurals=allow_plural_matching)
            if hit is not None:
                size, abbreviation, phrase = hit
                if abbreviation == DROP_MARKER:
                    index += size
                    continue
                out_parts.append(abbreviation)
                phrases.append(phrase)
                has_abbreviation = True
                index += size
                continue
            token = tokens[index]
            if keep_numbers and token.kind == "number":
                out_parts.append(token.text)
                index += 1
                continue
            if wordwise_unknown == WORDWISE_DROP:
                has_unknown = True
                index += 1
                continue
            if wordwise_unknown == WORDWISE_EMPTY:
                return None
            # WORDWISE_KEEP (default): keep original word
            out_parts.append(token.text)
            has_unknown = True
            index += 1

        if not out_parts:
            return None
        if not has_abbreviation and has_unknown:
            return None
        joined = separator.join(out_parts)
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
# column-name helper (kept for backwards compatibility; the filler itself
# no longer creates columns, so it does not use this any more)
# ---------------------------------------------------------------------------
def unique_column_name(existing: Sequence[object], wanted: str, fallback: str = _ABBREVIATION_FALLBACK) -> str:
    """A column name that does not clash with ``existing`` (case-insensitive).

    Excel treats headers case-insensitively, so "Abbr" and "abbr" are the same
    column.  Clashes get `` (2)``, `` (3)`` ... appended.
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
    """Fill every mapped target column and return the result frame.

    The source ``frame`` is never modified.  Abbreviations are written into
    the target column of each mapping (overwriting whatever it contained -
    it is normally empty).  Existing columns keep their position.  A mapping
    with ``new_column=True`` whose target is not in the frame creates that
    column at the **end** of the output; nothing else is created, removed or
    moved, and all rows are preserved.
    """
    if frame is None:
        raise ValueError("No data to fill - upload the main Excel file first.")

    config = config or FillConfig()
    table = table if table is not None else AbbreviationTable()
    mappings = list(mappings or [])

    available = [str(column) for column in frame.columns]
    existing_by_key = {name.strip().lower(): name for name in available}
    resolved: List[Tuple[FillMapping, str, str]] = []
    used_targets: set = set()
    for mapping in mappings:
        if mapping.source not in available:
            raise KeyError(
                f"Source column '{mapping.source}' was not found in the data file. "
                f"Available columns: {', '.join(available) or 'none'}."
            )
        target_name = mapping.resolved_target(config)
        target_key = target_name.strip().lower()
        if mapping.new_column:
            if target_key in existing_by_key:
                raise ValueError(
                    f"Cannot create a new column '{target_name}' - a column "
                    f"with that name already exists in the data file. Pick "
                    f"the existing column as the target, or choose another "
                    f"name for the new column."
                )
        elif target_name not in available:
            raise KeyError(
                f"Target column '{target_name}' was not found in the data file. "
                f"The filler does not create columns - choose a column that "
                f"already exists in the file, or mark the mapping as a new "
                f"column. "
                f"Available columns: {', '.join(available) or 'none'}."
            )
        if target_name == mapping.source and not mapping.new_column:
            raise ValueError(
                f"Source and target are both '{mapping.source}' - filling it "
                f"would overwrite the original text. Choose a different "
                f"target column."
            )
        if target_key in used_targets:
            raise ValueError(
                f"Target column '{target_name}' is used more than once. "
                f"Each target column can only be filled from one source column."
            )
        used_targets.add(target_key)
        resolved.append((mapping, target_name, mapping.resolved_mode(config)))

    filled_columns: List[FilledColumn] = []
    total = len(resolved) * len(frame)
    done = 0
    for mapping, target_name, mode in resolved:
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
                    wordwise_unknown=config.wordwise_unknown,
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
                target_name=target_name,
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
    """A copy of ``frame`` with every target column filled.

    Existing target columns keep their position.  Columns requested with
    ``new_column=True`` are appended at the end, in mapping order.  All other
    columns, their order and all rows are preserved.
    """
    output = frame.copy()
    for column in filled_columns:
        values = pd.Series(column.values, index=frame.index, dtype="object")
        # An existing name keeps its position; a name that is not there is
        # appended at the end (that is how pandas assigns a new column).
        output[column.target_name] = values
    return output


# ---------------------------------------------------------------------------
# report tables
# ---------------------------------------------------------------------------
def build_fill_summary_frame(result: FillResult) -> pd.DataFrame:
    """One row per mapped pair: how many cells were filled / left empty."""
    rows = []
    for column in result.columns:
        rows.append(
            {
                "Source column": column.mapping.source,
                "Target column": column.target_name,
                "New column": "Yes" if column.target_name in result.new_columns else "No",
                "Filled": column.filled,
                "Left empty (no abbreviation)": column.not_found,
                "Empty source cell": column.empty,
            }
        )
    columns = [
        "Source column",
        "Target column",
        "New column",
        "Filled",
        "Left empty (no abbreviation)",
        "Empty source cell",
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
