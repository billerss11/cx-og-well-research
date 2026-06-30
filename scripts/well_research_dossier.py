"""Well dossier assembly."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from well_research_config import *
from well_research_core import *
from well_research_casing import build_apd_casing, build_casing_comparison, build_war_casing
from well_research_eor import build_geomarkers, build_perforations
from well_research_evidence import build_logging, build_timeline, build_war_text
from well_research_lease import build_lease_information
from well_research_production import build_completion_reconciliation, build_production_summary
from well_research_trajectory import dls_analysis, standard_wellpath_metrics


def build_dossier(
    data_dir: Path,
    api: str,
    limit: int,
    min_step: float,
    keyword: str | None = None,
    include_production: bool = False,
    production_group_by: dict[str, str] | None = None,
    include_completion_reconcile: bool = False,
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
    wellpath_metrics = query_api_dataset(data_dir, "wellpath_metrics", "API Number", api)
    bhp = query_api_dataset(data_dir, "bhp", "API_WELL_NUMBER", api, order_by="BHTST_DATE")
    if not bhp.empty:
        bhp = bhp.drop_duplicates(
            subset=[
                c
                for c in ["BHTST_DATE", "BHTST_MD", "BHTST_TVD", "BHTST_PRESSURE", "BHTST_SI_PRSS", "BHTST_TEMP"]
                if c in bhp.columns
            ]
        )

    geomarkers = build_geomarkers(data_dir, sn_eors)
    perf = build_perforations(data_dir, sn_eors)

    apd = query_api_dataset(data_dir, "apd_main", "API_WELL_NUMBER", api)
    apd_casing = build_apd_casing(data_dir, apd)
    war_casing = build_war_casing(data_dir, war_main)
    logging = build_logging(data_dir, war_main)
    lease_information = build_lease_information(data_dir, api, limit)

    attachments = query_api_dataset(data_dir, "attachments", "API_WELL_NUMBER", api)
    frs = query_api_dataset(data_dir, "frs", "API", api)
    war_text = build_war_text(data_dir, war_main, keyword)
    production = (
        build_production_summary(data_dir, api, production_group_by)
        if include_production or include_timeline or production_group_by
        else {"records": 0}
    )

    identity_cols = [
        "API_WELL_NUMBER",
        "WELL_NAME",
        "WELL_NAME_SUFFIX",
        "COMPANY_NAME",
        "FIELD",
        "OPERATOR FIELD",
        "AREA",
        "BLOCK",
        "LEASE",
        "WELL_SPUD_DATE",
        "TOTAL_DEPTH_DATE",
        "BH_TOTAL_MD",
        "WELL_BORE_TVD",
        "WELL_TD_SS",
        "RKB_ELEVATION",
        "WELL_TYPE_CODE",
        "BOREHOLE_STAT_CD",
        "WATER_DEPTH",
        "SURF_LATITUDE",
        "SURF_LONGITUDE",
        "BOTM_LATITUDE",
        "BOTM_LONGITUDE",
    ]

    standard_metrics = standard_wellpath_metrics(points)

    sections = {
        "borehole": {"records": int(len(bore)), "units": BOREHOLE_UNITS, "sample": top_rows(bore, None, limit)},
        "lease_information": lease_information,
        "eor_main": {"records": int(len(eor_main)), "sample": top_rows(eor_main, None, limit)},
        "wellpath_raw": {
            "records": int(len(points)),
            "units": TRAJECTORY_UNITS,
            "metrics": standard_metrics,
            "numeric_summary": numeric_summary(
                points,
                [
                    "Survey Point MD",
                    "Survey Point TVD",
                    "Latitude",
                    "Longitude",
                    "webmerc_easting_ft",
                    "webmerc_northing_ft",
                    "easting",
                    "northing",
                ],
            ),
            "sample": top_rows(
                points,
                [
                    "API Number",
                    "Survey Point MD",
                    "Survey Point TVD",
                    "Incl Ang Deg Val",
                    "Latitude",
                    "Longitude",
                    "webmerc_easting_ft",
                    "webmerc_northing_ft",
                ],
                limit,
            ),
        },
        "wellpath_metrics": {
            "records": int(len(wellpath_metrics)),
            "source": "df_wellpath_metrics.parquet",
            "units": WELLPATH_METRICS_UNITS,
            "sample": top_rows(wellpath_metrics, None, 1),
        },
        "azimuth_dls": dls_analysis(azimuth, min_step, limit),
        "geological_markers": {
            "records": int(len(geomarkers)),
            "units": EOR_INTERVAL_UNITS,
            "deepest_marker_ft": float(pd.to_numeric(geomarkers["TOP_MD"], errors="coerce").max())
            if not geomarkers.empty and "TOP_MD" in geomarkers.columns
            else None,
            "sample": top_rows(
                geomarkers.sort_values("TOP_MD") if "TOP_MD" in geomarkers.columns else geomarkers,
                ["GEO_MARKER_NAME", "TOP_MD"],
                limit,
            ),
        },
        "bhp_survey": {
            "records": int(len(bhp)),
            "units": BHP_UNITS,
            "date_range": date_range(bhp, "BHTST_DATE"),
            "sample": top_rows(bhp, None, limit),
        },
        "perforations": {
            "records": int(len(perf)),
            "units": EOR_INTERVAL_UNITS,
            "sample": top_rows(
                perf,
                [
                    "SN_EOR_FK",
                    "SN_EOR_WELL_COMP",
                    "INTERVAL",
                    "PERF_TOP_MD",
                    "PERF_BASE_MD",
                    "PERF_TOP_TVD",
                    "PERF_BOTM_TVD",
                ],
                limit,
            ),
        },
        "apd_casing": {
            "records": int(len(apd_casing)),
            "units": CASING_UNITS,
            "version_metrics": version_metrics(
                apd_casing, "Submission_Version", "Submission_Date", "CASING_SECTION_MD"
            ),
            "sample": top_rows(apd_casing, None, limit),
        },
        "war_casing": {
            "records": int(len(war_casing)),
            "units": CASING_UNITS,
            "version_metrics": version_metrics(
                war_casing,
                "Report_Version",
                "Report_End_Date",
                "CSNG_SETTING_BOTM_MD",
            ),
            "sample": top_rows(war_casing, None, limit),
        },
        "open_hole_logging": {"records": int(len(logging)), "sample": top_rows(logging, None, limit)},
        "war_remarks": {
            "records": int(len(war_text)),
            "date_range": date_range(war_text, "WAR_START_DT"),
            "sample": top_rows(
                war_text, ["SN_WAR", "WAR_START_DT", "WAR_END_DT", "RIG_NAME", "BUS_ASC_NAME", "TEXT_REMARK"], limit
            ),
        },
        "attachments": {"records": int(len(attachments)), "sample": top_rows(attachments, None, limit)},
        "frs_files": {
            "records": int(len(frs)),
            "sample": top_rows(
                frs,
                [
                    "DOC_ID",
                    "DOC_TYPE",
                    "API",
                    "WELL_NAME",
                    "RUN_DATE",
                    "FILE_EXT",
                    "LOG_SOURCE",
                    "COMMENTS",
                ],
                limit,
            ),
        },
    }

    if include_production or production_group_by:
        sections["production"] = production
    if include_completion_reconcile:
        sections["completion_reconciliation"] = build_completion_reconciliation(data_dir, api, limit)
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
