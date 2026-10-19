"""Build the downloadable files.

Everything is produced in memory - the uploaded file is never opened for
writing, so the original data cannot be modified.
"""

from __future__ import annotations

from datetime import datetime
from typing import Dict

import pandas as pd

from .abbreviations import AbbreviationTable
from .io_utils import dataframe_to_excel_bytes
from .pipeline import PipelineResult, build_output_frame
from .reporting import build_report_sheets

__all__ = [
    "build_processed_workbook",
    "build_report_workbook",
    "build_abbreviations_csv",
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
