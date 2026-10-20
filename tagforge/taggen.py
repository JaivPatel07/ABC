"""Turn free text into a tag name.

The generator is deliberately dumb in one specific way: **if a word is not in
the company abbreviation list it is kept exactly as written and reported.**  No
abbreviation is ever invented.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .abbreviations import DROP_MARKER, AbbreviationTable
from .config import (
    CASE_LOWER,
    CASE_UPPER,
    TRUNCATE_OFF,
    TRUNCATE_SEPARATOR,
    NamingConfig,
    _PLACEHOLDER_RE,
)
from .text_utils import (
    collapse_repeats,
    is_code_token,
    is_single_letter_token,
    normalize_code_token,
    singular_candidates,
    to_text,
    tokenize,
    trim_edges,
    unique_preserving_order,
)

__all__ = ["MatchedPiece", "RowResult", "TagGenerator", "render_template"]

_EMPTY = object()


@dataclass
class MatchedPiece:
    """One piece of the generated abbreviation."""

    text: str
    known: bool
    phrase: str = ""
    is_number: bool = False
    dropped: bool = False
    note: str = ""

    def __str__(self) -> str:  # pragma: no cover - debugging helper
        return self.text


@dataclass
class RowResult:
    """Everything the app knows about one generated row."""

    row_id: int
    original: str
    tag: str
    pieces: List[MatchedPiece] = field(default_factory=list)
    unknown_words: List[str] = field(default_factory=list)
    notes: List[str] = field(default_factory=list)
    edited: bool = False

    @property
    def is_empty(self) -> bool:
        return not self.tag.strip()

    @property
    def status(self) -> str:
        if self.is_empty:
            return "Empty"
        if self.unknown_words:
            return "Unknown words"
        return "OK"

    @property
    def unknown_text(self) -> str:
        return ", ".join(self.unknown_words)


def render_template(
    template: str,
    values: Dict[str, str],
    separator: str,
    context: Optional[Dict[str, str]] = None,
) -> str:
    """Fill ``template`` using ``values`` (``abbr``/``prefix``/... ) and ``context``.

    Two placeholders written *next to each other* (``{prefix}{abbr}``) are joined
    with ``separator``.  A separator typed by the user (``{prefix}-{abbr}``) is
    kept exactly as typed.
    """
    context = context or {}
    chunks = re.split(r"(\{[^}]*\})", template or "")
    parts: List[str] = []

    def resolve(chunk: str) -> str:
        match = _PLACEHOLDER_RE.fullmatch(chunk)
        if not match:
            return chunk
        name = match.group(1).strip().lower()
        spec = (match.group(2) or "").strip()
        if name in ("col", "column", "field"):
            column = spec.strip("'\"")
            return context.get(column, "")
        if name == "index":
            raw = values.get("index", "")
            try:
                number = int(raw)
            except (TypeError, ValueError):
                return raw
            if spec:
                try:
                    return format(number, spec)
                except (ValueError, TypeError):
                    return str(number)
            return str(number)
        if name in values:
            return values[name]
        return chunk  # unknown placeholder: keep it visible instead of guessing

    for position, chunk in enumerate(chunks):
        if not chunk:
            # Gap between two placeholders -> insert the configured separator.
            if 0 < position < len(chunks) - 1:
                parts.append(separator)
            continue
        if chunk.startswith("{") and chunk.endswith("}"):
            parts.append(resolve(chunk))
        else:
            parts.append(chunk)

    return "".join(parts)


class TagGenerator:
    """Generate tags for a whole column using a company abbreviation list."""

    def __init__(
        self,
        table: AbbreviationTable,
        config: NamingConfig,
        context_columns: Optional[Sequence[str]] = None,
    ) -> None:
        self.table = table
        self.config = config
        self.context_columns = list(context_columns or [])
        self._context_cache: Optional[Dict[str, List[str]]] = None
        self._context_frame_id: Optional[int] = None

    # ------------------------------------------------------------------ helpers
    def _template_columns(self) -> List[str]:
        """Names of the file columns referenced by ``{col:Name}`` placeholders."""
        wanted: List[str] = []
        for chunk in re.split(r"(\{[^}]*\})", self.config.template or ""):
            if not (chunk.startswith("{") and chunk.endswith("}")):
                continue
            match = _PLACEHOLDER_RE.fullmatch(chunk)
            if not match:
                continue
            name = (match.group(1) or "").strip().lower()
            column = (match.group(2) or "").strip().strip("'\"")
            if name in ("col", "column", "field") and column:
                wanted.append(column)
        return wanted

    def _prepare_context(self, frame: Optional[pd.DataFrame]) -> None:
        """Cache the columns referenced by ``{col:...}`` as plain lists."""
        self.context_columns = unique_preserving_order(
            list(self.context_columns) + self._template_columns()
        )
        if frame is None:
            self._context_cache = {}
            self._context_frame_id = None
            return
        frame_id = id(frame)
        if self._context_cache is not None and self._context_frame_id == frame_id:
            return
        cache: Dict[str, List[str]] = {}
        for column in self.context_columns:
            if column in frame.columns:
                cache[column] = [to_text(value) for value in frame[column].tolist()]
        self._context_cache = cache
        self._context_frame_id = frame_id

    # ------------------------------------------------------------- single value
    def build_pieces(self, text: str) -> List[MatchedPiece]:
        """Split ``text`` into abbreviation pieces (longest phrase match wins)."""
        config = self.config
        tokens = tokenize(to_text(text))
        keys = [token.key for token in tokens]
        stop_words = config.stop_word_set() if config.drop_stop_words else set()

        pieces: List[MatchedPiece] = []
        index = 0
        while index < len(tokens):
            token = tokens[index]
            hit = self.table.lookup(keys, index, allow_plurals=config.allow_plural_matching)
            if hit is not None:
                size, abbr, matched_phrase = hit
                note = ""
                if config.allow_plural_matching and token.key != matched_phrase.lower() and size == 1:
                    if singular_candidates(token.text) and matched_phrase.lower() in singular_candidates(token.text):
                        note = "plural"
                if abbr == DROP_MARKER:
                    # user explicitly asked for this word to be dropped
                    pieces.append(MatchedPiece("", True, matched_phrase, dropped=True, note="dropped"))
                else:
                    pieces.append(MatchedPiece(abbr, True, matched_phrase, note=note))
                index += size
                continue

            if token.kind == "number" and config.keep_numbers:
                pieces.append(MatchedPiece(token.text, True, "", is_number=True))
                index += 1
                continue

            if is_code_token(token.text):
                pieces.append(MatchedPiece(normalize_code_token(token.text), True, "", is_number=True, note="code"))
                index += 1
                continue

            if is_single_letter_token(token.text):
                pieces.append(MatchedPiece(token.text, True, ""))
                index += 1
                continue

            if token.key in stop_words:
                pieces.append(MatchedPiece(token.text, True, "", dropped=True))
                index += 1
                continue

            pieces.append(MatchedPiece(token.text, False, ""))
            index += 1

        return pieces

    def generate_one(self, value: object, row_id: int = 0, context: Optional[Dict[str, str]] = None) -> RowResult:
        """Generate the tag for a single cell value."""
        config = self.config
        original = to_text(value)
        context = context or {}

        # Nothing in -> nothing out.  An empty cell must never produce a
        # half-built tag such as "PLANT_" just because a prefix is configured.
        if not original:
            return RowResult(
                row_id=row_id,
                original="",
                tag="",
                pieces=[],
                unknown_words=[],
                notes=["empty source value - no tag generated"],
            )

        pieces = self.build_pieces(original)
        unknown_words = unique_preserving_order(
            [piece.text for piece in pieces if not piece.known]
        )

        used = [piece for piece in pieces if not piece.dropped and piece.text]
        if config.dedupe_consecutive_tokens:
            deduped: List[MatchedPiece] = []
            for piece in used:
                if deduped and deduped[-1].text == piece.text:
                    continue
                deduped.append(piece)
            used = deduped

        inner_separator = config.effective_inner_separator()
        abbr_text = inner_separator.join(piece.text for piece in used)
        original_clean = original

        values = {
            "abbr": abbr_text,
            "original": original_clean,
            "prefix": to_text(config.prefix),
            "suffix": to_text(config.suffix),
            "index": str(config.index_start + row_id),
        }
        if config.index_padding and "{" in config.template:
            # honour a padding setting even without an explicit format spec
            template = re.sub(
                r"\{index(?::(\d+)d)?\}",
                lambda m: "{index:0" + str(m.group(1) or config.index_padding) + "d}",
                config.template,
            )
        else:
            template = config.template

        tag = render_template(template, values, config.separator, context)
        tag, notes = self.clean(tag)

        notes = list(notes)
        if unknown_words:
            notes.append("unmatched: " + ", ".join(unknown_words))
        if not original:
            notes.append("empty source value")

        return RowResult(
            row_id=row_id,
            original=original,
            tag=tag,
            pieces=pieces,
            unknown_words=unknown_words,
            notes=notes,
        )

    # ------------------------------------------------------------------ cleanup
    def clean(self, tag: str) -> tuple:
        """Apply casing, invalid-character and length rules.  Returns ``(tag, notes)``."""
        config = self.config
        notes: List[str] = []
        tag = to_text(tag)

        if config.case == CASE_LOWER:
            tag = tag.lower()
        elif config.case == CASE_UPPER:
            tag = tag.upper()

        pattern = config.effective_invalid_pattern()
        try:
            compiled = re.compile(pattern)
        except re.error:
            compiled = re.compile(r"[^A-Za-z0-9_]")
            notes.append("invalid-character pattern was invalid, used the default")
        tag = compiled.sub(config.replace_invalid_with, tag)

        if config.collapse_repeated_separators and config.separator:
            tag = collapse_repeats(tag, config.separator)
        if config.trim_separator_edges:
            tag = trim_edges(tag, config.separator, config.allowed_extra_chars)
        tag = tag.strip()

        if config.max_length and len(tag) > config.max_length:
            if config.truncate_mode == TRUNCATE_OFF:
                # the user only wants to be warned (see validation report)
                notes.append(f"longer than {config.max_length} characters")
            else:
                tag = self._truncate(tag, config)
                notes.append(f"truncated to {config.max_length} characters")

        return tag, notes

    @staticmethod
    def _truncate(tag: str, config: NamingConfig) -> str:
        limit = int(config.max_length)
        if config.truncate_mode == TRUNCATE_SEPARATOR and config.separator:
            head = tag[:limit]
            cut = head.rfind(config.separator)
            if cut > 0:
                return head[:cut]
        return tag[:limit]

    # ------------------------------------------------------------------- series
    def generate_series(
        self,
        values: Sequence[object],
        context_frame: Optional[pd.DataFrame] = None,
        overrides: Optional[Dict[int, str]] = None,
        progress_callback=None,
    ) -> List[RowResult]:
        """Generate tags for a whole column.

        ``overrides`` maps a row position to a manually edited tag; those rows
        keep their edit instead of being regenerated.
        """
        overrides = overrides or {}
        self._prepare_context(context_frame)
        cache = self._context_cache or {}
        results: List[RowResult] = []
        total = len(values)
        step = max(1, total // 100)

        for row_id, value in enumerate(values):
            context = {column: rows[row_id] for column, rows in cache.items() if row_id < len(rows)}
            result = self.generate_one(value, row_id=row_id, context=context)
            if row_id in overrides:
                override = to_text(overrides[row_id])
                if override != result.tag:
                    result.tag = override
                    result.edited = True
                    result.notes.append("manually edited")
            results.append(result)
            if progress_callback and (row_id % step == 0 or row_id == total - 1):
                progress_callback(row_id + 1, total)

        return results

    # ------------------------------------------------------------------ preview
    def preview_samples(self, values: Sequence[object], limit: int = 3) -> List[RowResult]:
        """Quick preview used by the settings screen."""
        samples: List[RowResult] = []
        seen = set()
        for value in list(values)[:200]:
            text = to_text(value)
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            samples.append(self.generate_one(text, row_id=len(samples)))
            if len(samples) >= limit:
                break
        return samples
