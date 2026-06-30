"""Lease, block, and ownership helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from well_research_core import api_match_sql, duckdb_df, norm_api, parquet_path, parquet_sql, top_rows


LEASE_REQUIRED_DATASETS = [
    "boreholes",
    "lease_data",
    "lease_owner",
    "lease_owner_designated_operator",
    "lease_owner_remarks",
    "company_all",
]


def status_label_expr(column_expr: str) -> str:
    return (
        f"CASE {column_expr} "
        "WHEN 'C' THEN 'Current' "
        "WHEN 'T' THEN 'Terminated' "
        "WHEN '' THEN 'Unknown' "
        f"ELSE {column_expr} END"
    )


def lease_base_ctes(data_dir: Path) -> str:
    return f"""
    WITH selected_boreholes AS (
        SELECT *
        FROM {parquet_sql(data_dir, "boreholes")}
        WHERE {api_match_sql("API_WELL_NUMBER")}
    ),
    lease_roles AS (
        SELECT DISTINCT
            API_WELL_NUMBER,
            WELL_NAME,
            WELL_NAME_SUFFIX,
            'Surface' AS lease_role,
            NULLIF(TRIM(CAST(SURF_LEASE_NUMBER AS VARCHAR)), '') AS lease_number,
            NULLIF(TRIM(CAST(SURF_AREA_CODE AS VARCHAR)), '') AS area_code,
            NULLIF(TRIM(CAST(SURF_BLOCK_NUMBER AS VARCHAR)), '') AS block_number
        FROM selected_boreholes
        WHERE NULLIF(TRIM(CAST(SURF_LEASE_NUMBER AS VARCHAR)), '') IS NOT NULL

        UNION ALL

        SELECT DISTINCT
            API_WELL_NUMBER,
            WELL_NAME,
            WELL_NAME_SUFFIX,
            'Bottom' AS lease_role,
            NULLIF(TRIM(CAST(BOTM_LEASE_NUMBER AS VARCHAR)), '') AS lease_number,
            NULLIF(TRIM(CAST(BOTM_AREA_CODE AS VARCHAR)), '') AS area_code,
            NULLIF(TRIM(CAST(BOTM_BLOCK_NUMBER AS VARCHAR)), '') AS block_number
        FROM selected_boreholes
        WHERE NULLIF(TRIM(CAST(BOTM_LEASE_NUMBER AS VARCHAR)), '') IS NOT NULL
    ),
    selected_leases AS (
        SELECT DISTINCT lease_number
        FROM lease_roles
        WHERE lease_number IS NOT NULL
    ),
    company_latest AS (
        SELECT MMS_COMPANY_NUM, BUS_ASC_NAME
        FROM (
            SELECT
                MMS_COMPANY_NUM,
                BUS_ASC_NAME,
                ROW_NUMBER() OVER (
                    PARTITION BY MMS_COMPANY_NUM
                    ORDER BY MMS_START_DATE DESC NULLS LAST, MMS_TERM_DATE DESC NULLS LAST, BUS_ASC_NAME
                ) AS row_num
            FROM {parquet_sql(data_dir, "company_all")}
        )
        WHERE row_num = 1
    )
    """


def empty_lease_section(data_dir: Path, missing: list[str]) -> dict[str, Any]:
    return {
        "records": 0,
        "available": False,
        "missing_datasets": missing,
        "lease_numbers": [],
        "limitations": [
            "Lease lookup needs generated lease/company parquet files from the CX O&G APP pipeline.",
            "BSEE assignment rows do not directly name legal buyer/seller pairs.",
        ],
        "lease_summary": {"records": 0, "sample": []},
        "current_owners": {"records": 0, "sample": []},
        "ownership_detail": {"records": 0, "sample": []},
        "assignment_history": {"records": 0, "sample": []},
        "data_dir": str(data_dir),
    }


def build_lease_information(data_dir: Path, api: str, limit: int) -> dict[str, Any]:
    missing = [key for key in LEASE_REQUIRED_DATASETS if not parquet_path(data_dir, key).exists()]
    if missing or not norm_api(api):
        return empty_lease_section(data_dir, missing)

    params = [norm_api(api), norm_api(api), norm_api(api)]
    base_ctes = lease_base_ctes(data_dir)

    summary = duckdb_df(
        f"""
        {base_ctes}
        SELECT
            lease_roles.lease_role AS "Lease Role",
            lease_roles.lease_number AS "Lease Number",
            lease_roles.area_code AS "Area",
            lease_roles.block_number AS "Block",
            lease_roles.WELL_NAME AS "Well Name",
            lease_roles.WELL_NAME_SUFFIX AS "Well Name Suffix",
            lease_data.LEASE_STATUS_CODE AS "Lease Status",
            lease_data.LEASE_EFFECTIVE_DATE AS "Lease Effective Date",
            lease_data.LEASE_EXPIRATION_DATE AS "Lease Expiration Date",
            lease_data.CURRENT_AREA AS "Current Area",
            lease_data.ROYALTY_RATE AS "Royalty Rate"
        FROM lease_roles
        LEFT JOIN {parquet_sql(data_dir, "lease_data")} AS lease_data
            ON lease_roles.lease_number = lease_data.LEASE_NUMBER
        ORDER BY
            CASE lease_roles.lease_role WHEN 'Surface' THEN 1 ELSE 2 END,
            lease_roles.lease_number
        """,
        params,
    )

    current_owners = duckdb_df(
        f"""
        {base_ctes}
        SELECT DISTINCT
            owner.LEASE_NUMBER AS "Lease Number",
            owner.MMS_COMPANY_NUM AS "Owner Company Number",
            COALESCE(owner_company.BUS_ASC_NAME, owner.MMS_COMPANY_NUM) AS "Owner Company",
            owner.ASSIGNMENT_PCT AS "Ownership %",
            {status_label_expr("owner.ASGN_STATUS_CODE")} AS "Assignment Status",
            owner.ASGN_APRV_DATE AS "Assignment Approval Date",
            owner.ASGN_EFF_DATE AS "Assignment Effective Date",
            owner.LEASE_DESIG_DATE AS "Lease Designation Date",
            owner.OPERATOR_NUM AS "Designated Operator Number",
            COALESCE(operator_company.BUS_ASC_NAME, owner.OPERATOR_NUM) AS "Designated Operator"
        FROM {parquet_sql(data_dir, "lease_owner_designated_operator")} AS owner
        INNER JOIN selected_leases
            ON owner.LEASE_NUMBER = selected_leases.lease_number
        LEFT JOIN company_latest AS owner_company
            ON owner.MMS_COMPANY_NUM = owner_company.MMS_COMPANY_NUM
        LEFT JOIN company_latest AS operator_company
            ON owner.OPERATOR_NUM = operator_company.MMS_COMPANY_NUM
        WHERE owner.ASGN_STATUS_CODE = 'C'
        ORDER BY owner.LEASE_NUMBER, owner.ASSIGNMENT_PCT DESC, "Owner Company"
        """,
        params,
    )

    ownership_detail = duckdb_df(
        f"""
        {base_ctes}
        SELECT DISTINCT
            remarks.LEASE_NUMBER AS "Lease Number",
            remarks.MMS_COMPANY_NUM AS "Owner Company Number",
            COALESCE(company_latest.BUS_ASC_NAME, remarks.MMS_COMPANY_NUM) AS "Owner Company",
            remarks.ASSIGNMENT_PCT AS "Ownership %",
            remarks.ASGN_APRV_DATE AS "Assignment Approval Date",
            remarks.ASGN_EFF_DATE AS "Assignment Effective Date",
            remarks.OWNER_ALIQUOT_CD AS "Owner Aliquot Code",
            remarks.OWNER_ALQT_DESC AS "Owner Aliquot Description",
            remarks.ALIQUOT_AREA AS "Aliquot Area"
        FROM {parquet_sql(data_dir, "lease_owner_remarks")} AS remarks
        INNER JOIN selected_leases
            ON remarks.LEASE_NUMBER = selected_leases.lease_number
        LEFT JOIN company_latest
            ON remarks.MMS_COMPANY_NUM = company_latest.MMS_COMPANY_NUM
        ORDER BY
            remarks.LEASE_NUMBER,
            remarks.ASGN_EFF_DATE DESC NULLS LAST,
            remarks.ASGN_APRV_DATE DESC NULLS LAST,
            "Owner Company"
        """,
        params,
    )

    assignment_history = duckdb_df(
        f"""
        {base_ctes}
        SELECT DISTINCT
            owner.LEASE_NUMBER AS "Lease Number",
            owner.MMS_COMPANY_NUM AS "Owner Company Number",
            COALESCE(company_latest.BUS_ASC_NAME, owner.MMS_COMPANY_NUM) AS "Owner Company",
            owner.ASSIGNMENT_PCT AS "Ownership %",
            {status_label_expr("owner.ASGN_STATUS_CODE")} AS "Assignment Status",
            owner.ASGN_APRV_DATE AS "Assignment Approval Date",
            owner.ASGN_EFF_DATE AS "Assignment Effective Date",
            owner.ASGN_TERM_DATE AS "Assignment Termination Date",
            owner.OWNER_GROUP_CODE AS "Owner Group",
            owner.SN_LSE_OWNER AS "Lease Owner Serial"
        FROM {parquet_sql(data_dir, "lease_owner")} AS owner
        INNER JOIN selected_leases
            ON owner.LEASE_NUMBER = selected_leases.lease_number
        LEFT JOIN company_latest
            ON owner.MMS_COMPANY_NUM = company_latest.MMS_COMPANY_NUM
        ORDER BY
            owner.LEASE_NUMBER,
            CASE owner.ASGN_STATUS_CODE WHEN 'C' THEN 1 WHEN 'T' THEN 2 ELSE 3 END,
            owner.ASGN_APRV_DATE DESC NULLS LAST,
            owner.ASGN_EFF_DATE DESC NULLS LAST,
            "Owner Company"
        """,
        params,
    )

    lease_numbers = (
        sorted(str(value) for value in summary["Lease Number"].dropna().unique())
        if "Lease Number" in summary.columns
        else []
    )
    return {
        "records": int(len(summary)),
        "available": bool(len(summary) or len(current_owners) or len(ownership_detail) or len(assignment_history)),
        "lease_numbers": lease_numbers,
        "sources": {
            "lease_summary": "df_boreholes.parquet + df_lease_data.parquet",
            "current_owners": "df_lease_owner_designated_operator.parquet",
            "ownership_detail": "df_lease_owner_remarks.parquet",
            "assignment_history": "df_lease_owner.parquet",
            "company_names": "df_company_all.parquet",
        },
        "limitations": [
            "BSEE assignment rows identify current and terminated ownership records, but do not directly name legal buyer/seller pairs.",
            "Lease owner remarks include assignment percentage and aliquot detail, but not current/terminated status.",
        ],
        "lease_summary": {"records": int(len(summary)), "sample": top_rows(summary, None, limit)},
        "current_owners": {"records": int(len(current_owners)), "sample": top_rows(current_owners, None, limit)},
        "ownership_detail": {"records": int(len(ownership_detail)), "sample": top_rows(ownership_detail, None, limit)},
        "assignment_history": {"records": int(len(assignment_history)), "sample": top_rows(assignment_history, None, limit)},
    }
