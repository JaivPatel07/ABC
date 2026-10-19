"""Validation: empty values, duplicates, invalid characters and length."""

import pandas as pd

from tagforge import AbbreviationTable, NamingConfig, run_pipeline
from tagforge.validation import (
    CODE_DUPLICATE,
    CODE_EMPTY,
    CODE_INVALID_CHAR,
    CODE_TOO_LONG,
    CODE_UNKNOWN,
    find_duplicate_tags,
    summarise_issues,
    uniquify_tags,
)


def _table():
    table = AbbreviationTable()
    for phrase, abbr in [("Cooling Tower", "CT"), ("Pump", "PMP"), ("Fan", "FAN")]:
        table.add(phrase, abbr, source="company list")
    return table


def test_empty_values_are_flagged():
    frame = pd.DataFrame({"Equipment": ["Cooling Tower", None, "   "]})
    result = run_pipeline(frame, "Equipment", _table(), NamingConfig())
    codes = {issue.code for issue in result.issues}
    assert CODE_EMPTY in codes
    assert result.stats["empty values"] == 2
    assert list(result.tags) == ["CT", "", ""]


def test_duplicate_tags_are_found_and_can_be_numbered():
    frame = pd.DataFrame({"Equipment": ["Cooling Tower", "Cooling Tower", "Cooling Tower"]})
    result = run_pipeline(frame, "Equipment", _table(), NamingConfig())
    assert result.duplicate_groups == {"CT": [0, 1, 2]}
    assert summarise_issues(result.issues)[CODE_DUPLICATE] == 1

    fixed = run_pipeline(
        frame, "Equipment", _table(), NamingConfig(uniquify_duplicates=True)
    )
    assert list(fixed.tags) == ["CT", "CT_2", "CT_3"]
    assert fixed.duplicate_groups == {}


def test_duplicate_format_is_configurable():
    tags = ["CT", "CT", "CT"]
    config = NamingConfig(uniquify_format="{tag}-{n}", uniquify_start=2)
    assert uniquify_tags(tags, config) == ["CT", "CT-2", "CT-3"]

    config = NamingConfig(uniquify_format="{tag}{separator}{n}", uniquify_start=10)
    assert uniquify_tags(tags, config) == ["CT", "CT_10", "CT_11"]


def test_invalid_characters_are_reported_when_they_survive():
    frame = pd.DataFrame({"Equipment": ["Cooling Tower Pump"]})
    config = NamingConfig(separator="_", invalid_char_pattern=r"[^A-Z]", replace_invalid_with="@")
    result = run_pipeline(frame, "Equipment", _table(), config)
    codes = {issue.code for issue in result.issues}
    assert CODE_INVALID_CHAR in codes


def test_too_long_tags_are_reported():
    frame = pd.DataFrame({"Equipment": ["Cooling Tower Pump Fan"]})
    config = NamingConfig(max_length=4, truncate_mode="Cut at limit")
    result = run_pipeline(frame, "Equipment", _table(), config)
    assert CODE_TOO_LONG not in {issue.code for issue in result.issues}  # already truncated
    assert len(result.tags.iloc[0]) == 4

    config = NamingConfig(max_length=4, truncate_mode="Do not limit")
    result = run_pipeline(frame, "Equipment", _table(), config)
    assert CODE_TOO_LONG in {issue.code for issue in result.issues}


def test_unknown_words_are_reported_per_row():
    frame = pd.DataFrame({"Equipment": ["Cooling Tower Scrubber"]})
    result = run_pipeline(frame, "Equipment", _table(), NamingConfig())
    assert summarise_issues(result.issues)[CODE_UNKNOWN] == 1


def test_duplicate_tags_ignore_empty_values():
    assert find_duplicate_tags(["CT", "", "", "CT"]) == {"CT": [0, 3]}
    assert find_duplicate_tags(["", " "]) == {}
