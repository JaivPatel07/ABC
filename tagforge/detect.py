"""Column *hints*.

These helpers only ever produce a **suggestion** for a dropdown default.  The
user always sees the full list of columns from the uploaded file and can pick a
different one, so nothing here is hardcoded behaviour.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

__all__ = ["guess_column", "guess_pair", "looks_like_header_row", "suggest_output_column"]

_PHRASE_HINTS = (
    "full form",
    "full name",
    "long name",
    "description",
    "term",
    "phrase",
    "word",
    "equipment",
    "name",
    "text",
    "meaning",
)

_ABBREVIATION_HINTS = (
    "abbreviation",
    "abbrev",
    "abbr",
    "short",
    "code",
    "tag",
    "symbol",
    "acronym",
    "short form",
    "short name",
)

_TARGET_HINTS = (
    "equipment",
    "description",
    "item",
    "name",
    "title",
    "tag",
    "label",
    "service",
    "section",
    "parameter",
    "device",
)


def _score(column_name: str, hints: Sequence[str]) -> int:
    lowered = str(column_name).strip().lower()
    if not lowered:
        return -1
    best = -1
    for index, hint in enumerate(hints):
        position = lowered.find(hint)
        if position < 0:
            continue
        # exact match scores highest, then hint at the start, then anywhere
        score = (0 if lowered == hint else (5 if position == 0 else 20)) + index
        best = score if best < 0 else min(best, score)
    return best


def guess_column(columns: Sequence[str], hints: Sequence[str]) -> Optional[str]:
    """Return the most likely column for ``hints`` (never raises)."""
    if not columns:
        return None
    scored = [( _score(column, hints), index, column) for index, column in enumerate(columns)]
    scored = [item for item in scored if item[0] >= 0]
    if not scored:
        return None
    scored.sort()
    return str(scored[0][2])


def guess_pair(columns: Sequence[str]) -> tuple:
    """Guess ``(phrase_column, abbreviation_column)`` for an abbreviation file."""
    abbr_col = guess_column(columns, _ABBREVIATION_HINTS)
    remaining = [c for c in columns if c != abbr_col]
    phrase_col = guess_column(remaining, _PHRASE_HINTS) or guess_column(columns, _PHRASE_HINTS)
    if phrase_col == abbr_col:
        phrase_col = next((c for c in columns if c != abbr_col), abbr_col)
    return phrase_col, abbr_col


def looks_like_header_row(values: Sequence[object]) -> bool:
    """True when a row looks like column headers rather than data."""
    texts = [str(value).strip() for value in values if value is not None]
    if not texts:
        return False
    non_empty = [t for t in texts if t and t.lower() != "nan"]
    if len(non_empty) < max(2, len(texts) * 0.6):
        return False
    if len(set(non_empty)) != len(non_empty):
        return False
    numeric = sum(1 for t in non_empty if re.fullmatch(r"[-+]?[\d.,]+", t))
    return numeric <= max(0, len(non_empty) // 4)


def suggest_output_column(existing: Sequence[str], default: str = "Generated_Tag") -> str:
    """A free column name for the generated tags (``Generated_Tag``, ``..._2``)."""
    if default not in existing:
        return default
    index = 2
    while f"{default}_{index}" in existing:
        index += 1
    return f"{default}_{index}"
