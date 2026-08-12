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
EXCLUDED_MAP_KEY_PARTS = (
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


def assert_no_map_payload_keys(value):
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).casefold()
            assert not any(part in normalized for part in EXCLUDED_MAP_KEY_PARTS), key
            assert normalized not in {"geom", "wkt", "wkb", "shape"}
            assert_no_map_payload_keys(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_map_payload_keys(child)


@pytest.mark.parametrize(
    "arguments,expected_command",
    [
        (["doctor"], "doctor"),
        (["wells", "search", "608054000500", "--page-size", "1"], "wells.search"),
        (["evidence", "search", "stuck pipe", "--page-size", "1"], "evidence.search"),
        (["evidence", "detail", "608044019701", "stuck pipe", "--page-size", "1"], "evidence.detail"),
        (["well", "dossier", "608054000500", "--sections", "relationships"], "well.dossier"),
        (["well", "raw", "608054000500", "boreholes", "--page-size", "1"], "well.raw"),
        (["well", "summary", "608054000500"], "well.summary"),
        (["well", "availability", "608054000500"], "well.availability"),
        (["well", "relationships", "608054000500"], "well.relationships"),
        (["well", "ownership", "608054000500"], "well.ownership"),
        (["well", "production", "608054000500"], "well.production"),
        (["well", "trajectory", "608054000500"], "well.trajectory"),
        (["well", "wellbore", "608054000500"], "well.wellbore"),
        (["well", "casing", "608054000500"], "well.casing"),
        (["well", "war", "608054000500"], "well.war"),
        (["well", "permits", "608054000500"], "well.permits"),
        (["well", "files", "608054000500"], "well.files"),
        (["well", "applications", "608044019701", "--page-size", "1"], "well.applications"),
        (["well", "documents", "608044019701", "--page-size", "1"], "well.documents"),
        (["well", "timeline", "608044019701", "--page-size", "1"], "well.timeline"),
        (["well", "timeline-detail", "608044019701", "WAR:-419928"], "well.timeline-detail"),
        (["well", "batch", "documents", "608044019701", "608054000500", "--page-size", "1"], "well.batch"),
        (["fields", "list"], "fields.list"),
        (["fields", "compare", "AC336"], "fields.compare"),
        (["fields", "wells", "AC336"], "fields.wells"),
        (["fields", "leases", "AC336"], "fields.leases"),
        (["fields", "lease-context", "AC336"], "fields.lease-context"),
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
    assert_no_map_payload_keys(result)


def test_search_and_summary_return_scalar_coordinates():
    search = run_cli(["wells", "search", "608054000500", "--page-size", "1"])
    assert search.returncode == 0, search.stderr
    search_row = json.loads(search.stdout)["data"]["rows"][0]
    assert search_row["Surface latitude"] is not None
    assert search_row["Surface longitude"] is not None

    summary = run_cli(["well", "summary", "608054000500"])
    assert summary.returncode == 0, summary.stderr
    summary_data = json.loads(summary.stdout)["data"]
    assert summary_data["surface_latitude"] is not None
    assert summary_data["surface_longitude"] is not None
    assert "bottom_latitude" in summary_data
    assert "bottom_longitude" in summary_data


def test_field_raw_table_and_dossier_return_scalar_coordinates():
    fields = run_cli(["fields", "wells", "AC336"])
    assert fields.returncode == 0, fields.stderr
    field_row = json.loads(fields.stdout)["data"]["wells"][0]
    assert field_row["surface_latitude"] is not None
    assert field_row["surface_longitude"] is not None

    raw = run_cli(
        ["well", "raw", "608054000500", "boreholes", "--page-size", "1"]
    )
    assert raw.returncode == 0, raw.stderr
    raw_row = json.loads(raw.stdout)["data"]["rows"][0]
    assert raw_row["SURF_LATITUDE"] is not None
    assert raw_row["SURF_LONGITUDE"] is not None
    assert "BOTM_LATITUDE" in raw_row
    assert "BOTM_LONGITUDE" in raw_row

    table = run_cli(["tables", "describe", "boreholes"])
    assert table.returncode == 0, table.stderr
    table_data = json.loads(table.stdout)["data"]
    column_names = {column["name"] for column in table_data["columns"]}
    assert {
        "SURF_LATITUDE",
        "SURF_LONGITUDE",
        "BOTM_LATITUDE",
        "BOTM_LONGITUDE",
    } <= column_names

    dossier = run_cli(
        ["well", "dossier", "608054000500", "--sections", "borehole"]
    )
    assert dossier.returncode == 0, dossier.stderr
    dossier_data = json.loads(dossier.stdout)["data"]
    assert dossier_data["identity"]["SURF_LATITUDE"] is not None
    assert dossier_data["identity"]["SURF_LONGITUDE"] is not None
    assert "BOTM_LATITUDE" in dossier_data["identity"]
    assert "BOTM_LONGITUDE" in dossier_data["identity"]


def test_empty_search_is_successful():
    completed = run_cli(
        ["wells", "search", "NO_SUCH_WELL_VALUE_983742", "--page-size", "1"]
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["data"]["total_count"] == 0


def test_well_search_accepts_structured_filters():
    completed = run_cli(
        ["wells", "search", "--operator", "Renaissance", "--page-size", "3"]
    )
    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["data"]["total_count"] > 0
    assert all(
        "renaissance" in row["Operator"].casefold()
        for row in result["data"]["rows"]
    )


def test_batch_well_section_returns_one_result_per_api():
    completed = run_cli(
        [
            "well",
            "batch",
            "timeline",
            "608044019701",
            "608054000500",
            "--source",
            "WAR",
            "--page-size",
            "1",
        ]
    )
    assert completed.returncode == 0
    result = json.loads(completed.stdout)
    assert result["data"]["section"] == "timeline"
    assert result["data"]["api_well_numbers"] == [
        "608044019701",
        "608054000500",
    ]
    assert result["data"]["result_count"] == 2
    assert all(
        item["data"]["page_size"] == 1
        for item in result["data"]["results"]
    )


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
    assert_no_map_payload_keys(dossier_result)
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
