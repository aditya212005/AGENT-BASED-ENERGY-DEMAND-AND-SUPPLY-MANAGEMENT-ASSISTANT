"""Command-line ingestion workflow and output publication."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from energy_assistant.config import (
    CSV_CHUNK_SIZE,
    ELECTRICITY_FILES,
    ELECTRICITY_SOURCE_URL,
    OUTAGE_SOURCE_URL,
    PipelinePaths,
)
from energy_assistant.preprocessing import process_electricity_workbooks
from energy_assistant.validation import (
    check_required_files,
    new_validation_report,
    validate_outage_csv,
)


ProgressCallback = Callable[[str], None]


def _write_json(path: Path, content: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(content, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def run_pipeline(
    paths: PipelinePaths = PipelinePaths(),
    *,
    csv_chunk_size: int = CSV_CHUNK_SIZE,
    parquet_batch_size: int = 25_000,
    progress: ProgressCallback | None = print,
) -> dict[str, Any]:
    """Validate sources and create Parquet outputs for the electricity workbooks.

    The outage CSV is audited directly in chunks and is never copied to the
    processed directory.
    """
    sources = check_required_files(
        paths.electricity_dir,
        ELECTRICITY_FILES,
        paths.outage_file,
    )
    paths.processed_dir.mkdir(parents=True, exist_ok=True)
    report = new_validation_report()
    report["sources"] = [
        {
            "path": str(source.relative_to(paths.project_root))
            if source.is_relative_to(paths.project_root)
            else str(source),
            "size_bytes": source.stat().st_size,
            "source_url": (
                ELECTRICITY_SOURCE_URL
                if source.suffix.lower() == ".xlsx"
                else OUTAGE_SOURCE_URL
            ),
        }
        for source in sources
    ]

    with tempfile.TemporaryDirectory(
        prefix="ingestion-staging-",
        dir=paths.processed_dir,
    ) as temporary_directory:
        staging_dir = Path(temporary_directory)

        def workbook_progress(filename: str, sheet: str, count: int) -> None:
            if progress is not None:
                progress(f"Read {filename} / {sheet}: {count:,} rows")

        staged_outputs = process_electricity_workbooks(
            paths.electricity_dir,
            staging_dir,
            report,
            batch_size=parquet_batch_size,
            progress=workbook_progress,
        )

        def outage_progress(row_count: int, chunk_number: int) -> None:
            if progress is not None:
                progress(
                    f"Validated outage CSV: {row_count:,} rows "
                    f"(chunk {chunk_number})"
                )

        validate_outage_csv(
            paths.outage_file,
            report,
            chunk_size=csv_chunk_size,
            progress=outage_progress,
        )

        report["finished_at"] = datetime.now().astimezone().isoformat()
        report["status"] = "failed" if report["errors"] else "success"
        report["processed_outputs"] = []

        if report["status"] == "success":
            electricity_output_dir = paths.processed_dir / "electricity"
            report_output_dir = paths.processed_dir / "reports"
            electricity_output_dir.mkdir(parents=True, exist_ok=True)
            report_output_dir.mkdir(parents=True, exist_ok=True)
            for name, staged_path in staged_outputs.items():
                target_dir = (
                    report_output_dir
                    if name.endswith("_schema.json")
                    else electricity_output_dir
                )
                target = target_dir / name
                os.replace(staged_path, target)
                report["processed_outputs"].append(
                    str(target.relative_to(paths.project_root))
                    if target.is_relative_to(paths.project_root)
                    else str(target)
                )
        else:
            report["message"] = (
                "Validation found errors. No staged Parquet files were published; "
                "the original datasets remain unchanged."
            )

    report_path = paths.processed_dir / "reports" / "validation_report.json"
    report["validation_report_path"] = str(report_path)
    _write_json(report_path, report)
    return report
