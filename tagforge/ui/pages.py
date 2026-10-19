"""The eight steps of the Streamlit wizard.

Each ``_step_*`` function is independent: it reads what it needs from
:class:`~tagforge.ui.state.AppState`, shows a friendly message when a
prerequisite is missing, and writes its own choices back to the state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import streamlit as st

from ..abbreviations import DROP_MARKER, SOURCE_USER, AbbreviationTable, load_table_from_frame
from ..config import (
    CASE_OPTIONS,
    PLACEHOLDER_HELP,
    TEMPLATE_PRESETS,
    TRUNCATE_OPTIONS,
    NamingConfig,
    validate_template,
)
from ..detect import guess_column, guess_pair
from ..exporters import (
    build_abbreviations_csv,
    build_processed_workbook,
    build_report_workbook,
    default_meta,
)
from ..io_utils import (
    FileReadError,
    dataframe_to_csv_bytes,
    list_sheets,
    read_table,
    safe_filename,
)
from ..pipeline import ROW_ID_COLUMN, PipelineResult, build_output_frame, run_pipeline
from ..taggen import TagGenerator
from ..text_utils import phrase_key, to_text
from .widgets import (
    chips,
    display_frame,
    full_width,
    column_picker,
    download_button,
    header_row_picker,
    metric_row,
    note,
    placeholder_help_table,
    section,
    sheet_picker,
    styled_status_frame,
)

__all__ = ["STEP_TITLES", "STEPS", "render_sidebar", "render_current_step"]

STEP_TITLES = [
    "Upload equipment data",
    "Upload abbreviation list",
    "Choose column to convert",
    "Set naming convention",
    "Preview and edit",
    "Fix unmatched words",
    "Check validation",
    "Download results",
]
STEPS = [f"{index}. {title}" for index, title in enumerate(STEP_TITLES, start=1)]
CUSTOM_PRESET = "Custom (type your own)"


# ===========================================================================
# navigation
# ===========================================================================
def render_sidebar(state) -> None:
    with st.sidebar:
        st.divider()
        current = int(state.get("step", 1) or 1)
        # Initialise the widget's session-state value once instead of passing
        # ``index``.  Callbacks may update ``step_nav`` before the rerun, and
        # Streamlit warns when a widget has both a default and a value set
        # through the Session State API.
        if "step_nav" not in st.session_state:
            st.session_state["step_nav"] = STEPS[
                min(max(current - 1, 0), len(STEPS) - 1)
            ]
        choice = st.radio(
            "Steps",
            options=STEPS,
            key="step_nav",
            label_visibility="collapsed",
        )
        if choice in STEPS:
            state.step = STEPS.index(choice) + 1

        st.divider()
        st.caption("Loaded")
        checks = [
            ("Equipment data", bool(state.data_frame is not None)),
            ("Abbreviation list", bool(state.table is not None)),
            ("Column selected", bool(state.target_col)),
            ("Tags generated", bool(state.result is not None)),
        ]
        for label, done in checks:
            st.markdown(f"{'✅' if done else '⬜'} {label}")

        st.divider()
        if st.button("Start over", **full_width(st.button), key="start_over",
                 help="Clear every uploaded file and setting"):
            _reset_all(state)
            st.rerun()

        with st.expander("Good to know"):
            st.markdown(
                "- Your uploaded files are **never modified** - results are only "
                "offered as a download.\n"
                "- Words that are not in the abbreviation list are **kept as typed** "
                "and reported, never guessed.\n"
                "- Column names are read from your file; nothing is hardcoded."
            )


def _reset_all(state) -> None:
    state.clear_prefixed(extra=(
        "upl_data", "upl_abbr", "data_sheet", "data_header", "abbr_sheet", "abbr_header",
        "abbr_phrase_col", "abbr_abbr_col", "target_col", "step_nav", "cfg_preset",
        "cfg_template", "cfg_prefix", "cfg_suffix", "cfg_sep", "cfg_inner", "cfg_case",
        "cfg_uniquify", "cfg_maxlen", "cfg_stop", "cfg_dropstop", "cfg_keepnumbers",
        "cfg_plural", "cfg_dedupe", "cfg_collapse", "cfg_trim", "cfg_allowed",
        "cfg_pattern", "cfg_replace", "cfg_indexstart", "cfg_trunc", "editor_preview",
        "mode_radio",
    ))
    # The filler mode uses dynamic widget keys (one per selected column), so
    # remove them by prefix instead of listing every possible name.
    for key in list(st.session_state.keys()):
        if key.startswith("fill_"):
            del st.session_state[key]


def render_current_step(state) -> None:
    step = int(state.get("step", 1) or 1)
    handlers = {
        1: _step_upload_data,
        2: _step_abbreviations,
        3: _step_choose_column,
        4: _step_naming,
        5: _step_preview,
        6: _step_unmatched,
        7: _step_validation,
        8: _step_export,
    }
    handlers.get(step, _step_upload_data)(state)


def _set_step(state, step: int) -> None:
    """Jump to ``step`` and keep the sidebar radio in sync.

    This runs as a Streamlit *callback*: callbacks execute before the script is
    re-run, which is the only safe moment to change the value of a widget that
    was already created (the sidebar radio).  Without it the radio's old value
    would immediately overwrite ``state.step`` on the next run.
    """
    step = max(1, min(int(step), len(STEPS)))
    state.step = step
    st.session_state["step_nav"] = STEPS[step - 1]


def _next_button(state, label: str = "Next step", enabled: bool = True) -> None:
    col, _ = st.columns([1, 5])
    with col:
        st.button(
            f"{label} →",
            disabled=not enabled,
            on_click=_set_step,
            args=(state, int(state.get("step", 1)) + 1),
            **full_width(st.button),
        )


def _go_to(state, step: int) -> None:
    st.button(
        f"Go to step {step}",
        type="primary",
        on_click=_set_step,
        args=(state, step),
    )


# ===========================================================================
# file helpers (cached so big files are only parsed once)
# ===========================================================================
@st.cache_data(show_spinner="Reading file…")
def _read_cached(data: bytes, file_name: str, sheet: Optional[str], header_row: int) -> pd.DataFrame:
    return read_table(data, file_name, sheet, header_row)


@st.cache_data(show_spinner=False)
def _sheets_cached(data: bytes, file_name: str) -> Tuple[str, ...]:
    return tuple(list_sheets(data, file_name))


def _store_upload(state, kind: str, uploaded) -> None:
    """Remember an uploaded file and forget everything derived from the old one."""
    file_id = (uploaded.name, uploaded.size, hash(uploaded.getvalue()) & 0xFFFFFFFF)
    if getattr(state, f"{kind}_file_id", None) == file_id and getattr(state, f"{kind}_bytes", None):
        return
    setattr(state, f"{kind}_file_id", file_id)
    setattr(state, f"{kind}_bytes", uploaded.getvalue())
    setattr(state, f"{kind}_file_name", uploaded.name)
    state.clear(
        f"{kind}_sheet",
        f"{kind}_header_row",
        f"{kind}_frame",
        f"{kind}_columns",
        f"{kind}_sheets",
    )
    if kind == "data":
        state.clear("target_col", "result", "result_fp", "overrides", "export_bytes", "export_fp",
                    "fill_mappings", "fill_result", "fill_result_fp",
                    "fill_export", "fill_export_fp")
        for widget_key in list(st.session_state.keys()):
            if widget_key in ("fill_sources",) or widget_key.startswith(("fill_out::", "fill_rule::")):
                del st.session_state[widget_key]
    if kind == "abbr":
        state.clear("abbr_phrase_col", "abbr_abbr_col", "abbr_signature", "table", "table_report",
                    "result", "result_fp", "export_bytes", "export_fp",
                    "fill_result", "fill_result_fp", "fill_export", "fill_export_fp")


def _load_frame(state, kind: str) -> Optional[pd.DataFrame]:
    """Read (and cache) the uploaded file for ``kind`` (``data`` or ``abbr``)."""
    data = getattr(state, f"{kind}_bytes", None)
    file_name = getattr(state, f"{kind}_file_name", "") or "file"
    if not data:
        return None

    sheets: List[str] = []
    try:
        sheets = list(_sheets_cached(data, file_name))
    except FileReadError as exc:
        st.error(str(exc))
        return None

    setattr(state, f"{kind}_sheets", sheets)
    sheet = sheet_picker(sheets, key=f"{kind}_sheet", label=f"Worksheet ({file_name})")
    setattr(state, f"{kind}_sheet", sheet)

    header_row = header_row_picker(f"{kind}_header", int(getattr(state, f"{kind}_header_row", 0) or 0))
    if header_row != getattr(state, f"{kind}_header_row", 0):
        setattr(state, f"{kind}_header_row", header_row)
        state.clear("result", "result_fp", "export_bytes", "export_fp",
                    "fill_result", "fill_result_fp", "fill_export", "fill_export_fp")
        if kind == "abbr":
            state.clear("table", "abbr_signature")

    try:
        frame = _read_cached(data, file_name, sheet, int(header_row or 0))
    except FileReadError as exc:
        st.error(str(exc))
        note("Tip: close the file in Excel if it is open, or pick a different header row.", "info")
        return None

    columns = [str(column) for column in frame.columns]
    previous = getattr(state, f"{kind}_columns", None)
    setattr(state, f"{kind}_frame", frame)
    setattr(state, f"{kind}_columns", columns)
    if previous is not None and previous != columns:
        state.clear("result", "result_fp", "export_bytes", "export_fp",
                    "fill_result", "fill_result_fp", "fill_export", "fill_export_fp")
    return frame


def _require_data(state) -> Optional[pd.DataFrame]:
    frame = state.data_frame
    if frame is None:
        note("Upload your equipment data first (step 1).", "warning")
        _go_to(state, 1)
        return None
    return frame


# ===========================================================================
# step 1 - equipment data
# ===========================================================================
def _step_upload_data(state) -> None:
    section(
        "1 · Upload the equipment data",
        "The file can contain equipment names, plant sections, parameters, descriptions or "
        "existing tags - any spreadsheet with the text you want to convert.",
    )

    uploaded = st.file_uploader(
        "Equipment data file (.xlsx, .xlsm or .csv)",
        type=["xlsx", "xlsm", "csv"],
        key="upl_data",
        help="The file is only read. Nothing is ever written back to it.",
    )
    if uploaded is not None:
        _store_upload(state, "data", uploaded)
    elif state.data_bytes:
        st.caption(f"Loaded: **{getattr(state, 'data_file_name', '')}** - upload a different "
                   f"file above to replace it.")

    if not state.data_bytes:
        note("No file loaded yet. Upload an .xlsx or .csv file, or try the sample files in "
             "the *samples* folder of the project.", "info")
        with st.expander("What files are supported?"):
            st.markdown(
                "- `.xlsx` / `.xlsm` - Excel workbooks (all worksheets are listed)\n"
                "- `.csv` - comma, semicolon, tab or pipe separated text files\n"
                "- Legacy `.xls` is not supported: open it in Excel and use *Save As* → *Excel Workbook (.xlsx)*."
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
        "These names come from your file. You choose which one to convert in step 3 - "
        "the app never assumes a column name or position."
    )

    if len(frame) > 50_000:
        note(f"Large file: {len(frame):,} rows. Only the first rows are shown here, but the "
             f"export always contains every row.", "info")

    st.dataframe(display_frame(frame.head(25)), **full_width(st.dataframe), hide_index=True)
    _next_button(state, "Next: abbreviation list", enabled=frame is not None)


# ===========================================================================
# step 2 - abbreviation list
# ===========================================================================
def _step_abbreviations(state) -> None:
    section(
        "2 · Upload the company abbreviation list",
        "The list must contain at least one column with the full word/phrase and one column "
        "with the approved abbreviation. You pick which columns those are below.",
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
        st.caption(f"Loaded: **{getattr(state, 'abbr_file_name', '')}** - upload a different "
                   f"file above to replace it.")

    start_empty = st.checkbox(
        "I do not have a list yet - start empty and add words later (step 6)",
        value=bool(state.get("abbr_start_empty", False)),
        key="abbr_start_empty_box",
    )
    state.abbr_start_empty = start_empty

    if not state.abbr_bytes and not start_empty:
        note("Upload the company abbreviation list to continue. Only abbreviations from this "
             "file are used - the app never invents one.", "info")
        return

    if start_empty and not state.abbr_bytes:
        if state.table is None:
            state.table = AbbreviationTable()
        note("Working with an empty list. Every word will be reported as unmatched so you can "
             "build the list as you go.", "info")
        _render_table_summary(state)
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
            help_text="The full form, e.g. 'Cooling Tower'.",
        )
    with right:
        abbr_col = column_picker(
            columns, "abbr_abbr_col", "Column with the abbreviation",
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

    _render_table_summary(state, frame)


def _load_table(state, frame, phrase_col, abbr_col, expand_slashes) -> Optional[AbbreviationTable]:
    signature = (
        state.abbr_file_id, state.abbr_sheet, state.abbr_header_row,
        phrase_col, abbr_col, expand_slashes,
    )
    if state.abbr_signature == signature and state.table is not None:
        return state.table
    try:
        table, report = load_table_from_frame(frame, phrase_col, abbr_col, expand_slashes=expand_slashes)
    except KeyError as exc:
        note(str(exc), "error")
        return None
    state.table = table
    state.table_report = report
    state.abbr_signature = signature
    state.clear("result", "result_fp", "export_bytes", "export_fp",
                "fill_result", "fill_result_fp", "fill_export", "fill_export_fp")
    return table


def _render_table_summary(state, frame: Optional[pd.DataFrame] = None) -> None:
    table: AbbreviationTable = state.table
    report = state.table_report
    if table is None:
        return

    metric_row(
        [
            ("Abbreviations loaded", f"{len(table):,}"),
            ("Longest phrase", f"{table.max_phrase_len} word(s)"),
            ("Rows in file", f"{len(frame):,}" if frame is not None else "0"),
        ],
        columns=3,
    )

    if report is not None:
        for message in report.messages:
            note(message, "warning")
        if report.added:
            note(f"{report.added:,} abbreviations are ready to use.", "success")

    if frame is not None:
        with st.expander("Preview of the abbreviation file"):
            st.dataframe(display_frame(frame.head(30)), **full_width(st.dataframe), hide_index=True)

    with st.expander(f"Show all {len(table):,} loaded abbreviations"):
        search = st.text_input("Filter", key="abbr_filter", placeholder="type to search…")
        view = table.to_frame()
        if search:
            mask = view.apply(
                lambda row: search.lower() in " ".join(row.astype(str)).lower(), axis=1
            )
            view = view[mask]
        st.dataframe(view, **full_width(st.dataframe), hide_index=True)

    _next_button(state, "Next: choose column", enabled=bool(state.data_frame is not None))


# ===========================================================================
# step 3 - choose the column
# ===========================================================================
def _step_choose_column(state) -> None:
    section(
        "3 · Choose the column to convert",
        "Pick the column that holds the text you want to turn into tag names. Every other "
        "column is preserved exactly as it is.",
    )
    frame = _require_data(state)
    if frame is None:
        return

    columns = list(frame.columns)
    guess = state.target_col if state.target_col in columns else guess_column(columns, ("equipment", "description", "name", "item", "tag", "section"))
    choice = column_picker(
        columns,
        "target_col",
        "Column to process",
        guess=guess,
        help_text="You can change this at any time - nothing is lost.",
    )
    if choice != state.target_col:
        state.target_col = choice
        state.clear("result", "result_fp", "export_bytes", "export_fp", "overrides")

    if not choice:
        note("Select the column that contains the equipment or section names.", "info")
        return

    values = frame[choice]
    blanks = int(values.isna().sum() + (values.astype(str).str.strip() == "").sum())
    unique = int(values.nunique(dropna=True))

    metric_row(
        [
            ("Rows", f"{len(values):,}"),
            ("Distinct values", f"{unique:,}"),
            ("Empty cells", f"{blanks:,}"),
            ("Other columns kept", f"{len(columns) - 1:,}"),
        ],
        columns=4,
    )

    sample = pd.DataFrame({"Example value": [to_text(v) for v in values.head(8).tolist()]})
    st.dataframe(sample, **full_width(st.dataframe), hide_index=True)
    st.caption(
        "Columns available for the naming template in the next step: "
        + ", ".join(f"`{column}`" for column in columns)
    )
    _next_button(state, "Next: naming convention", enabled=bool(choice))


# ===========================================================================
# step 4 - naming convention
# ===========================================================================
def _step_naming(state) -> None:
    section(
        "4 · Configure the naming convention",
        "Build the tag exactly the way your company specifies it. If a rule is not covered "
        "here, type it into the template - nothing is guessed for you.",
    )
    frame = _require_data(state)
    if frame is None:
        return
    if not state.target_col:
        note("Choose the column to convert first (step 3).", "warning")
        _go_to(state, 3)
        return
    table = state.table
    if table is None:
        note("Load the company abbreviation list first (step 2).", "warning")
        _go_to(state, 2)
        return

    config: NamingConfig = state.config or NamingConfig()
    columns = list(frame.columns)

    preset_names = list(TEMPLATE_PRESETS)
    current_preset = next(
        (name for name, value in TEMPLATE_PRESETS.items() if value == config.template),
        CUSTOM_PRESET,
    )
    preset = st.selectbox("Start from a template", preset_names, index=preset_names.index(current_preset),
                          key="cfg_preset")
    if preset != CUSTOM_PRESET and TEMPLATE_PRESETS[preset] != config.template:
        config = config.replace(template=TEMPLATE_PRESETS[preset])
        st.session_state["cfg_template"] = TEMPLATE_PRESETS[preset]

    template = st.text_input(
        "Naming template",
        value=config.template,
        key="cfg_template",
        help="Combine placeholders, e.g. {prefix}{abbr}{index:03d}. Two placeholders written "
             "next to each other are joined with the separator below.",
    )
    config = config.replace(template=template)

    errors, warnings = validate_template(template, columns)
    for error in errors:
        note(error, "error")
    for warning in warnings:
        note(warning, "warning")
    config_ok = not errors

    with st.expander("What can I put in the template?"):
        placeholder_help_table(PLACEHOLDER_HELP)
        st.caption(
            "Example: `{prefix}{abbr}` with prefix `ADANI_XYZ` and separator `_` produces "
            "`ADANI_XYZ_BFW_PMP`. `{prefix}-{abbr}` keeps the dash you typed."
        )

    left, right = st.columns(2)
    with left:
        st.markdown("**Separators and casing**")
        config = config.replace(
            separator=st.text_input("Separator", value=config.separator, key="cfg_sep",
                                    help="Used between template parts and between abbreviated words."),
            inner_separator=st.text_input(
                "Separator between abbreviated words (blank = same as separator)",
                value=config.inner_separator, key="cfg_inner"),
            case=st.radio("Letter case", CASE_OPTIONS,
                          index=CASE_OPTIONS.index(config.case) if config.case in CASE_OPTIONS else 0,
                          key="cfg_case", horizontal=True),
            prefix=st.text_input("Prefix (e.g. plant code)", value=config.prefix, key="cfg_prefix"),
            suffix=st.text_input("Suffix (e.g. revision)", value=config.suffix, key="cfg_suffix"),
            index_start=st.number_input("Row number starts at", min_value=0, value=int(config.index_start),
                                        step=1, key="cfg_indexstart"),
        )
    with right:
        st.markdown("**Text handling**")
        config = config.replace(
            drop_stop_words=st.checkbox(
                "Drop filler words (of, the, and …)", value=config.drop_stop_words, key="cfg_dropstop"),
            keep_numbers=st.checkbox("Keep numbers (2, 3 …) in the tag", value=config.keep_numbers,
                                     key="cfg_keepnumbers"),
            allow_plural_matching=st.checkbox(
                "Match simple plurals ('Pumps' → 'Pump')", value=config.allow_plural_matching,
                key="cfg_plural", help="Only matches an abbreviation that already exists."),
            dedupe_consecutive_tokens=st.checkbox(
                "Remove repeated words next to each other", value=config.dedupe_consecutive_tokens,
                key="cfg_dedupe"),
            collapse_repeated_separators=st.checkbox("Collapse repeated separators (`A__B` → `A_B`)",
                                                     value=config.collapse_repeated_separators,
                                                     key="cfg_collapse"),
            trim_separator_edges=st.checkbox("Remove separators at the start/end",
                                             value=config.trim_separator_edges, key="cfg_trim"),
        )
        if config.drop_stop_words:
            config = config.replace(
                stop_words=st.text_area("Filler words (one per line)", value=config.stop_words,
                                        key="cfg_stop", height=90)
            )

    with st.expander("Advanced: length, characters and duplicates"):
        adv_left, adv_right = st.columns(2)
        with adv_left:
            config = config.replace(
                max_length=int(st.number_input("Maximum tag length (0 = no limit)",
                                               min_value=0, value=int(config.max_length), step=1,
                                               key="cfg_maxlen")),
                truncate_mode=st.selectbox(
                    "When a tag is too long",
                    TRUNCATE_OPTIONS,
                    index=TRUNCATE_OPTIONS.index(config.truncate_mode)
                    if config.truncate_mode in TRUNCATE_OPTIONS else 0,
                    key="cfg_trunc", disabled=not config.max_length),
                allowed_extra_chars=st.text_input("Extra characters to allow",
                                                  value=config.allowed_extra_chars, key="cfg_allowed",
                                                  help="Beyond letters, digits and the separator."),
                invalid_char_pattern=st.text_input(
                    "Custom 'invalid characters' pattern (advanced, regex)",
                    value=config.invalid_char_pattern, key="cfg_pattern",
                    help="Leave empty to use the default, which is built from the separator."),
                replace_invalid_with=st.text_input("Replace invalid characters with",
                                                   value=config.replace_invalid_with, key="cfg_replace"),
            )
        with adv_right:
            config = config.replace(
                uniquify_duplicates=st.checkbox(
                    "Number duplicate tags automatically so every tag is unique",
                    value=config.uniquify_duplicates, key="cfg_uniquify"),
                uniquify_format=st.text_input(
                    "Duplicate format", value=config.uniquify_format, key="cfg_uniqfmt",
                    help="{tag} original tag · {separator} · {n} number · {index} row number"),
                uniquify_start=int(st.number_input("First duplicate number", min_value=2,
                                                   value=int(config.uniquify_start), step=1,
                                                   key="cfg_uniqstart")),
            )

    for problem in config.issues():
        note(problem, "warning")

    state.config = config

    if config_ok:
        st.markdown("**Live preview (first rows of the selected column)**")
        preview = TagGenerator(table, config).preview_samples(frame[state.target_col].tolist(), limit=5)
        if preview:
            st.dataframe(
                pd.DataFrame(
                    [{"Original": row.original, "Generated tag": row.tag,
                      "Unmatched": ", ".join(row.unknown_words)} for row in preview]
                ),
                **full_width(st.dataframe),
                hide_index=True,
            )
        _next_button(state, "Next: preview", enabled=True)
    else:
        note("Fix the template above before continuing.", "warning")


# ===========================================================================
# step 5 - preview and edit
# ===========================================================================
def _fingerprint(state) -> str:
    payload = [
        str(state.data_file_id),
        str(state.data_sheet),
        str(state.data_header_row),
        str(state.target_col),
        str(getattr(state.table, "version", "0")),
        str(state.config.fingerprint() if state.config else ""),
        json.dumps(sorted((str(k), str(v)) for k, v in (state.overrides or {}).items())),
    ]
    return "||".join(payload)


def _ensure_results(state) -> Optional[PipelineResult]:
    frame = state.data_frame
    table = state.table
    config = state.config
    target = state.target_col
    if frame is None or table is None or config is None or not target:
        return None

    fingerprint = _fingerprint(state)
    if state.result is not None and state.result_fp == fingerprint:
        return state.result

    progress = st.progress(0.0, text="Generating tag names…")

    def _tick(done, total):
        progress.progress(min(done / max(total, 1), 1.0), text=f"Generating tag names… {done:,}/{total:,}")

    try:
        result = run_pipeline(frame, target, table, config, overrides=state.overrides or {},
                              progress_callback=_tick)
    except KeyError as exc:
        progress.empty()
        note(str(exc), "error")
        return None
    progress.empty()
    state.result = result
    state.result_fp = fingerprint
    state.clear("export_bytes", "export_fp")
    return result


def _step_preview(state) -> None:
    section(
        "5 · Preview the generated tag names",
        "Original text and generated tag side by side. You can edit any tag directly in the "
        "table - your edit is kept and marked as manual.",
    )
    result = _ensure_results(state)
    if result is None:
        note("Complete steps 1-4 to generate tags.", "warning")
        _go_to(state, 1)
        return

    metric_row(
        [
            ("Rows", f"{result.stats['rows']:,}"),
            ("Tags generated", f"{result.stats['tags generated']:,}"),
            ("Rows with unmatched words", f"{result.stats['rows with unknown words']:,}"),
            ("Duplicate tags", f"{result.stats['duplicate tags']:,}"),
        ],
        columns=4,
    )

    tag_column = result.config.output_column
    left, middle, right = st.columns([2, 2, 2])
    with left:
        only_problems = st.checkbox("Only rows that need attention", value=False, key="pv_problems")
    with middle:
        limit = st.selectbox("Rows to show", [25, 100, 500, 2000], index=1, key="pv_limit")
    with right:
        search = st.text_input("Search", key="pv_search", placeholder="text or tag…")

    frame = result.preview_frame.copy()
    if only_problems:
        frame = frame[frame["Status"] != "OK"]
    if search:
        needle = search.lower()
        frame = frame[frame.apply(lambda row: needle in " ".join(row.astype(str)).lower(), axis=1)]
    frame = frame.head(int(limit))

    if frame.empty:
        note("No rows match these filters.", "info")

    editable = st.data_editor(
        frame,
        key="editor_preview",
        num_rows="fixed",
        **full_width(st.data_editor),
        hide_index=True,
        disabled=[ROW_ID_COLUMN, "Row", "Original value", "Unknown words", "Status", "Notes"],
        column_config={
            ROW_ID_COLUMN: None,
            tag_column: st.column_config.TextColumn(tag_column, help="Type to override this tag"),
            "Row": st.column_config.NumberColumn("Row", width="small"),
        },
    )

    overrides: Dict[int, str] = dict(state.overrides or {})
    changed = False
    for row_id, value in zip(editable[ROW_ID_COLUMN].tolist(), editable[tag_column].tolist()):
        row_id = int(row_id)
        generated = ""
        if 0 <= row_id < len(result.results):
            generated = result.results[row_id].tag
        current = overrides.get(row_id, generated)
        new_value = to_text(value)
        if new_value != current:
            overrides[row_id] = new_value
            changed = True
    if changed:
        state.overrides = overrides
        st.rerun()

    if result.stats["manually edited"]:
        col, _ = st.columns([2, 6])
        with col:
            if st.button("Clear all manual edits", **full_width(st.button)):
                state.clear("overrides")
                st.rerun()
        st.caption(f"{result.stats['manually edited']} tag(s) were edited by hand and will be "
                   f"exported as typed.")

    st.markdown("**Highlighted view**")
    st.dataframe(styled_status_frame(result.preview_frame.drop(columns=[ROW_ID_COLUMN]).head(int(limit))),
                 **full_width(st.dataframe), hide_index=True)
    _next_button(state, "Next: unmatched words", enabled=True)


# ===========================================================================
# step 6 - unmatched words and mapping editor
# ===========================================================================
def _step_unmatched(state) -> None:
    section(
        "6 · Review unmatched words and the abbreviation list",
        "Words that are not in the company list are kept as typed (never guessed). Add a "
        "mapping only when you know the official abbreviation.",
    )
    result = _ensure_results(state)
    if result is None:
        note("Generate tags first (steps 1-4).", "warning")
        _go_to(state, 1)
        return

    table: AbbreviationTable = state.table
    unknown = result.unknown_frame

    if unknown.empty:
        note("Every word in the selected column was found in the abbreviation list.", "success")
    else:
        st.markdown(f"**{len(unknown)} different word(s) are not in the abbreviation list** "
                    f"({result.stats['rows with unknown words']} row(s) affected)")
        editable = unknown.copy()
        editable["Action"] = "Use abbreviation"
        edited = st.data_editor(
            editable,
            key=f"editor_unknown_{table.version}",
            num_rows="fixed",
            **full_width(st.data_editor),
            hide_index=True,
            disabled=["Unknown word", "Occurrences", "Example row", "Example text"],
            column_config={
                "Your abbreviation": st.column_config.TextColumn(
                    "Your abbreviation", help="Type the official abbreviation for this word"),
                "Action": st.column_config.SelectboxColumn(
                    "Action", options=["Use abbreviation", "Ignore word (drop from tag)"],
                    help="Choose 'Ignore word' to remove the word from the tag completely."),
            },
        )

        if st.button("Add the abbreviations I typed", type="primary", key="btn_add_abbr"):
            added = 0
            messages = []
            for word, abbr, action in zip(edited["Unknown word"], edited["Your abbreviation"],
                                          edited["Action"]):
                word = to_text(word)
                abbr = to_text(abbr)
                if action == "Ignore word (drop from tag)":
                    abbr = DROP_MARKER
                if not abbr:
                    continue
                ok, message = table.add(word, abbr, source=SOURCE_USER)
                if ok:
                    added += 1
                    messages.append(message)
            state.table = table
            if added:
                st.session_state.pop(f"editor_unknown_{table.version}", None)
                note(f"{added} mapping(s) added. Tags are regenerated with the new list.", "success")
                st.rerun()
            else:
                note("Nothing was added - type an abbreviation in the 'Your abbreviation' "
                     "column first.", "warning")

    st.divider()
    st.markdown("**Abbreviation list** - add, edit or remove entries")
    st.caption("Edit the cells below, add rows at the bottom, or delete rows. Press "
               "*Apply changes* when you are done.")
    current = table.to_frame()
    edited_map = st.data_editor(
        current,
        key=f"editor_mappings_{table.version}",
        num_rows="dynamic",
        **full_width(st.data_editor),
        hide_index=True,
        disabled=["Source"],
        column_config={
            "Phrase": st.column_config.TextColumn("Phrase", required=True),
            "Abbreviation": st.column_config.TextColumn("Abbreviation", required=True),
        },
    )

    if st.button("Apply changes to the abbreviation list", type="primary", key="btn_apply_map"):
        _apply_mapping_changes(state, table, current, edited_map)
        st.rerun()

    if len(table):
        download_button(
            "Download the updated abbreviation list (CSV)",
            build_abbreviations_csv(table),
            file_name="abbreviations_updated.csv",
            mime="text/csv",
            key="dl_abbr",
        )

    _next_button(state, "Next: validation", enabled=True)


def _apply_mapping_changes(state, table: AbbreviationTable, current: pd.DataFrame,
                           edited: pd.DataFrame) -> None:
    wanted: Dict[str, Tuple[str, str, str]] = {}
    for _, row in edited.iterrows():
        phrase = to_text(row.get("Phrase"))
        abbr = to_text(row.get("Abbreviation"))
        if not phrase:
            continue
        wanted[phrase_key(phrase)] = (phrase, abbr, to_text(row.get("Note")))

    removed = 0
    for entry in list(table):
        if entry.key not in wanted:
            table.remove(entry.phrase)
            removed += 1

    changed = 0
    for key, (phrase, abbr, note_text) in wanted.items():
        existing = table.get(phrase)
        if existing is None or existing.abbr != abbr or existing.note != note_text:
            table.add(
                phrase,
                abbr,
                source=existing.source if existing else SOURCE_USER,
                note=note_text or (existing.note if existing else ""),
            )
            changed += 1

    state.table = table
    st.session_state.pop(f"editor_mappings_{table.version}", None)
    if changed or removed:
        note(f"Abbreviation list updated: {changed} added/changed, {removed} removed. "
             f"Tags are regenerated.", "success")
    else:
        note("No changes to apply.", "info")


# ===========================================================================
# step 7 - validation
# ===========================================================================
def _step_validation(state) -> None:
    section(
        "7 · Validation report",
        "Empty values, unmatched words, duplicate tags and invalid characters are listed "
        "here before anything is exported.",
    )
    result = _ensure_results(state)
    if result is None:
        note("Generate tags first (steps 1-4).", "warning")
        _go_to(state, 1)
        return

    from ..validation import summarise_issues

    counts = summarise_issues(result.issues)
    metric_row(
        [
            ("Rows checked", f"{result.stats['rows']:,}"),
            ("Empty values", f"{result.stats['empty values']:,}"),
            ("Unmatched words", f"{result.stats['distinct unknown words']:,}"),
            ("Duplicate tag groups", f"{len(result.duplicate_groups):,}"),
        ],
        columns=4,
    )

    if not result.issues:
        note("No problems found - every row produced a unique, complete tag.", "success")
    else:
        for code, count in counts.items():
            st.markdown(f"- **{code}**: {count:,}")

        st.divider()
        from ..validation import issues_to_frame

        issues_frame = issues_to_frame(result.issues)
        codes = sorted(set(issues_frame["Issue"]))
        selected = st.multiselect("Filter by issue", codes, default=codes, key="val_filter")
        view = issues_frame[issues_frame["Issue"].isin(selected)] if selected else issues_frame
        st.dataframe(view, **full_width(st.dataframe), hide_index=True)

        if result.duplicate_groups:
            st.markdown("**Duplicate tags**")
            duplicate_rows = [
                {
                    "Tag": tag,
                    "Rows": ", ".join(str(row + 1) for row in rows),
                    "Count": len(rows),
                }
                for tag, rows in sorted(result.duplicate_groups.items())
            ]
            st.dataframe(pd.DataFrame(duplicate_rows), **full_width(st.dataframe), hide_index=True)
            if not result.config.uniquify_duplicates:
                if st.button("Number duplicate tags automatically", type="primary",
                            key="btn_uniquify"):
                    state.config = result.config.replace(uniquify_duplicates=True)
                    st.session_state["cfg_uniquify"] = True
                    st.rerun()
                st.caption("Adds `_2`, `_3` … to the repeated tags so every tag is unique.")

        download_button(
            "Download the validation issues (CSV)",
            dataframe_to_csv_bytes(issues_frame),
            file_name="validation_issues.csv",
            mime="text/csv",
            key="dl_issues",
        )

    _next_button(state, "Next: download", enabled=True)


# ===========================================================================
# step 8 - export
# ===========================================================================
def _step_export(state) -> None:
    section(
        "8 · Download the processed file",
        "The export contains every original column and row plus the generated tags. "
        "Your uploaded file is never changed.",
    )
    result = _ensure_results(state)
    if result is None:
        note("Generate tags first (steps 1-4).", "warning")
        _go_to(state, 1)
        return

    frame = state.data_frame
    config: NamingConfig = state.config

    left, right = st.columns(2)
    with left:
        output_column = st.text_input(
            "Name of the new column",
            value=config.output_column,
            key="exp_colname",
            help="Used when the tags are added as a new column.",
        )
        include_report = st.checkbox(
            "Add report sheets to the workbook (unmatched words, issues, settings)",
            value=bool(state.get("exp_report", True)),
            key="exp_report_box",
        )
    with right:
        replace_source = st.checkbox(
            f"Replace the '{state.target_col}' column instead of adding a new one",
            value=bool(state.get("exp_replace", False)),
            key="exp_replace_box",
            help="The original text is kept in a new '<column> (original)' column so nothing "
                 "is lost.",
        )
        data_sheet_name = st.text_input("Worksheet name for the data", value="Processed Data",
                                        key="exp_sheetname")

    output_column = (output_column or "Generated_Tag").strip()
    config = config.replace(output_column=output_column, replace_source_column=replace_source)
    state.exp_report = include_report
    state.exp_replace = replace_source
    if config.output_column != result.config.output_column or config.replace_source_column != result.config.replace_source_column:
        state.config = config
        result = _ensure_results(state) or result

    output_frame = build_output_frame(frame, result.tags, config, state.target_col)
    st.markdown(f"**Result: {len(output_frame):,} rows × {len(output_frame.columns)} columns**")
    st.dataframe(display_frame(output_frame.head(20)), **full_width(st.dataframe), hide_index=True)

    meta = default_meta(
        data_file=getattr(state, "data_file_name", ""),
        sheet_name=getattr(state, "data_sheet", "") or "",
        target_column=state.target_col,
        table=state.table,
        abbr_file=getattr(state, "abbr_file_name", "") or "",
    )
    meta["Output column"] = output_column if not replace_source else f"{state.target_col} (replaced)"
    meta["Manual edits"] = result.stats["manually edited"]

    fingerprint = _fingerprint(state) + f"||{output_column}||{replace_source}||{include_report}||{data_sheet_name}"
    if state.export_bytes is None or state.export_fp != fingerprint:
        with st.spinner("Building the Excel file…"):
            state.export_bytes = build_processed_workbook(
                result, frame, meta,
                data_sheet_name=data_sheet_name or "Processed Data",
                include_report=include_report,
            )
            state.export_fp = fingerprint

    stem = Path(getattr(state, "data_file_name", "equipment") or "equipment").stem
    base = safe_filename(stem) or "equipment"

    st.markdown("### Download")
    left, right = st.columns(2)
    with left:
        download_button(
            "⬇ Download processed Excel file",
            state.export_bytes,
            file_name=f"{base}_with_tags.xlsx",
            key="dl_main",
            help_text=f"{len(state.export_bytes) / 1024:,.0f} KB · all original columns preserved",
        )
    with right:
        download_button(
            "⬇ Download validation report (Excel)",
            build_report_workbook(result, meta),
            file_name=f"{base}_validation_report.xlsx",
            key="dl_report",
            help_text="Unmatched words, validation issues, abbreviations used and settings",
        )

    note(f"Your source file **{getattr(state, 'data_file_name', '')}** was never modified - "
         f"everything above was created in memory.", "success")
