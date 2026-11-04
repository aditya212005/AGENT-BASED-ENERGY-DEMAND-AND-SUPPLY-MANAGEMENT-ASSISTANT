"""Beginner-friendly command-line entry point for data ingestion."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from energy_assistant.config import (
    CSV_CHUNK_SIZE,
    PARQUET_BATCH_SIZE,
    PipelinePaths,
)
from energy_assistant.pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Validate the supplied energy datasets and write processed electricity "
            "time series to Parquet."
        )
    )
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parents[2],
        help="Project folder containing raw_data/ and processed/.",
    )
    parser.add_argument(
        "--csv-chunk-size",
        type=int,
        default=CSV_CHUNK_SIZE,
        help="Number of outage CSV rows read at a time (default: %(default)s).",
    )
    parser.add_argument(
        "--parquet-batch-size",
        type=int,
        default=PARQUET_BATCH_SIZE,
        help="Number of electricity rows written at a time (default: %(default)s).",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.csv_chunk_size <= 0 or args.parquet_batch_size <= 0:
        print("Chunk and batch sizes must be positive integers.", file=sys.stderr)
        return 2
    root = args.project_root.resolve()
    paths = PipelinePaths(
        project_root=root,
        electricity_dir=root / "raw_data" / "electricity_demand",
        outage_file=root / "raw_data" / "outages" / "daily_power_outage.csv",
        processed_dir=root / "processed",
    )
    try:
        report = run_pipeline(
            paths,
            csv_chunk_size=args.csv_chunk_size,
            parquet_batch_size=args.parquet_batch_size,
        )
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"Ingestion could not continue: {error}", file=sys.stderr)
        return 1

    print(f"\nPipeline status: {report['status']}")
    print(f"Outage rows checked: {report['outages']['row_count']:,}")
    if report["status"] == "success":
        print("Processed electricity files:")
        for output in report["processed_outputs"]:
            print(f"  - {output}")
    else:
        print(report.get("message", "Validation errors prevented output."))
        for issue in report["errors"]:
            print(
                f"  ERROR {issue['code']} ({issue['source']}): {issue['message']}"
            )
    for issue in report["warnings"]:
        print(
            f"  WARNING {issue['code']} ({issue['source']}): {issue['message']}"
        )
    print(f"Full validation report: {report['validation_report_path']}")
    return 0 if report["status"] == "success" else 1


if __name__ == "__main__":
    raise SystemExit(main())

