"""EOR marker and perforation helpers."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from well_research_core import duckdb_df, parquet_sql


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
