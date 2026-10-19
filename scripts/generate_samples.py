"""Create the fictional sample files in ``samples/``.

Run with::

    python scripts/generate_samples.py

All data here is fictional and safe to share: an invented company
("Meridian Process Plants"), invented equipment and invented abbreviations.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SAMPLES = ROOT / "samples"

# ---------------------------------------------------------------------------
# 1. Equipment data - deliberately messy on purpose:
#    mixed casing, double spaces, trailing spaces, blanks, duplicates,
#    numbers, punctuation and a few words that are NOT in the abbreviation list.
# ---------------------------------------------------------------------------
EQUIPMENT_ROWS = [
    ("Power House", "Cooling Tower No 2", "Temperature", 2, "old tag: CT-02"),
    ("Power House", "Cooling Tower No.  3", "Temperature", 2, "old tag: CT-03"),
    ("Boiler House", "boiler feed water pump a", "Flow", 1, "lowercase source data"),
    ("Boiler House", "Boiler Feed Water Pump B", "Flow", 1, ""),
    ("Boiler House", "Primary Air Fan - 1", "Pressure", 1, ""),
    ("Boiler House", "Primary Air Fan - 1", "Pressure", 1, "exact duplicate of row 5 -> duplicate tag"),
    ("Boiler House", "Primary Air Fan", "Pressure", 1, ""),
    ("Boiler House", "Induced Draft Fan", "Pressure", 1, ""),
    ("Boiler House", "Steam Drum Level Transmitter", "Level", 1, ""),
    ("Boiler House", "   steam   DRUM   pressure   TRANSMITTER  ", "Pressure", 1, "messy spacing + casing"),
    ("Cooling Water System", "Circulating Water Pump 1", "Flow", 1, ""),
    ("Cooling Water System", "Circulating Water Pump 2", "Flow", 1, ""),
    ("Water Treatment Plant", "Raw Water Storage Tank", "Level", 1, ""),
    ("Water Treatment Plant", "DM Water Storage Tank", "Level", 1, ""),
    ("Water Treatment Plant", "Effluent Treatment Plant Agitator", "Level", 1, "Agitator is not mapped"),
    ("Flue Gas System", "Flue Gas Desulphurisation Unit", "Pressure", 1, ""),
    ("Flue Gas System", "Electrostatic Precipitator", "Pressure", 1, ""),
    ("Flue Gas System", "Scrubber Recirculation Pump", "Flow", 1, "Scrubber is not mapped"),
    ("Ash Handling", "Ash Handling Conveyor 3", "Flow", 1, ""),
    ("Ash Handling", "Ash Silo Level Indicator", "Level", 1, "Silo is not mapped"),
    ("Turbine Hall", "Turbine Lube Oil Cooler", "Temperature", 1, ""),
    ("Turbine Hall", "Turbine Lube Oil Pump", "Flow", 1, ""),
    ("Compressor House", "Compressor Discharge Pressure Indicator", "Pressure", 1, ""),
    ("Compressor House", "Compressor Suction Temperature Gauge", "Temperature", 1, ""),
    ("Compressor House", "Instrument Air Receiver", "Pressure", 1, ""),
    ("Utilities", "Chiller Unit 2", "Temperature", 1, "Chiller is not mapped"),
    ("Utilities", "Fire Water Pump", "Pressure", 1, ""),
    ("Utilities", "", "Level", 0, "empty description - nothing to convert"),
    ("Utilities", "Emergency Diesel Generator", "Level", 1, "Diesel/Generator are not mapped"),
]

SECTION_ROWS = [
    ("PH", "Power House", "North"),
    ("BH", "Boiler House", "North"),
    ("CWS", "Cooling Water System", "South"),
    ("WTP", "Water Treatment Plant", "South"),
    ("FGS", "Flue Gas System", "North"),
    ("AH", "Ash Handling", "South"),
    ("TH", "Turbine Hall", "North"),
    ("CH", "Compressor House", "North"),
    ("UT", "Utilities", "South"),
]

# ---------------------------------------------------------------------------
# 2. The company abbreviation list.
#    Column names are unusual on purpose - the app must read them dynamically.
# ---------------------------------------------------------------------------
ABBREVIATIONS = [
    ("Cooling Tower", "CT", "Equipment"),
    ("Cooling Water", "CW", "System"),
    ("Boiler", "BLR", "Equipment"),
    ("Boiler Feed Water", "BFW", "System"),
    ("Feed Water", "FW", "System"),
    ("Feed", "FD", "General"),
    ("Water", "WTR", "General"),
    ("Pump", "PMP", "Equipment"),
    ("Primary Air", "PA", "System"),
    ("Forced Draft", "FD", "System"),
    ("Induced Draft", "ID", "System"),
    ("Fan", "FAN", "Equipment"),
    ("Air", "AIR", "General"),
    ("Steam", "STM", "General"),
    ("Drum", "DRM", "Equipment"),
    ("Level", "LVL", "Parameter"),
    ("Transmitter", "TX", "Instrument"),
    ("Level Transmitter", "LT", "Instrument"),
    ("Pressure", "PR", "Parameter"),
    ("Indicator", "IND", "Instrument"),
    ("Pressure Indicator", "PI", "Instrument"),
    ("Temperature", "TMP", "Parameter"),
    ("Gauge", "GA", "Instrument"),
    ("Temperature Gauge", "TG", "Instrument"),
    ("Tank", "TNK", "Equipment"),
    ("Storage Tank", "STK", "Equipment"),
    ("Raw Water", "RW", "System"),
    ("DM Water", "DMW", "System"),
    ("Flue Gas", "FG", "System"),
    ("Flue Gas Desulphurisation", "FGD", "System"),
    ("Unit", "UNT", "General"),
    ("Electrostatic Precipitator", "ESP", "Equipment"),
    ("Ash", "ASH", "Material"),
    ("Ash Handling", "AH", "System"),
    ("Handling", "HND", "General"),
    ("Conveyor", "CNV", "Equipment"),
    ("Turbine", "TUR", "Equipment"),
    ("Lube Oil", "LO", "System"),
    ("Oil", "OIL", "Material"),
    ("Cooler", "CLR", "Equipment"),
    ("Compressor", "CMP", "Equipment"),
    ("Discharge", "DIS", "General"),
    ("Suction", "SUC", "General"),
    ("Instrument", "INST", "General"),
    ("Instrument Air", "IA", "System"),
    ("Receiver", "RCV", "Equipment"),
    ("Effluent Treatment Plant", "ETP", "System"),
    ("Treatment", "TRT", "General"),
    ("Fire Water", "FWP", "System"),
    ("Fire", "FIR", "General"),
    ("Water Treatment Plant", "WTP", "System"),
    ("Power House", "PH", "Area"),
    ("Boiler House", "BH", "Area"),
    ("Plant", "PLT", "General"),
    ("Motor", "MTR", "Equipment"),
    ("Valve / Valves", "VLV", "Equipment"),
    ("Control Valve", "CV", "Equipment"),
    ("Panel", "PNL", "Electrical"),
    ("Switchgear", "SG", "Electrical"),
    ("Transformer", "TRF", "Electrical"),
    ("Emergency", "EMG", "General"),
    ("Standby", "STB", "General"),
    ("North", "N", "Direction"),
    ("South", "S", "Direction"),
    # --- the rows below exercise the "something is wrong" paths ---------------
    ("pump", "PMP", "duplicate of 'Pump' - ignored"),
    ("Cooling Tower", "CT", "duplicate entry - ignored"),
    ("", "", "blank row - ignored"),
]


def build_equipment_frame() -> pd.DataFrame:
    # The empty "… Abbr" columns are the *targets*: the filler writes the
    # abbreviation into the existing column, it never creates a new one.
    rows = []
    for index, (section, description, parameter, quantity, remark) in enumerate(EQUIPMENT_ROWS, start=1):
        rows.append(
            {
                "Sr No": index,
                "Plant Section": section,
                "Plant Section Abbr": "",
                "Equipment Description": description,
                "Equipment Description Abbr": "",
                "Parameter": parameter,
                "Parameter Abbr": "",
                "Qty": quantity,
                "Remarks": remark,
            }
        )
    return pd.DataFrame(rows)


def build_section_frame() -> pd.DataFrame:
    return pd.DataFrame(SECTION_ROWS, columns=["Section Code", "Section Name", "Area"])


def build_abbreviation_frame() -> pd.DataFrame:
    return pd.DataFrame(ABBREVIATIONS, columns=["Word / Phrase", "Approved Abbreviation", "Category"])


def main() -> None:
    SAMPLES.mkdir(parents=True, exist_ok=True)

    equipment = build_equipment_frame()
    sections = build_section_frame()
    abbreviations = build_abbreviation_frame()

    # Excel with two worksheets (so the worksheet dropdown has something to do)
    with pd.ExcelWriter(SAMPLES / "equipment_data.xlsx", engine="openpyxl") as writer:
        equipment.to_excel(writer, sheet_name="Equipment List", index=False)
        sections.to_excel(writer, sheet_name="Section List", index=False)

    equipment.to_csv(SAMPLES / "equipment_data.csv", index=False)

    with pd.ExcelWriter(SAMPLES / "company_abbreviations.xlsx", engine="openpyxl") as writer:
        abbreviations.to_excel(writer, sheet_name="Abbreviations", index=False)

    abbreviations.to_csv(SAMPLES / "company_abbreviations.csv", index=False)

    print(f"Equipment rows      : {len(equipment)} (sheet 'Equipment List') + {len(sections)} (sheet 'Section List')")
    print(f"Abbreviation rows   : {len(abbreviations)}")
    print(f"Written to          : {SAMPLES}")


if __name__ == "__main__":
    main()
