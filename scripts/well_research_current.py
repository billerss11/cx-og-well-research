"""Standalone queries that mirror the current CX O&G application."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

import pandas as pd
from rapidfuzz import fuzz

from well_research_casing import (
    build_apd_casing,
    build_casing_comparison,
    build_global_casing_search,
    build_war_casing,
)
from well_research_config import DATASET_CATALOG, DATASETS
from well_research_core import (
    date_range,
    duckdb_df,
    norm_api,
    parquet_path,
    parquet_sql,
    query_api_dataset,
    read_dataset,
    to_jsonable,
    top_rows,
)
from well_research_decom import build_decom_research
from well_research_dossier import build_dossier as build_legacy_dossier
from well_research_evidence import build_field_audit
from well_research_lease import build_lease_information
from well_research_production import build_completion_reconciliation


SEARCH_SORT_FIELDS = {
    "api_well_number": '"API well number"',
    "well_name": '"Well name"',
    "operator": '"Operator"',
    "field": '"Field"',
    "lease": '"Lease"',
    "area": '"Area"',
    "block": '"Block"',
    "platform": '"Platform"',
    "status": '"Status"',
}

RAW_DATASETS = {
    "boreholes": ("boreholes", "API_WELL_NUMBER"),
    "war_main": ("war_main", "API_WELL_NUMBER"),
    "war_remarks": ("war_text", None),
    "apd_main": ("apd_main", "API_WELL_NUMBER"),
    "permit_attachments": ("attachments", "API_WELL_NUMBER"),
    "frs_files": ("frs", "API"),
    "trajectory_points": ("points", "API Number"),
    "trajectory_azimuth": ("azimuth", "API Number"),
    "bhp_surveys": ("bhp", "API_WELL_NUMBER"),
    "eor_main": ("eor_main", "API_WELL_NUMBER"),
    "eor_completions": ("eor_completions", None),
    "geological_markers": ("eor_geomarkers", None),
    "perforations": ("eor_perf", None),
    "war_casing_summary": ("war_tubular", None),
    "war_casing_properties": ("war_tubular_prop", None),
    "open_hole_runs": ("open_hole_runs", None),
    "open_hole_tools": ("open_hole_tools", None),
    "apd_casing_intervals": ("apd_casing_intervals", None),
    "apd_casing_sections": ("apd_casing_sections", None),
    "applications_apm": ("apm_applications", "api_well_number"),
    "application_events": ("apm_events", "api_well_number"),
    "application_documents": ("application_attachments", "api_well_number"),
    "api_changes": ("api_changes", "API_WELL_NUMBER"),
    "directional_surveys": ("directional_surveys", "API_WELL_NUMBER"),
    "well_potential_tests": ("well_potential_tests", "API_WELL_NUMBER"),
}


class ResearchDataError(RuntimeError):
    """Raised when a required local data source cannot be queried."""


def _require(data_dir: Path, key: str) -> Path:
    path = parquet_path(data_dir, key)
    if not path.is_file():
        raise ResearchDataError(f"Required dataset is unavailable: {path}")
    return path


def _records(frame: pd.DataFrame) -> list[dict[str, Any]]:
    return to_jsonable(frame.where(pd.notna(frame), None).to_dict(orient="records"))


def _gdb_property_rows(
    data_dir: Path,
    geodatabase: str,
    layer: str,
) -> tuple[list[dict[str, Any]] | None, list[str]]:
    """Read source attributes only. Fiona geometry objects are never requested."""
    path = data_dir / "unzipped" / f"{geodatabase}.gdb"
    if not path.is_dir():
        return None, [
            f"Missing optional asset source: {path}; using Parquet enrichment where available."
        ]
    try:
        import fiona

        with fiona.open(path, layer=layer, ignore_geometry=True) as source:
            rows = [to_jsonable(dict(feature["properties"])) for feature in source]
        return rows, []
    except Exception as exc:
        return None, [
            f"Asset source unavailable: {path} ({exc}); using Parquet enrichment where available."
        ]


def _asset_key(value: Any) -> str:
    if value is None:
        return ""
    try:
        number = float(value)
        if number.is_integer():
            return str(int(number))
    except (TypeError, ValueError):
        pass
    return str(value).strip()


def _count(data_dir: Path, key: str) -> int | None:
    path = parquet_path(data_dir, key)
    if not path.is_file():
        return None
    frame = duckdb_df(f"SELECT COUNT(*) AS count FROM {parquet_sql(data_dir, key)}")
    return int(frame.iloc[0]["count"])


def coverage(data_dir: Path, keys: Iterable[str]) -> list[dict[str, Any]]:
    rows = []
    for key in dict.fromkeys(keys):
        spec = DATASET_CATALOG[key]
        count = _count(data_dir, key)
        rows.append(
            {
                "source": spec["filename"],
                "family": spec["family"],
                "record_count": count,
                "status": "available" if count is not None else "missing",
                "required": bool(spec["required"]),
            }
        )
    return rows


def provenance(
    keys: Iterable[str],
    source_family: str,
    join_identifier: str,
    *,
    units: dict[str, str] | None = None,
    derived_fields: dict[str, str] | None = None,
) -> dict[str, Any]:
    ordered = list(dict.fromkeys(keys))
    return {
        "datasets": [DATASETS[key] for key in ordered],
        "source_family": source_family,
        "join_identifier": join_identifier,
        "units": units or {},
        "derived_fields": derived_fields or {},
    }


def _exact_api_values(query: str) -> list[str]:
    if not query.isdigit() or len(query) not in {11, 12}:
        return []
    values = [query]
    padded = query.zfill(12)
    if padded != query:
        values.append(padded)
    return values


def _fuzzy_score(term: str, text: str, partial: bool) -> float:
    if partial and len(text) >= len(term):
        return float(fuzz.partial_ratio(term.casefold(), text.casefold()))
    return float(fuzz.ratio(term.casefold(), text.casefold()))


def _fuzzy_fragments(terms: list[str]) -> list[str]:
    fragments: list[str] = []
    for term in terms:
        normalized = term.strip().casefold()
        if not normalized:
            continue
        size = 3 if len(normalized) >= 5 else 2
        candidates = (
            [normalized]
            if len(normalized) <= size
            else [normalized[index : index + size] for index in range(len(normalized) - size + 1)]
        )
        for fragment in candidates:
            if fragment not in fragments:
                fragments.append(fragment)
            if len(fragments) >= 80:
                return fragments
    return fragments


def _match_snippet(
    text: str | None,
    terms: list[str],
    context: int = 180,
    max_windows: int = 3,
) -> str | None:
    if not text:
        return None
    lowered = text.casefold()
    matches: list[tuple[int, int]] = []
    for term in terms:
        needle = term.strip().casefold()
        if not needle:
            continue
        start = 0
        while True:
            position = lowered.find(needle, start)
            if position < 0:
                break
            matches.append((position, position + len(needle)))
            start = position + len(needle)
    if not matches:
        return text[: context * 2]
    windows: list[list[int]] = []
    for match_start, match_end in sorted(matches):
        start = max(0, match_start - context)
        end = min(len(text), match_end + context)
        if windows and start <= windows[-1][1]:
            windows[-1][1] = max(windows[-1][1], end)
        else:
            windows.append([start, end])
    snippets = []
    for start, end in windows[:max_windows]:
        prefix = "…" if start else ""
        suffix = "…" if end < len(text) else ""
        snippets.append(prefix + text[start:end].strip() + suffix)
    return " ".join(snippets)


def _well_projection(data_dir: Path, where_sql: str = "") -> str:
    return f"""
        WITH platform_links AS (
            SELECT
                b.API_WELL_NUMBER,
                STRING_AGG(
                    DISTINCT COALESCE(
                        NULLIF(TRIM(s.STRUCTURE_NAME), ''),
                        'Structure ' || TRIM(s.STRUCTURE_NUMBER)
                    ),
                    ', '
                    ORDER BY COALESCE(
                        NULLIF(TRIM(s.STRUCTURE_NAME), ''),
                        'Structure ' || TRIM(s.STRUCTURE_NUMBER)
                    )
                ) AS platform,
                STRING_AGG(
                    DISTINCT CONCAT_WS(
                        ' ',
                        s.STRUCTURE_NAME,
                        s.STRUCTURE_NUMBER,
                        s.COMPLEX_ID_NUM
                    ),
                    ' '
                ) AS platform_search
            FROM {parquet_sql(data_dir, "boreholes")} AS b
            JOIN {parquet_sql(data_dir, "structures")} AS s
              ON UPPER(TRIM(b.SURF_AREA_CODE)) = UPPER(TRIM(s.AREA_CODE))
             AND REGEXP_REPLACE(UPPER(TRIM(b.SURF_BLOCK_NUMBER)), '\\s+', '', 'g')
                 = REGEXP_REPLACE(UPPER(TRIM(s.BLOCK_NUMBER)), '\\s+', '', 'g')
             AND POWER(b.SURF_LATITUDE - s.LATITUDE, 2)
                 + POWER(
                    (b.SURF_LONGITUDE - s.LONGITUDE)
                    * COS(RADIANS(b.SURF_LATITUDE)),
                    2
                 ) <= POWER(0.05 / 69.0, 2)
            GROUP BY b.API_WELL_NUMBER
        )
        SELECT
            b.API_WELL_NUMBER AS "API well number",
            NULLIF(TRIM(CONCAT_WS(' ', b.WELL_NAME, b.WELL_NAME_SUFFIX)), '')
                AS "Well name",
            b.COMPANY_NAME AS "Operator",
            COALESCE(NULLIF(b."OPERATOR FIELD", ''), NULLIF(b.FIELD, ''), b.BOTM_FLD_NAME_CD)
                AS "Field",
            COALESCE(NULLIF(b.LEASE, ''), b.BOTM_LEASE_NUMBER) AS "Lease",
            COALESCE(NULLIF(b.AREA, ''), b.BOTM_AREA_CODE) AS "Area",
            COALESCE(NULLIF(b.BLOCK, ''), b.BOTM_BLOCK_NUMBER) AS "Block",
            platforms.platform AS "Platform",
            platforms.platform_search AS "_platform_search",
            b.BOREHOLE_STAT_CD AS "Status",
            b.WATER_DEPTH AS "Water depth (ft)",
            b.WELL_NAME AS "_base_well_name",
            b.WELL_NAME_SUFFIX AS "_well_name_suffix",
            b.FIELD AS "_field_name",
            b."OPERATOR FIELD" AS "_operator_field_name",
            b.BOTM_FLD_NAME_CD AS "_bottom_field_code",
            b.LEASE AS "_lease_number",
            b.AREA AS "_area_code",
            b.BLOCK AS "_block_number",
            b.SURF_LEASE_NUMBER AS "_surface_lease_number",
            b.SURF_AREA_CODE AS "_surface_area_code",
            b.SURF_BLOCK_NUMBER AS "_surface_block_number",
            b.BOTM_LEASE_NUMBER AS "_bottom_lease_number",
            b.BOTM_AREA_CODE AS "_bottom_area_code",
            b.BOTM_BLOCK_NUMBER AS "_bottom_block_number"
        FROM {parquet_sql(data_dir, "boreholes")} AS b
        LEFT JOIN platform_links AS platforms USING (API_WELL_NUMBER)
        {where_sql}
    """


def _paged_wells(
    data_dir: Path,
    where_sql: str,
    parameters: list[Any],
    *,
    page: int,
    page_size: int,
    sort_by: str,
    sort_direction: str,
) -> dict[str, Any]:
    projection = _well_projection(data_dir, where_sql)
    direction = "DESC" if sort_direction == "desc" else "ASC"
    sort = SEARCH_SORT_FIELDS[sort_by]
    frame = duckdb_df(
        f"""
        SELECT *, COUNT(*) OVER() AS _total_count
        FROM ({projection}) AS wells
        ORDER BY {sort} {direction} NULLS LAST
        LIMIT ? OFFSET ?
        """,
        [*parameters, page_size, (page - 1) * page_size],
    )
    total = int(frame.iloc[0]["_total_count"]) if not frame.empty else 0
    if "_total_count" in frame:
        frame = frame.drop(columns=["_total_count"])
    hidden_columns = [column for column in frame.columns if str(column).startswith("_")]
    if hidden_columns:
        frame = frame.drop(columns=hidden_columns)
    return {
        "rows": _records(frame),
        "page": page,
        "page_size": page_size,
        "total_count": total,
    }


def search_wells(
    data_dir: Path,
    query: str,
    *,
    page: int = 1,
    page_size: int = 25,
    sort_by: str = "api_well_number",
    sort_direction: str = "asc",
    match_mode: str = "exact",
    threshold: int = 90,
    partial: bool = True,
) -> dict[str, Any]:
    for key in ("boreholes", "structures", "war_main", "war_text", "attachments"):
        _require(data_dir, key)
    normalized = query.strip()
    exact_api = _exact_api_values(normalized)
    if not normalized:
        return _paged_wells(
            data_dir,
            "WHERE b.API_WELL_NUMBER IS NOT NULL AND TRIM(b.API_WELL_NUMBER) <> ''",
            [],
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )
    if exact_api:
        placeholders = ", ".join("?" for _ in exact_api)
        return _paged_wells(
            data_dir,
            f"WHERE TRIM(b.API_WELL_NUMBER) IN ({placeholders})",
            exact_api,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )

    terms = [term.strip() for term in normalized.split(",") if term.strip()][:10]
    if match_mode == "fuzzy":
        candidate = duckdb_df(_well_projection(data_dir))
        searchable = [
            "API well number",
            "Well name",
            "Operator",
            "_base_well_name",
            "_well_name_suffix",
            "_field_name",
            "_operator_field_name",
            "_bottom_field_code",
            "_lease_number",
            "_area_code",
            "_block_number",
            "Status",
            "_platform_search",
        ]
        candidate_searchable = [
            *searchable,
            "_surface_lease_number",
            "_surface_area_code",
            "_surface_block_number",
            "_bottom_lease_number",
            "_bottom_area_code",
            "_bottom_block_number",
        ]
        candidate_fragments = _fuzzy_fragments(terms)
        matched_apis: set[str] = set()
        for _, row in candidate.iterrows():
            values = [
                str(row[column])
                for column in searchable
                if column in row and pd.notna(row[column]) and str(row[column]).strip()
            ]
            candidate_text = " ".join(
                str(row[column])
                for column in candidate_searchable
                if column in row and pd.notna(row[column]) and str(row[column]).strip()
            ).casefold()
            if not any(fragment in candidate_text for fragment in candidate_fragments):
                continue
            if values and max(
                _fuzzy_score(term, value, partial)
                for term in terms
                for value in values
            ) >= threshold:
                matched_apis.add(str(row["API well number"]))
        evidence = search_evidence(
            data_dir,
            normalized,
            page=1,
            page_size=100000,
            match_mode="fuzzy",
            threshold=threshold,
            partial=partial,
        )
        matched_apis.update(str(row["api_well_number"]) for row in evidence["rows"])
        if not matched_apis:
            return {"rows": [], "page": page, "page_size": page_size, "total_count": 0}
        values = sorted(matched_apis)
        placeholders = ", ".join("?" for _ in values)
        return _paged_wells(
            data_dir,
            f"WHERE TRIM(b.API_WELL_NUMBER) IN ({placeholders})",
            values,
            page=page,
            page_size=page_size,
            sort_by=sort_by,
            sort_direction=sort_direction,
        )

    metadata = "LOWER(CONCAT_WS(' ', b.API_WELL_NUMBER, b.WELL_NAME, b.WELL_NAME_SUFFIX, b.COMPANY_NAME, b.FIELD, b.\"OPERATOR FIELD\", b.BOTM_FLD_NAME_CD, b.LEASE, b.AREA, b.BLOCK, b.SURF_LEASE_NUMBER, b.SURF_AREA_CODE, b.SURF_BLOCK_NUMBER, b.BOTM_LEASE_NUMBER, b.BOTM_AREA_CODE, b.BOTM_BLOCK_NUMBER, platforms.platform_search))"
    conditions: list[str] = []
    parameters: list[Any] = []
    for term in terms:
        conditions.append(f"STRPOS({metadata}, LOWER(?)) > 0")
        parameters.append(term)
    war_conditions = " OR ".join(
        "STRPOS(LOWER(COALESCE(remarks.TEXT_REMARK, '')), LOWER(?)) > 0"
        for _ in terms
    )
    attachment_conditions = " OR ".join(
        "STRPOS(LOWER(COALESCE(attachment.ATT_NAME, '')), LOWER(?)) > 0"
        for _ in terms
    )
    parameters.extend(terms)
    parameters.extend(terms)
    conditions.extend(
        [
            "b.API_WELL_NUMBER IN ("
            f"SELECT DISTINCT main.API_WELL_NUMBER FROM {parquet_sql(data_dir, 'war_text')} remarks "
            f"JOIN {parquet_sql(data_dir, 'war_main')} main USING (SN_WAR) "
            f"WHERE {war_conditions})",
            "b.API_WELL_NUMBER IN ("
            f"SELECT DISTINCT attachment.API_WELL_NUMBER FROM {parquet_sql(data_dir, 'attachments')} attachment "
            f"WHERE {attachment_conditions})",
        ]
    )
    where = (
        "WHERE b.API_WELL_NUMBER IS NOT NULL "
        "AND TRIM(b.API_WELL_NUMBER) <> '' "
        f"AND ({' OR '.join(conditions)})"
    )
    return _paged_wells(
        data_dir,
        where,
        parameters,
        page=page,
        page_size=page_size,
        sort_by=sort_by,
        sort_direction=sort_direction,
    )


def _evidence_rows(
    data_dir: Path,
    terms: list[str],
    *,
    match_mode: str,
    threshold: int,
    partial: bool,
    api_well_number: str | None = None,
) -> dict[str, list[dict[str, Any]]]:
    for key in ("boreholes", "war_main", "war_text", "attachments"):
        _require(data_dir, key)
    if not terms:
        return {"war": [], "attachments": []}
    api_filter_war = "AND main.API_WELL_NUMBER = ?" if api_well_number else ""
    api_filter_attachment = "AND attachment.API_WELL_NUMBER = ?" if api_well_number else ""
    if match_mode == "fuzzy":
        fragments = _fuzzy_fragments(terms)
        war_condition = " OR ".join(
            "STRPOS(LOWER(COALESCE(remarks.TEXT_REMARK, '')), ?) > 0"
            for _ in fragments
        ) or "FALSE"
        attachment_condition = " OR ".join(
            "STRPOS(LOWER(COALESCE(attachment.ATT_NAME, '')), ?) > 0"
            for _ in fragments
        ) or "FALSE"
        war_parameters = fragments
        attachment_parameters = fragments
    else:
        war_condition = " OR ".join(
            "STRPOS(LOWER(COALESCE(remarks.TEXT_REMARK, '')), LOWER(?)) > 0"
            for _ in terms
        )
        attachment_condition = " OR ".join(
            "STRPOS(LOWER(COALESCE(attachment.ATT_NAME, '')), LOWER(?)) > 0"
            for _ in terms
        )
        war_parameters = terms
        attachment_parameters = terms

    war = duckdb_df(
        f"""
        SELECT DISTINCT
            main.API_WELL_NUMBER AS api_well_number,
            NULLIF(TRIM(CONCAT_WS(' ', borehole.WELL_NAME, borehole.WELL_NAME_SUFFIX)), '')
                AS well_name,
            COALESCE(borehole.COMPANY_NAME, main.BUS_ASC_NAME) AS operator_name,
            borehole."OPERATOR FIELD" AS field_name,
            main.SN_WAR AS report_id,
            main.WAR_START_DT AS start_date,
            main.WAR_END_DT AS end_date,
            remarks.TEXT_REMARK AS match_text
        FROM {parquet_sql(data_dir, "war_text")} remarks
        JOIN {parquet_sql(data_dir, "war_main")} main USING (SN_WAR)
        LEFT JOIN {parquet_sql(data_dir, "boreholes")} borehole
          ON main.API_WELL_NUMBER = borehole.API_WELL_NUMBER
        WHERE ({war_condition}) {api_filter_war}
        """,
        [*war_parameters, *([api_well_number] if api_well_number else [])],
    )
    attachments = duckdb_df(
        f"""
        SELECT
            attachment.API_WELL_NUMBER AS api_well_number,
            NULLIF(TRIM(CONCAT_WS(' ', borehole.WELL_NAME, borehole.WELL_NAME_SUFFIX)), '')
                AS well_name,
            COALESCE(borehole.COMPANY_NAME, attachment.BUS_ASC_NAME) AS operator_name,
            borehole."OPERATOR FIELD" AS field_name,
            attachment.ATT_NAME AS attachment_name,
            attachment.ATT_EXTENSION AS attachment_extension,
            attachment.BUS_ASC_NAME AS business_association,
            attachment.Source AS source,
            COUNT(*) AS duplicate_count
        FROM {parquet_sql(data_dir, "attachments")} attachment
        LEFT JOIN {parquet_sql(data_dir, "boreholes")} borehole
          ON attachment.API_WELL_NUMBER = borehole.API_WELL_NUMBER
        WHERE ({attachment_condition}) {api_filter_attachment}
        GROUP BY ALL
        """,
        [*attachment_parameters, *([api_well_number] if api_well_number else [])],
    )
    war_rows = _records(war)
    attachment_rows = _records(attachments)
    if match_mode == "fuzzy":
        def score(rows: list[dict[str, Any]], field: str) -> list[dict[str, Any]]:
            selected = []
            for row in rows:
                text = str(row.get(field) or "")
                value = max(_fuzzy_score(term, text, partial) for term in terms)
                if value < threshold:
                    continue
                row["match_score"] = round(value, 1)
                if field == "match_text":
                    row[field] = _match_snippet(text, terms)
                selected.append(row)
            return sorted(
                selected,
                key=lambda row: (
                    -float(row["match_score"]),
                    str(row["api_well_number"]),
                    str(row.get(field) or ""),
                ),
            )
        war_rows = score(war_rows, "match_text")
        attachment_rows = score(attachment_rows, "attachment_name")
    else:
        for row in war_rows:
            row["match_text"] = _match_snippet(row.get("match_text"), terms)
        war_rows.sort(
            key=lambda row: (
                str(row.get("start_date") or ""),
                str(row.get("report_id") or ""),
            ),
            reverse=True,
        )
        attachment_rows.sort(
            key=lambda row: (
                str(row.get("api_well_number") or ""),
                str(row.get("attachment_name") or ""),
                str(row.get("source") or ""),
            )
        )
    return {"war": war_rows, "attachments": attachment_rows}


def _group_evidence(
    matches: dict[str, list[dict[str, Any]]],
    *,
    fuzzy: bool,
    sort_by: str,
) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for kind, source_rows in (("war", matches["war"]), ("attachments", matches["attachments"])):
        for row in source_rows:
            api = str(row["api_well_number"])
            group = grouped.setdefault(
                api,
                {
                    "api_well_number": api,
                    "well_name": row.get("well_name"),
                    "operator_name": row.get("operator_name"),
                    "field_name": row.get("field_name"),
                    "_war": [],
                    "_attachments": [],
                },
            )
            group[f"_{kind}"].append(row)
    rows = []
    for group in grouped.values():
        war = group.pop("_war")
        attachments = group.pop("_attachments")
        dates = [
            str(row.get("end_date") or row.get("start_date"))
            for row in war
            if row.get("end_date") or row.get("start_date")
        ]
        scores = [
            float(row["match_score"])
            for row in [*war, *attachments]
            if row.get("match_score") is not None
        ]
        group.update(
            {
                "war_match_count": len(war),
                "attachment_match_count": len(attachments),
                "total_match_count": len(war) + len(attachments),
                "latest_war_date": max(dates) if dates else None,
                "best_match_score": max(scores) if scores else None,
                "war_previews": war[:3],
                "attachment_previews": attachments[:3],
            }
        )
        rows.append(group)
    if sort_by == "recent":
        key = lambda row: (
            row["latest_war_date"] or "",
            row["total_match_count"],
            row["api_well_number"],
        )
    elif fuzzy:
        key = lambda row: (
            row["best_match_score"] or 0,
            row["total_match_count"],
            row["latest_war_date"] or "",
            row["api_well_number"],
        )
    else:
        key = lambda row: (
            row["total_match_count"],
            row["latest_war_date"] or "",
            row["api_well_number"],
        )
    rows.sort(key=key, reverse=True)
    return rows


def search_evidence(
    data_dir: Path,
    query: str,
    *,
    page: int = 1,
    page_size: int = 25,
    match_mode: str = "exact",
    threshold: int = 90,
    partial: bool = True,
    sort_by: str = "matches",
) -> dict[str, Any]:
    terms = [term.strip() for term in query.split(",") if term.strip()][:10]
    matches = _evidence_rows(
        data_dir,
        terms,
        match_mode=match_mode,
        threshold=threshold,
        partial=partial,
    ) if terms else {"war": [], "attachments": []}
    grouped = _group_evidence(matches, fuzzy=match_mode == "fuzzy", sort_by=sort_by)
    offset = (page - 1) * page_size
    return {
        "rows": grouped[offset : offset + page_size],
        "page": page,
        "page_size": page_size,
        "total_count": len(grouped),
        "match_totals": {
            "distinct_wells": len(grouped),
            "distinct_war_matches": len(matches["war"]),
            "raw_attachment_rows": sum(
                int(row.get("duplicate_count") or 1)
                for row in matches["attachments"]
            ),
            "collapsed_attachment_rows": len(matches["attachments"]),
        },
    }


def evidence_detail(
    data_dir: Path,
    query: str,
    api_well_number: str,
    *,
    war_page: int = 1,
    attachment_page: int = 1,
    page_size: int = 25,
    match_mode: str = "exact",
    threshold: int = 90,
    partial: bool = True,
) -> dict[str, Any]:
    terms = [term.strip() for term in query.split(",") if term.strip()][:10]
    matches = _evidence_rows(
        data_dir,
        terms,
        match_mode=match_mode,
        threshold=threshold,
        partial=partial,
        api_well_number=api_well_number,
    ) if terms else {"war": [], "attachments": []}

    def page_rows(rows: list[dict[str, Any]], page: int) -> dict[str, Any]:
        offset = (page - 1) * page_size
        return {
            "rows": rows[offset : offset + page_size],
            "page": page,
            "page_size": page_size,
            "total_count": len(rows),
        }

    return {
        "api_well_number": api_well_number,
        "war": page_rows(matches["war"], war_page),
        "attachments": page_rows(matches["attachments"], attachment_page),
    }


def field_options(data_dir: Path) -> list[dict[str, Any]]:
    for key in ("boreholes", "azimuth"):
        _require(data_dir, key)
    return _records(
        duckdb_df(
            f"""
            WITH trajectory_counts AS (
                SELECT "API Number" AS api_well_number, COUNT(*) AS source_station_count
                FROM {parquet_sql(data_dir, "azimuth")}
                WHERE "API Number" IS NOT NULL
                GROUP BY "API Number"
            )
            SELECT
                TRIM(borehole.FIELD) AS field_code,
                MIN(TRIM(borehole."OPERATOR FIELD")) AS name,
                COUNT(DISTINCT borehole.API_WELL_NUMBER) AS recorded_well_count,
                COUNT(DISTINCT trajectory.api_well_number) AS trajectory_well_count,
                COALESCE(SUM(trajectory.source_station_count), 0) AS source_station_count
            FROM {parquet_sql(data_dir, "boreholes")} borehole
            LEFT JOIN trajectory_counts trajectory
              ON borehole.API_WELL_NUMBER = trajectory.api_well_number
            WHERE TRIM(COALESCE(borehole.FIELD, '')) <> ''
              AND TRIM(COALESCE(borehole."OPERATOR FIELD", '')) <> ''
            GROUP BY TRIM(borehole.FIELD)
            ORDER BY name, field_code
            """
        )
    )


def _resolve_fields(data_dir: Path, requested: list[str]) -> tuple[list[str], list[str]]:
    options = field_options(data_dir)
    by_code = {str(row["field_code"]).casefold(): str(row["field_code"]) for row in options}
    by_name: dict[str, list[str]] = defaultdict(list)
    for row in options:
        by_name[str(row["name"]).casefold()].append(str(row["field_code"]))
    resolved: list[str] = []
    missing: list[str] = []
    for value in dict.fromkeys(item.strip() for item in requested if item.strip()):
        key = value.casefold()
        code = by_code.get(key)
        if code is None and len(by_name.get(key, [])) == 1:
            code = by_name[key][0]
        if code is None:
            missing.append(value)
        elif code not in resolved:
            resolved.append(code)
    return resolved, missing


def compare_fields(data_dir: Path, requested: list[str], sample_limit: int) -> dict[str, Any]:
    resolved, missing = _resolve_fields(data_dir, requested)
    if not resolved:
        return {"fields": [], "missing_fields": missing, "totals": {}, "wells": [], "structures": []}
    placeholders = ", ".join("?" for _ in resolved)
    wells = duckdb_df(
        f"""
        SELECT
            API_WELL_NUMBER AS api_well_number,
            NULLIF(TRIM(CONCAT_WS(' ', WELL_NAME, WELL_NAME_SUFFIX)), '') AS well_name,
            COMPANY_NAME AS operator,
            TRIM("OPERATOR FIELD") AS field_name,
            TRIM(FIELD) AS field_code,
            WELL_TYPE_CODE AS well_type,
            BOREHOLE_STAT_CD AS status,
            WATER_DEPTH AS water_depth_ft
        FROM {parquet_sql(data_dir, "boreholes")}
        WHERE UPPER(TRIM(FIELD)) IN ({placeholders})
        ORDER BY field_name, api_well_number
        """,
        [value.upper() for value in resolved],
    )
    trajectory = duckdb_df(
        f"""
        SELECT
            survey."API Number" AS api_well_number,
            COUNT(*) AS station_count,
            MIN(survey.MD) AS first_md_ft,
            MAX(survey.MD) AS final_md_ft,
            MAX(survey.TVD) AS max_tvd_ft,
            MAX(survey."Deviation Angle") AS max_inclination_deg
        FROM {parquet_sql(data_dir, "azimuth")} survey
        JOIN {parquet_sql(data_dir, "boreholes")} borehole
          ON survey."API Number" = borehole.API_WELL_NUMBER
        WHERE UPPER(TRIM(borehole.FIELD)) IN ({placeholders})
        GROUP BY survey."API Number"
        """,
        [value.upper() for value in resolved],
    )
    structures = duckdb_df(
        f"""
        SELECT
            FIELD_NAME_CODE AS field_code,
            STRUCTURE_NAME AS structure_name,
            STRUCTURE_NUMBER AS structure_number,
            STRUC_TYPE_CODE AS structure_type,
            BUS_ASC_NAME AS operator,
            COMPLEX_ID_NUM AS complex_id,
            INSTALL_DATE AS install_date,
            REMOVAL_DATE AS removal_date,
            WATER_DEPTH AS water_depth_ft
        FROM {parquet_sql(data_dir, "structures")}
        WHERE UPPER(TRIM(FIELD_NAME_CODE)) IN ({placeholders})
        ORDER BY field_code, structure_name, structure_number
        """,
        [value.upper() for value in resolved],
    )
    merged = wells.merge(trajectory, how="left", on="api_well_number")
    options = [row for row in field_options(data_dir) if row["field_code"] in resolved]
    return {
        "fields": options,
        "missing_fields": missing,
        "totals": {
            "recorded_well_count": int(len(wells)),
            "trajectory_well_count": int(trajectory["api_well_number"].nunique()) if not trajectory.empty else 0,
            "missing_trajectory_count": int(len(wells) - trajectory["api_well_number"].nunique())
            if not trajectory.empty
            else int(len(wells)),
            "source_station_count": int(trajectory["station_count"].sum()) if not trajectory.empty else 0,
            "structure_count": int(len(structures)),
        },
        "wells": top_rows(merged, None, sample_limit),
        "structures": top_rows(structures, None, sample_limit),
    }


def field_leases(data_dir: Path, requested: list[str], sample_limit: int) -> dict[str, Any]:
    resolved, missing = _resolve_fields(data_dir, requested)
    if not resolved:
        return {"fields": [], "missing_fields": missing, "relationships": []}
    placeholders = ", ".join("?" for _ in resolved)
    frame = duckdb_df(
        f"""
        SELECT DISTINCT
            TRIM(FIELD) AS field_code,
            TRIM("OPERATOR FIELD") AS field_name,
            COALESCE(NULLIF(TRIM(BOTM_LEASE_NUMBER), ''), TRIM(LEASE))
                AS lease_number,
            COALESCE(NULLIF(TRIM(BOTM_AREA_CODE), ''), TRIM(AREA)) AS area_code,
            COALESCE(NULLIF(TRIM(BOTM_BLOCK_NUMBER), ''), TRIM(BLOCK)) AS block_number,
            COUNT(DISTINCT API_WELL_NUMBER) OVER (
                PARTITION BY
                    TRIM(FIELD),
                    COALESCE(NULLIF(TRIM(BOTM_LEASE_NUMBER), ''), TRIM(LEASE)),
                    COALESCE(NULLIF(TRIM(BOTM_AREA_CODE), ''), TRIM(AREA)),
                    COALESCE(NULLIF(TRIM(BOTM_BLOCK_NUMBER), ''), TRIM(BLOCK))
            ) AS well_count
        FROM {parquet_sql(data_dir, "boreholes")}
        WHERE UPPER(TRIM(FIELD)) IN ({placeholders})
        ORDER BY field_code, lease_number, area_code, block_number
        """,
        [value.upper() for value in resolved],
    )
    return {
        "fields": resolved,
        "missing_fields": missing,
        "relationship_count": int(len(frame)),
        "relationships": top_rows(frame, None, sample_limit),
    }


def _production_stream_rows(data_dir: Path, api_well_numbers: list[str]) -> pd.DataFrame:
    _require(data_dir, "production")
    _require(data_dir, "boreholes")
    placeholders = ", ".join("?" for _ in api_well_numbers)
    return duckdb_df(
        f"""
        WITH metadata AS (
            SELECT
                API_WELL_NUMBER AS api_well_number,
                NULLIF(TRIM(CONCAT_WS(' ', WELL_NAME, WELL_NAME_SUFFIX)), '') AS well_name,
                COMPANY_NAME AS operator_name
            FROM {parquet_sql(data_dir, "boreholes")}
            WHERE API_WELL_NUMBER IN ({placeholders})
        ),
        grouped AS (
            SELECT
                CAST("Api Well Number" AS VARCHAR) AS api_well_number,
                CAST("Production Date" AS DATE) AS production_date,
                NULLIF(TRIM("Completion Name"), '') AS completion_name,
                NULLIF(TRIM("Production Interval Code"), '') AS production_interval_code,
                NULLIF(TRIM("Product Code"), '') AS product_code,
                SUM(COALESCE("Monthly Oil Volume", 0)) AS oil_bbl,
                SUM(COALESCE("Monthly Gas Volume", 0)) AS gas_mcf,
                SUM(COALESCE("Monthly Water Volume", 0)) AS water_bbl,
                MAX("Days On Prod") AS days_on_production,
                DAY(LAST_DAY("Production Date")) AS calendar_days
            FROM {parquet_sql(data_dir, "production")}
            WHERE CAST("Api Well Number" AS VARCHAR) IN ({placeholders})
            GROUP BY
                CAST("Api Well Number" AS VARCHAR),
                "Production Date",
                NULLIF(TRIM("Completion Name"), ''),
                NULLIF(TRIM("Production Interval Code"), ''),
                NULLIF(TRIM("Product Code"), '')
        )
        SELECT
            grouped.*,
            metadata.well_name,
            metadata.operator_name
        FROM grouped
        LEFT JOIN metadata USING (api_well_number)
        ORDER BY
            api_well_number,
            completion_name NULLS LAST,
            production_interval_code NULLS LAST,
            product_code NULLS LAST,
            production_date
        """,
        [*api_well_numbers, *api_well_numbers],
    )


def production_comparison(
    data_dir: Path,
    api_well_numbers: list[str],
    group_by: str,
    sample_limit: int = 10,
) -> dict[str, Any]:
    values = list(dict.fromkeys(value.strip() for value in api_well_numbers if value.strip()))
    if not values:
        raise ValueError("Provide at least one API well number")
    frame = _production_stream_rows(data_dir, values)
    dimension = {
        "completion": "completion_name",
        "product": "product_code",
        "interval": "production_interval_code",
    }.get(group_by)
    series: list[dict[str, Any]] = []
    totals = {
        "well_count": len(values),
        "series_count": 0,
        "oil_bbl": float(frame["oil_bbl"].fillna(0).sum()) if not frame.empty else 0,
        "gas_mcf": float(frame["gas_mcf"].fillna(0).sum()) if not frame.empty else 0,
        "water_bbl": float(frame["water_bbl"].fillna(0).sum()) if not frame.empty else 0,
    }
    for api in values:
        well_rows = frame[frame["api_well_number"].astype(str) == api].copy()
        well_name = (
            str(well_rows["well_name"].dropna().iloc[0])
            if not well_rows.empty and well_rows["well_name"].notna().any()
            else None
        )
        operator = (
            str(well_rows["operator_name"].dropna().iloc[0])
            if not well_rows.empty and well_rows["operator_name"].notna().any()
            else None
        )
        well_label = f"{well_name} · {api}" if well_name else api
        grouped: list[tuple[Any, pd.DataFrame]]
        if dimension is None:
            grouped = [(None, well_rows)]
        else:
            grouped = list(well_rows.groupby(dimension, dropna=False))
        for dimension_value, selected in grouped:
            if selected.empty:
                monthly = selected
            else:
                monthly = (
                    selected.groupby("production_date", dropna=False)
                    .agg(
                        oil_bbl=("oil_bbl", "sum"),
                        gas_mcf=("gas_mcf", "sum"),
                        water_bbl=("water_bbl", "sum"),
                        days_on_production=("days_on_production", "max"),
                        calendar_days=("calendar_days", "max"),
                    )
                    .reset_index()
                    .sort_values("production_date")
                )
                for volume, rate in (
                    ("oil_bbl", "oil_bpd"),
                    ("gas_mcf", "gas_mcfpd"),
                    ("water_bbl", "water_bpd"),
                ):
                    monthly[rate] = monthly[volume] / monthly["calendar_days"]
                monthly["production_date"] = pd.to_datetime(
                    monthly["production_date"], errors="coerce"
                ).dt.date
                monthly["rate_basis"] = "calendar_days"
                monthly["rate_status"] = "valid"
            dimension_text = None if pd.isna(dimension_value) else str(dimension_value)
            label = well_label
            if dimension is not None:
                label += f" · {group_by.title()} {dimension_text or 'Not reported'}"
            series.append(
                {
                    "series_key": api if dimension is None else f"{api}:{group_by}:{dimension_text or 'Not reported'}",
                    "label": label,
                    "api_well_number": api,
                    "well_name": well_name,
                    "operator_name": operator,
                    "completion_name": dimension_text if group_by == "completion" else None,
                    "production_interval_code": dimension_text if group_by == "interval" else None,
                    "product_code": dimension_text if group_by == "product" else None,
                    "summary": {
                        "oil_bbl": float(monthly["oil_bbl"].fillna(0).sum()) if not monthly.empty else 0,
                        "gas_mcf": float(monthly["gas_mcf"].fillna(0).sum()) if not monthly.empty else 0,
                        "water_bbl": float(monthly["water_bbl"].fillna(0).sum()) if not monthly.empty else 0,
                        "months": int(len(monthly)),
                    },
                    "row_count": int(len(monthly)),
                    "rows": _records(monthly.head(sample_limit)),
                    "truncated": len(monthly) > sample_limit,
                }
            )
    totals["series_count"] = len(series)
    return {
        "group_by": group_by,
        "api_well_numbers": values,
        "totals": totals,
        "series": series,
    }


def search_approvals(
    data_dir: Path,
    *,
    page: int = 1,
    page_size: int = 50,
    query: str | None = None,
    asset_type: str | None = None,
    asset_identifier: str | None = None,
    business_process: str | None = None,
    approval_type: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> dict[str, Any]:
    _require(data_dir, "asset_approvals")
    conditions: list[str] = []
    parameters: list[Any] = []
    if query:
        conditions.append(
            "LOWER(CONCAT_WS(' ', operator_name, short_description, regulation_number, "
            "raw_attributes, asset_identifier)) LIKE LOWER(?)"
        )
        parameters.append(f"%{query.strip()}%")
    for column, value in (
        ("asset_type", asset_type),
        ("asset_identifier", asset_identifier),
        ("business_process", business_process),
        ("approval_type", approval_type),
    ):
        if value:
            conditions.append(f"LOWER({column}) = LOWER(?)")
            parameters.append(value.strip())
    if date_from:
        conditions.append("CAST(event_date AS DATE) >= CAST(? AS DATE)")
        parameters.append(date_from)
    if date_to:
        conditions.append("CAST(event_date AS DATE) <= CAST(? AS DATE)")
        parameters.append(date_to)
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    matched = duckdb_df(
        f"""
        SELECT *
        FROM {parquet_sql(data_dir, "asset_approvals")}
        {where}
        ORDER BY event_date DESC NULLS LAST, approval_event_id
        """,
        parameters,
    )
    rows = _records(matched)
    by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        by_group[str(row["approval_group_id"])].append(row)
    group_ids = sorted(
        by_group,
        key=lambda key: (
            max(str(row.get("event_date") or "") for row in by_group[key]),
            key,
        ),
        reverse=True,
    )
    selected_ids = group_ids[(page - 1) * page_size : page * page_size]
    linked_by_group: dict[str, list[dict[str, Any]]] = defaultdict(list)
    if selected_ids:
        placeholders = ", ".join("?" for _ in selected_ids)
        linked = duckdb_df(
            f"""
            SELECT *
            FROM {parquet_sql(data_dir, "asset_approvals")}
            WHERE approval_group_id IN ({placeholders})
            ORDER BY
                event_date DESC NULLS LAST,
                approval_group_id,
                asset_type,
                asset_identifier
            """,
            selected_ids,
        )
        for row in _records(linked):
            linked_by_group[str(row["approval_group_id"])].append(row)
    matched_keys = {
        (row.get("approval_event_id"), row.get("source_row_number"))
        for row in rows
    }
    grouped = []
    for group_id in selected_ids:
        assets = linked_by_group.get(group_id, [])
        if not assets:
            continue
        header = assets[0]
        grouped.append(
            {
                "approval_group_id": group_id,
                "event_date": header.get("event_date"),
                "business_process": header.get("business_process"),
                "approval_type": header.get("approval_type"),
                "regulation_number": header.get("regulation_number"),
                "operator_number": header.get("operator_number"),
                "operator_name": header.get("operator_name"),
                "short_description": header.get("short_description"),
                "region": header.get("region"),
                "asset_count": len(assets),
                "assets": [
                    {
                        "approval_event_id": item.get("approval_event_id"),
                        "asset_type": item.get("asset_type"),
                        "asset_identifier": item.get("asset_identifier"),
                        "link_method": item.get("link_method"),
                        "source_row_number": item.get("source_row_number"),
                        "matches_filter": (
                            item.get("approval_event_id"),
                            item.get("source_row_number"),
                        )
                        in matched_keys,
                    }
                    for item in assets
                ],
            }
        )
    return {
        "rows": grouped,
        "page": page,
        "page_size": page_size,
        "total_count": len(group_ids),
        "matching_asset_count": len(rows),
    }


def approval_options(data_dir: Path) -> dict[str, list[str]]:
    _require(data_dir, "asset_approvals")
    result = {}
    for output, column in (
        ("asset_types", "asset_type"),
        ("business_processes", "business_process"),
        ("approval_types", "approval_type"),
    ):
        frame = duckdb_df(
            f"""
            SELECT DISTINCT CAST({column} AS VARCHAR) AS value
            FROM {parquet_sql(data_dir, "asset_approvals")}
            WHERE {column} IS NOT NULL AND TRIM(CAST({column} AS VARCHAR)) <> ''
            ORDER BY value
            """
        )
        result[output] = frame["value"].astype(str).tolist()
    return result


def well_applications(
    data_dir: Path,
    api_well_number: str,
    sample_limit: int,
    source_family: str | None = None,
) -> dict[str, Any]:
    unions: list[str] = []
    parameters: list[Any] = []
    warnings: list[str] = []
    attachments = (
        parquet_sql(data_dir, "application_attachments")
        if parquet_path(data_dir, "application_attachments").is_file()
        else None
    )
    if parquet_path(data_dir, "apd_main").is_file():
        apd_document_join = ""
        apd_document_count = "0"
        if attachments:
            apd_document_join = f"""
                LEFT JOIN (
                    SELECT parent_id, COUNT(*) AS document_count
                    FROM {attachments}
                    WHERE parent_type = 'APD'
                    GROUP BY parent_id
                ) AS documents
                  ON CAST(permit.SN_APD AS VARCHAR) = documents.parent_id
            """
            apd_document_count = "COALESCE(documents.document_count, 0)"
        unions.append(
            f"""
            WITH source AS (
                SELECT *, ROW_NUMBER() OVER () AS _source_order
                FROM {parquet_sql(data_dir, "apd_main")}
                WHERE CAST(API_WELL_NUMBER AS VARCHAR) = ?
            ),
            ranked AS (
                SELECT *,
                    COUNT(*) OVER (
                        PARTITION BY CAST(SN_APD AS VARCHAR)
                    ) AS source_duplicate_count,
                    ROW_NUMBER() OVER (
                        PARTITION BY CAST(SN_APD AS VARCHAR)
                        ORDER BY
                            TRY_CAST(APD_STATUS_DT AS TIMESTAMP) DESC NULLS LAST,
                            TRY_CAST(APD_SUB_STATUS_DT AS TIMESTAMP) DESC NULLS LAST,
                            _source_order
                    ) AS _duplicate_rank
                FROM source
            ),
            canonical AS (
                SELECT * EXCLUDE (_source_order, _duplicate_rank)
                FROM ranked
                WHERE _duplicate_rank = 1
            )
            SELECT
                CAST(permit.SN_APD AS VARCHAR) AS application_id,
                'APD' AS source_family,
                CAST(permit.PERMIT_TYPE AS VARCHAR) AS application_type,
                NULL::VARCHAR AS status_code,
                TRY_CAST(permit.APD_STATUS_DT AS TIMESTAMP) AS status_date,
                TRY_CAST(permit.APD_SUB_STATUS_DT AS TIMESTAMP) AS submitted_date,
                TRY_CAST(permit.REQ_SPUD_DATE AS TIMESTAMP) AS requested_work_date,
                CAST(permit.BUS_ASC_NAME AS VARCHAR) AS operator_name,
                CAST(permit.RIG_NAME AS VARCHAR) AS rig_name,
                CAST(permit.RIG_ID_NUM AS VARCHAR) AS rig_id,
                {apd_document_count}::BIGINT AS document_count,
                0::BIGINT AS question_count,
                0::BIGINT AS response_count,
                0::BIGINT AS resubmittal_count,
                0::BIGINT AS verbal_count,
                CAST(permit.source_duplicate_count AS BIGINT)
                    AS source_duplicate_count
            FROM canonical AS permit
            {apd_document_join}
            """
        )
        parameters.append(api_well_number)
    else:
        warnings.append(f"Missing optional dataset: {DATASETS['apd_main']}")
    if parquet_path(data_dir, "apm_applications").is_file():
        apm_document_join = ""
        apm_document_count = "application.attachment_count"
        if attachments:
            apm_document_join = f"""
                LEFT JOIN (
                    SELECT parent_id, COUNT(*) AS document_count
                    FROM {attachments}
                    WHERE parent_type = 'APM'
                    GROUP BY parent_id
                ) AS documents
                  ON CAST(application.application_id AS VARCHAR)
                     = documents.parent_id
            """
            apm_document_count = "COALESCE(documents.document_count, 0)"
        unions.append(
            f"""
            SELECT
                CAST(application.application_id AS VARCHAR) AS application_id,
                'APM' AS source_family,
                CAST(application.operation_code AS VARCHAR) AS application_type,
                CAST(application.borehole_status_code AS VARCHAR) AS status_code,
                CAST(application.application_status_date AS TIMESTAMP) AS status_date,
                CAST(application.submitted_date AS TIMESTAMP) AS submitted_date,
                CAST(application.work_commences_date AS TIMESTAMP)
                    AS requested_work_date,
                CAST(application.operator_name AS VARCHAR) AS operator_name,
                NULL::VARCHAR AS rig_name,
                CAST(application.rig_id AS VARCHAR) AS rig_id,
                {apm_document_count}::BIGINT AS document_count,
                CAST(application.question_count AS BIGINT) AS question_count,
                CAST(application.response_count AS BIGINT) AS response_count,
                CAST(application.resubmittal_count AS BIGINT) AS resubmittal_count,
                CAST(application.verbal_count AS BIGINT) AS verbal_count,
                CAST(application.source_duplicate_count AS BIGINT)
                    AS source_duplicate_count
            FROM {parquet_sql(data_dir, "apm_applications")} AS application
            {apm_document_join}
            WHERE CAST(application.api_well_number AS VARCHAR) = ?
            """
        )
        parameters.append(api_well_number)
    else:
        warnings.append(f"Missing optional dataset: {DATASETS['apm_applications']}")
    if not attachments:
        warnings.append(
            f"Missing optional dataset: {DATASETS['application_attachments']}"
        )
    if not unions:
        return {"records": None, "sample": [], "warnings": warnings}
    union_sql = "\nUNION ALL\n".join(f"SELECT * FROM ({query})" for query in unions)
    source_where = "WHERE LOWER(source_family) = LOWER(?)" if source_family else ""
    source_parameters = [source_family] if source_family else []
    total = duckdb_df(
        f"""
        SELECT COUNT(*) AS count
        FROM ({union_sql}) AS application
        {source_where}
        """,
        [*parameters, *source_parameters],
    )
    sample = duckdb_df(
        f"""
        SELECT * FROM ({union_sql}) AS application
        {source_where}
        ORDER BY status_date DESC NULLS LAST,
                 submitted_date DESC NULLS LAST,
                 application_id
        LIMIT ?
        """,
        [*parameters, *source_parameters, sample_limit],
    )
    return {
        "records": int(total.iloc[0]["count"]),
        "sample": _records(sample),
        "warnings": warnings,
    }


def _approved_roots(repo: Path) -> tuple[Path, ...]:
    roots = [
        (repo / "data" / "unzipped").resolve(),
        (repo / "files" / "war_documents").resolve(),
    ]
    config = repo / "config.yaml"
    if config.is_file():
        try:
            import yaml

            values = yaml.safe_load(config.read_text(encoding="utf-8")) or {}
            for key in ("RAW_FILES_DIR", "MAIN_FILES_DIR", "DATA_SOURCE_FOR_ALL_APPS"):
                if not values.get(key):
                    continue
                path = Path(values[key])
                if not path.is_absolute():
                    path = repo / path
                roots.append(path.resolve())
        except (OSError, ValueError, TypeError):
            pass
    return tuple(dict.fromkeys(roots))


def _resolve_document_path(
    repo: Path,
    api_well_number: str,
    document_id: str,
    extension: str | None,
) -> str | None:
    safe_extension = (extension or "").strip()
    if safe_extension and not safe_extension.startswith("."):
        safe_extension = "." + safe_extension
    filename = f"{document_id}{safe_extension}"
    for root in _approved_roots(repo):
        for candidate in (
            root / filename,
            root / api_well_number / filename,
            root / f"api_{api_well_number[:4]}" / filename,
        ):
            resolved = candidate.resolve()
            if resolved.is_relative_to(root) and resolved.is_file():
                return str(resolved)
    return None


def well_documents(
    data_dir: Path,
    repo: Path,
    api_well_number: str,
    sample_limit: int,
) -> dict[str, Any]:
    unions: list[str] = []
    parameters: list[Any] = []
    warnings: list[str] = []
    if parquet_path(data_dir, "frs").is_file():
        unions.append(
            f"""
            SELECT
                CAST(DOC_ID AS VARCHAR) AS document_id,
                'FRS' AS parent_type,
                CAST(DOC_ID AS VARCHAR) AS parent_id,
                CAST(API AS VARCHAR) AS api_well_number,
                COALESCE(DOC_TYPE, CAST(DOC_ID AS VARCHAR)) AS document_name,
                CAST(FILE_EXT AS VARCHAR) AS file_extension,
                CAST(DOC_TYPE AS VARCHAR) AS business_category,
                COALESCE(
                    CAST(CREATED_DATE AS TIMESTAMP),
                    TRY_CAST(RUN_DATE AS TIMESTAMP)
                ) AS document_date,
                NULL::VARCHAR AS operator_name,
                'FRS' AS source_family,
                'local_or_metadata_only' AS availability,
                CAST(FILE_SIZE AS DOUBLE) AS file_size_source,
                CAST(LEASE AS VARCHAR) AS lease_number,
                CAST(AREA AS VARCHAR) AS area,
                CAST(BLOCK AS VARCHAR) AS block
            FROM {parquet_sql(data_dir, "frs")}
            WHERE CAST(API AS VARCHAR) = ?
            """
        )
        parameters.append(api_well_number)
    else:
        warnings.append(f"Missing optional dataset: {DATASETS['frs']}")
    if parquet_path(data_dir, "application_attachments").is_file():
        unions.append(
            f"""
            SELECT
                CAST(document_id AS VARCHAR) AS document_id,
                CAST(parent_type AS VARCHAR) AS parent_type,
                CAST(parent_id AS VARCHAR) AS parent_id,
                CAST(api_well_number AS VARCHAR) AS api_well_number,
                CAST(document_name AS VARCHAR) AS document_name,
                CAST(file_extension AS VARCHAR) AS file_extension,
                CAST(business_category AS VARCHAR) AS business_category,
                CAST(document_date AS TIMESTAMP) AS document_date,
                CAST(operator_name AS VARCHAR) AS operator_name,
                CAST(source_family AS VARCHAR) AS source_family,
                CAST(availability AS VARCHAR) AS availability,
                NULL::DOUBLE AS file_size_source,
                NULL::VARCHAR AS lease_number,
                NULL::VARCHAR AS area,
                NULL::VARCHAR AS block
            FROM {parquet_sql(data_dir, "application_attachments")}
            WHERE CAST(api_well_number AS VARCHAR) = ?
            """
        )
        parameters.append(api_well_number)
    else:
        warnings.append(f"Missing optional dataset: {DATASETS['application_attachments']}")
    if not unions:
        return {"records": None, "sample": [], "warnings": warnings}
    union_sql = "\nUNION ALL\n".join(f"SELECT * FROM ({query})" for query in unions)
    total = duckdb_df(
        f"SELECT COUNT(*) AS count FROM ({union_sql}) AS document",
        parameters,
    )
    sample = duckdb_df(
        f"""
        SELECT * FROM ({union_sql}) AS document
        ORDER BY document_date DESC NULLS LAST, document_id
        LIMIT ?
        """,
        [*parameters, sample_limit],
    )
    rows = _records(sample)
    for row in rows:
        row["local_path"] = (
            _resolve_document_path(
                repo,
                api_well_number,
                str(row.get("document_id") or ""),
                row.get("file_extension"),
            )
            if row.get("source_family") == "FRS"
            else None
        )
    return {
        "records": int(total.iloc[0]["count"]),
        "sample": rows,
        "warnings": warnings,
    }


def well_timeline(
    data_dir: Path,
    api_well_number: str,
    legacy_rows: list[dict[str, Any]] | None,
    sample_limit: int,
) -> dict[str, Any]:
    del legacy_rows
    events: list[dict[str, Any]] = []
    warnings: list[str] = []
    missing_sources: list[str] = []

    def add_event(
        *,
        event_id: Any,
        event_date: Any,
        source_family: str,
        event_type: str,
        title: str,
        summary: Any = None,
        event_end_date: Any = None,
        source_record_id: Any = None,
        event_category: str = "operations",
        document_count: Any = 0,
        link_method: str = "exact_api",
        is_planned: bool = False,
    ) -> None:
        parsed = pd.to_datetime(event_date, errors="coerce")
        if pd.isna(parsed) or parsed.date().year < 1900:
            return
        if not is_planned and parsed.date() > pd.Timestamp.now().date():
            return
        events.append(
            {
                "event_id": str(event_id),
                "api_well_number": api_well_number,
                "event_date": parsed,
                "event_end_date": event_end_date,
                "event_category": event_category,
                "event_type": event_type,
                "source_family": source_family,
                "source_record_id": (
                    str(source_record_id) if source_record_id is not None else None
                ),
                "title": title,
                "summary": summary,
                "document_count": int(document_count or 0),
                "link_method": link_method,
                "is_planned": bool(is_planned),
            }
        )

    if parquet_path(data_dir, "war_main").is_file():
        war = query_api_dataset(
            data_dir,
            "war_main",
            "API_WELL_NUMBER",
            api_well_number,
            order_by="WAR_START_DT",
        )
        for row in _records(war):
            report_id = row.get("SN_WAR")
            add_event(
                event_id=f"WAR:{report_id}",
                event_date=row.get("WAR_START_DT"),
                event_end_date=row.get("WAR_END_DT"),
                source_family="WAR",
                event_type="war",
                source_record_id=report_id,
                title="Well activity report",
                summary=row.get("RIG_NAME") or row.get("BUS_ASC_NAME"),
                event_category="activity",
                link_method="source_record",
            )
    else:
        missing_sources.append("WAR")

    if parquet_path(data_dir, "eor_main").is_file():
        eor = query_api_dataset(
            data_dir,
            "eor_main",
            "API_WELL_NUMBER",
            api_well_number,
            order_by="BOREHOLE_STAT_DT",
        )
        for row in _records(eor):
            record_id = row.get("SN_EOR")
            add_event(
                event_id=f"EOR:{record_id}",
                event_date=row.get("BOREHOLE_STAT_DT"),
                source_family="EOR",
                event_type="eor_status",
                source_record_id=record_id,
                title=(
                    f"EOR {row.get('EOR_OPERATION_CD')}"
                    if row.get("EOR_OPERATION_CD")
                    else "End of operations"
                ),
                summary=row.get("OPERATIONAL_NARRATIVE"),
                link_method="source_record",
            )
    else:
        missing_sources.append("EOR")

    if parquet_path(data_dir, "boreholes").is_file():
        borehole = query_api_dataset(
            data_dir,
            "boreholes",
            "API_WELL_NUMBER",
            api_well_number,
        )
        eor_dates = {
            str(pd.to_datetime(row.get("BOREHOLE_STAT_DT"), errors="coerce").date())
            for row in _records(eor)
            if not pd.isna(pd.to_datetime(row.get("BOREHOLE_STAT_DT"), errors="coerce"))
        } if "eor" in locals() else set()
        for row in _records(borehole.head(1)):
            add_event(
                event_id=f"BOREHOLE:{api_well_number}:spud",
                event_date=row.get("WELL_SPUD_DATE"),
                source_family="Borehole",
                event_type="well_spud",
                source_record_id=f"{api_well_number}:spud",
                title="Well spudded",
                summary=row.get("WELL_NAME"),
                event_category="milestone",
            )
            add_event(
                event_id=f"BOREHOLE:{api_well_number}:total_depth",
                event_date=row.get("TOTAL_DEPTH_DATE"),
                source_family="Borehole",
                event_type="total_depth",
                source_record_id=f"{api_well_number}:total_depth",
                title="Total depth reached",
                summary=(
                    f"{row.get('BH_TOTAL_MD')} ft MD"
                    if row.get("BH_TOTAL_MD") is not None
                    else None
                ),
                event_category="milestone",
            )
            status_date = pd.to_datetime(row.get("BOREHOLE_STAT_DT"), errors="coerce")
            if (
                not pd.isna(status_date)
                and str(status_date.date()) not in eor_dates
            ):
                add_event(
                    event_id=f"BOREHOLE:{api_well_number}:status",
                    event_date=status_date,
                    source_family="Borehole",
                    event_type="borehole_status",
                    source_record_id=f"{api_well_number}:status",
                    title="Borehole status",
                    summary=row.get("BOREHOLE_STAT_CD"),
                    event_category="milestone",
                )
    else:
        missing_sources.append("Borehole")

    applications = well_applications(data_dir, api_well_number, 100_000)
    warnings.extend(applications.get("warnings", []))
    for row in applications.get("sample", []):
        if row.get("source_family") != "APD":
            continue
        application_id = row.get("application_id")
        add_event(
            event_id=f"APD:{application_id}:status",
            event_date=row.get("status_date"),
            source_family="APD",
            event_type="apd_status",
            source_record_id=application_id,
            title=(
                f"APD {row.get('application_type')}"
                if row.get("application_type")
                else "APD status"
            ),
            summary=row.get("operator_name"),
            event_category="application",
            document_count=row.get("document_count"),
            link_method="source_record",
        )

    if parquet_path(data_dir, "apm_events").is_file():
        apm = query_api_dataset(
            data_dir,
            "apm_events",
            "api_well_number",
            api_well_number,
            order_by="event_date",
        )
        for row in _records(apm):
            event_type = str(row.get("event_type") or "event")
            add_event(
                event_id=row.get("event_id"),
                event_date=row.get("event_date"),
                event_end_date=row.get("event_end_date"),
                source_family=str(row.get("source_family") or "APM"),
                event_type=event_type,
                source_record_id=row.get("source_record_id"),
                title=str(row.get("title") or "APM event"),
                summary=row.get("summary"),
                event_category=str(row.get("event_category") or "application"),
                document_count=row.get("document_count"),
                link_method=str(row.get("link_method") or "source_parent"),
                is_planned="requested" in event_type.casefold(),
            )
    else:
        missing_sources.append("APM")

    simple_sources = (
        (
            "bhp",
            "BHP",
            "API_WELL_NUMBER",
            "BHTST_DATE",
            "BHP",
            "bhp_survey",
            "Bottom-hole pressure survey",
            "RESERVOIR_NAME",
            "survey",
        ),
        (
            "api_changes",
            "API change",
            "API_WELL_NUMBER",
            "ACTIVITY_DATE",
            "SOURCE_RECORD_ID",
            "api_change",
            "API number changed",
            "PREV_API_NUMBER",
            "administrative",
        ),
        (
            "directional_surveys",
            "Directional survey",
            "API_WELL_NUMBER",
            "RECEIPT_DATE",
            "SOURCE_RECORD_ID",
            "directional_survey_received",
            "Directional survey received",
            "WELL_NAME",
            "survey",
        ),
        (
            "well_potential_tests",
            "Well potential",
            "API_WELL_NUMBER",
            "TEST_DATE",
            "SOURCE_RECORD_ID",
            "well_potential_test",
            "Well potential test",
            "FIELD_NAME",
            "operations",
        ),
    )
    for (
        key,
        source_family,
        api_column,
        date_column,
        id_column,
        event_type,
        title,
        summary_column,
        category,
    ) in simple_sources:
        if not parquet_path(data_dir, key).is_file():
            missing_sources.append(source_family)
            continue
        frame = query_api_dataset(
            data_dir,
            key,
            api_column,
            api_well_number,
            order_by=date_column,
        )
        for index, row in enumerate(_records(frame), start=1):
            record_id = row.get(id_column) or f"{source_family}:{index}"
            summary = row.get(summary_column)
            if source_family == "API change" and summary is not None:
                summary = f"Previous API {summary}"
            add_event(
                event_id=record_id,
                event_date=row.get(date_column),
                source_family=source_family,
                event_type=event_type,
                source_record_id=record_id,
                title=title,
                summary=summary,
                event_category=category,
                document_count=(
                    1
                    if source_family in {"Directional survey", "Well potential"}
                    else 0
                ),
            )

    if parquet_path(data_dir, "api_well_completions").is_file():
        completions = query_api_dataset(
            data_dir,
            "api_well_completions",
            "API_WELL_NUMBER",
            api_well_number,
            order_by="COMPLETION_DATE",
        )
        for row in _records(completions):
            record_id = row.get("SOURCE_RECORD_ID")
            summary = row.get("PROD_INTERVAL_CD") or row.get("COMP_STATUS_CD")
            add_event(
                event_id=f"{record_id}:completion",
                event_date=row.get("COMPLETION_DATE"),
                source_family="Completion",
                event_type="well_completion",
                source_record_id=record_id,
                title="Well completion",
                summary=summary,
            )
            add_event(
                event_id=f"{record_id}:squeeze",
                event_date=row.get("SQUEEZED_DATE"),
                source_family="Completion",
                event_type="completion_squeeze",
                source_record_id=record_id,
                title="Completion squeezed",
                summary=summary,
            )
    else:
        missing_sources.append("Completion")

    if parquet_path(data_dir, "asset_approvals").is_file():
        approvals = duckdb_df(
            f"""
            SELECT *
            FROM {parquet_sql(data_dir, "asset_approvals")}
            WHERE LOWER(asset_type) = 'well'
              AND link_method = 'exact_attribute'
              AND regexp_replace(
                    CAST(asset_identifier AS VARCHAR),
                    '[^0-9]',
                    '',
                    'g'
                  ) = ?
            ORDER BY event_date
            """,
            [norm_api(api_well_number)],
        )
        for row in _records(approvals):
            add_event(
                event_id=f"APPROVAL:{row.get('approval_event_id')}",
                event_date=row.get("event_date"),
                source_family="Approval",
                event_type="regulatory_approval",
                source_record_id=row.get("approval_event_id"),
                title=str(
                    row.get("approval_type")
                    or row.get("business_process")
                    or "Regulatory approval"
                ),
                summary=row.get("short_description"),
                event_category="approval",
                link_method=str(row.get("link_method") or "exact_attribute"),
            )
    else:
        missing_sources.append("Approval")

    for key, stage in (
        ("decom_prop_well", "proposed"),
        ("decom_spud_well", "installed"),
    ):
        if not parquet_path(data_dir, key).is_file():
            continue
        decom = query_api_dataset(
            data_dir,
            key,
            "API_WELL_NUMBER",
            api_well_number,
            order_by="EFFECTIVE_DATE",
        )
        for row in _records(decom):
            add_event(
                event_id=f"DECOM:{stage}:{api_well_number}",
                event_date=row.get("EFFECTIVE_DATE"),
                event_end_date=row.get("EXPIRATION_DATE"),
                source_family="Decommission",
                event_type="decommission_cost_estimate",
                source_record_id=f"DECOM:{stage}:{api_well_number}",
                title="Decommissioning cost estimate effective",
                summary=row.get("WELL_NAME"),
                event_category="cost",
            )

    events.sort(key=lambda row: row["event_id"])
    events.sort(key=lambda row: str(row.get("event_date") or ""), reverse=True)
    counts: dict[str, int] = defaultdict(int)
    for event in events:
        counts[event["source_family"]] += 1
    warnings.extend(
        f"Missing optional timeline source: {source}"
        for source in dict.fromkeys(missing_sources)
    )
    return {
        "records": len(events),
        "sample": events[:sample_limit] if sample_limit else [],
        "source_counts": dict(sorted(counts.items())),
        "warnings": list(dict.fromkeys(warnings)),
    }


def _search_platforms_parquet(
    data_dir: Path,
    *,
    query: str | None = None,
    status: str | None = None,
    company: str | None = None,
    lease: str | None = None,
    area: str | None = None,
    block: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    _require(data_dir, "structures")
    conditions = []
    parameters: list[Any] = []
    if query:
        conditions.append(
            "LOWER(CONCAT_WS(' ', STRUCTURE_NAME, STRUCTURE_NUMBER, COMPLEX_ID_NUM, "
            "BUS_ASC_NAME, FIELD_NAME_CODE, LEASE_NUMBER, AREA_CODE, BLOCK_NUMBER)) "
            "LIKE LOWER(?)"
        )
        parameters.append(f"%{query.strip()}%")
    if status:
        normalized = status.strip().casefold()
        if normalized == "active":
            conditions.append("REMOVAL_DATE IS NULL")
        elif normalized == "removed":
            conditions.append("REMOVAL_DATE IS NOT NULL")
        else:
            raise ValueError("Platform status must be active or removed")
    for column, value in (
        ("BUS_ASC_NAME", company),
        ("LEASE_NUMBER", lease),
        ("AREA_CODE", area),
        ("BLOCK_NUMBER", block),
    ):
        if value:
            comparator = "LIKE LOWER(?)" if column == "BUS_ASC_NAME" else "= LOWER(?)"
            conditions.append(f"LOWER(CAST({column} AS VARCHAR)) {comparator}")
            parameters.append(f"%{value.strip()}%" if column == "BUS_ASC_NAME" else value.strip())
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    frame = duckdb_df(
        f"""
        SELECT
            COMPLEX_ID_NUM AS complex_id,
            STRUCTURE_NUMBER AS structure_number,
            STRUCTURE_NAME AS structure_name,
            STRUC_TYPE_CODE AS structure_type,
            BUS_ASC_NAME AS operator,
            FIELD_NAME_CODE AS field_code,
            LEASE_NUMBER AS lease_number,
            AREA_CODE AS area_code,
            BLOCK_NUMBER AS block_number,
            INSTALL_DATE AS install_date,
            REMOVAL_DATE AS removal_date,
            CASE WHEN REMOVAL_DATE IS NULL THEN 'active' ELSE 'removed' END AS status,
            WATER_DEPTH AS water_depth_ft,
            MAJ_STRUC_FLAG AS major_structure_flag,
            MANNED_24_HR_FL AS manned_24_hour_flag,
            COUNT(*) OVER() AS _total_count
        FROM {parquet_sql(data_dir, "structures")}
        {where}
        ORDER BY status, operator, structure_name, complex_id, structure_number
        LIMIT ? OFFSET ?
        """,
        [*parameters, page_size, (page - 1) * page_size],
    )
    total = int(frame.iloc[0]["_total_count"]) if not frame.empty else 0
    if "_total_count" in frame:
        frame = frame.drop(columns=["_total_count"])
    return {
        "rows": _records(frame),
        "page": page,
        "page_size": page_size,
        "total_count": total,
        "warnings": [],
    }


def search_platforms(
    data_dir: Path,
    *,
    query: str | None = None,
    status: str | None = None,
    company: str | None = None,
    lease: str | None = None,
    area: str | None = None,
    block: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    if status and status.strip().casefold() not in {"active", "removed"}:
        raise ValueError("Platform status must be active or removed")

    source_rows, warnings = _gdb_property_rows(
        data_dir, "Platforms", "Platforms"
    )
    if source_rows is None:
        result = _search_platforms_parquet(
            data_dir,
            query=query,
            status=status,
            company=company,
            lease=lease,
            area=area,
            block=block,
            page=page,
            page_size=page_size,
        )
        result["warnings"] = warnings
        return result

    enrichment: dict[tuple[str, str], dict[str, Any]] = {}
    if parquet_path(data_dir, "structures").is_file():
        frame = duckdb_df(
            f"""
            SELECT
                COMPLEX_ID_NUM,
                STRUCTURE_NUMBER,
                STRUCTURE_NAME,
                STRUC_TYPE_CODE,
                BUS_ASC_NAME,
                FIELD_NAME_CODE,
                LEASE_NUMBER,
                AREA_CODE,
                BLOCK_NUMBER,
                WATER_DEPTH,
                MAJ_STRUC_FLAG,
                MANNED_24_HR_FL
            FROM {parquet_sql(data_dir, "structures")}
            """
        )
        for row in _records(frame):
            key = (
                _asset_key(row.get("COMPLEX_ID_NUM")),
                _asset_key(row.get("STRUCTURE_NUMBER")),
            )
            enrichment.setdefault(key, row)
    else:
        warnings.append(
            "Missing optional platform enrichment: structures Parquet; coverage is partial."
        )

    normalized_rows = []
    for source in source_rows:
        key = (
            _asset_key(source.get("COMPLEX_ID_NUM")),
            _asset_key(source.get("STRUCTURE_NUMBER")),
        )
        extra = enrichment.get(key, {})
        removal_date = source.get("REMOVAL_DATE")
        normalized_rows.append(
            {
                "complex_id": source.get("COMPLEX_ID_NUM"),
                "structure_number": source.get("STRUCTURE_NUMBER"),
                "structure_name": source.get("STRUCTURE_NAME")
                or extra.get("STRUCTURE_NAME"),
                "structure_type": extra.get("STRUC_TYPE_CODE"),
                "operator": extra.get("BUS_ASC_NAME"),
                "field_code": extra.get("FIELD_NAME_CODE"),
                "lease_number": extra.get("LEASE_NUMBER"),
                "area_code": extra.get("AREA_CODE"),
                "block_number": extra.get("BLOCK_NUMBER"),
                "install_date": source.get("INSTALL_DATE"),
                "removal_date": removal_date,
                "status": "removed" if removal_date is not None else "active",
                "water_depth_ft": extra.get("WATER_DEPTH"),
                "major_structure_flag": extra.get("MAJ_STRUC_FLAG"),
                "manned_24_hour_flag": extra.get("MANNED_24_HR_FL"),
            }
        )

    def contains(value: Any, expected: str | None) -> bool:
        return not expected or expected.strip().casefold() in str(value or "").casefold()

    def equals(value: Any, expected: str | None) -> bool:
        return not expected or str(value or "").strip().casefold() == expected.strip().casefold()

    filtered = []
    for row in normalized_rows:
        searchable = " ".join(str(value or "") for value in row.values())
        if query and query.strip().casefold() not in searchable.casefold():
            continue
        if status and row["status"] != status.strip().casefold():
            continue
        if not contains(row.get("operator"), company):
            continue
        if not equals(row.get("lease_number"), lease):
            continue
        if not equals(row.get("area_code"), area):
            continue
        if not equals(row.get("block_number"), block):
            continue
        filtered.append(row)

    offset = (page - 1) * page_size
    return {
        "rows": filtered[offset : offset + page_size],
        "page": page,
        "page_size": page_size,
        "total_count": len(filtered),
        "warnings": warnings,
    }


def platform_detail(
    data_dir: Path,
    complex_id: int,
    structure_number: int,
    sample_limit: int,
) -> dict[str, Any]:
    _require(data_dir, "structures")
    structure = duckdb_df(
        f"""
        SELECT *
        FROM {parquet_sql(data_dir, "structures")}
        WHERE TRY_CAST(COMPLEX_ID_NUM AS BIGINT) = ?
          AND TRY_CAST(STRUCTURE_NUMBER AS BIGINT) = ?
        LIMIT 1
        """,
        [complex_id, structure_number],
    )
    if structure.empty:
        return {"platform": None, "approvals": [], "removal_history": []}
    row = _records(structure)[0]
    approvals = pd.DataFrame()
    if parquet_path(data_dir, "platform_approvals").is_file():
        approvals = duckdb_df(
            f"""
            SELECT *
            FROM {parquet_sql(data_dir, "platform_approvals")}
            WHERE UPPER(TRIM(COALESCE(AREA_CODE, ''))) = UPPER(TRIM(?))
              AND REGEXP_REPLACE(UPPER(TRIM(COALESCE(BLOCK_NUMBER, ''))), '\\s+', '', 'g')
                  = REGEXP_REPLACE(UPPER(TRIM(?)), '\\s+', '', 'g')
              AND UPPER(TRIM(COALESCE(PLATFORM_NAME, '')))
                  = UPPER(TRIM(COALESCE(?, '')))
            ORDER BY PLATFORM_APPROVAL_DATE DESC NULLS LAST
            """,
            [row.get("AREA_CODE"), row.get("BLOCK_NUMBER"), row.get("STRUCTURE_NAME")],
        )
    removals = pd.DataFrame()
    if parquet_path(data_dir, "platform_removals").is_file():
        removals = duckdb_df(
            f"""
            SELECT *
            FROM {parquet_sql(data_dir, "platform_removals")}
            WHERE TRY_CAST(COMPLEX_ID_NUM AS BIGINT) = ?
              AND TRY_CAST(STRUCTURE_NUMBER AS BIGINT) = ?
            ORDER BY REMOVAL_DATE DESC NULLS LAST, APPLICATION_FINAL_ACTION_DATE DESC NULLS LAST
            """,
            [complex_id, structure_number],
        )
    regulatory_approvals = pd.DataFrame()
    if parquet_path(data_dir, "asset_approvals").is_file():
        regulatory_approvals = duckdb_df(
            f"""
            SELECT *
            FROM {parquet_sql(data_dir, "asset_approvals")}
            WHERE LOWER(asset_type) = 'platform'
              AND link_method = 'exact_attribute'
              AND LOWER(CAST(asset_identifier AS VARCHAR)) = LOWER(?)
            ORDER BY event_date DESC NULLS LAST, approval_event_id
            """,
            [f"complex:{complex_id}"],
        )
    row.pop("LATITUDE", None)
    row.pop("LONGITUDE", None)
    row.pop("PTFRM_X_LOCATION", None)
    row.pop("PTFRM_Y_LOCATION", None)
    source_rows, warnings = _gdb_property_rows(
        data_dir, "Platforms", "Platforms"
    )
    source_attributes = None
    if source_rows is not None:
        wanted = (_asset_key(complex_id), _asset_key(structure_number))
        for source in source_rows:
            actual = (
                _asset_key(source.get("COMPLEX_ID_NUM")),
                _asset_key(source.get("STRUCTURE_NUMBER")),
            )
            if actual == wanted:
                source_attributes = {
                    "complex_id": source.get("COMPLEX_ID_NUM"),
                    "structure_number": source.get("STRUCTURE_NUMBER"),
                    "structure_name": source.get("STRUCTURE_NAME"),
                    "install_date": source.get("INSTALL_DATE"),
                    "removal_date": source.get("REMOVAL_DATE"),
                }
                break
    if not regulatory_approvals.empty and approvals.empty:
        warnings.append(
            f"Regulatory approvals resolve to complex {complex_id}, not specifically "
            f"to structure {structure_number}; they are returned as complex-level links."
        )
    return {
        "platform": row,
        "source_attributes": source_attributes,
        "approvals": top_rows(approvals, None, sample_limit),
        "regulatory_approvals": top_rows(
            regulatory_approvals, None, sample_limit
        ),
        "removal_history": top_rows(removals, None, sample_limit),
        "warnings": warnings,
    }


def _search_pipelines_parquet(
    data_dir: Path,
    *,
    status: str | None = None,
    product: str | None = None,
    company: str | None = None,
    query: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    _require(data_dir, "pipeline_permit_segments")
    conditions: list[str] = []
    parameters: list[Any] = []
    for column, value in (
        ("status_code", status),
        ("product_code", product),
    ):
        if value:
            conditions.append(f"LOWER(CAST({column} AS VARCHAR)) = LOWER(?)")
            parameters.append(value.strip())
    if company:
        conditions.append("LOWER(COALESCE(operator_name, '')) LIKE LOWER(?)")
        parameters.append(f"%{company.strip()}%")
    if query:
        conditions.append(
            "LOWER(CONCAT_WS(' ', segment_number, origin_name, destination_name, "
            "operator_name, origin_area_code, origin_block_number, destination_area_code, "
            "destination_block_number)) LIKE LOWER(?)"
        )
        parameters.append(f"%{query.strip()}%")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    frame = duckdb_df(
        f"""
        WITH ranked AS (
            SELECT *,
                ROW_NUMBER() OVER (
                    PARTITION BY CAST(segment_number AS VARCHAR)
                    ORDER BY approved_date DESC NULLS LAST, source_row_number DESC
                ) AS version_rank
            FROM {parquet_sql(data_dir, "pipeline_permit_segments")}
            {where}
        )
        SELECT
            segment_number,
            origin_name,
            origin_area_code,
            origin_block_number,
            origin_lease_number,
            destination_name,
            destination_area_code,
            destination_block_number,
            destination_lease_number,
            approved_date,
            status_code,
            product_code,
            operator_number,
            operator_name,
            max_water_depth_ft,
            maop_psi,
            segment_length_ft,
            authority_code,
            abandonment_date,
            out_of_service_date,
            COUNT(*) OVER() AS _total_count
        FROM ranked
        WHERE version_rank = 1
        ORDER BY segment_number
        LIMIT ? OFFSET ?
        """,
        [*parameters, page_size, (page - 1) * page_size],
    )
    total = int(frame.iloc[0]["_total_count"]) if not frame.empty else 0
    if "_total_count" in frame:
        frame = frame.drop(columns=["_total_count"])
    return {
        "rows": _records(frame),
        "page": page,
        "page_size": page_size,
        "total_count": total,
        "warnings": [],
    }


def search_pipelines(
    data_dir: Path,
    *,
    status: str | None = None,
    product: str | None = None,
    company: str | None = None,
    query: str | None = None,
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    source_rows, warnings = _gdb_property_rows(
        data_dir, "Pipelines", "Pipelines"
    )
    if source_rows is None:
        result = _search_pipelines_parquet(
            data_dir,
            status=status,
            product=product,
            company=company,
            query=query,
            page=page,
            page_size=page_size,
        )
        result["warnings"] = warnings
        return result

    normalized_rows = [
        {
            "segment_number": row.get("SEGMENT_NUM"),
            "segment_length_ft": row.get("SEG_LENGTH"),
            "status_code": row.get("STATUS_CODE"),
            "size_code": row.get("PPL_SIZE_CODE"),
            "row_number": row.get("ROW_NUMBER"),
            "product_code": row.get("PROD_CODE"),
            "approval_code": row.get("APRV_CODE"),
            "company": row.get("SDE_COMPANY_DESG"),
        }
        for row in source_rows
    ]

    def equals(value: Any, expected: str | None) -> bool:
        return not expected or str(value or "").strip().casefold() == expected.strip().casefold()

    filtered = []
    for row in normalized_rows:
        if not equals(row.get("status_code"), status):
            continue
        if not equals(row.get("product_code"), product):
            continue
        if company and company.strip().casefold() not in str(row.get("company") or "").casefold():
            continue
        searchable = " ".join(str(value or "") for value in row.values())
        if query and query.strip().casefold() not in searchable.casefold():
            continue
        filtered.append(row)

    offset = (page - 1) * page_size
    return {
        "rows": filtered[offset : offset + page_size],
        "page": page,
        "page_size": page_size,
        "total_count": len(filtered),
        "warnings": warnings,
    }


def pipeline_detail(
    data_dir: Path,
    segment_number: str,
    *,
    history_page: int = 1,
    history_page_size: int = 50,
    sample_limit: int = 10,
) -> dict[str, Any]:
    _require(data_dir, "pipeline_permit_segments")
    source_rows, warnings = _gdb_property_rows(
        data_dir, "Pipelines", "Pipelines"
    )
    source_attributes = None
    if source_rows is not None:
        wanted = _asset_key(segment_number)
        for source in source_rows:
            if _asset_key(source.get("SEGMENT_NUM")) == wanted:
                source_attributes = {
                    "segment_number": source.get("SEGMENT_NUM"),
                    "segment_length_ft": source.get("SEG_LENGTH"),
                    "status_code": source.get("STATUS_CODE"),
                    "size_code": source.get("PPL_SIZE_CODE"),
                    "row_number": source.get("ROW_NUMBER"),
                    "product_code": source.get("PROD_CODE"),
                    "approval_code": source.get("APRV_CODE"),
                    "company": source.get("SDE_COMPANY_DESG"),
                }
                break
    permits = duckdb_df(
        f"""
        SELECT *
        FROM {parquet_sql(data_dir, "pipeline_permit_segments")}
        WHERE CAST(segment_number AS VARCHAR) = ?
        ORDER BY approved_date DESC NULLS LAST, source_row_number DESC
        """,
        [segment_number],
    )
    if permits.empty:
        return {
            "segment": None,
            "source_attributes": source_attributes,
            "permit_history": {"rows": [], "total_count": 0},
            "submittals": [],
            "submittal_history": {
                "rows": [],
                "page": history_page,
                "page_size": history_page_size,
                "total_count": 0,
            },
            "connections": [],
            "platform_matches": [],
            "approvals": [],
            "warnings": warnings,
        }
    permit_rows = _records(permits)
    latest = dict(permit_rows[0])
    origin_key = latest.get("origin_endpoint_key")
    destination_key = latest.get("destination_endpoint_key")
    connection_conditions = []
    connection_parameters: list[Any] = [segment_number]
    for endpoint in (origin_key, destination_key):
        if endpoint:
            connection_conditions.extend(
                ["origin_endpoint_key = ?", "destination_endpoint_key = ?"]
            )
            connection_parameters.extend([endpoint, endpoint])
    connections = pd.DataFrame()
    if connection_conditions:
        connections = duckdb_df(
            f"""
            SELECT DISTINCT
                segment_number,
                origin_name,
                destination_name,
                operator_name,
                status_code,
                product_code
            FROM {parquet_sql(data_dir, "pipeline_permit_segments")}
            WHERE CAST(segment_number AS VARCHAR) <> ?
              AND ({' OR '.join(connection_conditions)})
            ORDER BY segment_number
            """,
            connection_parameters,
        )
    submittals = pd.DataFrame()
    if parquet_path(data_dir, "pipeline_submittals").is_file():
        submittals = duckdb_df(
            f"""
            SELECT *
            FROM {parquet_sql(data_dir, "pipeline_submittals")}
            WHERE CAST(segment_number AS VARCHAR) = ?
            ORDER BY status_date DESC NULLS LAST, received_date DESC NULLS LAST
            """,
            [segment_number],
        )
    approvals = pd.DataFrame()
    if parquet_path(data_dir, "asset_approvals").is_file():
        approvals = duckdb_df(
            f"""
            SELECT *
            FROM {parquet_sql(data_dir, "asset_approvals")}
            WHERE LOWER(asset_type) = 'pipeline'
              AND link_method = 'exact_attribute'
              AND LOWER(CAST(asset_identifier AS VARCHAR)) = LOWER(?)
            ORDER BY event_date DESC NULLS LAST
            """,
            [segment_number],
        )
    platform_matches = pd.DataFrame()
    if parquet_path(data_dir, "structures").is_file():
        conditions = []
        parameters = []
        for prefix in ("origin", "destination"):
            name = latest.get(f"{prefix}_name")
            area = latest.get(f"{prefix}_area_code")
            block = latest.get(f"{prefix}_block_number")
            if name and area and block:
                conditions.append(
                    "(UPPER(TRIM(STRUCTURE_NAME)) = UPPER(TRIM(?)) "
                    "AND UPPER(TRIM(AREA_CODE)) = UPPER(TRIM(?)) "
                    "AND REGEXP_REPLACE(UPPER(TRIM(BLOCK_NUMBER)), '\\s+', '', 'g') "
                    "= REGEXP_REPLACE(UPPER(TRIM(?)), '\\s+', '', 'g'))"
                )
                parameters.extend([name, area, block])
        if conditions:
            platform_matches = duckdb_df(
                f"""
                SELECT
                    COMPLEX_ID_NUM AS complex_id,
                    STRUCTURE_NUMBER AS structure_number,
                    STRUCTURE_NAME AS structure_name,
                    BUS_ASC_NAME AS operator,
                    AREA_CODE AS area_code,
                    BLOCK_NUMBER AS block_number,
                    LEASE_NUMBER AS lease_number,
                    REMOVAL_DATE AS removal_date
                FROM {parquet_sql(data_dir, "structures")}
                WHERE {' OR '.join(conditions)}
                ORDER BY complex_id, structure_number
                """,
                parameters,
            )
    offset = (history_page - 1) * history_page_size
    submittal_rows = _records(submittals)
    submittal_offset = (history_page - 1) * history_page_size
    submittal_page = submittal_rows[
        submittal_offset : submittal_offset + history_page_size
    ]
    source_status = (source_attributes or {}).get("status_code")
    permit_status = latest.get("status_code")
    if (
        source_status
        and permit_status
        and str(source_status).casefold() != str(permit_status).casefold()
    ):
        warnings.append(
            f"Pipeline source status {source_status} differs from latest permit "
            f"status {permit_status}; both are preserved with their source context."
        )
    return {
        "segment": latest,
        "source_attributes": source_attributes,
        "permit_history": {
            "rows": permit_rows[offset : offset + history_page_size],
            "page": history_page,
            "page_size": history_page_size,
            "total_count": len(permit_rows),
        },
        "submittals": submittal_page,
        "submittal_history": {
            "rows": submittal_page,
            "page": history_page,
            "page_size": history_page_size,
            "total_count": len(submittal_rows),
        },
        "connections": top_rows(connections, None, sample_limit),
        "platform_matches": top_rows(platform_matches, None, sample_limit),
        "approvals": top_rows(approvals, None, sample_limit),
        "warnings": warnings,
    }


def bulk_files(
    data_dir: Path,
    api_well_numbers: list[str],
    sample_limit: int = 10,
) -> dict[str, Any]:
    values = list(dict.fromkeys(value.strip() for value in api_well_numbers if value.strip()))
    if not values:
        raise ValueError("Provide at least one API well number")
    placeholders = ", ".join("?" for _ in values)
    attachments = duckdb_df(
        f"""
        SELECT
            API_WELL_NUMBER AS api_well_number,
            ATT_NAME AS attachment_name,
            ATT_EXTENSION AS attachment_extension,
            BUS_ASC_NAME AS operator_name,
            Source AS source,
            COUNT(*) AS duplicate_count
        FROM {parquet_sql(data_dir, "attachments")}
        WHERE API_WELL_NUMBER IN ({placeholders})
        GROUP BY ALL
        ORDER BY API_WELL_NUMBER, ATT_NAME, Source
        """,
        values,
    )
    files = duckdb_df(
        f"""
        SELECT
            API AS api_well_number,
            DOC_ID AS document_id,
            DOC_TYPE AS document_type,
            FILE_EXT AS file_extension,
            RUN_DATE AS run_date,
            FILE_SIZE AS file_size_source,
            LOG_SOURCE AS log_source,
            RELEASABLE_DATE AS releasable_date,
            CREATED_DATE AS created_date,
            LEASE AS lease_number,
            AREA AS area,
            BLOCK AS block
        FROM {parquet_sql(data_dir, "frs")}
        WHERE API IN ({placeholders})
        ORDER BY API, CREATED_DATE DESC NULLS LAST, DOC_ID
        """,
        values,
    )
    return {
        "api_well_numbers": values,
        "attachments": _records(attachments.head(sample_limit)),
        "files": _records(files.head(sample_limit)),
        "sample_limit": sample_limit,
        "counts": {
            "raw_attachment_rows": int(attachments["duplicate_count"].fillna(0).sum())
            if not attachments.empty
            else 0,
            "distinct_attachment_rows": int(len(attachments)),
            "frs_file_rows": int(len(files)),
        },
    }


def bulk_war(
    data_dir: Path,
    api_well_numbers: list[str],
    sample_limit: int = 10,
) -> dict[str, Any]:
    values = list(dict.fromkeys(value.strip() for value in api_well_numbers if value.strip()))
    if not values:
        raise ValueError("Provide at least one API well number")
    placeholders = ", ".join("?" for _ in values)
    frame = duckdb_df(
        f"""
        SELECT
            main.API_WELL_NUMBER AS api_well_number,
            main.SN_WAR AS report_id,
            main.WAR_START_DT AS start_date,
            main.WAR_END_DT AS end_date,
            main.RIG_NAME AS rig_name,
            main.BUS_ASC_NAME AS operator_name,
            remarks.TEXT_REMARK AS activity_remark
        FROM {parquet_sql(data_dir, "war_main")} main
        LEFT JOIN {parquet_sql(data_dir, "war_text")} remarks USING (SN_WAR)
        WHERE main.API_WELL_NUMBER IN ({placeholders})
        ORDER BY main.API_WELL_NUMBER, main.WAR_START_DT NULLS LAST, main.SN_WAR
        """,
        values,
    )
    return {
        "api_well_numbers": values,
        "rows": _records(frame.head(sample_limit)),
        "sample_limit": sample_limit,
        "counts": {"war_rows": int(len(frame))},
    }


def raw_well_records(
    data_dir: Path,
    api_well_number: str,
    dataset: str,
    *,
    page: int = 1,
    page_size: int = 25,
) -> dict[str, Any]:
    if dataset not in RAW_DATASETS:
        raise ValueError(
            f"Unknown raw dataset '{dataset}'. Use one of: {', '.join(sorted(RAW_DATASETS))}"
        )
    key, api_column = RAW_DATASETS[dataset]
    if not parquet_path(data_dir, key).is_file():
        warning = f"Missing optional dataset: {DATASETS[key]}"
        return {
            "dataset": dataset,
            "rows": [],
            "page": page,
            "page_size": page_size,
            "total_count": None,
            "warning": warning,
            "warnings": [warning],
        }
    if api_column:
        target = norm_api(api_well_number)
        frame = duckdb_df(
            f"""
            SELECT *, COUNT(*) OVER() AS _total_count
            FROM {parquet_sql(data_dir, key)}
            WHERE regexp_replace(CAST("{api_column}" AS VARCHAR), '[^0-9]', '', 'g') = ?
            LIMIT ? OFFSET ?
            """,
            [target, page_size, (page - 1) * page_size],
        )
        total = int(frame.iloc[0]["_total_count"]) if not frame.empty else 0
        if "_total_count" in frame:
            frame = frame.drop(columns=["_total_count"])
        return {
            "dataset": dataset,
            "rows": _records(frame),
            "page": page,
            "page_size": page_size,
            "total_count": total,
        }

    legacy = build_legacy_dossier(
        data_dir,
        api_well_number,
        max(page * page_size, page_size),
        100.0,
        include_production=False,
        include_completion_reconcile=False,
        include_casing_compare=False,
        include_timeline=False,
    )
    section_map = {
        "war_remarks": "war_remarks",
        "eor_completions": "eor_main",
        "geological_markers": "geological_markers",
        "perforations": "perforations",
        "war_casing_summary": "war_casing",
        "war_casing_properties": "war_casing",
        "open_hole_runs": "open_hole_logging",
        "open_hole_tools": "open_hole_logging",
        "apd_casing_intervals": "apd_casing",
        "apd_casing_sections": "apd_casing",
    }
    section = legacy["sections"].get(section_map[dataset], {})
    rows = list(section.get("sample", []))
    offset = (page - 1) * page_size
    warning = (
        "This indirect dataset is returned through the normalized dossier join "
        "because it does not carry API_WELL_NUMBER directly."
    )
    return {
        "dataset": dataset,
        "rows": rows[offset : offset + page_size],
        "page": page,
        "page_size": page_size,
        "total_count": section.get("records", len(rows)),
        "warning": warning,
        "warnings": [warning],
    }


def _well_approval_rows(
    data_dir: Path,
    api_well_number: str,
    sample_limit: int,
) -> dict[str, Any]:
    if not parquet_path(data_dir, "asset_approvals").is_file():
        return {
            "records": None,
            "sample": [],
            "warnings": [f"Missing optional dataset: {DATASETS['asset_approvals']}"],
        }
    frame = duckdb_df(
        f"""
        SELECT *
        FROM {parquet_sql(data_dir, "asset_approvals")}
        WHERE LOWER(asset_type) = 'well'
          AND regexp_replace(CAST(asset_identifier AS VARCHAR), '[^0-9]', '', 'g') = ?
        ORDER BY event_date DESC NULLS LAST, approval_event_id
        """,
        [norm_api(api_well_number)],
    )
    return {"records": int(len(frame)), "sample": top_rows(frame, None, sample_limit)}


def well_relationships(
    data_dir: Path,
    api_well_number: str,
    sample_limit: int,
) -> dict[str, Any]:
    """Resolve operator, field, lease, and platform links without map fields."""
    _require(data_dir, "boreholes")
    frame = duckdb_df(
        f"""
        SELECT
            NULLIF(NULLIF(TRIM(COMPANY_NAME), ''), 'UNKNOWN') AS operator_name,
            NULLIF(NULLIF(TRIM(FIELD), ''), 'UNKNOWN') AS field_code,
            NULLIF(NULLIF(TRIM("OPERATOR FIELD"), ''), 'UNKNOWN') AS field_name,
            NULLIF(NULLIF(TRIM(SURF_LEASE_NUMBER), ''), 'UNKNOWN')
                AS surface_lease_number,
            NULLIF(NULLIF(TRIM(SURF_AREA_CODE), ''), 'UNKNOWN') AS surface_area,
            NULLIF(NULLIF(TRIM(SURF_BLOCK_NUMBER), ''), 'UNKNOWN') AS surface_block,
            NULLIF(NULLIF(TRIM(BOTM_LEASE_NUMBER), ''), 'UNKNOWN')
                AS bottom_lease_number,
            NULLIF(NULLIF(TRIM(BOTM_AREA_CODE), ''), 'UNKNOWN') AS bottom_area,
            NULLIF(NULLIF(TRIM(BOTM_BLOCK_NUMBER), ''), 'UNKNOWN') AS bottom_block
        FROM {parquet_sql(data_dir, "boreholes")}
        WHERE API_WELL_NUMBER = ?
        LIMIT 1
        """,
        [api_well_number],
    )
    if frame.empty:
        return {
            "records": 0,
            "operator": None,
            "field": None,
            "surface_location": None,
            "bottom_location": None,
            "leases": [],
            "platforms": [],
            "warnings": [],
        }

    well = _records(frame)[0]
    warnings: list[str] = []
    operator = None
    if well.get("operator_name"):
        if parquet_path(data_dir, "company_all").is_file():
            companies = duckdb_df(
                f"""
                SELECT DISTINCT
                    MMS_COMPANY_NUM AS company_number,
                    BUS_ASC_NAME AS name,
                    MMS_START_DATE AS start_date,
                    MMS_TERM_DATE AS term_date
                FROM {parquet_sql(data_dir, "company_all")}
                WHERE UPPER(TRIM(BUS_ASC_NAME)) = UPPER(TRIM(?))
                ORDER BY MMS_TERM_DATE NULLS FIRST, MMS_START_DATE DESC NULLS LAST
                LIMIT 1
                """,
                [well["operator_name"]],
            )
            operator = (
                _records(companies)[0]
                if not companies.empty
                else {
                    "name": well["operator_name"],
                    "company_number": None,
                    "start_date": None,
                    "term_date": None,
                }
            )
        else:
            warnings.append(f"Missing optional dataset: {DATASETS['company_all']}")
            operator = {
                "name": well["operator_name"],
                "company_number": None,
                "start_date": None,
                "term_date": None,
            }

    roles_by_lease: dict[str, list[str]] = {}
    for role, key in (
        ("surface", "surface_lease_number"),
        ("bottom", "bottom_lease_number"),
    ):
        lease_number = well.get(key)
        if lease_number:
            roles_by_lease.setdefault(str(lease_number), []).append(role)

    lease_rows: list[dict[str, Any]] = []
    if roles_by_lease and parquet_path(data_dir, "lease_data").is_file():
        placeholders = ", ".join("?" for _ in roles_by_lease)
        leases = duckdb_df(
            f"""
            SELECT
                TRIM(LEASE_NUMBER) AS lease_number,
                LEASE_STATUS_CODE AS status,
                LEASE_EFFECTIVE_DATE AS effective_date,
                LEASE_EXPIRATION_DATE AS expiration_date,
                AREA_CODE AS area,
                BLOCK_NUMBER AS block,
                NUMBER_OF_PLATFORMS AS platform_count,
                FIRST_PRODUCTION_DATE AS first_production_date
            FROM {parquet_sql(data_dir, "lease_data")}
            WHERE TRIM(LEASE_NUMBER) IN ({placeholders})
            """,
            list(roles_by_lease),
        )
        by_number = {
            str(row["lease_number"]): row
            for row in _records(leases)
        }
        for lease_number, roles in roles_by_lease.items():
            row = by_number.get(
                lease_number,
                {
                    "lease_number": lease_number,
                    "status": None,
                    "effective_date": None,
                    "expiration_date": None,
                    "area": None,
                    "block": None,
                    "platform_count": None,
                    "first_production_date": None,
                },
            )
            row["roles"] = roles
            lease_rows.append(row)
    elif roles_by_lease:
        warnings.append(f"Missing optional dataset: {DATASETS['lease_data']}")
        lease_rows = [
            {"lease_number": lease_number, "roles": roles}
            for lease_number, roles in roles_by_lease.items()
        ]

    platform_rows: list[dict[str, Any]] = []
    if parquet_path(data_dir, "structures").is_file():
        platforms = duckdb_df(
            f"""
            SELECT DISTINCT
                structure.STRUCTURE_NAME AS structure_name,
                structure.STRUCTURE_NUMBER AS structure_number,
                structure.COMPLEX_ID_NUM AS complex_id,
                structure.STRUC_TYPE_CODE AS structure_type,
                structure.BUS_ASC_NAME AS operator_name,
                structure.LEASE_NUMBER AS lease_number,
                structure.REMOVAL_DATE AS removal_date,
                structure.WATER_DEPTH AS water_depth_ft
            FROM {parquet_sql(data_dir, "boreholes")} AS borehole
            JOIN {parquet_sql(data_dir, "structures")} AS structure
              ON UPPER(TRIM(borehole.SURF_AREA_CODE))
                    = UPPER(TRIM(structure.AREA_CODE))
             AND REGEXP_REPLACE(
                    UPPER(TRIM(borehole.SURF_BLOCK_NUMBER)),
                    '\\s+',
                    '',
                    'g'
                 ) = REGEXP_REPLACE(
                    UPPER(TRIM(structure.BLOCK_NUMBER)),
                    '\\s+',
                    '',
                    'g'
                 )
             AND POWER(borehole.SURF_LATITUDE - structure.LATITUDE, 2)
                 + POWER(
                    (borehole.SURF_LONGITUDE - structure.LONGITUDE)
                    * COS(RADIANS(borehole.SURF_LATITUDE)),
                    2
                 ) <= POWER(0.05 / 69.0, 2)
            WHERE borehole.API_WELL_NUMBER = ?
            ORDER BY structure_name, structure_number
            LIMIT ?
            """,
            [api_well_number, sample_limit],
        )
        platform_rows = _records(platforms)
    else:
        warnings.append(f"Missing optional dataset: {DATASETS['structures']}")

    field = (
        {"code": well.get("field_code"), "name": well.get("field_name")}
        if well.get("field_code") or well.get("field_name")
        else None
    )
    return {
        "records": (
            int(operator is not None)
            + int(field is not None)
            + len(lease_rows)
            + len(platform_rows)
        ),
        "operator": operator,
        "field": field,
        "surface_location": {
            "lease_number": well.get("surface_lease_number"),
            "area": well.get("surface_area"),
            "block": well.get("surface_block"),
        },
        "bottom_location": {
            "lease_number": well.get("bottom_lease_number"),
            "area": well.get("bottom_area"),
            "block": well.get("bottom_block"),
        },
        "leases": lease_rows,
        "platforms": platform_rows,
        "warnings": warnings,
    }


def _raw_counts(data_dir: Path, api_well_number: str) -> dict[str, int | None]:
    counts: dict[str, int | None] = {}
    for name, (key, api_column) in RAW_DATASETS.items():
        if not parquet_path(data_dir, key).is_file():
            counts[name] = None
            continue
        if api_column is None:
            counts[name] = None
            continue
        frame = duckdb_df(
            f"""
            SELECT COUNT(*) AS count
            FROM {parquet_sql(data_dir, key)}
            WHERE regexp_replace(CAST("{api_column}" AS VARCHAR), '[^0-9]', '', 'g') = ?
            """,
            [norm_api(api_well_number)],
        )
        counts[name] = int(frame.iloc[0]["count"])
    return counts


def build_dossier(
    data_dir: Path,
    repo: Path,
    api_well_number: str,
    sample_limit: int,
    *,
    sections: list[str] | None = None,
    min_step: float = 100.0,
) -> dict[str, Any]:
    legacy = build_legacy_dossier(
        data_dir,
        api_well_number,
        sample_limit,
        min_step,
        include_production=True,
        include_completion_reconcile=True,
        include_casing_compare=True,
        include_timeline=True,
    )
    section_data = dict(legacy["sections"])
    applications = well_applications(data_dir, api_well_number, sample_limit)
    documents = well_documents(data_dir, repo, api_well_number, sample_limit)
    legacy_timeline = section_data.get("timeline", {}).get("sample", [])
    section_data["relationships"] = well_relationships(
        data_dir,
        api_well_number,
        sample_limit,
    )
    section_data["ownership"] = dict(section_data.get("lease_information", {}))
    section_data["trajectory"] = {
        "records": section_data.get("azimuth_dls", {}).get("records", 0),
        "stations": section_data.get("azimuth_dls", {}).get("sample", []),
        "metrics": section_data.get("wellpath_metrics", {}).get("sample", []),
    }
    section_data["casing"] = {
        "records": sum(
            int(section_data.get(name, {}).get("records") or 0)
            for name in ("apd_casing", "war_casing")
        ),
        "planned_apd": section_data.get("apd_casing", {}).get("sample", []),
        "actual_war": section_data.get("war_casing", {}).get("sample", []),
        "reconciliation": section_data.get("casing_comparison", {}),
        "guardrail": (
            "APD casing is planned; WAR casing is reported actual work. "
            "Do not merge them as one physical casing record."
        ),
    }
    section_data["war"] = dict(section_data.get("war_remarks", {}))
    evidence_names = (
        "eor_main",
        "geological_markers",
        "bhp_survey",
        "perforations",
        "open_hole_logging",
    )
    section_data["wellbore_evidence"] = {
        "records": sum(
            int(section_data.get(name, {}).get("records") or 0)
            for name in evidence_names
        ),
        "samples": {
            name: section_data.get(name, {}).get("sample", [])
            for name in evidence_names
        },
        "trajectory": section_data["trajectory"],
    }
    section_data["applications"] = applications
    section_data["permits"] = well_applications(
        data_dir,
        api_well_number,
        sample_limit,
        source_family="APD",
    )
    section_data["documents"] = documents
    section_data["approvals"] = _well_approval_rows(data_dir, api_well_number, sample_limit)
    section_data["timeline"] = well_timeline(
        data_dir,
        api_well_number,
        legacy_timeline,
        sample_limit,
    )
    section_data["raw_dataset_counts"] = {
        "records": len(RAW_DATASETS),
        "counts": _raw_counts(data_dir, api_well_number),
    }
    decommissioning = build_decom_research(
        data_dir=data_dir,
        lease=None,
        api=api_well_number,
        area=None,
        block=None,
        min_cost=None,
        cost_case="p90",
        pa_adjustment=None,
        limit=sample_limit,
    )
    decommissioning["records"] = sum(
        int(value or 0)
        for value in decommissioning.get("summary", {}).values()
    )
    section_data["decommissioning"] = decommissioning
    if sections:
        unknown = sorted(set(sections) - set(section_data))
        if unknown:
            raise ValueError(
                f"Unknown dossier sections: {', '.join(unknown)}. "
                f"Use one or more of: {', '.join(sorted(section_data))}"
            )
        section_data = {name: section_data[name] for name in sections}

    def bound_lists(value: Any) -> Any:
        if isinstance(value, dict):
            return {key: bound_lists(item) for key, item in value.items()}
        if isinstance(value, list):
            rows = (
                value[:sample_limit]
                if any(isinstance(item, dict) for item in value)
                else value
            )
            return [bound_lists(item) for item in rows]
        return value

    section_data = bound_lists(section_data)
    return {
        "api_well_number": api_well_number,
        "identity": legacy["identity"],
        "availability": {
            name: section.get("records")
            for name, section in section_data.items()
            if isinstance(section, dict)
        },
        "sections": section_data,
    }


def doctor(data_dir: Path) -> dict[str, Any]:
    datasets = []
    missing_required = []
    invalid_required = []
    for key, spec in DATASET_CATALOG.items():
        path = data_dir / spec["filename"]
        row = {
            "key": key,
            "filename": spec["filename"],
            "family": spec["family"],
            "required": bool(spec["required"]),
            "status": "missing",
            "record_count": None,
            "missing_columns": [],
        }
        if path.is_file():
            try:
                columns = duckdb_df(
                    f"DESCRIBE SELECT * FROM {parquet_sql(data_dir, key)}"
                )["column_name"].astype(str).tolist()
                missing_columns = sorted(set(spec["required_columns"]) - set(columns))
                row["missing_columns"] = missing_columns
                row["record_count"] = _count(data_dir, key)
                row["status"] = "invalid" if missing_columns else "available"
            except Exception as error:
                row["status"] = "invalid"
                row["error"] = str(error)
        if spec["required"] and row["status"] == "missing":
            missing_required.append(key)
        if spec["required"] and row["status"] == "invalid":
            invalid_required.append(key)
        datasets.append(row)
    return {
        "data_dir": str(data_dir),
        "ok": not missing_required and not invalid_required,
        "required_dataset_count": sum(bool(spec["required"]) for spec in DATASET_CATALOG.values()),
        "available_dataset_count": sum(row["status"] == "available" for row in datasets),
        "missing_required": missing_required,
        "invalid_required": invalid_required,
        "datasets": datasets,
    }
