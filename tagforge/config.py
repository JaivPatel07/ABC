"""Configuration objects for tag-name generation.

Nothing about a company's naming convention is hardcoded here.  A
:class:`NamingConfig` is built by the user (through the Streamlit UI or
programmatically) and describes *their* rules.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Dict, List, Tuple

__all__ = [
    "NamingConfig",
    "TemplateError",
    "CASE_OPTIONS",
    "TRUNCATE_OPTIONS",
    "TEMPLATE_PRESETS",
    "PLACEHOLDER_HELP",
    "validate_template",
    "template_placeholders",
    "default_invalid_pattern",
]

CASE_UPPER = "UPPERCASE"
CASE_LOWER = "lowercase"
CASE_PRESERVE = "Keep original"
CASE_OPTIONS: Tuple[str, ...] = (CASE_UPPER, CASE_LOWER, CASE_PRESERVE)

TRUNCATE_OFF = "Do not limit"
TRUNCATE_HARD = "Cut at limit"
TRUNCATE_SEPARATOR = "Cut at last separator"
TRUNCATE_OPTIONS: Tuple[str, ...] = (TRUNCATE_OFF, TRUNCATE_HARD, TRUNCATE_SEPARATOR)

# Named starting points offered in the UI.  "Custom" simply means "use whatever
# the user typed".
TEMPLATE_PRESETS: Dict[str, str] = {
    "Abbreviation only": "{abbr}",
    "Prefix + abbreviation": "{prefix}{abbr}",
    "Abbreviation + suffix": "{abbr}{suffix}",
    "Prefix + abbreviation + suffix": "{prefix}{abbr}{suffix}",
    "Prefix + abbreviation + row number": "{prefix}{abbr}{index}",
    "Original text, cleaned": "{original}",
    "Custom (type your own)": "",
}

PLACEHOLDER_HELP: List[Tuple[str, str]] = [
    ("{abbr}", "the abbreviated form of the selected column"),
    ("{original}", "the original text of the selected column (cleaned)"),
    ("{prefix}", "the text typed in the *Prefix* box (e.g. a plant code)"),
    ("{suffix}", "the text typed in the *Suffix* box (e.g. a revision)"),
    ("{index}", "the row number, starting at *Row number starts at*"),
    ("{index:04d}", "the row number zero padded to 4 digits (0001, 0002, ...)"),
    ("{col:Column Name}", "the value of another column of the same row"),
]

# Placeholder syntax:  {name}  or  {name:spec}
_PLACEHOLDER_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_ ]*)(?::([^}]*))?\}")

_KNOWN_PARTS = {"abbr", "original", "prefix", "suffix", "index", "col", "column", "field"}


class TemplateError(ValueError):
    """Raised when a naming template cannot be understood."""


def template_placeholders(template: str) -> List[str]:
    """Return the raw placeholder strings found in ``template``."""
    return [match.group(0) for match in _PLACEHOLDER_RE.finditer(template or "")]


def validate_template(template: str, available_columns: List[str]) -> Tuple[List[str], List[str]]:
    """Check a naming template.

    Returns ``(errors, warnings)``.  Errors block generation, warnings are just
    hints shown to the user.
    """
    errors: List[str] = []
    warnings: List[str] = []
    template = template or ""

    if not template.strip():
        errors.append("The naming template is empty. Add at least one placeholder such as {abbr}.")
        return errors, warnings

    try:
        _PLACEHOLDER_RE.sub(" ", template)
    except re.error as exc:  # pragma: no cover - defensive
        errors.append(f"The template could not be parsed: {exc}")
        return errors, warnings

    found = False
    for match in _PLACEHOLDER_RE.finditer(template):
        found = True
        name = match.group(1).strip().lower()
        spec = (match.group(2) or "").strip()
        if name in ("col", "column", "field"):
            column = spec.strip("'\"")
            if not column:
                errors.append(
                    f"'{match.group(0)}' is missing a column name. Use the form "
                    f"{{col:Section}} - available columns: {', '.join(available_columns) or 'none'}."
                )
            elif column not in available_columns:
                errors.append(
                    f"'{match.group(0)}' refers to column '{column}' which is not in the file. "
                    f"Available columns: {', '.join(available_columns) or 'none'}."
                )
        elif name not in _KNOWN_PARTS:
            errors.append(
                f"'{match.group(0)}' is not a known placeholder. "
                f"Valid placeholders: " + ", ".join(p for p, _ in PLACEHOLDER_HELP) + "."
            )
        elif name == "index" and spec:
            try:
                format(1, spec)
            except (ValueError, TypeError):
                errors.append(f"'{match.group(0)}' has an invalid number format ('{spec}').")

    if not found:
        warnings.append(
            "The template contains no placeholders, so every row would get the same tag. "
            "Add {abbr} to use the generated abbreviation."
        )

    if "{" in template and template.count("{") != template.count("}"):
        errors.append("Unbalanced braces in the template - check for a missing '{' or '}'.")

    return errors, warnings


def default_invalid_pattern(separator: str, extra_allowed: str = "") -> str:
    """Build the 'characters that are not allowed in a tag' pattern.

    The default keeps letters, digits, the chosen separator and any extra
    characters the company allows (e.g. ``-``).
    """
    allowed = "".join(sorted(set((separator or "") + (extra_allowed or ""))))
    return r"[^A-Za-z0-9" + re.escape(allowed) + r"]"


@dataclass
class NamingConfig:
    """Every knob that controls how a tag name is produced."""

    # --- what goes into the tag -------------------------------------------------
    template: str = "{abbr}"
    prefix: str = ""
    suffix: str = ""
    index_start: int = 1
    index_padding: int = 0

    # --- separators -------------------------------------------------------------
    separator: str = "_"
    inner_separator: str = ""  # empty => use `separator`
    column_reference_separator: str = ""  # empty => use separator

    # --- casing / cleaning ------------------------------------------------------
    case: str = CASE_UPPER
    allowed_extra_chars: str = "-"
    invalid_char_pattern: str = ""  # empty => derived from separator + allowed extras
    replace_invalid_with: str = "_"
    collapse_repeated_separators: bool = True
    trim_separator_edges: bool = True

    # --- token handling ---------------------------------------------------------
    drop_stop_words: bool = False
    stop_words: str = "of\nthe\nand\nfor\nwith\n&"
    keep_numbers: bool = True
    allow_plural_matching: bool = False
    dedupe_consecutive_tokens: bool = False

    # --- length / uniqueness ----------------------------------------------------
    max_length: int = 0  # 0 = unlimited
    truncate_mode: str = TRUNCATE_OFF
    uniquify_duplicates: bool = False
    uniquify_format: str = "{tag}{separator}{n}"
    uniquify_start: int = 2

    # --- labels -----------------------------------------------------------------
    output_column: str = "Generated_Tag"
    replace_source_column: bool = False

    # ------------------------------------------------------------------ helpers
    def effective_inner_separator(self) -> str:
        return self.inner_separator if self.inner_separator else self.separator

    def effective_invalid_pattern(self) -> str:
        if self.invalid_char_pattern.strip():
            return self.invalid_char_pattern
        return default_invalid_pattern(self.separator, self.allowed_extra_chars)

    def stop_word_set(self) -> set:
        return {
            line.strip().lower()
            for line in (self.stop_words or "").replace(",", "\n").splitlines()
            if line.strip()
        }

    def to_dict(self) -> Dict[str, object]:
        """Plain dict - used for fingerprints, reports and tests."""
        return asdict(self)

    def replace(self, **changes) -> "NamingConfig":
        """Return a copy with ``changes`` applied (dataclasses.replace helper)."""
        from dataclasses import replace as _replace

        return _replace(self, **changes)

    def fingerprint(self) -> str:
        """Stable signature used to detect 'settings changed -> regenerate'."""
        import json

        return json.dumps(self.to_dict(), sort_keys=True, default=str)

    def issues(self) -> List[str]:
        """Basic self-checks surfaced in the UI before generation."""
        problems: List[str] = []
        if self.separator is None or self.separator.strip() == "":
            problems.append("The separator is empty, so words would run together (e.g. COOLINGTOWER).")
        if self.max_length and self.max_length < 1:
            problems.append("The maximum length must be 1 or more (0 means unlimited).")
        if self.truncate_mode != TRUNCATE_OFF and not self.max_length:
            problems.append("A truncation mode is selected but no maximum length is set.")
        if self.replace_invalid_with == "":
            if not self.collapse_repeated_separators:
                problems.append(
                    "Invalid characters are removed and repeated separators are not collapsed - "
                    "tags may contain double separators."
                )
        pattern = self.effective_invalid_pattern()
        try:
            re.compile(pattern)
        except re.error as exc:
            problems.append(f"The 'invalid characters' pattern is not a valid regular expression: {exc}")
        return problems


# Rebuild-friendly alias so `NamingConfig()` reads nicely in docs.
DEFAULT_NAMING_CONFIG = NamingConfig
