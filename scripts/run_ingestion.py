"""Run the Phase 2 ingestion pipeline from a source checkout."""

from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from energy_assistant.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

