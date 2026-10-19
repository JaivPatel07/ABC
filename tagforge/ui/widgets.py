"""Small reusable Streamlit widgets used by the step pages."""

from __future__ import annotations

import inspect
from typing import Any, Dict, List, Optional, Sequence, Tuple

import pandas as pd
import streamlit as st

__all__ = [
    "full_width",
    "section",
    "note",
    "metric_row",
    "download_button",
    "column_picker",
    "sheet_picker",
    "header_row_picker",
    "placeholder_help_table",
    "styled_status_frame",
    "chips",
    "two_column",
]

def full_width(element) -> Dict[str, Any]:
    """``kwargs`` that make an element span the page.

    Streamlit renamed ``use_container_width=True`` to ``width="stretch"``
    (1.50+) and will drop the old name, so the argument is chosen by looking at
    the element's signature instead of hardcoding one of them.
    """
    try:
        parameters = inspect.signature(element).parameters
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return {"use_container_width": True}
    return {"width": "stretch"} if "width" in parameters else {"use_container_width": True}


_SEVERITY_COLORS = {
    "OK": "#0f9d58",
    "Unknown words": "#f4b400",
    "Empty": "#db4437",
    "error": "#db4437",
    "warning": "#f4b400",
    "info": "#4285f4",
}


def section(title: str, subtitle: str = "") -> None:
    """A step heading with a divider."""
    st.subheader(title)
    if subtitle:
        st.caption(subtitle)
    st.divider()


def note(text: str, kind: str = "info") -> None:
    """Render one of Streamlit's callouts by name."""
    render = {
        "info": st.info,
        "success": st.success,
        "warning": st.warning,
        "error": st.error,
    }.get(kind, st.info)
    render(text, icon=None)


def metric_row(items: Sequence[Tuple[str, object]], columns: int = 4) -> None:
    """Render a row of metrics (label, value)."""
    if not items:
        return
    cols = st.columns(min(columns, max(1, len(items))))
    for col, (label, value) in zip(cols, items):
        col.metric(label, value)


def download_button(
    label: str,
    data: bytes,
    file_name: str,
    mime: str = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    key: Optional[str] = None,
    help_text: Optional[str] = None,
) -> None:
    st.download_button(
        label=label,
        data=data,
        file_name=file_name,
        mime=mime,
        key=key,
        help=help_text,
        **full_width(st.download_button),
    )


def column_picker(
    columns: Sequence[str],
    key: str,
    label: str = "Column",
    guess: Optional[str] = None,
    help_text: Optional[str] = None,
) -> Optional[str]:
    """A dropdown built from the columns that are actually in the file."""
    options: List[str] = [""] + [str(column) for column in columns]
    index = 0
    if guess and str(guess) in options:
        index = options.index(str(guess))
    choice = st.selectbox(
        label,
        options=options,
        index=index,
        key=key,
        format_func=lambda value: "-- select a column --" if value == "" else value,
        help=help_text,
    )
    return choice or None


def sheet_picker(sheets: Sequence[str], key: str, label: str = "Worksheet") -> Optional[str]:
    if not sheets:
        return None
    if len(sheets) == 1:
        st.caption(f"Worksheet: **{sheets[0]}**")
        return sheets[0]
    return st.selectbox(label, options=list(sheets), key=key)


def header_row_picker(key: str, value: int = 0, max_row: int = 25) -> int:
    """1-based header row number for the user, 0-based for pandas."""
    return int(
        st.number_input(
            "Header row (1 = first row of the file)",
            min_value=1,
            max_value=max_row,
            value=int(value or 0) + 1,
            step=1,
            key=key,
            help="If the first rows contain a report title, set this to the row that holds the column names.",
        )
    ) - 1


def placeholder_help_table(rows: Sequence[Tuple[str, str]]) -> None:
    st.table(pd.DataFrame(rows, columns=["Placeholder", "What it becomes"]))


def chips(values: Sequence[str], color: str = "#e8f0fe") -> None:
    """Render short labels as inline 'chips'."""
    if not values:
        return
    html = " ".join(
        f'<span style="background:{color};border-radius:10px;padding:2px 9px;'
        f'margin:2px;display:inline-block;font-size:0.85rem;">{value}</span>'
        for value in values
    )
    st.markdown(html, unsafe_allow_html=True)


def two_column(left_ratio: int = 1, right_ratio: int = 1):
    return st.columns([left_ratio, right_ratio])


def styled_status_frame(frame: pd.DataFrame, status_column: str = "Status") -> "pd.io.formats.style.Styler":
    """Colour rows by their status so problems stand out."""

    def _colour(row):
        status = str(row.get(status_column, ""))
        colour = _SEVERITY_COLORS.get(status, "#ffffff")
        if status == "OK":
            return [f"background-color: {colour}22"] * len(row)
        return [f"background-color: {colour}33; font-weight: 600"] * len(row)

    styler = frame.style.apply(_colour, axis=1)
    return styler
