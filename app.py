"""TagForge - Streamlit app entry point.

Run with::

    streamlit run app.py

The app itself only sets up the page and hands over to
:mod:`tagforge.ui.pages`, which contains the eight wizard steps.
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
from tagforge.ui.pages import render_current_step, render_sidebar  # noqa: E402
from tagforge.ui.state import AppState  # noqa: E402

APP_TITLE = "TagForge · Industrial Tag Name Generator"

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
                "TagForge - generate industrial equipment tag names from your company "
                "abbreviation list. Runs fully offline; your files are never modified."
            )
        },
    )
    st.markdown(CUSTOM_CSS, unsafe_allow_html=True)

    st.title("🏷️ TagForge")
    st.caption(
        "Turn equipment descriptions into standard tag names using your company's own "
        "abbreviation list - offline, with every original column preserved."
    )

    state = AppState()
    render_sidebar(state)
    render_current_step(state)

    st.divider()
    st.caption(f"TagForge v{__version__} · works locally, no external services · "
               f"your uploaded files are never modified")


if __name__ == "__main__":
    main()
else:  # Streamlit executes the script as a module, so run it either way
    main()
