from __future__ import annotations

import json
import subprocess
import sys

import pytest

from conftest import APP_REPO, CLI


CANONICAL_KEYS = {
    "schema_version",
    "command",
    "query",
    "data",
    "provenance",
    "coverage",
    "warnings",
}
MAP_KEY_PARTS = (
    "latitude",
    "longitude",
    "geometry",
    "geojson",
    "easting",
    "northing",
    "x_location",
    "y_location",
    "x_coordinate",
    "y_coordinate",
    "bathymetry",
    "continental_shelf",
    "east_offset",
    "north_offset",
    "surf_e_w",
    "surf_n_s",
    "nad_year",
    "proj_code",
)


def run_cli(arguments: list[str], *, repo=APP_REPO) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(CLI),
            "--repo",
            str(repo),
            "--sample-limit",
            "1",
            *arguments,
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=120,
        check=False,
    )


def assert_no_map_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold()
            assert not any(part in normalized for part in MAP_KEY_PARTS), key
            assert normalized not in {"geom", "wkt", "wkb", "shape"}
            assert_no_map_keys(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_map_keys(child)


@pytest.mark.parametrize(
    "arguments,expected_command",
    [
        (["doctor"], "doctor"),
        (["wells", "search", "608054000500", "--page-size", "1"], "wells.search"),
        (["evidence", "search", "stuck pipe", "--page-size", "1"], "evidence.search"),
        (["evidence", "detail", "608044019701", "stuck pipe", "--page-size", "1"], "evidence.detail"),
        (["well", "dossier", "608054000500", "--sections", "relationships"], "well.dossier"),
        (["well", "raw", "608054000500", "boreholes", "--page-size", "1"], "well.raw"),
        (["fields", "list"], "fields.list"),
        (["fields", "compare", "AC336"], "fields.compare"),
        (["fields", "leases", "AC336"], "fields.leases"),
        (["production", "compare", "608054000500", "608054001200"], "production.compare"),
        (["approvals", "search", "--asset-type", "well", "--page-size", "1"], "approvals.search"),
        (["approvals", "options"], "approvals.options"),
        (["platforms", "search", "--status", "active", "--page-size", "1"], "platforms.search"),
        (["platforms", "detail", "822", "1"], "platforms.detail"),
        (["pipelines", "search", "--status", "ACT", "--page-size", "1"], "pipelines.search"),
        (["pipelines", "detail", "1", "--history-page-size", "1"], "pipelines.detail"),
        (["bulk", "files", "608054000500"], "bulk.files"),
        (["bulk", "war", "608054000500"], "bulk.war"),
        (["casing", "search", "9.625", "--source", "any"], "casing.search"),
        (["decommissioning", "search", "--api", "608054000500"], "decommissioning.search"),
        (["tables", "list"], "tables.list"),
        (["tables", "describe", "production"], "tables.describe"),
        (["tables", "rank", "production", "oil_volume"], "tables.rank"),
    ],
)
def test_every_public_command_runs_with_canonical_bounded_json(
    arguments, expected_command
):
    completed = run_cli(arguments)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert set(result) == CANONICAL_KEYS
    assert result["command"] == expected_command
    assert result["schema_version"] == 1
    assert isinstance(result["warnings"], list)
    assert_no_map_keys(result)


def test_empty_search_is_successful():
    completed = run_cli(
        ["wells", "search", "NO_SUCH_WELL_VALUE_983742", "--page-size", "1"]
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["data"]["total_count"] == 0


def test_incident_preset_hands_off_from_search_to_detail():
    search = run_cli(
        ["evidence", "search", "--incident", "stuck-pipe", "--page-size", "1"]
    )
    assert search.returncode == 0
    search_result = json.loads(search.stdout)
    api = search_result["data"]["rows"][0]["api_well_number"]
    detail = run_cli(
        [
            "evidence",
            "detail",
            api,
            "--incident",
            "stuck-pipe",
            "--page-size",
            "1",
        ]
    )
    assert detail.returncode == 0
    detail_result = json.loads(detail.stdout)
    assert (
        detail_result["data"]["war"]["total_count"]
        + detail_result["data"]["attachments"]["total_count"]
        > 0
    )
    assert search_result["warnings"]


def test_selected_dossier_reports_focused_coverage():
    completed = run_cli(
        [
            "well",
            "dossier",
            "608054000500",
            "--sections",
            "relationships,ownership,timeline",
        ]
    )
    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert len(result["coverage"]) < 30
    assert result["provenance"]["source_family"] == (
        "BSEE sources used by the selected well dossier sections"
    )
    assert "coverage_scope" in result["provenance"]["derived_fields"]
    assert {row["family"] for row in result["coverage"]}.issubset(
        {"wells", "platforms", "leases", "companies", "applications", "regulatory", "wellbore", "trajectory", "approvals", "decommissioning"}
    )


def test_sample_limit_bounds_production_rows_and_dossier_lists():
    comparison = run_cli(
        ["production", "compare", "608054000500", "608054000501"]
    )
    assert comparison.returncode == 0
    comparison_result = json.loads(comparison.stdout)
    assert all(
        len(series["rows"]) <= 1
        for series in comparison_result["data"]["series"]
    )
    assert any(
        series["truncated"]
        for series in comparison_result["data"]["series"]
    )

    dossier = run_cli(
        [
            "well",
            "dossier",
            "608054000500",
            "--sections",
            "production,wellpath_metrics",
        ]
    )
    assert dossier.returncode == 0
    dossier_result = json.loads(dossier.stdout)
    assert_no_map_keys(dossier_result)
    assert len(
        dossier_result["data"]["sections"]["production"]["sample"]
    ) <= 1
    assert len(
        dossier_result["data"]["sections"]["wellpath_metrics"]["sample"]
    ) <= 1


def test_api_decommissioning_excludes_unrelated_global_totals():
    completed = run_cli(
        ["decommissioning", "search", "--api", "608054000500"]
    )
    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert all(count == 0 for count in result["data"]["summary"].values())
    assert result["warnings"]


def test_asset_details_explain_approval_scope_and_status_conflicts():
    platform = run_cli(["platforms", "detail", "822", "1"])
    assert platform.returncode == 0
    platform_result = json.loads(platform.stdout)
    assert platform_result["data"]["regulatory_approvals"]
    assert any("complex-level" in warning for warning in platform_result["warnings"])

    pipeline = run_cli(["pipelines", "detail", "1"])
    assert pipeline.returncode == 0
    pipeline_result = json.loads(pipeline.stdout)
    assert any(
        "differs from latest permit status" in warning
        for warning in pipeline_result["warnings"]
    )


def test_invalid_input_uses_exit_code_2():
    completed = run_cli(["wells", "search", "x", "--threshold", "20"])
    assert completed.returncode == 2


def test_unavailable_required_data_uses_exit_code_3(tmp_path):
    completed = run_cli(["doctor"], repo=tmp_path)
    assert completed.returncode == 3
    result = json.loads(completed.stdout)
    assert set(result) == CANONICAL_KEYS
    assert result["data"]["ok"] is False
