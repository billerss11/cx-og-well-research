"""Standalone query ports used by the Vue application.

This module intentionally depends only on the skill's own helpers and the
published data files.  It must never import the application backend.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any

import pandas as pd

from well_research_core import duckdb_df, parquet_path, parquet_sql, top_rows
from well_research_current import field_options
from well_research_trajectory import dls_analysis


FILTER_OPTION_FIELDS = {
    "operator",
    "field",
    "status",
    "area",
    "block",
    "platform",
    "lease",
}


def _require(data_dir: Path, *keys: str) -> None:
    missing = [str(parquet_path(data_dir, key)) for key in keys if not parquet_path(data_dir, key).is_file()]
    if missing:
        raise FileNotFoundError("Missing required dataset(s): " + ", ".join(missing))


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return top_rows(frame, None, len(frame))


def _page(frame: pd.DataFrame, page: int, page_size: int) -> dict[str, Any]:
    offset = (page - 1) * page_size
    return {
        "rows": top_rows(frame.iloc[offset : offset + page_size], None, page_size),
        "page": page,
        "page_size": page_size,
        "total_count": int(len(frame)),
    }


def well_suggestions(data_dir: Path, query: str, limit: int = 10) -> list[dict[str, Any]]:
    """Return the same non-map well suggestions used by the Vue search box."""
    normalized_query = query.strip().casefold()
    if len(normalized_query) < 2:
        return []
    _require(data_dir, "boreholes")
    rows = _records(
        duckdb_df(
            f"""
            SELECT
                TRIM(API_WELL_NUMBER) AS api_well_number,
                NULLIF(TRIM(CONCAT_WS(' ', WELL_NAME, WELL_NAME_SUFFIX)), '') AS well_name,
                NULLIF(TRIM(COMPANY_NAME), '') AS operator,
                COALESCE(
                    NULLIF(TRIM("OPERATOR FIELD"), ''),
                    NULLIF(TRIM(FIELD), ''),
                    NULLIF(TRIM(BOTM_FLD_NAME_CD), '')
                ) AS field
            FROM {parquet_sql(data_dir, "boreholes")}
            WHERE NULLIF(TRIM(API_WELL_NUMBER), '') IS NOT NULL
            ORDER BY api_well_number
            """
        )
    )
    aliases_by_api: dict[str, list[str]] = {}
    if parquet_path(data_dir, "api_changes").is_file():
        aliases = _records(
            duckdb_df(
                f"""
                SELECT DISTINCT
                    TRIM(CAST(API_WELL_NUMBER AS VARCHAR)) AS api_well_number,
                    TRIM(CAST(PREV_API_NUMBER AS VARCHAR)) AS previous_api
                FROM {parquet_sql(data_dir, "api_changes")}
                WHERE API_WELL_NUMBER IS NOT NULL
                  AND PREV_API_NUMBER IS NOT NULL
                  AND TRIM(CAST(API_WELL_NUMBER AS VARCHAR)) <> ''
                  AND TRIM(CAST(PREV_API_NUMBER AS VARCHAR)) <> ''
                  AND TRIM(CAST(API_WELL_NUMBER AS VARCHAR))
                      <> TRIM(CAST(PREV_API_NUMBER AS VARCHAR))
                ORDER BY api_well_number, previous_api
                """
            )
        )
        for alias in aliases:
            aliases_by_api.setdefault(str(alias["api_well_number"]), []).append(
                str(alias["previous_api"])
            )

    ranked: list[tuple[int, int, str, dict[str, Any], str | None]] = []
    for row in rows:
        aliases = aliases_by_api.get(str(row["api_well_number"]), [])
        values = [
            str(value).casefold()
            for value in (
                row["api_well_number"],
                *aliases,
                row["well_name"],
                row["operator"],
                row["field"],
            )
            if value
        ]
        matches: list[tuple[int, int, str]] = []
        for priority, value in enumerate(values):
            rank = _match_rank(value, normalized_query)
            if rank is not None:
                matches.append((rank, priority, value))
        if not matches:
            continue
        rank, priority, matched_value = min(matches)
        matched_alias = matched_value if 1 <= priority <= len(aliases) else None
        ranked.append((rank, priority, str(row["api_well_number"]), row, matched_alias))
    ranked.sort(key=lambda item: item[:3])
    return [
        {
            "api_well_number": row["api_well_number"],
            "well_name": row["well_name"],
            "operator": row["operator"],
            "field": row["field"],
            "matched_alias": matched_alias,
        }
        for _rank, _priority, _api, row, matched_alias in ranked[:limit]
    ]


def _match_rank(value: str, query: str) -> int | None:
    if value == query:
        return 0
    if value.startswith(query):
        return 1
    if query in value:
        return 2
    return None


def well_filter_options(
    data_dir: Path,
    field: str,
    query: str = "",
    limit: int = 20,
) -> list[str]:
    """Discover valid values for a Vue well-search filter."""
    if field not in FILTER_OPTION_FIELDS:
        raise ValueError(f"Unsupported well filter field: {field}")
    _require(data_dir, "boreholes")
    if field == "platform":
        _require(data_dir, "structures")
        frame = duckdb_df(
            f"""
            SELECT DISTINCT COALESCE(
                NULLIF(TRIM(structure.STRUCTURE_NAME), ''),
                'Structure ' || TRIM(structure.STRUCTURE_NUMBER)
            ) AS value
            FROM {parquet_sql(data_dir, "boreholes")} AS borehole
            JOIN {parquet_sql(data_dir, "structures")} AS structure
              ON UPPER(TRIM(borehole.SURF_AREA_CODE)) = UPPER(TRIM(structure.AREA_CODE))
             AND REGEXP_REPLACE(UPPER(TRIM(borehole.SURF_BLOCK_NUMBER)), '\\s+', '', 'g')
                 = REGEXP_REPLACE(UPPER(TRIM(structure.BLOCK_NUMBER)), '\\s+', '', 'g')
             AND POWER(borehole.SURF_LATITUDE - structure.LATITUDE, 2)
                 + POWER(
                    (borehole.SURF_LONGITUDE - structure.LONGITUDE)
                    * COS(RADIANS(borehole.SURF_LATITUDE)), 2
                 ) <= POWER(0.05 / 69.0, 2)
            WHERE COALESCE(
                NULLIF(TRIM(structure.STRUCTURE_NAME), ''),
                NULLIF(TRIM(structure.STRUCTURE_NUMBER), '')
            ) IS NOT NULL
            """
        )
    else:
        expressions = {
            "operator": "NULLIF(TRIM(COMPANY_NAME), '')",
            "field": "COALESCE(NULLIF(TRIM(\"OPERATOR FIELD\"), ''), NULLIF(TRIM(FIELD), ''), NULLIF(TRIM(BOTM_FLD_NAME_CD), ''))",
            "status": "NULLIF(TRIM(BOREHOLE_STAT_CD), '')",
            "area": "COALESCE(NULLIF(TRIM(AREA), ''), NULLIF(TRIM(BOTM_AREA_CODE), ''))",
            "block": "COALESCE(NULLIF(TRIM(BLOCK), ''), NULLIF(TRIM(BOTM_BLOCK_NUMBER), ''))",
            "lease": "COALESCE(NULLIF(TRIM(LEASE), ''), NULLIF(TRIM(BOTM_LEASE_NUMBER), ''))",
        }
        expression = expressions[field]
        frame = duckdb_df(
            f"SELECT DISTINCT {expression} AS value FROM {parquet_sql(data_dir, 'boreholes')} WHERE {expression} IS NOT NULL"
        )
    normalized_query = query.strip().casefold()
    ranked: list[tuple[int, str, str]] = []
    for value in frame["value"].dropna().astype(str):
        normalized_value = value.casefold()
        rank = 0 if not normalized_query else _match_rank(normalized_value, normalized_query)
        if rank is not None:
            ranked.append((rank, normalized_value, value))
    ranked.sort()
    return [value for _rank, _normalized, value in ranked[:limit]]


def well_summary(data_dir: Path, api_well_number: str) -> dict[str, Any] | None:
    _require(data_dir, "boreholes", "war_main")
    rows = _records(
        duckdb_df(
            f"""
            WITH war_dates AS (
                SELECT API_WELL_NUMBER,
                       MIN(WAR_START_DT) AS war_first_date,
                       MAX(COALESCE(WAR_END_DT, WAR_START_DT)) AS war_latest_date
                FROM {parquet_sql(data_dir, "war_main")}
                WHERE API_WELL_NUMBER = ?
                GROUP BY API_WELL_NUMBER
            )
            SELECT
                API_WELL_NUMBER AS api_well_number,
                NULLIF(TRIM(WELL_NAME), '') AS well_name,
                NULLIF(TRIM(WELL_NAME_SUFFIX), '') AS well_name_suffix,
                COMPANY_NAME AS operator,
                BOREHOLE_STAT_CD AS status,
                WELL_TYPE_CODE AS well_type,
                COALESCE(NULLIF(FIELD, ''), BOTM_FLD_NAME_CD) AS field,
                COALESCE(NULLIF(LEASE, ''), BOTM_LEASE_NUMBER) AS lease,
                COALESCE(NULLIF(AREA, ''), BOTM_AREA_CODE) AS area,
                COALESCE(NULLIF(BLOCK, ''), BOTM_BLOCK_NUMBER) AS block,
                WELL_SPUD_DATE AS spud_date,
                TOTAL_DEPTH_DATE AS total_depth_date,
                war_dates.war_first_date,
                war_dates.war_latest_date,
                WATER_DEPTH AS water_depth_ft,
                BH_TOTAL_MD AS total_md_ft,
                WELL_BORE_TVD AS tvd_ft,
                SURF_LATITUDE AS surface_latitude,
                SURF_LONGITUDE AS surface_longitude,
                BOTM_LATITUDE AS bottom_latitude,
                BOTM_LONGITUDE AS bottom_longitude
            FROM {parquet_sql(data_dir, "boreholes")} AS borehole
            LEFT JOIN war_dates USING (API_WELL_NUMBER)
            WHERE borehole.API_WELL_NUMBER = ?
            LIMIT 1
            """,
            [api_well_number, api_well_number],
        )
    )
    if not rows:
        return None
    row = rows[0]
    same_surface = _records(
        duckdb_df(
            f"""
            SELECT
                API_WELL_NUMBER AS api_well_number,
                NULLIF(TRIM(WELL_NAME), '') AS well_name,
                NULLIF(TRIM(WELL_NAME_SUFFIX), '') AS well_name_suffix,
                NULLIF(TRIM(COMPANY_NAME), '') AS operator,
                BOREHOLE_STAT_CD AS status,
                WELL_TYPE_CODE AS well_type,
                COALESCE(NULLIF(TRIM(FIELD), ''), BOTM_FLD_NAME_CD) AS field,
                COALESCE(NULLIF(TRIM(LEASE), ''), BOTM_LEASE_NUMBER) AS lease,
                COALESCE(NULLIF(TRIM(AREA), ''), BOTM_AREA_CODE) AS area,
                COALESCE(NULLIF(TRIM(BLOCK), ''), BOTM_BLOCK_NUMBER) AS block,
                WELL_SPUD_DATE AS spud_date,
                TOTAL_DEPTH_DATE AS total_depth_date
            FROM {parquet_sql(data_dir, "boreholes")}
            WHERE API_WELL_NUMBER <> ?
              AND SURF_LATITUDE = ?
              AND SURF_LONGITUDE = ?
            ORDER BY API_WELL_NUMBER
            """,
            [api_well_number, row["surface_latitude"], row["surface_longitude"]],
        )
    )
    row["same_surface_location_wells"] = same_surface
    return row


def lease_activity(
    data_dir: Path,
    api_well_number: str,
    lease_number: str,
    page: int = 1,
    page_size: int = 50,
    include_administrative: bool = False,
) -> dict[str, Any]:
    _require(data_dir, "boreholes", "lease_remarks", "lease_descriptions")
    normalized_lease = lease_number.strip().upper()
    associated = duckdb_df(
        f"""
        SELECT lease_number FROM (
            SELECT UPPER(TRIM(SURF_LEASE_NUMBER)) AS lease_number
            FROM {parquet_sql(data_dir, "boreholes")} WHERE API_WELL_NUMBER = ?
            UNION
            SELECT UPPER(TRIM(BOTM_LEASE_NUMBER)) AS lease_number
            FROM {parquet_sql(data_dir, "boreholes")} WHERE API_WELL_NUMBER = ?
        )
        WHERE lease_number IS NOT NULL AND lease_number NOT IN ('', 'UNKNOWN')
        """,
        [api_well_number, api_well_number],
    )
    if normalized_lease not in set(associated["lease_number"].astype(str)):
        raise KeyError(f"Lease {lease_number} is not associated with well {api_well_number}")

    raw_events = _records(
        duckdb_df(
            f"""
            SELECT
                TRIM(LEASE_NUMBER) AS lease_number,
                RMK_ORDR AS remark_order,
                REMARK_DATE AS event_date,
                REMARK AS remark
            FROM {parquet_sql(data_dir, "lease_remarks")}
            WHERE UPPER(TRIM(LEASE_NUMBER)) = ?
            ORDER BY event_date DESC NULLS LAST, remark_order ASC NULLS LAST
            """,
            [normalized_lease],
        )
    )
    events: list[dict[str, Any]] = []
    for event in raw_events:
        normalized = re.sub(r"\s+", " ", str(event.get("remark") or "")).strip().upper()
        if normalized in {"OWNER FOR PL/SQL", "CHECK LEASE OWNER GROUP"}:
            category = "administrative"
        elif "SUSPEND" in normalized or "SUSPENSION" in normalized:
            category = "suspension"
        elif any(term in normalized for term in ("LEASE STATUS", "TERMINAT", "RELINQUISH", "EXPIR")):
            category = "lease_status"
        elif any(term in normalized for term in ("OWNER", "OPERATOR", "ASSIGN", "DESIGNAT", "CHANGED ITS NAME")):
            category = "ownership_operator"
        elif any(term in normalized for term in ("DRILL", "OPERAT", "PRODUC", "WELL", "PLAN")):
            category = "operations"
        else:
            category = "other"
        token = "|".join(str(event.get(key) or "") for key in ("lease_number", "event_date", "remark_order", "remark"))
        events.append({"event_id": hashlib.md5(token.encode("utf-8")).hexdigest(), **event, "category": category})
    administrative_count = sum(event["category"] == "administrative" for event in events)
    visible = events if include_administrative else [event for event in events if event["category"] != "administrative"]
    offset = (page - 1) * page_size
    descriptions = _records(
        duckdb_df(
            f"""
            SELECT
                TRIM(LEASE_NUMBER) AS lease_number,
                NULLIF(TRIM(LEASE_DESC), '') AS description,
                NULLIF(TRIM(PROT_NAME), '') AS protraction_name,
                NULLIF(TRIM(PROT_NUMBER), '') AS protraction_number,
                NULLIF(TRIM(BLOCK_NUMBER), '') AS block_number,
                LSE_DESC_EFF_DT AS effective_date,
                NULLIF(TRIM(DESC_STATUS_CODE), '') AS status_code
            FROM {parquet_sql(data_dir, "lease_descriptions")}
            WHERE UPPER(TRIM(LEASE_NUMBER)) = ?
            ORDER BY CASE WHEN UPPER(TRIM(DESC_STATUS_CODE)) = 'C' THEN 0 ELSE 1 END,
                     LSE_DESC_EFF_DT DESC NULLS LAST, LEASE_DESC
            """,
            [normalized_lease],
        )
    )
    return {
        "lease_number": normalized_lease,
        "legal_descriptions": descriptions,
        "latest_event": visible[0] if visible else None,
        "events": visible[offset : offset + page_size],
        "page": page,
        "page_size": page_size,
        "total_count": len(visible),
        "administrative_count": administrative_count,
        "include_administrative": include_administrative,
    }


def trajectory_analysis(
    data_dir: Path,
    api_well_number: str,
    min_step: float = 100.0,
    limit: int = 100,
) -> dict[str, Any]:
    _require(data_dir, "azimuth")
    frame = duckdb_df(
        f"""
        SELECT * FROM {parquet_sql(data_dir, "azimuth")}
        WHERE "API Number" = ?
        ORDER BY MD
        """,
        [api_well_number],
    )
    return dls_analysis(frame, min_step, limit)


def casing_versions(data_dir: Path, api_well_number: str) -> dict[str, Any]:
    _require(data_dir, "apd_main", "apd_casing_intervals", "war_main", "war_tubular")
    apd = _records(
        duckdb_df(
            f"""
            SELECT DISTINCT permit.SN_APD AS record_id,
                   permit.APD_STATUS_DT AS record_date,
                   permit.PERMIT_TYPE AS record_type
            FROM {parquet_sql(data_dir, "apd_main")} AS permit
            JOIN {parquet_sql(data_dir, "apd_casing_intervals")} AS interval
              ON permit.SN_APD = interval.SN_APD_FK
            WHERE permit.API_WELL_NUMBER = ?
            ORDER BY record_date DESC NULLS LAST, record_id DESC
            """,
            [api_well_number],
        )
    )
    war = _records(
        duckdb_df(
            f"""
            SELECT DISTINCT war.SN_WAR AS record_id,
                   COALESCE(war.WAR_END_DT, war.WAR_START_DT) AS record_date,
                   'WAR' AS record_type
            FROM {parquet_sql(data_dir, "war_main")} AS war
            JOIN {parquet_sql(data_dir, "war_tubular")} AS casing
              ON war.SN_WAR = casing.SN_WAR_FK
            WHERE war.API_WELL_NUMBER = ?
            ORDER BY record_date DESC NULLS LAST, record_id DESC
            """,
            [api_well_number],
        )
    )
    for rows in (apd, war):
        for index, row in enumerate(rows, start=1):
            row["version"] = index
    return {"apd": apd, "war": war}


def _casing_validation(rows: list[dict[str, Any]]) -> dict[str, Any]:
    problems = []
    for index, row in enumerate(rows):
        issues = []
        if row.get("top_depth") is None:
            issues.append("missing_top_depth")
        if row.get("bottom_depth") is None:
            issues.append("missing_bottom_depth")
        if row.get("top_depth") is not None and row.get("bottom_depth") is not None and row["bottom_depth"] <= row["top_depth"]:
            issues.append("invalid_depth_order")
        if row.get("casing_size_source") is None:
            issues.append("missing_casing_size")
        elif row["casing_size_source"] <= 0:
            issues.append("non_positive_casing_size")
        if issues:
            problems.append({"row_index": index, "issues": issues})
    return {"problem_row_count": len(problems), "problems": problems}


def casing_analysis(
    data_dir: Path,
    api_well_number: str,
    source: str,
    version: int,
    units: str = "feet",
) -> dict[str, Any] | None:
    versions = casing_versions(data_dir, api_well_number)[source]
    if version > len(versions):
        return None
    selected = versions[version - 1]
    record_id = selected["record_id"]
    if source == "apd":
        _require(data_dir, "apd_casing_sections")
        frame = duckdb_df(
            f"""
            SELECT permit.SN_APD AS record_id,
                   permit.APD_STATUS_DT AS record_date,
                   interval.CSNG_INTV_NUM AS interval_number,
                   interval.CSNG_INTV_TYPE_CD AS interval_type_code,
                   interval.CSNG_INTV_NAME AS interval_name,
                   interval.CSNG_HOLESIZE AS hole_size_source,
                   section.CASING_SIZE AS casing_size_source,
                   section.CASING_WEIGHT AS casing_weight_source,
                   section.CASING_GRADE AS casing_grade,
                   interval.CSNG_TOP_MD AS top_depth,
                   section.CASING_SECTION_MD AS bottom_depth,
                   section.CASING_SECTION_TVD AS bottom_tvd,
                   interval.SN_APD_CSG_INTV AS _cement_key,
                   interval.CSNG_CEMENT_VOL AS cement_volume_source,
                   section.CASING_BURST_PSI AS burst_psi,
                   section.CASING_COLLPSE_PSI AS collapse_psi
            FROM {parquet_sql(data_dir, "apd_main")} AS permit
            JOIN {parquet_sql(data_dir, "apd_casing_intervals")} AS interval
              ON permit.SN_APD = interval.SN_APD_FK
            LEFT JOIN {parquet_sql(data_dir, "apd_casing_sections")} AS section
              ON interval.SN_APD_CSG_INTV = section.SN_APD_CSNG_INTV_FK
            WHERE permit.API_WELL_NUMBER = ? AND permit.SN_APD = ?
            ORDER BY interval.CSNG_INTV_NUM, section.CASING_SECTION_NUM
            """,
            [api_well_number, record_id],
        )
    else:
        _require(data_dir, "war_tubular_prop")
        frame = duckdb_df(
            f"""
            SELECT war.SN_WAR AS record_id,
                   COALESCE(war.WAR_END_DT, war.WAR_START_DT) AS record_date,
                   NULL::BIGINT AS interval_number,
                   summary.CSNG_INTV_TYPE_CD AS interval_type_code,
                   NULL::VARCHAR AS interval_name,
                   summary.CSNG_HOLE_SIZE AS hole_size_source,
                   summary.CASING_SIZE AS casing_size_source,
                   summary.CASING_WEIGHT AS casing_weight_source,
                   summary.CASING_GRADE AS casing_grade,
                   property.CSNG_SETTING_TOP_MD AS top_depth,
                   property.CSNG_SETTING_BOTM_MD AS bottom_depth,
                   NULL::DOUBLE AS bottom_tvd,
                   summary.SN_WAR_CSNG_INTV AS _cement_key,
                   summary.CSNG_CEMENT_VOL AS cement_volume_source,
                   summary.CSNG_LINER_TEST_PRSS AS burst_psi,
                   summary.CSNG_SHOE_TEST_PRSS AS collapse_psi
            FROM {parquet_sql(data_dir, "war_main")} AS war
            JOIN {parquet_sql(data_dir, "war_tubular")} AS summary
              ON war.SN_WAR = summary.SN_WAR_FK
            LEFT JOIN {parquet_sql(data_dir, "war_tubular_prop")} AS property
              ON CAST(summary.SN_WAR_CSNG_INTV AS VARCHAR) = property.SN_WAR_CSNG_INTV_FK
             AND summary.SN_WAR_FK = property.SN_WAR_FK
            WHERE war.API_WELL_NUMBER = ? AND war.SN_WAR = ?
            ORDER BY property.CSNG_SETTING_BOTM_MD NULLS LAST, summary.SN_WAR_CSNG_INTV
            """,
            [api_well_number, record_id],
        )
    rows = _records(frame)
    if units == "meters":
        for row in rows:
            for field in ("top_depth", "bottom_depth", "bottom_tvd"):
                if row[field] is not None:
                    row[field] *= 0.3048
    depths = [row["bottom_depth"] for row in rows if row["bottom_depth"] is not None]
    grades = sorted({row["casing_grade"] for row in rows if row["casing_grade"]})
    cement: dict[str, float] = {}
    for index, row in enumerate(rows):
        key = str(row.pop("_cement_key", index))
        if row["cement_volume_source"] is not None:
            cement.setdefault(key, row["cement_volume_source"])
    return {
        "source": source,
        "version": version,
        "record_id": record_id,
        "record_date": selected["record_date"],
        "units": units,
        "summary": {
            "string_count": len(rows),
            "maximum_depth": max(depths) if depths else None,
            "casing_grades": grades,
            "total_cement_volume_source": sum(cement.values()),
        },
        "validation": _casing_validation(rows),
        "rows": rows,
    }


def well_casing_page(data_dir: Path, api_well_number: str, page: int, page_size: int) -> dict[str, Any]:
    _require(data_dir, "apd_main", "apd_casing_intervals", "apd_casing_sections")
    frame = duckdb_df(
        f"""
        SELECT permit.SN_APD AS permit_id,
               permit.PERMIT_TYPE AS permit_type,
               permit.APD_STATUS_DT AS permit_status_date,
               interval.CSNG_INTV_NUM AS interval_number,
               interval.CSNG_INTV_TYPE_CD AS interval_type_code,
               interval.CSNG_INTV_NAME AS interval_name,
               interval.CSNG_HOLESIZE AS hole_size_source,
               interval.CSNG_MUD_WGT_PPG AS mud_weight_ppg,
               interval.CSNG_FRAC_GRAD_PPG AS frac_gradient_ppg,
               interval.CSNG_TOP_MD AS top_md_ft,
               interval.CSNG_CEMENT_VOL AS cement_volume_source,
               section.CASING_SECTION_NUM AS section_number,
               section.CASING_SIZE AS casing_size_source,
               section.CASING_WEIGHT AS casing_weight_source,
               section.CASING_GRADE AS casing_grade,
               section.CASING_BURST_PSI AS burst_psi,
               section.CASING_COLLPSE_PSI AS collapse_psi,
               section.CASING_SECTION_MD AS section_md_ft,
               section.CASING_SECTION_TVD AS section_tvd_ft,
               section.CASING_PORE_PRSS_PPG AS pore_pressure_ppg
        FROM {parquet_sql(data_dir, "apd_main")} AS permit
        JOIN {parquet_sql(data_dir, "apd_casing_intervals")} AS interval
          ON permit.SN_APD = interval.SN_APD_FK
        LEFT JOIN {parquet_sql(data_dir, "apd_casing_sections")} AS section
          ON interval.SN_APD_CSG_INTV = section.SN_APD_CSNG_INTV_FK
        WHERE permit.API_WELL_NUMBER = ?
        ORDER BY permit_id, interval_number NULLS LAST, section_number NULLS LAST
        """,
        [api_well_number],
    )
    return _page(frame, page, page_size)


def well_permits_page(data_dir: Path, api_well_number: str, page: int, page_size: int) -> dict[str, Any]:
    _require(data_dir, "apd_main", "attachments")
    frame = duckdb_df(
        f"""
        SELECT * FROM (
            SELECT 'permit' AS record_kind,
                   'APD' AS source,
                   permit.SN_APD AS permit_id,
                   permit.PERMIT_TYPE AS permit_type,
                   permit.APD_STATUS_DT AS status_date,
                   permit.REQ_SPUD_DATE AS requested_spud_date,
                   permit.BUS_ASC_NAME AS operator_name,
                   permit.RIG_NAME AS rig_name,
                   NULL::VARCHAR AS attachment_name,
                   NULL::VARCHAR AS attachment_extension,
                   1::BIGINT AS duplicate_count
            FROM {parquet_sql(data_dir, "apd_main")} AS permit
            WHERE permit.API_WELL_NUMBER = ?

            UNION ALL

            SELECT 'attachment' AS record_kind,
                   attachment.Source AS source,
                   NULL::VARCHAR AS permit_id,
                   NULL::VARCHAR AS permit_type,
                   NULL::VARCHAR AS status_date,
                   NULL::VARCHAR AS requested_spud_date,
                   attachment.BUS_ASC_NAME AS operator_name,
                   NULL::VARCHAR AS rig_name,
                   attachment.ATT_NAME AS attachment_name,
                   attachment.ATT_EXTENSION AS attachment_extension,
                   COUNT(*) AS duplicate_count
            FROM {parquet_sql(data_dir, "attachments")} AS attachment
            WHERE attachment.API_WELL_NUMBER = ?
            GROUP BY ALL
        ) AS permits
        ORDER BY record_kind DESC, status_date DESC NULLS LAST, source,
                 attachment_name NULLS LAST, permit_id NULLS LAST
        """,
        [api_well_number, api_well_number],
    )
    return _page(frame, page, page_size)


def well_files_page(data_dir: Path, api_well_number: str, page: int, page_size: int) -> dict[str, Any]:
    _require(data_dir, "frs")
    frame = duckdb_df(
        f"""
        SELECT DOC_ID AS document_id,
               DOC_TYPE AS document_type,
               FILE_EXT AS file_extension,
               RUN_DATE AS run_date,
               FILE_SIZE AS file_size_source,
               LOG_PKG_VOLUME AS log_package_volume,
               LOG_SOURCE AS log_source,
               BARCODE_ID AS barcode_id,
               RELEASABLE_DATE AS releasable_date,
               CREATED_DATE AS created_date,
               LEASE AS lease_number,
               AREA AS area,
               BLOCK AS block
        FROM {parquet_sql(data_dir, "frs")}
        WHERE API = ?
        ORDER BY created_date DESC NULLS LAST, document_id
        """,
        [api_well_number],
    )
    return _page(frame, page, page_size)


def well_war_page(data_dir: Path, repo: Path, api_well_number: str, page: int, page_size: int) -> dict[str, Any]:
    _require(data_dir, "war_main", "war_text")
    frame = duckdb_df(
        f"""
        SELECT main.SN_WAR AS report_id,
               main.WAR_START_DT AS start_date,
               main.WAR_END_DT AS end_date,
               main.RIG_NAME AS rig_name,
               main.BUS_ASC_NAME AS operator_name,
               main.MMS_COMPANY_NUM AS company_number,
               main.WATER_DEPTH AS water_depth_ft,
               main.RKB_ELEVATION AS rkb_elevation_ft,
               main.BOP_TEST_DATE AS bop_test_date,
               main.RAM_TST_PRSS AS ram_test_pressure_source,
               main.ANNULAR_TST_PRSS AS annular_test_pressure_source,
               remarks.TEXT_REMARK AS activity_remark
        FROM {parquet_sql(data_dir, "war_main")} AS main
        LEFT JOIN {parquet_sql(data_dir, "war_text")} AS remarks
          ON main.SN_WAR = remarks.SN_WAR
        WHERE main.API_WELL_NUMBER = ?
        ORDER BY start_date ASC NULLS LAST, report_id
        """,
        [api_well_number],
    )
    result = _page(frame, page, page_size)
    available = war_report_path(repo, api_well_number) is not None
    for row in result["rows"]:
        row["report_available"] = available
    return result


def well_war_record(data_dir: Path, repo: Path, api_well_number: str, report_id: str) -> dict[str, Any] | None:
    result = well_war_page(data_dir, repo, api_well_number, 1, 1_000_000)
    for row in result["rows"]:
        if str(row["report_id"]) == str(report_id):
            return row
    return None


def war_report_path(repo: Path, api_well_number: str) -> Path | None:
    if not api_well_number.isdigit() or len(api_well_number) != 12:
        return None
    candidates = (
        repo / "files" / "war_documents" / f"api_{api_well_number[:4]}" / f"WAR_{api_well_number}.txt",
        repo / "files" / f"api_{api_well_number[:4]}" / f"WAR_{api_well_number}.txt",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    return None


def war_report_text(repo: Path, api_well_number: str, max_chars: int | None = None) -> dict[str, Any]:
    path = war_report_path(repo, api_well_number)
    if path is None:
        raise FileNotFoundError(f"WAR report text is unavailable for {api_well_number}")
    text = path.read_text(encoding="utf-8", errors="replace")
    truncated = max_chars is not None and max_chars > 0 and len(text) > max_chars
    return {
        "api_well_number": api_well_number,
        "path": str(path),
        "character_count": len(text),
        "truncated": truncated,
        "text": text[:max_chars] if truncated and max_chars is not None else text,
    }


def field_well_selection(data_dir: Path, requested_fields: list[str]) -> dict[str, Any]:
    from well_research_current import _resolve_fields

    _require(data_dir, "boreholes", "azimuth")
    resolved, missing = _resolve_fields(data_dir, requested_fields)
    if not resolved:
        return {"fields": [], "missing_fields": missing, "totals": {}, "wells": []}
    placeholders = ", ".join("?" for _ in resolved)
    wells = duckdb_df(
        f"""
        WITH trajectory_counts AS (
            SELECT "API Number" AS api_well_number, COUNT(*) AS trajectory_station_count
            FROM {parquet_sql(data_dir, "azimuth")}
            WHERE "API Number" IS NOT NULL
            GROUP BY "API Number"
        )
        SELECT borehole.API_WELL_NUMBER AS api_well_number,
               NULLIF(TRIM(CONCAT_WS(' ', borehole.WELL_NAME, borehole.WELL_NAME_SUFFIX)), '') AS well_name,
               borehole.COMPANY_NAME AS operator,
               COALESCE(NULLIF(TRIM(borehole."OPERATOR FIELD"), ''), NULLIF(TRIM(borehole.FIELD), ''), borehole.BOTM_FLD_NAME_CD) AS field_name,
               TRIM(borehole.FIELD) AS field_code,
               borehole.WELL_TYPE_CODE AS well_type,
               borehole.BOREHOLE_STAT_CD AS status,
               borehole.WATER_DEPTH AS water_depth_ft,
               borehole.SURF_LATITUDE AS surface_latitude,
               borehole.SURF_LONGITUDE AS surface_longitude,
               COALESCE(trajectory.trajectory_station_count, 0) AS trajectory_station_count
        FROM {parquet_sql(data_dir, "boreholes")} AS borehole
        LEFT JOIN trajectory_counts AS trajectory
          ON borehole.API_WELL_NUMBER = trajectory.api_well_number
        WHERE UPPER(TRIM(borehole.FIELD)) IN ({placeholders})
        ORDER BY field_name, api_well_number
        """,
        [value.upper() for value in resolved],
    )
    options = [row for row in field_options(data_dir) if str(row["field_code"]).casefold() in {value.casefold() for value in resolved}]
    return {
        "fields": options,
        "missing_fields": missing,
        "totals": {
            "recorded_well_count": int(len(wells)),
            "trajectory_well_count": int((wells["trajectory_station_count"] > 0).sum()),
            "source_station_count": int(wells["trajectory_station_count"].sum()),
        },
        "wells": _records(wells),
    }


def field_trajectory_comparison(
    data_dir: Path,
    requested_fields: list[str],
    api_well_numbers: list[str],
) -> dict[str, Any]:
    from well_research_current import _resolve_fields

    _require(data_dir, "boreholes", "azimuth", "structures")
    resolved, missing = _resolve_fields(data_dir, requested_fields)
    if not resolved or not api_well_numbers:
        return {"fields": [], "missing_fields": missing, "totals": {}, "wells": [], "structures": []}
    field_marks = ", ".join("?" for _ in resolved)
    api_marks = ", ".join("?" for _ in api_well_numbers)
    parameters = [*[value.upper() for value in resolved], *api_well_numbers]
    wells = _records(
        duckdb_df(
            f"""
            SELECT API_WELL_NUMBER AS api_well_number,
                   NULLIF(TRIM(CONCAT_WS(' ', WELL_NAME, WELL_NAME_SUFFIX)), '') AS well_name,
                   COMPANY_NAME AS operator,
                   COALESCE(NULLIF(TRIM("OPERATOR FIELD"), ''), NULLIF(TRIM(FIELD), ''), BOTM_FLD_NAME_CD) AS field_name,
                   TRIM(FIELD) AS field_code,
                   WELL_TYPE_CODE AS well_type,
                   BOREHOLE_STAT_CD AS status,
                   WATER_DEPTH AS water_depth_ft
            FROM {parquet_sql(data_dir, "boreholes")}
            WHERE UPPER(TRIM(FIELD)) IN ({field_marks})
              AND TRIM(API_WELL_NUMBER) IN ({api_marks})
            ORDER BY field_name, api_well_number
            """,
            parameters,
        )
    )
    trajectory = _records(
        duckdb_df(
            f"""
            WITH selected AS (
                SELECT API_WELL_NUMBER FROM {parquet_sql(data_dir, "boreholes")}
                WHERE UPPER(TRIM(FIELD)) IN ({field_marks})
                  AND TRIM(API_WELL_NUMBER) IN ({api_marks})
            )
            SELECT survey."API Number" AS api_well_number,
                   survey.MD AS measured_depth_ft,
                   survey.TVD AS tvd_ft,
                   survey."Deviation Angle" AS inclination_deg,
                   survey.Azimuth AS azimuth_deg
            FROM {parquet_sql(data_dir, "azimuth")} AS survey
            JOIN selected ON survey."API Number" = selected.API_WELL_NUMBER
            ORDER BY api_well_number, measured_depth_ft NULLS LAST
            """,
            parameters,
        )
    )
    by_well: dict[str, list[dict[str, Any]]] = {}
    for station in trajectory:
        api = str(station.pop("api_well_number"))
        station["is_artificial_origin"] = False
        by_well.setdefault(api, []).append(station)
    for well in wells:
        stations = by_well.get(str(well["api_well_number"]), [])
        if stations and (stations[0]["measured_depth_ft"] or 0) > 0:
            stations.insert(0, {"measured_depth_ft": 0.0, "tvd_ft": 0.0, "inclination_deg": 0.0, "azimuth_deg": 0.0, "is_artificial_origin": True})
        well["trajectory"] = stations
    structure_marks = ", ".join("?" for _ in resolved)
    structures = _records(
        duckdb_df(
            f"""
            SELECT FIELD_NAME_CODE AS field_code,
                   STRUCTURE_NAME AS structure_name,
                   STRUCTURE_NUMBER AS structure_number,
                   STRUC_TYPE_CODE AS structure_type,
                   BUS_ASC_NAME AS operator,
                   COMPLEX_ID_NUM AS complex_id,
                   MAJ_STRUC_FLAG AS major_structure_flag,
                   INSTALL_DATE AS install_date,
                   REMOVAL_DATE AS removal_date,
                   MANNED_24_HR_FL AS manned_24_hour_flag,
                   WATER_DEPTH AS water_depth_ft
            FROM {parquet_sql(data_dir, "structures")}
            WHERE UPPER(TRIM(FIELD_NAME_CODE)) IN ({structure_marks})
            ORDER BY field_code, structure_name, structure_number
            """,
            [value.upper() for value in resolved],
        )
    )
    options = [row for row in field_options(data_dir) if str(row["field_code"]).casefold() in {value.casefold() for value in resolved}]
    return {
        "fields": options,
        "missing_fields": missing,
        "totals": {
            "recorded_well_count": len(wells),
            "trajectory_well_count": sum(bool(well["trajectory"]) for well in wells),
            "missing_trajectory_count": sum(not bool(well["trajectory"]) for well in wells),
            "source_station_count": len(trajectory),
            "plotted_point_count": sum(len(well["trajectory"]) for well in wells),
            "structure_count": len(structures),
        },
        "wells": wells,
        "structures": structures,
    }
