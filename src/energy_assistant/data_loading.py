"""Memory-conscious readers for the supplied Excel and CSV datasets."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pandas as pd
from openpyxl import load_workbook

from energy_assistant.config import CSV_CHUNK_SIZE, ELECTRICITY_LABEL_ALIASES


def _column_letter(index: int) -> str:
    """Return an Excel column name for a zero-based index."""
    result = ""
    number = index + 1
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def _normalize_label(label: Any) -> str | None:
    if label is None:
        return None
    text = str(label).strip()
    if not text:
        return None
    return ELECTRICITY_LABEL_ALIASES.get(text, text)


def _column_mapping(
    raw_headers: tuple[Any, ...],
    labels: tuple[Any, ...],
) -> list[dict[str, Any]]:
    mapping = []
    for index in range(max(len(raw_headers), len(labels))):
        raw_header = raw_headers[index] if index < len(raw_headers) else None
        label = labels[index] if index < len(labels) else None
        raw_header = str(raw_header).strip() if raw_header is not None else ""
        label = str(label).strip() if label is not None else ""
        if raw_header:
            output_name = raw_header
            naming_rule = "raw_header"
        elif label:
            output_name = _normalize_label(label)
            naming_rule = "descriptive_label_for_blank_header"
        else:
            output_name = f"unlabeled_column_{_column_letter(index)}"
            naming_rule = "explicit_unlabeled_column_name"
        mapping.append(
            {
                "excel_column": _column_letter(index),
                "output_name": output_name,
                "raw_header": raw_header or None,
                "descriptive_label": label or None,
                "naming_rule": naming_rule,
            }
        )
    names = [entry["output_name"] for entry in mapping]
    if len(names) != len(set(names)):
        raise ValueError(f"Workbook columns do not have unique output names: {names}")
    return mapping


def _formula_metadata(path: Path, sheet_name: str) -> dict[str, str]:
    """Read formulas from the first measurement row without recalculating them."""
    workbook = load_workbook(path, read_only=True, data_only=False)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Required worksheet {sheet_name!r} is missing from {path.name}")
        worksheet = workbook[sheet_name]
        rows = worksheet.iter_rows(min_row=1, max_row=3, values_only=False)
        header_rows = [next(rows, ()), next(rows, ())]
        formula_row = next(rows, ())
        mapping = _column_mapping(
            tuple(cell.value for cell in header_rows[0]),
            tuple(cell.value for cell in header_rows[1]),
        )
        return {
            mapping[index]["output_name"]: str(cell.value)
            for index, cell in enumerate(formula_row)
            if cell.data_type == "f" and index < len(mapping)
        }
    finally:
        workbook.close()


@contextmanager
def open_electricity_sheet(
    path: Path,
    sheet_name: str,
) -> Iterator[tuple[list[dict[str, Any]], Iterator[tuple[int, tuple[Any, ...]]], dict[str, str]]]:
    """Open one worksheet read-only and yield its mapping and measurement rows.

    Formula cells are read with ``data_only=True`` for their saved cached values.
    Formulas themselves are inspected separately and recorded as provenance;
    this pipeline does not recalculate spreadsheet formulas.
    """
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if sheet_name not in workbook.sheetnames:
            raise ValueError(f"Required worksheet {sheet_name!r} is missing from {path.name}")
        worksheet = workbook[sheet_name]
        if worksheet.max_column is None or worksheet.max_column < 1:
            raise ValueError(f"Worksheet {sheet_name!r} in {path.name} is empty")
        header_rows = list(
            worksheet.iter_rows(min_row=1, max_row=2, values_only=True)
        )
        if len(header_rows) < 2:
            raise ValueError(f"Worksheet {sheet_name!r} in {path.name} has no label row")
        mapping = _column_mapping(header_rows[0], header_rows[1])
        formulas = _formula_metadata(path, sheet_name)

        def measurements() -> Iterator[tuple[int, tuple[Any, ...]]]:
            for excel_row, values in enumerate(
                worksheet.iter_rows(
                    min_row=3,
                    max_col=worksheet.max_column,
                    values_only=True,
                ),
                start=3,
            ):
                yield excel_row, tuple(values)

        yield mapping, measurements(), formulas
    finally:
        workbook.close()


def iter_csv_chunks(
    path: Path,
    chunk_size: int = CSV_CHUNK_SIZE,
) -> Iterator[pd.DataFrame]:
    """Yield outage CSV chunks as strings, preserving blanks and literal ``None``."""
    yield from pd.read_csv(
        path,
        chunksize=chunk_size,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        encoding="utf-8-sig",
        on_bad_lines="error",
    )


def _row_digest(values: tuple[Any, ...]) -> bytes:
    encoded = json.dumps(values, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.blake2b(encoded, digest_size=16).digest()


@contextmanager
def temporary_duplicate_index() -> Iterator[sqlite3.Connection]:
    """Provide disk-backed exact-row and ID indexes without retaining them in RAM."""
    with tempfile.TemporaryDirectory(prefix="energy-ingestion-") as directory:
        connection = sqlite3.connect(Path(directory) / "duplicates.sqlite3")
        try:
            connection.execute("PRAGMA journal_mode=OFF")
            connection.execute("PRAGMA synchronous=OFF")
            connection.execute(
                "CREATE TABLE rows (digest BLOB PRIMARY KEY) WITHOUT ROWID"
            )
            connection.execute("CREATE TABLE ids (value TEXT PRIMARY KEY) WITHOUT ROWID")
            yield connection
        finally:
            connection.close()


def update_duplicate_counts(
    connection: sqlite3.Connection,
    records: list[tuple[str, ...]],
    *,
    id_index: int | None = 0,
) -> tuple[int, int]:
    """Add records to disk-backed indexes and return row and ID duplicate counts."""
    row_hashes = [(_row_digest(record),) for record in records]
    before = connection.total_changes
    connection.executemany("INSERT OR IGNORE INTO rows VALUES (?)", row_hashes)
    duplicate_rows = len(records) - (connection.total_changes - before)

    duplicate_ids = 0
    if id_index is not None:
        ids = [(record[id_index],) for record in records]
        before = connection.total_changes
        connection.executemany("INSERT OR IGNORE INTO ids VALUES (?)", ids)
        duplicate_ids = len(ids) - (connection.total_changes - before)
    connection.commit()
    return duplicate_rows, duplicate_ids
