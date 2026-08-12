# Trajectory

Commands: `well trajectory-analysis <api> --min-step 100`; `well dossier <api> --sections trajectory,wellpath_metrics,azimuth_dls`; `fields compare <fields...>`; `fields trajectory-comparison <field> --api <api>`; `tables rank wellpath_metrics horizontal_departure`.

Prefer `wellpath_metrics` for departure, TVD delta, closure azimuth, inclination, lateral length, DLS, type, and status. Calculations use MD/inclination/azimuth with minimum curvature and exclude artificial plot-only MD=0 rows.

Classification: horizontal if max inclination ≥80°; vertical if MD-weighted average inclination ≤3°; otherwise directional.

Report API, requested alias/resolved column, value, units, station count, type, and metric status. Preserve scalar latitude/longitude values. Exclude geometry, GeoJSON, rendered map layers, and map-only coordinate systems.
