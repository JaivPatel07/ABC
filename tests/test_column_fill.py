"""Tests for the "fill abbreviations into columns" engine.

The important guarantee is the user's rule: **if a value has no abbreviation,
the new cell stays empty** - the original text is never copied into it.
"""

import io

import pandas as pd
import pytest

from tagforge.abbreviations import DROP_MARKER
from tagforge.column_fill import (
    CASE_LOWER,
    CASE_UPPER,
    MATCH_ALL_WORDS,
    MATCH_ANY,
    MATCH_EXACT,
    NOT_FOUND_KEEP,
    STATUS_EMPTY,
    STATUS_FILLED,
    STATUS_KEPT,
    STATUS_NOT_FOUND,
    FillConfig,
    FillMapping,
    build_fill_not_found_frame,
    build_fill_summary_frame,
    find_match,
    run_column_fill,
    unique_column_name,
)
from tagforge.exporters import build_fill_report_workbook, build_fill_workbook


@pytest.fixture
def frame() -> pd.DataFrame:
    """A small main sheet with several columns of text."""
    return pd.DataFrame(
        {
            "Equipment": [
                "Cooling Tower No 2",
                "Boiler Feed Water Pump B",
                "Agitator",
                "",
            ],
            "Parameter": ["Temperature", "Flow", "", "Pressure Indicator"],
            "Qty": [1, 2, 3, 4],
        }
    )


# ---------------------------------------------------------------------------
# matching rules
# ---------------------------------------------------------------------------
def test_any_match_takes_the_longest_phrase_anywhere(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT", "BFW", "", ""]


def test_any_match_ignores_unknown_words_before_the_match(sample_table):
    frame = pd.DataFrame({"Equipment": ["Scrubber Recirculation Pump"]})
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    assert result.output_frame["Equipment Abbr"].tolist() == ["PMP"]


def test_missing_abbreviation_leaves_the_cell_empty(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    cells = result.columns[0].cells
    assert cells[2].status == STATUS_NOT_FOUND
    assert cells[2].abbreviation == ""
    assert cells[3].status == STATUS_EMPTY
    assert cells[3].abbreviation == ""
    # the original text is never copied into the new column
    assert "Agitator" not in result.output_frame["Equipment Abbr"].tolist()


def test_whole_cell_must_match_exactly(sample_table):
    frame = pd.DataFrame({"Equipment": ["Cooling Tower", "Cooling Tower No 2", "Temperature"]})
    config = FillConfig(match_mode=MATCH_EXACT)
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT", "", "TMP"]


def test_whole_cell_ignores_case_and_extra_spaces(sample_table):
    frame = pd.DataFrame({"Equipment": ["  cooling   TOWER "]})
    config = FillConfig(match_mode=MATCH_EXACT)
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT"]


def test_every_word_must_match(table):
    frame = pd.DataFrame({"Equipment": ["Boiler Feed Water Pump", "Cooling Tower No 2", "Agitator Pump"]})
    config = FillConfig(match_mode=MATCH_ALL_WORDS, separator="_")
    result = run_column_fill(frame, table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["BFW_PMP", "CT_NO_2", ""]


def test_one_unknown_word_empties_the_whole_all_words_cell(table):
    frame = pd.DataFrame({"Equipment": ["Pump Agitator"]})
    config = FillConfig(match_mode=MATCH_ALL_WORDS)
    result = run_column_fill(frame, table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == [""]
    assert result.not_found_cells == 1


def test_find_match_returns_none_for_unknown_text(sample_table):
    assert find_match(sample_table, "Agitator", MATCH_ANY) is None
    assert find_match(sample_table, "", MATCH_ANY) is None


def test_drop_marker_never_writes_the_marker(sample_table):
    sample_table.add("Agitator", DROP_MARKER, source="user added")
    result = run_column_fill(
        pd.DataFrame({"Equipment": ["Agitator"]}), sample_table, [FillMapping("Equipment")], FillConfig()
    )
    assert result.output_frame["Equipment Abbr"].tolist() == [""]


# ---------------------------------------------------------------------------
# output layout
# ---------------------------------------------------------------------------
def test_new_columns_are_inserted_next_to_their_source(frame, sample_table):
    mappings = [FillMapping("Equipment"), FillMapping("Parameter")]
    result = run_column_fill(frame, sample_table, mappings, FillConfig())
    assert list(result.output_frame.columns) == [
        "Equipment",
        "Equipment Abbr",
        "Parameter",
        "Parameter Abbr",
        "Qty",
    ]
    assert len(result.output_frame) == len(frame)


def test_source_frame_is_never_modified(frame, sample_table):
    before = frame.copy(deep=True)
    run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    pd.testing.assert_frame_equal(frame, before)


def test_two_mappings_of_the_same_column_keep_their_order(frame, sample_table):
    mappings = [FillMapping("Equipment", output="Short"), FillMapping("Equipment", output="Exact")]
    result = run_column_fill(frame, sample_table, mappings, FillConfig())
    assert list(result.output_frame.columns) == ["Equipment", "Short", "Exact", "Parameter", "Qty"]


def test_existing_column_is_never_overwritten(frame, sample_table):
    frame = frame.copy()
    frame["Equipment Abbr"] = ["keep 1", "keep 2", "keep 3", "keep 4"]
    result = run_column_fill(
        frame, sample_table, [FillMapping("Equipment", output="Equipment Abbr")], FillConfig()
    )
    assert result.columns[0].output_name == "Equipment Abbr (2)"
    assert frame["Equipment Abbr"].tolist() == ["keep 1", "keep 2", "keep 3", "keep 4"]


def test_unique_column_name_is_case_insensitive():
    assert unique_column_name(["Code"], "code") == "code (2)"
    assert unique_column_name(["Code", "code (2)"], "code") == "code (3)"
    assert unique_column_name([], "Code") == "Code"


def test_no_mappings_returns_a_copy(frame, sample_table):
    result = run_column_fill(frame, sample_table, [], FillConfig())
    pd.testing.assert_frame_equal(result.output_frame, frame)


def test_unknown_source_column_raises(frame, sample_table):
    with pytest.raises(KeyError, match="not found"):
        run_column_fill(frame, sample_table, [FillMapping("Does not exist")], FillConfig())


def test_empty_output_name_falls_back_to_the_suffix(frame, sample_table):
    result = run_column_fill(
        frame, sample_table, [FillMapping("Equipment", output="")], FillConfig(output_suffix=" Code")
    )
    assert result.columns[0].output_name == "Equipment Code"


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
def test_letter_case_setting(frame, sample_table):
    lower = run_column_fill(
        frame, sample_table, [FillMapping("Equipment")], FillConfig(case=CASE_LOWER)
    )
    assert lower.output_frame["Equipment Abbr"].iloc[0] == "ct"
    upper = run_column_fill(
        frame, sample_table, [FillMapping("Equipment")], FillConfig(case=CASE_UPPER)
    )
    assert upper.output_frame["Equipment Abbr"].iloc[0] == "CT"


def test_plural_matching_is_off_by_default(sample_table):
    frame = pd.DataFrame({"Equipment": ["Pumps", "Pump"]})
    plain = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    assert plain.output_frame["Equipment Abbr"].tolist() == ["", "PMP"]

    plural = run_column_fill(
        frame, sample_table, [FillMapping("Equipment")], FillConfig(allow_plural_matching=True)
    )
    assert plural.output_frame["Equipment Abbr"].tolist() == ["PMP", "PMP"]


def test_not_found_can_keep_the_original_text_when_asked(sample_table):
    frame = pd.DataFrame({"Equipment": ["Agitator"]})
    config = FillConfig(when_not_found=NOT_FOUND_KEEP)
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["Agitator"]
    assert result.columns[0].cells[0].status == STATUS_KEPT


def test_per_column_rule_overrides_the_default(sample_table):
    frame = pd.DataFrame({"Equipment": ["Cooling Tower", "Cooling Tower No 2"]})
    config = FillConfig(match_mode=MATCH_ANY)
    mapping = FillMapping("Equipment", match_mode=MATCH_EXACT)
    result = run_column_fill(frame, sample_table, [mapping], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT", ""]


# ---------------------------------------------------------------------------
# reports and export
# ---------------------------------------------------------------------------
def test_summary_counts(frame, sample_table):
    mappings = [FillMapping("Equipment"), FillMapping("Parameter")]
    result = run_column_fill(frame, sample_table, mappings, FillConfig())
    summary = build_fill_summary_frame(result)

    assert list(summary["Source column"]) == ["Equipment", "Parameter"]
    equipment = summary.iloc[0]
    assert equipment["Filled"] == 2
    assert equipment["Left empty (no abbreviation)"] == 1
    assert equipment["Empty source cell"] == 1

    parameter = summary.iloc[1]
    assert parameter["Filled"] == 2  # Temperature, Pressure Indicator
    assert parameter["Left empty (no abbreviation)"] == 1  # Flow
    assert parameter["Empty source cell"] == 1


def test_not_found_report_lists_distinct_values(frame, sample_table):
    result = run_column_fill(
        frame, sample_table, [FillMapping("Equipment"), FillMapping("Parameter")], FillConfig()
    )
    report = build_fill_not_found_frame(result)
    values = set(report["Value with no abbreviation"])
    assert "Agitator" in values
    assert "Flow" in values
    assert 2 <= len(report)  # one row per column/value pair


def test_not_found_report_is_empty_when_everything_matches(sample_table):
    frame = pd.DataFrame({"Equipment": ["Pump", "Cooling Tower"]})
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    report = build_fill_not_found_frame(result)
    assert report.empty
    assert list(report.columns) == [
        "Source column",
        "Value with no abbreviation",
        "Occurrences",
        "First row",
    ]


def test_fill_workbook_round_trip(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    data = build_fill_workbook(result)
    assert data[:2] == b"PK"

    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert "Filled Data" in sheets
    assert {"Summary", "Not Found", "Run Settings"}.issubset(sheets)
    filled = sheets["Filled Data"]
    assert len(filled) == len(frame)
    assert "Equipment Abbr" in filled.columns
    assert filled["Equipment Abbr"].iloc[0] == "CT"


def test_fill_workbook_without_reports_has_one_sheet(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    data = build_fill_workbook(result, include_report=False)
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert list(sheets) == ["Filled Data"]


def test_fill_report_workbook(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    data = build_fill_report_workbook(result)
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert set(sheets) == {"Summary", "Not Found", "Run Settings"}


def test_statuses_are_reported(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    statuses = [cell.status for cell in result.columns[0].cells]
    assert statuses == [STATUS_FILLED, STATUS_FILLED, STATUS_NOT_FOUND, STATUS_EMPTY]


def test_any_match_prefers_the_longest_phrase_then_the_earliest(table):
    frame = pd.DataFrame({"Text": ["Tower Cooling", "Cooling Tower"]})
    result = run_column_fill(frame, table, [FillMapping("Text")], FillConfig())
    # "Tower" (1 word) and "Cooling" (1 word) are both matches in the first
    # cell -> the earliest one wins. In the second cell "Cooling Tower" (2
    # words) beats both single words.
    assert result.output_frame["Text Abbr"].tolist() == ["TWR", "CT"]
