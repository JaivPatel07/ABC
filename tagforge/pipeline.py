"""Orchestration: one DataFrame in, tags + reports out.

``run_pipeline`` is the single entry point used by the Streamlit app (and by the
tests).  It never mutates the input DataFrame.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .abbreviations import AbbreviationTable
from .config import NamingConfig
from .taggen import RowResult, TagGenerator
from .text_utils import unique_preserving_order
from .validation import (
    CODE_DUPLICATE,
    Issue,
    check_results,
    find_duplicate_tags,
    summarise_issues,
    uniquify_tags,
)

__all__ = ["PipelineResult", "run_pipeline", "build_unknown_frame", "build_preview_frame", "build_output_frame"]

ROW_ID_COLUMN = "_row_id"


@dataclass
class PipelineResult:
    """Everything the UI needs to show a preview and an export."""

    results: List[RowResult]
    tags: pd.Series
    issues: List[Issue]
    unknown_frame: pd.DataFrame
    preview_frame: pd.DataFrame
    stats: Dict[str, int]
    target_column: str
    config: NamingConfig
    table: AbbreviationTable

    @property
    def duplicate_groups(self) -> Dict[str, List[int]]:
        return find_duplicate_tags([result.tag for result in self.results])


def run_pipeline(
    frame: pd.DataFrame,
    target_column: str,
    table: AbbreviationTable,
    config: NamingConfig,
    overrides: Optional[Dict[int, str]] = None,
    progress_callback=None,
) -> PipelineResult:
    """Generate tags for ``frame[target_column]`` using ``table`` and ``config``."""
    if frame is None or target_column not in getattr(frame, "columns", []):
        available = ", ".join(map(str, getattr(frame, "columns", []))) or "none"
        raise KeyError(
            f"Column '{target_column}' was not found in the data file. Available columns: {available}."
        )

    overrides = dict(overrides or {})
    values = frame[target_column].tolist()

    generator = TagGenerator(table, config)
    results = generator.generate_series(values, frame, overrides=overrides, progress_callback=progress_callback)

    if config.uniquify_duplicates:
        unique = uniquify_tags([result.tag for result in results], config)
        for result, new_tag in zip(results, unique):
            if new_tag != result.tag and result.tag:
                result.tag = new_tag
                result.notes.append("numbered to remove duplicate")

    tags = pd.Series([result.tag for result in results], index=frame.index, name=config.output_column)
    issues = check_results(results, config, values)
    unknown_frame = build_unknown_frame(results)
    preview_frame = build_preview_frame(values, results, config)
    stats = build_stats(results, issues, unknown_frame)

    return PipelineResult(
        results=results,
        tags=tags,
        issues=issues,
        unknown_frame=unknown_frame,
        preview_frame=preview_frame,
        stats=stats,
        target_column=target_column,
        config=config,
        table=table,
    )


def build_stats(
    results: Sequence[RowResult],
    issues: Sequence[Issue],
    unknown_frame: pd.DataFrame,
) -> Dict[str, int]:
    counts = summarise_issues(issues)
    filled = sum(1 for result in results if result.tag.strip())
    return {
        "rows": len(results),
        "tags generated": filled,
        "empty values": sum(1 for result in results if not result.original.strip()),
        "rows with unknown words": sum(1 for result in results if result.unknown_words),
        "distinct unknown words": len(unknown_frame),
        "duplicate tags": counts.get(CODE_DUPLICATE, 0),
        "manually edited": sum(1 for result in results if result.edited),
    }


def build_unknown_frame(results: Sequence[RowResult]) -> pd.DataFrame:
    """Aggregate every word that is missing from the abbreviation list."""
    order: List[str] = []
    counts: Dict[str, int] = {}
    examples: Dict[str, tuple] = {}

    for result in results:
        for word in result.unknown_words:
            key = word.lower()
            if key not in counts:
                counts[key] = 0
                order.append(word)
                examples[key] = (result.row_id + 1, result.original)
            counts[key] += 1

    rows = [
        {
            "Unknown word": word,
            "Occurrences": counts[word.lower()],
            "Example row": examples[word.lower()][0],
            "Example text": examples[word.lower()][1],
            "Your abbreviation": "",
        }
        for word in sorted(order, key=lambda w: (-counts[w.lower()], w.lower()))
    ]
    if not rows:
        return pd.DataFrame(
            columns=["Unknown word", "Occurrences", "Example row", "Example text", "Your abbreviation"]
        )
    return pd.DataFrame(rows)


def build_preview_frame(
    values: Sequence[object],
    results: Sequence[RowResult],
    config: NamingConfig,
) -> pd.DataFrame:
    """Side-by-side ``original -> generated tag`` table (editable in the UI)."""
    rows = []
    for result in results:
        rows.append(
            {
                ROW_ID_COLUMN: result.row_id,
                "Row": result.row_id + 1,
                "Original value": result.original,
                config.output_column: result.tag,
                "Unknown words": result.unknown_text,
                "Status": result.status,
                "Notes": "; ".join(unique_preserving_order(result.notes)),
            }
        )
    if not rows:
        return pd.DataFrame(
            columns=[ROW_ID_COLUMN, "Row", "Original value", config.output_column, "Unknown words", "Status", "Notes"]
        )
    return pd.DataFrame(rows)


def build_output_frame(
    source: pd.DataFrame,
    tags: pd.Series,
    config: NamingConfig,
    target_column: str,
) -> pd.DataFrame:
    """Copy of the uploaded data with the generated tags added.

    * default: a new column is inserted right after the processed column,
    * ``config.replace_source_column``: the processed column is replaced and the
      original text is kept in ``"<column> (original)"`` so nothing is lost.
    """
    output = source.copy()
    tags = pd.Series(list(tags), index=output.index)

    if config.replace_source_column:
        original_name = f"{target_column} (original)"
        position = output.columns.get_loc(target_column)
        output.insert(position + 1, original_name, output[target_column])
        output[target_column] = tags
    else:
        position = output.columns.get_loc(target_column)
        output.insert(position + 1, config.output_column, tags)

    return output
