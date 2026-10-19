"""Report tables: unmatched words, validation issues and run settings."""

from __future__ import annotations

from typing import Dict, List, Sequence

import pandas as pd

from .config import NamingConfig
from .pipeline import PipelineResult
from .text_utils import to_text
from .validation import Issue, issues_to_frame

__all__ = [
    "build_unmatched_frame",
    "build_usage_frame",
    "build_settings_frame",
    "build_summary_frame",
    "build_issue_frame",
    "build_report_sheets",
]


def build_unmatched_frame(result: PipelineResult) -> pd.DataFrame:
    """Unmatched words with counts and where they came from."""
    frame = result.unknown_frame.copy()
    if frame.empty:
        return pd.DataFrame(
            [{"Unknown word": "(none)", "Occurrences": 0, "Example row": "", "Example text": "",
              "Your abbreviation": ""}]
        )
    return frame


def build_usage_frame(result: PipelineResult) -> pd.DataFrame:
    """Which abbreviations were actually used, and how often."""
    counts: Dict[str, int] = {}
    phrases: Dict[str, str] = {}
    for row in result.results:
        for piece in row.pieces:
            if piece.known and piece.phrase:
                key = piece.phrase.lower()
                counts[key] = counts.get(key, 0) + 1
                # `piece.text` is the abbreviation, `piece.phrase` is what matched
                phrases.setdefault(key, piece.phrase)

    table = result.table
    used_rows = []
    for key, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        phrase = phrases.get(key, "")
        entry = table.get(phrase)
        used_rows.append(
            {
                "Phrase": phrase,
                "Abbreviation": entry.abbr if entry else "",
                "Times used": count,
                "Source": entry.source if entry else "",
            }
        )

    unused_rows = []
    used_keys = set(counts)
    for entry in table:
        if entry.key in used_keys:
            continue
        unused_rows.append(
            {"Phrase": entry.phrase, "Abbreviation": entry.abbr, "Times used": 0, "Source": entry.source}
        )

    rows = used_rows + sorted(unused_rows, key=lambda row: row["Phrase"].lower())
    if not rows:
        rows = [{"Phrase": "", "Abbreviation": "", "Times used": 0, "Source": ""}]
    return pd.DataFrame(rows)


def build_settings_frame(config: NamingConfig, meta: Dict[str, object]) -> pd.DataFrame:
    """Human readable snapshot of every setting used for this run."""
    rows: List[Dict[str, object]] = []
    for key, value in meta.items():
        rows.append({"Setting": key, "Value": to_text(value)})
    rows.append({"Setting": "--- naming convention ---", "Value": ""})
    for key, value in config.to_dict().items():
        rows.append({"Setting": key, "Value": to_text(value).replace("\n", ", ")})
    return pd.DataFrame(rows)


def build_summary_frame(result: PipelineResult) -> pd.DataFrame:
    return pd.DataFrame(
        [{"Summary": key, "Count": value} for key, value in result.stats.items()]
    )


def build_issue_frame(issues: Sequence[Issue]) -> pd.DataFrame:
    frame = issues_to_frame(issues)
    if frame.empty:
        return pd.DataFrame(
            [{"Row": "", "Severity": "", "Issue": "No issues found", "Details": "",
              "Original value": "", "Generated tag": ""}]
        )
    return frame


def build_report_sheets(result: PipelineResult, meta: Dict[str, object]) -> Dict[str, pd.DataFrame]:
    """All report sheets, ready to be written into a workbook."""
    return {
        "Summary": build_summary_frame(result),
        "Unmatched Words": build_unmatched_frame(result),
        "Validation Issues": build_issue_frame(result.issues),
        "Abbreviations Used": build_usage_frame(result),
        "Run Settings": build_settings_frame(result.config, meta),
    }
