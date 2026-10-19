# 🏷️ TagForge — Industrial Tag Name Generator

Turn long equipment / section / parameter descriptions into standard tag names
using **your company's own abbreviation list**.

```
"Cooling Tower No 2"                 →  CT_NO_2
"Boiler Feed Water Pump B"           →  BFW_PMP_B
"Compressor Discharge Pressure …"    →  CMP_DIS_PI
```

Runs **100 % locally** — no internet, no API keys, no AI service. Your uploaded
file is only ever read; results are offered as a download.

---

## Contents

1. [What it does (and what it never does)](#what-it-does-and-what-it-never-does)
2. [Install and run on Windows (step by step)](#install-and-run-on-windows-step-by-step)
3. [Install on macOS / Linux](#install-on-macos--linux)
4. [Project structure](#project-structure)
5. [How to use the app — the 8 steps](#how-to-use-the-app--the-8-steps)
6. [The naming template](#the-naming-template)
7. [Sample files](#sample-files)
8. [Running the tests](#running-the-tests)
9. [Troubleshooting](#troubleshooting)
10. [Design notes](#design-notes)

---

## What it does (and what it never does)

**Does**

- reads `.xlsx`, `.xlsm` and `.csv` files (equipment data **and** abbreviation list)
- lists every worksheet and every column **found in your file** — you choose
- matches **multi-word phrases** (`Cooling Tower` → `CT`) and always prefers the
  **longest** match
- lets you add, edit or remove abbreviation mappings
- builds tags from a **naming template you configure** (separator, casing,
  prefix, suffix, row number, other columns…)
- shows original and generated tag side by side, fully editable
- flags unknown words, duplicate tags, empty cells and invalid characters
- exports a new Excel file with **all original columns and rows preserved**,
  plus a separate validation report
- handles messy data: inconsistent spacing, mixed casing, blank cells,
  duplicate rows, punctuation, numbers

**Never**

- ❌ hardcodes a column name, column position, equipment name or abbreviation
- ❌ invents an abbreviation that is not in your list (unknown words are kept
  as typed **and reported**)
- ❌ modifies, moves or overwrites your source file
- ❌ needs internet access or a paid service

---

## Install and run on Windows (step by step)

You need **Python 3.10 or newer** (3.11 recommended). Check with:

```bat
python --version
```

If that prints nothing, install Python from <https://www.python.org/downloads/>
and tick **“Add python.exe to PATH”** during installation.

### Option A — the two batch files (easiest)

1. Put the project folder somewhere easy, e.g. `C:\TagForge\`.
2. **Double-click `setup_windows.bat`** — it creates a virtual environment and
   installs the dependencies (needs internet only the first time).
3. **Double-click `run_app.bat`** — it starts the app and opens your browser at
   `http://localhost:8501`.

To stop the app: click the terminal window and press `Ctrl + C`.

### Option B — manual, step by step

Open **Command Prompt** (`Win + R` → `cmd` → Enter) and type:

```bat
cd C:\TagForge

REM 1. create an isolated environment (do this once)
python -m venv .venv

REM 2. activate it (you will see (.venv) at the start of the line)
.venv\Scripts\activate

REM 3. install the dependencies (once, needs internet)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt

REM 4. run the app
streamlit run app.py
```

Your browser opens automatically at **http://localhost:8501**.
To run it again later, repeat steps 2 and 4 (activation + `streamlit run`).

> **Tip:** keep the Command Prompt window open while you use the app. Closing it
> stops the server.

### Updating / reinstalling

```bat
.venv\Scripts\activate
python -m pip install --upgrade -r requirements.txt
```

---

## Install on macOS / Linux

```bash
cd TagForge
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
streamlit run app.py
```

---

## Project structure

```
TagForge/
├── app.py                      # Streamlit entry point (run this)
├── requirements.txt            # dependencies
├── README.md                   # this file
├── setup_windows.bat           # one-time Windows installer
├── run_app.bat                 # starts the app on Windows
│
├── tagforge/                   # the application package
│   ├── __init__.py             # public API (import shortcuts)
│   ├── text_utils.py           # cleaning + tokenising text
│   ├── abbreviations.py        # the abbreviation list and phrase matching
│   ├── config.py               # NamingConfig: template, separators, casing
│   ├── taggen.py               # text -> tag name
│   ├── validation.py           # empty / unknown / duplicate / invalid checks
│   ├── pipeline.py             # ties it together for a whole DataFrame
│   ├── reporting.py            # unmatched-word and issue reports
│   ├── exporters.py            # builds the downloadable workbooks
│   ├── io_utils.py             # dynamic .xlsx / .csv reading and writing
│   ├── detect.py               # column *hints* for dropdown defaults
│   └── ui/
│       ├── state.py            # namespaced session state
│       ├── widgets.py          # small reusable Streamlit widgets
│       └── pages.py            # the eight wizard steps
│
├── samples/                    # fictional test data
│   ├── equipment_data.xlsx     # 29 rows, 2 worksheets
│   ├── equipment_data.csv
│   ├── company_abbreviations.xlsx
│   └── company_abbreviations.csv
│
├── scripts/
│   └── generate_samples.py     # recreates the sample files
│
└── tests/                      # pytest suite (79 tests)
    ├── test_text_utils.py
    ├── test_abbreviations.py
    ├── test_phrase_matching.py
    ├── test_unknown_words.py
    ├── test_tag_generation.py
    ├── test_validation.py
    ├── test_pipeline_export.py
    └── test_streamlit_app.py
```

The engine (`tagforge/*.py`) has **no Streamlit dependency** — you can import it
in your own scripts:

```python
import pandas as pd
from tagforge import NamingConfig, load_table_from_frame, run_pipeline

abbr = pd.read_csv("samples/company_abbreviations.csv")
table, report = load_table_from_frame(abbr, "Word / Phrase", "Approved Abbreviation")

df = pd.read_excel("samples/equipment_data.xlsx", sheet_name="Equipment List")
config = NamingConfig(template="{prefix}{abbr}", prefix="MERIDIAN", separator="_")

result = run_pipeline(df, "Equipment Description", table, config)
df["Generated_Tag"] = result.tags
```

---

## How to use the app — the 8 steps

| Step | What you do |
| ---- | ----------- |
| **1. Upload equipment data** | Choose the `.xlsx`/`.csv` file with the names to convert. Pick the worksheet and the header row if your file has a title above the column names. Every column found in the file is listed. |
| **2. Upload abbreviation list** | Upload your company list and say which column holds the **word/phrase** and which holds the **abbreviation** (dropdowns are filled from your file). Duplicate or blank rows are reported, not guessed. |
| **3. Choose column to convert** | Pick the column to process from a dropdown built from your file. All other columns are kept exactly as they are. You can change this at any time. |
| **4. Set naming convention** | Choose a template, separator, letter case, prefix/suffix, row numbers… A live preview shows the first rows. |
| **5. Preview and edit** | Original text and generated tag side by side. Type in the tag column to override any row (kept and marked as *manually edited*). |
| **6. Fix unmatched words** | Every word missing from the list, with the number of occurrences and an example row. Type the official abbreviation (or mark the word to be dropped) and press **Add the abbreviations I typed**. You can also edit the whole list in the table below. |
| **7. Check validation** | Summary of empty values, unmatched words, duplicate tags and invalid characters, with one click to number duplicate tags automatically. |
| **8. Download results** | New workbook with every original column and row plus the generated tags. Also downloadable: the validation report and the updated abbreviation list. |

### Export options (step 8)

- **Add a new column** (default) — e.g. `Generated_Tag`, inserted right after the
  column you processed.
- **Replace the processed column** — the original text is kept in a new
  `<column> (original)` column so nothing is lost.
- **Include report sheets** — adds *Summary*, *Unmatched Words*,
  *Validation Issues*, *Abbreviations Used* and *Run Settings* to the same
  workbook (or download them as a separate file).

---

## The naming template

The template decides what a tag is made of. Placeholders:

| Placeholder | Becomes |
| ----------- | ------- |
| `{abbr}` | the abbreviated form of the selected column |
| `{original}` | the original text of the selected column (cleaned) |
| `{prefix}` | the text in the *Prefix* box (e.g. a plant code) |
| `{suffix}` | the text in the *Suffix* box (e.g. a revision) |
| `{index}` | the row number, starting at *Row number starts at* |
| `{index:04d}` | the row number zero padded → `0001`, `0002`, … |
| `{col:Column Name}` | the value of another column of the same row |

**Separators:** two placeholders written next to each other are joined with the
configured separator. A separator you type yourself is kept as typed.

| Template | Separator | Prefix | Result |
| -------- | --------- | ------ | ------ |
| `{abbr}` | `_` | – | `CT_NO_2` |
| `{prefix}{abbr}` | `_` | `ADANI_XYZ` | `ADANI_XYZ_CT_NO_2` |
| `{prefix}-{abbr}` | `_` | `ADANI` | `ADANI-CT-NO-2` |
| `{prefix}{abbr}{index:03d}` | `_` | `P1` | `P1_CT_NO_2_001` |
| `{col:Plant Section}{abbr}` | `_` | – | `POWER_HOUSE_CT_NO_2` |

Other settings (step 4): letter case (`UPPERCASE` / `lowercase` / keep
original), separator between abbreviated words, filler words to drop, keep or
remove numbers, plural matching, repeated-word collapsing, maximum length with
truncation mode, allowed characters, and automatic numbering of duplicate tags.

> If your company uses a format that is not covered, type it into the template
> or tell me the rule — the app will ask rather than guess.

---

## Sample files

Everything in `samples/` is **fictional** (invented company “Meridian Process
Plants”) and safe to use for a first test:

- `equipment_data.xlsx` — 29 rows, two worksheets, with messy spacing, mixed
  casing, one empty description, an exact duplicate row and several words that
  are deliberately **not** in the abbreviation list (`Scrubber`, `Chiller`,
  `Silo`, `Agitator`, `Diesel`, `Generator`, `Recirculation`, `Circulating`).
- `company_abbreviations.xlsx` — 67 rows, columns named
  `Word / Phrase` / `Approved Abbreviation` / `Category`, including multi-word
  phrases, a `Valve / Valves` entry and two duplicate rows (reported on load).

Recreate them at any time with:

```bash
python scripts/generate_samples.py
```

---

## Running the tests

```bash
.venv\Scripts\activate          # Windows
python -m pytest -q
```

The suite covers abbreviation matching, phrase (longest-match) matching,
unknown words, tag generation (templates, separators, casing, truncation),
validation (empty, duplicates, invalid characters), file import/export
round-trips and a headless run of every wizard step (`streamlit.testing`).

---

## Troubleshooting

| Message | What to do |
| ------- | ---------- |
| *"'x.xls' is not a supported file type"* | Open it in Excel and **Save As → Excel Workbook (.xlsx)**. |
| *"… could not be read"* | Close the file in Excel (Excel locks open files) and try again. |
| Wrong column names shown | Change **Header row** (step 1) to the row that actually holds the column names. |
| Every word is “unmatched” | Check you selected the right **phrase** and **abbreviation** columns in step 2. |
| Tag contains words I expected to be abbreviated | The word is not in your list — see step 6. Longer phrases always win, so check whether a longer phrase overlaps. |
| Tags are too long | Set *Maximum tag length* in step 4 (advanced section). |
| `streamlit` is not recognised | Activate the environment first: `.venv\Scripts\activate`. |
| Port 8501 already in use | Run `streamlit run app.py --server.port 8502`. |

---

## Design notes

- **No guessing.** If a word is not in the abbreviation list it is written into
  the tag as typed and reported on the *Unmatched Words* sheet. The app never
  creates an abbreviation on its own.
- **Nothing is hardcoded.** Column names, worksheets, header rows, separators,
  casing and templates all come from the user at runtime. `tagforge/detect.py`
  only *suggests* dropdown defaults.
- **Source files are read-only.** `io_utils.read_table` opens the uploaded bytes;
  exports are written into an in-memory buffer and handed to the browser as a
  download.
- **Large files.** Excel files are opened in read-only mode, the preview shows a
  limited number of rows (25 / 100 / 500 / 2000) while the export always
  contains every row, and generation runs once per settings change with a
  progress bar.
- **Modular.** The engine has no UI dependency, so it is easy to script, test or
  extend (for example a different front end, or a command-line version).
