"""Timeline, text, logging, and field audit helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from well_research_config import *
from well_research_core import *
from well_research_search import build_filter_clause


def build_timeline(
    bore: pd.DataFrame,
    apd: pd.DataFrame,
    war_text: pd.DataFrame,
    eor_main: pd.DataFrame,
    bhp: pd.DataFrame,
    perf: pd.DataFrame,
    logging: pd.DataFrame,
    apd_casing: pd.DataFrame,
    war_casing: pd.DataFrame,
    production: dict[str, Any],
    limit: int,
) -> dict[str, Any]:
    events: list[dict[str, Any]] = []

    def add(date_value: Any, source: str, event: str, details: Any = None) -> None:
        date = parse_datetime(date_value)
        if pd.isna(date):
            return
        events.append({"date": date, "source": source, "event": event, "details": details})

    if not bore.empty:
        row = bore.iloc[0]
        add(row.get("WELL_SPUD_DATE"), "borehole", "spud", row.get("WELL_NAME"))
        add(row.get("TOTAL_DEPTH_DATE"), "borehole", "total depth", row.get("BH_TOTAL_MD"))
        add(row.get("BOREHOLE_STAT_DT"), "borehole", "borehole status", row.get("BOREHOLE_STAT_CD"))
    for _, row in apd.iterrows():
        add(row.get("APD_SUB_STATUS_DT"), "apd", "APD submission/status", row.get("PERMIT_TYPE"))
    for _, row in war_text.iterrows():
        add(row.get("WAR_START_DT"), "war", "WAR remark", clean_text(row.get("TEXT_REMARK"), 220))
    for _, row in eor_main.iterrows():
        add(
            row.get("BOREHOLE_STAT_DT"),
            "eor",
            "EOR/end-of-well report",
            clean_text(row.get("OPERATIONAL_NARRATIVE"), 220),
        )
    for _, row in bhp.iterrows():
        add(row.get("BHTST_DATE"), "bhp", "BHP survey", row.get("BHTST_PRESSURE"))
    if not perf.empty:
        events.append(
            {
                "date": pd.NaT,
                "source": "perforation",
                "event": "perforation interval records",
                "details": int(len(perf)),
            }
        )
    for _, row in logging.iterrows():
        add(row.get("Operation Date"), "logging", "open-hole logging", row.get("Logging Method"))
    for _, row in apd_casing.iterrows():
        add(row.get("Submission_Date"), "apd_casing", "planned casing submission", row.get("CASING_SIZE"))
    for _, row in war_casing.iterrows():
        add(row.get("Report_End_Date"), "war_casing", "WAR casing report", row.get("CASING_SIZE"))
    prod_range = production.get("date_range") if isinstance(production, dict) else None
    if prod_range:
        add(prod_range.get("first"), "production", "first production record", None)
        add(prod_range.get("last"), "production", "last production record", None)

    dated = sorted([e for e in events if pd.notna(e["date"])], key=lambda e: e["date"])
    undated = [e for e in events if pd.isna(e["date"])]
    ordered = dated + undated
    sample = [
        {**event, "date": event["date"].date().isoformat() if pd.notna(event["date"]) else None}
        for event in ordered[:limit]
    ]
    return {"records": int(len(ordered)), "sample": sample}


def build_war_text(data_dir: Path, war_main: pd.DataFrame, keyword: str | None) -> pd.DataFrame:
    if war_main.empty or "SN_WAR" not in war_main.columns:
        return pd.DataFrame()
    sn_wars = set(war_main["SN_WAR"].dropna().astype(str))
    if not sn_wars:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(sn_wars))
    keyword_clause = " AND lower(CAST(w.TEXT_REMARK AS VARCHAR)) LIKE lower(?)" if keyword else ""
    params = list(sn_wars) + ([f"%{keyword}%"] if keyword else [])
    war_text = duckdb_df(
        f"""
        SELECT w.SN_WAR, wm.WAR_START_DT, wm.WAR_END_DT, wm.RIG_NAME, wm.BUS_ASC_NAME, w.TEXT_REMARK
        FROM {parquet_sql(data_dir, "war_text")} w
        JOIN {parquet_sql(data_dir, "war_main")} wm ON w.SN_WAR = wm.SN_WAR
        WHERE CAST(w.SN_WAR AS VARCHAR) IN ({placeholders})
        {keyword_clause}
        ORDER BY wm.WAR_START_DT
        """,
        params,
    )
    return war_text


def build_logging(data_dir: Path, war_main: pd.DataFrame) -> pd.DataFrame:
    if war_main.empty or "SN_WAR" not in war_main.columns:
        return pd.DataFrame()
    sn_wars = [str(v) for v in war_main["SN_WAR"].dropna().astype(str)]
    if not sn_wars:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(sn_wars))
    out = duckdb_df(
        f"""
        SELECT
            runs.TOOL_LOGGING_METHOD_NAME AS "Logging Method",
            tools.LOG_TOOL_TYPE_CODE AS "Tool Type Code",
            runs.LOG_INTV_TOP_MD AS "Top MD",
            runs.LOG_INTV_BOTM_MD AS "Bottom MD",
            runs.OPERATIONS_COMPLETED_DATE AS "Operation Date"
        FROM {parquet_sql(data_dir, "open_hole_runs")} runs
        JOIN {parquet_sql(data_dir, "open_hole_tools")} tools
            ON runs.SN_OPEN_HOLE = tools.SN_OPEN_HOLE_FK
        WHERE CAST(runs.SN_WAR_FK AS VARCHAR) IN ({placeholders})
        ORDER BY runs.LOG_INTV_TOP_MD
        """,
        sn_wars,
    )
    cols = ["Logging Method", "Tool Type Code", "Top MD", "Bottom MD", "Operation Date"]
    out = out[[c for c in cols if c in out.columns]].copy()
    for col in ["Top MD", "Bottom MD"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values("Top MD") if "Top MD" in out.columns else out


def build_field_audit(data_dir: Path, field: str, limit: int) -> dict[str, Any]:
    bore = read_dataset(data_dir, "boreholes")
    if bore.empty:
        return {"field_query": field, "units": BOREHOLE_UNITS, "well_count": 0, "wells": []}
    target = field.casefold()
    haystack = pd.Series("", index=bore.index)
    for col in ["FIELD", "OPERATOR FIELD", "AREA", "BLOCK", "LEASE", "COMPANY_NAME", "WELL_NAME"]:
        if col in bore.columns:
            haystack = haystack + " " + bore[col].fillna("").astype(str)
    field_wells = bore[haystack.str.casefold().str.contains(target, na=False)].copy()
    if field_wells.empty:
        return {"field_query": field, "units": BOREHOLE_UNITS, "well_count": 0, "wells": []}

    apis = [str(api) for api in field_wells["API_WELL_NUMBER"].dropna().unique()]
    api_norms = {norm_api(api): api for api in apis}
    availability_sets = {
        "war": api_set(data_dir, "war_main", "API_WELL_NUMBER"),
        "production": api_set(data_dir, "production", "Api Well Number"),
        "trajectory": api_set(data_dir, "points", "API Number"),
        "wellpath_metrics": api_set(data_dir, "wellpath_metrics", "API Number"),
        "apd": api_set(data_dir, "apd_main", "API_WELL_NUMBER"),
        "bhp": api_set(data_dir, "bhp", "API_WELL_NUMBER"),
        "eor": api_set(data_dir, "eor_main", "API_WELL_NUMBER"),
        "attachments": api_set(data_dir, "attachments", "API_WELL_NUMBER"),
        "frs": api_set(data_dir, "frs", "API"),
    }

    rows = []
    for _, row in field_wells.iterrows():
        api = str(row.get("API_WELL_NUMBER", ""))
        n_api = norm_api(api)
        flags = {name: n_api in values for name, values in availability_sets.items()}
        rows.append(
            {
                "API_WELL_NUMBER": api_norms.get(n_api, api),
                "WELL_NAME": row.get("WELL_NAME"),
                "WELL_NAME_SUFFIX": row.get("WELL_NAME_SUFFIX"),
                "COMPANY_NAME": row.get("COMPANY_NAME"),
                "FIELD": row.get("FIELD"),
                "OPERATOR FIELD": row.get("OPERATOR FIELD"),
                "AREA": row.get("AREA"),
                "BLOCK": row.get("BLOCK"),
                "LEASE": row.get("LEASE"),
                "BH_TOTAL_MD": row.get("BH_TOTAL_MD"),
                "WATER_DEPTH": row.get("WATER_DEPTH"),
                "data_score": int(sum(flags.values())),
                "availability": flags,
            }
        )
    rows = sorted(rows, key=lambda r: (r["data_score"], r.get("BH_TOTAL_MD") or 0), reverse=True)
    return {
        "field_query": field,
        "units": BOREHOLE_UNITS,
        "well_count": int(len(rows)),
        "availability_counts": {
            name: int(sum(1 for row in rows if row["availability"][name])) for name in availability_sets
        },
        "wells": rows[:limit],
    }


def api_set(data_dir: Path, dataset: str, column: str) -> set[str]:
    df = read_dataset(data_dir, dataset, columns=[column])
    if df.empty or column not in df.columns:
        return set()
    return set(df[column].map(norm_api).dropna())
