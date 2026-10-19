"""Validation of generated tag names.

Every problem the app can spot is expressed as an :class:`Issue` with a stable
``code`` so it can be counted, filtered and exported.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Sequence

import pandas as pd

from .config import NamingConfig
from .taggen import RowResult

__all__ = [
    "Issue",
    "CODE_EMPTY",
    "CODE_UNKNOWN",
    "CODE_DUPLICATE",
    "CODE_INVALID_CHAR",
    "CODE_TOO_LONG",
    "CODE_MANUAL",
    "SEVERITY_ORDER",
    "check_results",
    "find_duplicate_tags",
    "uniquify_tags",
    "issues_to_frame",
    "summarise_issues",
]

CODE_EMPTY = "Empty source value"
CODE_UNKNOWN = "Unknown word"
CODE_DUPLICATE = "Duplicate tag"
CODE_INVALID_CHAR = "Invalid character"
CODE_TOO_LONG = "Too long"
CODE_MANUAL = "Manually edited"
CODE_DUPLICATE_SOURCE = "Duplicate source value"

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}

SEVERITY_FOR_CODE = {
    CODE_EMPTY: "error",
    CODE_UNKNOWN: "warning",
    CODE_DUPLICATE: "error",
    CODE_INVALID_CHAR: "warning",
    CODE_TOO_LONG: "warning",
    CODE_MANUAL: "info",
    CODE_DUPLICATE_SOURCE: "info",
}


@dataclass
class Issue:
    """One validation finding."""

    code: str
    message: str
    row_id: Optional[int] = None
    severity: str = "warning"
    value: str = ""
    tag: str = ""

    def to_dict(self) -> Dict[str, object]:
        data = asdict(self)
        data["row_id"] = "" if self.row_id is None else int(self.row_id) + 1  # 1-based for humans
        return data


def check_results(
    results: Sequence[RowResult],
    config: NamingConfig,
    source_values: Optional[Sequence[object]] = None,
) -> List[Issue]:
    """Run every row-level check and return the findings."""
    issues: List[Issue] = []
    try:
        invalid_re = re.compile(config.effective_invalid_pattern())
    except re.error:
        invalid_re = re.compile(r"[^A-Za-z0-9_]")

    seen_source: Dict[str, int] = {}

    for result in results:
        row_number = result.row_id + 1

        if not result.original:
            issues.append(
                Issue(
                    CODE_EMPTY,
                    f"Row {row_number}: the selected column is empty, so no tag could be generated.",
                    row_id=result.row_id,
                    severity=SEVERITY_FOR_CODE[CODE_EMPTY],
                    value="",
                    tag=result.tag,
                )
            )
        elif source_values is not None:
            key = " ".join(result.original.lower().split())
            if key in seen_source:
                issues.append(
                    Issue(
                        CODE_DUPLICATE_SOURCE,
                        f"Row {row_number}: same text as row {seen_source[key] + 1} "
                        f"('{result.original}') - both get the tag '{result.tag}'.",
                        row_id=result.row_id,
                        severity=SEVERITY_FOR_CODE[CODE_DUPLICATE_SOURCE],
                        value=result.original,
                        tag=result.tag,
                    )
                )
            else:
                seen_source[key] = result.row_id

        for word in result.unknown_words:
            issues.append(
                Issue(
                    CODE_UNKNOWN,
                    f"Row {row_number}: '{word}' is not in the abbreviation list - "
                    f"the word was kept as typed.",
                    row_id=result.row_id,
                    severity=SEVERITY_FOR_CODE[CODE_UNKNOWN],
                    value=result.original,
                    tag=result.tag,
                )
            )

        if result.tag and invalid_re.search(result.tag):
            found = sorted(set(invalid_re.findall(result.tag)))
            issues.append(
                Issue(
                    CODE_INVALID_CHAR,
                    f"Row {row_number}: tag '{result.tag}' still contains "
                    f"{', '.join(repr(f) for f in found)}.",
                    row_id=result.row_id,
                    severity=SEVERITY_FOR_CODE[CODE_INVALID_CHAR],
                    value=result.original,
                    tag=result.tag,
                )
            )

        if config.max_length and len(result.tag) > config.max_length:
            issues.append(
                Issue(
                    CODE_TOO_LONG,
                    f"Row {row_number}: tag is {len(result.tag)} characters "
                    f"(limit {config.max_length}).",
                    row_id=result.row_id,
                    severity=SEVERITY_FOR_CODE[CODE_TOO_LONG],
                    value=result.original,
                    tag=result.tag,
                )
            )

        if result.edited:
            issues.append(
                Issue(
                    CODE_MANUAL,
                    f"Row {row_number}: '{result.tag}' was typed by the user.",
                    row_id=result.row_id,
                    severity=SEVERITY_FOR_CODE[CODE_MANUAL],
                    value=result.original,
                    tag=result.tag,
                )
            )

    issues.extend(duplicate_issues([result.tag for result in results]))
    issues.sort(key=lambda issue: (SEVERITY_ORDER.get(issue.severity, 9), issue.row_id or -1, issue.code))
    return issues


def find_duplicate_tags(tags: Sequence[str]) -> Dict[str, List[int]]:
    """Map ``tag -> list of row positions`` for every tag used more than once."""
    positions: Dict[str, List[int]] = {}
    for row_id, tag in enumerate(tags):
        text = "" if tag is None else str(tag)
        if not text.strip():
            continue
        positions.setdefault(text, []).append(row_id)
    return {tag: rows for tag, rows in positions.items() if len(rows) > 1}


def duplicate_issues(tags: Sequence[str]) -> List[Issue]:
    issues: List[Issue] = []
    for tag, rows in find_duplicate_tags(tags).items():
        numbers = ", ".join(str(row + 1) for row in rows)
        issues.append(
            Issue(
                CODE_DUPLICATE,
                f"Rows {numbers}: all produce the tag '{tag}'.",
                row_id=rows[0],
                severity=SEVERITY_FOR_CODE[CODE_DUPLICATE],
                tag=tag,
            )
        )
    return issues


def uniquify_tags(tags: Sequence[str], config: NamingConfig) -> List[str]:
    """Make duplicate tags unique by numbering them (``{tag}_{2}`` by default)."""
    result = ["" if tag is None else str(tag) for tag in tags]
    separator = config.separator or "_"
    start = max(2, int(config.uniquify_start or 2))

    for rows in find_duplicate_tags(result).values():
        # the first occurrence keeps the original tag, the rest get numbered
        counter = start
        for row_id in rows[1:]:
            base = result[row_id]
            new_tag = config.uniquify_format.format(
                tag=base, separator=separator, n=counter, index=row_id + 1
            )
            while new_tag in result:
                counter += 1
                new_tag = config.uniquify_format.format(
                    tag=base, separator=separator, n=counter, index=row_id + 1
                )
            result[row_id] = new_tag
            counter += 1
    return result


def issues_to_frame(issues: Sequence[Issue]) -> pd.DataFrame:
    """Issues as a tidy DataFrame (row numbers are 1-based, like Excel)."""
    if not issues:
        return pd.DataFrame(columns=["Row", "Severity", "Issue", "Details", "Original value", "Generated tag"])
    rows = []
    for issue in issues:
        data = issue.to_dict()
        rows.append(
            {
                "Row": data["row_id"],
                "Severity": issue.severity.capitalize(),
                "Issue": issue.code,
                "Details": issue.message,
                "Original value": issue.value,
                "Generated tag": issue.tag,
            }
        )
    return pd.DataFrame(rows)


def summarise_issues(issues: Sequence[Issue]) -> Dict[str, int]:
    """Count issues per code (ordered by severity)."""
    counts: Dict[str, int] = {}
    for issue in issues:
        counts[issue.code] = counts.get(issue.code, 0) + 1
    return dict(
        sorted(counts.items(), key=lambda item: (SEVERITY_ORDER.get(SEVERITY_FOR_CODE.get(item[0], "warning"), 9), item[0]))
    )
