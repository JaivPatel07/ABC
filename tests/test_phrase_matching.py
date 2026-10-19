"""Longest-phrase-first matching, multi-word phrases and messy input."""

from tagforge import AbbreviationTable
from tagforge.taggen import TagGenerator
from tagforge.config import NamingConfig


def _table(pairs):
    table = AbbreviationTable()
    for phrase, abbr in pairs:
        table.add(phrase, abbr, source="company list")
    return table


def test_longest_phrase_wins(table):
    generator = TagGenerator(table, NamingConfig())
    assert generator.generate_one("Cooling Tower Level").tag == "CT_LVL"
    assert generator.generate_one("Cooling Level").tag == "COL_LVL"
    assert generator.generate_one("Tower Level").tag == "TWR_LVL"


def test_three_word_phrase_beats_two_word_phrase():
    table = _table(
        [("Boiler", "BLR"), ("Boiler Feed", "BF"), ("Boiler Feed Water", "BFW"), ("Pump", "PMP")]
    )
    generator = TagGenerator(table, NamingConfig())
    assert generator.generate_one("Boiler Feed Water Pump").tag == "BFW_PMP"
    assert generator.generate_one("Boiler Feed Pump").tag == "BF_PMP"


def test_matching_ignores_casing_spacing_and_punctuation():
    table = _table([("Cooling Tower", "CT"), ("Pump", "PMP")])
    generator = TagGenerator(table, NamingConfig())
    assert generator.generate_one("  cooling   TOWER  ").tag == "CT"
    assert generator.generate_one("Cooling Tower - Pump").tag == "CT_PMP"
    assert generator.generate_one("COOLING.TOWER").tag == "CT"


def test_numbers_are_kept_but_not_matched_as_words():
    table = _table([("Cooling Tower", "CT"), ("No", "NO")])
    generator = TagGenerator(table, NamingConfig())
    assert generator.generate_one("Cooling Tower No 2").tag == "CT_NO_2"


def test_plural_matching_is_off_by_default():
    table = _table([("Pump", "PMP")])
    strict = TagGenerator(table, NamingConfig())
    assert strict.generate_one("Pumps").unknown_words == ["Pumps"]

    lenient = TagGenerator(table, NamingConfig(allow_plural_matching=True))
    result = lenient.generate_one("Pumps")
    assert result.tag == "PMP"
    assert result.unknown_words == []


def test_stop_words_are_only_dropped_when_enabled():
    table = _table([("Water", "WTR"), ("Tank", "TNK")])
    generator = TagGenerator(table, NamingConfig(drop_stop_words=True, stop_words="of\nthe"))
    assert generator.generate_one("Tank of Water").tag == "TNK_WTR"

    generator = TagGenerator(table, NamingConfig(drop_stop_words=False, stop_words="of\nthe"))
    assert generator.generate_one("Tank of Water").tag == "TNK_OF_WTR"


def test_repeated_words_can_be_collapsed():
    table = _table([("Pump", "PMP")])
    generator = TagGenerator(table, NamingConfig(dedupe_consecutive_tokens=True))
    assert generator.generate_one("Pump Pump").tag == "PMP"
    generator = TagGenerator(table, NamingConfig())
    assert generator.generate_one("Pump Pump").tag == "PMP_PMP"


def test_dropped_words_disappear_from_the_tag():
    from tagforge.abbreviations import DROP_MARKER

    table = _table([("Pump", "PMP"), ("Unit", DROP_MARKER)])
    generator = TagGenerator(table, NamingConfig())
    assert generator.generate_one("Pump Unit 2").tag == "PMP_2"
