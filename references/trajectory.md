# Trajectory And Wellpath Rules

Use for trajectory, DLS, horizontal departure, and viewer questions.

## Metrics

Prefer `df_wellpath_metrics.parquet` for per-well horizontal distance, TVD delta, closure azimuth, max departure, inclination, lateral length, DLS, trajectory type, and metric status.

- For "furthest horizontally", rank `wellpath_metrics` by alias `horizontal_departure`.
- Use `source_max_horizontal_departure_ft` only when the user asks for source endpoint/survey-derived metrics.
- Source metrics use lon/lat endpoints and TVD delta.
- Calculated metrics use full MD/inc/azimuth stations with minimum curvature.
- Metrics do not use plot-only artificial MD=0 rows.

## Coordinates

- `df_points.easting` / `northing` are legacy Web Mercator aliases.
- Prefer `webmerc_easting_ft` / `webmerc_northing_ft` for displayed map coordinates.
- Do not calculate horizontal displacement from Web Mercator deltas.
- Source displacement uses local offsets from `Latitude` / `Longitude`.
- Calculated path displacement and DLS use `MD`, `Deviation Angle`, `Azimuth`, and minimum curvature.
- For 3D viewers, use local east/north offsets and TVD/depth as vertical axis; label vertical exaggeration.
- If first survey MD is above 0, surface-to-first-survey is visual only unless source data provides it.

## Trajectory Type

- `horizontal`: max inclination >= 80 degrees from vertical.
- `vertical`: MD-weighted average inclination <= 3 degrees.
- `directional`: all remaining wells.

## Answer Checks

Always report metric alias/column, value, units, API number, trajectory type, station counts when available, and `metric_status`.
