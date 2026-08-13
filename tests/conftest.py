from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import pytest


SKILL_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = SKILL_ROOT / "scripts"
_app_repo = os.environ.get("CX_OG_APP_REPO")
_data_dir = os.environ.get("CX_OG_DATA_DIR")
APP_REPO = Path(_app_repo).expanduser() if _app_repo else None
DATA_DIR = (
    Path(_data_dir).expanduser()
    if _data_dir
    else APP_REPO / "data"
    if APP_REPO
    else None
)
CLI = SCRIPTS / "cx_og_research.py"

if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))


def write_fixture(data_dir: Path, filename: str, rows: list[dict]) -> None:
    pd.DataFrame(rows).to_parquet(data_dir / filename, index=False)


@pytest.fixture
def write_parquet():
    return write_fixture
