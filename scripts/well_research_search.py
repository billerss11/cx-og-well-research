"""Keyword and incident search helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from well_research_config import *
from well_research_core import *


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
            + build_filter_clause(
                filter_text,
                [
                    "wm.API_WELL_NUMBER",
                    "wm.WELL_NAME",
                    "wm.RIG_NAME",
                    "wm.BUS_ASC_NAME",
                    'b."OPERATOR FIELD"',
                    "b.FIELD",
                    "b.AREA",
                    "b.BLOCK",
                    "b.LEASE",
                ],
            ),
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
                    "first_date": date_range(group, "WAR_START_DT")["first"]
                    if date_range(group, "WAR_START_DT")
                    else None,
                    "last_date": date_range(group, "WAR_START_DT")["last"]
                    if date_range(group, "WAR_START_DT")
                    else None,
                    "well_name": group["WELL_NAME"].dropna().astype(str).iloc[0]
                    if "WELL_NAME" in group and group["WELL_NAME"].notna().any()
                    else None,
                    "operator": group["BUS_ASC_NAME"].dropna().astype(str).iloc[0]
                    if "BUS_ASC_NAME" in group and group["BUS_ASC_NAME"].notna().any()
                    else None,
                    "field": group["OPERATOR FIELD"].dropna().astype(str).iloc[0]
                    if "OPERATOR FIELD" in group and group["OPERATOR FIELD"].notna().any()
                    else None,
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
        "war_samples": top_rows(
            war_hits,
            [
                "API_WELL_NUMBER",
                "WELL_NAME",
                "WAR_START_DT",
                "WAR_END_DT",
                "RIG_NAME",
                "BUS_ASC_NAME",
                "OPERATOR FIELD",
                "TEXT_REMARK",
            ],
            limit,
        ),
        "attachment_samples": top_rows(
            attachment_hits, ["API_WELL_NUMBER", "ATT_NAME", "ATT_EXTENSION", "BUS_ASC_NAME", "Source"], limit
        ),
    }


def build_filter_clause(filter_text: str | None, expressions: list[str]) -> str:
    if not filter_text:
        return ""
    haystack = " || ' ' || ".join(f"coalesce(CAST({expr} AS VARCHAR), '')" for expr in expressions)
    return f" AND lower({haystack}) LIKE lower(?)"
