from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from cx_og_research import (
    _strip_map_data,
    build_parser,
    emit,
    run,
)
from well_research_casing import build_global_casing_search
from well_research_config import DATASET_CATALOG, DATASETS
from well_research_core import build_ranked_dataset, describe_table, to_jsonable
from well_research_current import (
    raw_well_records,
    well_applications,
    well_documents,
    well_timeline,
)
from well_research_decom import build_decom_research
from well_research_lease import build_lease_information
from well_research_settings import config_path, resolve_data_dir


CANONICAL_KEYS = {
    "schema_version",
    "command",
    "query",
    "data",
    "provenance",
    "coverage",
    "warnings",
}


@pytest.mark.parametrize(
    "arguments,command",
    [
        (["configure", "cx-data"], "configure"),
        (["doctor"], "doctor"),
        (["wells", "search", "MADISON"], "wells.search"),
        (["wells", "suggestions", "MADISON"], "wells.suggestions"),
        (["wells", "filter-options", "field", "MAD"], "wells.filter-options"),
        (["evidence", "search", "stuck pipe"], "evidence.search"),
        (["evidence", "detail", "608044019701", "stuck pipe"], "evidence.detail"),
        (["well", "dossier", "608054000500"], "well.dossier"),
        (["well", "raw", "608054000500", "boreholes"], "well.raw"),
        (["well", "identity", "608054000500"], "well.identity"),
        (["well", "lease-activity", "608054000500", "G10379"], "well.lease-activity"),
        (["well", "trajectory-analysis", "608054000500"], "well.trajectory-analysis"),
        (["well", "casing-versions", "608054000500"], "well.casing-versions"),
        (["well", "casing-analysis", "608054000500", "--source", "war"], "well.casing-analysis"),
        (["well", "war-record", "608054000500", "2988"], "well.war-record"),
        (["fields", "list"], "fields.list"),
        (["fields", "compare", "AC336"], "fields.compare"),
        (["fields", "leases", "AC336"], "fields.leases"),
        (["fields", "trajectory-comparison", "MC194", "--api", "608054000500"], "fields.trajectory-comparison"),
        (["production", "compare", "608054000500"], "production.compare"),
        (["approvals", "search"], "approvals.search"),
        (["approvals", "options"], "approvals.options"),
        (["platforms", "search"], "platforms.search"),
        (["platforms", "detail", "822", "1"], "platforms.detail"),
        (["pipelines", "search"], "pipelines.search"),
        (["pipelines", "detail", "1"], "pipelines.detail"),
        (["bulk", "files", "608054000500"], "bulk.files"),
        (["bulk", "war", "608054000500"], "bulk.war"),
        (["casing", "search", "9.625"], "casing.search"),
        (["decommissioning", "search"], "decommissioning.search"),
        (["decommissioning", "authorities"], "decommissioning.authorities"),
        (["decommissioning", "authority", "LSE", "00008"], "decommissioning.authority"),
        (["decommissioning", "well", "608054000500"], "decommissioning.well"),
        (["decommissioning", "pipeline", "12237"], "decommissioning.pipeline"),
        (["decommissioning", "platform", "822", "1"], "decommissioning.platform"),
        (["tables", "list"], "tables.list"),
        (["tables", "describe", "production"], "tables.describe"),
        (["tables", "rank", "production", "oil_volume"], "tables.rank"),
    ],
)
def test_parser_exposes_every_public_command(arguments, command):
    args = build_parser().parse_args(arguments)
    actual = args.group if not hasattr(args, "action") else f"{args.group}.{args.action}"
    assert actual == command


def test_configure_saves_valid_data_folder_locally(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    for spec in DATASET_CATALOG.values():
        if spec["required"]:
            pd.DataFrame(columns=spec["required_columns"]).to_parquet(
                data_dir / spec["filename"],
                index=False,
            )

    local_config = tmp_path / "local-config"
    monkeypatch.setenv("LOCALAPPDATA", str(local_config))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(local_config))
    monkeypatch.delenv("CX_OG_DATA_DIR", raising=False)

    result, status = run(build_parser().parse_args(["configure", str(data_dir)]))

    assert status == 0
    assert result["data"]["validation_ok"] is True
    assert config_path().is_file()
    assert resolve_data_dir() == data_dir.resolve()


def test_json_helpers_preserve_scalar_coordinates_and_strip_map_data():
    value = {
        "path": Path("example.txt"),
        "latitude": 29.0,
        "nested": {"geometry": "not allowed", "value": (1, 2)},
        "geojson": {"type": "FeatureCollection", "features": []},
        "bathymetry": [{"depth": 1000}],
        "columns": [
            {"name": "LONGITUDE", "unit": "deg", "aliases": []},
            {"name": "oil", "unit": "bbl", "aliases": []},
        ],
    }
    cleaned = to_jsonable(_strip_map_data(value))
    assert cleaned["path"] == "example.txt"
    assert cleaned["latitude"] == 29.0
    assert "geometry" not in cleaned["nested"]
    assert "geojson" not in cleaned
    assert "bathymetry" not in cleaned
    assert [column["name"] for column in cleaned["columns"]] == ["LONGITUDE", "oil"]


def test_emit_writes_canonical_json(tmp_path):
    output = tmp_path / "nested" / "result.json"
    result = {
        "schema_version": 1,
        "command": "doctor",
        "query": {},
        "data": {"ok": True},
        "provenance": {},
        "coverage": [],
        "warnings": [],
    }
    emit(result, "json", output)
    saved = json.loads(output.read_text(encoding="utf-8"))
    assert set(saved) == CANONICAL_KEYS
    assert saved == result


def test_rank_and_describe_keep_trajectory_and_production_contracts(
    tmp_path, write_parquet
):
    write_parquet(
        tmp_path,
        DATASETS["wellpath_metrics"],
        [
            {"API Number": "111", "calc_max_horizontal_departure_ft": 300.0},
            {"API Number": "222", "calc_max_horizontal_departure_ft": 900.0},
        ],
    )
    ranked = build_ranked_dataset(
        tmp_path, "wellpath_metrics", "horizontal_departure", 1
    )
    assert ranked["sample"][0]["API Number"] == "222"
    assert ranked["rank_unit"] == "ft"

    write_parquet(
        tmp_path,
        DATASETS["production"],
        [{"Api Well Number": "111", "Monthly Oil Volume": 100.0, "Day_Aver_Oil": 10.0}],
    )
    description = describe_table(tmp_path, "production", 1)
    assert description["units"]["Monthly Oil Volume"] == "bbl"
    assert description["units"]["Day_Aver_Oil"] == "bbl/day"


def test_casing_fixture_keeps_apd_planned_and_war_actual_separate(
    tmp_path, write_parquet
):
    api = "123456789000"
    write_parquet(
        tmp_path,
        DATASETS["boreholes"],
        [{
            "API_WELL_NUMBER": api,
            "WELL_NAME": "A-1",
            "WELL_NAME_SUFFIX": None,
            "COMPANY_NAME": "Example",
            "FIELD": "TEST",
            "OPERATOR FIELD": "TEST FIELD",
            "AREA": "AC",
            "BLOCK": "100",
            "LEASE": "G00001",
        }],
    )
    write_parquet(
        tmp_path,
        DATASETS["apd_main"],
        [{"API_WELL_NUMBER": api, "SN_APD": "10", "APD_SUB_STATUS_DT": "2020-01-01"}],
    )
    write_parquet(
        tmp_path,
        DATASETS["apd_casing_intervals"],
        [{
            "SN_APD_FK": "10",
            "SN_APD_CSG_INTV": "20",
            "CSNG_INTV_TYPE_CD": "C",
            "CSNG_INTV_NAME": "planned",
            "CSNG_TOP_MD": 0,
        }],
    )
    write_parquet(
        tmp_path,
        DATASETS["apd_casing_sections"],
        [{
            "SN_APD_CSNG_INTV_FK": "20",
            "CASING_SIZE": 9.625,
            "CASING_WEIGHT": 47,
            "CASING_GRADE": "P110",
            "CASING_SECTION_MD": 5000,
        }],
    )
    write_parquet(
        tmp_path,
        DATASETS["war_main"],
        [{"API_WELL_NUMBER": api, "SN_WAR": "30", "WAR_END_DT": "2021-01-01"}],
    )
    write_parquet(
        tmp_path,
        DATASETS["war_tubular"],
        [{
            "SN_WAR_FK": "30",
            "SN_WAR_CSNG_INTV": "40",
            "CSNG_INTV_TYPE_CD": "C",
            "CASING_SIZE": 9.625,
            "CASING_WEIGHT": 47,
            "CASING_GRADE": "P110",
        }],
    )
    write_parquet(
        tmp_path,
        DATASETS["war_tubular_prop"],
        [{
            "SN_WAR_FK": "30",
            "SN_WAR_CSNG_INTV_FK": "40",
            "CSNG_SETTING_TOP_MD": 0,
            "CSNG_SETTING_BOTM_MD": 4900,
        }],
    )
    result = build_global_casing_search(
        tmp_path, [9.625], "any", "all", 0.01, None, False, 10
    )
    assert result["well_count"] == 1
    assert result["wells"][0]["sources_available"] == ["APD", "WAR"]
    assert {row["DATA_SOURCE"] for row in result["wells"][0]["sample"]} == {
        "APD",
        "WAR",
    }


def test_lease_fixture_preserves_current_owner_and_assignment_guardrail(
    tmp_path, write_parquet
):
    api = "123456789000"
    fixtures = {
        "boreholes": [{
            "API_WELL_NUMBER": api,
            "WELL_NAME": "A-1",
            "WELL_NAME_SUFFIX": "ST01",
            "SURF_LEASE_NUMBER": "G36102",
            "BOTM_LEASE_NUMBER": "G36102",
            "SURF_AREA_CODE": "AC",
            "SURF_BLOCK_NUMBER": "336",
            "BOTM_AREA_CODE": "AC",
            "BOTM_BLOCK_NUMBER": "336",
        }],
        "lease_data": [{
            "LEASE_NUMBER": "G36102",
            "LEASE_STATUS_CODE": "UNIT",
            "LEASE_EFFECTIVE_DATE": "2020-01-01",
            "LEASE_EXPIRATION_DATE": "2030-01-01",
            "CURRENT_AREA": 5760.0,
            "ROYALTY_RATE": 18.75,
        }],
        "lease_owner_designated_operator": [{
            "LEASE_NUMBER": "G36102",
            "MMS_COMPANY_NUM": "00002",
            "ASSIGNMENT_PCT": 50.0,
            "ASGN_STATUS_CODE": "C",
            "ASGN_APRV_DATE": "2024-10-01",
            "ASGN_EFF_DATE": "2024-10-01",
            "LEASE_DESIG_DATE": "2024-10-05",
            "OPERATOR_NUM": "00003",
        }],
        "lease_owner": [
            {
                "LEASE_NUMBER": "G36102",
                "MMS_COMPANY_NUM": "00001",
                "ASSIGNMENT_PCT": 100.0,
                "ASGN_STATUS_CODE": "T",
                "ASGN_APRV_DATE": "2022-01-01",
                "ASGN_EFF_DATE": "2022-01-01",
                "ASGN_TERM_DATE": "2023-01-01",
                "OWNER_GROUP_CODE": "",
                "SN_LSE_OWNER": "10",
            },
            {
                "LEASE_NUMBER": "G36102",
                "MMS_COMPANY_NUM": "00002",
                "ASSIGNMENT_PCT": 50.0,
                "ASGN_STATUS_CODE": "C",
                "ASGN_APRV_DATE": "2024-10-01",
                "ASGN_EFF_DATE": "2024-10-01",
                "ASGN_TERM_DATE": None,
                "OWNER_GROUP_CODE": "",
                "SN_LSE_OWNER": "11",
            },
        ],
        "lease_owner_remarks": [{
            "LEASE_NUMBER": "G36102",
            "MMS_COMPANY_NUM": "00002",
            "ASSIGNMENT_PCT": 50.0,
            "ASGN_APRV_DATE": "2024-10-01",
            "ASGN_EFF_DATE": "2024-10-01",
            "OWNER_ALIQUOT_CD": "1",
            "OWNER_ALQT_DESC": "All rights",
            "ALIQUOT_AREA": 2880.0,
        }],
        "company_all": [
            {"MMS_COMPANY_NUM": "00001", "BUS_ASC_NAME": "Seller Energy", "MMS_START_DATE": "2020-01-01", "MMS_TERM_DATE": None},
            {"MMS_COMPANY_NUM": "00002", "BUS_ASC_NAME": "Buyer Offshore", "MMS_START_DATE": "2024-01-01", "MMS_TERM_DATE": None},
            {"MMS_COMPANY_NUM": "00003", "BUS_ASC_NAME": "Operator LLC", "MMS_START_DATE": "2024-01-01", "MMS_TERM_DATE": None},
        ],
    }
    for key, rows in fixtures.items():
        write_parquet(tmp_path, DATASETS[key], rows)
    result = build_lease_information(tmp_path, api, 10)
    assert result["current_owners"]["sample"][0]["Owner Company"] == "Buyer Offshore"
    assert result["current_owners"]["sample"][0]["Designated Operator"] == "Operator LLC"
    assert "do not directly name legal buyer/seller pairs" in result["limitations"][0]


def test_decommissioning_fixture_filters_cost_and_api(tmp_path, write_parquet):
    write_parquet(
        tmp_path,
        DATASETS["decom_totals"],
        [{
            "AUTH_TYPE_CODE": "LSE",
            "AUTH_NUMBER": "G34454",
            "TYPE": "Wells Decom Cost",
            "CNT": 1,
            "P50_COST": 100,
            "P70_COST": 150,
            "P90_COST": 200,
            "DTR_COST": 0,
        }],
    )
    write_parquet(
        tmp_path,
        DATASETS["decom_spud_well"],
        [{
            "API_WELL_NUMBER": "123",
            "BOTM_LEASE_NUM": "G34454",
            "SURF_LEASE_NUM": "G34454",
            "WELL_NAME": "A001",
            "WELL_INST_DCOM_P50": 110,
            "WELL_INST_DCOM_P70": 160,
            "WELL_INST_DCOM_P90": 210,
            "WELL_INST_DCOM_INDTR": 0,
            "BOTM_AREA_CODE": "GC",
            "BOTM_BLOCK_NUM": "100",
            "BOREHOLE_STAT_CD": "COM",
            "EFFECTIVE_DATE": "2020-01-01",
        }],
    )
    result = build_decom_research(
        tmp_path, "G34454", "123", None, None, 100, "p90", None, 10
    )
    assert result["sections"]["totals"]["records"] == 1
    assert result["sections"]["installed_wells"]["records"] == 1


def test_regulatory_fixture_covers_apps_documents_and_timeline(
    tmp_path, write_parquet
):
    api = "123456789000"
    fixtures = {
        "apd_main": [{
            "API_WELL_NUMBER": api,
            "SN_APD": "APD1",
            "PERMIT_TYPE": "NEW",
            "APD_STATUS_DT": "2020-02-01",
            "APD_SUB_STATUS_DT": "2020-01-01",
            "REQ_SPUD_DATE": "2020-03-01",
            "BUS_ASC_NAME": "Operator",
            "RIG_NAME": "Rig",
            "RIG_ID_NUM": "R1",
        }],
        "apm_applications": [{
            "api_well_number": api,
            "application_id": "APM1",
            "operation_code": "WORKOVER",
            "borehole_status_code": "APP",
            "application_status_date": "2021-02-01",
            "submitted_date": "2021-01-01",
            "work_commences_date": "2021-03-01",
            "operator_name": "Operator",
            "rig_id": "R2",
            "attachment_count": 1,
            "question_count": 1,
            "response_count": 1,
            "resubmittal_count": 0,
            "verbal_count": 0,
            "source_duplicate_count": 1,
        }],
        "application_attachments": [{
            "document_id": "ATT1",
            "parent_type": "APD",
            "parent_id": "APD1",
            "api_well_number": api,
            "document_name": "Application",
            "file_extension": "pdf",
            "business_category": "Permit",
            "document_date": "2020-01-02",
            "operator_name": "Operator",
            "source_family": "APD",
            "availability": "metadata_only",
        }],
        "frs": [{
            "DOC_ID": "DOC1",
            "API": api,
            "DOC_TYPE": "LOG",
            "FILE_EXT": "pdf",
            "CREATED_DATE": "2022-01-01",
            "RUN_DATE": "2022-01-01",
            "FILE_SIZE": 100,
            "LEASE": "G1",
            "AREA": "AC",
            "BLOCK": "100",
        }],
        "war_main": [{
            "API_WELL_NUMBER": api,
            "SN_WAR": "WAR1",
            "WAR_START_DT": "2019-01-01",
            "WAR_END_DT": "2019-01-02",
            "RIG_NAME": "Rig",
            "BUS_ASC_NAME": "Operator",
        }],
        "boreholes": [{
            "API_WELL_NUMBER": api,
            "WELL_SPUD_DATE": "2018-01-01",
            "TOTAL_DEPTH_DATE": "2018-02-01",
            "BH_TOTAL_MD": 10000,
            "WELL_NAME": "A-1",
            "BOREHOLE_STAT_DT": "2018-03-01",
            "BOREHOLE_STAT_CD": "COM",
        }],
        "eor_main": [{
            "API_WELL_NUMBER": api,
            "SN_EOR": "EOR1",
            "BOREHOLE_STAT_DT": "2018-03-01",
            "BOREHOLE_STAT_CD": "COM",
            "EOR_OPERATION_CD": "DRL",
        }],
        "apm_events": [{
            "api_well_number": api,
            "event_id": "APM:E1",
            "event_date": "2021-02-01",
            "event_end_date": None,
            "source_family": "APM",
            "event_type": "approved",
            "source_record_id": "APM1",
            "title": "APM approved",
            "summary": "Approved",
            "event_category": "application",
            "document_count": 0,
            "link_method": "source_parent",
        }],
        "bhp": [{"API_WELL_NUMBER": api, "BHTST_DATE": "2022-02-01", "BHP": "1000", "RESERVOIR_NAME": "R"}],
        "api_changes": [{"API_WELL_NUMBER": api, "ACTIVITY_DATE": "2022-03-01", "SOURCE_RECORD_ID": "C1", "PREV_API_NUMBER": "123"}],
        "directional_surveys": [{"API_WELL_NUMBER": api, "RECEIPT_DATE": "2022-04-01", "SOURCE_RECORD_ID": "D1", "DOC_ID": "D"}],
        "well_potential_tests": [{"API_WELL_NUMBER": api, "TEST_DATE": "2022-05-01", "SOURCE_RECORD_ID": "P1", "FIELD_NAME": "TEST"}],
        "asset_approvals": [{
            "approval_event_id": "A1",
            "approval_group_id": "G1",
            "event_date": "2022-06-01",
            "asset_type": "well",
            "asset_identifier": api,
            "business_process": "Permit",
            "approval_type": "Approved",
            "regulation_number": None,
            "operator_number": "1",
            "operator_name": "Operator",
            "short_description": "Approved",
            "region": "GOM",
            "raw_attributes": "{}",
            "link_method": "exact_attribute",
            "source_row_number": 1,
        }],
    }
    for key, rows in fixtures.items():
        write_parquet(tmp_path, DATASETS[key], rows)

    applications = well_applications(tmp_path, api, 10)
    documents = well_documents(tmp_path, api, 10)
    timeline = well_timeline(tmp_path, api, None, 100)
    assert applications["records"] == 2
    assert {row["source_family"] for row in applications["sample"]} == {"APD", "APM"}
    assert documents["records"] == 2
    assert all("local_path" not in row for row in documents["sample"])
    assert {
        "API change",
        "Directional survey",
        "Well potential",
        "Approval",
        "APM",
    }.issubset(timeline["source_counts"])


def test_missing_optional_data_is_not_reported_as_zero(tmp_path):
    applications = well_applications(tmp_path, "123456789000", 10)
    raw = raw_well_records(tmp_path, "123456789000", "applications_apm")
    assert applications["records"] is None
    assert applications["warnings"]
    assert raw["total_count"] is None
    assert raw["warnings"]
