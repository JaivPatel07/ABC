"""End-to-end: reading files, preserving columns/rows and exporting."""

import io

import pandas as pd
import pytest

from tagforge import (
    NamingConfig,
    build_output_frame,
    build_processed_workbook,
    build_report_workbook,
    build_report_sheets,
    default_meta,
    load_table_from_frame,
    read_table,
    run_pipeline,
)
from tagforge.io_utils import FileReadError, list_sheets, sanitize_sheet_name

DATA = Path = __import__("pathlib").Path(__file__).resolve().parent.parent / "samples"


def _run(**config_kwargs):
    frame = pd.read_excel(DATA / "equipment_data.xlsx", sheet_name="Equipment List")
    abbreviations = pd.read_csv(DATA / "company_abbreviations.csv")
    table, _ = load_table_from_frame(abbreviations, "Word / Phrase", "Approved Abbreviation")
    config = NamingConfig(**config_kwargs)
    return frame, table, config, run_pipeline(frame, "Equipment Description", table, config)


def test_rows_and_columns_are_preserved():
    frame, table, config, result = _run()
    output = build_output_frame(frame, result.tags, config, "Equipment Description")

    assert len(output) == len(frame)
    for column in frame.columns:
        assert column in output.columns
    assert "Generated_Tag" in output.columns
    # the new column sits right after the processed one
    position = list(output.columns).index("Generated_Tag")
    assert list(output.columns)[position - 1] == "Equipment Description"
    assert output["Sr No"].tolist() == frame["Sr No"].tolist()


def test_replacing_the_source_column_keeps_the_original_text():
    frame, table, config, result = _run(replace_source_column=True)
    output = build_output_frame(frame, result.tags, config, "Equipment Description")
    assert output["Equipment Description"].tolist() == list(result.tags)
    assert "Equipment Description (original)" in output.columns
    assert output["Equipment Description (original)"].tolist() == frame["Equipment Description"].tolist()


def test_manual_edits_survive_export():
    frame, table, config, _ = _run()
    result = run_pipeline(frame, "Equipment Description", table, config, overrides={0: "MY_TAG"})
    output = build_output_frame(frame, result.tags, config, "Equipment Description")
    assert output["Generated_Tag"].iloc[0] == "MY_TAG"


def test_exported_workbook_can_be_read_back():
    frame, table, config, result = _run(prefix="MERIDIAN", template="{prefix}{abbr}")
    meta = default_meta("equipment_data.xlsx", "Equipment List", "Equipment Description", table,
                        abbr_file="company_abbreviations.csv")
    data = build_processed_workbook(result, frame, meta)

    assert data[:2] == b"PK"  # a real xlsx file
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert "Processed Data" in sheets
    assert "Unmatched Words" in sheets
    assert "Validation Issues" in sheets
    assert "Run Settings" in sheets
    assert "Abbreviations Used" in sheets

    processed = sheets["Processed Data"]
    assert len(processed) == len(frame)
    assert "Generated_Tag" in processed.columns
    assert processed["Generated_Tag"].iloc[0] == "MERIDIAN_CT_NO_2"


def test_usage_report_shows_which_phrases_were_used():
    frame, table, config, result = _run()
    report = build_report_sheets(result, default_meta("f", "s", "c", table))
    used = report["Abbreviations Used"]

    cooling = used[used["Phrase"].str.lower() == "cooling tower"]
    assert not cooling.empty
    assert cooling["Abbreviation"].iloc[0] == "CT"
    assert int(cooling["Times used"].iloc[0]) == 2  # rows 1 and 2
    assert cooling["Source"].iloc[0] == "company list"

    # entries that were never needed are listed with 0 uses
    assert (used["Times used"] == 0).any()


def test_report_workbook_lists_unmatched_words():
    frame, table, config, result = _run()
    meta = default_meta("equipment_data.xlsx", "Equipment List", "Equipment Description", table)
    report = pd.read_excel(io.BytesIO(build_report_workbook(result, meta)), sheet_name=None)
    unmatched = report["Unmatched Words"]
    assert "Unknown word" in unmatched.columns
    assert "Scrubber" in set(unmatched["Unknown word"])
    assert "Occurrences" in unmatched.columns


def test_source_file_is_never_modified(tmp_path):
    source = DATA / "equipment_data.csv"
    before = source.read_bytes()
    frame, table, config, result = _run()
    build_processed_workbook(result, frame, default_meta("x", "y", "z", table))
    assert source.read_bytes() == before


def test_sheets_are_listed_dynamically():
    sheets = list_sheets((DATA / "equipment_data.xlsx").read_bytes(), "equipment_data.xlsx")
    assert sheets == ["Equipment List", "Section List"]
    assert list_sheets((DATA / "equipment_data.csv").read_bytes(), "equipment_data.csv") == []


def test_header_row_can_be_selected():
    default = read_table((DATA / "equipment_data.csv").read_bytes(), "equipment_data.csv")
    shifted = read_table((DATA / "equipment_data.csv").read_bytes(), "equipment_data.csv", header_row=1)
    assert len(shifted) == len(default) - 1
    assert list(shifted.columns) != list(default.columns)


def test_unsupported_file_types_raise_a_helpful_error():
    with pytest.raises(FileReadError) as error:
        read_table(b"not really", "old.xls")
    assert "re-save" in str(error.value)


def test_empty_file_raises_a_helpful_error():
    with pytest.raises(FileReadError):
        read_table(b"", "empty.xlsx")


def test_sheet_names_are_sanitised():
    assert sanitize_sheet_name("Data/Sheet:1") == "Data_Sheet_1"
    assert len(sanitize_sheet_name("x" * 60)) <= 31
    assert sanitize_sheet_name("Data", used=["Data"]) == "Data_2"


def test_messy_sample_data_is_handled():
    frame, table, config, result = _run()
    tags = list(result.tags)
    # messy spacing + casing on row 10 ("   steam   DRUM   pressure   TRANSMITTER  ")
    assert "STM_DRM_PR_TX" in tags
    # the empty row stays empty
    assert tags[27] == ""
    # duplicate source rows produce the same tag and are flagged
    assert tags[4] == tags[5]
    assert result.duplicate_groups
