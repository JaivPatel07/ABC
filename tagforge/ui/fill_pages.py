"""The four steps of the "fill abbreviations into columns" mode.

Kept as simple as possible:

1. upload the main file,
2. upload the abbreviation list,
3. map columns - **source column -> target column**.  The target column
   already exists in the user's file (usually empty), so no new column is
   ever created.  Any number of pairs can be filled in one run,
4. preview and download.

There are no settings screens: abbreviations are matched word by word
(the :class:`~tagforge.column_fill.FillConfig` defaults) and a value with
no abbreviation leaves the target cell empty.

Uploaded files and the abbreviation table are shared with the tag wizard.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

from ..column_fill import (
    FillConfig,
    FillMapping,
    FillResult,
    build_fill_not_found_frame,
    build_fill_summary_frame,
    run_column_fill,
)
from ..detect import guess_fill_pairs, guess_pair
from ..exporters import build_fill_workbook
from ..io_utils import safe_filename
from .pages import _load_frame, _load_table, _reset_all, _store_upload
from .widgets import column_picker, display_frame, download_button, full_width, note

__all__ = [
    "FILL_STEP_TITLES",
    "FILL_STEPS",
    "render_fill_sidebar",
    "render_fill_step",
]

FILL_STEP_TITLES = [
    "Upload main file",
    "Upload abbreviation list",
    "Map columns (source -> target)",
    "Preview and download",
]
FILL_STEPS = [f"{index}. {title}" for index, title in enumerate(FILL_STEP_TITLES, start=1)]


# ===========================================================================
# navigation
# ===========================================================================
def render_fill_sidebar(state) -> None:
    with st.sidebar:
        st.divider()
        current = int(state.get("fill_step", 1) or 1)
        # Initialise the widget's session-state value once instead of passing
        # ``index``: callbacks may update ``fill_step_nav`` before the rerun,
        # and Streamlit warns when a widget has both defaults.
        if "fill_step_nav" not in st.session_state:
            st.session_state["fill_step_nav"] = FILL_STEPS[
                min(max(current, 1), len(FILL_STEPS)) - 1
            ]
        choice = st.radio(
            "Steps",
            options=FILL_STEPS,
            key="fill_step_nav",
            label_visibility="collapsed",
        )
        if choice in FILL_STEPS:
            state.fill_step = FILL_STEPS.index(choice) + 1

        if st.button("Start over", key="start_over", **full_width(st.button)):
            _reset_all(state)
            st.rerun()


def render_fill_step(state) -> None:
    step = int(state.get("fill_step", 1) or 1)
    handlers = {
        1: _step_fill_data,
        2: _step_fill_abbreviations,
        3: _step_fill_columns,
        4: _step_fill_download,
    }
    handlers.get(step, _step_fill_data)(state)


def _set_fill_step(state, step: int) -> None:
    """Callback: jump to ``step`` and update the sidebar radio with it."""
    step = max(1, min(int(step), len(FILL_STEPS)))
    state.fill_step = step
    st.session_state["fill_step_nav"] = FILL_STEPS[step - 1]


def _next_fill(state, label: str, enabled: bool = True) -> None:
    st.button(
        f"{label} →",
        disabled=not enabled,
        on_click=_set_fill_step,
        args=(state, int(state.get("fill_step", 1)) + 1),
        key="fill_next",
    )


def _go_fill(state, step: int) -> None:
    st.button(
        f"Go to step {step}",
        type="primary",
        key=f"fill_go_{step}",
        on_click=_set_fill_step,
        args=(state, step),
    )


def _require_fill_data(state) -> Optional[pd.DataFrame]:
    frame = state.data_frame
    if frame is None:
        note("Upload the main file first (step 1).", "warning")
        _go_fill(state, 1)
        return None
    return frame


def _require_fill_table(state):
    table = state.table
    if table is None or not len(table):
        note("Upload the abbreviation list first (step 2).", "warning")
        _go_fill(state, 2)
        return None
    return table


# ===========================================================================
# step 1 - main file
# ===========================================================================
def _step_fill_data(state) -> None:
    st.subheader("1. Upload main file")

    uploaded = st.file_uploader(
        "Main file (.xlsx, .xlsm or .csv)",
        type=["xlsx", "xlsm", "csv"],
        key="upl_data",
    )
    if uploaded is not None:
        _store_upload(state, "data", uploaded)
    elif state.data_bytes:
        st.caption(f"Loaded: **{getattr(state, 'data_file_name', '')}**")

    if not state.data_bytes:
        st.info("Upload your file. It should already contain the (empty) "
                "abbreviation column(s) you want filled.")
        return

    frame = _load_frame(state, "data")
    if frame is None:
        return

    st.caption(
        f"{len(frame):,} rows · {len(frame.columns):,} columns: "
        + ", ".join(str(column) for column in frame.columns)
    )
    st.dataframe(display_frame(frame.head(25)), **full_width(st.dataframe), hide_index=True)
    _next_fill(state, "Next: abbreviation list")


# ===========================================================================
# step 2 - abbreviation list
# ===========================================================================
def _step_fill_abbreviations(state) -> None:
    st.subheader("2. Upload abbreviation list")

    uploaded = st.file_uploader(
        "Abbreviation file (.xlsx, .xlsm or .csv)",
        type=["xlsx", "xlsm", "csv"],
        key="upl_abbr",
    )
    if uploaded is not None:
        _store_upload(state, "abbr", uploaded)
    elif state.abbr_bytes:
        st.caption(f"Loaded: **{getattr(state, 'abbr_file_name', '')}**")

    if not state.abbr_bytes:
        st.info("Upload the abbreviation list (word / phrase -> abbreviation).")
        return

    frame = _load_frame(state, "abbr")
    if frame is None:
        return

    columns = list(frame.columns)
    guess_phrase, guess_abbr = guess_pair(columns)
    left, right = st.columns(2)
    with left:
        phrase_col = column_picker(
            columns, "abbr_phrase_col", "Column with the word or phrase",
            guess=state.abbr_phrase_col or guess_phrase,
        )
    with right:
        abbr_col = column_picker(
            columns, "abbr_abbr_col", "Column with the abbreviation",
            guess=state.abbr_abbr_col or guess_abbr,
        )
    state.abbr_phrase_col = phrase_col
    state.abbr_abbr_col = abbr_col

    if not phrase_col or not abbr_col:
        note("Select both columns.", "warning")
        st.dataframe(display_frame(frame.head(15)), **full_width(st.dataframe), hide_index=True)
        return
    if phrase_col == abbr_col:
        note("Please choose two different columns.", "error")
        return

    table = _load_table(state, frame, phrase_col, abbr_col, False)
    if table is None:
        return

    report = state.table_report
    if report is not None:
        for message in report.messages:
            note(message, "warning")
    st.caption(f"{len(table):,} abbreviations ready.")
    st.dataframe(display_frame(frame.head(15)), **full_width(st.dataframe), hide_index=True)
    _next_fill(state, "Next: map columns")


# ===========================================================================
# step 3 - map source columns to existing target columns
# ===========================================================================
def _set_fill_targets(targets: List[str]) -> None:
    """Callback for the *Select all* / *Clear* buttons."""
    st.session_state["fill_targets"] = list(targets)


def _step_fill_columns(state) -> None:
    st.subheader("3. Map columns (source -> target)")
    st.caption(
        "Target = the existing column in your file where the abbreviation "
        "will be put. Source = the column with the full text. "
        "No new column is created. No match = empty cell."
    )

    frame = _require_fill_data(state)
    if frame is None:
        return
    table = _require_fill_table(state)
    if table is None:
        return

    config = FillConfig()  # fixed defaults - no settings to pick
    state.fill_config = config

    columns = [str(column) for column in frame.columns]
    detected = guess_fill_pairs(columns)
    detected_targets = [target for _source, target in detected]
    detected_source = {target: source for source, target in detected}
    previous = {
        mapping.target: mapping.source
        for mapping in (state.fill_mappings or [])
        if mapping.target in columns and mapping.source in columns
    }

    # Seed / clean the multiselect value before the widget is created.
    if "fill_targets" not in st.session_state:
        st.session_state["fill_targets"] = list(previous) or list(detected_targets)
    else:
        valid = [name for name in st.session_state["fill_targets"] if name in columns]
        if valid != list(st.session_state["fill_targets"]):
            st.session_state["fill_targets"] = valid

    left, right = st.columns(2)
    with left:
        st.button(
            "Select all abbreviation columns",
            key="fill_select_all",
            disabled=not detected_targets,
            on_click=_set_fill_targets,
            args=(detected_targets,),
            **full_width(st.button),
        )
    with right:
        st.button(
            "Clear",
            key="fill_clear",
            on_click=_set_fill_targets,
            args=([],),
            **full_width(st.button),
        )
    if detected:
        st.caption(
            "Detected: "
            + ", ".join(f"{source} -> {target}" for source, target in detected)
        )

    selected = st.multiselect(
        "Target columns to fill (already in your file)",
        options=columns,
        key="fill_targets",
    )

    mappings: List[FillMapping] = []
    missing: List[str] = []
    for target in selected:
        key = f"fill_src_for::{target}"
        options = [""] + [name for name in columns if name != target]
        guess = previous.get(target) or detected_source.get(target) or ""
        if key not in st.session_state:
            st.session_state[key] = guess if guess in options else ""
        elif st.session_state[key] not in options:
            st.session_state[key] = ""
        source = st.selectbox(
            f"Fill '{target}' from",
            options=options,
            key=key,
            format_func=lambda value: "-- select source column --" if value == "" else value,
        )
        if source:
            mappings.append(FillMapping(source=source, target=target))
        else:
            missing.append(target)

    state.fill_mappings = mappings

    if not selected:
        st.info("Select at least one target column above.")
        return
    if missing:
        st.warning("Select a source column for: " + ", ".join(missing))
        return

    preview = run_column_fill(frame.head(10), table, mappings, config)
    shown: List[str] = []
    for mapping in mappings:
        for name in (mapping.source, mapping.target):
            if name not in shown:
                shown.append(name)
    st.markdown("**Preview (first 10 rows)**")
    st.dataframe(
        display_frame(preview.output_frame[shown]),
        **full_width(st.dataframe),
        hide_index=True,
    )
    st.caption(
        f"{preview.filled_cells:,} filled · {preview.not_found_cells:,} empty "
        f"(no abbreviation) in the preview. Target columns are overwritten "
        f"in the downloaded file; your uploaded file is never changed."
    )
    _next_fill(state, "Next: preview and download", enabled=bool(mappings))


# ===========================================================================
# step 4 - preview and download
# ===========================================================================
def _fill_fingerprint(state, mappings: List[FillMapping], config: FillConfig) -> str:
    payload = [
        str(state.data_file_id),
        str(state.data_sheet),
        str(state.data_header_row),
        str(getattr(state.table, "version", "0")),
        json.dumps([asdict(mapping) for mapping in mappings], sort_keys=True),
        config.fingerprint(),
    ]
    return "||".join(payload)


def _ensure_fill_result(state) -> Optional[FillResult]:
    frame = state.data_frame
    table = state.table
    mappings = list(state.fill_mappings or [])
    config = state.fill_config or FillConfig()
    if frame is None or table is None or not mappings:
        return None

    fingerprint = _fill_fingerprint(state, mappings, config)
    if state.fill_result is not None and state.fill_result_fp == fingerprint:
        return state.fill_result

    progress = st.progress(0.0, text="Filling abbreviations…")

    def _tick(done: int, total: int) -> None:
        progress.progress(
            min(done / max(total, 1), 1.0),
            text=f"Filling abbreviations… {done:,}/{total:,}",
        )

    try:
        result = run_column_fill(frame, table, mappings, config, progress_callback=_tick)
    except (KeyError, ValueError) as exc:
        progress.empty()
        note(str(exc), "error")
        return None
    progress.empty()
    state.fill_result = result
    state.fill_result_fp = fingerprint
    state.clear("fill_export", "fill_export_fp")
    return result


def _step_fill_download(state) -> None:
    st.subheader("4. Preview and download")

    if not state.fill_mappings:
        note("Map the columns first (step 3).", "warning")
        _go_fill(state, 3)
        return

    result = _ensure_fill_result(state)
    if result is None:
        note("Complete steps 1-3 first.", "warning")
        _go_fill(state, 1)
        return

    st.caption(
        f"{result.rows:,} rows · {result.filled_cells:,} cells filled · "
        f"{result.not_found_cells:,} cells empty (no abbreviation)"
    )
    st.dataframe(
        build_fill_summary_frame(result), **full_width(st.dataframe), hide_index=True
    )
    st.dataframe(
        display_frame(result.output_frame.head(25)),
        **full_width(st.dataframe),
        hide_index=True,
    )

    not_found = build_fill_not_found_frame(result)
    if not not_found.empty:
        st.markdown("**Values with no abbreviation (left empty)**")
        st.dataframe(not_found, **full_width(st.dataframe), hide_index=True)

    # One simple download: same file, same sheet name, target columns
    # filled. No extra sheets, no new columns.
    sheet_name = str(state.get("data_sheet") or "Filled Data")
    fingerprint = (
        _fill_fingerprint(state, list(state.fill_mappings), state.fill_config or FillConfig())
        + f"||{sheet_name}"
    )
    if state.fill_export is None or state.fill_export_fp != fingerprint:
        with st.spinner("Building the Excel file…"):
            state.fill_export = build_fill_workbook(
                result, data_sheet_name=sheet_name, include_report=False
            )
            state.fill_export_fp = fingerprint

    base = safe_filename(Path(getattr(state, "data_file_name", "data") or "data").stem) or "data"
    download_button(
        "⬇ Download filled Excel file",
        state.fill_export,
        file_name=f"{base}_filled.xlsx",
        key="fill_dl_main",
    )
    st.success(
        f"Done. {result.filled_cells:,} cell(s) filled, "
        f"{result.not_found_cells:,} left empty."
    )
