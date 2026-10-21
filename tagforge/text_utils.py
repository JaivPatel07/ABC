"""Text normalisation and tokenisation helpers.

Everything in this module is pure Python (no Streamlit, no pandas UI code) so it
can be unit tested and reused from any interface.

The rules implemented here are deliberately conservative:

* spacing / casing / unicode noise is cleaned up,
* text is split into *word* and *number* tokens,
* nothing is ever abbreviated or guessed - that is the job of
  :mod:`tagforge.abbreviations` and :mod:`tagforge.taggen`.
"""

from __future__ import annotations

import math
import re
import unicodedata
from dataclasses import dataclass
from typing import Iterable, List, Sequence

import pandas as pd

__all__ = [
    "Token",
    "TOKEN_PATTERN",
    "is_missing",
    "to_text",
    "tokenize",
    "token_keys",
    "normalise_phrase",
    "phrase_key",
    "singular_candidates",
    "collapse_repeats",
    "trim_edges",
    "is_single_letter_token",
    "is_code_token",
    "normalize_code_token",
]

# A token is a word, a number (optionally with a decimal separator) or a code.
# Everything else (punctuation, brackets, dashes, slashes ...) is treated as a
# separator.  That keeps "Cooling Tower - No 2" and "Cooling Tower No. 2"
# equivalent.

# The "body" of a code: letters, a hyphen or underscore, then digits.
_CODE_BODY = r"[A-Za-z]+[-_]\d+"

# The optional letter suffix of a code.  It may be written attached
# ("R-200A"), joined with a hyphen/underscore ("R-200-A") or separated by one
# space ("R-200 A").  Only a *single* free-standing letter is allowed after a
# space, so "Primary Air Fan - 1" is never mistaken for a code.
_CODE_SUFFIX = r"(?:[A-Za-z]+|(?:[-_][A-Za-z]+)+|\s[A-Za-z](?![A-Za-z]))"

# Codes like R-1400 / R-200A / T-1000-A / T-1000 A
_CODE_RE = re.compile(r"^" + _CODE_BODY + r"(?:" + _CODE_SUFFIX + r")?$")

# A code typed with spaces around its hyphen ("T - 1000A", "T - 1000 A").  Only
# a single letter may start it - guarded by lookarounds so the tail of a normal
# word ("Fan - 1") is never swallowed - and the trailing letter is required.
_SPACED_CODE = (
    r"(?<![A-Za-z])[A-Za-z](?![A-Za-z])\s*[-_]\s*\d+(?:\s?[A-Za-z](?![A-Za-z]))"
)

TOKEN_PATTERN = re.compile(
    _CODE_BODY + r"(?:" + _CODE_SUFFIX + r")?"
    r"|" + _SPACED_CODE +
    r"|[A-Za-zÀ-ɏ]+|\d+(?:[.,]\d+)?"
)

# Whitespace written around the hyphen/underscore of a code is not part of the
# code itself: "T - 1000A" -> "T-1000A".
_SPACE_AROUND_SEPARATOR_RE = re.compile(r"\s*([-_])\s*")

# Separator between the digits and a trailing letter group of a code.  A code
# is always written with the suffix attached: T-1000-A -> T_1000A.
_CODE_SUFFIX_JOIN_RE = re.compile(r"(?<=\d)[\s_]+(?=[A-Za-z])")


def _compact_code(text: str) -> str:
    """Drop the spaces a code may carry around its hyphen/underscore."""
    return _SPACE_AROUND_SEPARATOR_RE.sub(r"\1", text.strip())


def is_single_letter_token(text: str) -> bool:
    """True for a single alphabetic character (e.g. \"A\", \"b\")."""
    return len(text) == 1 and text.isalpha()


def is_code_token(text: str) -> bool:
    """True for R-like codes: letters + '-'/'_' + digits + optional letters.

    Examples: R-1400, R-200A, AB-123, P_100, R_1400, T-1000-A, T-1000 A,
    T - 1000A
    """
    if not text:
        return False
    return bool(_CODE_RE.match(_compact_code(text)))


def normalize_code_token(text: str) -> str:
    """Normalise a code token: R-1400 -> R_1400, R-200A -> R_200A.

    The trailing letter suffix always stays attached to the digits, so
    ``T-1000A``, ``T-1000-A`` and ``T - 1000 A`` all become ``T_1000A``
    (never ``T_1000_A``).  Only hyphens are replaced; an already-normalised
    R_1400 is left as is.  Single letters are returned unchanged.
    """
    if not text:
        return text
    if is_code_token(text):
        normalized = _compact_code(text).replace("-", "_")
        return _CODE_SUFFIX_JOIN_RE.sub("", normalized)
    return text

_WHITESPACE_PATTERN = re.compile(r"\s+")

# Characters that pandas/Spreadsheets insert that we always want to treat as a
# plain space.
_SPACE_LIKE = {
    " ": " ",  # non breaking space
    " ": " ",  # figure space
    " ": " ",  # narrow no-break space
    " ": " ",  # thin space
    " ": " ",  # hair space
    "　": " ",  # ideographic space
    "\t": " ",
    "\r": " ",
    "\n": " ",
}


@dataclass(frozen=True)
class Token:
    """A single token produced by :func:`tokenize`."""

    text: str
    kind: str  # "word" or "number"

    @property
    def key(self) -> str:
        """Lower-cased lookup form of the token."""
        return self.text.lower()

    def __str__(self) -> str:  # pragma: no cover - convenience only
        return self.text


def is_missing(value: object) -> bool:
    """True for ``None``, ``NaN``, ``NaT``, ``pd.NA`` and blank strings."""
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):  # non scalar objects (lists, dicts, ...)
        return False


def _format_number(value: float) -> str:
    """Render numbers the way an engineer would expect (101.0 -> ``101``)."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return ""
        if value.is_integer() and abs(value) < 1e15:
            return str(int(value))
        return ("%f" % value).rstrip("0").rstrip(".")
    return str(value)


def to_text(value: object) -> str:
    """Convert any spreadsheet cell value into a clean string.

    ``None``/``NaN`` become ``""``.  Unicode is NFKC-normalised (so a single
    "smart" character never sneaks into a tag) and every run of whitespace -
    including non-breaking spaces - collapses into one plain space.
    """
    if is_missing(value):
        return ""
    if isinstance(value, str):
        text = value
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        text = _format_number(value)
    else:
        text = str(value)

    if not text.isascii():
        # only pay for unicode folding and exotic spaces when they can occur
        text = unicodedata.normalize("NFKC", text)
        for bad, good in _SPACE_LIKE.items():
            text = text.replace(bad, good)
    text = _WHITESPACE_PATTERN.sub(" ", text)
    return text.strip()


def tokenize(text: str) -> List[Token]:
    """Split ``text`` into :class:`Token` objects.

    ``"Boiler Feed Water Pump No. 2"`` ->
    ``["Boiler", "Feed", "Water", "Pump", "No", "2"]``
    """
    if not text:
        return []
    tokens: List[Token] = []
    for match in TOKEN_PATTERN.finditer(text):
        raw = match.group(0).replace(",", ".")
        if not raw:
            continue
        if raw[0].isdigit():
            kind = "number"
        elif is_code_token(raw):
            kind = "code"
        else:
            kind = "word"
        tokens.append(Token(raw, kind))
    return tokens


def token_keys(tokens: Sequence[Token]) -> List[str]:
    """Lower-cased lookup keys for a token sequence."""
    return [token.key for token in tokens]


def normalise_phrase(phrase: str) -> List[str]:
    """Normalised token keys of a phrase (used for abbreviation lookups)."""
    return token_keys(tokenize(to_text(phrase)))


def phrase_key(phrase: str) -> str:
    """A stable, case/space-insensitive key for a phrase."""
    return " ".join(normalise_phrase(phrase))


def singular_candidates(word: str) -> List[str]:
    """Cheap singular forms of ``word`` used only when plural matching is on.

    This never *creates* an abbreviation - it only lets "Pumps" hit the
    officially approved "Pump" entry.  Off by default, and every hit is still
    reported with the phrase that was matched.
    """
    lowered = word.lower()
    candidates: List[str] = []
    if lowered.endswith("ies") and len(lowered) > 4:
        candidates.append(lowered[:-3] + "y")
    if lowered.endswith(("ses", "xes", "zes", "ches", "shes")):
        candidates.append(lowered[:-2])
    if lowered.endswith("s") and not lowered.endswith("ss") and len(lowered) > 2:
        candidates.append(lowered[:-1])
    # de-duplicate, keep order
    seen = set()
    unique = [c for c in candidates if not (c in seen or seen.add(c))]
    return unique


def collapse_repeats(text: str, separator: str) -> str:
    """Collapse runs of ``separator`` (e.g. ``A___B`` -> ``A_B``)."""
    if not separator or not text:
        return text
    pattern = re.compile(re.escape(separator) + r"{2,}")
    return pattern.sub(separator, text)


def trim_edges(text: str, separator: str, extra: str = "") -> str:
    """Strip leading/trailing separators and whitespace from ``text``."""
    if not text:
        return text
    chars = " " + (separator or "") + (extra or "")
    return text.strip(chars) if chars.strip() else text.strip()


def unique_preserving_order(items: Iterable[str]) -> List[str]:
    """De-duplicate while keeping the original order."""
    seen = set()
    result: List[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            result.append(item)
    return result
