"""Standalone decommissioning authority and asset drill-down queries."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from well_research_core import duckdb_df, parquet_path, parquet_sql, top_rows


TOTAL_TYPE_MAP = {
    "Wells Decom Cost": ("well_abandonment", "installed"),
    "Wells (Proposed) Decom Cost": ("well_abandonment", "proposed"),
    "Pipelines Decom Cost": ("pipeline_decommissioning", "installed"),
    "Pipelines (Proposed) Decom Cost": ("pipeline_decommissioning", "proposed"),
    "Platforms Decom Cost": ("platform_removal", "installed"),
    "Platforms (Proposed) Decom Cost": ("platform_removal", "proposed"),
    "Platforms Site Clear Cost": ("platform_site_clearance", "installed"),
    "Platforms (Proposed) Site Clear Cost": ("platform_site_clearance", "proposed"),
}


def _require(data_dir: Path, *keys: str) -> None:
    missing = [str(parquet_path(data_dir, key)) for key in keys if not parquet_path(data_dir, key).is_file()]
    if missing:
        raise FileNotFoundError("Missing required dataset(s): " + ", ".join(missing))


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return top_rows(frame, None, len(frame))


def _inventory_cte(data_dir: Path) -> str:
    return f"""
        raw_inventory AS (
            SELECT
                CASE
                    WHEN NULLIF(TRIM(LEASE_NUMBER), '') IS NOT NULL
                     AND LOWER(TRIM(LEASE_NUMBER)) NOT IN ('nan', '<na>') THEN 'LSE'
                    WHEN NULLIF(TRIM(ROW_NUMBER), '') IS NOT NULL
                     AND LOWER(TRIM(ROW_NUMBER)) NOT IN ('nan', '<na>') THEN 'ROW'
                    WHEN NULLIF(TRIM(RUE_NUMBER), '') IS NOT NULL
                     AND LOWER(TRIM(RUE_NUMBER)) NOT IN ('nan', '<na>') THEN 'RUE'
                END AS authority_type,
                COALESCE(
                    NULLIF(NULLIF(LOWER(TRIM(LEASE_NUMBER)), 'nan'), '<na>'),
                    NULLIF(NULLIF(LOWER(TRIM(ROW_NUMBER)), 'nan'), '<na>'),
                    NULLIF(NULLIF(LOWER(TRIM(RUE_NUMBER)), 'nan'), '<na>')
                ) AS normalized_authority_number,
                COALESCE(
                    NULLIF(NULLIF(TRIM(LEASE_NUMBER), 'nan'), '<NA>'),
                    NULLIF(NULLIF(TRIM(ROW_NUMBER), 'nan'), '<NA>'),
                    NULLIF(NULLIF(TRIM(RUE_NUMBER), 'nan'), '<NA>')
                ) AS authority_number,
                NULLIF(NULLIF(TRIM(LEASE_STATUS_CD), ''), 'nan') AS lease_status,
                BLK_MAX_WTR_DPTH AS max_water_depth_m,
                CASE TRIM(PA_ADJUSTMENT_FL) WHEN 'Y' THEN TRUE WHEN 'N' THEN FALSE END AS pa_adjustment,
                NULLIF(NULLIF(TRIM(AREA_CODE), ''), 'nan') AS area_code,
                NULLIF(NULLIF(TRIM(BLOCK_NUMBER), ''), 'nan') AS block_number,
                NULLIF(TRIM(UPDATED_DATE), '') AS updated_date,
                COALESCE(WELL_INST_DCOM_COUNT, 0) AS installed_wells,
                COALESCE(WELL_PRP_DCOM_COUNT, 0) AS proposed_wells,
                COALESCE(PTFRM_INST_DCOM_COUNT, 0) AS installed_platforms,
                COALESCE(PTFRM_PRP_DCOM_COUNT, 0) AS proposed_platform_removals,
                COALESCE(PTFRM_INST_SITE_CLRNCE_COUNT, 0) AS installed_platform_site_clearance,
                COALESCE(PTFRM_PRP_SITE_CLRNCE_COUNT, 0) AS proposed_platform_site_clearance,
                COALESCE(PPL_INST_DCOM_COUNT, 0) AS installed_pipelines,
                COALESCE(PPL_PRP_DCOM_COUNT, 0) AS proposed_pipelines
            FROM {parquet_sql(data_dir, "decom_estimates")}
        ),
        inventory AS (
            SELECT * FROM raw_inventory
            WHERE authority_type IS NOT NULL
              AND normalized_authority_number IS NOT NULL
              AND normalized_authority_number <> ''
        )
    """


def authority_search(
    data_dir: Path,
    *,
    page: int = 1,
    page_size: int = 50,
    query: str | None = None,
    authority_type: str | None = None,
    area: str | None = None,
    block: str | None = None,
) -> dict[str, Any]:
    _require(data_dir, "decom_estimates", "decom_totals")
    conditions: list[str] = []
    parameters: list[Any] = []
    if query:
        conditions.append("LOWER(a.authority_number) LIKE LOWER(?)")
        parameters.append(f"%{query}%")
    if authority_type:
        conditions.append("a.authority_type = ?")
        parameters.append(authority_type.upper())
    location_conditions: list[str] = []
    location_parameters: list[Any] = []
    if area:
        location_conditions.append("LOWER(i.area_code) = LOWER(?)")
        location_parameters.append(area)
    if block:
        location_conditions.append("LOWER(i.block_number) = LOWER(?)")
        location_parameters.append(block)
    if location_conditions:
        conditions.append(
            "a.authority_type = 'LSE' AND EXISTS (SELECT 1 FROM inventory i "
            "WHERE i.authority_type = a.authority_type "
            "AND i.normalized_authority_number = a.normalized_authority_number AND "
            + " AND ".join(location_conditions)
            + ")"
        )
        parameters.extend(location_parameters)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    cte = f"""
        WITH {_inventory_cte(data_dir)},
        total_authorities AS (
            SELECT DISTINCT UPPER(TRIM(AUTH_TYPE_CODE)) AS authority_type,
                   LOWER(TRIM(AUTH_NUMBER)) AS normalized_authority_number,
                   TRIM(AUTH_NUMBER) AS authority_number
            FROM {parquet_sql(data_dir, "decom_totals")}
            WHERE UPPER(TRIM(AUTH_TYPE_CODE)) IN ('LSE', 'ROW', 'RUE')
              AND NULLIF(TRIM(AUTH_NUMBER), '') IS NOT NULL
        ),
        authorities AS (
            SELECT DISTINCT authority_type, normalized_authority_number, authority_number FROM inventory
            UNION
            SELECT authority_type, normalized_authority_number, authority_number FROM total_authorities
        ),
        inventory_summary AS (
            SELECT authority_type, normalized_authority_number,
                   LIST_SORT(LIST(DISTINCT area_code) FILTER (WHERE area_code IS NOT NULL)) AS area_codes,
                   COUNT(*) AS location_count,
                   SUM(installed_wells + installed_platforms + installed_pipelines) AS installed_asset_count,
                   SUM(proposed_wells + proposed_platform_removals + proposed_pipelines) AS proposed_asset_count
            FROM inventory GROUP BY authority_type, normalized_authority_number
        ),
        total_summary AS (
            SELECT UPPER(TRIM(AUTH_TYPE_CODE)) AS authority_type,
                   LOWER(TRIM(AUTH_NUMBER)) AS normalized_authority_number,
                   MAX(COALESCE(P50_COST, 0) + COALESCE(P70_COST, 0) + COALESCE(P90_COST, 0) + COALESCE(DTR_COST, 0)) > 0 AS has_cost_estimate
            FROM {parquet_sql(data_dir, "decom_totals")}
            GROUP BY authority_type, normalized_authority_number
        ),
        filtered AS (SELECT a.* FROM authorities a {where})
    """
    total = duckdb_df(f"{cte} SELECT COUNT(*) AS total_count FROM filtered", parameters)
    rows = _records(
        duckdb_df(
            f"""
            {cte}
            SELECT f.authority_type, f.authority_number,
                   COALESCE(i.area_codes, []) AS area_codes,
                   COALESCE(i.location_count, 0) AS location_count,
                   COALESCE(i.installed_asset_count, 0) AS installed_asset_count,
                   COALESCE(i.proposed_asset_count, 0) AS proposed_asset_count,
                   COALESCE(t.has_cost_estimate, FALSE) AS has_cost_estimate
            FROM filtered f
            LEFT JOIN inventory_summary i USING (authority_type, normalized_authority_number)
            LEFT JOIN total_summary t USING (authority_type, normalized_authority_number)
            ORDER BY f.authority_type, f.authority_number
            LIMIT ? OFFSET ?
            """,
            [*parameters, page_size, (page - 1) * page_size],
        )
    )
    return {
        "rows": [
            {
                "authority": {"type": row["authority_type"], "number": row["authority_number"]},
                "area_codes": row["area_codes"] or [],
                "location_count": row["location_count"],
                "installed_asset_count": row["installed_asset_count"],
                "proposed_asset_count": row["proposed_asset_count"],
                "has_cost_estimate": row["has_cost_estimate"],
            }
            for row in rows
        ],
        "page": page,
        "page_size": page_size,
        "total_count": int(total.iloc[0]["total_count"]),
    }


def _cost(p50: Any, p70: Any, p90: Any, deterministic: Any) -> dict[str, Any]:
    values = {"p50": int(p50 or 0), "p70": int(p70 or 0), "p90": int(p90 or 0)}
    deterministic_value = int(deterministic or 0)
    return {
        "distribution": values,
        "deterministic": deterministic_value,
        "scenario_total": {key: value + deterministic_value for key, value in values.items()},
        "currency": "USD",
    }


def _component(kind: str, status: str, row: dict[str, Any], prefix: str) -> dict[str, Any]:
    deterministic_column = {
        "WELL_INST_DCOM": "WELL_INST_DCOM_INDTR",
        "SEGMENT_DCOM": "SEGMENT_DCOM_INDTR",
        "PLT_REMOVAL_DCOM": "PLT_REMOVAL_DCOM_INDTR",
        "PLT_SITE_CLRNC_DCOM": "PLT_SITE_CLRNC_DCOM_INDTR",
    }[prefix]
    return {
        "kind": kind,
        "status": status,
        "asset_count": 1,
        "cost": _cost(
            row.get(f"{prefix}_P50"),
            row.get(f"{prefix}_P70"),
            row.get(f"{prefix}_P90"),
            row.get(deterministic_column),
        ),
    }


def _well_assignment(row: dict[str, Any], status: str) -> dict[str, Any]:
    component = _component("well_abandonment", status, row, "WELL_INST_DCOM")
    api = row.get("API_WELL_NUMBER")
    lease = row.get("BOTM_LEASE_NUM")
    return {
        "asset_type": "well",
        "status": status,
        "identifier": str(api or f"{lease}:{row.get('WELL_NAME') or 'proposed-well'}"),
        "authority": {"type": "LSE", "number": lease},
        "name": row.get("WELL_NAME"),
        "source_status": row.get("BOREHOLE_STAT_CD"),
        "area_code": row.get("BOTM_AREA_CODE"),
        "block_number": str(row["BOTM_BLOCK_NUM"]) if row.get("BOTM_BLOCK_NUM") is not None else None,
        "effective_date": row.get("EFFECTIVE_DATE"),
        "api_well_number": api,
        "has_estimate": any(component["cost"]["scenario_total"].values()),
        "components": [component],
        "attributes": {
            "bottom_lease_number": lease,
            "surface_lease_number": row.get("SURF_LEASE_NUM"),
            "surface_area_code": row.get("SURF_AREA_CODE"),
            "surface_block_number": row.get("SURF_BLOCK_NUM"),
            "expiration_date": row.get("EXPIRATION_DATE"),
        },
    }


def _pipeline_assignment(row: dict[str, Any], status: str) -> dict[str, Any]:
    component = _component("pipeline_decommissioning", status, row, "SEGMENT_DCOM")
    segment = str(row["SEGMENT_NUM"])
    return {
        "asset_type": "pipeline",
        "status": status,
        "identifier": segment,
        "authority": {"type": row["AUTH_TYPE_CODE"], "number": row["AUTH_NUMBER"]},
        "name": row.get("ORIG_ID_NAME"),
        "source_status": row.get("STATUS_CODE"),
        "area_code": row.get("ORIG_AR_CODE"),
        "block_number": str(row["ORIG_BLK_NUM"]) if row.get("ORIG_BLK_NUM") is not None else None,
        "effective_date": row.get("EFFECTIVE_DATE"),
        "segment_number": segment,
        "has_estimate": any(component["cost"]["scenario_total"].values()),
        "components": [component],
        "attributes": {
            "origin_lease_number": row.get("ORIG_LSE_NUM"),
            "destination_lease_number": row.get("DEST_LSE_NUM"),
            "destination_area_code": row.get("DEST_AR_CODE"),
            "destination_block_number": row.get("DEST_BLK_NUM"),
            "destination_name": row.get("DEST_ID_NAME"),
            "product_code": row.get("PROD_CODE"),
            "size_code": row.get("PPL_SIZE_CODE"),
        },
    }


def _platform_assignment(row: dict[str, Any], status: str) -> dict[str, Any]:
    components = [
        _component("platform_removal", status, row, "PLT_REMOVAL_DCOM"),
        _component("platform_site_clearance", status, row, "PLT_SITE_CLRNC_DCOM"),
    ]
    complex_id = str(row["COMPLEX_ID_NUM"])
    structure_number = str(row["STRUCTURE_NUMBER"])
    return {
        "asset_type": "platform",
        "status": status,
        "identifier": f"{complex_id}:{structure_number}",
        "authority": {"type": row["AUTH_TYPE_CODE"], "number": row["AUTH_NUMBER"]},
        "name": row.get("STRUCTURE_NAME"),
        "area_code": row.get("AREA_CODE"),
        "block_number": row.get("BLOCK_NUMBER"),
        "effective_date": row.get("EFFECTIVE_DATE"),
        "complex_id": complex_id,
        "structure_number": structure_number,
        "has_estimate": any(any(component["cost"]["scenario_total"].values()) for component in components),
        "components": components,
        "attributes": {},
    }


def _assets(
    data_dir: Path,
    *,
    authority_type: str | None = None,
    authority_number: str | None = None,
    asset_type: str | None = None,
    identifier: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    assignments: list[dict[str, Any]] = []
    if asset_type in (None, "well"):
        for key, status in (("decom_spud_well", "installed"), ("decom_prop_well", "proposed")):
            _require(data_dir, key)
            conditions = []
            parameters: list[Any] = []
            if authority_number is not None:
                if authority_type != "LSE":
                    continue
                conditions.append("LOWER(TRIM(BOTM_LEASE_NUM)) = LOWER(TRIM(?))")
                parameters.append(authority_number)
            if identifier is not None:
                conditions.append("CAST(API_WELL_NUMBER AS VARCHAR) = ?")
                parameters.append(identifier[0])
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = _records(duckdb_df(f"SELECT * FROM {parquet_sql(data_dir, key)} {where} ORDER BY API_WELL_NUMBER NULLS LAST, WELL_NAME", parameters))
            assignments.extend(_well_assignment(row, status) for row in rows)
    if asset_type in (None, "pipeline"):
        for key, status in (("decom_inst_pipe", "installed"), ("decom_prop_pipe", "proposed")):
            _require(data_dir, key)
            conditions = []
            parameters = []
            if authority_type is not None and authority_number is not None:
                conditions.extend(["UPPER(TRIM(AUTH_TYPE_CODE)) = ?", "LOWER(TRIM(AUTH_NUMBER)) = LOWER(TRIM(?))"])
                parameters.extend([authority_type, authority_number])
            if identifier is not None:
                conditions.append("CAST(SEGMENT_NUM AS VARCHAR) = ?")
                parameters.append(identifier[0])
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = _records(duckdb_df(f"SELECT * FROM {parquet_sql(data_dir, key)} {where} ORDER BY SEGMENT_NUM, AUTH_TYPE_CODE, AUTH_NUMBER", parameters))
            assignments.extend(_pipeline_assignment(row, status) for row in rows)
    if asset_type in (None, "platform"):
        for key, status in (("decom_inst_plat", "installed"), ("decom_prop_plat", "proposed")):
            _require(data_dir, key)
            conditions = []
            parameters = []
            if authority_type is not None and authority_number is not None:
                conditions.extend(["UPPER(TRIM(AUTH_TYPE_CODE)) = ?", "LOWER(TRIM(AUTH_NUMBER)) = LOWER(TRIM(?))"])
                parameters.extend([authority_type, authority_number])
            if identifier is not None:
                conditions.extend(["CAST(COMPLEX_ID_NUM AS VARCHAR) = ?", "CAST(STRUCTURE_NUMBER AS VARCHAR) = ?"])
                parameters.extend(identifier)
            where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
            rows = _records(duckdb_df(f"SELECT * FROM {parquet_sql(data_dir, key)} {where} ORDER BY COMPLEX_ID_NUM, STRUCTURE_NUMBER, AUTH_TYPE_CODE, AUTH_NUMBER", parameters))
            assignments.extend(_platform_assignment(row, status) for row in rows)
    linked_wells: set[str] = set()
    linked_pipelines: set[str] = set()
    linked_platforms: set[tuple[str, str]] = set()
    if asset_type in (None, "well") and parquet_path(data_dir, "boreholes").is_file():
        linked_wells = {
            str(row["identifier"])
            for row in _records(
                duckdb_df(
                    f"SELECT DISTINCT CAST(API_WELL_NUMBER AS VARCHAR) AS identifier FROM {parquet_sql(data_dir, 'boreholes')}"
                )
            )
            if row["identifier"]
        }
    if asset_type in (None, "pipeline") and parquet_path(data_dir, "pipeline_permit_segments").is_file():
        linked_pipelines = {
            str(row["identifier"])
            for row in _records(
                duckdb_df(
                    f"SELECT DISTINCT CAST(segment_number AS VARCHAR) AS identifier FROM {parquet_sql(data_dir, 'pipeline_permit_segments')}"
                )
            )
            if row["identifier"]
        }
    if asset_type in (None, "platform") and parquet_path(data_dir, "structures").is_file():
        linked_platforms = {
            (str(row["complex_id"]), str(row["structure_number"]))
            for row in _records(
                duckdb_df(
                    f"SELECT DISTINCT CAST(COMPLEX_ID_NUM AS VARCHAR) AS complex_id, CAST(STRUCTURE_NUMBER AS VARCHAR) AS structure_number FROM {parquet_sql(data_dir, 'structures')}"
                )
            )
            if row["complex_id"] and row["structure_number"]
        }
    for assignment in assignments:
        if assignment["asset_type"] == "well":
            assignment["linkable"] = bool(
                assignment.get("api_well_number")
                and str(assignment["api_well_number"]) in linked_wells
            )
        elif assignment["asset_type"] == "pipeline":
            assignment["linkable"] = str(assignment["segment_number"]) in linked_pipelines
        else:
            assignment["linkable"] = (
                str(assignment["complex_id"]),
                str(assignment["structure_number"]),
            ) in linked_platforms
    return assignments


def authority_detail(data_dir: Path, authority_type: str, authority_number: str) -> dict[str, Any]:
    authority_type = authority_type.upper()
    _require(data_dir, "decom_estimates", "decom_totals")
    inventory_rows = _records(
        duckdb_df(
            f"""
            WITH {_inventory_cte(data_dir)}
            SELECT * FROM inventory
            WHERE authority_type = ? AND normalized_authority_number = LOWER(TRIM(?))
            ORDER BY area_code NULLS LAST, block_number NULLS LAST
            """,
            [authority_type, authority_number],
        )
    )
    inventory = [
        {
            "lease_status": row["lease_status"],
            "max_water_depth_m": row["max_water_depth_m"],
            "pa_adjustment": row["pa_adjustment"],
            "area_code": row["area_code"],
            "block_number": row["block_number"],
            "updated_date": row["updated_date"],
            "obligations": {key: row[key] for key in (
                "installed_wells", "proposed_wells", "installed_platforms",
                "proposed_platform_removals", "installed_platform_site_clearance",
                "proposed_platform_site_clearance", "installed_pipelines", "proposed_pipelines",
            )},
        }
        for row in inventory_rows
    ]
    total_rows = _records(
        duckdb_df(
            f"""
            SELECT TYPE AS source_type, SUM(CNT) AS asset_count,
                   SUM(P50_COST) AS p50, SUM(P70_COST) AS p70,
                   SUM(P90_COST) AS p90, SUM(DTR_COST) AS deterministic
            FROM {parquet_sql(data_dir, "decom_totals")}
            WHERE UPPER(TRIM(AUTH_TYPE_CODE)) = ?
              AND LOWER(TRIM(AUTH_NUMBER)) = LOWER(TRIM(?))
            GROUP BY TYPE ORDER BY TYPE
            """,
            [authority_type, authority_number],
        )
    )
    components = []
    overall = {"p50": 0, "p70": 0, "p90": 0, "deterministic": 0}
    for row in total_rows:
        mapping = TOTAL_TYPE_MAP.get(row["source_type"])
        if not mapping:
            continue
        cost = _cost(row["p50"], row["p70"], row["p90"], row["deterministic"])
        components.append({"kind": mapping[0], "status": mapping[1], "asset_count": row["asset_count"], "cost": cost})
        for key in ("p50", "p70", "p90"):
            overall[key] += cost["distribution"][key]
        overall["deterministic"] += cost["deterministic"]
    assets = _assets(data_dir, authority_type=authority_type, authority_number=authority_number)
    if not inventory and not components and not assets:
        raise KeyError("Decommissioning authority not found")
    canonical = assets[0]["authority"]["number"] if assets else authority_number.strip().upper()
    return {
        "authority": {"type": authority_type, "number": canonical},
        "inventory": inventory,
        "totals": {"cost": _cost(overall["p50"], overall["p70"], overall["p90"], overall["deterministic"]), "components": components},
        "installed_assets": [row for row in assets if row["status"] == "installed"],
        "proposed_assets": [row for row in assets if row["status"] == "proposed"],
    }


def asset_detail(data_dir: Path, asset_type: str, *identifier: str) -> dict[str, Any]:
    assignments = _assets(data_dir, asset_type=asset_type, identifier=identifier)
    if not assignments:
        raise KeyError("Decommissioning estimate not found")
    return {"asset_type": asset_type, "identifier": ":".join(identifier), "assignments": assignments}
