# Agent-Based Energy Demand and Supply Management Assistant

## Phase 2: data ingestion and validation

This project includes a small Python pipeline that reads the three supplied
electricity workbooks and checks the large outage CSV without copying it.
Original files in `raw_data/` are never edited.

### 1. Install the required Python packages

From the project folder, run:

```powershell
python -m pip install -r requirements.txt
```

### 2. Run the pipeline

```powershell
python scripts/run_ingestion.py
```

The script prints progress as it reads workbook batches and CSV chunks. To
change the amount of data handled at once, use `--csv-chunk-size` or
`--parquet-batch-size`:

```powershell
python scripts/run_ingestion.py --csv-chunk-size 50000 --parquet-batch-size 10000
```

### 3. Check the results

- `processed/electricity/` contains one Parquet file per workbook sheet. Parquet
  stores timestamps and numbers compactly and is faster to read than repeatedly
  parsing the original Excel files.
- `processed/reports/electricity_schema.json` records how the two header rows
  were interpreted, original labels, formula expressions, and source filenames.
- `processed/reports/validation_report.json` records missing values, invalid
  values, duplicate checks, date ranges, and any warnings or errors.

The large `daily_power_outage.csv` is validated in chunks and remains in
`raw_data/outages/`; the pipeline does **not** make another processed copy of
that file. It preserves empty fields and the literal text `None` as distinct
values. If validation finds errors, the report is saved and staged Parquet
outputs are not published.

The electricity workbooks contain 10-second observations despite the Mendeley
title describing hourly data. The pipeline preserves those timestamps and does
not aggregate, fill gaps, recalculate formulas, or invent electricity units.
Cached formula results are read from the workbooks and formula expressions are
recorded for provenance. Raw signal IDs are retained; blank header cells use
their descriptive label when available, otherwise they receive an explicit
`unlabeled_column_*` name documented in the schema report.

Excel formula error values are not recalculated or hidden. They are reported
and preserved in a corresponding `__formula_error` string column in the
Parquet output, while the numeric value column remains null for those cells.

### Run the tests

```powershell
python -m unittest discover -s tests -v
```

## Phase 3: Streamlit dashboard

After running the ingestion pipeline, launch the dashboard from the project
folder:

```powershell
python -m pip install -r requirements.txt
streamlit run app.py
```

The dashboard reads electricity values from `processed/electricity/` and the
validation/schema reports from `processed/reports/`. It visualizes the actual
`SCADA/ANALOG/044MQ067/0` demand signal, `SCADA/ANALOG/044MQ070/0` wind signal,
`SCADA/ANALOG/044MQ206/0` raw solar signal, and the formula-derived `Solar`
column. Electricity units are **not specified in the source**. The dashboard
preserves the source timestamps and does not aggregate readings; for chart
performance it may show evenly spaced source rows, with this display sampling
identified in the interface.

The outage tab summarizes the original CSV in chunks and caches the result
between reruns. It uses the CSV's `date`, `region`, `station_type`,
`power_station`, and `outage_type` fields. The outage and electricity datasets
are shown separately; the dashboard does not infer a causal relationship.
Formula-error text is retained in the explorer and flagged on the electricity
tab rather than treated as a measurement. The raw datasets are never modified.