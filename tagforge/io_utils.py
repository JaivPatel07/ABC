"""Reading and writing spreadsheet files.

Two guarantees matter for this project:

1. Column names and positions are **never** assumed - they are read from the
   file and handed to the user as choices.
2. The uploaded file is only ever read.  Output is written to an in-memory
   buffer and offered as a download, so the source file can never be damaged.
"""

from __future__ import annotations

import io
import re
from typing import Dict, List, Optional, Tuple

import pandas as pd

__all__ = [
    "SUPPORTED_EXTENSIONS",
    "FileReadError",
    "file_extension",
    "is_supported",
    "list_sheets",
    "read_table",
    "sanitize_sheet_name",
    "dataframe_to_excel_bytes",
    "dataframe_to_csv_bytes",
    "safe_filename",
]

SUPPORTED_EXTENSIONS = (".xlsx", ".xlsm", ".csv", ".txt", ".tsv")

_XLSX_EXTENSIONS = (".xlsx", ".xlsm")
_INVALID_SHEET_CHARS = re.compile(r"[\[\]\:\*\?\/\\]")


class FileReadError(Exception):
    """Raised when an uploaded file cannot be read (shown to the user)."""


def file_extension(name: str) -> str:
    return ("." + str(name).rsplit(".", 1)[-1]).lower() if "." in str(name) else ""


def is_supported(name: str) -> bool:
    return file_extension(name) in SUPPORTED_EXTENSIONS


def _check_supported(name: str) -> None:
    extension = file_extension(name)
    if not is_supported(name):
        raise FileReadError(
            f"'{name}' is not a supported file type ({extension or 'no extension'}). "
            f"Please upload an .xlsx or .csv file. "
            f"Legacy .xls files must be re-saved as .xlsx in Excel first."
        )


def list_sheets(data: bytes, file_name: str) -> List[str]:
    """Return worksheet names (empty list for CSV files)."""
    _check_supported(file_name)
    if file_extension(file_name) not in _XLSX_EXTENSIONS:
        return []
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        sheets = list(workbook.sheetnames)
        workbook.close()
        return sheets
    except Exception as exc:  # pragma: no cover - openpyxl raises many types
        raise FileReadError(
            f"The workbook '{file_name}' could not be opened ({exc}). "
            f"If it is password protected or an old .xls file, re-save it as .xlsx."
        ) from exc


def _sniff_csv(raw: bytes, encoding: str) -> Tuple[str, int]:
    """Guess ``(delimiter, header_row)`` for a CSV file."""
    import csv

    sample = raw[:64 * 1024].decode(encoding, errors="replace")
    delimiter = ","
    try:
        delimiter = csv.Sniffer().sniff(sample, delimiters=",;\t|").delimiter
    except csv.Error:
        counts = {sep: sample.count(sep) for sep in (",", ";", "\t", "|")}
        delimiter = max(counts, key=counts.get) if max(counts.values()) else ","
    return delimiter, 0


def read_table(
    data: bytes,
    file_name: str,
    sheet_name: Optional[str] = None,
    header_row: int = 0,
    nrows: Optional[int] = None,
) -> pd.DataFrame:
    """Read an uploaded file into a DataFrame.

    ``header_row`` is 0-based.  All columns are returned exactly as they appear
    in the file; nothing is renamed or reordered here.
    """
    _check_supported(file_name)
    if data is None or len(data) == 0:
        raise FileReadError(f"'{file_name}' is empty (0 bytes).")

    buffer = io.BytesIO(data)
    extension = file_extension(file_name)
    header_row = max(0, int(header_row or 0))

    try:
        if extension in _XLSX_EXTENSIONS:
            frame = pd.read_excel(
                buffer,
                sheet_name=sheet_name or 0,
                header=header_row,
                nrows=nrows,
                engine="openpyxl",
                engine_kwargs={"read_only": True, "data_only": True},
            )
        else:
            encoding = "utf-8-sig"
            try:
                raw = data.decode(encoding)
            except UnicodeDecodeError:
                encoding = "cp1252"
                raw = data.decode(encoding, errors="replace")
            delimiter, _ = _sniff_csv(data, encoding)
            frame = pd.read_csv(
                io.StringIO(raw),
                sep=delimiter,
                header=header_row,
                nrows=nrows,
                engine="python",
                skip_blank_lines=True,
            )
    except FileReadError:
        raise
    except Exception as exc:
        raise FileReadError(
            f"'{file_name}' could not be read ({exc}). "
            f"Check that the file is not open in Excel and that the header row setting is correct."
        ) from exc

    if isinstance(frame, dict):  # multiple sheets requested
        frame = next(iter(frame.values()))

    return _tidy_columns(frame, file_name)


def _tidy_columns(frame: pd.DataFrame, file_name: str) -> pd.DataFrame:
    """Give unnamed columns a readable name and make sure headers are unique."""
    frame = frame.copy()
    columns: List[str] = []
    for index, column in enumerate(frame.columns):
        name = str(column).strip()
        if name.lower().startswith("unnamed:") or name in ("", "nan", "None"):
            name = f"Column {index + 1}"
        columns.append(name)

    seen: Dict[str, int] = {}
    unique_columns: List[str] = []
    for name in columns:
        if name in seen:
            seen[name] += 1
            candidate = f"{name} ({seen[name]})"
            while candidate in seen:
                seen[name] += 1
                candidate = f"{name} ({seen[name]})"
            seen[candidate] = 0
            unique_columns.append(candidate)
        else:
            seen[name] = 0
            unique_columns.append(name)

    frame.columns = unique_columns
    if frame.columns.empty:
        raise FileReadError(f"'{file_name}' has no columns - nothing to process.")
    return frame


def sanitize_sheet_name(name: str, used: Optional[List[str]] = None, fallback: str = "Sheet") -> str:
    """Excel sheet names: max 31 chars, no ``[ ] : * ? / \\`` and unique."""
    used = list(used or [])
    clean = _INVALID_SHEET_CHARS.sub("_", str(name or "").strip())[:31].strip() or fallback
    candidate = clean
    index = 2
    while candidate in used:
        suffix = f"_{index}"
        candidate = clean[: 31 - len(suffix)] + suffix
        index += 1
    return candidate


def _autosize(worksheet, frame: pd.DataFrame, max_width: int = 48) -> None:
    """Widen columns so the exported sheet is readable when opened."""
    from openpyxl.utils import get_column_letter

    from .text_utils import to_text  # local import avoids a circular import

    for position, column in enumerate(frame.columns, start=1):
        # to_text() also handles NaN/None, which `astype(str)` keeps as missing
        # values in pandas 3 string columns.
        values = [to_text(value) for value in frame[column].head(300).tolist()]
        width = max([len(str(column))] + [len(value) for value in values]) + 2
        worksheet.column_dimensions[get_column_letter(position)].width = min(max(width, 10), max_width)


def dataframe_to_excel_bytes(
    sheets: Dict[str, pd.DataFrame],
    freeze_header: bool = True,
    autofilter: bool = True,
) -> bytes:
    """Write one or more DataFrames into a single ``.xlsx`` file in memory."""
    if not sheets:
        raise ValueError("No sheets to write.")

    buffer = io.BytesIO()
    used: List[str] = []
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for raw_name, frame in sheets.items():
            sheet_name = sanitize_sheet_name(raw_name, used)
            used.append(sheet_name)
            frame = frame if isinstance(frame, pd.DataFrame) else pd.DataFrame(frame)
            frame.to_excel(writer, sheet_name=sheet_name, index=False)
            worksheet = writer.sheets[sheet_name]
            _autosize(worksheet, frame)
            if freeze_header and len(frame.columns):
                worksheet.freeze_panes = "A2"
            if autofilter and len(frame.columns) and len(frame):
                worksheet.auto_filter.ref = worksheet.dimensions

    buffer.seek(0)
    return buffer.getvalue()


def dataframe_to_csv_bytes(frame: pd.DataFrame) -> bytes:
    return frame.to_csv(index=False).encode("utf-8-sig")


def safe_filename(name: str, default: str = "export") -> str:
    """Make a file name safe for Windows/macOS/Linux downloads."""
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name or "").strip())
    clean = clean.rstrip(" .")
    return clean or default
