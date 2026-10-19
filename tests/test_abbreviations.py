"""Loading the company abbreviation list - column names are never assumed."""

import pandas as pd
import pytest

from tagforge import AbbreviationTable, load_table_from_frame
from tagforge.abbreviations import DROP_MARKER


def _frame(rows, phrase_col="Word / Phrase", abbr_col="Approved Abbreviation"):
    return pd.DataFrame(rows, columns=[phrase_col, abbr_col])


def test_columns_are_chosen_at_runtime():
    frame = _frame([("Cooling Tower", "CT")], phrase_col="Full Form", abbr_col="Short Code")
    table, report = load_table_from_frame(frame, "Full Form", "Short Code")
    assert len(table) == 1
    assert table.get("cooling tower").abbr == "CT"
    assert report.added == 1


def test_unknown_column_names_raise_a_clear_error():
    frame = _frame([("Cooling Tower", "CT")])
    with pytest.raises(KeyError) as error:
        load_table_from_frame(frame, "Nope", "Approved Abbreviation")
    assert "Available columns" in str(error.value)


def test_matching_is_case_insensitive_and_lookup_returns_longest_allowed_phrase():
    table = AbbreviationTable()
    table.add("Pump", "PMP")
    assert table.get("pump").abbr == "PMP"
    assert table.get("  PUMP  ").abbr == "PMP"


def test_blank_rows_and_duplicates_are_reported_not_guessed():
    frame = _frame(
        [
            ("Pump", "PMP"),
            ("pump", "PMP"),          # duplicate (case difference)
            ("Cooling Tower", "CT"),  #
            ("Cooling Tower", "CT"),  # exact duplicate
            ("", ""),                 # blank
            ("Fan", ""),              # missing abbreviation
        ]
    )
    table, report = load_table_from_frame(frame, "Word / Phrase", "Approved Abbreviation")
    assert len(table) == 2                 # Pump + Cooling Tower
    assert report.added == 2
    assert report.duplicates               # reported, first entry kept
    assert report.blank_rows == 1          # the row with a phrase but no abbreviation
    assert table.get("Pump").abbr == "PMP"


def test_conflicting_abbreviations_keep_the_first_entry():
    frame = _frame([("Water", "WTR"), ("water", "H2O")])
    table, report = load_table_from_frame(frame, "Word / Phrase", "Approved Abbreviation")
    assert table.get("Water").abbr == "WTR"
    assert report.conflicts


def test_add_edit_remove_mappings():
    table = AbbreviationTable()
    changed, message = table.add("Cooling Tower", "CT")
    assert changed and "Added" in message
    assert len(table) == 1

    changed, message = table.add("Cooling Tower", "CT")  # identical -> no change
    assert not changed

    changed, message = table.add("Cooling Tower", "COT")  # edit
    assert changed and "Updated" in message
    assert table.get("Cooling Tower").abbr == "COT"

    assert table.remove("cooling tower") is True
    assert table.remove("cooling tower") is False
    assert len(table) == 0


def test_adding_without_an_abbreviation_is_refused():
    table = AbbreviationTable()
    changed, message = table.add("Scrubber", "   ")
    assert not changed
    assert "no abbreviation" in message
    assert len(table) == 0


def test_slash_entries_are_only_split_when_asked():
    frame = _frame([("Valve / Valves", "VLV")])
    table, plain = load_table_from_frame(frame, "Word / Phrase", "Approved Abbreviation")
    assert table.get("valve / valves") is not None
    assert plain.slash_expanded == 0

    table, expanded = load_table_from_frame(
        frame, "Word / Phrase", "Approved Abbreviation", expand_slashes=True
    )
    assert table.get("Valve") is not None and table.get("Valves") is not None
    assert expanded.slash_expanded == 1


def test_drop_marker_is_never_guessed_by_the_loader():
    frame = _frame([("Pump", "PMP")])
    table, _ = load_table_from_frame(frame, "Word / Phrase", "Approved Abbreviation")
    assert table.get("Pump").abbr != DROP_MARKER


def test_version_changes_when_the_list_changes():
    table = AbbreviationTable()
    before = table.version
    table.add("Pump", "PMP")
    assert table.version > before
