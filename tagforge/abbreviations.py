"""The company abbreviation list.

The :class:`AbbreviationTable` is the single source of truth for "this word or
phrase becomes that abbreviation".  It is intentionally strict:

* only entries that come from the uploaded company list (or that the user adds
  explicitly) are used,
* the **longest** matching phrase always wins ("Cooling Tower" beats "Cooling"),
* unknown words are returned untouched and reported - never guessed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pandas as pd

from .text_utils import phrase_key, singular_candidates, to_text

__all__ = [
    "Abbreviation",
    "AbbreviationTable",
    "LoadReport",
    "load_table_from_frame",
    "DROP_MARKER",
    "SOURCE_COMPANY",
    "SOURCE_USER",
]

SOURCE_COMPANY = "company list"
SOURCE_USER = "user added"
NOTE_PLURAL = "matched through plural form"

#: When a phrase maps to this value the word is removed from the tag instead of
#: being written out.  It is only ever set by the user, never guessed.
DROP_MARKER = "(ignore)"


@dataclass
class Abbreviation:
    """One row of the abbreviation list."""

    phrase: str
    abbr: str
    source: str = SOURCE_COMPANY
    note: str = ""

    # derived values are computed once - the tables are looked up very often
    _key: str = field(init=False, repr=False, compare=False, default="")
    _token_count: int = field(init=False, repr=False, compare=False, default=0)

    def __post_init__(self) -> None:
        self._key = phrase_key(self.phrase)
        self._token_count = len(self._key.split())

    @property
    def key(self) -> str:
        return self._key

    @property
    def token_count(self) -> int:
        return self._token_count


@dataclass
class LoadReport:
    """What happened while reading the abbreviation file."""

    rows_read: int = 0
    added: int = 0
    blank_rows: int = 0
    duplicates: List[str] = field(default_factory=list)
    conflicts: List[str] = field(default_factory=list)
    slash_expanded: int = 0

    @property
    def messages(self) -> List[str]:
        out: List[str] = []
        if self.blank_rows:
            out.append(f"{self.blank_rows} row(s) ignored because the phrase or abbreviation was empty.")
        if self.duplicates:
            out.append(
                f"{len(self.duplicates)} duplicate phrase(s) were ignored (first entry kept): "
                + ", ".join(self.duplicates[:10])
                + (" ..." if len(self.duplicates) > 10 else "")
            )
        if self.conflicts:
            out.append(
                f"{len(self.conflicts)} phrase(s) map to more than one abbreviation "
                f"(first entry kept): " + ", ".join(self.conflicts[:10])
            )
        if self.slash_expanded:
            out.append(f"{self.slash_expanded} mapping(s) were created by splitting 'A / B' entries.")
        return out


class AbbreviationTable:
    """An ordered, case-insensitive collection of phrase -> abbreviation."""

    def __init__(self, entries: Optional[Iterable[Abbreviation]] = None) -> None:
        self._entries: Dict[str, Abbreviation] = {}
        self._max_len: Optional[int] = None  # cached, see `max_phrase_len`
        self._version: int = 0
        for entry in entries or []:
            self._entries[entry.key] = entry

    # ------------------------------------------------------------------ basics
    def __len__(self) -> int:
        return len(self._entries)

    def __contains__(self, phrase: object) -> bool:
        return phrase_key(str(phrase)) in self._entries

    def __iter__(self):
        return iter(self._entries.values())

    @property
    def version(self) -> int:
        """Increases on every change - used to detect 'list changed -> regenerate'."""
        return self._version

    @property
    def entries(self) -> List[Abbreviation]:
        return list(self._entries.values())

    @property
    def max_phrase_len(self) -> int:
        """Longest phrase measured in tokens (1 for single words).

        Cached, because it is read for every single lookup.
        """
        if self._max_len is None:
            self._max_len = max((entry.token_count for entry in self._entries.values()), default=0)
        return self._max_len

    def get(self, phrase: str) -> Optional[Abbreviation]:
        return self._entries.get(phrase_key(phrase))

    # --------------------------------------------------------------- mutations
    def add(self, phrase: str, abbr: str, source: str = SOURCE_USER, note: str = "") -> Tuple[bool, str]:
        """Add or overwrite one mapping.  Returns ``(changed, message)``."""
        clean_phrase = to_text(phrase)
        clean_abbr = to_text(abbr)
        if not clean_phrase:
            return False, "The phrase is empty - nothing was added."
        if not clean_abbr:
            return False, f"'{clean_phrase}' was not added because no abbreviation was given."
        key = phrase_key(clean_phrase)
        existing = self._entries.get(key)
        self._entries[key] = Abbreviation(clean_phrase, clean_abbr, source, note)
        self._version += 1
        self._max_len = None
        if existing is None:
            return True, f"Added '{clean_phrase}' -> '{clean_abbr}'."
        if existing.abbr == clean_abbr:
            return False, f"'{clean_phrase}' -> '{clean_abbr}' is already in the list."
        return True, f"Updated '{clean_phrase}': '{existing.abbr}' -> '{clean_abbr}'."

    def remove(self, phrase: str) -> bool:
        """Remove one mapping by phrase (case/space insensitive)."""
        key = phrase_key(phrase)
        if key not in self._entries:
            return False
        del self._entries[key]
        self._version += 1
        self._max_len = None
        return True

    def replace_all(self, entries: Iterable[Abbreviation]) -> None:
        self._entries = {}
        for entry in entries:
            self._entries[entry.key] = entry
        self._version += 1
        self._max_len = None

    def clear(self) -> None:
        self._entries = {}
        self._version += 1
        self._max_len = None

    # ----------------------------------------------------------------- lookups
    def lookup(
        self,
        keys: Sequence[str],
        start: int,
        allow_plurals: bool = False,
    ) -> Optional[Tuple[int, str, str]]:
        """Find the longest phrase matching at ``keys[start:]``.

        Returns ``(tokens_consumed, abbreviation, matched_phrase)`` or ``None``.
        Longest match wins, so "Cooling Tower" is preferred over "Cooling".
        """
        if not self._entries:
            return None
        remaining = len(keys) - start
        max_len = min(self.max_phrase_len, remaining)
        for size in range(max_len, 0, -1):
            chunk = keys[start : start + size]
            candidate = tuple(chunk)
            hit = self._entries.get(" ".join(candidate))
            if hit is not None:
                return size, hit.abbr, hit.phrase
            if allow_plurals and size == 1:
                for singular in singular_candidates(chunk[0]):
                    hit = self._entries.get(singular)
                    if hit is not None:
                        return size, hit.abbr, hit.phrase
        return None

    # ------------------------------------------------------------------- export
    def to_frame(self) -> pd.DataFrame:
        """The list as a tidy DataFrame (ready for editing or export)."""
        rows = [
            {
                "Phrase": entry.phrase,
                "Abbreviation": entry.abbr,
                "Source": entry.source,
                "Note": entry.note,
            }
            for entry in self._entries.values()
        ]
        if not rows:
            return pd.DataFrame(columns=["Phrase", "Abbreviation", "Source", "Note"])
        return pd.DataFrame(rows)

    def to_csv_bytes(self) -> bytes:
        return self.to_frame().to_csv(index=False).encode("utf-8-sig")


def load_table_from_frame(
    frame: pd.DataFrame,
    phrase_column: str,
    abbr_column: str,
    expand_slashes: bool = False,
    source: str = SOURCE_COMPANY,
) -> Tuple[AbbreviationTable, LoadReport]:
    """Build an :class:`AbbreviationTable` from a user supplied DataFrame.

    ``phrase_column``/``abbr_column`` are chosen by the user at runtime - the
    column names of the abbreviation file are never assumed.
    """
    report = LoadReport(rows_read=len(frame))
    table = AbbreviationTable()

    if phrase_column not in frame.columns or abbr_column not in frame.columns:
        raise KeyError(
            f"Columns '{phrase_column}' / '{abbr_column}' were not found. "
            f"Available columns: {', '.join(map(str, frame.columns))}"
        )

    for phrase_value, abbr_value in zip(frame[phrase_column], frame[abbr_column]):
        report.rows_read = report.rows_read  # keep count stable
        phrase = to_text(phrase_value)
        abbr = to_text(abbr_value)
        if not phrase or not abbr:
            if phrase or abbr:
                report.blank_rows += 1
            continue

        phrases = [phrase]
        if expand_slashes and "/" in phrase:
            parts = [p for p in (to_text(p) for p in phrase.split("/")) if p]
            if len(parts) > 1:
                phrases = parts
                report.slash_expanded += len(parts) - 1

        for single_phrase in phrases:
            key = phrase_key(single_phrase)
            if not key:
                continue
            if key in table:
                existing = table.get(single_phrase)
                if existing and existing.abbr != abbr:
                    report.conflicts.append(f"'{single_phrase}': '{existing.abbr}' vs '{abbr}'")
                else:
                    report.duplicates.append(single_phrase)
                continue
            table.add(single_phrase, abbr, source=source)
            report.added += 1

    return table, report
