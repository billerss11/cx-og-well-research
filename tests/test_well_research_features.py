#!/usr/bin/env python
"""Regression checks for cx-og-well-research feature helpers."""

from __future__ import annotations

import importlib.util
import json
import tempfile
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "build_well_research.py"
REPO = Path(r"J:\cx_coding_project_unsyc\python\CX_O-G_APP")
DATA_DIR = REPO / "data"


def load_module():
    spec = importlib.util.spec_from_file_location("build_well_research", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("Cannot load build_well_research.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def module():
    return load_module()


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


def test_production_time_series_has_standard_plot_schema(module):
    group_by = module.normalize_production_group_by("interval code name")
    dossier = module.build_dossier(
        DATA_DIR,
        "608054000500",
        limit=2,
        min_step=100.0,
        production_group_by=group_by,
    )
    series = dossier["sections"]["production"]["time_series"]
    assert series["kind"] == "production_time_series"
    assert series["grain"] == "monthly"
    assert series["x"] == {"field": "period_start", "type": "date"}
    assert series["group_by"]["field"] == "production_interval_code"
    assert series["records"] > 0
    assert series["groups"]
    first_point = series["points"][0]
    assert {
        "period_start",
        "group",
        "oil_volume",
        "gas_volume",
        "water_volume",
        "injection_volume",
        "days_on_prod",
        "oil_rate",
        "gas_rate",
        "water_rate",
        "source_row_count",
    }.issubset(first_point)


def test_completion_reconciliation_keeps_production_and_eor_separate(module):
    dossier = module.build_dossier(
        DATA_DIR,
        "427064030600",
        limit=5,
        min_step=100.0,
        include_completion_reconcile=True,
    )
    reconciliation = dossier["sections"]["completion_reconciliation"]
    assert reconciliation["production"]["records"] > 0
    assert reconciliation["eor"]["records"] > 0
    assert "004" in reconciliation["production"]["completion_names"]
    assert "S3" in reconciliation["eor"]["intervals"]
    assert "production_interval_codes_not_in_eor" in reconciliation["comparison"]
    assert "eor_interval_codes_not_in_production" in reconciliation["comparison"]


def test_field_audit_ranks_wells(module):
    audit = module.build_field_audit(DATA_DIR, "MADISON", 5)
    assert audit["field_query"] == "MADISON"
    assert audit["well_count"] >= 2
    assert audit["wells"]
    assert "data_score" in audit["wells"][0]


def test_emit_result_can_save_json_for_rendering(module):
    result = {"api_query": "123", "availability": {"boreholes": 1}}
    with tempfile.TemporaryDirectory() as tmp:
        output = Path(tmp) / "well.json"
        module.emit_result(result, "json", output, module.print_dossier)
        saved = json.loads(output.read_text(encoding="utf-8"))
    assert saved == result


def main() -> int:
    module = load_module()
    test_incident_search_returns_expanded_terms(module)
    test_data_dir_validation_and_duckdb_api_query(module)
    test_dossier_can_include_production_casing_compare_and_timeline(module)
    test_production_time_series_has_standard_plot_schema(module)
    test_completion_reconciliation_keeps_production_and_eor_separate(module)
    test_field_audit_ranks_wells(module)
    test_emit_result_can_save_json_for_rendering(module)
    print("feature tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
