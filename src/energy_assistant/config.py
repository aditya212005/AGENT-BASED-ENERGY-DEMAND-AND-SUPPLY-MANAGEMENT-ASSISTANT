"""Project paths and source dataset configuration."""

from dataclasses import dataclass
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DATA_DIR = PROJECT_ROOT / "raw_data"
PROCESSED_DIR = PROJECT_ROOT / "processed"
ELECTRICITY_DIR = RAW_DATA_DIR / "electricity_demand"
OUTAGE_FILE = RAW_DATA_DIR / "outages" / "daily_power_outage.csv"

ELECTRICITY_FILES = (
    "March 2023.xlsx",
    "May 2023.xlsx",
    "October 2023.xlsx",
)

ELECTRICITY_SOURCE_URL = "https://data.mendeley.com/datasets/y58jknpgs8/1"
OUTAGE_SOURCE_URL = (
    "https://ckandev.indiadataportal.com/dataset/power/"
    "resource/abd6d0f5-b948-4c2e-9ca8-459721ee888d"
)

EXPECTED_EXCEL_SHEETS = ("_osi_config", "Sheet1", "Sheet2")
REQUIRED_ELECTRICITY_COLUMNS = (
    "Time",
    "SCADA/ANALOG/044MQ067/0",
    "SCADA/ANALOG/044MQ070/0",
    "SCADA/ANALOG/044MQ206/0",
)
EXPECTED_OUTAGE_COLUMNS = (
    "id",
    "date",
    "region",
    "state_name",
    "state_code",
    "sector",
    "station_type",
    "power_station",
    "power_station_unit",
    "outage_type",
    "monitored_capacity",
    "cap_under_outage",
    "outage_date",
    "expected_sync_date",
    "remarks",
)
OUTAGE_DATE_COLUMNS = ("date", "outage_date", "expected_sync_date")
OUTAGE_NUMERIC_COLUMNS = ("id", "monitored_capacity", "cap_under_outage")

# The source uses two word orders for this same descriptive label. The exact
# source label is retained in schema.json for every workbook and column.
ELECTRICITY_LABEL_ALIASES = {
    "Wind+Solar": "Solar+Wind",
}

CSV_CHUNK_SIZE = 100_000
PARQUET_BATCH_SIZE = 25_000


@dataclass(frozen=True)
class PipelinePaths:
    """Paths used by one ingestion run."""

    project_root: Path = PROJECT_ROOT
    electricity_dir: Path = ELECTRICITY_DIR
    outage_file: Path = OUTAGE_FILE
    processed_dir: Path = PROCESSED_DIR
