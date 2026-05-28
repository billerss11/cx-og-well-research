"""Trajectory and dogleg severity helpers."""

from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from well_research_config import *
from well_research_core import *


def dls_analysis(azimuth: pd.DataFrame, min_step: float, limit: int) -> dict[str, Any]:
    if azimuth.empty or not {"MD", "Deviation Angle", "Azimuth"}.issubset(azimuth.columns):
        return {"records": int(len(azimuth)), "available": False, "units": AZIMUTH_DLS_UNITS}

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
        north.append(
            north[-1] + delta_md / 2 * (math.sin(inc1) * math.cos(azi1) + math.sin(inc2) * math.cos(azi2)) * rf
        )
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
        "units": AZIMUTH_DLS_UNITS,
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
        "sample": top_rows(
            used,
            [
                "MD",
                "Deviation Angle",
                "Azimuth",
                "DLS",
                "Calc_TVD_ft",
                "Calc_Easting_offset_ft",
                "Calc_Northing_offset_ft",
            ],
            limit,
        ),
    }


def lon_lat_to_local_offsets_ft(longitude: pd.Series, latitude: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    lon = pd.to_numeric(longitude, errors="coerce").to_numpy(dtype=float)
    lat = pd.to_numeric(latitude, errors="coerce").to_numpy(dtype=float)
    if len(lon) == 0:
        return lon, lat

    origin_lat_rad = math.radians(float(lat[0]))
    east = (lon - lon[0]) * math.pi / 180.0 * EARTH_RADIUS_FT * math.cos(origin_lat_rad)
    north = (lat - lat[0]) * math.pi / 180.0 * EARTH_RADIUS_FT
    return east, north


def standard_wellpath_metrics(points: pd.DataFrame) -> dict[str, Any]:
    if points.empty or "Survey Point TVD" not in points.columns:
        return {}

    p = points.sort_values("Survey Point MD") if "Survey Point MD" in points.columns else points.copy()
    tvd_values = pd.to_numeric(p["Survey Point TVD"], errors="coerce")
    first_tvd = float(tvd_values.iloc[0])
    final_tvd = float(tvd_values.iloc[-1])
    tvd_delta = final_tvd - first_tvd

    if {"Longitude", "Latitude"}.issubset(p.columns):
        east, north = lon_lat_to_local_offsets_ft(p["Longitude"], p["Latitude"])
        dx = float(east[-1] - east[0])
        dy = float(north[-1] - north[0])
        basis = "local_lon_lat_offsets"
    elif {"Calc_Easting_offset_ft", "Calc_Northing_offset_ft"}.issubset(p.columns):
        dx = float(p["Calc_Easting_offset_ft"].iloc[-1] - p["Calc_Easting_offset_ft"].iloc[0])
        dy = float(p["Calc_Northing_offset_ft"].iloc[-1] - p["Calc_Northing_offset_ft"].iloc[0])
        basis = "calculated_trajectory_offsets"
    elif {"easting", "northing"}.issubset(p.columns):
        dx = float(p["easting"].iloc[-1] - p["easting"].iloc[0])
        dy = float(p["northing"].iloc[-1] - p["northing"].iloc[0])
        basis = "webmerc_legacy_fallback"
    else:
        return {
            "first_tvd_ft": first_tvd,
            "final_tvd_ft": final_tvd,
            "tvd_delta_ft": tvd_delta,
            "coordinate_basis": "unavailable",
        }

    horiz = float(math.hypot(dx, dy))
    return {
        "horizontal_distance_ft": horiz,
        "first_tvd_ft": first_tvd,
        "final_tvd_ft": final_tvd,
        "tvd_delta_ft": tvd_delta,
        "horizontal_tvd_ratio": horiz / tvd_delta if tvd_delta else None,
        "delta_easting_ft": dx,
        "delta_northing_ft": dy,
        "coordinate_basis": basis,
    }
