"""Reproducible transformations for the supplied electricity workbooks."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from openpyxl import load_workbook

from energy_assistant.config import (
    ELECTRICITY_FILES,
    ELECTRICITY_SOURCE_URL,
    PARQUET_BATCH_SIZE,
    REQUIRED_ELECTRICITY_COLUMNS,
)
from energy_assistant.data_loading import open_electricity_sheet
from energy_assistant.validation import record_issue, validate_sheet_names

EXCEL_ERROR_VALUES = {
    "#DIV/0!",
    "#N/A",
    "#NAME?",
    "#NULL!",
    "#NUM!",
    "#REF!",
    "#VALUE!",
    "#SPILL!",
    "#CALC!",
}


def _record_digest(values: tuple[Any, ...]) -> bytes:
    normalized = []
    for value in values:
        if isinstance(value, datetime):
            normalized.append(value.isoformat())
        elif isinstance(value, (str, int, float, bool)) or value is None:
            normalized.append(value)
        else:
            normalized.append(str(value))
    encoded = json.dumps(normalized, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.blake2b(encoded, digest_size=16).digest()


def _make_schema(
    column_names: list[str],
    formula_columns: set[str],
) -> pa.Schema:
    fields = [pa.field("Time", pa.timestamp("us"))]
    fields.extend(
        pa.field(name, pa.float64()) for name in column_names if name != "Time"
    )
    fields.extend(
        pa.field(f"{name}__formula_error", pa.string())
        for name in column_names
        if name in formula_columns
    )
    fields.extend(
        [
            pa.field("_source_file", pa.string()),
            pa.field("_source_sheet", pa.string()),
            pa.field("_source_row", pa.int64()),
        ]
    )
    return pa.schema(fields)


def _write_sheet(
    *,
    path: Path,
    sheet_name: str,
    output_path: Path,
    workbook_report: dict[str, Any],
    report: dict[str, Any],
    batch_size: int,
    progress: Callable[[str, str, int], None] | None = None,
) -> int:
    source = path.name
    with open_electricity_sheet(path, sheet_name) as (
        mapping,
        measurement_rows,
        formulas,
    ):
        column_names = [entry["output_name"] for entry in mapping]
        if "Time" not in column_names:
            record_issue(
                report,
                severity="error",
                code="missing_timestamp_column",
                message="The worksheet has no Time column.",
                source=source,
                field=sheet_name,
            )
            return 0
        required_columns = (
            REQUIRED_ELECTRICITY_COLUMNS
            if sheet_name == "Sheet1"
            else ("Time", "Solar+Wind")
        )
        missing_required = sorted(set(required_columns) - set(column_names))
        for name in missing_required:
            record_issue(
                report,
                severity="error",
                code="missing_required_column",
                message=f"Required electricity column {name!r} is missing.",
                source=source,
                field=name,
            )
        workbook_report["sheets"][sheet_name] = {
            "columns": mapping,
            "formula_expressions_from_first_measurement_row": formulas,
            "formula_values": "Cached values from the original workbook; formulas are not recalculated.",
            "units": "Not stated in the source workbook.",
            "row_count": 0,
            "missing_values": {name: 0 for name in column_names},
            "invalid_timestamps": 0,
            "invalid_numeric_values": {},
            "formula_error_values": {},
            "duplicate_rows": 0,
            "duplicate_or_non_increasing_timestamps": 0,
            "intervals_over_10_seconds": 0,
            "negative_raw_solar_values": 0,
            "timestamp_range": {"min": None, "max": None},
        }
        sheet_report = workbook_report["sheets"][sheet_name]
        formula_columns = set(formulas)
        schema = _make_schema(column_names, formula_columns)
        writer = pq.ParquetWriter(output_path, schema, compression="zstd")
        try:
            rows_buffer: list[tuple[int, tuple[Any, ...]]] = []
            seen_row_hashes: set[bytes] = set()
            previous_time: pd.Timestamp | None = None

            def flush_rows() -> None:
                if not rows_buffer:
                    return
                raw_values = [list(values) for _, values in rows_buffer]
                dataframe = pd.DataFrame(raw_values, columns=column_names)
                source_rows = [row_number for row_number, _ in rows_buffer]
                original_times = dataframe["Time"]
                times = pd.to_datetime(original_times, errors="coerce")
                missing_times = original_times.isna()
                invalid_times = times.isna() & ~missing_times
                for mask, code, message in (
                    (
                        missing_times,
                        "missing_timestamp",
                        "An electricity measurement row has no timestamp.",
                    ),
                    (
                        invalid_times,
                        "invalid_timestamp",
                        "A non-empty electricity timestamp could not be parsed.",
                    ),
                ):
                    count = int(mask.sum())
                    if count:
                        examples = [
                            {
                                "excel_row": source_rows[position],
                                "value": str(original_times.iloc[position]),
                            }
                            for position in list(mask[mask].index[:5])
                        ]
                        record_issue(
                            report,
                            severity="error",
                            code=code,
                            message=message,
                            source=source,
                            field=f"{sheet_name}.Time",
                            count=count,
                            examples=examples,
                        )
                sheet_report["invalid_timestamps"] += int(invalid_times.sum())
                dataframe["Time"] = times

                for name in column_names:
                    if name == "Time":
                        sheet_report["missing_values"][name] += int(
                            original_times.isna().sum()
                        )
                        continue
                    original = dataframe[name]
                    sheet_report["missing_values"][name] += int(original.isna().sum())
                    numeric = pd.to_numeric(original, errors="coerce")
                    formula_error_mask = (
                        original.isin(EXCEL_ERROR_VALUES)
                        if name in formula_columns
                        else pd.Series(False, index=original.index)
                    )
                    if name in formula_columns:
                        companion = f"{name}__formula_error"
                        dataframe[companion] = original.where(formula_error_mask)
                        formula_error_count = int(formula_error_mask.sum())
                        if formula_error_count:
                            sheet_report["formula_error_values"][name] = (
                                sheet_report["formula_error_values"].get(name, 0)
                                + formula_error_count
                            )
                            error_positions = list(
                                formula_error_mask[formula_error_mask].index[:5]
                            )
                            record_issue(
                                report,
                                severity="warning",
                                code="cached_formula_error",
                                message=(
                                    "An Excel formula's cached result is an error. "
                                    "The source error text is preserved in a companion "
                                    "Parquet column; the formula was not recalculated."
                                ),
                                source=source,
                                field=f"{sheet_name}.{name}",
                                count=formula_error_count,
                                examples=[
                                    {
                                        "excel_row": source_rows[position],
                                        "value": str(original.iloc[position]),
                                        "formula": formulas[name],
                                    }
                                    for position in error_positions
                                ],
                            )
                    invalid = original.notna() & numeric.isna() & ~formula_error_mask
                    non_finite = numeric.isin([float("inf"), float("-inf")])
                    invalid |= non_finite
                    if invalid.any():
                        count = int(invalid.sum())
                        sheet_report["invalid_numeric_values"][name] = (
                            sheet_report["invalid_numeric_values"].get(name, 0) + count
                        )
                        record_issue(
                            report,
                            severity="error",
                            code="invalid_numeric_value",
                            message="A non-empty electricity measurement is not a finite number.",
                            source=source,
                            field=f"{sheet_name}.{name}",
                            count=count,
                            examples=[
                                {
                                    "excel_row": source_rows[position],
                                    "value": str(original.iloc[position]),
                                }
                                for position in list(invalid[invalid].index[:5])
                            ],
                        )
                    dataframe[name] = numeric.where(~non_finite).astype("float64")

                solar_column = "SCADA/ANALOG/044MQ206/0"
                if solar_column in dataframe:
                    sheet_report["negative_raw_solar_values"] += int(
                        (dataframe[solar_column] < 0).sum()
                    )

                dataframe["_source_file"] = source
                dataframe["_source_sheet"] = sheet_name
                dataframe["_source_row"] = source_rows
                table = pa.Table.from_pandas(
                    dataframe,
                    schema=schema,
                    preserve_index=False,
                    safe=True,
                )
                writer.write_table(table)
                sheet_report["row_count"] += len(dataframe)
                rows_buffer.clear()

            for excel_row, values in measurement_rows:
                if len(values) > len(column_names) and any(
                    value is not None for value in values[len(column_names) :]
                ):
                    record_issue(
                        report,
                        severity="error",
                        code="data_beyond_header",
                        message="A measurement row contains data beyond its header columns.",
                        source=source,
                        field=sheet_name,
                        example={"excel_row": excel_row},
                    )
                row_values = tuple(values[index] if index < len(values) else None for index in range(len(column_names)))
                if not any(value is not None for value in row_values):
                    continue
                digest = _record_digest(row_values)
                if digest in seen_row_hashes:
                    sheet_report["duplicate_rows"] += 1
                    record_issue(
                        report,
                        severity="error",
                        code="duplicate_row",
                        message="An exact duplicate electricity measurement row was found.",
                        source=source,
                        field=sheet_name,
                        example={"excel_row": excel_row},
                    )
                else:
                    seen_row_hashes.add(digest)

                timestamp_value = row_values[column_names.index("Time")]
                if timestamp_value is not None:
                    timestamp = pd.to_datetime(timestamp_value, errors="coerce")
                    if not pd.isna(timestamp):
                        minimum = sheet_report["timestamp_range"]["min"]
                        maximum = sheet_report["timestamp_range"]["max"]
                        if minimum is None or timestamp < pd.Timestamp(minimum):
                            sheet_report["timestamp_range"]["min"] = timestamp.isoformat()
                        if maximum is None or timestamp > pd.Timestamp(maximum):
                            sheet_report["timestamp_range"]["max"] = timestamp.isoformat()
                        if previous_time is not None:
                            seconds = (timestamp - previous_time).total_seconds()
                            if seconds <= 0:
                                sheet_report[
                                    "duplicate_or_non_increasing_timestamps"
                                ] += 1
                                record_issue(
                                    report,
                                    severity="error",
                                    code="duplicate_or_non_increasing_timestamp",
                                    message=(
                                        "Electricity timestamps are duplicated or are "
                                        "not in increasing order."
                                    ),
                                    source=source,
                                    field=f"{sheet_name}.Time",
                                    example={"excel_row": excel_row, "seconds": seconds},
                                )
                            elif seconds > 10.1:
                                sheet_report["intervals_over_10_seconds"] += 1
                        previous_time = timestamp
                rows_buffer.append((excel_row, row_values))
                if len(rows_buffer) >= batch_size:
                    flush_rows()
                    if progress is not None:
                        progress(source, sheet_name, sheet_report["row_count"])
            flush_rows()
            if progress is not None:
                progress(source, sheet_name, sheet_report["row_count"])
        finally:
            writer.close()

        if sheet_report["negative_raw_solar_values"]:
            record_issue(
                report,
                severity="warning",
                code="negative_raw_solar_values",
                message=(
                    "The raw solar signal contains negative values. The workbook's "
                    "derived Solar column clips negative values to zero."
                ),
                source=source,
                field="SCADA/ANALOG/044MQ206/0",
                count=sheet_report["negative_raw_solar_values"],
                example={
                    "count": sheet_report["negative_raw_solar_values"],
                    "derived_formula": formulas.get("Solar"),
                },
            )
        if not sheet_report["row_count"]:
            record_issue(
                report,
                severity="error",
                code="empty_worksheet",
                message="The expected measurement worksheet contains no data rows.",
                source=source,
                field=sheet_name,
            )
        if sheet_report["intervals_over_10_seconds"]:
            record_issue(
                report,
                severity="warning",
                code="unexpected_timestamp_interval",
                message=(
                    "Some timestamps are more than 10.1 seconds apart; no rows were "
                    "aggregated or filled."
                ),
                source=source,
                field=f"{sheet_name}.Time",
                count=sheet_report["intervals_over_10_seconds"],
                example={"count": sheet_report["intervals_over_10_seconds"]},
            )
        return sheet_report["row_count"]


def process_electricity_workbooks(
    electricity_dir: Path,
    staging_dir: Path,
    report: dict[str, Any],
    *,
    batch_size: int = PARQUET_BATCH_SIZE,
    progress: Callable[[str, str, int], None] | None = None,
) -> dict[str, str]:
    """Transform all known workbook sheets into two provenance-rich Parquet files."""
    outputs = {}
    schema_report: dict[str, Any] = {
        "source_url": ELECTRICITY_SOURCE_URL,
        "formula_policy": (
            "Read cached formula results from the source workbooks; do not recalculate "
            "or replace formulas with synthetic values."
        ),
        "timestamp_policy": (
            "Preserve the original timestamp precision. No resampling, hourly "
            "aggregation, or gap filling is performed."
        ),
        "electricity_units": None,
        "workbooks": {},
    }

    for filename in ELECTRICITY_FILES:
        path = electricity_dir / filename
        workbook = load_workbook(path, read_only=True, data_only=True)
        try:
            sheet_names = list(workbook.sheetnames)
            validate_sheet_names(filename, sheet_names, report)
            config_text = None
            if "_osi_config" in workbook.sheetnames:
                config_sheet = workbook["_osi_config"]
                config_text = config_sheet.cell(row=2, column=1).value
                if config_text is not None:
                    config_text = str(config_text)
        finally:
            workbook.close()
        workbook_report: dict[str, Any] = {
            "file": filename,
            "size_bytes": path.stat().st_size,
            "source_url": ELECTRICITY_SOURCE_URL,
            "sheet_names": sheet_names,
            "osi_config_cell": config_text,
            "sheets": {},
        }
        schema_report["workbooks"][filename] = workbook_report
        for sheet_name in ("Sheet1", "Sheet2"):
            output_path = staging_dir / f"{Path(filename).stem.replace(' ', '_').lower()}_{sheet_name.lower()}.parquet"
            row_count = _write_sheet(
                path=path,
                sheet_name=sheet_name,
                output_path=output_path,
                workbook_report=workbook_report,
                report=report,
                batch_size=batch_size,
                progress=progress,
            )
            if row_count:
                outputs[str(output_path.name)] = str(output_path)

    schema_path = staging_dir / "electricity_schema.json"
    schema_path.write_text(
        json.dumps(schema_report, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    outputs[schema_path.name] = str(schema_path)
    report["electricity"] = schema_report
    return outputs
