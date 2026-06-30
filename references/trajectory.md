# Trajectory Rules

Use for trajectory, DLS, horizontal departure, and viewer questions.

## Metrics

Prefer `df_wellpath_metrics.parquet` for horizontal distance/departure, TVD delta, closure azimuth, inclination, lateral length, DLS, trajectory type, and metric status.

- Furthest horizontal: rank `wellpath_metrics` by `horizontal_departure`.
- Use source metrics only when the user asks for source endpoint/survey-derived values.
- Source metrics use lon/lat endpoints and TVD delta.
- Calculated metrics use full MD/inc/azimuth stations with minimum curvature.
- Metrics exclude plot-only artificial MD=0 rows.

## Coordinates

- Prefer `webmerc_easting_ft` / `webmerc_northing_ft`; `easting` / `northing` are legacy aliases.
- Do not calculate horizontal displacement from Web Mercator deltas.
- Source displacement uses local offsets from `Latitude` / `Longitude`.
- Calculated path displacement and DLS use `MD`, `Deviation Angle`, `Azimuth`.
- 3D viewers: use local east/north offsets plus TVD/depth; label vertical exaggeration.
- Surface-to-first-survey is visual only unless source data supports it.

## Type And Answer Checks

- `horizontal`: max inclination >= 80 degrees.
- `vertical`: MD-weighted average inclination <= 3 degrees.
- `directional`: everything else.
- Always report alias/column, value, units, API, trajectory type, station counts when available, and `metric_status`.
