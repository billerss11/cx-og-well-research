from __future__ import annotations

import sys
from pathlib import Path

from conftest import APP_REPO, DATA_DIR

if str(APP_REPO) not in sys.path:
    sys.path.append(str(APP_REPO))

from backend.repositories.approvals import ApprovalsRepository
from backend.repositories.pipelines import PipelineRepository
from backend.repositories.platforms import PlatformRepository
from backend.repositories.wells import WellRepository

from well_research_core import to_jsonable
from well_research_current import (
    build_dossier,
    pipeline_detail,
    platform_detail,
    production_comparison,
    search_approvals,
    search_evidence,
    search_pipelines,
    search_platforms,
    search_wells,
    well_applications,
    well_documents,
    well_timeline,
)


REGULATORY_API = "608044019701"
PRODUCTION_API = "608054000500"


def normalized(value):
    return to_jsonable(value)


def coverage_counts(rows):
    return {
        str(row["source"]): int(row["record_count"])
        for row in rows
        if row.get("record_count") is not None
    }


def test_runtime_layer_has_no_backend_imports():
    scripts = Path(__file__).resolve().parents[1] / "scripts"
    for path in (scripts / "cx_og_research.py", scripts / "well_research_current.py"):
        source = path.read_text(encoding="utf-8")
        assert "from backend" not in source
        assert "import backend" not in source


def test_exact_and_fuzzy_well_search_match_backend():
    backend = WellRepository(DATA_DIR)
    cases = [
        ("608054000500", "exact", 90, True),
        ("MADSN", "fuzzy", 70, True),
    ]
    for query, match_mode, threshold, partial in cases:
        backend_rows, backend_total = backend.search(
            query,
            1,
            10,
            "api_well_number",
            "asc",
            match_mode,
            threshold,
            partial,
        )
        skill = search_wells(
            DATA_DIR,
            query,
            page=1,
            page_size=10,
            sort_by="api_well_number",
            sort_direction="asc",
            match_mode=match_mode,
            threshold=threshold,
            partial=partial,
        )
        assert skill["total_count"] == backend_total
        assert normalized(skill["rows"]) == normalized(backend_rows)


def test_exact_and_fuzzy_evidence_search_match_backend():
    backend = WellRepository(DATA_DIR)
    cases = [
        ("stuck pipe", "exact", 90, True),
        ("stuck ppe", "fuzzy", 75, True),
    ]
    for query, match_mode, threshold, partial in cases:
        backend_result = backend.search_evidence(
            query,
            1,
            10,
            match_mode,
            threshold,
            partial,
            "matches",
        )
        skill = search_evidence(
            DATA_DIR,
            query,
            page=1,
            page_size=10,
            match_mode=match_mode,
            threshold=threshold,
            partial=partial,
            sort_by="matches",
        )
        assert normalized(skill) == normalized(backend_result)


def test_production_comparison_matches_backend_stream():
    backend = WellRepository(DATA_DIR).production(PRODUCTION_API)
    skill = production_comparison(DATA_DIR, [PRODUCTION_API], "well", 1_000)
    assert skill["totals"]["series_count"] == len(backend["streams"])
    assert normalized(skill["series"][0]["summary"]) == normalized(backend["summary"])
    assert normalized(skill["series"][0]["rows"]) == normalized(backend["rows"])


def test_applications_documents_and_timeline_match_backend():
    backend = WellRepository(DATA_DIR)

    app_rows, app_total, app_coverage, app_warnings = backend.applications(
        REGULATORY_API, page=1, page_size=10
    )
    skill_apps = well_applications(DATA_DIR, REGULATORY_API, 10)
    assert skill_apps["records"] == app_total
    assert normalized(skill_apps["sample"]) == normalized(app_rows)
    assert skill_apps["warnings"] == app_warnings
    assert sum(coverage_counts(app_coverage).values()) == app_total

    document_rows, document_total, document_coverage, document_warnings = (
        backend.documents(REGULATORY_API, page=1, page_size=10)
    )
    skill_documents = well_documents(DATA_DIR, APP_REPO, REGULATORY_API, 10)
    comparable_fields = (
        "document_id",
        "parent_type",
        "parent_id",
        "api_well_number",
        "document_name",
        "file_extension",
        "business_category",
        "document_date",
        "operator_name",
        "source_family",
        "file_size_source",
        "lease_number",
        "area",
        "block",
    )
    assert skill_documents["records"] == document_total
    assert [
        {field: normalized(row.get(field)) for field in comparable_fields}
        for row in skill_documents["sample"]
    ] == [
        {field: normalized(row.get(field)) for field in comparable_fields}
        for row in document_rows
    ]
    assert skill_documents["warnings"] == document_warnings
    assert sum(coverage_counts(document_coverage).values()) == document_total
    assert all("local_path" in row for row in skill_documents["sample"])

    timeline_rows, timeline_total, timeline_coverage, timeline_warnings = (
        backend.timeline(REGULATORY_API, page=1, page_size=10)
    )
    skill_timeline = well_timeline(DATA_DIR, REGULATORY_API, None, 10)
    assert skill_timeline["records"] == timeline_total
    assert normalized(skill_timeline["sample"]) == normalized(timeline_rows)
    assert skill_timeline["warnings"] == timeline_warnings
    backend_source_counts = {
        source: count
        for source, count in coverage_counts(timeline_coverage).items()
        if count
    }
    assert skill_timeline["source_counts"] == backend_source_counts


def test_known_dossier_section_counts_match_backend():
    backend = WellRepository(DATA_DIR)
    _, application_total, _, _ = backend.applications(
        PRODUCTION_API, page=1, page_size=1
    )
    _, document_total, _, _ = backend.documents(
        PRODUCTION_API, page=1, page_size=1
    )
    _, timeline_total, _, _ = backend.timeline(
        PRODUCTION_API, page=1, page_size=1
    )
    production = backend.production(PRODUCTION_API)
    dossier = build_dossier(
        DATA_DIR,
        APP_REPO,
        PRODUCTION_API,
        1,
        sections=["production", "applications", "documents", "timeline"],
    )
    assert dossier["identity"]["API_WELL_NUMBER"] == PRODUCTION_API
    assert dossier["availability"]["production"] == len(production["rows"])
    assert dossier["availability"]["applications"] == application_total
    assert dossier["availability"]["documents"] == document_total
    assert dossier["availability"]["timeline"] == timeline_total


def test_approval_filtering_matches_backend():
    backend = ApprovalsRepository(DATA_DIR).query(
        page=1,
        page_size=10,
        asset_type="well",
    )
    skill = search_approvals(
        DATA_DIR,
        page=1,
        page_size=10,
        asset_type="well",
    )
    assert skill["total_count"] == backend["total_count"]
    assert skill["matching_asset_count"] == backend["matching_asset_count"]
    assert normalized(skill["rows"]) == normalized(backend["rows"])


def test_platform_attributes_and_detail_match_backend_without_geometry():
    backend_repository = PlatformRepository(
        DATA_DIR / "unzipped" / "Platforms.gdb",
        DATA_DIR,
    )
    backend_query = backend_repository.query()
    backend_rows = [
        feature["properties"]
        for feature in backend_query["geojson"]["features"][:25]
    ]
    skill_query = search_platforms(DATA_DIR, page=1, page_size=25)
    assert skill_query["total_count"] == backend_query["summary"]["total_platforms"]
    for backend_row, skill_row in zip(backend_rows, skill_query["rows"]):
        assert {
            key: normalized(skill_row.get(key))
            for key in backend_row
        } == normalized(backend_row)

    backend_detail = backend_repository.detail(822, 1)
    skill_detail = platform_detail(DATA_DIR, 822, 1, 10)
    safe_fields = (
        "complex_id",
        "structure_number",
        "structure_name",
        "install_date",
        "removal_date",
    )
    assert {
        field: normalized(backend_detail["platform"].get(field))
        for field in safe_fields
    } == {
        field: normalized(skill_detail["source_attributes"].get(field))
        for field in safe_fields
    }
    assert len(skill_detail["removal_history"]) == len(
        backend_detail["removal_history"]
    )
    assert len(skill_detail["approvals"]) == len(
        backend_detail["approval_history"]
    )


def test_pipeline_attributes_filters_and_detail_match_backend_without_geometry():
    backend_repository = PipelineRepository(
        DATA_DIR / "unzipped" / "Pipelines.gdb",
        data_directory=DATA_DIR,
    )
    backend_query = backend_repository.query(
        status="ACT",
        product="OIL",
        company="RENAISSANCE",
    )
    backend_rows = [
        feature["properties"]
        for feature in backend_query["geojson"]["features"][:25]
    ]
    skill_query = search_pipelines(
        DATA_DIR,
        status="ACT",
        product="OIL",
        company="RENAISSANCE",
        page=1,
        page_size=25,
    )
    assert skill_query["total_count"] == backend_query["summary"]["matched_segments"]
    assert normalized(skill_query["rows"]) == normalized(backend_rows)

    backend_detail, backend_coverage, backend_warnings = backend_repository.detail(
        "1",
        history_page=1,
        history_page_size=10,
    )
    skill_detail = pipeline_detail(
        DATA_DIR,
        "1",
        history_page=1,
        history_page_size=10,
        sample_limit=10,
    )
    assert normalized(skill_detail["source_attributes"]) == normalized(
        backend_detail["map_segment"]
    )
    assert skill_detail["permit_history"]["total_count"] == len(
        backend_detail["permit_records"]
    )
    assert len(skill_detail["submittals"]) == backend_detail["history"]["total_count"]
    assert normalized(
        [str(row["segment_number"]) for row in skill_detail["connections"]]
    ) == normalized(backend_detail["connected_segment_numbers"])
    assert len(skill_detail["approvals"]) == len(backend_detail["approvals"])
    assert set(backend_warnings).issubset(skill_detail["warnings"])
    assert any(
        "differs from latest permit status" in warning
        for warning in skill_detail["warnings"]
    )
    assert coverage_counts(backend_coverage)["Pipeline permits"] == len(
        backend_detail["permit_records"]
    )
