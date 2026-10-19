# TagForge

Fill the abbreviation columns **already in your file** with your company's
abbreviation list. Runs 100% locally — no internet, no API keys.
Your uploaded files are never modified; the result is a download.

## How it works

Your main file already has empty abbreviation columns, for example:

| Equipment Description | Equipment Description Abbr | Parameter | Parameter Abbr |
| --------------------- | -------------------------- | --------- | -------------- |
| Cooling Tower No 2    |                            | Temperature |              |
| Agitator              |                            | Flow      |                |

You tell the app **which column to fill (target)** and **where the full
text comes from (source)** — for as many columns as you like in one run.
It downloads the same file with those columns filled:

| Equipment Description | Equipment Description Abbr | Parameter | Parameter Abbr |
| --------------------- | -------------------------- | --------- | -------------- |
| Cooling Tower No 2    | CT No 2                    | Temperature | TMP          |
| Agitator              | *(empty)*                  | Flow      | *(empty)*        |

Rules:

- **No new column is created.** You provide the target column; the app
  only writes into it (in the downloaded copy).
- Many columns at once — tick all target columns (or **Select all
  abbreviation columns**), pick a source for each one.
- A value that is not in the abbreviation list stays **empty**. The
  original text is never copied into the target column.
- No settings to choose. Each word/phrase is replaced by its
  abbreviation from your list (`Cooling Tower No 2` → `CT No 2`);
  unknown words are kept as typed, and a cell with no match at all
  stays empty.

## The 4 steps

| Step | What you do |
| ---- | ----------- |
| 1. Upload main file | Your `.xlsx` / `.xlsm` / `.csv` file, with its empty abbreviation columns. |
| 2. Upload abbreviation list | The word/phrase → abbreviation list. Pick which columns hold the phrase and the abbreviation. |
| 3. Map columns | Tick the target columns to fill, pick the source column for each. Columns named `… Abbr` are detected and paired automatically. |
| 4. Preview and download | Check the result, then download the filled Excel file (one sheet, same columns, same name). |

A separate **Tag name generator** mode (sidebar) builds complete tag
names from a template, e.g. `Cooling Tower No 2` → `CT_NO_2`.

## Run it

You need Python 3.10+.

**Windows (easiest):** double-click `setup_windows.bat` once, then
`run_app.bat`. The app opens at <http://localhost:8501>.

**Any OS:**

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Sample files to try are in `samples/` (`equipment_data.xlsx` already has
empty `… Abbr` target columns).

## Tests

```bash
python -m pytest -q
```

## Project structure

```
app.py                  Streamlit entry point
tagforge/
  column_fill.py        source -> target filling engine (no columns created)
  detect.py             guesses column pairs (e.g. "X" -> "X Abbr")
  abbreviations.py      the abbreviation list + phrase matching
  taggen.py, pipeline.py, config.py, validation.py, reporting.py
                        the tag-name generator mode
  io_utils.py, exporters.py, text_utils.py
  ui/
    fill_pages.py       the 4 simple fill steps
    pages.py            the tag-generator wizard
    modes.py, state.py, widgets.py
samples/                fictional sample files
tests/                  pytest suite
```

Programmatic use:

```python
from tagforge import FillConfig, FillMapping, run_column_fill

pairs = [FillMapping("Equipment Description", "Equipment Description Abbr")]
result = run_column_fill(df, table, pairs, FillConfig())
result.output_frame   # same columns as df, target column filled
```
