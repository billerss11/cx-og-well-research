from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
APP_REPO = Path(r"J:\cx_coding_project_unsyc\python\CX_O-G_APP")
DATA_DIR = APP_REPO / "data"
CLI = SCRIPTS / "cx_og_research.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def write_fixture(data_dir: Path, filename: str, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(data_dir / filename, index=False)


@pytest.fixture
def write_parquet():
    return write_fixture
