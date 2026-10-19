"""TagForge - Streamlit app entry point.

Run with::

    streamlit run app.py

* **Fill abbreviations into columns** (default) - map source columns to
  abbreviation columns that already exist in your file and download the
  filled workbook. No new columns are created.
* **Tag name generator** - the step-by-step wizard that builds complete
  tag names from a template.

Everything runs locally; uploaded files are never modified.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure "import tagforge" works no matter which folder Streamlit is
# started from.
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from tagforge.ui.fill_pages import render_fill_sidebar, render_fill_step  # noqa: E402
from tagforge.ui.modes import MODE_TAG, render_mode_switch  # noqa: E402
from tagforge.ui.pages import render_current_step, render_sidebar  # noqa: E402
from tagforge.ui.state import AppState  # noqa: E402


def main() -> None:
    st.set_page_config(
        page_title="TagForge",
        page_icon="🏷️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.title("TagForge")
    st.caption(
        "Fill the abbreviation columns already in your file from your "
        "abbreviation list. No match = empty cell. Runs fully offline."
    )

    state = AppState()
    with st.sidebar:
        mode = render_mode_switch(state)

    if mode == MODE_TAG:
        render_sidebar(state)
        render_current_step(state)
    else:
        render_fill_sidebar(state)
        render_fill_step(state)


if __name__ == "__main__":
    main()
else:  # Streamlit executes the script as a module, so run it either way
    main()
