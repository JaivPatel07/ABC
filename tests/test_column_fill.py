"""Tests for the "fill abbreviations into columns" engine.

The important guarantees are the user's rules: **the abbreviation is
written into the target column the user selected** (an existing column, or
one explicitly created at the end of the file), **words that have no
abbreviation are kept as typed**, and **a value where no word at all has an
abbreviation keeps its original text** - nothing is silently emptied.  Every
word that has no abbreviation is listed in the reports.
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
    STATUS_PARTIAL,
    FillConfig,
    FillMapping,
    build_fill_not_found_frame,
    build_fill_summary_frame,
    build_fill_unknown_words_frame,
    find_match,
    run_column_fill,
    unique_column_name,
)
from tagforge.detect import guess_fill_pairs
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
            "Equipment Abbr": ["", "", "", ""],
            "Parameter": ["Temperature", "Flow", "", "Pressure Indicator"],
            "Parameter Abbr": ["", "", "", ""],
            "Qty": [1, 2, 3, 4],
        }
    )


# ---------------------------------------------------------------------------
# matching rules
# ---------------------------------------------------------------------------
def test_any_match_takes_the_longest_phrase_anywhere(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig(match_mode=MATCH_ANY))
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT", "BFW", "", ""]


def test_any_match_ignores_unknown_words_before_the_match(sample_table):
    frame = pd.DataFrame({"Equipment": ["Scrubber Recirculation Pump"], "Equipment Abbr": [""]})
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig(match_mode=MATCH_ANY))
    assert result.output_frame["Equipment Abbr"].tolist() == ["PMP"]


def test_value_without_any_abbreviation_keeps_the_original_text(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    cells = result.columns[0].cells
    # "Agitator" has no abbreviation - the cell is not emptied, the old value stays
    assert cells[2].status == STATUS_KEPT
    assert cells[2].abbreviation == "Agitator"
    assert cells[2].unknown_words == ["Agitator"]
    assert result.output_frame["Equipment Abbr"].iloc[2] == "Agitator"
    # an empty source cell still stays empty
    assert cells[3].status == STATUS_EMPTY
    assert cells[3].abbreviation == ""


def test_unknown_words_inside_a_sentence_are_kept_as_typed(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    cells = result.columns[0].cells
    # "Cooling Tower No 2": "No" is not in the list -> kept, the rest abbreviated
    assert cells[0].status == STATUS_PARTIAL
    assert cells[0].abbreviation == "CT No 2"
    assert cells[0].unknown_words == ["No"]
    # "Boiler Feed Water Pump B": the trailing "B" is a single letter -> kept but not counted as unknown
    assert cells[1].status == STATUS_FILLED
    assert cells[1].abbreviation == "BFW PMP B"
    assert cells[1].unknown_words == []


def test_whole_cell_must_match_exactly(sample_table):
    frame = pd.DataFrame({"Equipment": ["Cooling Tower", "Cooling Tower No 2", "Temperature"], "Equipment Abbr": ["", "", ""]})
    config = FillConfig(match_mode=MATCH_EXACT)
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT", "", "TMP"]


def test_whole_cell_ignores_case_and_extra_spaces(sample_table):
    frame = pd.DataFrame({"Equipment": ["  cooling   TOWER "], "Equipment Abbr": [""]})
    config = FillConfig(match_mode=MATCH_EXACT)
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT"]


def test_every_word_must_match(table):
    frame = pd.DataFrame({"Equipment": ["Boiler Feed Water Pump", "Cooling Tower No 2", "Agitator Pump"], "Equipment Abbr": ["", "", ""]})
    config = FillConfig(match_mode=MATCH_ALL_WORDS, separator="_")
    result = run_column_fill(frame, table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["BFW_PMP", "CT_NO_2", ""]


def test_one_unknown_word_empties_the_whole_all_words_cell(table):
    frame = pd.DataFrame({"Equipment": ["Pump Agitator"], "Equipment Abbr": [""]})
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
        pd.DataFrame({"Equipment": ["Agitator"], "Equipment Abbr": [""]}),
        sample_table, [FillMapping("Equipment")], FillConfig(),
    )
    assert result.output_frame["Equipment Abbr"].tolist() == [""]


# ---------------------------------------------------------------------------
# output layout
# ---------------------------------------------------------------------------
def test_no_new_columns_are_created(frame, sample_table):
    mappings = [
        FillMapping("Equipment", "Equipment Abbr"),
        FillMapping("Parameter", "Parameter Abbr"),
    ]
    result = run_column_fill(frame, sample_table, mappings, FillConfig())
    # same columns, same order, same rows - only the targets got values
    assert list(result.output_frame.columns) == list(frame.columns)
    assert len(result.output_frame) == len(frame)
    assert result.output_frame["Equipment Abbr"].iloc[0] == "CT No 2"
    assert result.output_frame["Parameter Abbr"].iloc[0] == "TMP"


def test_source_frame_is_never_modified(frame, sample_table):
    before = frame.copy(deep=True)
    run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    pd.testing.assert_frame_equal(frame, before)


# ---------------------------------------------------------------------------
# new columns (added at the end)
# ---------------------------------------------------------------------------
def test_new_column_is_appended_at_the_end(frame, sample_table):
    mapping = FillMapping("Equipment", "Equipment Abbr 2", new_column=True)
    result = run_column_fill(frame, sample_table, [mapping], FillConfig())

    assert list(result.output_frame.columns) == list(frame.columns) + ["Equipment Abbr 2"]
    assert result.output_frame["Equipment Abbr 2"].tolist() == [
        "CT No 2", "BFW PMP B", "Agitator", ""
    ]
    assert result.new_columns == ["Equipment Abbr 2"]
    # the uploaded frame is untouched and never gets the new column
    assert "Equipment Abbr 2" not in frame.columns
    assert len(result.output_frame) == len(frame)


def test_new_column_uses_the_target_column_name_as_given(frame, sample_table):
    mapping = FillMapping("Parameter", "Short Param", new_column=True)
    result = run_column_fill(frame, sample_table, [mapping], FillConfig())
    assert result.columns[0].target_name == "Short Param"
    assert result.output_frame["Short Param"].tolist() == ["TMP", "Flow", "", "PI"]


def test_new_column_name_must_not_already_exist(frame, sample_table):
    mapping = FillMapping("Equipment", "Equipment Abbr", new_column=True)
    with pytest.raises(ValueError, match="already exists"):
        run_column_fill(frame, sample_table, [mapping], FillConfig())


def test_existing_and_new_targets_can_be_filled_together(frame, sample_table):
    mappings = [
        FillMapping("Equipment", "Equipment Abbr"),
        FillMapping("Equipment", "Short Equipment", new_column=True),
        FillMapping("Parameter", "Parameter Abbr"),
    ]
    result = run_column_fill(frame, sample_table, mappings, FillConfig())

    assert list(result.output_frame.columns) == list(frame.columns) + ["Short Equipment"]
    assert result.output_frame["Equipment Abbr"].tolist() == result.output_frame["Short Equipment"].tolist()
    assert result.new_columns == ["Short Equipment"]
    summary = build_fill_summary_frame(result)
    assert list(summary["New column"]) == ["No", "Yes", "No"]


def test_one_source_can_fill_two_existing_targets(frame, sample_table):
    frame = frame.assign(Short="", Exact="")
    mappings = [FillMapping("Equipment", "Short"), FillMapping("Equipment", "Exact")]
    result = run_column_fill(frame, sample_table, mappings, FillConfig())
    assert list(result.output_frame.columns) == list(frame.columns)
    assert result.output_frame["Short"].tolist() == result.output_frame["Exact"].tolist()
    assert result.output_frame["Short"].iloc[0] == "CT No 2"


def test_target_column_is_overwritten_in_the_output_only(frame, sample_table):
    frame = frame.copy()
    frame["Equipment Abbr"] = ["keep 1", "keep 2", "keep 3", "keep 4"]
    result = run_column_fill(
        frame, sample_table, [FillMapping("Equipment", target="Equipment Abbr")], FillConfig()
    )
    assert result.columns[0].target_name == "Equipment Abbr"
    assert result.columns[0].output_name == "Equipment Abbr"  # alias
    assert result.output_frame["Equipment Abbr"].tolist() == ["CT No 2", "BFW PMP B", "Agitator", ""]
    # the uploaded frame itself is untouched
    assert frame["Equipment Abbr"].tolist() == ["keep 1", "keep 2", "keep 3", "keep 4"]


def test_missing_target_column_raises(frame, sample_table):
    with pytest.raises(KeyError, match="does not create columns"):
        run_column_fill(
            frame, sample_table, [FillMapping("Equipment", "No Such Column")], FillConfig()
        )


def test_source_and_target_must_differ(frame, sample_table):
    with pytest.raises(ValueError, match="overwrite the original text"):
        run_column_fill(
            frame, sample_table, [FillMapping("Equipment", "Equipment")], FillConfig()
        )


def test_same_target_cannot_be_used_twice(frame, sample_table):
    mappings = [
        FillMapping("Equipment", "Equipment Abbr"),
        FillMapping("Parameter", "Equipment Abbr"),
    ]
    with pytest.raises(ValueError, match="more than once"):
        run_column_fill(frame, sample_table, mappings, FillConfig())


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


def test_empty_target_falls_back_to_existing_suffix_column(frame, sample_table):
    frame = frame.assign(**{"Equipment Code": ""})
    result = run_column_fill(
        frame, sample_table, [FillMapping("Equipment", output="")], FillConfig(output_suffix=" Code")
    )
    assert result.columns[0].target_name == "Equipment Code"
    assert result.output_frame["Equipment Code"].iloc[0] == "CT No 2"


# ---------------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------------
def test_letter_case_setting(frame, sample_table):
    lower = run_column_fill(
        frame, sample_table, [FillMapping("Equipment")], FillConfig(case=CASE_LOWER, match_mode=MATCH_ANY)
    )
    assert lower.output_frame["Equipment Abbr"].iloc[0] == "ct"
    upper = run_column_fill(
        frame, sample_table, [FillMapping("Equipment")], FillConfig(case=CASE_UPPER, match_mode=MATCH_ANY)
    )
    assert upper.output_frame["Equipment Abbr"].iloc[0] == "CT"


def test_plural_matching_is_off_by_default(sample_table):
    frame = pd.DataFrame({"Equipment": ["Pumps", "Pump"], "Equipment Abbr": ["", ""]})
    plain = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    # "Pumps" is not in the list -> kept as typed, never guessed to "PMP"
    assert plain.output_frame["Equipment Abbr"].tolist() == ["Pumps", "PMP"]
    assert plain.columns[0].cells[0].unknown_words == ["Pumps"]

    plural = run_column_fill(
        frame, sample_table, [FillMapping("Equipment")], FillConfig(allow_plural_matching=True)
    )
    assert plural.output_frame["Equipment Abbr"].tolist() == ["PMP", "PMP"]


def test_not_found_can_keep_the_original_text_when_asked(sample_table):
    frame = pd.DataFrame({"Equipment": ["Agitator"], "Equipment Abbr": [""]})
    config = FillConfig(when_not_found=NOT_FOUND_KEEP)
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], config)
    assert result.output_frame["Equipment Abbr"].tolist() == ["Agitator"]
    assert result.columns[0].cells[0].status == STATUS_KEPT


def test_per_column_rule_overrides_the_default(sample_table):
    frame = pd.DataFrame({"Equipment": ["Cooling Tower", "Cooling Tower No 2"], "Equipment Abbr": ["", ""]})
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
    assert list(summary["Target column"]) == ["Equipment Abbr", "Parameter Abbr"]
    equipment = summary.iloc[0]
    assert equipment["Filled (every word abbreviated)"] == 1  # B is single letter, not counted as unknown
    assert equipment["Filled, unknown words kept"] == 1  # Cooling Tower No 2 has No unknown
    assert equipment["Original kept (no abbreviation)"] == 1  # Agitator
    assert equipment["Empty source cell"] == 1

    parameter = summary.iloc[1]
    assert parameter["Filled (every word abbreviated)"] == 2  # Temperature, Pressure Indicator
    assert parameter["Filled, unknown words kept"] == 0
    assert parameter["Original kept (no abbreviation)"] == 1  # Flow
    assert parameter["Empty source cell"] == 1


def test_not_found_report_lists_distinct_values(frame, sample_table):
    result = run_column_fill(
        frame, sample_table, [FillMapping("Equipment"), FillMapping("Parameter")], FillConfig()
    )
    report = build_fill_not_found_frame(result)
    values = set(report["Value with no abbreviation"])
    assert "Agitator" in values
    assert "Flow" in values
    # values that were filled but contain an unknown word are listed as well
    assert "Cooling Tower No 2" in values
    assert 3 <= len(report)  # one row per column/value pair


def test_not_found_report_shows_the_unknown_words_and_what_was_written(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    report = build_fill_not_found_frame(result)
    row = report[report["Value with no abbreviation"] == "Cooling Tower No 2"].iloc[0]
    assert row["Words with no abbreviation"] == "No"
    assert row["Written in target column"] == "CT No 2"

    kept = report[report["Value with no abbreviation"] == "Agitator"].iloc[0]
    assert kept["Written in target column"] == "Agitator"


def test_unknown_words_report_counts_every_word(frame, sample_table):
    frame = pd.DataFrame(
        {
            "Equipment": ["Cooling Tower Scrubber", "Scrubber Pump", "Agitator"],
            "Equipment Abbr": ["", "", ""],
        }
    )
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    report = build_fill_unknown_words_frame(result)
    assert list(report["Word with no abbreviation"]) == ["Scrubber", "Agitator"]
    scrubber = report[report["Word with no abbreviation"] == "Scrubber"].iloc[0]
    assert scrubber["Occurrences"] == 2
    assert scrubber["Example result"] == "CT Scrubber"


def test_not_found_report_is_empty_when_everything_matches(sample_table):
    frame = pd.DataFrame({"Equipment": ["Pump", "Cooling Tower"], "Equipment Abbr": ["", ""]})
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    report = build_fill_not_found_frame(result)
    assert report.empty
    assert list(report.columns) == [
        "Source column",
        "Value with no abbreviation",
        "Words with no abbreviation",
        "Written in target column",
        "Occurrences",
        "First row",
    ]
    assert build_fill_unknown_words_frame(result).empty


def test_fill_workbook_round_trip(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig(match_mode=MATCH_ANY))
    data = build_fill_workbook(result)
    assert data[:2] == b"PK"

    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert "Filled Data" in sheets
    assert {"Summary", "Not Found", "Unknown Words", "Run Settings"}.issubset(sheets)
    filled = sheets["Filled Data"]
    assert len(filled) == len(frame)
    assert "Equipment Abbr" in filled.columns
    assert filled["Equipment Abbr"].iloc[0] == "CT"


def test_fill_workbook_without_reports_has_one_sheet(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    data = build_fill_workbook(result, include_report=False)
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert list(sheets) == ["Filled Data"]


def test_fill_workbook_keeps_a_new_column_at_the_end(frame, sample_table):
    mapping = FillMapping("Equipment", "Short Equipment", new_column=True)
    result = run_column_fill(frame, sample_table, [mapping], FillConfig())
    data = build_fill_workbook(result, include_report=False)
    filled = pd.read_excel(io.BytesIO(data), sheet_name="Filled Data")
    assert list(filled.columns) == list(frame.columns) + ["Short Equipment"]
    assert filled["Short Equipment"].iloc[0] == "CT No 2"


def test_fill_report_workbook(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    data = build_fill_report_workbook(result)
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert set(sheets) == {"Summary", "Not Found", "Unknown Words", "Run Settings"}


def test_statuses_are_reported(frame, sample_table):
    result = run_column_fill(frame, sample_table, [FillMapping("Equipment")], FillConfig())
    statuses = [cell.status for cell in result.columns[0].cells]
    assert statuses == [STATUS_PARTIAL, STATUS_FILLED, STATUS_KEPT, STATUS_EMPTY]


def test_any_match_prefers_the_longest_phrase_then_the_earliest(table):
    frame = pd.DataFrame({"Text": ["Tower Cooling", "Cooling Tower"], "Text Abbr": ["", ""]})
    result = run_column_fill(frame, table, [FillMapping("Text")], FillConfig(match_mode=MATCH_ANY))
    # "Tower" (1 word) and "Cooling" (1 word) are both matches in the first
    # cell -> the earliest one wins. In the second cell "Cooling Tower" (2
    # words) beats both single words.
    assert result.output_frame["Text Abbr"].tolist() == ["TWR", "CT"]


# ---------------------------------------------------------------------------
# source -> target pair detection
# ---------------------------------------------------------------------------
def test_guess_fill_pairs_detects_abbr_columns():
    columns = [
        "Sr No", "Plant Section", "Plant Section Abbr",
        "Equipment Description", "Equipment Description Abbr",
        "Parameter", "Parameter Abbr", "Qty",
    ]
    assert guess_fill_pairs(columns) == [
        ("Plant Section", "Plant Section Abbr"),
        ("Equipment Description", "Equipment Description Abbr"),
        ("Parameter", "Parameter Abbr"),
    ]


def test_guess_fill_pairs_uses_previous_column_for_plain_abbr():
    assert guess_fill_pairs(["Equipment", "Abbr", "Qty"]) == [("Equipment", "Abbr")]


def test_guess_fill_pairs_without_abbr_columns_is_empty():
    assert guess_fill_pairs(["Equipment", "Qty", "Remarks"]) == []
