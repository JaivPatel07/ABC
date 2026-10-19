"""Smoke test for the Streamlit app itself.

``AppTest`` runs app.py without a browser.  File upload widgets cannot be
driven this way, so the state that normally comes from an upload is injected -
exactly the values the upload handlers would have stored.
"""

import io
from pathlib import Path

import pandas as pd
import pytest

from tagforge import NamingConfig, load_table_from_frame
from tagforge.column_fill import FillConfig, FillMapping
from tagforge.ui.fill_pages import FILL_STEPS
from tagforge.ui.modes import MODE_FILL, MODE_TAG
from tagforge.ui.pages import STEPS

APP = Path(__file__).resolve().parent.parent / "app.py"
SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _app_test():
    from streamlit.testing.v1 import AppTest

    return AppTest.from_file(str(APP), default_timeout=180)


def _inject(at):
    abbreviations = pd.read_csv(SAMPLES / "company_abbreviations.csv")
    table, _report = load_table_from_frame(
        abbreviations, "Word / Phrase", "Approved Abbreviation"
    )
    frame = pd.read_excel(SAMPLES / "equipment_data.xlsx", sheet_name="Equipment List")

    at.session_state["tf_data_bytes"] = (SAMPLES / "equipment_data.xlsx").read_bytes()
    at.session_state["tf_data_file_name"] = "equipment_data.xlsx"
    at.session_state["tf_data_file_id"] = ("equipment_data.xlsx", 1, 1)
    at.session_state["tf_data_frame"] = frame
    at.session_state["tf_data_columns"] = list(frame.columns)

    at.session_state["tf_abbr_bytes"] = (SAMPLES / "company_abbreviations.csv").read_bytes()
    at.session_state["tf_abbr_file_name"] = "company_abbreviations.csv"
    at.session_state["tf_abbr_file_id"] = ("company_abbreviations.csv", 1, 2)
    at.session_state["tf_abbr_frame"] = abbreviations
    at.session_state["tf_abbr_phrase_col"] = "Word / Phrase"
    at.session_state["tf_abbr_abbr_col"] = "Approved Abbreviation"
    at.session_state["tf_table"] = table

    at.session_state["tf_target_col"] = "Equipment Description"
    at.session_state["tf_config"] = NamingConfig(template="{prefix}{abbr}", prefix="MERIDIAN")
    at.session_state["tf_mode"] = MODE_TAG
    return at


def _inject_fill(at):
    """Everything the filler needs, as if both files had been uploaded."""
    at = _inject(at)
    at.session_state["tf_mode"] = MODE_FILL
    at.session_state["tf_fill_config"] = FillConfig()
    at.session_state["tf_fill_mappings"] = [
        FillMapping("Equipment Description"),
        FillMapping("Parameter"),
    ]
    return at


def test_app_starts_in_fill_mode_at_step_one_without_errors():
    at = _app_test()
    at.run()
    assert not at.exception
    assert at.session_state["mode_radio"] == MODE_FILL
    assert at.session_state["tf_fill_step"] == 1


@pytest.mark.parametrize("step", range(1, 9))
def test_every_step_renders_without_errors(step):
    at = _inject(_app_test())
    at.session_state["tf_step"] = step
    at.session_state["step_nav"] = STEPS[step - 1]
    at.run()
    assert not at.exception, f"step {step} failed: {at.exception}"


def test_preview_step_generates_tags_from_the_injected_state():
    at = _inject(_app_test())
    at.session_state["tf_step"] = 5
    at.session_state["step_nav"] = STEPS[4]
    at.run()
    assert not at.exception
    # the wizard stored a result and the sidebar confirms it
    assert at.session_state["tf_result"] is not None
    tags = list(at.session_state["tf_result"].tags)
    assert "MERIDIAN_CT_NO_2" in tags


def test_unmatched_step_buttons_do_not_crash_and_change_nothing_when_empty():
    at = _inject(_app_test())
    at.session_state["tf_step"] = 6
    at.session_state["step_nav"] = STEPS[5]
    at.run()
    before = len(at.session_state["tf_table"])

    at.button(key="btn_add_abbr").click().run()
    assert not at.exception
    assert len(at.session_state["tf_table"]) == before  # nothing was typed, nothing added

    at.button(key="btn_apply_map").click().run()
    assert not at.exception
    assert len(at.session_state["tf_table"]) == before  # editor was not modified


def test_duplicate_tags_can_be_numbered_from_the_validation_step():
    at = _inject(_app_test())
    at.session_state["tf_step"] = 7
    at.session_state["step_nav"] = STEPS[6]
    at.run()
    assert not at.exception
    assert at.session_state["tf_result"].duplicate_groups, "sample data should contain duplicates"

    at.button(key="btn_uniquify").click().run()
    assert not at.exception
    assert at.session_state["tf_config"].uniquify_duplicates is True
    assert at.session_state["tf_result"].duplicate_groups == {}


def test_export_step_builds_a_workbook_in_memory():
    at = _inject(_app_test())
    at.session_state["tf_step"] = 8
    at.session_state["step_nav"] = STEPS[7]
    at.run()
    assert not at.exception

    data = at.session_state["tf_export_bytes"]
    assert data and data[:2] == b"PK"  # a real .xlsx file
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert "Processed Data" in sheets
    assert len(sheets["Processed Data"]) == 29
    assert "Generated_Tag" in sheets["Processed Data"].columns


def test_start_over_clears_the_session():
    at = _inject(_app_test())
    at.session_state["tf_step"] = 5
    at.session_state["step_nav"] = STEPS[4]
    at.run()
    assert at.session_state["tf_result"] is not None

    at.button(key="start_over").click().run()
    assert at.session_state.get("tf_result") is None
    assert at.session_state.get("tf_data_bytes") is None


# ===========================================================================
# column filler mode
# ===========================================================================
def test_fill_mode_step_three_suggests_columns_and_saves_the_mapping():
    at = _inject_fill(_app_test())
    at.session_state["tf_fill_step"] = 3
    at.session_state["fill_step_nav"] = FILL_STEPS[2]
    at.run()
    assert not at.exception

    mappings = at.session_state["tf_fill_mappings"]
    assert [mapping.source for mapping in mappings] == [
        "Plant Section",
        "Equipment Description",
        "Parameter",
    ]
    assert all(mapping.output.endswith("Abbr") for mapping in mappings)


def test_fill_mode_step_four_builds_the_workbook_with_empty_cells():
    at = _inject_fill(_app_test())
    at.session_state["tf_fill_step"] = 4
    at.session_state["fill_step_nav"] = FILL_STEPS[3]
    at.run()
    assert not at.exception

    data = at.session_state["tf_fill_export"]
    assert data and data[:2] == b"PK"
    sheets = pd.read_excel(io.BytesIO(data), sheet_name=None)
    assert "Filled Data" in sheets
    assert {"Summary", "Not Found", "Run Settings"}.issubset(sheets)

    filled = sheets["Filled Data"]
    assert len(filled) == 29
    assert "Equipment Description Abbr" in filled.columns
    assert "Parameter Abbr" in filled.columns
    assert filled.loc[0, "Equipment Description Abbr"] == "CT"
    # row 3 (index 2) has Parameter = "Flow" which is not in the sample list
    assert pd.isna(filled.loc[2, "Parameter Abbr"])
    # row 3 (index 2) has an equipment description, so it must be filled
    assert filled.loc[2, "Equipment Description Abbr"] == "BFW"
    # row 29 (index 27) has an empty description -> empty abbreviation
    assert pd.isna(filled.loc[27, "Equipment Description Abbr"])


def test_fill_mode_never_copies_unmatched_text():
    at = _inject_fill(_app_test())
    at.session_state["tf_fill_step"] = 4
    at.session_state["fill_step_nav"] = FILL_STEPS[3]
    at.run()
    assert not at.exception

    result = at.session_state["tf_fill_result"]
    values = result.output_frame["Equipment Description Abbr"].tolist()
    assert "Agitator" not in values
    assert "" in values


def test_fill_mode_downloads_are_available():
    at = _inject_fill(_app_test())
    at.session_state["tf_fill_step"] = 4
    at.session_state["fill_step_nav"] = FILL_STEPS[3]
    at.run()
    assert not at.exception
    labels = [button.label for button in at.get("download_button")]
    assert any("filled Excel file" in label for label in labels)
    assert any("summary report" in label for label in labels)


def test_next_button_advances_the_tag_wizard():
    at = _inject(_app_test())
    at.run()
    assert at.session_state["tf_step"] == 1

    buttons = [button for button in at.button if "Next: abbreviation list" in button.label]
    assert buttons, "the next button should be visible on step 1"
    buttons[0].click().run()
    assert not at.exception
    assert at.session_state["tf_step"] == 2
    assert at.session_state["step_nav"] == STEPS[1]


def test_next_button_advances_the_fill_mode():
    at = _inject_fill(_app_test())
    at.session_state["tf_fill_step"] = 3
    at.session_state["fill_step_nav"] = FILL_STEPS[2]
    at.run()
    assert not at.exception

    at.button(key="fill_next").click().run()
    assert not at.exception
    assert at.session_state["tf_fill_step"] == 4
    assert at.session_state["fill_step_nav"] == FILL_STEPS[3]
    assert at.session_state["tf_fill_result"] is not None
