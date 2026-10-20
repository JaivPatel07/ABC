"""The two things TagForge can do, chosen at the top of the sidebar."""

from __future__ import annotations

from typing import Tuple

import streamlit as st

__all__ = ["MODE_FILL", "MODE_TAG", "MODE_OPTIONS", "render_mode_switch"]

MODE_FILL = "Fill abbreviations into columns"
MODE_TAG = "Tag name generator"
MODE_OPTIONS: Tuple[str, ...] = (MODE_FILL, MODE_TAG)

_MODE_HELP = (
    "**Fill abbreviations into columns** lets you map each column by hand: "
    "choose the full-text column and the column where the abbreviation goes. "
    "The target can be an existing column or a new column added at the end. "
    "A value that is not in the list leaves the cell empty.\n\n"
    "**Tag name generator** is the step-by-step wizard that builds a "
    "complete tag from a template."
)


def render_mode_switch(state) -> str:
    """Render the mode radio in the sidebar and remember the choice.

    The fill mode is the default because it is the shortest path from two
    uploaded files to a finished workbook.
    """
    stored = state.get("mode", MODE_FILL)
    index = MODE_OPTIONS.index(stored) if stored in MODE_OPTIONS else 0
    choice = st.radio(
        "What do you want to do?",
        options=list(MODE_OPTIONS),
        index=index,
        key="mode_radio",
        help=_MODE_HELP,
    )
    state.mode = choice
    return choice
