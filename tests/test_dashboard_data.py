from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from energy_assistant.dashboard_data import (
    DERIVED_SOLAR_COLUMN,
    evenly_sample_for_chart,
    load_electricity_month,
    summarize_outage_csv,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class DashboardDataTests(unittest.TestCase):
    def test_real_parquet_loads_confirmed_source_signals(self) -> None:
        path = (
            PROJECT_ROOT
            / "processed"
            / "electricity"
            / "march_2023_sheet1.parquet"
        )
        self.assertTrue(path.is_file(), f"Missing processed dataset: {path}")

        frame = load_electricity_month(path)

        self.assertEqual(len(frame), 267_840)
        self.assertEqual(frame["Time"].iloc[0], pd.Timestamp("2023-03-01 00:00:00"))
        self.assertIn("SCADA/ANALOG/044MQ067/0", frame.columns)
        self.assertIn("SCADA/ANALOG/044MQ070/0", frame.columns)
        self.assertIn("SCADA/ANALOG/044MQ206/0", frame.columns)
        self.assertIn(DERIVED_SOLAR_COLUMN, frame.columns)

    def test_formula_error_rows_are_not_returned_as_solar_readings(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            parquet_path = Path(directory) / "sheet1.parquet"
            pd.DataFrame(
                {
                    "Time": pd.to_datetime(
                        ["2023-03-01 00:00:00", "2023-03-01 00:00:10"]
                    ),
                    "SCADA/ANALOG/044MQ067/0": [10.0, 11.0],
                    "SCADA/ANALOG/044MQ070/0": [1.0, 2.0],
                    "SCADA/ANALOG/044MQ206/0": [3.0, 4.0],
                    DERIVED_SOLAR_COLUMN: [3.0, 0.0],
                    "Solar__formula_error": [None, "#REF!"],
                }
            ).to_parquet(parquet_path)

            frame = load_electricity_month(parquet_path)

        self.assertEqual(frame[DERIVED_SOLAR_COLUMN].iloc[0], 3.0)
        self.assertTrue(pd.isna(frame[DERIVED_SOLAR_COLUMN].iloc[1]))
        self.assertEqual(frame["Solar__formula_error"].iloc[1], "#REF!")

    def test_outage_summary_reads_csv_in_chunks_and_keeps_literal_none(self) -> None:
        csv_text = (
            "date,region,state_name,station_type,power_station,outage_type\n"
            "2023-01-02,North,State A,Thermal,Station One,None\n"
            "2023-01-02,North,State A,Thermal,Station One,\n"
            "2023-02-01,South,State B,Hydro,Station Two,Planned\n"
        )
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / "outages.csv"
            csv_path.write_text(csv_text, encoding="utf-8")

            summary = summarize_outage_csv(csv_path, chunk_size=2)

        self.assertEqual(summary["row_count"], 3)
        self.assertEqual(summary["reporting_date_min"], "2023-01-02")
        self.assertEqual(summary["reporting_date_max"], "2023-02-01")
        self.assertEqual(summary["invalid_reporting_dates"], 0)
        self.assertEqual(
            summary["outage_types"],
            [
                {"category": "(blank)", "records": 1},
                {"category": "None", "records": 1},
                {"category": "Planned", "records": 1},
            ],
        )

    def test_chart_sampling_selects_rows_without_aggregation(self) -> None:
        frame = pd.DataFrame({"value": range(11)})

        sampled = evenly_sample_for_chart(frame, max_points=4)

        self.assertEqual(sampled["value"].tolist(), [0, 3, 6, 9])


if __name__ == "__main__":
    unittest.main()
