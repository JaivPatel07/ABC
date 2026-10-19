"""The four steps of the "fill abbreviations into columns" mode.

This mode is deliberately shorter than the tag wizard:

1. upload the main file,
2. upload the one shared abbreviation list,
3. tick the columns that should get an abbreviation column and choose how a
   cell is matched,
4. preview and download.

Everything reuses the readers and the abbreviation table of the tag wizard, so
a file uploaded in one mode is immediately available in the other.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import List, Optional

import pandas as pd
import streamlit as st

from ..column_fill import (
    CASE_OPTIONS,
    MATCH_ALL_WORDS,
    MATCH_MODES,
    MATCH_WORDWISE,
    NOT_FOUND_OPTIONS,
    WORDWISE_UNKNOWN_OPTIONS,
    FillConfig,
    FillMapping,
    FillResult,
    build_fill_not_found_frame,
    build_fill_summary_frame,
    run_column_fill,
    unique_column_name,
)
from ..detect import guess_pair, guess_source_columns
from ..exporters import build_fill_report_workbook, build_fill_workbook
from ..io_utils import dataframe_to_csv_bytes, safe_filename
from ..text_utils import to_text
from .pages import _load_frame, _load_table, _reset_all, _store_upload
from .widgets import (
    chips,
    column_picker,
    display_frame,
    download_button,
    full_width,
    metric_row,
    note,
    section,
)

__all__ = [
    "FILL_STEP_TITLES",
    "FILL_STEPS",
    "render_fill_sidebar",
    "render_fill_step",
]

FILL_STEP_TITLES = [
    "Upload the main Excel file",
    "Upload the abbreviation list",
    "Choose columns to fill",
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
        # ``index``.  Callbacks may update ``fill_step_nav`` before the rerun,
        # and Streamlit warns when a widget has both a default and a value set
        # through the Session State API.
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

        st.divider()
        st.caption("Loaded")
        checks = [
            ("Main Excel file", bool(state.data_frame is not None)),
            ("Abbreviation list", bool(state.table is not None)),
            ("Columns chosen", bool(state.fill_mappings)),
            ("Abbreviations filled", bool(state.fill_result is not None)),
        ]
        for label, done in checks:
            st.markdown(f"{'✅' if done else '⬜'} {label}")

        st.divider()
        if st.button(
            "Start over",
            **full_width(st.button),
            key="start_over",
            help="Clear every uploaded file and setting",
        ):
            _reset_all(state)
            st.rerun()

        with st.expander("Good to know"):
            st.markdown(
                "- One abbreviation list is used for **all** columns.\n"
                "- A new column is added next to each column you choose - the "
                "original columns are never changed.\n"
                "- If a value is **not** in the abbreviation list the new cell is "
                "left **empty** (the original text is never copied there).\n"
                "- Your uploaded files are never modified."
            )


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
    col, _ = st.columns([1.4, 4.6])
    with col:
        st.button(
            f"{label} →",
            disabled=not enabled,
            on_click=_set_fill_step,
            args=(state, int(state.get("fill_step", 1)) + 1),
            **full_width(st.button),
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
        note("Upload the main Excel file first (step 1).", "warning")
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
    section(
        "1 · Upload the main Excel file",
        "This is the sheet where every column of your data lives. Nothing in it is "
        "ever changed - the abbreviations are written into new columns.",
    )

    uploaded = st.file_uploader(
        "Main data file (.xlsx, .xlsm or .csv)",
        type=["xlsx", "xlsm", "csv"],
        key="upl_data",
        help="The file is only read. A new file is created for the download.",
    )
    if uploaded is not None:
        _store_upload(state, "data", uploaded)
    elif state.data_bytes:
        st.caption(
            f"Loaded: **{getattr(state, 'data_file_name', '')}** - upload a different "
            f"file above to replace it."
        )

    if not state.data_bytes:
        note(
            "No file loaded yet. Upload an .xlsx or .csv file, or try the sample files "
            "in the *samples* folder of the project.",
            "info",
        )
        with st.expander("What files are supported?"):
            st.markdown(
                "- `.xlsx` / `.xlsm` - Excel workbooks (all worksheets are listed)\n"
                "- `.csv` - comma, semicolon, tab or pipe separated text files\n"
                "- Legacy `.xls` is not supported: open it in Excel and use *Save As* "
                "→ *Excel Workbook (.xlsx)*."
            )
        return

    frame = _load_frame(state, "data")
    if frame is None:
        return

    metric_row(
        [
            ("Rows", f"{len(frame):,}"),
            ("Columns", f"{len(frame.columns):,}"),
            ("File", getattr(state, "data_file_name", "")),
        ],
        columns=3,
    )

    st.markdown("**Columns found in this file**")
    chips(list(frame.columns))
    st.caption(
        "You will choose which of these columns get an abbreviation column in step 3. "
        "The names come from your file - nothing is hardcoded."
    )
    st.dataframe(display_frame(frame.head(25)), **full_width(st.dataframe), hide_index=True)
    _next_fill(state, "Next: abbreviation list", enabled=True)


# ===========================================================================
# step 2 - the one shared abbreviation list
# ===========================================================================
def _step_fill_abbreviations(state) -> None:
    section(
        "2 · Upload the abbreviation list",
        "One list (word / phrase and approved abbreviation) is used for every column "
        "you choose. You pick which columns of this file hold the phrase and the "
        "abbreviation.",
    )

    uploaded = st.file_uploader(
        "Abbreviation file (.xlsx, .xlsm or .csv)",
        type=["xlsx", "xlsm", "csv"],
        key="upl_abbr",
        help="Usually a two or three column sheet, e.g. 'Full Form' / 'Approved Abbreviation'.",
    )
    if uploaded is not None:
        _store_upload(state, "abbr", uploaded)
    elif state.abbr_bytes:
        st.caption(
            f"Loaded: **{getattr(state, 'abbr_file_name', '')}** - upload a different "
            f"file above to replace it."
        )

    if not state.abbr_bytes:
        note(
            "Upload the abbreviation list to continue. Only abbreviations from this "
            "file are used - the app never invents one.",
            "info",
        )
        return

    frame = _load_frame(state, "abbr")
    if frame is None:
        return

    columns = list(frame.columns)
    guess_phrase, guess_abbr = guess_pair(columns)
    left, right = st.columns(2)
    with left:
        phrase_col = column_picker(
            columns,
            "abbr_phrase_col",
            "Column with the word or phrase",
            guess=state.abbr_phrase_col or guess_phrase,
            help_text="The full form, e.g. 'Cooling Tower'.",
        )
    with right:
        abbr_col = column_picker(
            columns,
            "abbr_abbr_col",
            "Column with the abbreviation",
            guess=state.abbr_abbr_col or guess_abbr,
            help_text="The approved short form, e.g. 'CT'.",
        )
    state.abbr_phrase_col = phrase_col
    state.abbr_abbr_col = abbr_col

    expand_slashes = st.checkbox(
        "Split entries written as 'A / B' into separate mappings",
        value=bool(state.get("abbr_expand_slashes", False)),
        key="abbr_expand_slashes_box",
        help="Off by default: the app will not guess that 'Valve / Valves' means two words "
        "unless you ask for it.",
    )
    state.abbr_expand_slashes = expand_slashes

    if not phrase_col or not abbr_col:
        note("Select both columns so the abbreviations can be loaded.", "warning")
        st.dataframe(display_frame(frame.head(15)), **full_width(st.dataframe), hide_index=True)
        return
    if phrase_col == abbr_col:
        note("The same column is selected twice - please choose two different columns.", "error")
        return

    table = _load_table(state, frame, phrase_col, abbr_col, expand_slashes)
    if table is None:
        return

    metric_row(
        [
            ("Abbreviations ready", f"{len(table):,}"),
            ("Longest phrase", f"{table.max_phrase_len} word(s)"),
            ("Rows in file", f"{len(frame):,}"),
        ],
        columns=3,
    )
    report = state.table_report
    if report is not None:
        for message in report.messages:
            note(message, "warning")
        if report.added:
            note(f"{report.added:,} abbreviations are ready to use.", "success")

    with st.expander("Preview of the abbreviation file"):
        st.dataframe(display_frame(frame.head(30)), **full_width(st.dataframe), hide_index=True)

    _next_fill(state, "Next: choose columns", enabled=True)


# ===========================================================================
# step 3 - choose columns and matching rule
# ===========================================================================
def _step_fill_columns(state) -> None:
    section(
        "3 · Choose which columns get abbreviations",
        "Tick every column that needs an abbreviation. A new column is inserted right "
        "after each one; all other columns and rows are kept exactly as they are.",
    )
    frame = _require_fill_data(state)
    if frame is None:
        return
    table = _require_fill_table(state)
    if table is None:
        return

    config = state.fill_config or FillConfig()
    config = _render_fill_settings(config)
    state.fill_config = config

    columns = [str(column) for column in frame.columns]
    stored_defaults = state.get("fill_sources_default")
    if stored_defaults is None:
        stored_defaults = guess_source_columns(columns)
    default_sources = [column for column in stored_defaults if column in columns]

    # A new data file may not contain the columns selected for the old file.
    # Drop those values before the widget is created, otherwise Streamlit
    # refuses a selection that is not in the options.
    stored_selection = st.session_state.get("fill_sources")
    if stored_selection is not None:
        valid_selection = [column for column in stored_selection if column in columns]
        if valid_selection != list(stored_selection):
            st.session_state["fill_sources"] = valid_selection

    selected = st.multiselect(
        "Columns to fill with abbreviations",
        options=columns,
        default=default_sources,
        key="fill_sources",
        help="Each ticked column gets its own new column with the abbreviation.",
    )

    mappings: List[FillMapping] = []
    if selected:
        st.markdown("**New column names and per-column matching rule**")
        st.caption(
            "Each ticked column gets its own abbreviation column right next to it. "
            "A name that already exists gets ` (2)` appended - an existing column is never overwritten. "
            "You can give each column its own matching rule - by default they use the rule chosen above. "
            "Changing the suffix rebuilds the suggested names."
        )
        # Allow per-column matching rule override
        per_column_mode: dict = {}
        # Load previous per-column choices if any
        prev_mappings = {m.source: m for m in (state.fill_mappings or [])}
        st.info(
            "💡 **Tip:** Use *Abbreviate each word/phrase (rebuild sentence)* to turn every word in a cell "
            "into its abbreviation and rebuild the sentence, e.g. `Cooling Tower No 2` → `CT NO 2`. "
            "The old *Any match* only keeps the longest phrase (`CT`).",
            icon="ℹ️",
        )
        taken: List[str] = list(columns)
        for source in selected:
            default_name = unique_column_name(taken, f"{source}{config.output_suffix}")
            taken.append(default_name)
            col1, col2 = st.columns([1.2, 1])
            with col1:
                output = st.text_input(
                    f"New column for '{source}'",
                    value=prev_mappings.get(source, FillMapping(source, output=default_name)).output or default_name,
                    # the suffix is part of the key, so changing the suffix rebuilds
                    # the suggested names instead of keeping old widget values
                    key=f"fill_out::{source}::{config.output_suffix}",
                    help="Leave the name empty to use the automatic name.",
                )
            with col2:
                # per-column matching rule - defaults to global config
                prev_mode = prev_mappings.get(source, FillMapping(source)).match_mode or config.match_mode
                if prev_mode not in MATCH_MODES:
                    prev_mode = config.match_mode
                mode = st.selectbox(
                    f"Rule for '{source}'",
                    options=list(MATCH_MODES),
                    index=list(MATCH_MODES).index(prev_mode),
                    key=f"fill_mode::{source}",
                    help="Override the global rule for this column only.",
                )
                per_column_mode[source] = mode
            mappings.append(FillMapping(source=source, output=to_text(output), match_mode=per_column_mode[source]))

    state.fill_mappings = mappings

    if not mappings:
        note(
            "Tick at least one column above. For example the equipment description and "
            "the parameter columns.",
            "info",
        )
        return

    _render_fill_preview(frame, table, mappings, config)

    problems = config.issues()
    for problem in problems:
        note(problem, "warning")

    _next_fill(state, "Next: preview and download", enabled=not problems)


def _render_fill_settings(config: FillConfig) -> FillConfig:
    """Render the settings shared by every selected column."""
    left, right = st.columns(2)
    with left:
        match_mode = st.selectbox(
            "Default matching rule",
            options=list(MATCH_MODES),
            index=list(MATCH_MODES).index(config.effective_mode()),
            key="fill_cfg_mode",
            help=(
                "Abbreviate each word/phrase (recommended): every word/phrase in the cell "
                "is turned into its abbreviation and the sentence is rebuilt, e.g. "
                "'Cooling Tower No 2' → 'CT NO 2' and 'Boiler Feed Water Pump B' → 'BFW PMP B'.\n\n"
                "Any match: the longest phrase found anywhere in the cell wins, e.g. "
                "'Cooling Tower No 2' → CT (rest ignored).\n\n"
                "Whole cell: only an exact phrase, e.g. 'Cooling Tower' → CT but "
                "'Cooling Tower No 2' stays empty.\n\n"
                "Every word: every word must be in the list, e.g. "
                "'Boiler Feed Water Pump' → BFW_PMP."
            ),
        )
        suffix = st.text_input(
            "Suffix for the new column names",
            value=config.output_suffix,
            key="fill_cfg_suffix",
            help="Default name = the source column + this suffix. You can rename each "
            "column below.",
        )
        case = st.selectbox(
            "Letter case of the abbreviation",
            options=list(CASE_OPTIONS),
            index=list(CASE_OPTIONS).index(config.case) if config.case in CASE_OPTIONS else 0,
            key="fill_cfg_case",
            help="'Keep original' writes exactly what is in the abbreviation list.",
        )
    with right:
        when_not_found = st.radio(
            "When no abbreviation is found",
            options=list(NOT_FOUND_OPTIONS),
            index=list(NOT_FOUND_OPTIONS).index(config.when_not_found)
            if config.when_not_found in NOT_FOUND_OPTIONS else 0,
            key="fill_cfg_notfound",
            help="'Leave the cell empty' never copies the original text into the new column.",
        )
        plural = st.checkbox(
            "Match simple plurals ('Pumps' → 'Pump')",
            value=bool(config.allow_plural_matching),
            key="fill_cfg_plural",
            help="Only matches an abbreviation that already exists in the list.",
        )
        separator = config.separator
        keep_numbers = config.keep_numbers
        wordwise_unknown = config.wordwise_unknown
        if match_mode in (MATCH_ALL_WORDS, MATCH_WORDWISE):
            separator = st.text_input(
                "Separator between abbreviations",
                value=config.separator,
                key="fill_cfg_sep",
                help="Used to join the abbreviations. Use a single space to rebuild a normal sentence, "
                "or '_' to build a tag-like value.",
            )
            keep_numbers = st.checkbox(
                "Keep numbers (2, 3 …) in the result",
                value=bool(config.keep_numbers),
                key="fill_cfg_keepnumbers",
                help="With this off, a number without an abbreviation makes the cell empty.",
            )
            if match_mode == MATCH_WORDWISE:
                wordwise_unknown = st.selectbox(
                    "If a word has no abbreviation",
                    options=list(WORDWISE_UNKNOWN_OPTIONS),
                    index=list(WORDWISE_UNKNOWN_OPTIONS).index(config.wordwise_unknown)
                    if config.wordwise_unknown in WORDWISE_UNKNOWN_OPTIONS else 0,
                    key="fill_cfg_wordwise_unknown",
                    help="Keep original word: rebuild the sentence with abbreviations where possible, "
                    "e.g. 'Scrubber Pump' → 'Scrubber PMP'. Drop: remove unknown words. "
                    "Empty: leave the whole cell empty if any word is unknown.",
                )
        elif config.separator != " ":
            separator = config.separator

    return FillConfig(
        match_mode=match_mode,
        case=case,
        separator=separator,
        allow_plural_matching=plural,
        keep_numbers=keep_numbers,
        when_not_found=when_not_found,
        output_suffix=suffix,
        wordwise_unknown=wordwise_unknown,
    )


def _render_fill_preview(frame: pd.DataFrame, table, mappings, config: FillConfig) -> None:
    """Show what the first rows would look like before generating everything."""
    sample = frame.head(12)
    preview = run_column_fill(sample, table, mappings, config)

    st.markdown("**Preview of the new columns**")
    rows = []
    for column in preview.columns:
        for cell in column.cells:
            rows.append(
                {
                    "Column in main file": column.mapping.source,
                    "New column": column.output_name,
                    "Original value": cell.original,
                    "Abbreviation (new)": cell.abbreviation,
                    "Matched phrase": cell.matched_phrase,
                    "Status": cell.status,
                }
            )
    if rows:
        st.dataframe(pd.DataFrame(rows), **full_width(st.dataframe), hide_index=True)
    else:
        note("All selected cells are empty - nothing would be filled.", "warning")

    metric_row(
        [
            ("Columns selected", f"{len(preview.columns)}"),
            ("Cells filled", f"{preview.filled_cells:,}"),
            ("Cells left empty", f"{preview.not_found_cells:,}"),
            ("Rows shown", f"{len(sample):,}"),
        ],
        columns=4,
    )
    st.caption(
        f"Preview of the first {len(sample)} row(s) only - the download contains every row."
    )


# ===========================================================================
# step 4 - generate and download
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
    section(
        "4 · Preview and download",
        "The new workbook contains every original column and row, plus one abbreviation "
        "column next to each column you selected. Cells with no abbreviation stay empty.",
    )

    if not state.fill_mappings:
        note("Choose the columns to fill first (step 3).", "warning")
        _go_fill(state, 3)
        return

    result = _ensure_fill_result(state)
    if result is None:
        note("Complete steps 1-3 to fill the abbreviations.", "warning")
        _go_fill(state, 1)
        return

    metric_row(
        [
            ("Rows", f"{result.rows:,}"),
            ("Columns filled", f"{len(result.columns):,}"),
            ("Cells with abbreviation", f"{result.filled_cells:,}"),
            ("Cells left empty", f"{result.not_found_cells:,}"),
        ],
        columns=4,
    )

    summary = build_fill_summary_frame(result)
    st.markdown("**Summary**")
    st.dataframe(summary, **full_width(st.dataframe), hide_index=True)

    not_found = build_fill_not_found_frame(result)
    if not not_found.empty:
        with st.expander(
            f"Values with no abbreviation ({len(not_found)} different value(s)) - these cells are empty"
        ):
            st.dataframe(not_found, **full_width(st.dataframe), hide_index=True)
            download_button(
                "Download this list (CSV)",
                dataframe_to_csv_bytes(not_found),
                file_name="values_without_abbreviation.csv",
                mime="text/csv",
                key="fill_dl_notfound",
            )

    st.markdown("**Preview of the new file**")
    st.dataframe(display_frame(result.output_frame.head(25)), **full_width(st.dataframe), hide_index=True)
    st.caption(
        "Every original column is kept. The abbreviation columns are inserted directly "
        "after the columns they belong to."
    )

    st.markdown("### Download")
    left, right = st.columns(2)
    with left:
        sheet_name = st.text_input(
            "Worksheet name for the filled data",
            value=state.get("fill_sheet_name", "Filled Data") or "Filled Data",
            key="fill_sheet_name",
        )
        include_report = st.checkbox(
            "Include the summary and 'not found' sheets",
            value=bool(state.get("fill_include_report", True)),
            key="fill_include_report",
        )
    with right:
        st.caption(
            "The workbook is created in memory. Your uploaded file is never changed."
        )

    fingerprint = (
        _fill_fingerprint(state, list(state.fill_mappings), state.fill_config or FillConfig())
        + f"||{sheet_name}||{include_report}"
    )
    if state.fill_export is None or state.fill_export_fp != fingerprint:
        with st.spinner("Building the Excel file…"):
            state.fill_export = build_fill_workbook(
                result,
                data_sheet_name=sheet_name or "Filled Data",
                include_report=include_report,
            )
            state.fill_export_fp = fingerprint

    base = safe_filename(Path(getattr(state, "data_file_name", "data") or "data").stem) or "data"
    download_button(
        "⬇ Download the filled Excel file",
        state.fill_export,
        file_name=f"{base}_with_abbreviations.xlsx",
        key="fill_dl_main",
        help_text=f"{len(state.fill_export) / 1024:,.0f} KB · all original columns preserved",
    )
    download_button(
        "⬇ Download the summary report (Excel)",
        build_fill_report_workbook(result),
        file_name=f"{base}_abbreviation_report.xlsx",
        key="fill_dl_report",
        help_text="How many cells were filled, and which values had no abbreviation",
    )
    download_button(
        "⬇ Download the result as CSV",
        dataframe_to_csv_bytes(result.output_frame),
        file_name=f"{base}_with_abbreviations.csv",
        mime="text/csv",
        key="fill_dl_csv",
    )

    note(
        f"Done. {result.filled_cells:,} cell(s) received an abbreviation and "
        f"{result.not_found_cells:,} stayed empty because the value is not in the list.",
        "success",
    )
