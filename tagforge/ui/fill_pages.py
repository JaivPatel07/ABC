"""The four steps of the "fill abbreviations into columns" mode.

Kept as simple as possible:

1. upload the main file,
2. upload the abbreviation list,
3. map columns **manually** - one row per pair: choose the source column
   with the full text and the target column where the abbreviation goes.
   The target normally already exists in the user's file (usually empty),
   but a row can also ask for a **new column**, which is added at the end
   of the downloaded file.  Any number of pairs can be filled in one run,
4. preview and download.

There are no settings screens: abbreviations are matched word by word
(the :class:`~tagforge.column_fill.FillConfig` defaults).  Words that have no
abbreviation are **kept as typed**, a value where no word matches keeps its
original text, and every such word/value is listed in step 4.

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
    build_fill_unknown_words_frame,
    run_column_fill,
    unique_column_name,
)
from ..detect import guess_fill_pairs, guess_pair
from ..exporters import build_fill_workbook
from ..io_utils import safe_filename
from .pages import _load_frame, _load_table, _reset_all, _store_upload
from .widgets import column_picker, display_frame, download_button, full_width, note

__all__ = [
    "FILL_STEP_TITLES",
    "FILL_STEPS",
    "NEW_TARGET_OPTION",
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
        st.info(
            "Upload your file. You can fill abbreviation columns that already "
            "exist in it - or create a new abbreviation column at the end in "
            "step 3."
        )
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
# step 3 - map columns manually (source -> target)
# ===========================================================================
NEW_TARGET_OPTION = "➕ New column at the end…"

_SRC_KEY = "fill_row_src::{}"
_TGT_KEY = "fill_row_tgt::{}"
_NEW_KEY = "fill_row_new::{}"
_FILL_ROW_WIDTHS = [3.2, 3.2, 2.4, 0.7]


def _fill_row_ids() -> List[int]:
    """The row ids currently shown in the manual mapping table."""
    try:
        return [int(value) for value in (st.session_state.get("fill_row_ids") or [])]
    except (TypeError, ValueError):  # pragma: no cover - defensive
        return []


def _fill_row_key(kind: str, row_id: int) -> str:
    template = {"source": _SRC_KEY, "target": _TGT_KEY, "name": _NEW_KEY}[kind]
    return template.format(row_id)


def _next_fill_row_id() -> int:
    # Never reuse an id, even if the counter and the visible rows got out of
    # sync (for example after a hot reload during development).
    current = max(
        int(st.session_state.get("fill_row_seq", 0) or 0),
        max(_fill_row_ids(), default=0),
    )
    row_id = current + 1
    st.session_state["fill_row_seq"] = row_id
    return row_id


def _add_fill_row(source: str = "", target: str = "", new_name: str = "") -> int:
    """Callback: add one mapping row (empty unless values are given)."""
    ids = _fill_row_ids()
    row_id = _next_fill_row_id()
    ids.append(row_id)
    st.session_state["fill_row_ids"] = ids
    st.session_state[_fill_row_key("source", row_id)] = source or ""
    st.session_state[_fill_row_key("target", row_id)] = target or ""
    st.session_state[_fill_row_key("name", row_id)] = new_name or ""
    return row_id


def _drop_fill_rows() -> None:
    for row_id in _fill_row_ids():
        for kind in ("source", "target", "name"):
            st.session_state.pop(_fill_row_key(kind, row_id), None)
    st.session_state["fill_row_ids"] = []


def _set_fill_rows(rows) -> None:
    """Callback: replace every row with ``(source, target, new_name)`` tuples."""
    _drop_fill_rows()
    for source, target, new_name in rows:
        _add_fill_row(source, target, new_name)


def _remove_fill_row(row_id: int) -> None:
    """Callback: remove one mapping row and forget its widget values."""
    st.session_state["fill_row_ids"] = [
        value for value in _fill_row_ids() if value != row_id
    ]
    for kind in ("source", "target", "name"):
        st.session_state.pop(_fill_row_key(kind, row_id), None)


def _seed_fill_rows(columns: List[str], detected, previous) -> None:
    """Create the rows once.  Detected pairs are only a starting hint."""
    if "fill_row_ids" in st.session_state:
        return
    rows = []
    for mapping in previous:
        source = mapping.source
        if source not in columns:
            continue
        target = mapping.resolved_target(FillConfig())
        if getattr(mapping, "new_column", False) or target not in columns:
            rows.append((source, NEW_TARGET_OPTION, target))
        else:
            rows.append((source, target, ""))
    if not rows:
        rows = [(source, target, "") for source, target in detected]
    if not rows:
        rows = [("", "", "")]
    _set_fill_rows(rows)


def _init_widget_value(key: str, value: str, options: List[str]) -> None:
    if key not in st.session_state or st.session_state[key] not in options:
        st.session_state[key] = value if value in options else options[0]


def _target_option_label(value: str) -> str:
    if value == "":
        return "-- select target column --"
    return value


def _build_fill_mappings(row_ids: List[int], columns: List[str]):
    """Turn the visible rows into mappings plus friendly validation notes."""
    mappings: List[FillMapping] = []
    problems: List[str] = []
    created: List[str] = []
    renamed: List[tuple] = []
    used_names = list(columns)
    used_targets: dict = {}

    for position, row_id in enumerate(row_ids, start=1):
        source = str(st.session_state.get(_fill_row_key("source", row_id)) or "")
        choice = str(st.session_state.get(_fill_row_key("target", row_id)) or "")
        if not source and not choice:
            continue  # an untouched row is ignored
        if not source:
            problems.append(f"Row {position}: choose the column with the full text.")
            continue
        if not choice:
            problems.append(f"Row {position}: choose where to put the abbreviation.")
            continue

        if choice == NEW_TARGET_OPTION:
            typed = str(
                st.session_state.get(_fill_row_key("name", row_id)) or ""
            ).strip()
            wanted = typed or f"{source} Abbr"
            final = unique_column_name(used_names, wanted)
            if final != wanted:
                renamed.append((wanted, final))
            used_names.append(final)
            mapping = FillMapping(source=source, target=final, new_column=True)
            created.append(final)
        else:
            mapping = FillMapping(source=source, target=choice)

        key = mapping.target.strip().lower()
        if key in used_targets:
            problems.append(
                f"'{mapping.target}' is selected as the target of more than one row."
            )
            continue
        if not mapping.new_column and mapping.target == mapping.source:
            problems.append(
                f"Row {position}: the source and the target are both "
                f"'{mapping.source}' - choose a different target column."
            )
            continue
        used_targets[key] = mapping.target
        mappings.append(mapping)

    return mappings, problems, created, renamed


def _step_fill_columns(state) -> None:
    st.subheader("3. Map columns manually (source -> target)")
    st.caption(
        "Choose the column with the full text (source) and the column where "
        "the abbreviation must be written (target). Add one row per column. "
        "You can also create a new column - it is added at the end of the "
        "file. Words without an abbreviation are kept as typed; a value "
        "with no abbreviation at all keeps its original text."
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
    previous = list(state.fill_mappings or [])
    _seed_fill_rows(columns, detected, previous)

    if detected:
        st.caption(
            "Suggested pairs (only a hint - change any dropdown): "
            + ", ".join(f"{source} -> {target}" for source, target in detected)
        )

    toolbar = st.columns([1.1, 1.4, 1.0, 0.9])
    with toolbar[0]:
        st.button(
            "＋ Add column",
            key="fill_add_row",
            on_click=_add_fill_row,
            help="Add another source -> target mapping row.",
            **full_width(st.button),
        )
    with toolbar[1]:
        st.button(
            "Add suggested pairs",
            key="fill_add_detected",
            on_click=_set_fill_rows,
            args=([(source, target, "") for source, target in detected],),
            disabled=not detected,
            help="Fill the rows with the pairs detected from the column names.",
            **full_width(st.button),
        )
    with toolbar[2]:
        st.button(
            "Remove all",
            key="fill_clear_rows",
            on_click=_set_fill_rows,
            args=([],),
            **full_width(st.button),
        )
    with toolbar[3]:
        st.caption(f"{len(_fill_row_ids()):,} mapping row(s)")

    st.caption(
        "To create a column that is not in the file yet, choose "
        f"**{NEW_TARGET_OPTION}** as the target."
    )
    head = st.columns(_FILL_ROW_WIDTHS)
    head[0].markdown("**Column with the full text (source)**")
    head[1].markdown("**Where to put the abbreviation (target)**")
    head[2].markdown("**Name of the new column**")
    head[3].markdown("")

    row_ids = _fill_row_ids()
    source_options = [""] + columns
    target_options = [""] + columns + [NEW_TARGET_OPTION]

    for row_id in row_ids:
        source_key = _fill_row_key("source", row_id)
        target_key = _fill_row_key("target", row_id)
        name_key = _fill_row_key("name", row_id)
        _init_widget_value(source_key, "", source_options)
        _init_widget_value(target_key, "", target_options)

        left, middle, right, remove = st.columns(_FILL_ROW_WIDTHS)
        with left:
            st.selectbox(
                "Column with the full text (source)",
                options=source_options,
                key=source_key,
                format_func=lambda value: "-- select source column --"
                if value == ""
                else value,
                label_visibility="collapsed",
            )
        with middle:
            st.selectbox(
                "Where to put the abbreviation (target)",
                options=target_options,
                key=target_key,
                format_func=_target_option_label,
                label_visibility="collapsed",
            )
        with right:
            if st.session_state.get(target_key) == NEW_TARGET_OPTION:
                source = str(st.session_state.get(source_key) or "")
                st.text_input(
                    "Name of the new column",
                    key=name_key,
                    placeholder=f"{source} Abbr" if source else "e.g. Equipment Abbr",
                    label_visibility="collapsed",
                    help="Leave empty to use '<source> Abbr'. "
                    "The column is added at the end of the file.",
                )
        with remove:
            st.button(
                "✕",
                key=f"fill_remove::{row_id}",
                on_click=_remove_fill_row,
                args=(row_id,),
                help="Remove this mapping row.",
                **full_width(st.button),
            )

    mappings, problems, created, renamed = _build_fill_mappings(row_ids, columns)
    # A half-finished row must not be used by step 4 behind the user's back.
    state.fill_mappings = [] if problems else mappings

    for problem in problems:
        note(problem, "error")
    if problems:
        return
    if not mappings:
        st.info(
            "No mapping yet. Pick a source and a target above, or click "
            "**＋ Add column** to add a row."
        )
        return

    for old, new in renamed:
        note(
            f"'{old}' is already used - the new column will be named '{new}'.",
            "info",
        )
    if created:
        st.caption("New column(s) at the end of the file: " + ", ".join(created))

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
        f"{preview.filled_cells:,} filled · {preview.cells_with_unknown_words:,} with "
        f"words that have no abbreviation (kept as typed) in the preview. "
        f"Target columns are overwritten in the downloaded file; your uploaded "
        f"file is never changed."
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
        f"{result.cells_with_unknown_words:,} cells contain words with no "
        f"abbreviation (kept as typed)"
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
        st.markdown("**Values with words that have no abbreviation**")
        st.caption(
            "Includes values that were filled and kept the unknown words as "
            "typed, values that had no abbreviation at all (original kept) and "
            "values that were left empty."
        )
        st.dataframe(not_found, **full_width(st.dataframe), hide_index=True)

        unknown_words = build_fill_unknown_words_frame(result)
        if not unknown_words.empty:
            st.markdown("**Words with no abbreviation (add these to your list)**")
            st.dataframe(unknown_words, **full_width(st.dataframe), hide_index=True)

    # One simple download: same file, same sheet name, mapped target columns
    # filled. New columns, when requested, are already at the end of the
    # output frame. No extra sheets.
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
        f"{result.cells_with_unknown_words:,} kept words that have no "
        f"abbreviation, {result.not_found_cells:,} left empty."
    )
