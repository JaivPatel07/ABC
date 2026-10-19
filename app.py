"""TagForge - Streamlit app entry point.

Run with::

    streamlit run app.py

Two modes share the same uploaded files and the same abbreviation table:

* **Fill abbreviations into columns** - the fast path: upload the main sheet and
  the abbreviation list, tick the columns that need a short form and download a
  workbook where every new cell contains the abbreviation or is left empty.
* **Tag name generator** - the eight-step wizard that builds complete tag names
  from a template.

The app itself only sets up the page and hands over to
:mod:`tagforge.ui.fill_pages` / :mod:`tagforge.ui.pages`.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Make sure "import tagforge" works no matter which folder Streamlit is started
# from (this is what makes `streamlit run app.py` work on any Windows PC).
ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st  # noqa: E402

from tagforge import __version__  # noqa: E402
from tagforge.ui.fill_pages import render_fill_sidebar, render_fill_step  # noqa: E402
from tagforge.ui.modes import MODE_TAG, render_mode_switch  # noqa: E402
from tagforge.ui.pages import render_current_step, render_sidebar  # noqa: E402
from tagforge.ui.state import AppState  # noqa: E402

APP_TITLE = "TagForge · Abbreviation Filler & Tag Name Generator"

CUSTOM_CSS = """
<style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    h1 {letter-spacing: -0.02em;}
    .stDownloadButton button {border-radius: 6px;}
    footer {visibility: hidden;}
</style>
"""


def main() -> None:
    st.set_page_config(
        page_title=APP_TITLE,
        page_icon="🏷️",
        layout="wide",
        initial_sidebar_state="expanded",
        menu_items={
            "About": (
                "TagForge - fill your spreadsheet columns with the abbreviations from "
                "your company list, or generate industrial tag names. Runs fully "
                "offline; your files are never modified."
            )
        },
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.title("🏷️ TagForge")
    st.caption(
        "Fill any number of columns with the abbreviations from your company list - "
        "values that are not in the list stay empty. Or generate full tag names with "
        "the step-by-step wizard. Everything runs offline and your original files are "
        "never modified."
    )

    state = AppState()
    with st.sidebar:
        st.title("TagForge")
        st.caption("Abbreviation filler & tag-name generator · works fully offline")
        mode = render_mode_switch(state)

    if mode == MODE_TAG:
        render_sidebar(state)
        render_current_step(state)
    else:
        render_fill_sidebar(state)
        render_fill_step(state)

    st.divider()
    st.caption(f"TagForge v{__version__} · works locally, no external services · "
               f"your uploaded files are never modified")


if __name__ == "__main__":
    main()
else:  # Streamlit executes the script as a module, so run it either way
    main()
