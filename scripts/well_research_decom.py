"""Decommissioning cost and inventory helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from well_research_config import *
from well_research_core import *

DECOM_CASE_COLUMNS = {
    "p50": {
        "totals": ["P50_COST"],
        "wells": ["WELL_INST_DCOM_P50"],
        "pipelines": ["SEGMENT_DCOM_P50"],
        "platforms": ["PLT_REMOVAL_DCOM_P50", "PLT_SITE_CLRNC_DCOM_P50"],
    },
    "p70": {
        "totals": ["P70_COST"],
        "wells": ["WELL_INST_DCOM_P70"],
        "pipelines": ["SEGMENT_DCOM_P70"],
        "platforms": ["PLT_REMOVAL_DCOM_P70", "PLT_SITE_CLRNC_DCOM_P70"],
    },
    "p90": {
        "totals": ["P90_COST"],
        "wells": ["WELL_INST_DCOM_P90"],
        "pipelines": ["SEGMENT_DCOM_P90"],
        "platforms": ["PLT_REMOVAL_DCOM_P90", "PLT_SITE_CLRNC_DCOM_P90"],
    },
    "dtr": {
        "totals": ["DTR_COST"],
        "wells": ["WELL_INST_DCOM_INDTR"],
        "pipelines": ["SEGMENT_DCOM_INDTR"],
        "platforms": ["PLT_REMOVAL_DCOM_INDTR", "PLT_SITE_CLRNC_DCOM_INDTR"],
    },
}


def build_decom_research(
    data_dir: Path,
    lease: str | None,
    api: str | None,
    area: str | None,
    block: str | None,
    min_cost: float | None,
    cost_case: str,
    pa_adjustment: str | None,
    limit: int,
) -> dict[str, Any]:
    cost_case = cost_case.casefold()
    result = {
        "filters": {
            "lease": lease,
            "api": api,
            "area": area,
            "block": block,
            "min_cost": min_cost,
            "cost_case": cost_case,
            "pa_adjustment": pa_adjustment,
        },
        "sections": {},
    }

    derived_lease_numbers = derive_decom_api_leases(data_dir, api) if api and not lease else set()
    estimates = apply_decom_common_filters(
        read_dataset(data_dir, "decom_estimates"), lease, None, area, block, pa_adjustment, None
    )
    if not lease and derived_lease_numbers:
        estimates = filter_df_by_lease_set(estimates, "LEASE_NUMBER", derived_lease_numbers)
    lease_numbers = decom_lease_numbers(estimates)
    result["sections"]["lease_estimates"] = decom_section(estimates, None, limit)

    totals = read_dataset(data_dir, "decom_totals")
    totals = filter_decom_lease(totals, ["AUTH_NUMBER"], lease)
    if not lease and (lease_numbers or derived_lease_numbers):
        totals = filter_df_by_lease_set(totals, "AUTH_NUMBER", lease_numbers or derived_lease_numbers)
    totals = filter_decom_min_cost(totals, DECOM_CASE_COLUMNS[cost_case]["totals"], min_cost)
    result["sections"]["totals"] = decom_section(totals, DECOM_CASE_COLUMNS[cost_case]["totals"], limit)

    installed_wells = apply_decom_common_filters(
        read_dataset(data_dir, "decom_spud_well"),
        lease,
        api,
        area,
        block,
        None,
        ["BOTM_LEASE_NUM", "SURF_LEASE_NUM"],
    )
    installed_wells = filter_decom_min_cost(installed_wells, DECOM_CASE_COLUMNS[cost_case]["wells"], min_cost)
    result["sections"]["installed_wells"] = decom_section(
        installed_wells, DECOM_CASE_COLUMNS[cost_case]["wells"], limit
    )

    proposed_wells = apply_decom_common_filters(
        read_dataset(data_dir, "decom_prop_well"),
        lease,
        api,
        area,
        block,
        None,
        ["BOTM_LEASE_NUM", "SURF_LEASE_NUM"],
    )
    proposed_wells = filter_decom_min_cost(proposed_wells, DECOM_CASE_COLUMNS[cost_case]["wells"], min_cost)
    result["sections"]["proposed_wells"] = decom_section(proposed_wells, DECOM_CASE_COLUMNS[cost_case]["wells"], limit)

    result["sections"]["installed_platforms"] = build_decom_asset_section(
        data_dir, "decom_inst_plat", "platforms", lease, derived_lease_numbers, area, block, min_cost, cost_case, limit
    )
    result["sections"]["proposed_platforms"] = build_decom_asset_section(
        data_dir, "decom_prop_plat", "platforms", lease, derived_lease_numbers, area, block, min_cost, cost_case, limit
    )
    result["sections"]["installed_pipelines"] = build_decom_asset_section(
        data_dir, "decom_inst_pipe", "pipelines", lease, derived_lease_numbers, area, block, min_cost, cost_case, limit
    )
    result["sections"]["proposed_pipelines"] = build_decom_asset_section(
        data_dir, "decom_prop_pipe", "pipelines", lease, derived_lease_numbers, area, block, min_cost, cost_case, limit
    )

    result["summary"] = {name: section["records"] for name, section in result["sections"].items()}
    return result


def build_decom_asset_section(
    data_dir: Path,
    dataset: str,
    kind: str,
    lease: str | None,
    lease_numbers: set[str],
    area: str | None,
    block: str | None,
    min_cost: float | None,
    cost_case: str,
    limit: int,
) -> dict[str, Any]:
    df = read_dataset(data_dir, dataset)
    if df.empty:
        return decom_section(df, DECOM_CASE_COLUMNS[cost_case][kind], limit)
    if kind == "platforms":
        df = apply_decom_common_filters(df, lease, None, area, block, None, ["AUTH_NUMBER"])
        if not lease and lease_numbers:
            df = filter_df_by_lease_set(df, "AUTH_NUMBER", lease_numbers)
    else:
        df = apply_decom_common_filters(
            df, lease, None, area, block, None, ["AUTH_NUMBER", "ORIG_LSE_NUM", "DEST_LSE_NUM"]
        )
        if not lease and lease_numbers:
            df = filter_df_by_any_lease_set(df, ["AUTH_NUMBER", "ORIG_LSE_NUM", "DEST_LSE_NUM"], lease_numbers)
    df = filter_decom_min_cost(df, DECOM_CASE_COLUMNS[cost_case][kind], min_cost)
    return decom_section(df, DECOM_CASE_COLUMNS[cost_case][kind], limit)


def derive_decom_api_leases(data_dir: Path, api: str | None) -> set[str]:
    if not api:
        return set()
    leases = set()
    for dataset in ["decom_spud_well", "decom_prop_well"]:
        df = read_dataset(data_dir, dataset)
        if df.empty or "API_WELL_NUMBER" not in df.columns:
            continue
        filtered = df[df["API_WELL_NUMBER"].map(norm_api) == norm_api(api)]
        for col in ["BOTM_LEASE_NUM", "SURF_LEASE_NUM"]:
            if col in filtered.columns:
                leases.update(filtered[col].map(lease_key).dropna())
    return {lease for lease in leases if lease}


def apply_decom_common_filters(
    df: pd.DataFrame,
    lease: str | None,
    api: str | None,
    area: str | None,
    block: str | None,
    pa_adjustment: str | None,
    lease_columns: list[str] | None,
) -> pd.DataFrame:
    if df.empty:
        return df
    out = df.copy()
    if lease:
        if lease_columns:
            out = filter_decom_lease(out, lease_columns, lease)
        elif "LEASE_NUMBER" in out.columns:
            out = filter_decom_lease(out, ["LEASE_NUMBER"], lease)
    if api and "API_WELL_NUMBER" in out.columns:
        target = norm_api(api)
        out = out[out["API_WELL_NUMBER"].map(norm_api) == target]
    if area:
        area_cols = [
            c
            for c in ["AREA_CODE", "BOTM_AREA_CODE", "SURF_AREA_CODE", "ORIG_AR_CODE", "DEST_AR_CODE"]
            if c in out.columns
        ]
        out = filter_text_columns(out, area_cols, area)
    if block:
        block_cols = [
            c
            for c in ["BLOCK_NUMBER", "BOTM_BLOCK_NUM", "SURF_BLOCK_NUM", "ORIG_BLK_NUM", "DEST_BLK_NUM"]
            if c in out.columns
        ]
        out = filter_text_columns(out, block_cols, block)
    if pa_adjustment and "PA_ADJUSTMENT_FL" in out.columns:
        out = out[out["PA_ADJUSTMENT_FL"].fillna("").astype(str).str.casefold() == pa_adjustment.casefold()]
    return out


def filter_text_columns(df: pd.DataFrame, columns: list[str], value: str) -> pd.DataFrame:
    if not columns:
        return df
    target = value.casefold()
    mask = pd.Series(False, index=df.index)
    for col in columns:
        mask = mask | df[col].fillna("").astype(str).str.casefold().eq(target)
    return df[mask]


def filter_decom_lease(df: pd.DataFrame, columns: list[str], lease: str | None) -> pd.DataFrame:
    if df.empty or not lease:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].map(lambda value: lease_matches(value, lease))
    return df[mask]


def filter_df_by_lease_set(df: pd.DataFrame, column: str, lease_numbers: set[str]) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return df
    return df[df[column].map(lambda value: lease_key(value) in lease_numbers)]


def filter_df_by_any_lease_set(df: pd.DataFrame, columns: list[str], lease_numbers: set[str]) -> pd.DataFrame:
    if df.empty:
        return df
    mask = pd.Series(False, index=df.index)
    for col in columns:
        if col in df.columns:
            mask = mask | df[col].map(lambda value: lease_key(value) in lease_numbers)
    return df[mask]


def lease_matches(value: Any, lease: str) -> bool:
    return lease_key(value) == lease_key(lease)


def lease_key(value: Any) -> str:
    text = "" if value is None or pd.isna(value) else str(value).strip().upper()
    digits = "".join(ch for ch in text if ch.isdigit()).lstrip("0")
    return digits or text


def decom_lease_numbers(df: pd.DataFrame) -> set[str]:
    if df.empty or "LEASE_NUMBER" not in df.columns:
        return set()
    return set(df["LEASE_NUMBER"].map(lease_key).dropna())


def filter_decom_min_cost(df: pd.DataFrame, columns: list[str], min_cost: float | None) -> pd.DataFrame:
    if df.empty or min_cost is None:
        return df
    present = [col for col in columns if col in df.columns]
    if not present:
        return df.iloc[0:0]
    costs = df[present].apply(pd.to_numeric, errors="coerce").fillna(0)
    return df[costs.max(axis=1) >= min_cost]


def decom_section(df: pd.DataFrame, cost_columns: list[str] | None, limit: int) -> dict[str, Any]:
    section = {
        "records": int(len(df)),
        "units": units_for(list(df.columns), DECOM_UNITS),
        "sample": top_rows(sort_decom_rows(df, cost_columns), None, limit),
    }
    if cost_columns:
        present = [col for col in cost_columns if col in df.columns]
        section["cost_columns"] = present
        section["cost_units"] = units_for(present, DECOM_UNITS)
        if present and not df.empty:
            values = df[present].apply(pd.to_numeric, errors="coerce").fillna(0)
            section["cost_sum"] = {col: float(values[col].sum()) for col in present}
            section["cost_max"] = {col: float(values[col].max()) for col in present}
    return section


def sort_decom_rows(df: pd.DataFrame, cost_columns: list[str] | None) -> pd.DataFrame:
    if df.empty or not cost_columns:
        return df
    present = [col for col in cost_columns if col in df.columns]
    if not present:
        return df
    out = df.copy()
    out["_sort_cost"] = out[present].apply(pd.to_numeric, errors="coerce").fillna(0).max(axis=1)
    return out.sort_values("_sort_cost", ascending=False).drop(columns=["_sort_cost"])


def latest_version_rows(df: pd.DataFrame, version_col: str) -> pd.DataFrame:
    if df.empty or version_col not in df.columns:
        return pd.DataFrame()
    versions = pd.to_numeric(df[version_col], errors="coerce").dropna()
    if versions.empty:
        return df
    return df[pd.to_numeric(df[version_col], errors="coerce") == versions.max()].copy()


def numeric_set(df: pd.DataFrame, column: str) -> set[float]:
    if df.empty or column not in df.columns:
        return set()
    return set(float(v) for v in pd.to_numeric(df[column], errors="coerce").dropna().round(4))


def numeric_max(df: pd.DataFrame, column: str) -> float | None:
    if df.empty or column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors="coerce").dropna()
    return float(values.max()) if not values.empty else None
