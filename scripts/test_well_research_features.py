#!/usr/bin/env python
"""Regression checks for cx-og-well-research feature helpers."""

from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).with_name("build_well_research.py")
REPO = Path(r"J:\cx_coding_project_unsyc\python\CX_O-G_APP")
DATA_DIR = REPO / "data"


def load_module():
    spec = importlib.util.spec_from_file_location("build_well_research", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load build_well_research.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_incident_search_returns_expanded_terms(module):
    result = module.search_incident(DATA_DIR, "stuck-pipe", None, 3)
    assert result["incident"] == "stuck-pipe"
    assert "stuck pipe" in result["terms"]
    assert result["war_hit_records"] > 0
    assert result["wells"]


def test_data_dir_validation_and_duckdb_api_query(module):
    validation = module.check_data_dir(DATA_DIR)
    assert validation["ok"], validation
    df = module.query_api_dataset(DATA_DIR, "boreholes", "API_WELL_NUMBER", "608054000500")
    assert len(df) == 1
    assert df.iloc[0]["API_WELL_NUMBER"] == "608054000500"


def test_dossier_can_include_production_casing_compare_and_timeline(module):
    dossier = module.build_dossier(
        DATA_DIR,
        "608054000500",
        limit=2,
        min_step=100.0,
        include_production=True,
        include_casing_compare=True,
        include_timeline=True,
    )
    assert "production" in dossier["sections"]
    assert dossier["sections"]["production"]["records"] == 42
    assert "casing_comparison" in dossier["sections"]
    assert "timeline" in dossier["sections"]
    assert dossier["sections"]["timeline"]["records"] > 0


def test_field_audit_ranks_wells(module):
    audit = module.build_field_audit(DATA_DIR, "MADISON", 5)
    assert audit["field_query"] == "MADISON"
    assert audit["well_count"] >= 2
    assert audit["wells"]
    assert "data_score" in audit["wells"][0]


def main() -> int:
    module = load_module()
    test_incident_search_returns_expanded_terms(module)
    test_data_dir_validation_and_duckdb_api_query(module)
    test_dossier_can_include_production_casing_compare_and_timeline(module)
    test_field_audit_ranks_wells(module)
    print("feature tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
