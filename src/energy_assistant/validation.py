"""Validation rules and audit reporting for the source datasets."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from energy_assistant.config import (
    EXPECTED_EXCEL_SHEETS,
    EXPECTED_OUTAGE_COLUMNS,
    OUTAGE_DATE_COLUMNS,
    OUTAGE_NUMERIC_COLUMNS,
)
from energy_assistant.data_loading import (
    iter_csv_chunks,
    temporary_duplicate_index,
    update_duplicate_counts,
)


def new_validation_report() -> dict[str, Any]:
    return {
        "started_at": datetime.now().astimezone().isoformat(),
        "status": "running",
        "errors": [],
        "warnings": [],
        "electricity": {},
        "outages": {},
    }


def record_issue(
    report: dict[str, Any],
    *,
    severity: str,
    code: str,
    message: str,
    source: str,
    field: str | None = None,
    example: dict[str, Any] | None = None,
    examples: list[dict[str, Any]] | None = None,
    count: int = 1,
) -> None:
    """Add an issue and keep only a few examples while counting all occurrences."""
    collection_name = "errors" if severity == "error" else "warnings"
    collection = report[collection_name]
    existing = next(
        (
            item
            for item in collection
            if item["code"] == code
            and item["source"] == source
            and item.get("field") == field
        ),
        None,
    )
    if existing is None:
        existing = {
            "severity": severity,
            "code": code,
            "message": message,
            "source": source,
            "field": field,
            "count": 0,
            "examples": [],
        }
        collection.append(existing)
    existing["count"] += count
    if example is not None and len(existing["examples"]) < 5:
        existing["examples"].append(example)
    if examples:
        existing["examples"].extend(examples[: max(0, 5 - len(existing["examples"]))])


def check_required_files(
    electricity_dir: Path,
    electricity_files: tuple[str, ...],
    outage_file: Path,
) -> list[Path]:
    paths = [electricity_dir / name for name in electricity_files]
    paths.append(outage_file)
    missing = [path for path in paths if not path.is_file()]
    if missing:
        names = "\n".join(f"- {path}" for path in missing)
        raise FileNotFoundError(f"Required source files are missing:\n{names}")
    return paths


def validate_sheet_names(
    workbook_name: str,
    actual_sheets: list[str],
    report: dict[str, Any],
) -> None:
    expected = set(EXPECTED_EXCEL_SHEETS)
    actual = set(actual_sheets)
    for sheet in sorted(expected - actual):
        record_issue(
            report,
            severity="error",
            code="missing_worksheet",
            message=f"Expected worksheet {sheet!r} is missing.",
            source=workbook_name,
            field=sheet,
        )
    for sheet in sorted(actual - expected):
        record_issue(
            report,
            severity="error",
            code="unexpected_worksheet",
            message=f"Unexpected worksheet {sheet!r} was not transformed.",
            source=workbook_name,
            field=sheet,
        )


def validate_outage_csv(
    path: Path,
    report: dict[str, Any],
    *,
    chunk_size: int,
    progress: Any = None,
) -> dict[str, Any]:
    """Validate the outage CSV in chunks without writing another full-size copy."""
    source = path.name
    summary: dict[str, Any] = {
        "file": source,
        "size_bytes": path.stat().st_size,
        "chunk_size": chunk_size,
        "row_count": 0,
        "columns": [],
        "missing_values": {},
        "date_ranges": {},
        "invalid_dates": {},
        "numeric_ranges": {},
        "invalid_numeric_values": {},
        "duplicate_rows": 0,
        "duplicate_ids": 0,
        "first_5_records": [],
    }
    missing_counts: dict[str, int] = {}
    date_min: dict[str, pd.Timestamp] = {}
    date_max: dict[str, pd.Timestamp] = {}
    numeric_min: dict[str, float] = {}
    numeric_max: dict[str, float] = {}
    invalid_date_counts: dict[str, int] = {}
    invalid_numeric_counts: dict[str, int] = {}
    invalid_date_examples: dict[str, list[dict[str, Any]]] = {}
    invalid_numeric_examples: dict[str, list[dict[str, Any]]] = {}
    chunk_number = 0

    with temporary_duplicate_index() as duplicate_index:
        try:
            for chunk in iter_csv_chunks(path, chunk_size):
                chunk_number += 1
                if not summary["columns"]:
                    summary["columns"] = list(chunk.columns)
                    for column in EXPECTED_OUTAGE_COLUMNS:
                        if column not in chunk.columns:
                            record_issue(
                                report,
                                severity="error",
                                code="missing_required_column",
                                message=f"Required outage CSV column {column!r} is missing.",
                                source=source,
                                field=column,
                            )
                    for column in chunk.columns:
                        if column not in EXPECTED_OUTAGE_COLUMNS:
                            record_issue(
                                report,
                                severity="warning",
                                code="unexpected_column",
                                message=(
                                    f"Unrecognized column {column!r} is retained in the "
                                    "original CSV and was not discarded."
                                ),
                                source=source,
                                field=column,
                            )
                        missing_counts[column] = 0

                summary["row_count"] += len(chunk)
                if len(summary["first_5_records"]) < 5:
                    summary["first_5_records"].extend(
                        chunk.head(5 - len(summary["first_5_records"])).to_dict(
                            orient="records"
                        )
                    )

                for column in chunk.columns:
                    missing_counts[column] += int(chunk[column].eq("").sum())

                for column in OUTAGE_DATE_COLUMNS:
                    if column not in chunk:
                        continue
                    values = chunk[column]
                    present = values.ne("")
                    parsed = pd.to_datetime(
                        values.where(present),
                        format="%Y-%m-%d",
                        errors="coerce",
                    )
                    bad = present & parsed.isna()
                    invalid_count = int(bad.sum())
                    invalid_date_counts[column] = (
                        invalid_date_counts.get(column, 0) + invalid_count
                    )
                    if invalid_count:
                        examples = invalid_date_examples.setdefault(column, [])
                        for row_index in chunk.index[bad][: max(0, 5 - len(examples))]:
                            examples.append(
                                {
                                    "source_row": int(row_index) + 2,
                                    "value": values.loc[row_index],
                                }
                            )
                    valid_dates = parsed.dropna()
                    if not valid_dates.empty:
                        current_min = valid_dates.min()
                        current_max = valid_dates.max()
                        date_min[column] = min(
                            current_min, date_min.get(column, current_min)
                        )
                        date_max[column] = max(
                            current_max, date_max.get(column, current_max)
                        )

                for column in OUTAGE_NUMERIC_COLUMNS:
                    if column not in chunk:
                        continue
                    values = chunk[column]
                    present = values.ne("")
                    parsed = pd.to_numeric(values.where(present), errors="coerce")
                    bad = present & parsed.isna()
                    if column == "id":
                        bad |= parsed.notna() & (parsed % 1 != 0)
                    invalid_count = int(bad.sum())
                    invalid_numeric_counts[column] = (
                        invalid_numeric_counts.get(column, 0) + invalid_count
                    )
                    if invalid_count:
                        examples = invalid_numeric_examples.setdefault(column, [])
                        for row_index in chunk.index[bad][: max(0, 5 - len(examples))]:
                            examples.append(
                                {
                                    "source_row": int(row_index) + 2,
                                    "value": values.loc[row_index],
                                }
                            )
                    valid_values = parsed.dropna()
                    if not valid_values.empty:
                        numeric_min[column] = min(
                            float(valid_values.min()),
                            numeric_min.get(column, float(valid_values.min())),
                        )
                        numeric_max[column] = max(
                            float(valid_values.max()),
                            numeric_max.get(column, float(valid_values.max())),
                        )

                records = [
                    tuple(str(value) for value in row)
                    for row in chunk.itertuples(index=False, name=None)
                ]
                id_index = (
                    int(chunk.columns.get_loc("id"))
                    if "id" in chunk.columns
                    else None
                )
                duplicate_rows, duplicate_ids = update_duplicate_counts(
                    duplicate_index,
                    records,
                    id_index=id_index,
                )
                summary["duplicate_rows"] += duplicate_rows
                summary["duplicate_ids"] += duplicate_ids
                if progress is not None:
                    progress(summary["row_count"], chunk_number)
        except (pd.errors.ParserError, UnicodeError) as error:
            record_issue(
                report,
                severity="error",
                code="csv_read_error",
                message=f"The CSV could not be read completely: {error}",
                source=source,
            )
            summary["read_error"] = str(error)

    summary["missing_values"] = missing_counts
    summary["date_ranges"] = {
        column: {
            "min": date_min[column].date().isoformat(),
            "max": date_max[column].date().isoformat(),
        }
        for column in date_min
    }
    summary["numeric_ranges"] = {
        column: {"min": numeric_min[column], "max": numeric_max[column]}
        for column in numeric_min
    }
    summary["invalid_dates"] = invalid_date_counts
    summary["invalid_numeric_values"] = invalid_numeric_counts

    for column, count in invalid_date_counts.items():
        if count:
            record_issue(
                report,
                severity="error",
                code="invalid_date",
                message="One or more non-empty date values do not match YYYY-MM-DD.",
                source=source,
                field=column,
                examples=invalid_date_examples.get(column, []),
                count=count,
            )
    for column, count in invalid_numeric_counts.items():
        if count:
            record_issue(
                report,
                severity="error",
                code="invalid_numeric_value",
                message="One or more non-empty values are not valid numeric values.",
                source=source,
                field=column,
                examples=invalid_numeric_examples.get(column, []),
                count=count,
            )
    if missing_counts.get("date", 0):
        record_issue(
            report,
            severity="error",
            code="missing_required_date",
            message="The required reporting date is blank.",
            source=source,
            field="date",
            count=missing_counts["date"],
            examples=[{"count": missing_counts["date"]}],
        )
    if missing_counts.get("id", 0):
        record_issue(
            report,
            severity="error",
            code="missing_required_id",
            message="One or more outage records have no ID.",
            source=source,
            field="id",
            count=missing_counts["id"],
            examples=[{"count": missing_counts["id"]}],
        )
    if summary["duplicate_rows"]:
        record_issue(
            report,
            severity="error",
            code="duplicate_row",
            message="Exact duplicate CSV records were found.",
            source=source,
            count=summary["duplicate_rows"],
            examples=[{"count": summary["duplicate_rows"]}],
        )
    if summary["duplicate_ids"]:
        record_issue(
            report,
            severity="error",
            code="duplicate_id",
            message="Duplicate outage record IDs were found.",
            source=source,
            field="id",
            count=summary["duplicate_ids"],
            examples=[{"count": summary["duplicate_ids"]}],
        )

    report["outages"] = summary
    return summary
