"""Streamlit dashboard for the supplied energy and outage datasets."""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from energy_assistant.dashboard_data import (  # noqa: E402
    DEMAND_COLUMN,
    DERIVED_SOLAR_COLUMN,
    ELECTRICITY_LABELS,
    RAW_SOLAR_COLUMN,
    TIME_COLUMN,
    WIND_COLUMN,
    evenly_sample_for_chart,
    load_electricity_month,
    load_parquet_sample,
    summarize_outage_csv,
)

ELECTRICITY_DIR = PROJECT_ROOT / "processed" / "electricity"
REPORT_DIR = PROJECT_ROOT / "processed" / "reports"
VALIDATION_REPORT = REPORT_DIR / "validation_report.json"
SCHEMA_REPORT = REPORT_DIR / "electricity_schema.json"
OUTAGE_FILE = PROJECT_ROOT / "raw_data" / "outages" / "daily_power_outage.csv"
MONTH_FILES = {
    "March 2023": ELECTRICITY_DIR / "march_2023_sheet1.parquet",
    "May 2023": ELECTRICITY_DIR / "may_2023_sheet1.parquet",
    "October 2023": ELECTRICITY_DIR / "october_2023_sheet1.parquet",
}
EXPLORER_FILES = {
    **MONTH_FILES,
    "March 2023 — Sheet2": ELECTRICITY_DIR / "march_2023_sheet2.parquet",
    "May 2023 — Sheet2": ELECTRICITY_DIR / "may_2023_sheet2.parquet",
    "October 2023 — Sheet2": ELECTRICITY_DIR / "october_2023_sheet2.parquet",
}

st.set_page_config(
    page_title="Energy Demand & Supply Assistant",
    page_icon="⚡",
    layout="wide",
)


@st.cache_data(show_spinner="Loading selected electricity records...")
def cached_electricity_month(path: str, modified_time: float) -> pd.DataFrame:
    del modified_time
    return load_electricity_month(Path(path))


@st.cache_data(show_spinner="Summarizing outage records in chunks...")
def cached_outage_summary(path: str, modified_time: float) -> dict[str, Any]:
    del modified_time
    return summarize_outage_csv(Path(path))


@st.cache_data(show_spinner=False)
def cached_parquet_sample(
    path: str,
    modified_time: float,
    row_count: int,
) -> pd.DataFrame:
    del modified_time
    return load_parquet_sample(Path(path), row_count=row_count)


@st.cache_data(show_spinner=False)
def cached_outage_sample(
    path: str,
    modified_time: float,
    row_count: int,
) -> pd.DataFrame:
    del modified_time
    if not Path(path).is_file():
        raise FileNotFoundError(f"Outage CSV not found: {path}")
    return pd.read_csv(
        path,
        nrows=row_count,
        dtype=str,
        keep_default_na=False,
        na_filter=False,
        encoding="utf-8-sig",
        on_bad_lines="error",
    )


def _file_mtime(path: Path) -> float:
    return path.stat().st_mtime


def _load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(f"Required report not found: {path}")
    with path.open(encoding="utf-8") as file:
        report = json.load(file)
    if not isinstance(report, dict):
        raise ValueError(f"Expected a JSON object in {path}")
    return report


def _units_label(schema: dict[str, Any]) -> str:
    units = schema.get("electricity_units")
    if not units or str(units).strip().lower() in {"unknown", "not specified"}:
        return "Units not specified in source"
    return str(units)


def _select_date_range(
    selected_months: list[str],
    month_frames: list[pd.DataFrame],
) -> tuple[date, date] | None:
    timestamps = pd.concat(
        [frame[TIME_COLUMN].dropna() for frame in month_frames],
        ignore_index=True,
    )
    if timestamps.empty:
        return None
    minimum = timestamps.min().date()
    maximum = timestamps.max().date()
    selection = st.sidebar.date_input(
        "Electricity date range",
        value=(minimum, maximum),
        min_value=minimum,
        max_value=maximum,
        key=f"date-range-{','.join(selected_months)}",
    )
    if isinstance(selection, tuple) and len(selection) == 2:
        return selection[0], selection[1]
    return None


def _filtered_electricity(
    month_frames: list[pd.DataFrame],
    date_range: tuple[date, date] | None,
) -> pd.DataFrame:
    combined = pd.concat(month_frames, ignore_index=True).sort_values(TIME_COLUMN)
    combined = combined.dropna(subset=[TIME_COLUMN])
    if date_range is not None:
        start, end = date_range
        combined = combined.loc[
            combined[TIME_COLUMN].dt.date.between(start, end)
        ]
    return combined


def _display_formula_warnings(report: dict[str, Any]) -> None:
    formula_warnings = [
        warning
        for warning in report.get("warnings", [])
        if warning.get("code") == "cached_formula_error"
    ]
    solar_warnings = [
        warning
        for warning in report.get("warnings", [])
        if warning.get("code") == "negative_raw_solar_values"
    ]
    for warning in formula_warnings:
        st.warning(
            f"{warning.get('source')}: cached formula errors in "
            f"{warning.get('field')} ({warning.get('count', 0):,} cells). "
            "The affected numeric readings are not plotted; the error text "
            "remains in the processed data."
        )
    for warning in solar_warnings:
        st.warning(
            f"{warning.get('source')}: {warning.get('count', 0):,} negative "
            "values were found in the raw solar signal. Raw readings are "
            "shown as stored, without clipping."
        )


def _show_overview(
    validation: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    st.subheader("Project overview")
    st.write(
        "Explore the supplied electricity demand and generation signals alongside "
        "the separate power-station outage dataset. No causal link between these "
        "datasets is established by the available data."
    )
    st.info(
        f"Electricity values: **{_units_label(schema)}**. "
        "Timestamps are kept at their source 10-second cadence; charts may select "
        "evenly spaced rows for display but do not aggregate readings."
    )

    electricity = validation.get("electricity", {})
    outages = validation.get("outages", {})
    workbook_count = len(electricity.get("workbooks", {}))
    metric_columns = st.columns(3)
    metric_columns[0].metric("Electricity workbooks", workbook_count)
    metric_columns[1].metric(
        "Outage records checked",
        f"{outages.get('row_count', 0):,}",
    )
    metric_columns[2].metric("Validation status", validation.get("status", "Unknown"))

    st.markdown("#### Data sources")
    st.markdown(
        f"- Electricity: [Mendeley dataset]({electricity.get('source_url', '')})"
    )
    outage_source = next(
        (
            source
            for source in validation.get("sources", [])
            if source.get("path", "").replace("\\", "/").endswith(
                "raw_data/outages/daily_power_outage.csv"
            )
        ),
        {},
    )
    outage_url = outage_source.get("source_url", "")
    st.markdown(f"- Outages: [India Data Portal resource]({outage_url})")
    st.caption(
        "The outage records and electricity time series are shown separately. "
        "This dashboard does not claim that outage records caused demand changes."
    )

    with st.expander("Validation details", expanded=False):
        st.write(
            f"Exact duplicate outage rows: "
            f"{outages.get('duplicate_rows', 'Not reported'):,}"
            if isinstance(outages.get("duplicate_rows"), int)
            else f"Exact duplicate outage rows: {outages.get('duplicate_rows', 'Not reported')}"
        )
        st.write(
            f"Duplicate outage IDs: "
            f"{outages.get('duplicate_ids', 'Not reported'):,}"
            if isinstance(outages.get("duplicate_ids"), int)
            else f"Duplicate outage IDs: {outages.get('duplicate_ids', 'Not reported')}"
        )
        st.json(
            {
                "errors": validation.get("errors", []),
                "warnings": validation.get("warnings", []),
                "electricity_date_ranges": electricity.get("date_ranges", {}),
                "outage_date_ranges": outages.get("date_ranges", {}),
                "outage_missing_values": outages.get("missing_values", {}),
            },
            expanded=False,
        )
        st.markdown("**Workbook schemas and metadata**")
        workbook_rows = []
        for name, metadata in electricity.get("workbooks", {}).items():
            workbook_rows.append(
                {
                    "Workbook": name,
                    "Sheets": ", ".join(metadata.get("sheet_names", [])),
                    "Size (bytes)": metadata.get("size_bytes"),
                    "Sheet1 rows": metadata.get("sheets", {})
                    .get("Sheet1", {})
                    .get("row_count"),
                }
            )
        if workbook_rows:
            st.dataframe(
                pd.DataFrame(workbook_rows),
                width="stretch",
                hide_index=True,
            )


def _show_electricity(
    validation: dict[str, Any],
    schema: dict[str, Any],
) -> None:
    st.subheader("Electricity demand and generation")
    selected_months = st.sidebar.multiselect(
        "Electricity months",
        options=list(MONTH_FILES),
        default=list(MONTH_FILES),
    )
    if not selected_months:
        st.info("Select at least one month to view electricity readings.")
        return

    missing_paths = [MONTH_FILES[month] for month in selected_months if not MONTH_FILES[month].is_file()]
    if missing_paths:
        st.error(
            "Processed electricity data is missing. Run "
            "`python scripts/run_ingestion.py` first. Missing: "
            + ", ".join(str(path.relative_to(PROJECT_ROOT)) for path in missing_paths)
        )
        return

    month_frames = [
        cached_electricity_month(str(MONTH_FILES[month]), _file_mtime(MONTH_FILES[month]))
        for month in selected_months
    ]
    date_range = _select_date_range(selected_months, month_frames)
    readings = _filtered_electricity(month_frames, date_range)
    if readings.empty:
        st.info("No electricity readings are available for this date selection.")
        return

    chart_readings = evenly_sample_for_chart(readings)
    if len(chart_readings) < len(readings):
        st.caption(
            f"Showing {len(chart_readings):,} evenly spaced source rows from "
            f"{len(readings):,} selected readings for chart performance. "
            "This is display sampling, not aggregation."
        )
    st.caption(
        "All electricity chart axes use source values. "
        f"{_units_label(schema)}."
    )
    demand = chart_readings[[TIME_COLUMN, DEMAND_COLUMN]].dropna(
        subset=[DEMAND_COLUMN]
    )
    st.markdown(f"#### Demand — {ELECTRICITY_LABELS[DEMAND_COLUMN]}")
    if demand.empty:
        st.info("No valid demand values are available in this selection.")
    else:
        st.line_chart(
            demand,
            x=TIME_COLUMN,
            y=DEMAND_COLUMN,
            x_label="Timestamp",
            y_label=_units_label(schema),
            width="stretch",
        )

    signal_options = [WIND_COLUMN, RAW_SOLAR_COLUMN, DERIVED_SOLAR_COLUMN]
    selected_signals = st.multiselect(
        "Generation signals",
        options=signal_options,
        default=signal_options,
        format_func=lambda column: ELECTRICITY_LABELS[column],
    )
    if selected_signals:
        signals = chart_readings[[TIME_COLUMN, *selected_signals]].dropna(
            subset=selected_signals,
            how="all",
        )
        st.markdown("#### Available wind and solar signals")
        if signals.empty:
            st.info("No valid generation values are available in this selection.")
        else:
            st.line_chart(
                signals,
                x=TIME_COLUMN,
                y=selected_signals,
                x_label="Timestamp",
                y_label=_units_label(schema),
                width="stretch",
            )
    _display_formula_warnings(validation)


def _show_outages(validation: dict[str, Any]) -> None:
    st.subheader("Power-station outage dataset")
    st.caption(
        "This is a separate dataset. Its records are not joined to the electricity "
        "time series and are not evidence of demand changes caused by outages."
    )
    metadata = validation.get("outages", {})
    metrics = st.columns(4)
    metrics[0].metric("Records validated", f"{metadata.get('row_count', 0):,}")
    metrics[1].metric(
        "Reporting date starts",
        metadata.get("date_ranges", {}).get("date", {}).get("min", "Not reported"),
    )
    metrics[2].metric(
        "Reporting date ends",
        metadata.get("date_ranges", {}).get("date", {}).get("max", "Not reported"),
    )
    metrics[3].metric(
        "Duplicate rows",
        f"{metadata.get('duplicate_rows', 0):,}",
    )

    if metadata.get("missing_values"):
        missing = pd.DataFrame(
            [
                {"Source column": column, "Missing records": count}
                for column, count in metadata["missing_values"].items()
            ]
        ).sort_values("Missing records", ascending=False)
        st.markdown("#### Missing values reported by validation")
        st.dataframe(missing, width="stretch", hide_index=True)

    if not OUTAGE_FILE.is_file():
        st.warning(
            "The validated CSV is not available at "
            f"`{OUTAGE_FILE.relative_to(PROJECT_ROOT)}`. "
            "The report metadata above is still available."
        )
        return

    try:
        summary = cached_outage_summary(str(OUTAGE_FILE), _file_mtime(OUTAGE_FILE))
    except (OSError, ValueError, pd.errors.ParserError) as error:
        st.error(f"Could not summarize the outage CSV: {error}")
        return

    st.markdown("#### Reporting records by month")
    monthly = pd.DataFrame(summary["monthly_records"])
    if monthly.empty:
        st.info("No valid reporting dates were found in the outage CSV.")
    else:
        monthly["month"] = pd.to_datetime(monthly["month"], format="%Y-%m")
        st.bar_chart(
            monthly,
            x="month",
            y="records",
            x_label="Reporting month (`date`)",
            y_label="Outage records",
            width="stretch",
        )
    if summary["invalid_reporting_dates"]:
        st.warning(
            f"{summary['invalid_reporting_dates']:,} reporting dates could not "
            "be parsed in the chunked summary."
        )

    category_columns = st.columns(2)
    for column, title, key in (
        (category_columns[0], "Records by region", "regions"),
        (category_columns[1], "Records by station type", "station_types"),
        (category_columns[0], "Records by outage type", "outage_types"),
        (category_columns[1], "Most frequent power-station names", "power_stations"),
    ):
        with column:
            st.markdown(f"#### {title}")
            category_frame = pd.DataFrame(summary[key])
            if category_frame.empty:
                st.info("No category values are available.")
            else:
                st.bar_chart(
                    category_frame.set_index("category"),
                    y="records",
                    x_label="Category",
                    y_label="Records",
                    width="stretch",
                )
    st.info(
        "The outage CSV has no explicit outage-duration field. "
        "The fields `outage_date` and `expected_sync_date` are reported as source "
        "dates and are not interpreted as actual duration."
    )


def _show_explorer(validation: dict[str, Any]) -> None:
    st.subheader("Dataset explorer")
    dataset_name = st.selectbox("Dataset", list(EXPLORER_FILES) + ["Outage CSV"])
    row_count = st.selectbox("Sample rows", [5, 20, 50, 100], index=1)
    if dataset_name == "Outage CSV":
        if not OUTAGE_FILE.is_file():
            st.error(f"Outage CSV not found: {OUTAGE_FILE}")
            return
        try:
            sample = cached_outage_sample(
                str(OUTAGE_FILE),
                _file_mtime(OUTAGE_FILE),
                row_count,
            )
        except (OSError, ValueError, pd.errors.ParserError) as error:
            st.error(f"Could not read the outage CSV sample: {error}")
            return
        st.caption(
            f"Showing the first {len(sample):,} source records from "
            f"{validation.get('outages', {}).get('row_count', 0):,} validated rows."
        )
    else:
        parquet_path = EXPLORER_FILES[dataset_name]
        if not parquet_path.is_file():
            st.error(
                f"Processed dataset not found: "
                f"`{parquet_path.relative_to(PROJECT_ROOT)}`. "
                "Run `python scripts/run_ingestion.py` first."
            )
            return
        sample = cached_parquet_sample(
            str(parquet_path),
            _file_mtime(parquet_path),
            row_count,
        )
        st.caption(
            f"Showing the first {len(sample):,} source rows from "
            f"`{parquet_path.relative_to(PROJECT_ROOT)}`. "
            "Formula error companion columns are retained where present."
        )
    st.dataframe(sample, width="stretch", hide_index=True)


def main() -> None:
    st.title("⚡ Energy Demand & Supply Assistant")
    st.caption("Phase 3: an interactive view of the supplied real datasets")
    try:
        validation = _load_json(VALIDATION_REPORT)
        schema = _load_json(SCHEMA_REPORT)
    except (OSError, json.JSONDecodeError, ValueError) as error:
        st.error(
            f"Could not load the Phase 2 reports: {error}. "
            "Run the ingestion pipeline and check `processed/reports/`."
        )
        st.stop()

    section = st.sidebar.radio(
        "Dashboard section",
        ["Overview", "Electricity", "Outages", "Dataset explorer"],
    )
    if section == "Overview":
        _show_overview(validation, schema)
    elif section == "Electricity":
        _show_electricity(validation, schema)
    elif section == "Outages":
        _show_outages(validation)
    else:
        _show_explorer(validation)


if __name__ == "__main__":
    main()
