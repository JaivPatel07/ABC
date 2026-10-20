# TagForge

Fill the abbreviation columns in your file — or add a **new abbreviation
column at the end** — from your company's abbreviation list. Runs 100%
locally — no internet, no API keys. Your uploaded files are never modified;
the result is a download.

## How it works

Your main file may already have empty abbreviation columns, for example:

| Equipment Description | Equipment Description Abbr | Parameter | Parameter Abbr |
| --------------------- | -------------------------- | --------- | -------------- |
| Cooling Tower No 2    |                            | Temperature |              |
| Agitator              |                            | Flow      |                |

You map every column **by hand**, one row per column: choose **where the
full text comes from (source)** and **where the abbreviation must go
(target)**. The target can be:

- a column that **already exists** in your file (usually empty), or
- **a new column**, which is added at the **end** of the downloaded file.

It downloads the same file with those columns filled:

| Equipment Description | Equipment Description Abbr | Parameter | Parameter Abbr |
| --------------------- | -------------------------- | --------- | -------------- |
| Cooling Tower No 2    | CT No 2                    | Temperature | TMP          |
| Agitator              | Agitator                   | Flow      | Flow             |

Rules:

- **You choose every mapping.** Nothing is decided for you; the suggested
  pairs (`… Abbr` columns) are only a starting point you can change.
- **New columns are optional.** A new column is appended at the end of the
  downloaded file; existing columns keep their place.
- Many columns at once — **＋ Add column** adds another mapping row.
  **✕** removes a row, **Remove all** starts over.
- **Nothing is emptied.** A word that is not in the abbreviation list is
  **kept as typed**, so a sentence is never lost because of one missing
  word (`Cooling Tower Scrubber` → `CT Scrubber`). A value where **no**
  word has an abbreviation keeps its original text (`Agitator` →
  `Agitator`). Only a cell that is empty in your file stays empty.
- **Every missing word is listed.** Step 4 shows *Values with words that
  have no abbreviation* (the original value, which words were missing and
  what was written) and *Words with no abbreviation* (one row per word,
  with a count), so you can add them to your list and fill again.
- No settings to choose. Each word/phrase is replaced by its
  abbreviation from your list (`Cooling Tower No 2` → `CT No 2`);
  numbers and unknown words stay as typed.

## The 4 steps

| Step | What you do |
| ---- | ----------- |
| 1. Upload main file | Your `.xlsx` / `.xlsm` / `.csv` file. It can already hold abbreviation columns, but it does not have to. |
| 2. Upload abbreviation list | The word/phrase → abbreviation list. Pick which columns hold the phrase and the abbreviation. |
| 3. Map columns manually | One row per column: pick the full-text **source** and the **target** column. Choose **➕ New column at the end…** to create one; type its name (blank = `<source> Abbr`). |
| 4. Preview and download | Check the result and the list of words with no abbreviation, then download the filled Excel file (one sheet, same columns — plus any new columns at the end). |

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
  column_fill.py        source -> target filling engine (new columns optional)
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

pairs = [
    # write into a column that already exists
    FillMapping("Equipment Description", "Equipment Description Abbr"),
    # create a new column and append it at the end of the output
    FillMapping("Parameter", "Short Parameter", new_column=True),
]
result = run_column_fill(df, table, pairs, FillConfig())
result.output_frame   # same columns as df (+ new ones at the end), filled
result.new_columns    # ["Short Parameter"]
```
