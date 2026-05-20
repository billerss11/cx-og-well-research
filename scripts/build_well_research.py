#!/usr/bin/env python
"""Search CX O&G APP records or build a full page-8-style well dossier."""

from __future__ import annotations

import argparse
import json
import math
import re
import warnings
from pathlib import Path
from typing import Any

warnings.filterwarnings("ignore", message="Pandas requires version .*bottleneck.*")

try:
    import duckdb
except ImportError as exc:
    raise SystemExit(
        "duckdb is required for cx-og-well-research. Use the shared env: "
        "conda activate codex_env && pip install duckdb pandas pyarrow"
    ) from exc

import numpy as np
import pandas as pd


DATASETS = {
    "boreholes": "df_boreholes.parquet",
    "production": "df_gom_production.parquet",
    "war_main": "df_WAR_main.parquet",
    "war_text": "df_WAR.parquet",
    "war_tubular": "df_mv_war_tubular_summaries.parquet",
    "war_tubular_prop": "df_mv_war_tubular_summaries_prop.parquet",
    "points": "df_points.parquet",
    "azimuth": "df_azimuth.parquet",
    "bhp": "df_bhp_survey.parquet",
    "eor_main": "df_eor_mv_eor_mainquery.parquet",
    "eor_geomarkers": "df_eor_mv_eor_geomarkers.parquet",
    "eor_completions": "df_eor_mv_eor_completions.parquet",
    "eor_perf": "df_eor_mv_eor_perf_intervals.parquet",
    "apd_main": "df_apd_main.parquet",
    "apd_casing_intervals": "df_apd_casing_intervals.parquet",
    "apd_casing_sections": "df_apd_casing_sectons.parquet",
    "open_hole_runs": "df_open_hole_runs.parquet",
    "open_hole_tools": "df_open_hole_tools.parquet",
    "attachments": "df_apd_apm_att.parquet",
    "frs": "df_frs_files_list.parquet",
}

MIN_REQUIRED_DATASETS = [
    "boreholes",
    "war_main",
    "war_text",
    "points",
    "azimuth",
    "production",
    "frs",
]

INCIDENT_TERMS = {
    "stuck-pipe": ["stuck pipe", "stuck drill pipe", "stuck bha", "stuck string", "jarred", "fishing", "washover", "overshot"],
    "lost-circulation": ["lost circulation", "losses", "lost returns", "lc material", "lcm", "seepage loss"],
    "kick": ["kick", "well control", "flow check", "shut in", "sidpp", "sicp"],
    "fishing": ["fish", "fishing", "overshot", "spear", "junk basket", "washover", "milling"],
    "cementing": ["cement", "squeeze", "plug", "shoe test", "liner test"],
    "logging": ["wireline", "mwd", "lwd", "log", "gamma ray", "resistivity"],
}


def norm_api(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return "".join(ch for ch in str(value) if ch.isdigit())


def repo_root_from(start: Path) -> Path:
    here = start.resolve()
    for candidate in [here, *here.parents]:
        if (candidate / "config.yaml").exists() and (candidate / "data").exists():
            return candidate
    return here


def sql_literal(value: Any) -> str:
    return "'" + str(value).replace("'", "''") + "'"


def parquet_path(data_dir: Path, key: str) -> Path:
    return data_dir / DATASETS[key]


def parquet_sql(data_dir: Path, key: str) -> str:
    return f"read_parquet({sql_literal(parquet_path(data_dir, key).as_posix())})"


def columns_sql(columns: list[str] | None) -> str:
    if not columns:
        return "*"
    return ", ".join(f'"{col}"' for col in columns)


def duckdb_df(sql: str, params: list[Any] | None = None) -> pd.DataFrame:
    with duckdb.connect(database=":memory:") as con:
        return con.execute(sql, params or []).fetchdf()


def api_match_sql(column: str) -> str:
    normalized = f"regexp_replace(CAST(\"{column}\" AS VARCHAR), '[^0-9]', '', 'g')"
    return f"({normalized} = ? OR starts_with({normalized}, ?) OR ends_with({normalized}, ?))"


def query_api_dataset(
    data_dir: Path,
    key: str,
    api_column: str,
    api: str,
    columns: list[str] | None = None,
    order_by: str | None = None,
) -> pd.DataFrame:
    path = parquet_path(data_dir, key)
    if not path.exists():
        return pd.DataFrame()
    target = norm_api(api)
    if not target:
        return pd.DataFrame()
    order_clause = f' ORDER BY "{order_by}"' if order_by else ""
    sql = f"""
        SELECT {columns_sql(columns)}
        FROM {parquet_sql(data_dir, key)}
        WHERE {api_match_sql(api_column)}
        {order_clause}
    """
    return duckdb_df(sql, [target, target, target])


def check_data_dir(data_dir: Path) -> dict[str, Any]:
    present = sorted(key for key, filename in DATASETS.items() if (data_dir / filename).exists())
    missing_required = sorted(key for key in MIN_REQUIRED_DATASETS if not parquet_path(data_dir, key).exists())
    return {
        "data_dir": str(data_dir),
        "ok": not missing_required,
        "present_count": len(present),
        "present": present,
        "missing_required": missing_required,
    }


def read_dataset(data_dir: Path, key: str, columns: list[str] | None = None) -> pd.DataFrame:
    path = data_dir / DATASETS[key]
    if not path.exists():
        return pd.DataFrame()
    return duckdb_df(f"SELECT {columns_sql(columns)} FROM {parquet_sql(data_dir, key)}")


def filter_api(df: pd.DataFrame, column: str, api: str) -> pd.DataFrame:
    if df.empty or column not in df.columns:
        return pd.DataFrame()
    normalized = df[column].map(norm_api)
    target = norm_api(api)
    mask = (normalized == target) | normalized.str.endswith(target, na=False) | normalized.str.startswith(target, na=False)
    return df.loc[mask].copy()


def clean_text(value: Any, max_chars: int = 450) -> str:
    if value is None or pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text if len(text) <= max_chars else text[: max_chars - 3] + "..."


def to_jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [to_jsonable(v) for v in value]
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, np.ndarray):
        return [to_jsonable(v) for v in value.tolist()]
    if not isinstance(value, (dict, list, tuple)):
        try:
            if pd.isna(value):
                return None
        except Exception:
            pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def top_rows(df: pd.DataFrame, columns: list[str] | None, limit: int) -> list[dict[str, Any]]:
    if df.empty:
        return []
    use_cols = [c for c in (columns or list(df.columns)) if c in df.columns]
    rows = df[use_cols].head(limit).where(pd.notna(df[use_cols].head(limit)), None)
    return rows.to_dict(orient="records")


def date_range(df: pd.DataFrame, column: str) -> dict[str, str] | None:
    if df.empty or column not in df.columns:
        return None
    dates = pd.to_datetime(df[column], errors="coerce").dropna()
    if dates.empty:
        return None
    return {"first": dates.min().date().isoformat(), "last": dates.max().date().isoformat()}


def numeric_summary(df: pd.DataFrame, columns: list[str]) -> dict[str, dict[str, float]]:
    out = {}
    for col in columns:
        if col in df.columns:
            s = pd.to_numeric(df[col], errors="coerce").dropna()
            if not s.empty:
                out[col] = {"min": float(s.min()), "max": float(s.max()), "mean": float(s.mean())}
    return out


def version_metrics(df: pd.DataFrame, version_col: str, date_col: str, depth_col: str, size_col: str = "CASING_SIZE") -> list[dict[str, Any]]:
    if df.empty or version_col not in df.columns:
        return []
    out = []
    for version in sorted(df[version_col].dropna().unique()):
        version_df = df[df[version_col] == version]
        metric = {
            "version": version,
            "records": int(len(version_df)),
            "date": version_df[date_col].iloc[0] if date_col in version_df.columns and len(version_df) else None,
        }
        if size_col in version_df.columns:
            s = pd.to_numeric(version_df[size_col], errors="coerce").dropna()
            if not s.empty:
                metric["max_size"] = float(s.max())
        if depth_col in version_df.columns:
            d = pd.to_numeric(version_df[depth_col], errors="coerce").dropna()
            if not d.empty:
                metric["max_depth"] = float(d.max())
        spec_cols = [c for c in ["CASING_SIZE", "CASING_WEIGHT", "CASING_GRADE"] if c in version_df.columns]
        if spec_cols:
            metric["unique_specs"] = int(len(version_df[spec_cols].drop_duplicates()))
        out.append(metric)
    return out


def dls_analysis(azimuth: pd.DataFrame, min_step: float) -> dict[str, Any]:
    if azimuth.empty or not {"MD", "Deviation Angle", "Azimuth"}.issubset(azimuth.columns):
        return {"records": int(len(azimuth)), "available": False}

    df = azimuth.sort_values("MD").copy()
    for col in ["MD", "Deviation Angle", "Azimuth"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=["MD", "Deviation Angle", "Azimuth"])
    df["MD_Diff"] = df["MD"].diff()
    df["Is_MD_Problematic"] = (df["MD_Diff"] < min_step) & (df["MD_Diff"] > 0)

    selected = []
    last_md = None
    for idx, row in df.iterrows():
        md = row["MD"]
        if last_md is None or md - last_md >= min_step or idx == df.index[-1]:
            selected.append(idx)
            last_md = md
    used = df.loc[selected].copy()

    dls_values = [np.nan]
    tvd = [0.0]
    north = [0.0]
    east = [0.0]
    for i in range(1, len(used)):
        prev = used.iloc[i - 1]
        cur = used.iloc[i]
        delta_md = float(cur["MD"] - prev["MD"])
        inc1 = math.radians(float(prev["Deviation Angle"]))
        inc2 = math.radians(float(cur["Deviation Angle"]))
        azi1 = math.radians(float(prev["Azimuth"] % 360))
        azi2 = math.radians(float(cur["Azimuth"] % 360))
        cos_dl = math.cos(inc2 - inc1) - math.sin(inc1) * math.sin(inc2) * (1 - math.cos(azi2 - azi1))
        cos_dl = max(-1.0, min(1.0, cos_dl))
        dogleg = math.acos(cos_dl)
        dls_values.append(math.degrees(dogleg) * 100 / delta_md if delta_md else np.nan)
        rf = 1.0 if abs(dogleg) < 1e-12 else 2 / dogleg * math.tan(dogleg / 2)
        north.append(north[-1] + delta_md / 2 * (math.sin(inc1) * math.cos(azi1) + math.sin(inc2) * math.cos(azi2)) * rf)
        east.append(east[-1] + delta_md / 2 * (math.sin(inc1) * math.sin(azi1) + math.sin(inc2) * math.sin(azi2)) * rf)
        tvd.append(tvd[-1] + delta_md / 2 * (math.cos(inc1) + math.cos(inc2)) * rf)

    used["DLS"] = dls_values
    used["Calc_TVD_ft"] = tvd
    used["Calc_Northing_offset_ft"] = north
    used["Calc_Easting_offset_ft"] = east
    dls_series = pd.to_numeric(used["DLS"], errors="coerce").dropna()
    horizontal = float(math.hypot(east[-1], north[-1])) if east and north else None
    final_tvd = float(tvd[-1]) if tvd else None

    return {
        "records": int(len(df)),
        "available": True,
        "used_points": int(len(used)),
        "excluded_points": int(len(df) - len(used)),
        "md_spacing_lt_min_step": int(df["Is_MD_Problematic"].sum()),
        "min_step_ft": min_step,
        "max_deviation_deg": float(df["Deviation Angle"].max()) if len(df) else None,
        "max_dls_deg_per_100ft": float(dls_series.max()) if not dls_series.empty else None,
        "avg_dls_deg_per_100ft": float(dls_series.mean()) if not dls_series.empty else None,
        "calculated_horizontal_distance_ft": horizontal,
        "calculated_final_tvd_ft": final_tvd,
        "calculated_horizontal_tvd_ratio": horizontal / final_tvd if horizontal is not None and final_tvd else None,
        "sample": top_rows(used, ["MD", "Deviation Angle", "Azimuth", "DLS", "Calc_TVD_ft", "Calc_Easting_offset_ft", "Calc_Northing_offset_ft"], 10),
    }


def search_keyword(data_dir: Path, keyword: str, filter_text: str | None, limit: int) -> dict[str, Any]:
    return search_terms(data_dir, [keyword], filter_text, limit, label=keyword)


def search_incident(data_dir: Path, incident: str, filter_text: str | None, limit: int) -> dict[str, Any]:
    incident_key = incident.casefold().strip()
    terms = INCIDENT_TERMS.get(incident_key)
    if not terms:
        terms = [incident]
    result = search_terms(data_dir, terms, filter_text, limit, label=incident)
    result["incident"] = incident_key
    result["terms"] = terms
    return result


def search_terms(data_dir: Path, terms: list[str], filter_text: str | None, limit: int, label: str) -> dict[str, Any]:
    pattern = "|".join(re.escape(term.casefold()) for term in terms if term)
    war_hits = pd.DataFrame()
    if pattern and parquet_path(data_dir, "war_text").exists():
        war_hits = duckdb_df(
            f"""
            SELECT
                wm.API_WELL_NUMBER,
                wm.WELL_NAME,
                wm.WAR_START_DT,
                wm.WAR_END_DT,
                wm.RIG_NAME,
                wm.BUS_ASC_NAME,
                b."OPERATOR FIELD",
                b.FIELD,
                b.AREA,
                b.BLOCK,
                b.LEASE,
                w.TEXT_REMARK
            FROM {parquet_sql(data_dir, "war_text")} w
            JOIN {parquet_sql(data_dir, "war_main")} wm ON w.SN_WAR = wm.SN_WAR
            LEFT JOIN {parquet_sql(data_dir, "boreholes")} b ON wm.API_WELL_NUMBER = b.API_WELL_NUMBER
            WHERE regexp_matches(lower(CAST(w.TEXT_REMARK AS VARCHAR)), ?)
            """
            + build_filter_clause(filter_text, ["wm.API_WELL_NUMBER", "wm.WELL_NAME", "wm.RIG_NAME", "wm.BUS_ASC_NAME", 'b."OPERATOR FIELD"', "b.FIELD", "b.AREA", "b.BLOCK", "b.LEASE"]),
            [pattern] + ([f"%{filter_text}%"] if filter_text else []),
        )

    attachment_hits = pd.DataFrame()
    if pattern and parquet_path(data_dir, "attachments").exists():
        attachment_hits = duckdb_df(
            f"""
            SELECT API_WELL_NUMBER, ATT_NAME, ATT_EXTENSION, BUS_ASC_NAME, Source
            FROM {parquet_sql(data_dir, "attachments")}
            WHERE regexp_matches(lower(CAST(ATT_NAME AS VARCHAR)), ?)
            """
            + build_filter_clause(filter_text, ["API_WELL_NUMBER", "ATT_NAME", "BUS_ASC_NAME", "Source"]),
            [pattern] + ([f"%{filter_text}%"] if filter_text else []),
        )

    grouped = []
    if not war_hits.empty and "API_WELL_NUMBER" in war_hits.columns:
        for api, group in war_hits.groupby("API_WELL_NUMBER"):
            grouped.append(
                {
                    "API_WELL_NUMBER": api,
                    "war_hits": int(len(group)),
                    "first_date": date_range(group, "WAR_START_DT")["first"] if date_range(group, "WAR_START_DT") else None,
                    "last_date": date_range(group, "WAR_START_DT")["last"] if date_range(group, "WAR_START_DT") else None,
                    "well_name": group["WELL_NAME"].dropna().astype(str).iloc[0] if "WELL_NAME" in group and group["WELL_NAME"].notna().any() else None,
                    "operator": group["BUS_ASC_NAME"].dropna().astype(str).iloc[0] if "BUS_ASC_NAME" in group and group["BUS_ASC_NAME"].notna().any() else None,
                    "field": group["OPERATOR FIELD"].dropna().astype(str).iloc[0] if "OPERATOR FIELD" in group and group["OPERATOR FIELD"].notna().any() else None,
                    "sample_remark": clean_text(group["TEXT_REMARK"].iloc[0]) if "TEXT_REMARK" in group else None,
                }
            )
    grouped = sorted(grouped, key=lambda row: row["war_hits"], reverse=True)

    return {
        "keyword": label,
        "terms": terms,
        "filter": filter_text,
        "war_hit_records": int(len(war_hits)),
        "attachment_hit_records": int(len(attachment_hits)),
        "wells": grouped[:limit],
        "war_samples": top_rows(war_hits, ["API_WELL_NUMBER", "WELL_NAME", "WAR_START_DT", "WAR_END_DT", "RIG_NAME", "BUS_ASC_NAME", "OPERATOR FIELD", "TEXT_REMARK"], limit),
        "attachment_samples": top_rows(attachment_hits, ["API_WELL_NUMBER", "ATT_NAME", "ATT_EXTENSION", "BUS_ASC_NAME", "Source"], limit),
    }


def build_filter_clause(filter_text: str | None, expressions: list[str]) -> str:
    if not filter_text:
        return ""
    haystack = " || ' ' || ".join(f"coalesce(CAST({expr} AS VARCHAR), '')" for expr in expressions)
    return f" AND lower({haystack}) LIKE lower(?)"


def build_dossier(
    data_dir: Path,
    api: str,
    limit: int,
    min_step: float,
    keyword: str | None = None,
    include_production: bool = False,
    include_casing_compare: bool = False,
    include_timeline: bool = False,
) -> dict[str, Any]:
    bore = query_api_dataset(data_dir, "boreholes", "API_WELL_NUMBER", api)
    eor_main = query_api_dataset(data_dir, "eor_main", "API_WELL_NUMBER", api).drop_duplicates()
    war_main = query_api_dataset(data_dir, "war_main", "API_WELL_NUMBER", api, order_by="WAR_START_DT")
    sn_wars = set(war_main["SN_WAR"].dropna().astype(str)) if "SN_WAR" in war_main.columns else set()
    sn_eors = set(eor_main["SN_EOR"].dropna().astype(str)) if "SN_EOR" in eor_main.columns else set()

    points = query_api_dataset(data_dir, "points", "API Number", api, order_by="Survey Point MD")
    azimuth = query_api_dataset(data_dir, "azimuth", "API Number", api, order_by="MD")
    bhp = query_api_dataset(data_dir, "bhp", "API_WELL_NUMBER", api, order_by="BHTST_DATE")
    if not bhp.empty:
        bhp = bhp.drop_duplicates(subset=[c for c in ["BHTST_DATE", "BHTST_MD", "BHTST_TVD", "BHTST_PRESSURE", "BHTST_SI_PRSS", "BHTST_TEMP"] if c in bhp.columns])

    geomarkers = build_geomarkers(data_dir, sn_eors)
    perf = build_perforations(data_dir, sn_eors)

    apd = query_api_dataset(data_dir, "apd_main", "API_WELL_NUMBER", api)
    apd_casing = build_apd_casing(data_dir, apd)
    war_casing = build_war_casing(data_dir, war_main)
    logging = build_logging(data_dir, war_main)

    attachments = query_api_dataset(data_dir, "attachments", "API_WELL_NUMBER", api)
    frs = query_api_dataset(data_dir, "frs", "API", api)
    war_text = build_war_text(data_dir, war_main, keyword)
    production = build_production_summary(data_dir, api) if include_production or include_timeline else {"records": 0}

    identity_cols = [
        "API_WELL_NUMBER", "WELL_NAME", "WELL_NAME_SUFFIX", "COMPANY_NAME", "FIELD", "OPERATOR FIELD", "AREA", "BLOCK",
        "LEASE", "WELL_SPUD_DATE", "TOTAL_DEPTH_DATE", "BH_TOTAL_MD", "WELL_BORE_TVD", "WELL_TD_SS", "RKB_ELEVATION",
        "WELL_TYPE_CODE", "BOREHOLE_STAT_CD", "WATER_DEPTH", "SURF_LATITUDE", "SURF_LONGITUDE", "BOTM_LATITUDE", "BOTM_LONGITUDE",
    ]

    standard_metrics = {}
    if not points.empty and {"easting", "northing", "Survey Point TVD"}.issubset(points.columns):
        p = points.sort_values("Survey Point MD") if "Survey Point MD" in points.columns else points
        dx = float(p["easting"].iloc[-1] - p["easting"].iloc[0])
        dy = float(p["northing"].iloc[-1] - p["northing"].iloc[0])
        horiz = float(math.hypot(dx, dy))
        tvd = float(pd.to_numeric(p["Survey Point TVD"], errors="coerce").iloc[-1])
        standard_metrics = {
            "horizontal_distance_ft": horiz,
            "final_tvd_ft": tvd,
            "horizontal_tvd_ratio": horiz / tvd if tvd else None,
            "delta_easting_ft": dx,
            "delta_northing_ft": dy,
        }

    sections = {
        "borehole": {"records": int(len(bore)), "sample": top_rows(bore, None, limit)},
        "eor_main": {"records": int(len(eor_main)), "sample": top_rows(eor_main, None, limit)},
        "wellpath_raw": {
            "records": int(len(points)),
            "metrics": standard_metrics,
            "numeric_summary": numeric_summary(points, ["Survey Point MD", "Survey Point TVD", "easting", "northing", "Latitude", "Longitude"]),
            "sample": top_rows(points, ["API Number", "Survey Point MD", "Survey Point TVD", "Incl Ang Deg Val", "easting", "northing", "Latitude", "Longitude"], limit),
        },
        "azimuth_dls": dls_analysis(azimuth, min_step),
        "geological_markers": {
            "records": int(len(geomarkers)),
            "deepest_marker_ft": float(pd.to_numeric(geomarkers["TOP_MD"], errors="coerce").max()) if not geomarkers.empty and "TOP_MD" in geomarkers.columns else None,
            "sample": top_rows(geomarkers.sort_values("TOP_MD") if "TOP_MD" in geomarkers.columns else geomarkers, ["GEO_MARKER_NAME", "TOP_MD"], limit),
        },
        "bhp_survey": {"records": int(len(bhp)), "date_range": date_range(bhp, "BHTST_DATE"), "sample": top_rows(bhp, None, limit)},
        "perforations": {"records": int(len(perf)), "sample": top_rows(perf, ["SN_EOR_FK", "SN_EOR_WELL_COMP", "INTERVAL", "PERF_TOP_MD", "PERF_BASE_MD", "PERF_TOP_TVD", "PERF_BOTM_TVD"], limit)},
        "apd_casing": {
            "records": int(len(apd_casing)),
            "version_metrics": version_metrics(apd_casing, "Submission_Version", "Submission_Date", "CASING_SECTION_MD"),
            "sample": top_rows(apd_casing, None, limit),
        },
        "war_casing": {
            "records": int(len(war_casing)),
            "version_metrics": version_metrics(war_casing, "Report_Version", "Report_End_Date", "CSNG_SETTING_BOTM_MD"),
            "sample": top_rows(war_casing, None, limit),
        },
        "open_hole_logging": {"records": int(len(logging)), "sample": top_rows(logging, None, limit)},
        "war_remarks": {
            "records": int(len(war_text)),
            "date_range": date_range(war_text, "WAR_START_DT"),
            "sample": top_rows(war_text, ["SN_WAR", "WAR_START_DT", "WAR_END_DT", "RIG_NAME", "BUS_ASC_NAME", "TEXT_REMARK"], limit),
        },
        "attachments": {"records": int(len(attachments)), "sample": top_rows(attachments, None, limit)},
        "frs_files": {"records": int(len(frs)), "sample": top_rows(frs, ["DOC_ID", "DOC_TYPE", "API", "WELL_NAME", "RUN_DATE", "FILE_EXT", "LOG_SOURCE", "COMMENTS"], limit)},
    }

    if include_production:
        sections["production"] = production
    if include_casing_compare:
        sections["casing_comparison"] = build_casing_comparison(apd_casing, war_casing, limit)
    if include_timeline:
        sections["timeline"] = build_timeline(
            bore=bore,
            apd=apd,
            war_text=war_text,
            eor_main=eor_main,
            bhp=bhp,
            perf=perf,
            logging=logging,
            apd_casing=apd_casing,
            war_casing=war_casing,
            production=production,
            limit=limit,
        )

    identity = {}
    if not bore.empty:
        row = bore.iloc[0]
        identity = {col: row[col] for col in identity_cols if col in bore.columns and pd.notna(row[col])}

    return {
        "api_query": api,
        "data_dir": str(data_dir),
        "identity": identity,
        "availability": {name: section.get("records", 0) for name, section in sections.items()},
        "sections": sections,
    }


def build_production_summary(data_dir: Path, api: str) -> dict[str, Any]:
    cols = [
        "Api Well Number", "Production Date", "Days On Prod", "Product Code", "Monthly Oil Volume",
        "Monthly Gas Volume", "Monthly Water Volume", "Well Status Code", "Completion Name",
        "Operator Name", "Production Interval Code", "First Production Date",
    ]
    prod = query_api_dataset(data_dir, "production", "Api Well Number", api, columns=cols, order_by="Production Date")
    if prod.empty:
        return {"records": 0, "date_range": None, "totals": {}, "peak_months": {}, "sample": []}
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
    return {
        "records": int(len(prod)),
        "date_range": date_range(prod, "Production Date"),
        "first_production_date": date_range(prod, "First Production Date")["first"] if date_range(prod, "First Production Date") else None,
        "totals": totals,
        "peak_months": peak_months,
        "status_codes": sorted([str(v) for v in prod["Well Status Code"].dropna().unique()]) if "Well Status Code" in prod.columns else [],
        "completion_count": int(prod["Completion Name"].nunique()) if "Completion Name" in prod.columns else 0,
        "sample": top_rows(prod, ["Production Date", "Completion Name", "Product Code", "Monthly Oil Volume", "Monthly Gas Volume", "Monthly Water Volume", "Well Status Code"], 8),
    }


def build_geomarkers(data_dir: Path, sn_eors: set[str]) -> pd.DataFrame:
    if not sn_eors:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(sn_eors))
    return duckdb_df(
        f"""
        SELECT DISTINCT GEO_MARKER_NAME, TOP_MD
        FROM {parquet_sql(data_dir, "eor_geomarkers")}
        WHERE CAST(SN_EOR_FK AS VARCHAR) IN ({placeholders})
        ORDER BY TOP_MD
        """,
        list(sn_eors),
    )


def build_perforations(data_dir: Path, sn_eors: set[str]) -> pd.DataFrame:
    if not sn_eors:
        return pd.DataFrame()
    placeholders = ", ".join(["?"] * len(sn_eors))
    return duckdb_df(
        f"""
        SELECT
            comp.SN_EOR_FK,
            comp.SN_EOR_WELL_COMP,
            comp.INTERVAL,
            perf.PERF_TOP_MD,
            perf.PERF_BASE_MD,
            perf.PERF_TOP_TVD,
            perf.PERF_BOTM_TVD
        FROM {parquet_sql(data_dir, "eor_completions")} comp
        JOIN {parquet_sql(data_dir, "eor_perf")} perf
            ON comp.SN_EOR_WELL_COMP = perf.SN_EOR_WELL_COMP_FK
        WHERE CAST(comp.SN_EOR_FK AS VARCHAR) IN ({placeholders})
        ORDER BY perf.PERF_TOP_MD
        """,
        list(sn_eors),
    )


def build_casing_comparison(apd_casing: pd.DataFrame, war_casing: pd.DataFrame, limit: int) -> dict[str, Any]:
    result = {
        "records": int(len(apd_casing) + len(war_casing)),
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
        date = pd.to_datetime(date_value, errors="coerce")
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
        add(row.get("BOREHOLE_STAT_DT"), "eor", "EOR/end-of-well report", clean_text(row.get("OPERATIONAL_NARRATIVE"), 220))
    for _, row in bhp.iterrows():
        add(row.get("BHTST_DATE"), "bhp", "BHP survey", row.get("BHTST_PRESSURE"))
    if not perf.empty:
        events.append({"date": pd.NaT, "source": "perforation", "event": "perforation interval records", "details": int(len(perf))})
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


def build_apd_casing(data_dir: Path, apd: pd.DataFrame) -> pd.DataFrame:
    if apd.empty or "SN_APD" not in apd.columns:
        return pd.DataFrame()
    main = apd[["SN_APD", "APD_SUB_STATUS_DT"]].copy() if "APD_SUB_STATUS_DT" in apd.columns else apd[["SN_APD"]].copy()
    main["Submission_Date"] = pd.to_datetime(main.get("APD_SUB_STATUS_DT"), errors="coerce")
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
    out = joined.merge(main[["SN_APD", "Submission_Date", "Submission_Version"]], left_on="SN_APD_FK", right_on="SN_APD", how="inner")
    cols = ["Submission_Version", "Submission_Date", "CASING_SIZE", "CASING_WEIGHT", "CASING_GRADE", "CSNG_TOP_MD", "CASING_SECTION_MD", "CASING_SECTION_TVD", "CSNG_INTV_TYPE_CD", "CSNG_INTV_NAME"]
    out = out[[c for c in cols if c in out.columns]].copy()
    for col in ["CASING_SIZE", "CASING_WEIGHT", "CSNG_TOP_MD", "CASING_SECTION_MD", "CASING_SECTION_TVD"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values([c for c in ["Submission_Version", "CSNG_TOP_MD"] if c in out.columns])


def build_war_casing(data_dir: Path, war_main: pd.DataFrame) -> pd.DataFrame:
    if war_main.empty or "SN_WAR" not in war_main.columns:
        return pd.DataFrame()
    main = war_main[["SN_WAR", "WAR_END_DT"]].copy()
    main["Report_End_Date"] = pd.to_datetime(main["WAR_END_DT"], errors="coerce")
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
    cols = ["SN_WAR", "Report_Version", "Report_End_Date", "Casing_Type", "CASING_SIZE", "CASING_WEIGHT", "CASING_GRADE", "CSNG_SETTING_TOP_MD", "CSNG_SETTING_BOTM_MD"]
    out = out[[c for c in cols if c in out.columns]].copy()
    for col in ["CASING_SIZE", "CASING_WEIGHT", "CSNG_SETTING_TOP_MD", "CSNG_SETTING_BOTM_MD"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out.sort_values([c for c in ["Report_Version", "CSNG_SETTING_TOP_MD"] if c in out.columns])


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
        return {"field_query": field, "well_count": 0, "wells": []}
    target = field.casefold()
    haystack = pd.Series("", index=bore.index)
    for col in ["FIELD", "OPERATOR FIELD", "AREA", "BLOCK", "LEASE", "COMPANY_NAME", "WELL_NAME"]:
        if col in bore.columns:
            haystack = haystack + " " + bore[col].fillna("").astype(str)
    field_wells = bore[haystack.str.casefold().str.contains(target, na=False)].copy()
    if field_wells.empty:
        return {"field_query": field, "well_count": 0, "wells": []}

    apis = [str(api) for api in field_wells["API_WELL_NUMBER"].dropna().unique()]
    api_norms = {norm_api(api): api for api in apis}
    availability_sets = {
        "war": api_set(data_dir, "war_main", "API_WELL_NUMBER"),
        "production": api_set(data_dir, "production", "Api Well Number"),
        "trajectory": api_set(data_dir, "points", "API Number"),
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
        "well_count": int(len(rows)),
        "availability_counts": {name: int(sum(1 for row in rows if row["availability"][name])) for name in availability_sets},
        "wells": rows[:limit],
    }


def api_set(data_dir: Path, dataset: str, column: str) -> set[str]:
    df = read_dataset(data_dir, dataset, columns=[column])
    if df.empty or column not in df.columns:
        return set()
    return set(df[column].map(norm_api).dropna())


def print_search(result: dict[str, Any]) -> None:
    print(f"# Keyword Discovery: {result['keyword']}")
    if result.get("filter"):
        print(f"\nFilter: `{result['filter']}`")
    print(f"\n- WAR hit records: {result['war_hit_records']}")
    print(f"- Attachment hit records: {result['attachment_hit_records']}")
    print("\n## Wells")
    if not result["wells"]:
        print("- No wells found in WAR remarks.")
    for row in result["wells"]:
        print(f"- {row['API_WELL_NUMBER']}: {row.get('well_name') or ''}, {row.get('field') or ''}, hits={row['war_hits']}, {row.get('first_date')} to {row.get('last_date')}: {row.get('sample_remark')}")
    print("\n## WAR Samples")
    for row in result["war_samples"]:
        if "TEXT_REMARK" in row:
            row["TEXT_REMARK"] = clean_text(row["TEXT_REMARK"])
        print(f"- {json.dumps(to_jsonable(row), ensure_ascii=False)}")
    print("\n## Attachment Samples")
    for row in result["attachment_samples"]:
        print(f"- {json.dumps(to_jsonable(row), ensure_ascii=False)}")


def print_field_audit(audit: dict[str, Any]) -> None:
    print(f"# Field Audit: {audit['field_query']}")
    print(f"\n- Wells matched: {audit['well_count']}")
    if "availability_counts" in audit:
        print(f"- Availability counts: {json.dumps(to_jsonable(audit['availability_counts']), ensure_ascii=False)}")
    print("\n## Ranked Wells")
    if not audit["wells"]:
        print("- No matching wells.")
    for row in audit["wells"]:
        print(
            f"- {row['API_WELL_NUMBER']}: {row.get('WELL_NAME') or ''} {row.get('WELL_NAME_SUFFIX') or ''}, "
            f"{row.get('OPERATOR FIELD') or row.get('FIELD') or ''}, score={row['data_score']}, "
            f"availability={json.dumps(to_jsonable(row['availability']), ensure_ascii=False)}"
        )


def print_dossier(dossier: dict[str, Any]) -> None:
    print(f"# Well Research Dossier: {dossier['api_query']}")
    print(f"\nData dir: `{dossier['data_dir']}`")
    if dossier["identity"]:
        print("\n## Executive Summary")
        fields = ["API_WELL_NUMBER", "WELL_NAME", "WELL_NAME_SUFFIX", "COMPANY_NAME", "OPERATOR FIELD", "FIELD", "AREA", "BLOCK", "LEASE", "BH_TOTAL_MD", "WELL_BORE_TVD", "WATER_DEPTH"]
        for field in fields:
            if field in dossier["identity"]:
                print(f"- {field}: {dossier['identity'][field]}")

    print("\n## Data Availability")
    for name, count in dossier["availability"].items():
        print(f"- {name}: {count}")

    for name, section in dossier["sections"].items():
        print(f"\n## {name.replace('_', ' ').title()}")
        for key, value in section.items():
            if key == "sample":
                continue
            print(f"- {key}: {json.dumps(to_jsonable(value), ensure_ascii=False, default=str)}")
        sample = section.get("sample", [])
        if sample:
            print("- sample:")
            for row in sample:
                if "TEXT_REMARK" in row:
                    row["TEXT_REMARK"] = clean_text(row["TEXT_REMARK"])
                print(f"  - {json.dumps(to_jsonable(row), ensure_ascii=False, default=str)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.cwd(), help="CX O&G APP repo root. Defaults to current directory.")
    parser.add_argument("--data-dir", type=Path, help="Parquet data directory. Defaults to <repo>/data.")
    parser.add_argument("--check-data-dir", action="store_true", help="Validate that the Parquet data directory has required files.")
    parser.add_argument("--api", help="API well number for full dossier.")
    parser.add_argument("--keyword", help="Keyword discovery across WAR remarks and APD/APM attachment names.")
    parser.add_argument("--incident", help=f"Incident search preset. Known: {', '.join(sorted(INCIDENT_TERMS))}.")
    parser.add_argument("--field", help="Field/operator/name text for field research or audit.")
    parser.add_argument("--filter", help="Optional text filter for keyword discovery, e.g. field/operator/well.")
    parser.add_argument("--include-production", action="store_true", help="Include production history summary in API dossier.")
    parser.add_argument("--casing-compare", action="store_true", help="Add APD planned vs WAR actual casing comparison.")
    parser.add_argument("--timeline", action="store_true", help="Add chronological timeline across available well evidence.")
    parser.add_argument("--audit", action="store_true", help="Audit data completeness for wells matching --field.")
    parser.add_argument("--min-step", type=float, default=100.0, help="Minimum MD spacing in feet for DLS analysis.")
    parser.add_argument("--limit", type=int, default=8, help="Sample row limit.")
    parser.add_argument("--full", action="store_true", help="Return more sample rows.")
    parser.add_argument("--format", choices=["markdown", "json"], default="markdown")
    args = parser.parse_args()

    repo = repo_root_from(args.repo)
    data_dir = args.data_dir or (repo / "data")
    limit = 1000 if args.full else args.limit

    if args.check_data_dir:
        validation = check_data_dir(data_dir)
        if args.format == "json":
            print(json.dumps(to_jsonable(validation), indent=2, ensure_ascii=False, default=str))
        else:
            print("# Data Directory Check")
            print(f"\n- Data dir: `{validation['data_dir']}`")
            print(f"- OK: {validation['ok']}")
            print(f"- Present datasets: {validation['present_count']}")
            print(f"- Missing required: {', '.join(validation['missing_required']) if validation['missing_required'] else 'None'}")
        return 0 if validation["ok"] else 2

    if args.incident and not args.api:
        result = search_incident(data_dir, args.incident, args.filter or args.field, limit)
        if args.format == "json":
            print(json.dumps(to_jsonable(result), indent=2, ensure_ascii=False, default=str))
        else:
            print_search(result)
        return 0

    if args.keyword and not args.api:
        result = search_keyword(data_dir, args.keyword, args.filter, limit)
        if args.format == "json":
            print(json.dumps(to_jsonable(result), indent=2, ensure_ascii=False, default=str))
        else:
            print_search(result)
        return 0

    if args.field and (args.audit or not args.api):
        audit = build_field_audit(data_dir, args.field, limit)
        if args.format == "json":
            print(json.dumps(to_jsonable(audit), indent=2, ensure_ascii=False, default=str))
        else:
            print_field_audit(audit)
        return 0

    if not args.api:
        parser.error("--api, --keyword, --incident, or --field is required")

    dossier = build_dossier(
        data_dir,
        args.api,
        limit,
        args.min_step,
        args.keyword,
        include_production=args.include_production,
        include_casing_compare=args.casing_compare,
        include_timeline=args.timeline,
    )
    if args.format == "json":
        print(json.dumps(to_jsonable(dossier), indent=2, ensure_ascii=False, default=str))
    else:
        print_dossier(dossier)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
