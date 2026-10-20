
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
