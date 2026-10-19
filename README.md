# 🏷️ TagForge — Abbreviation Filler & Tag Name Generator

One app, **your company's own abbreviation list**, two ways to use it.

**Fill abbreviations into columns** — upload the main sheet and the abbreviation
list, tick the columns that need a short form, download the same sheet with a new
abbreviation column next to each one. A value that is **not** in the list stays
**empty** — the original text is never copied into the new column.

```
Plant Section      →  Plant Section Abbr     Equipment Description     →  Equipment Description Abbr
Power House           PH                     Cooling Tower No 2           CT
Boiler House          BH                     Agitator                     (empty)
```

**Generate tag names** — build a complete tag from a naming template:

```
"Cooling Tower No 2"                 →  CT_NO_2
"Boiler Feed Water Pump B"           →  BFW_PMP_B
"Compressor Discharge Pressure …"    →  CMP_DIS_PI
```

Runs **100 % locally** — no internet, no API keys, no AI service. Your uploaded
files are only ever read; results are offered as a download.

---

## Contents

1. [What it does (and what it never does)](#what-it-does-and-what-it-never-does)
2. [The two modes](#the-two-modes)
3. [Mode 1 — fill abbreviations into columns](#mode-1--fill-abbreviations-into-columns-4-steps)
4. [Install and run on Windows (step by step)](#install-and-run-on-windows-step-by-step)
5. [Install on macOS / Linux](#install-on-macos--linux)
6. [Project structure](#project-structure)
7. [Mode 2 — the tag-name generator (8 steps)](#mode-2--the-tag-name-generator-8-steps)
8. [The naming template](#the-naming-template)
9. [Sample files](#sample-files)
10. [Running the tests](#running-the-tests)
11. [Troubleshooting](#troubleshooting)
12. [Design notes](#design-notes)

---

## What it does (and what it never does)

**Does**

- reads `.xlsx`, `.xlsm` and `.csv` files (equipment data **and** abbreviation list)
- lists every worksheet and every column **found in your file** — you choose
- matches **multi-word phrases** (`Cooling Tower` → `CT`) and always prefers the
  **longest** match
- fills **any number of columns in one run** — each chosen column gets its own
  abbreviation column right next to it
- leaves the new cell **empty** when a value is not in the list (the original
  text is never copied into it)
- offers three matching rules: *any match in the cell*, *whole cell must match*,
  *every word must match*
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
- ❌ invents an abbreviation that is not in your list (the filler leaves the
  cell **empty**; the tag wizard keeps unknown words as typed **and reports
  them**)
- ❌ modifies, moves or overwrites your source file
- ❌ needs internet access or a paid service

---

## The two modes

Pick the mode at the top of the sidebar. Uploaded files and the abbreviation
list are **shared** between the modes, so you only upload them once.

| Mode | What it is for | Steps |
| ---- | -------------- | ----- |
| **Fill abbreviations into columns** | Fill one or many columns of an existing sheet with short forms. Unmatched values stay empty. | 4 |
| **Tag name generator** | Build a complete tag name (prefix, separator, row number, other columns…) from one text column. | 8 |

---

## Mode 1 — fill abbreviations into columns (4 steps)

This is the fast path when your main sheet already has all the data and you only
want the approved short form next to each value.

| Step | What you do |
| ---- | ----------- |
| **1. Upload the main Excel file** | Choose the `.xlsx`/`.xlsm`/`.csv` file with all your data. Pick the worksheet and header row if needed. Every column found in the file is shown. |
| **2. Upload the abbreviation list** | Upload the **one** list used for every column and say which column holds the word/phrase and which holds the abbreviation. |
| **3. Choose columns to fill** | Tick every column that needs a short form (e.g. `Equipment Description`, `Parameter`, `Plant Section`). A new column is added next to each one. You can rename each new column; the matching rule you pick applies to all of them. |
| **4. Preview and download** | Check the summary and the preview, then download the workbook (plus a summary / *not found* report and a CSV if you want). |

### Matching rules

| Rule | Meaning | `Cooling Tower No 2` | `Cooling Tower` |
| ---- | ------- | -------------------- | --------------- |
| **Any match** (default) | The longest phrase found **anywhere** in the cell wins; the rest of the cell is ignored. | `CT` | `CT` |
| **Whole cell must match exactly** | The complete cell must be a phrase from the list. | *(empty)* | `CT` |
| **Every word must match** | Every word must be in the list; the abbreviations are joined. One unknown word empties the cell (numbers can be kept). | `CT_NO_2` | `CT` |

Phrases are matched case-insensitively and regardless of extra spaces or
punctuation, so `  cooling   TOWER ` and `Cooling Tower` are the same value.
Simple plurals (`Pumps` → `Pump`) can be switched on; they are off by default.

### What happens when there is no abbreviation?

By default the new cell is **left empty** — the original text is **not** copied
into it and the source column is **not** changed. A *Not Found* report lists
every value that had no abbreviation, with its count and first row, so you can
add the missing entries to your list and run it again.

If you prefer to keep the original text for unmatched values, there is an option
for that in step 3. The default is empty, exactly as described above.

### Example

Main file (unchanged) and the two new columns created by the filler:

| Plant Section | **Plant Section Abbr** | Equipment Description | **Equipment Description Abbr** | Parameter | **Parameter Abbr** |
| ------------- | ---------------------- | --------------------- | ------------------------------ | --------- | ------------------ |
| Power House | `PH` | Cooling Tower No 2 | `CT` | Temperature | `TMP` |
| Boiler House | `BH` | Boiler Feed Water Pump B | `BFW` | Flow | *(empty)* |
| Boiler House | `BH` | Agitator | *(empty)* | Pressure | `PR` |

The original columns are kept exactly as they are; the abbreviation columns are
inserted directly after the column they belong to. If a name you type already
exists, ` (2)` is appended so an existing column can never be overwritten.

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
│   ├── column_fill.py          # fills columns; empty cell when no match
│   ├── config.py               # NamingConfig: template, separators, casing
│   ├── taggen.py               # text -> tag name
│   ├── validation.py           # empty / unknown / duplicate / invalid checks
│   ├── pipeline.py             # ties it together for a whole DataFrame
│   ├── reporting.py            # unmatched-word and issue reports
│   ├── exporters.py            # builds the downloadable workbooks
│   ├── io_utils.py             # dynamic .xlsx / .csv reading and writing
│   ├── detect.py               # column *hints* for dropdown defaults
│   └── ui/
│       ├── modes.py            # the two modes and the sidebar switch
│       ├── fill_pages.py       # the four column-filler steps
│       ├── state.py            # namespaced session state
│       ├── widgets.py          # small reusable Streamlit widgets
│       └── pages.py            # the eight tag-wizard steps
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
└── tests/                      # pytest suite (114 tests)
    ├── test_text_utils.py
    ├── test_abbreviations.py
    ├── test_phrase_matching.py
    ├── test_unknown_words.py
    ├── test_tag_generation.py
    ├── test_validation.py
    ├── test_pipeline_export.py
    ├── test_column_fill.py     # the abbreviation filler engine + export
    └── test_streamlit_app.py   # both modes, headless
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

The column filler is just as scriptable:

```python
from tagforge import FillConfig, FillMapping, run_column_fill

result = run_column_fill(
    df,
    table,
    [FillMapping("Equipment Description"), FillMapping("Parameter")],
    FillConfig(),  # "Any match" + empty cell when nothing is found
)

print(result.output_frame[["Equipment Description", "Equipment Description Abbr"]].head())
result.not_found_cells   # how many cells stayed empty
```

---

## Mode 2 — the tag-name generator (8 steps)

Switch to **Tag name generator** at the top of the sidebar. This mode builds one
complete tag from a template instead of just filling a short form.

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

They also work for the filler: upload `equipment_data.xlsx` as the main file and
`company_abbreviations.csv` as the list, then tick `Plant Section`,
`Equipment Description` and `Parameter`. You will see filled cells for known
values and empty cells for `Flow`, `Agitator`, `Chiller`, `Diesel` and the other
words that are deliberately missing from the list.

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
validation (empty, duplicates, invalid characters), the column filler (all three
matching rules, empty cells, output column placement, reports), file
import/export round-trips and a headless run of every step of both modes
(`streamlit.testing`).

---

## Troubleshooting

| Message | What to do |
| ------- | ---------- |
| *"'x.xls' is not a supported file type"* | Open it in Excel and **Save As → Excel Workbook (.xlsx)**. |
| *"… could not be read"* | Close the file in Excel (Excel locks open files) and try again. |
| Wrong column names shown | Change **Header row** (step 1) to the row that actually holds the column names. |
| Filler leaves almost everything empty | Check that the right phrase / abbreviation columns are selected in step 2, and try the *Any match* rule in step 3. |
| Filler fills a word I did not expect | *Any match* takes the longest phrase **anywhere** in the cell. Use *Whole cell must match exactly* for a strict match. |
| Filler should keep the original text for missing values | Change *When no abbreviation is found* in step 3 (the default is empty). |
| Every word is “unmatched” | Check you selected the right **phrase** and **abbreviation** columns in step 2. |
| Tag contains words I expected to be abbreviated | The word is not in your list — see step 6. Longer phrases always win, so check whether a longer phrase overlaps. |
| Tags are too long | Set *Maximum tag length* in step 4 (advanced section). |
| `streamlit` is not recognised | Activate the environment first: `.venv\Scripts\activate`. |
| Port 8501 already in use | Run `streamlit run app.py --server.port 8502`. |

---

## Design notes

- **No guessing, two honest behaviours.** In the filler, a value with no entry in
  the list produces an **empty cell**; the original text is never copied into
  the new column and a *Not Found* report lists the value. In the tag wizard the
  unknown word is written into the tag as typed and reported. Neither mode ever
  creates an abbreviation on its own.
- **Nothing is overwritten by the filler.** New columns are inserted after the
  source column; a clashing name gets ` (2)` appended, and the source frame is
  copied before anything is written.
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
