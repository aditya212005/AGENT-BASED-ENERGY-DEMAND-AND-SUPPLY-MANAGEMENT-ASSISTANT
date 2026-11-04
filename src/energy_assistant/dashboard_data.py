"""Memory-conscious data access helpers for the Streamlit dashboard."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

import pandas as pd
import pyarrow.parquet as pq

TIME_COLUMN = "Time"
DEMAND_COLUMN = "SCADA/ANALOG/044MQ067/0"
WIND_COLUMN = "SCADA/ANALOG/044MQ070/0"
RAW_SOLAR_COLUMN = "SCADA/ANALOG/044MQ206/0"
DERIVED_SOLAR_COLUMN = "Solar"
ELECTRICITY_COLUMNS = (
    TIME_COLUMN,
    DEMAND_COLUMN,
    WIND_COLUMN,
    RAW_SOLAR_COLUMN,
    DERIVED_SOLAR_COLUMN,
    "Solar__formula_error",
)
ELECTRICITY_LABELS = {
    DEMAND_COLUMN: "NLDC demand (SCADA/ANALOG/044MQ067/0)",
    WIND_COLUMN: "ALL_INDIA_WIND|P (SCADA/ANALOG/044MQ070/0)",
    RAW_SOLAR_COLUMN: "ALL_IND_SOLAR|P (raw SCADA/ANALOG/044MQ206/0)",
    DERIVED_SOLAR_COLUMN: "Solar (formula-derived)",
}
OUTAGE_SUMMARY_COLUMNS = (
    "date",
    "region",
    "state_name",
    "station_type",
    "power_station",
    "outage_type",
)


def load_electricity_month(path: Path) -> pd.DataFrame:
    """Load only the confirmed dashboard signals from one Sheet1 Parquet file."""
    if not path.is_file():
        raise FileNotFoundError(f"Processed electricity file not found: {path}")

    available_columns = set(pq.read_schema(path).names)
    required_columns = set(ELECTRICITY_COLUMNS[:5])
    missing_columns = required_columns - available_columns
    if missing_columns:
        raise ValueError(
            f"{path.name} is missing expected source columns: "
            f"{', '.join(sorted(missing_columns))}"
        )

    columns = [
        column for column in ELECTRICITY_COLUMNS if column in available_columns
    ]
    frame = pd.read_parquet(path, columns=columns)
    frame[TIME_COLUMN] = pd.to_datetime(frame[TIME_COLUMN], errors="coerce")

    for column in columns:
        if column == TIME_COLUMN or column.endswith("__formula_error"):
            continue
        frame[column] = pd.to_numeric(frame[column], errors="coerce")

    error_column = f"{DERIVED_SOLAR_COLUMN}__formula_error"
    if error_column in frame.columns:
        has_formula_error = frame[error_column].fillna("").ne("")
        frame.loc[has_formula_error, DERIVED_SOLAR_COLUMN] = pd.NA

    return frame


def load_parquet_sample(path: Path, row_count: int = 100) -> pd.DataFrame:
    """Read a small leading sample without materializing an entire Parquet file."""
    if row_count < 1:
        raise ValueError("row_count must be at least 1")
    if not path.is_file():
        raise FileNotFoundError(f"Processed electricity file not found: {path}")

    parquet_file = pq.ParquetFile(path)
    batches = parquet_file.iter_batches(batch_size=row_count)
    first_batch = next(batches, None)
    if first_batch is None:
        return pd.DataFrame(columns=parquet_file.schema_arrow.names)
    return first_batch.to_pandas()


def _category_counts(counter: Counter[str]) -> list[dict[str, Any]]:
    return [
        {"category": category, "records": count}
        for category, count in sorted(
            counter.items(),
            key=lambda item: (-item[1], item[0]),
        )[:15]
    ]


def summarize_outage_csv(
    path: Path,
    *,
    chunk_size: int = 100_000,
) -> dict[str, Any]:
    """Aggregate outage CSV categories and reporting dates in bounded chunks."""
    if not path.is_file():
        raise FileNotFoundError(f"Outage CSV not found: {path}")
    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")

    region_counts: Counter[str] = Counter()
    station_type_counts: Counter[str] = Counter()
    outage_type_counts: Counter[str] = Counter()
    power_station_counts: Counter[str] = Counter()
    monthly_counts: Counter[str] = Counter()
    minimum_date: pd.Timestamp | None = None
    maximum_date: pd.Timestamp | None = None
    invalid_reporting_dates = 0
    row_count = 0

    for chunk in pd.read_csv(
        path,
        usecols=list(OUTAGE_SUMMARY_COLUMNS),
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        encoding="utf-8-sig",
        on_bad_lines="error",
        chunksize=chunk_size,
    ):
        row_count += len(chunk)
        for column, counter in (
            ("region", region_counts),
            ("station_type", station_type_counts),
            ("outage_type", outage_type_counts),
            ("power_station", power_station_counts),
        ):
            values = chunk[column].where(chunk[column].ne(""), "(blank)")
            counter.update(values.value_counts(dropna=False).to_dict())

        reporting_dates = pd.to_datetime(chunk["date"], errors="coerce")
        invalid_reporting_dates += int(reporting_dates.isna().sum())
        valid_dates = reporting_dates.dropna()
        if not valid_dates.empty:
            chunk_min = valid_dates.min()
            chunk_max = valid_dates.max()
            minimum_date = chunk_min if minimum_date is None else min(minimum_date, chunk_min)
            maximum_date = chunk_max if maximum_date is None else max(maximum_date, chunk_max)
            monthly_counts.update(
                valid_dates.dt.strftime("%Y-%m").value_counts().to_dict()
            )

    return {
        "row_count": row_count,
        "reporting_date_min": (
            minimum_date.date().isoformat() if minimum_date is not None else None
        ),
        "reporting_date_max": (
            maximum_date.date().isoformat() if maximum_date is not None else None
        ),
        "invalid_reporting_dates": invalid_reporting_dates,
        "monthly_records": [
            {"month": month, "records": count}
            for month, count in sorted(monthly_counts.items())
        ],
        "regions": _category_counts(region_counts),
        "station_types": _category_counts(station_type_counts),
        "outage_types": _category_counts(outage_type_counts),
        "power_stations": _category_counts(power_station_counts),
    }


def evenly_sample_for_chart(
    frame: pd.DataFrame,
    *,
    max_points: int = 12_000,
) -> pd.DataFrame:
    """Select evenly spaced source rows for display without aggregating them."""
    if max_points < 1:
        raise ValueError("max_points must be at least 1")
    if len(frame) <= max_points:
        return frame
    stride = (len(frame) + max_points - 1) // max_points
    return frame.iloc[::stride].head(max_points)
