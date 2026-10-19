"""Unknown words are kept, reported and never guessed."""

from tagforge import AbbreviationTable, NamingConfig
from tagforge.pipeline import build_unknown_frame, run_pipeline
from tagforge.taggen import TagGenerator
import pandas as pd


def _table():
    table = AbbreviationTable()
    for phrase, abbr in [("Cooling Tower", "CT"), ("Pump", "PMP")]:
        table.add(phrase, abbr, source="company list")
    return table


def test_unknown_word_is_kept_as_typed():
    generator = TagGenerator(_table(), NamingConfig())
    result = generator.generate_one("Cooling Tower Scrubber")
    assert result.tag == "CT_SCRUBBER"
    assert result.unknown_words == ["Scrubber"]
    assert result.status == "Unknown words"


def test_nothing_is_guessed_for_a_word_that_looks_similar():
    generator = TagGenerator(_table(), NamingConfig())
    result = generator.generate_one("Pumps")  # 'Pump' exists, 'Pumps' does not
    assert result.tag == "PUMPS"
    assert result.unknown_words == ["Pumps"]


def test_unknown_report_counts_and_examples():
    frame = pd.DataFrame(
        {"Equipment": ["Cooling Tower Scrubber", "Scrubber Pump", "Cooling Tower Pump", None]}
    )
    result = run_pipeline(frame, "Equipment", _table(), NamingConfig())
    unknown = result.unknown_frame

    assert "Scrubber" in set(unknown["Unknown word"])
    assert int(unknown.loc[unknown["Unknown word"] == "Scrubber", "Occurrences"].iloc[0]) == 2
    assert "Your abbreviation" in unknown.columns  # the column the user fills in
    assert result.stats["distinct unknown words"] == 1
    assert result.stats["empty values"] == 1


def test_adding_a_mapping_removes_the_unknown_word():
    frame = pd.DataFrame({"Equipment": ["Cooling Tower Scrubber"]})
    table = _table()
    assert run_pipeline(frame, "Equipment", table, NamingConfig()).unknown_frame.shape[0] == 1

    table.add("Scrubber", "SCR", source="user added")
    result = run_pipeline(frame, "Equipment", table, NamingConfig())
    assert result.unknown_frame.empty
    assert result.tags.iloc[0] == "CT_SCR"


def test_user_added_entry_is_market_as_user_source():
    table = _table()
    table.add("Scrubber", "SCR", source="user added")
    assert table.get("Scrubber").source == "user added"


def test_empty_input_produces_an_empty_tag_and_a_note():
    generator = TagGenerator(_table(), NamingConfig(prefix="PLANT"))
    result = generator.generate_one("   ")
    assert result.tag == ""
    assert result.notes and "empty" in result.notes[0]


def test_build_unknown_frame_on_empty_results():
    generator = TagGenerator(_table(), NamingConfig())
    results = [generator.generate_one("Cooling Tower Pump")]
    frame = build_unknown_frame(results)
    assert frame.empty
