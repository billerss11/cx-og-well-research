"""Casing comparison and casing search helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from well_research_config import *
from well_research_core import *
from well_research_decom import latest_version_rows, numeric_max, numeric_set


def build_casing_comparison(apd_casing: pd.DataFrame, war_casing: pd.DataFrame, limit: int) -> dict[str, Any]:
    result = {
        "records": int(len(apd_casing) + len(war_casing)),
        "units": CASING_UNITS,
        "apd_records": int(len(apd_casing)),
        "war_records": int(len(war_casing)),
        "status": "missing_apd_and_war",
        "latest_apd_sample": [],
        "latest_war_sample": [],
        "differences": {},
    }
    if not apd_casing.empty and not war_casing.empty:
        result["status"] = "apd_and_war_available"
    elif not apd_casing.empty:
        result["status"] = "apd_only"
    elif not war_casing.empty:
        result["status"] = "war_only"

    latest_apd = latest_version_rows(apd_casing, "Submission_Version")
    latest_war = latest_version_rows(war_casing, "Report_Version")
    result["latest_apd_sample"] = top_rows(latest_apd, None, limit)
    result["latest_war_sample"] = top_rows(latest_war, None, limit)

    if not latest_apd.empty or not latest_war.empty:
        apd_sizes = numeric_set(latest_apd, "CASING_SIZE")
        war_sizes = numeric_set(latest_war, "CASING_SIZE")
        result["differences"] = {
            "apd_sizes_not_in_war": sorted(apd_sizes - war_sizes),
            "war_sizes_not_in_apd": sorted(war_sizes - apd_sizes),
            "apd_max_depth_ft": numeric_max(latest_apd, "CASING_SECTION_MD"),
            "war_max_depth_ft": numeric_max(latest_war, "CSNG_SETTING_BOTM_MD"),
        }
    return result


def parse_casing_sizes(value: str | None) -> list[float]:
    if not value:
        return []
    sizes = []
    for part in re.split(r"[,;| ]+", value):
        if not part.strip():
            continue
        sizes.append(float(part.strip().replace('"', "")))
    return sizes


def casing_size_matches(values: pd.Series, target: float, tolerance: float) -> pd.Series:
    numeric = pd.to_numeric(values, errors="coerce")
    return (numeric - target).abs() <= tolerance


def build_global_casing_search(
    data_dir: Path,
    sizes: list[float],
    source: str,
    match_mode: str,
    tolerance: float,
    filter_text: str | None,
    latest_only: bool,
    limit: int,
) -> dict[str, Any]:
    rows = []
    if source in {"any", "apd"}:
        rows.append(load_global_apd_casing(data_dir))
    if source in {"any", "war"}:
        rows.append(load_global_war_casing(data_dir))
    casing = pd.concat([df for df in rows if not df.empty], ignore_index=True) if rows else pd.DataFrame()

    result = {
        "query": {
            "sizes": sizes,
            "source": source,
            "match_mode": match_mode,
            "tolerance": tolerance,
            "filter": filter_text,
            "latest_only": latest_only,
        },
        "records_scanned": int(len(casing)),
        "units": CASING_UNITS,
        "well_count": 0,
        "wells": [],
    }
    if casing.empty or not sizes:
        return result

    casing["API_NORM"] = casing["API_WELL_NUMBER"].map(norm_api)
    casing["CASING_SIZE"] = pd.to_numeric(casing["CASING_SIZE"], errors="coerce")
    casing = casing.dropna(subset=["API_NORM", "CASING_SIZE"])
    if latest_only:
        casing = latest_casing_records(casing)

    if filter_text:
        haystack = pd.Series("", index=casing.index)
        for col in [
            "API_WELL_NUMBER",
            "WELL_NAME",
            "WELL_NAME_SUFFIX",
            "COMPANY_NAME",
            "FIELD",
            "OPERATOR FIELD",
            "AREA",
            "BLOCK",
            "LEASE",
        ]:
            if col in casing.columns:
                haystack = haystack + " " + casing[col].fillna("").astype(str)
        casing = casing[haystack.str.casefold().str.contains(filter_text.casefold(), na=False)]

    wells = []
    for _, group in casing.groupby("API_NORM"):
        matched_sizes = []
        matched_records = []
        for size in sizes:
            matches = group[casing_size_matches(group["CASING_SIZE"], size, tolerance)]
            if not matches.empty:
                matched_sizes.append(size)
                matched_records.extend(top_rows(matches, casing_output_columns(), limit))
        if match_mode == "all" and len(matched_sizes) != len(sizes):
            continue
        if match_mode == "any" and not matched_sizes:
            continue

        first = group.iloc[0]
        wells.append(
            {
                "API_WELL_NUMBER": first.get("API_WELL_NUMBER"),
                "WELL_NAME": first.get("WELL_NAME"),
                "WELL_NAME_SUFFIX": first.get("WELL_NAME_SUFFIX"),
                "COMPANY_NAME": first.get("COMPANY_NAME"),
                "FIELD": first.get("FIELD"),
                "OPERATOR FIELD": first.get("OPERATOR FIELD"),
                "AREA": first.get("AREA"),
                "BLOCK": first.get("BLOCK"),
                "LEASE": first.get("LEASE"),
                "matched_sizes": matched_sizes,
                "missing_sizes": [size for size in sizes if size not in matched_sizes],
                "sources_available": sorted(str(v) for v in group["DATA_SOURCE"].dropna().unique()),
                "record_count": int(len(group)),
                "max_depth_ft": numeric_max(group, "BOTTOM_MD"),
                "sample": matched_records[:limit],
            }
        )

    wells = sorted(
        wells,
        key=lambda row: (len(row["matched_sizes"]), row["record_count"], row.get("max_depth_ft") or 0),
        reverse=True,
    )
    result["well_count"] = int(len(wells))
    result["wells"] = wells[:limit]
    return result


def casing_output_columns() -> list[str]:
    return [
        "API_WELL_NUMBER",
        "WELL_NAME",
        "DATA_SOURCE",
        "Version",
        "Record_Date",
        "Casing_Type",
        "CASING_SIZE",
        "CASING_WEIGHT",
        "CASING_GRADE",
        "TOP_MD",
        "BOTTOM_MD",
    ]


def latest_casing_records(casing: pd.DataFrame) -> pd.DataFrame:
    version = pd.to_numeric(casing.get("Version"), errors="coerce")
    casing = casing.copy()
    casing["_version"] = version.fillna(0)
    latest = casing.groupby(["API_NORM", "DATA_SOURCE"])["_version"].transform("max")
    return casing[casing["_version"] == latest].drop(columns=["_version"])


def load_global_apd_casing(data_dir: Path) -> pd.DataFrame:
    if not all(
        parquet_path(data_dir, key).exists() for key in ["apd_main", "apd_casing_intervals", "apd_casing_sections"]
    ):
        return pd.DataFrame()
    bore_join = ""
    bore_cols = (
        "NULL AS WELL_NAME, NULL AS WELL_NAME_SUFFIX, NULL AS COMPANY_NAME, "
        'NULL AS FIELD, NULL AS "OPERATOR FIELD", NULL AS AREA, NULL AS BLOCK, NULL AS LEASE'
    )
    if parquet_path(data_dir, "boreholes").exists():
        bore_join = f'LEFT JOIN {parquet_sql(data_dir, "boreholes")} b ON main.API_WELL_NUMBER = b.API_WELL_NUMBER'
        bore_cols = (
            'b.WELL_NAME, b.WELL_NAME_SUFFIX, b.COMPANY_NAME, b.FIELD, b."OPERATOR FIELD", b.AREA, b.BLOCK, b.LEASE'
        )
    df = duckdb_df(
        f"""
        SELECT DISTINCT
            main.API_WELL_NUMBER,
            main.SN_APD AS Source_Record_Id,
            main.APD_SUB_STATUS_DT AS Record_Date,
            i.CSNG_INTV_TYPE_CD AS Casing_Type,
            i.CSNG_INTV_NAME AS Casing_Name,
            s.CASING_SIZE,
            s.CASING_WEIGHT,
            s.CASING_GRADE,
            i.CSNG_TOP_MD AS TOP_MD,
            s.CASING_SECTION_MD AS BOTTOM_MD,
            {bore_cols},
            'APD' AS DATA_SOURCE
        FROM {parquet_sql(data_dir, "apd_main")} main
        JOIN {parquet_sql(data_dir, "apd_casing_intervals")} i ON i.SN_APD_FK = main.SN_APD
        JOIN {parquet_sql(data_dir, "apd_casing_sections")} s ON s.SN_APD_CSNG_INTV_FK = i.SN_APD_CSG_INTV
        {bore_join}
        WHERE main.API_WELL_NUMBER IS NOT NULL
        """
    )
    if df.empty:
        return df
    df["Record_Date"] = parse_datetime(df["Record_Date"])
    df = df.sort_values(["API_WELL_NUMBER", "Record_Date", "Source_Record_Id"])
    df["Version"] = df.groupby("API_WELL_NUMBER")["Source_Record_Id"].transform(
        lambda s: pd.factorize(s.astype(str))[0] + 1
    )
    return df


def load_global_war_casing(data_dir: Path) -> pd.DataFrame:
    if not all(parquet_path(data_dir, key).exists() for key in ["war_main", "war_tubular", "war_tubular_prop"]):
        return pd.DataFrame()
    bore_join = ""
    bore_cols = (
        "NULL AS WELL_NAME, NULL AS WELL_NAME_SUFFIX, NULL AS COMPANY_NAME, "
        'NULL AS FIELD, NULL AS "OPERATOR FIELD", NULL AS AREA, NULL AS BLOCK, NULL AS LEASE'
    )
    if parquet_path(data_dir, "boreholes").exists():
        bore_join = f'LEFT JOIN {parquet_sql(data_dir, "boreholes")} b ON main.API_WELL_NUMBER = b.API_WELL_NUMBER'
        bore_cols = (
            'b.WELL_NAME, b.WELL_NAME_SUFFIX, b.COMPANY_NAME, b.FIELD, b."OPERATOR FIELD", b.AREA, b.BLOCK, b.LEASE'
        )
    df = duckdb_df(
        f"""
        SELECT DISTINCT
            main.API_WELL_NUMBER,
            main.SN_WAR AS Source_Record_Id,
            main.WAR_END_DT AS Record_Date,
            summ.CSNG_INTV_TYPE_CD AS Casing_Type,
            NULL AS Casing_Name,
            summ.CASING_SIZE,
            summ.CASING_WEIGHT,
            summ.CASING_GRADE,
            prop.CSNG_SETTING_TOP_MD AS TOP_MD,
            prop.CSNG_SETTING_BOTM_MD AS BOTTOM_MD,
            {bore_cols},
            'WAR' AS DATA_SOURCE
        FROM {parquet_sql(data_dir, "war_main")} main
        JOIN {parquet_sql(data_dir, "war_tubular")} summ ON main.SN_WAR = summ.SN_WAR_FK
        JOIN {parquet_sql(data_dir, "war_tubular_prop")} prop
            ON summ.SN_WAR_FK = prop.SN_WAR_FK
           AND summ.SN_WAR_CSNG_INTV = prop.SN_WAR_CSNG_INTV_FK
        {bore_join}
        WHERE main.API_WELL_NUMBER IS NOT NULL
        """
    )
    if df.empty:
        return df
    df["Record_Date"] = parse_datetime(df["Record_Date"])
    df = df.sort_values(["API_WELL_NUMBER", "Record_Date", "Source_Record_Id"])
    df["Version"] = df.groupby("API_WELL_NUMBER")["Source_Record_Id"].transform(
        lambda s: pd.factorize(s.astype(str))[0] + 1
    )
    return df


def build_apd_casing(data_dir: Path, apd: pd.DataFrame) -> pd.DataFrame:
    if apd.empty or "SN_APD" not in apd.columns:
        return pd.DataFrame()
    submission_columns = ["SN_APD"]
    if "APD_SUB_STATUS_DT" in apd.columns:
        submission_columns.append("APD_SUB_STATUS_DT")
    main = apd[submission_columns].copy()
    main["Submission_Date"] = parse_datetime(main.get("APD_SUB_STATUS_DT"))
    main = main.sort_values("Submission_Date")
    main["Submission_Version"] = pd.factorize(main["SN_APD"])[0] + 1
    sn_apds = [str(v) for v in main["SN_APD"].dropna().astype(str)]
    if not sn_apds:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(sn_apds))
    joined = duckdb_df(
        f"""
        SELECT
            i.SN_APD_FK,
            s.CASING_SIZE,
            s.CASING_WEIGHT,
            s.CASING_GRADE,
            i.CSNG_TOP_MD,
            s.CASING_SECTION_MD,
            s.CASING_SECTION_TVD,
            i.CSNG_INTV_TYPE_CD,
            i.CSNG_INTV_NAME
        FROM {parquet_sql(data_dir, "apd_casing_intervals")} i
        JOIN {parquet_sql(data_dir, "apd_casing_sections")} s
            ON s.SN_APD_CSNG_INTV_FK = i.SN_APD_CSG_INTV
        WHERE CAST(i.SN_APD_FK AS VARCHAR) IN ({placeholders})
        """,
        sn_apds,
    )
    if joined.empty:
        return pd.DataFrame()
    joined["SN_APD_FK"] = joined["SN_APD_FK"].astype(str)
    main["SN_APD"] = main["SN_APD"].astype(str)
    out = joined.merge(
        main[["SN_APD", "Submission_Date", "Submission_Version"]], left_on="SN_APD_FK", right_on="SN_APD", how="inner"
    )
    cols = [
        "Submission_Version",
        "Submission_Date",
        "CASING_SIZE",
        "CASING_WEIGHT",
        "CASING_GRADE",
        "CSNG_TOP_MD",
        "CASING_SECTION_MD",
        "CASING_SECTION_TVD",
        "CSNG_INTV_TYPE_CD",
        "CSNG_INTV_NAME",
    ]
    out = out[[c for c in cols if c in out.columns]].copy()
    for col in ["CASING_SIZE", "CASING_WEIGHT", "CSNG_TOP_MD", "CASING_SECTION_MD", "CASING_SECTION_TVD"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values([c for c in ["Submission_Version", "CSNG_TOP_MD"] if c in out.columns])


def build_war_casing(data_dir: Path, war_main: pd.DataFrame) -> pd.DataFrame:
    if war_main.empty or "SN_WAR" not in war_main.columns:
        return pd.DataFrame()
    main = war_main[["SN_WAR", "WAR_END_DT"]].copy()
    main["Report_End_Date"] = parse_datetime(main["WAR_END_DT"])
    dated = main[main["Report_End_Date"].notna()].sort_values("Report_End_Date").copy()
    if not dated.empty:
        dated["Report_Version"] = pd.factorize(dated["Report_End_Date"])[0] + 2
    undated = main[main["Report_End_Date"].isna()].copy()
    if not undated.empty:
        undated["Report_Version"] = 0
    main = pd.concat([undated, dated], ignore_index=True)

    sn_wars = [str(v) for v in main["SN_WAR"].dropna().astype(str)]
    if not sn_wars:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(sn_wars))
    out = duckdb_df(
        f"""
        SELECT
            summ.SN_WAR_FK AS SN_WAR,
            summ.CSNG_INTV_TYPE_CD,
            summ.CASING_SIZE,
            summ.CASING_WEIGHT,
            summ.CASING_GRADE,
            prop.CSNG_SETTING_TOP_MD,
            prop.CSNG_SETTING_BOTM_MD
        FROM {parquet_sql(data_dir, "war_tubular")} summ
        JOIN {parquet_sql(data_dir, "war_tubular_prop")} prop
            ON CAST(summ.SN_WAR_FK AS VARCHAR) = CAST(prop.SN_WAR_FK AS VARCHAR)
           AND CAST(summ.SN_WAR_CSNG_INTV AS VARCHAR) = CAST(prop.SN_WAR_CSNG_INTV_FK AS VARCHAR)
        WHERE CAST(summ.SN_WAR_FK AS VARCHAR) IN ({placeholders})
        """,
        sn_wars,
    )
    if out.empty:
        return pd.DataFrame()
    out["SN_WAR"] = out["SN_WAR"].astype(str)
    main["SN_WAR"] = main["SN_WAR"].astype(str)
    out = out.merge(main[["SN_WAR", "Report_End_Date", "Report_Version"]], on="SN_WAR", how="inner")
    rename = {"CSNG_INTV_TYPE_CD": "Casing_Type"}
    out = out.rename(columns=rename)
    cols = [
        "SN_WAR",
        "Report_Version",
        "Report_End_Date",
        "Casing_Type",
        "CASING_SIZE",
        "CASING_WEIGHT",
        "CASING_GRADE",
        "CSNG_SETTING_TOP_MD",
        "CSNG_SETTING_BOTM_MD",
    ]
    out = out[[c for c in cols if c in out.columns]].copy()
    for col in ["CASING_SIZE", "CASING_WEIGHT", "CSNG_SETTING_TOP_MD", "CSNG_SETTING_BOTM_MD"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values([c for c in ["Report_Version", "CSNG_SETTING_TOP_MD"] if c in out.columns])
