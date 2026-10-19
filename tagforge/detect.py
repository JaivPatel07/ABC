"""Column *hints*.

These helpers only ever produce a **suggestion** for a dropdown default.  The
user always sees the full list of columns from the uploaded file and can pick a
different one, so nothing here is hardcoded behaviour.
"""

from __future__ import annotations

import re
from typing import Optional, Sequence

__all__ = [
    "guess_column",
    "guess_fill_pairs",
    "guess_pair",
    "guess_source_columns",
    "looks_like_abbreviation_column",
    "looks_like_header_row",
    "suggest_output_column",
]

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


_FILL_SOURCE_HINTS = (
    "equipment",
    "description",
    "parameter",
    "item",
    "service",
    "section",
    "name",
    "material",
    "type",
    "area",
    "category",
    "device",
    "activity",
)


def guess_source_columns(columns: Sequence[str]) -> list:
    """Suggest columns that probably contain names worth abbreviating.

    Used only as a suggestion in the filler; the user is always free to
    pick anything.  Abbreviation (target) columns are never suggested as
    sources.
    """
    matches = []
    for column in columns:
        if looks_like_abbreviation_column(column):
            continue
        lowered = str(column).strip().lower()
        if any(hint in lowered for hint in _FILL_SOURCE_HINTS):
            matches.append(str(column))
    return matches


# ---------------------------------------------------------------------------
# "source column -> existing abbreviation column" pairs
# ---------------------------------------------------------------------------
_TARGET_SUFFIXES = (
    "abbreviation",
    "abbrev",
    "abbr",
    "short form",
    "short name",
    "short",
    "acronym",
    "code",
)

_TARGET_SUFFIX_RE = re.compile(
    r"[\s_\-.(\[]*"
    r"(abbreviation|abbrev|abbr|short\s+form|short\s+name|short|acronym|code)"
    r"\.?\s*[)\]]*$",
    re.IGNORECASE,
)


def _normalised_name(name: object) -> str:
    text = str(name).strip().lower().replace("_", " ").replace("-", " ")
    text = re.sub(r"[.()\]]+$", "", text.strip())
    return re.sub(r"\s+", " ", text).strip()


def looks_like_abbreviation_column(column: object) -> bool:
    """True for names like ``Equipment Abbr`` or just ``Abbreviation``."""
    normalised = _normalised_name(column)
    if not normalised:
        return False
    return normalised in _TARGET_SUFFIXES or any(
        normalised.endswith(f" {suffix}") for suffix in _TARGET_SUFFIXES
    )


def guess_fill_pairs(columns: Sequence[str]) -> list:
    """Suggest ``(source, target)`` pairs for the column filler.

    A *target* is an existing abbreviation-looking column
    (``… Abbr``, ``… Abbreviation``, ``… Code`` …).  Its source is, in
    order of preference: the column named like the target without the
    suffix (``Equipment Description Abbr`` -> ``Equipment Description``),
    the nearest plain column before it, then the nearest one after it.

    Suggestions only - the user confirms or changes every pair.
    """
    names = [str(column) for column in columns]
    by_normalised = {}
    for name in names:
        by_normalised.setdefault(_normalised_name(name), name)

    pairs: list = []
    used_sources: set = set()
    for index, target in enumerate(names):
        if not looks_like_abbreviation_column(target):
            continue

        source = None
        base = _TARGET_SUFFIX_RE.sub("", target).strip(" _-.()[]")
        if base:
            candidate = by_normalised.get(_normalised_name(base))
            if candidate is not None and candidate != target:
                source = candidate
        if source is None:  # nearest plain column before, then after
            neighbours = list(reversed(names[:index])) + names[index + 1:]
            source = next(
                (name for name in neighbours if not looks_like_abbreviation_column(name)),
                None,
            )
        if source is None or source in used_sources:
            continue
        used_sources.add(source)
        pairs.append((source, target))
    return pairs
