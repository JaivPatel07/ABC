"""Build the downloadable files.

Everything is produced in memory - the uploaded file is never opened for
writing, so the original data cannot be modified.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict

import pandas as pd

from .abbreviations import AbbreviationTable
from .column_fill import (
    FillResult,
    build_fill_not_found_frame,
    build_fill_summary_frame,
    build_fill_unknown_words_frame,
)
from .io_utils import dataframe_to_excel_bytes
from .pipeline import PipelineResult, build_output_frame
from .reporting import build_report_sheets

__all__ = [
    "build_processed_workbook",
    "build_report_workbook",
    "build_abbreviations_csv",
    "build_fill_workbook",
    "build_fill_report_workbook",
    "default_meta",
]


def default_meta(
    data_file: str,
    sheet_name: str,
    target_column: str,
    table: AbbreviationTable,
    abbr_file: str = "",
) -> Dict[str, object]:
    """Descriptive information shown on the 'Run Settings' report sheet."""
    return {
        "Generated on": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "Source data file": data_file,
        "Worksheet": sheet_name or "(single sheet / csv)",
        "Processed column": target_column,
        "Rows processed": len(table) and "" or "",  # replaced below
        "Abbreviation file": abbr_file or "(not provided)",
        "Abbreviations available": len(table),
    }


def build_processed_workbook(
    result: PipelineResult,
    source_frame: pd.DataFrame,
    meta: Dict[str, object],
    data_sheet_name: str = "Processed Data",
    include_report: bool = True,
) -> bytes:
    """The main deliverable: original data + generated tags (+ report sheets)."""
    meta = dict(meta)
    meta["Rows processed"] = len(source_frame)

    output = build_output_frame(
        source_frame, result.tags, result.config, result.target_column
    )
    sheets: Dict[str, pd.DataFrame] = {data_sheet_name: output}
    if include_report:
        sheets.update(build_report_sheets(result, meta))
    return dataframe_to_excel_bytes(sheets)


def build_report_workbook(result: PipelineResult, meta: Dict[str, object]) -> bytes:
    """Standalone validation / unmatched-word report."""
    return dataframe_to_excel_bytes(build_report_sheets(result, meta))


def build_abbreviations_csv(table: AbbreviationTable) -> bytes:
    """The abbreviation list including the user's additions, as CSV."""
    return table.to_csv_bytes()


# ---------------------------------------------------------------------------
# column-filler mode
# ---------------------------------------------------------------------------
def build_fill_settings_frame(result: FillResult) -> pd.DataFrame:
    """A short 'what was used' sheet for a fill run."""
    config = result.config
    rows = [
        ("Generated on", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        ("Rows in the file", result.rows),
        ("Columns filled", len(result.columns)),
        ("New columns created at the end", len(result.new_columns)),
        ("Cells with an abbreviation", result.filled_cells),
        ("Cells with unknown words kept as typed", result.partial_cells),
        ("Cells with no abbreviation at all (original kept)", result.kept_cells),
        ("Cells left empty (no abbreviation)", result.not_found_cells),
        ("Empty source cells", result.empty_cells),
        ("Default matching rule", config.match_mode),
        ("Letter case", config.case),
        ("When no abbreviation is found", config.when_not_found),
        ("Match simple plurals", "Yes" if config.allow_plural_matching else "No"),
        ("Keep numbers in 'every word' mode", "Yes" if config.keep_numbers else "No"),
        ("Separator between abbreviations", config.separator),
        ("Abbreviations in the list", len(result.table)),
    ]
    return pd.DataFrame(rows, columns=["Setting", "Value"])


def _fill_report_sheets(result: FillResult) -> Dict[str, pd.DataFrame]:
    not_found = build_fill_not_found_frame(result)
    if not_found.empty:
        not_found = pd.DataFrame(
            [{"Info": "Every word of every value found an abbreviation in the list."}]
        )
    unknown_words = build_fill_unknown_words_frame(result)
    if unknown_words.empty:
        unknown_words = pd.DataFrame(
            [{"Info": "Every word of every value found an abbreviation in the list."}]
        )
    return {
        "Summary": build_fill_summary_frame(result),
        "Not Found": not_found,
        "Unknown Words": unknown_words,
        "Run Settings": build_fill_settings_frame(result),
    }


def build_fill_workbook(
    result: FillResult,
    data_sheet_name: str = "Filled Data",
    include_report: bool = True,
) -> bytes:
    """The main deliverable of the filler: original data, target columns filled."""
    sheets: Dict[str, pd.DataFrame] = {data_sheet_name: result.output_frame}
    if include_report:
        sheets.update(_fill_report_sheets(result))
    return dataframe_to_excel_bytes(sheets)


def build_fill_report_workbook(result: FillResult) -> bytes:
    """Standalone summary / not-found report for a fill run."""
    return dataframe_to_excel_bytes(_fill_report_sheets(result))
