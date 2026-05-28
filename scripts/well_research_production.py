"""Production and completion reconciliation helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from well_research_config import *
from well_research_core import *


def build_production_summary(data_dir: Path, api: str, group_by: dict[str, str] | None = None) -> dict[str, Any]:
    cols = [
        "Api Well Number",
        "Production Date",
        "Days On Prod",
        "Product Code",
        "Monthly Oil Volume",
        "Monthly Gas Volume",
        "Monthly Water Volume",
        "Well Status Code",
        "Completion Name",
        "Operator Name",
        "Production Interval Code",
        "First Production Date",
    ]
    prod = query_api_dataset(data_dir, "production", "Api Well Number", api, columns=cols, order_by="Production Date")
    if prod.empty:
        summary = {
            "records": 0,
            "date_range": None,
            "units": PRODUCTION_UNITS,
            "totals": {},
            "peak_months": {},
            "sample": [],
        }
        if group_by:
            summary["time_series"] = empty_production_time_series(api, group_by)
        return summary
    if "Production Date" in prod.columns:
        prod = prod.sort_values("Production Date")
    totals = {}
    peak_months = {}
    for col in ["Monthly Oil Volume", "Monthly Gas Volume", "Monthly Water Volume", "Days On Prod"]:
        if col in prod.columns:
            values = pd.to_numeric(prod[col], errors="coerce").fillna(0)
            totals[col] = float(values.sum())
            if col.startswith("Monthly") and not values.empty:
                idx = values.idxmax()
                peak_months[col] = {
                    "date": prod.loc[idx, "Production Date"] if "Production Date" in prod.columns else None,
                    "value": float(values.loc[idx]),
                }
    summary = {
        "records": int(len(prod)),
        "date_range": date_range(prod, "Production Date"),
        "first_production_date": date_range(prod, "First Production Date")["first"]
        if date_range(prod, "First Production Date")
        else None,
        "units": PRODUCTION_UNITS,
        "totals": totals,
        "peak_months": peak_months,
        "status_codes": sorted([str(v) for v in prod["Well Status Code"].dropna().unique()])
        if "Well Status Code" in prod.columns
        else [],
        "completion_count": int(prod["Completion Name"].nunique()) if "Completion Name" in prod.columns else 0,
        "sample": top_rows(
            prod,
            [
                "Production Date",
                "Completion Name",
                "Product Code",
                "Monthly Oil Volume",
                "Monthly Gas Volume",
                "Monthly Water Volume",
                "Well Status Code",
            ],
            8,
        ),
    }
    if group_by:
        summary["time_series"] = build_production_time_series(data_dir, api, group_by)
    return summary


def empty_production_time_series(api: str, group_by: dict[str, str]) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "kind": "production_time_series",
        "api_well_number": norm_api(api),
        "grain": "monthly",
        "x": {"field": "period_start", "type": "date"},
        "group_by": group_by,
        "units": PRODUCTION_UNITS,
        "metrics": PRODUCTION_TIME_SERIES_METRICS,
        "records": 0,
        "groups": [],
        "points": [],
    }


def build_production_time_series(data_dir: Path, api: str, group_by: dict[str, str]) -> dict[str, Any]:
    path = parquet_path(data_dir, "production")
    if not path.exists():
        return empty_production_time_series(api, group_by)

    group_col = group_by["source_column"]
    target = norm_api(api)
    sql = f"""
        SELECT
            CAST(date_trunc('month', "Production Date") AS DATE) AS period_start,
            coalesce(nullif(trim(CAST("{group_col}" AS VARCHAR)), ''), 'Unspecified') AS group_value,
            sum(coalesce(TRY_CAST("Monthly Oil Volume" AS DOUBLE), 0)) AS oil_volume,
            sum(coalesce(TRY_CAST("Monthly Gas Volume" AS DOUBLE), 0)) AS gas_volume,
            sum(coalesce(TRY_CAST("Monthly Water Volume" AS DOUBLE), 0)) AS water_volume,
            sum(coalesce(TRY_CAST("Injection Volume" AS DOUBLE), 0)) AS injection_volume,
            sum(coalesce(TRY_CAST("Days On Prod" AS DOUBLE), 0)) AS days_on_prod,
            count(*) AS source_row_count
        FROM {parquet_sql(data_dir, "production")}
        WHERE {api_match_sql("Api Well Number")}
          AND "Production Date" IS NOT NULL
        GROUP BY 1, 2
        ORDER BY 1, 2
    """
    df = duckdb_df(sql, [target, target, target])
    result = empty_production_time_series(api, group_by)
    if df.empty:
        return result

    points = []
    for _, row in df.iterrows():
        days = float(row.get("days_on_prod") or 0)
        oil = float(row.get("oil_volume") or 0)
        gas = float(row.get("gas_volume") or 0)
        water = float(row.get("water_volume") or 0)
        points.append(
            {
                "period_start": pd.to_datetime(row["period_start"]).date().isoformat(),
                "group": str(row["group_value"]),
                "oil_volume": oil,
                "gas_volume": gas,
                "water_volume": water,
                "injection_volume": float(row.get("injection_volume") or 0),
                "days_on_prod": days,
                "oil_rate": oil / days if days else None,
                "gas_rate": gas / days if days else None,
                "water_rate": water / days if days else None,
                "source_row_count": int(row.get("source_row_count") or 0),
            }
        )

    result["records"] = len(points)
    result["groups"] = sorted({point["group"] for point in points})
    result["points"] = points
    return result


def build_completion_reconciliation(data_dir: Path, api: str, limit: int) -> dict[str, Any]:
    target = norm_api(api)
    result = {
        "records": 0,
        "interpretation": (
            "Production completions are reporting/allocation identifiers; EOR completions are physical "
            "wellbore/reservoir completion records. Compare them side-by-side, do not merge blindly."
        ),
        "production_source": "df_gom_production.parquet",
        "eor_sources": [
            "df_eor_mv_eor_mainquery.parquet",
            "df_eor_mv_eor_completions.parquet",
            "df_eor_mv_eor_completionsprop.parquet",
        ],
        "production": {
            "records": 0,
            "units": PRODUCTION_UNITS,
            "completion_names": [],
            "product_codes": [],
            "production_interval_codes": [],
            "combinations": [],
        },
        "eor": {
            "records": 0,
            "well_completion_ids": [],
            "intervals": [],
            "completion_status_codes": [],
            "reservoir_names": [],
            "completion_interval_names": [],
            "completions": [],
        },
        "comparison": {},
    }

    if parquet_path(data_dir, "production").exists():
        prod_sql = f"""
            SELECT
                coalesce(nullif(trim(CAST("Completion Name" AS VARCHAR)), ''), 'Unspecified') AS completion_name,
                coalesce(nullif(trim(CAST("Product Code" AS VARCHAR)), ''), 'Unspecified') AS product_code,
                coalesce(
                    nullif(trim(CAST("Production Interval Code" AS VARCHAR)), ''),
                    'Unspecified'
                ) AS production_interval_code,
                count(*) AS source_row_count,
                min(CAST("Production Date" AS DATE)) AS first_production_date,
                max(CAST("Production Date" AS DATE)) AS last_production_date,
                sum(coalesce(TRY_CAST("Monthly Oil Volume" AS DOUBLE), 0)) AS oil_volume,
                sum(coalesce(TRY_CAST("Monthly Gas Volume" AS DOUBLE), 0)) AS gas_volume,
                sum(coalesce(TRY_CAST("Monthly Water Volume" AS DOUBLE), 0)) AS water_volume
            FROM {parquet_sql(data_dir, "production")}
            WHERE {api_match_sql("Api Well Number")}
            GROUP BY 1, 2, 3
            ORDER BY 1, 2, 3
        """
        prod = duckdb_df(prod_sql, [target, target, target])
        if not prod.empty:
            combinations = top_rows(prod, None, limit)
            interval_codes = sorted(str(v) for v in prod["production_interval_code"].dropna().unique())
            result["production"] = {
                "records": int(len(prod)),
                "units": PRODUCTION_UNITS,
                "completion_names": sorted(str(v) for v in prod["completion_name"].dropna().unique()),
                "product_codes": sorted(str(v) for v in prod["product_code"].dropna().unique()),
                "production_interval_codes": interval_codes,
                "combinations": combinations,
            }

    eor_ready = all(
        parquet_path(data_dir, key).exists() for key in ["eor_main", "eor_completions", "eor_completions_prop"]
    )
    if eor_ready:
        eor_sql = f"""
            SELECT DISTINCT
                comp.SN_EOR_WELL_COMP AS well_completion_id,
                comp.INTERVAL AS interval_code,
                comp.COMP_STATUS_CD AS completion_status_code,
                prop.COMP_RSVR_NAME AS reservoir_name,
                prop.COMP_INTERVAL_NAME AS completion_interval_name
            FROM {parquet_sql(data_dir, "eor_main")} main
            JOIN {parquet_sql(data_dir, "eor_completions")} comp
                ON main.SN_EOR = comp.SN_EOR_FK
            LEFT JOIN {parquet_sql(data_dir, "eor_completions_prop")} prop
                ON comp.SN_EOR_FK = prop.SN_EOR_FK
               AND comp.SN_EOR_WELL_COMP = prop.SN_EOR_WELL_COMP
            WHERE {api_match_sql("API_WELL_NUMBER").replace('"API_WELL_NUMBER"', 'main.API_WELL_NUMBER')}
            ORDER BY 1, 2
        """
        eor = duckdb_df(eor_sql, [target, target, target])
        if not eor.empty:
            result["eor"] = {
                "records": int(len(eor)),
                "well_completion_ids": sorted(str(v) for v in eor["well_completion_id"].dropna().unique()),
                "intervals": sorted(str(v) for v in eor["interval_code"].dropna().unique()),
                "completion_status_codes": sorted(str(v) for v in eor["completion_status_code"].dropna().unique()),
                "reservoir_names": sorted(str(v) for v in eor["reservoir_name"].dropna().unique()),
                "completion_interval_names": sorted(str(v) for v in eor["completion_interval_name"].dropna().unique()),
                "completions": top_rows(eor, None, limit),
            }

    prod_intervals = set(result["production"]["production_interval_codes"])
    eor_intervals = set(result["eor"]["intervals"])
    result["records"] = int(result["production"]["records"] + result["eor"]["records"])
    result["comparison"] = {
        "has_production_completion_data": bool(result["production"]["records"]),
        "has_eor_completion_data": bool(result["eor"]["records"]),
        "shared_interval_codes": sorted(prod_intervals & eor_intervals),
        "production_interval_codes_not_in_eor": sorted(prod_intervals - eor_intervals),
        "eor_interval_codes_not_in_production": sorted(eor_intervals - prod_intervals),
    }
    return result
