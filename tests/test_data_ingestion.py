from __future__ import annotations

import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from energy_assistant.config import ELECTRICITY_DIR, OUTAGE_FILE
from energy_assistant.data_loading import (
    _column_mapping,
    iter_csv_chunks,
    open_electricity_sheet,
    temporary_duplicate_index,
    update_duplicate_counts,
)
from energy_assistant.validation import new_validation_report, record_issue


class ColumnMappingTests(unittest.TestCase):
    def test_blank_headers_keep_labels_and_unlabeled_columns_are_explicit(self) -> None:
        mapping = _column_mapping(
            ("Time", None, None),
            (None, "Wind+Solar", None),
        )

        self.assertEqual(
            [column["output_name"] for column in mapping],
            ["Time", "Solar+Wind", "unlabeled_column_C"],
        )
        self.assertEqual(mapping[1]["descriptive_label"], "Wind+Solar")
        self.assertEqual(
            mapping[1]["naming_rule"],
            "descriptive_label_for_blank_header",
        )


class RealDatasetReaderTests(unittest.TestCase):
    def test_electricity_reader_uses_two_header_rows_and_formula_cache(self) -> None:
        workbook = ELECTRICITY_DIR / "May 2023.xlsx"
        self.assertTrue(workbook.is_file(), f"Missing real workbook: {workbook}")

        with open_electricity_sheet(workbook, "Sheet1") as (
            mapping,
            rows,
            formulas,
        ):
            by_name = {column["output_name"]: column for column in mapping}
            self.assertIn("SCADA/ANALOG/044MQ067/0", by_name)
            self.assertEqual(
                by_name["Solar"]["descriptive_label"],
                "Solar",
            )
            self.assertEqual(formulas["Solar"], "=MAX(0,G3)")
            excel_row, values = next(rows)
            self.assertEqual(excel_row, 3)
            self.assertEqual(str(values[0]), "2023-05-01 00:00:00")
            self.assertEqual(values[7], 0)
            self.assertEqual(values[8], 3891.726318359375)

    def test_sheet_two_unlabeled_measurement_is_retained(self) -> None:
        workbook = ELECTRICITY_DIR / "March 2023.xlsx"
        with open_electricity_sheet(workbook, "Sheet2") as (
            mapping,
            rows,
            formulas,
        ):
            self.assertEqual(
                [column["output_name"] for column in mapping],
                ["Time", "Solar+Wind", "unlabeled_column_C"],
            )
            self.assertEqual(
                formulas["unlabeled_column_C"],
                "=OFFSET($B$3,(ROW(B1)-1)*360,0)",
            )
            _, values = next(rows)
            self.assertEqual(values[2], 9109.718322753906)
            for _ in range(2913):
                excel_row, values = next(rows)
            self.assertEqual(excel_row, 2916)
            self.assertEqual(values[2], "#REF!")

    def test_outage_chunks_preserve_literal_none_and_state_code(self) -> None:
        self.assertTrue(OUTAGE_FILE.is_file(), f"Missing real CSV: {OUTAGE_FILE}")
        chunk = next(iter_csv_chunks(OUTAGE_FILE, chunk_size=5))

        self.assertEqual(len(chunk), 5)
        self.assertEqual(chunk.iloc[0]["state_code"], "07")
        self.assertEqual(chunk.iloc[2]["outage_type"], "None")
        self.assertEqual(chunk.iloc[2]["cap_under_outage"], "")


class ValidationHelperTests(unittest.TestCase):
    def test_duplicate_index_counts_exact_rows_and_duplicate_ids(self) -> None:
        records = [
            ("1", "2023-01-01", "station"),
            ("1", "2023-01-01", "station"),
            ("2", "2023-01-01", "station"),
        ]
        with temporary_duplicate_index() as connection:
            duplicate_rows, duplicate_ids = update_duplicate_counts(
                connection,
                records,
            )

        self.assertEqual(duplicate_rows, 1)
        self.assertEqual(duplicate_ids, 1)

    def test_issue_counts_are_aggregated_without_losing_examples(self) -> None:
        report = new_validation_report()
        record_issue(
            report,
            severity="error",
            code="invalid_timestamp",
            message="Invalid timestamp.",
            source="March 2023.xlsx",
            field="Sheet1.Time",
            count=2,
            examples=[{"excel_row": 3}, {"excel_row": 4}],
        )

        self.assertEqual(len(report["errors"]), 1)
        self.assertEqual(report["errors"][0]["count"], 2)
        self.assertEqual(
            report["errors"][0]["examples"],
            [{"excel_row": 3}, {"excel_row": 4}],
        )


if __name__ == "__main__":
    unittest.main()
