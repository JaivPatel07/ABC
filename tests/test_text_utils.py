"""Cleaning, tokenising and missing-value handling."""

import pandas as pd

from tagforge.text_utils import (
    is_code_token,
    is_missing,
    normalize_code_token,
    phrase_key,
    singular_candidates,
    to_text,
    tokenize,
)


def test_missing_values_are_detected():
    assert is_missing(None)
    assert is_missing(float("nan"))
    assert is_missing(pd.NA)
    assert is_missing("")
    assert is_missing("   ")
    assert not is_missing(0)
    assert not is_missing("Pump")


def test_to_text_cleans_whitespace_and_unicode():
    assert to_text("  Cooling   Tower  No 2 ") == "Cooling Tower No 2"
    assert to_text(None) == ""
    assert to_text(float("nan")) == ""
    assert to_text(101.0) == "101"
    assert to_text(12.5) == "12.5"


def test_tokenize_splits_words_and_numbers():
    tokens = tokenize("Boiler Feed Water Pump No. 2")
    assert [token.text for token in tokens] == ["Boiler", "Feed", "Water", "Pump", "No", "2"]
    assert [token.kind for token in tokens] == ["word"] * 5 + ["number"]


def test_tokenize_ignores_punctuation():
    tokens = tokenize("Primary Air Fan - 1 / (A)")
    assert [token.text for token in tokens] == ["Primary", "Air", "Fan", "1", "A"]


def test_phrase_key_is_case_and_space_insensitive():
    assert phrase_key("Cooling Tower") == phrase_key("  cooling   TOWER ")
    assert phrase_key("Cooling Tower") == "cooling tower"


def test_singular_candidates_are_only_used_on_request():
    assert "pump" in singular_candidates("Pumps")
    assert "pump" in singular_candidates("pumps")
    assert singular_candidates("Pump") == []


def test_code_tokens_are_recognised():
    assert is_code_token("T-1000A")
    assert is_code_token("T-1000-A")
    assert is_code_token("T - 1000A")
    assert is_code_token("R-1400")
    assert is_code_token("P_100")
    assert not is_code_token("Pump")
    assert not is_code_token("Primary Air Fan - 1")


def test_code_suffix_stays_attached_to_the_number():
    # a letter suffix after the number belongs to the code: T_1000A, never T_1000_A
    assert normalize_code_token("T-1000A") == "T_1000A"
    assert normalize_code_token("T-1000-A") == "T_1000A"
    assert normalize_code_token("T_1000_A") == "T_1000A"
    assert normalize_code_token("T-1000 A") == "T_1000A"
    assert normalize_code_token("T - 1000 A") == "T_1000A"
    assert normalize_code_token("R-1400") == "R_1400"
    assert normalize_code_token("Pump") == "Pump"
    assert normalize_code_token("A") == "A"


def test_tokenize_keeps_a_code_in_one_piece():
    assert [token.text for token in tokenize("T-1000A")] == ["T-1000A"]
    assert [token.text for token in tokenize("T-1000-A")] == ["T-1000-A"]
    assert [token.text for token in tokenize("T-1000 A")] == ["T-1000 A"]
    assert [token.text for token in tokenize("T - 1000A")] == ["T - 1000A"]
    assert [token.kind for token in tokenize("T - 1000A")] == ["code"]


def test_short_words_are_not_mistaken_for_codes():
    assert [token.text for token in tokenize("No - 2")] == ["No", "2"]
    assert [token.text for token in tokenize("Fan - 1 A")] == ["Fan", "1", "A"]
    assert [token.text for token in tokenize("Primary Air Fan - 1 / (A)")] == [
        "Primary",
        "Air",
        "Fan",
        "1",
        "A",
    ]
