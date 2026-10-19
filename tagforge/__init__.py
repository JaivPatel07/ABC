"""TagForge - abbreviation filler and industrial tag-name generator.

The package is split into small, testable pieces:

===========================  ==================================================
module                       responsibility
===========================  ==================================================
:mod:`tagforge.text_utils`   cleaning and tokenising text
:mod:`tagforge.abbreviations` the company abbreviation list and phrase matching
:mod:`tagforge.column_fill`  fill columns; empty cell when there is no match
:mod:`tagforge.config`       the naming convention (template, separators, case)
:mod:`tagforge.taggen`       text -> tag name
:mod:`tagforge.validation`   empty / unknown / duplicate / invalid checks
:mod:`tagforge.pipeline`     ties everything together for a whole DataFrame
:mod:`tagforge.reporting`    unmatched-word and issue reports
:mod:`tagforge.exporters`    builds the downloadable workbooks
:mod:`tagforge.io_utils`     dynamic reading/writing of .xlsx and .csv
===========================  ==================================================

Typical use of the filler::

    from tagforge import FillConfig, FillMapping, run_column_fill

    result = run_column_fill(df, table, [FillMapping("Equipment Description")], FillConfig())
    result.output_frame          # original columns + "Equipment Description Abbr"

Typical use of the tag wizard::

    from tagforge import AbbreviationTable, NamingConfig, run_pipeline

    table, report = AbbreviationTable.from_file(...)   # see abbreviations.py
    config = NamingConfig(separator="_", prefix="PLANT1")
    result = run_pipeline(df, "Equipment Description", table, config)
    df["Tag"] = result.tags
"""

from .abbreviations import (
    DROP_MARKER,
    SOURCE_USER,
    Abbreviation,
    AbbreviationTable,
    LoadReport,
    load_table_from_frame,
)
from .column_fill import (
    FillConfig,
    FillMapping,
    FillResult,
    build_fill_not_found_frame,
    build_fill_summary_frame,
    run_column_fill,
)
from .config import (
    CASE_LOWER,
    CASE_OPTIONS,
    CASE_PRESERVE,
    CASE_UPPER,
    TEMPLATE_PRESETS,
    NamingConfig,
    TemplateError,
    validate_template,
)
from .detect import guess_column, guess_pair, guess_source_columns
from .exporters import (
    build_abbreviations_csv,
    build_fill_report_workbook,
    build_fill_workbook,
    build_processed_workbook,
    build_report_workbook,
    default_meta,
)
from .io_utils import (
    SUPPORTED_EXTENSIONS,
    FileReadError,
    dataframe_to_excel_bytes,
    list_sheets,
    read_table,
)
from .pipeline import PipelineResult, build_output_frame, run_pipeline
from .reporting import build_report_sheets
from .taggen import RowResult, TagGenerator
from .validation import Issue, check_results

__version__ = "1.1.0"

__all__ = [
    "FillConfig",
    "FillMapping",
    "FillResult",
    "run_column_fill",
    "build_fill_summary_frame",
    "build_fill_not_found_frame",
    "build_fill_workbook",
    "build_fill_report_workbook",
    "guess_source_columns",
    "Abbreviation",
    "DROP_MARKER",
    "SOURCE_USER",
    "AbbreviationTable",
    "LoadReport",
    "load_table_from_frame",
    "NamingConfig",
    "TemplateError",
    "validate_template",
    "TEMPLATE_PRESETS",
    "CASE_OPTIONS",
    "CASE_UPPER",
    "CASE_LOWER",
    "CASE_PRESERVE",
    "guess_column",
    "guess_pair",
    "TagGenerator",
    "RowResult",
    "PipelineResult",
    "run_pipeline",
    "build_output_frame",
    "build_report_sheets",
    "build_processed_workbook",
    "build_report_workbook",
    "build_abbreviations_csv",
    "default_meta",
    "check_results",
    "Issue",
    "read_table",
    "list_sheets",
    "dataframe_to_excel_bytes",
    "FileReadError",
    "SUPPORTED_EXTENSIONS",
    "__version__",
]
