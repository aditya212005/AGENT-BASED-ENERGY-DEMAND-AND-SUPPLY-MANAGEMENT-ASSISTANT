# Dataset Inspection Summary

## What was inspected

All four files in `raw_data/` were read without changing them. The workbooks were inspected sheet by sheet, including their raw header row, the following descriptive-label row, formula cells, cached values, and timestamps. The outage CSV was read one record at a time; it was not loaded all at once.

This report distinguishes **confirmed** observations from **interpretations**. A column label or plausible meaning is not treated as proof of a unit or calculation definition.

## Source files

| Dataset | Local filename | Size | Official source |
|---|---|---:|---|
| Electricity demand, solar and wind generation | `March 2023.xlsx` | 49,484,787 bytes (47.19 MiB) | [Mendeley Data dataset page](https://data.mendeley.com/datasets/y58jknpgs8/1) |
| Electricity demand, solar and wind generation | `May 2023.xlsx` | 48,850,493 bytes (46.59 MiB) | [Mendeley Data dataset page](https://data.mendeley.com/datasets/y58jknpgs8/1) |
| Electricity demand, solar and wind generation | `October 2023.xlsx` | 49,491,582 bytes (47.20 MiB) | [Mendeley Data dataset page](https://data.mendeley.com/datasets/y58jknpgs8/1) |
| Daily power outage | `daily_power_outage.csv` | 296,742,548 bytes (283.00 MiB) | [India Data Portal resource page](https://ckandev.indiadataportal.com/dataset/power/resource/abd6d0f5-b948-4c2e-9ca8-459721ee888d); [official CSV download URL](https://ckandev.indiadataportal.com/dataset/6b0ff86f-1a92-40a6-93fa-086be0334c8e/resource/abd6d0f5-b948-4c2e-9ca8-459721ee888d/download/daily_power_outage.csv) |

The Mendeley page describes a dataset spanning September 2021–December 2023. Only the three local monthly workbooks listed above were inspected; their observed dates are in 2023. The India Data Portal identifies the CSV as daily power-outage data and lists a 2017–2024 coverage period.

## Electricity workbooks

### Sheets and structure

Each workbook has the same three sheet names:

1. `_osi_config` — exporter configuration/metadata, not a time-series measurement table. It contains a JSON-like configuration cell and signal/tag names.
2. `Sheet1` — main time-series sheet. Row 1 contains `Time`, signal IDs, and three blank header cells. Row 2 provides descriptive labels for the signal IDs and those otherwise blank columns. Measurements start on row 3.
3. `Sheet2` — another time-series sheet. Row 1 contains `Time` and blank cells; row 2 labels column B `Solar+Wind` in March and October, and `Wind+Solar` in May. Column C has no descriptive label but contains values/formulas.

The `Sheet1` row-1 column names and row-2 labels are consistent across the three files except for the ordering of “Solar+Wind”/“Wind+Solar” in one label. Treat these as a two-row header, not as identical flat headers. `Sheet2` is more ambiguous: its second numeric series is unlabeled.

### `Sheet1` columns

The raw header is shown first; the label in parentheses comes from row 2. Blank raw headers are real blank header cells in the workbook.

| Raw column | Row-2 label | What can be identified |
|---|---|---|
| `Time` | — | Timestamp |
| `SCADA/ANALOG/044MQ068/0` | `TOTAL_THM_ONLY\|P` | Thermal-only total, based on the tag label |
| `SCADA/ANALOG/044MQ062/0` | `TOTAL_NLDC_HYD\|P` | Hydro total, based on the tag label |
| `SCADA/ANALOG/044MQ063/0` | `TOTAL_NLDC_GAS\|P` | Gas total, based on the tag label |
| `SCADA/ANALOG/044MQ064/0` | `TOTAL_NLDC_NPC\|P` | Tag label is available; `NPC` is not expanded in the workbook |
| `SCADA/ANALOG/044MQ070/0` | `ALL_INDIA_WIND\|P` | India wind signal, based on the tag label |
| `SCADA/ANALOG/044MQ206/0` | `ALL_IND_SOLAR\|P` | India solar signal, based on the tag label |
| *(blank)* | `Solar` | Formula-derived column |
| *(blank)* | `Solar+Wind` or `Wind+Solar` | Formula-derived combined column |
| *(blank)* | `Total` | Formula-derived column |
| `SCADA/ANALOG/044MQ067/0` | `NLDC_DEMAND\|P` | Demand signal, based on the tag label |
| `SCADA/ANALOG/030K90IF/0` | `INTRA_SYSTEM_INTERTIA\|P` | Tag label as written; definition not provided |
| `SCADA/ANALOG/031E3193/0` | `ER_Total_Inertia\|P` | Tag label as written; definition not provided |
| `SCADA/ANALOG/034MT227/0` | `SYS_IN\|P` | Tag label as written; definition not provided |
| `SCADA/ANALOG/044MW005/0` | `SPARE 05` | Spare signal; meaning not specified |

**Units:** No measurement unit is stated in the inspected workbook headers or labels. The `|P` suffix appears in several signal names but does not, by itself, confirm a unit. Do not label the measurements as MW or MWh until the dataset owner/source documentation confirms it.

### `Sheet2` columns and meaning

| Raw column | Row-2 label | Confirmed observation |
|---|---|---|
| `Time` | — | Timestamp |
| *(blank)* | `Solar+Wind` or `Wind+Solar` | Values match the combined column in `Sheet1` at the sampled timestamps |
| *(blank)* | *(blank)* | Contains formula-derived values but has no descriptive label; its meaning is unknown |

Do not assign a name or operational meaning to the unlabeled third column without more documentation. Its first 2,913 cached values are numeric, but the remaining **264,927 of 267,840** values in each workbook are cached `#REF!` errors. The first-row formula is `=OFFSET($B$3,(ROW(B1)-1)*360,0)`. This is a source formula issue, not a missing value to fill. The ingestion pipeline preserves the cell error text in an explicitly named companion column and does not recalculate or invent replacement values.

### Dates, row counts, and schema comparison

| Workbook | `Sheet1` and `Sheet2` observed time range | Measurement rows per sheet | Approximate sampling interval |
|---|---|---:|---|
| `March 2023.xlsx` | 2023-03-01 00:00:00 to 2023-03-31 23:59:50 | 267,840 | 10 seconds |
| `May 2023.xlsx` | 2023-05-01 00:00:00 to 2023-05-31 23:59:50 | 267,840 | 10 seconds |
| `October 2023.xlsx` | 2023-10-01 00:00:00 to 2023-10-31 23:59:50 | 267,840 | 10 seconds |

The time values are stored as Excel timestamps and display with small floating-point fractions of a second. Each month has a continuous 10-second timestamp sequence in both measurement sheets: no invalid, duplicate, non-increasing, or missing-interval timestamps were found. The largest observed deviation from a 10-second step was about 0.000006 seconds, consistent with timestamp representation precision.

**Important source-description mismatch:** Although the Mendeley title says “1-hour interval,” the inspected workbooks contain 10-second observations (267,840 per 31-day month). Use the observed files, not the title, to determine the actual cadence.

Each workbook has 803,520 formula cells in `Sheet1` and 267,840 in `Sheet2`. The inspected formulas have saved cached results, but many cached results in `Sheet2` column C are Excel errors (see below). `Sheet1` has no missing measurement cells in the 267,840 measurement rows. `Sheet2` column C is not a clean numeric series.

### Sample records: `Sheet1`

The following is a readable excerpt of the first five measurement rows from each workbook. Values are rounded to two decimal places here; timestamps are rounded to the nearest second for readability. The original workbook retains more precision. Columns are selected from the full schema above.

| File | Time | `ALL_INDIA_WIND\|P` | `ALL_IND_SOLAR\|P` (raw) | Formula `Solar+Wind`/`Wind+Solar` | Formula `Total` | `NLDC_DEMAND\|P` |
|---|---|---:|---:|---:|---:|---:|
| March | 00:00:00 | 8,976.19 | 133.52 | 9,109.72 | 166,132.38 | 165,773.86 |
| March | 00:00:10 | 8,957.70 | 133.51 | 9,091.21 | 166,061.17 | 165,651.95 |
| March | 00:00:20 | 8,955.04 | 106.73 | 9,061.77 | 166,032.43 | 165,563.09 |
| March | 00:00:30 | 8,948.26 | 106.67 | 9,054.94 | 165,965.95 | 165,500.72 |
| March | 00:00:40 | 8,945.60 | 106.68 | 9,052.28 | 165,959.04 | 165,479.39 |
| May | 00:00:00 | 3,891.73 | -13.12 | 3,891.73 | 157,748.75 | 153,649.41 |
| May | 00:00:10 | 3,878.94 | -13.07 | 3,878.94 | 157,781.01 | 153,624.27 |
| May | 00:00:20 | 3,873.32 | -13.21 | 3,873.32 | 157,445.27 | 152,871.16 |
| May | 00:00:30 | 3,873.59 | -13.19 | 3,873.59 | 157,338.99 | 153,160.66 |
| May | 00:00:40 | 3,872.47 | -13.12 | 3,872.47 | 157,519.02 | 153,394.28 |
| October | 00:00:00 | 9,113.58 | 64.45 | 9,178.03 | 185,869.51 | 184,229.77 |
| October | 00:00:10 | 9,104.26 | 64.46 | 9,168.72 | 185,698.65 | 184,080.45 |
| October | 00:00:20 | 9,100.09 | 65.36 | 9,165.45 | 185,608.93 | 183,949.16 |
| October | 00:00:30 | 9,079.02 | 66.93 | 9,145.95 | 185,550.89 | 183,846.39 |
| October | 00:00:40 | 9,100.89 | 66.82 | 9,167.71 | 185,509.70 | 183,743.55 |

### Sample records: `Sheet2`

These are the first five measurement rows for each workbook. Times are rounded to the nearest second for readability. Column B has the label shown; column C is intentionally left unnamed because the workbook does not label it.

| File | Time | Column B | Unlabeled column C |
|---|---|---:|---:|
| March | 00:00:00 | 9,109.72 | 9,109.72 |
| March | 00:00:10 | 9,091.21 | 9,297.63 |
| March | 00:00:20 | 9,061.77 | 8,708.93 |
| March | 00:00:30 | 9,054.94 | 7,830.45 |
| March | 00:00:40 | 9,052.28 | 7,060.16 |
| May | 00:00:00 | 3,891.73 | 3,891.73 |
| May | 00:00:10 | 3,878.94 | 3,499.37 |
| May | 00:00:20 | 3,873.32 | 2,897.91 |
| May | 00:00:30 | 3,873.59 | 2,436.77 |
| May | 00:00:40 | 3,872.47 | 1,719.71 |
| October | 00:00:00 | 9,178.03 | 9,178.03 |
| October | 00:00:10 | 9,168.72 | 9,699.90 |
| October | 00:00:20 | 9,165.45 | 9,705.13 |
| October | 00:00:30 | 9,145.95 | 8,587.34 |
| October | 00:00:40 | 9,167.71 | 8,221.19 |

### Electricity data-quality observations

- The three workbooks have matching sheet names, measurement row counts, and `Sheet1` raw-header schemas. `Sheet2` has an incomplete header in all three files. The descriptive combined-generation label varies in word order between files.
- The inspection found no missing measurement values in `Sheet1` or `Sheet2`; the blank `Time` cells in row 2 belong to the descriptive-label row, not measurement records.
- Raw `ALL_IND_SOLAR|P` contains negative readings in all three inspected months:

  | Workbook | Negative raw solar readings | Minimum raw solar value |
  |---|---:|---:|
  | March 2023 | 23,528 of 267,840 | -350.71 |
  | May 2023 | 37,792 of 267,840 | -269.44 |
  | October 2023 | 31,369 of 267,840 | -1,887.31 |

  In the first data row of all three workbooks, the formula for the derived `Solar` column is `MAX(0,G3)`, so negative raw solar is clipped to zero in that derived series. Confirm this treatment with the source before deciding which solar signal to use.
- The workbook does not explain most formula definitions, the meaning of the `Sheet2` unlabeled series, or the units. The `Sheet2` formula shown above produces cached `#REF!` values for most of the month, so that unlabeled series should not be used as numeric input without source clarification.

## Daily power outage CSV

### Columns and observed types

The file contains 2,664,042 data records and 15 columns. Types below are inferred from the values and corroborated where available by the India Data Portal resource metadata. In a CSV file, values are physically stored as text until parsed.

| Column | Observed/inferred type | Meaning |
|---|---|---|
| `id` | Integer | Record identifier |
| `date` | Date (`YYYY-MM-DD`) | Reporting/snapshot date |
| `region` | Text | Region |
| `state_name` | Text | State/area name |
| `state_code` | Text | State/area code; preserve as text so leading zeroes remain |
| `sector` | Text | Utility sector |
| `station_type` | Text | Generation station type |
| `power_station` | Text | Power station |
| `power_station_unit` | Text | Unit within the station |
| `outage_type` | Text | Outage category; the literal string `None` occurs |
| `monitored_capacity` | Number, metadata unit MW | Monitored station/unit capacity |
| `cap_under_outage` | Number, metadata unit MW | Capacity under outage |
| `outage_date` | Date (`YYYY-MM-DD`) | Recorded start/outage date where supplied |
| `expected_sync_date` | Date (`YYYY-MM-DD`) | Expected synchronization date where supplied |
| `remarks` | Text | Free-text notes; the literal string `None` occurs |

The source metadata describes the resource as daily and identifies power-station/unit-level outage information. There is **no explicit duration column**. Computing a duration from `date` and `outage_date` would require confirming the source's date semantics first.

### Date ranges, values, and sample records

| Date field | Observed range | Non-empty values |
|---|---|---:|
| `date` | 2017-09-01 to 2025-04-22 | 2,664,042 |
| `outage_date` | 1999-05-07 to 2024-11-11 | 529,635 |
| `expected_sync_date` | 2014-11-04 to 2024-12-02 | 86,303 |

The CSV's `date` field extends through 2025-04-22 even though the resource metadata's `years_covered` says 2017–2024. The file's date field is therefore the observed range used here.

The first five records are shown below. Empty cells are blank in the source; the literal word `None` is not a blank.

| id | date | region | state_name | state_code | sector | station_type | power_station | power_station_unit | outage_type | monitored_capacity | cap_under_outage | outage_date | expected_sync_date | remarks |
|---:|---|---|---|---|---|---|---|---|---|---:|---:|---|---|---|
| 0 | 2017-09-01 | Northern | Delhi | 07 | State | Thermal | Rajghat Tps | Unit 1 | Long Duration Outage | 67.5 | 67.5 | 2015-05-08 | *(blank)* | Rsd/Low Schedule |
| 1 | 2017-09-01 | Northern | Delhi | 07 | State | Thermal | Rajghat Tps | Unit 2 | Long Duration Outage | 67.5 | 67.5 | 2015-05-21 | 2017-09-18 | Rsd/Low Schedule |
| 2 | 2017-09-01 | Northern | Delhi | 07 | State | Ther (Gt) | I.P.Ccpp | Single Unit | None | 270.0 | *(blank)* | *(blank)* | *(blank)* | None |
| 3 | 2017-09-01 | Northern | Delhi | 07 | State | Ther (Gt) | Pragati Ccgt-Iii | Single Unit | None | 1500.0 | *(blank)* | *(blank)* | *(blank)* | None |
| 4 | 2017-09-01 | Northern | Delhi | 07 | State | Ther (Gt) | Pragati Ccpp | Single Unit | None | 330.4 | *(blank)* | *(blank)* | *(blank)* | None |

### Outage data-quality observations

- All populated date fields use `YYYY-MM-DD`; no invalid dates or malformed row widths were found.
- No duplicate IDs were found. Every record ID is unique across the full observed range 0–2,664,041; since an exact duplicate row would repeat its ID, no exact duplicate records were found.
- Blank values: `outage_date` 2,134,407 (about 80.1%); `expected_sync_date` 2,577,739 (about 96.8%); `cap_under_outage` 166,730 (about 6.3%); `monitored_capacity` 17,189 (about 0.6%). `date` is populated for every row.
- No negative capacity values or unparseable numeric values were found. Observed `monitored_capacity` is 0–2,920 MW; `cap_under_outage` is 0–1,967.08 MW.
- Some fields use the literal string `None`, rather than a blank: `outage_type` 2,153,661 rows, `remarks` 2,007,748 rows, and `state_code`, `sector`, and `station_type` each 13,089 rows. Preserve this distinction until its meaning is confirmed.
- There are six distinct `region` values, including `Bhutan Imp.`. This may represent an import/area category rather than an Indian state; do not silently discard or remap it.

## Potential use in the project

**Confirmed usefulness**

- The electricity workbooks contain timestamped demand, wind, solar, thermal/hydro/gas/nuclear-like generation tags, and formula-derived combined/total series. They can support ingestion, time-series validation, and simple demand-versus-renewables analysis.
- The outage CSV contains dated, state/region/station/unit-level outage categories and capacity fields. It can support descriptive outage summaries by date, geography, station type, or capacity.

**Limitations to account for**

- The provided electricity files cover only March, May, and October 2023. Three months are useful for an initial data pipeline/demo, but are not enough for dependable year-round forecasting, seasonal analysis, or broad operational recommendations.
- The actual electricity cadence is 10 seconds, while the Mendeley title says one hour. Decide and document any aggregation interval before analysis; do not mistake the existing observations for hourly readings.
- No explicit unit is available for the electricity measurements. Confirm units before comparing them numerically with the outage resource's MW capacity fields.
- The outage data is daily, while the demand/generation data is 10-second and national/tag-based. The outage file does not provide station generation or a direct link to the national demand signals, so it cannot by itself establish the effect of an outage on demand or generation.
- Large numbers of blank outage event/synchronization dates and literal `None` values require deliberate missing-value handling. There is no explicit outage-duration field.
- Workbook formulas, label inconsistencies, negative raw solar samples, and the unlabeled `Sheet2` series need clarification before they are used as model targets or trusted business metrics.

## Suitability and next step

The files are sufficient to begin **data ingestion and validation**, create exploratory summaries, and demonstrate basic charts on the provided periods. They are **not sufficient by themselves for a reliable forecasting/decision-support system**. The next development step should be a small, transparent ingestion layer that reads these original files without rewriting them, normalizes the two-row workbook headers and dates, records units as unknown until verified, and aggregates the 10-second series only after the desired interval is agreed. In parallel, confirm the electricity units/formulas and the meaning of the unlabeled `Sheet2` series with the dataset source.
