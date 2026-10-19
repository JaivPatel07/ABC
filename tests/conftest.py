"""Shared fixtures for the TagForge test suite.

All data here is fictional - no real company names, equipment or abbreviations.
"""

from pathlib import Path

import pandas as pd
import pytest

from tagforge import AbbreviationTable, NamingConfig, load_table_from_frame

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return SAMPLES


@pytest.fixture(scope="session")
def equipment_frame() -> pd.DataFrame:
    return pd.read_excel(SAMPLES / "equipment_data.xlsx", sheet_name="Equipment List")


@pytest.fixture(scope="session")
def abbreviation_frame() -> pd.DataFrame:
    return pd.read_csv(SAMPLES / "company_abbreviations.csv")


@pytest.fixture
def table() -> AbbreviationTable:
    """A small fictional abbreviation list, built by hand."""
    built = AbbreviationTable()
    for phrase, abbr in [
        ("Cooling Tower", "CT"),
        ("Cooling", "COL"),
        ("Tower", "TWR"),
        ("Boiler Feed Water", "BFW"),
        ("Feed Water", "FW"),
        ("Water", "WTR"),
        ("Pump", "PMP"),
        ("Level Transmitter", "LT"),
        ("Level", "LVL"),
        ("Transmitter", "TX"),
        ("Tank", "TNK"),
        ("No", "NO"),
    ]:
        built.add(phrase, abbr, source="company list")
    return built


@pytest.fixture
def config() -> NamingConfig:
    return NamingConfig()


@pytest.fixture
def sample_table(abbreviation_frame) -> AbbreviationTable:
    """The list built from the sample file (columns chosen at runtime)."""
    built, _report = load_table_from_frame(
        abbreviation_frame, "Word / Phrase", "Approved Abbreviation"
    )
    return built
