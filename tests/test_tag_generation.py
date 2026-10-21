"""Tag name generation: templates, separators, casing and cleaning rules."""

import pandas as pd

from tagforge import AbbreviationTable, NamingConfig
from tagforge.config import validate_template
from tagforge.taggen import TagGenerator


def _table():
    table = AbbreviationTable()
    for phrase, abbr in [
        ("Cooling Tower", "CT"),
        ("Boiler Feed Water", "BFW"),
        ("Pump", "PMP"),
        ("Level Transmitter", "LT"),
        ("No", "NO"),
    ]:
        table.add(phrase, abbr, source="company list")
    return table


def _tag(text, **overrides):
    config = NamingConfig(**overrides)
    return TagGenerator(_table(), config).generate_one(text).tag


def test_default_configuration():
    assert _tag("Cooling Tower No 2") == "CT_NO_2"


def test_prefix_and_suffix():
    config = NamingConfig(template="{prefix}{abbr}{suffix}", prefix="ADANI_XYZ", suffix="R1")
    assert TagGenerator(_table(), config).generate_one("Cooling Tower").tag == "ADANI_XYZ_CT_R1"


def test_separator_is_configurable():
    assert _tag("Cooling Tower Pump", separator="-") == "CT-PMP"
    assert _tag("Cooling Tower Pump", separator="") == "CTPMP"
    assert _tag("Cooling Tower Pump", separator=".") == "CT.PMP"


def test_typed_separator_beats_the_default():
    config = NamingConfig(template="{prefix}-{abbr}", prefix="PLANT", separator="_")
    assert TagGenerator(_table(), config).generate_one("Cooling Tower").tag == "PLANT-CT"


def test_inner_separator_can_differ_from_the_template_separator():
    config = NamingConfig(template="{prefix}{abbr}", prefix="PLANT", separator="_", inner_separator="-")
    assert TagGenerator(_table(), config).generate_one("Cooling Tower Pump").tag == "PLANT_CT-PMP"


def test_letter_case_options():
    assert _tag("Cooling Tower", case="lowercase") == "ct"
    assert _tag("Cooling Tower", case="UPPERCASE") == "CT"
    assert _tag("Cooling Tower Scrubber", case="Keep original") == "CT_Scrubber"


def test_row_number_and_padding():
    config = NamingConfig(template="{abbr}{index}", index_start=1)
    generator = TagGenerator(_table(), config)
    assert generator.generate_one("Cooling Tower", row_id=0).tag == "CT_1"
    assert generator.generate_one("Cooling Tower", row_id=6).tag == "CT_7"

    padded = NamingConfig(template="{abbr}{index:04d}", index_start=1)
    assert TagGenerator(_table(), padded).generate_one("Cooling Tower", row_id=6).tag == "CT_0007"


def test_other_columns_can_be_used_in_the_template():
    frame = pd.DataFrame(
        {
            "Equipment": ["Cooling Tower Pump", "Boiler Feed Water Pump"],
            "Plant Section": ["Power House", "Boiler House"],
        }
    )
    config = NamingConfig(template="{col:Plant Section}{abbr}")
    results = TagGenerator(_table(), config).generate_series(frame["Equipment"], frame)
    assert results[0].tag == "POWER_HOUSE_CT_PMP"
    assert results[1].tag == "BOILER_HOUSE_BFW_PMP"


def test_invalid_characters_are_replaced():
    # punctuation in the source text is simply not part of any token
    assert _tag("Cooling Tower/Scrubber") == "CT_SCRUBBER"
    assert _tag("Cooling Tower/Scrubber", separator="-", allowed_extra_chars="-") == "CT-SCRUBBER"

    # characters coming from a prefix / suffix / another column are cleaned up
    config = NamingConfig(template="{prefix}{abbr}", prefix="Plant #1", replace_invalid_with="X")
    # both the space and the '#' are replaced
    assert TagGenerator(_table(), config).generate_one("Cooling Tower").tag == "PLANTXX1_CT"

    config = NamingConfig(template="{prefix}{abbr}", prefix="Plant #1", replace_invalid_with="")
    assert TagGenerator(_table(), config).generate_one("Cooling Tower").tag == "PLANT1_CT"


def test_a_custom_invalid_pattern_is_used_when_provided():
    config = NamingConfig(template="{prefix}{abbr}", prefix="PLANT", invalid_char_pattern=r"[^a-z]",
                          replace_invalid_with=".")
    assert TagGenerator(_table(), config).generate_one("Cooling Tower").tag.endswith("..")


def test_repeated_and_edge_separators_are_cleaned():
    config = NamingConfig(template="{prefix}{abbr}", prefix="PLANT")
    assert TagGenerator(_table(), config).generate_one("Cooling Tower").tag == "PLANT_CT"
    assert TagGenerator(_table(), config).generate_one("").tag == ""


def test_maximum_length_and_truncation():
    long_text = "Cooling Tower Pump Level Transmitter No 2"
    config = NamingConfig(max_length=8, truncate_mode="Cut at limit")
    assert len(TagGenerator(_table(), config).generate_one(long_text).tag) == 8

    config = NamingConfig(max_length=8, truncate_mode="Cut at last separator")
    # "CT_PMP_LT_NO_2" is cut back to the last separator before the limit
    assert TagGenerator(_table(), config).generate_one(long_text).tag == "CT_PMP"

    warned = NamingConfig(max_length=8, truncate_mode="Do not limit")
    result = TagGenerator(_table(), warned).generate_one(long_text)
    assert result.tag == "CT_PMP_LT_NO_2"
    assert any("longer than" in note for note in result.notes)


def test_template_validation_catches_mistakes():
    errors, warnings = validate_template("{abbr}", ["Equipment"])
    assert not errors and not warnings

    errors, _ = validate_template("{abrv}", ["Equipment"])
    assert errors and "not a known placeholder" in errors[0]

    errors, _ = validate_template("{col:Missing}", ["Equipment"])
    assert errors and "not in the file" in errors[0]

    errors, _ = validate_template("", ["Equipment"])
    assert errors

    _errors, warnings = validate_template("PLANT-", ["Equipment"])
    assert warnings and "no placeholders" in warnings[0]


def test_manual_overrides_are_kept():
    frame = pd.DataFrame({"Equipment": ["Cooling Tower", "Boiler Feed Water Pump"]})
    config = NamingConfig()
    generator = TagGenerator(_table(), config)
    results = generator.generate_series(frame["Equipment"], frame, overrides={1: "MY_OWN_TAG"})
    assert results[0].tag == "CT"
    assert results[1].tag == "MY_OWN_TAG"
    assert results[1].edited is True


def test_code_like_names_keep_the_letter_suffix_attached():
    # T-1000A must become T_1000A, never T_1000_A
    assert _tag("T-1000A") == "T_1000A"
    assert _tag("T-1000-A") == "T_1000A"
    assert _tag("T_1000_A") == "T_1000A"
    assert _tag("T-1000 A") == "T_1000A"
    assert _tag("T - 1000A") == "T_1000A"
    assert _tag("T - 1000 A") == "T_1000A"

    # the code is one piece, so it is joined to the rest of the tag normally
    assert _tag("T-1000A Pump") == "T_1000A_PMP"
    assert _tag("Pump T-1000A") == "PMP_T_1000A"
    # the code keeps its own "_" between letters and digits; the configured
    # separator is only used *between* pieces
    assert _tag("T-1000A Pump", separator=".") == "T_1000A.PMP"
    assert _tag("T-1000A Pump", separator="-") == "T_1000A-PMP"
