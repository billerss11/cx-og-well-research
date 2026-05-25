# Trajectory And Wellpath Rules

Use this reference for trajectory, DLS, horizontal departure, and 2D/3D viewer questions.

## Metric Source

Prefer `df_wellpath_metrics.parquet` for query/export/ranking of per-well horizontal distance, TVD delta, closure azimuth, max departure, inclination, lateral length, DLS summary, trajectory type, and metric quality/status.

`df_wellpath_metrics.parquet` is one row per API:

- Source metrics use source survey lon/lat endpoints and TVD delta.
- Calculated metrics use full real MD/inc/azimuth stations via minimum curvature.
- Metrics do not use plot-only artificial MD=0 rows.

For "furthest horizontally", rank `wellpath_metrics` by alias `horizontal_departure`, which resolves to `calc_max_horizontal_departure_ft`.

Use `source_max_horizontal_departure_ft` only when the user explicitly wants source endpoint/survey-derived metrics instead of calculated minimum-curvature metrics.

## Coordinate Rules

- `df_points.easting` / `df_points.northing` are legacy Web Mercator aliases.
- Prefer `webmerc_easting_ft` / `webmerc_northing_ft` when showing map coordinates.
- Do not calculate wellpath horizontal displacement from Web Mercator deltas.
- For source wellpath displacement, use local offsets from `Latitude` / `Longitude`.
- For calculated path displacement and DLS, use `MD`, `Deviation Angle`, `Azimuth`, and minimum-curvature offsets.
- For 3D viewers, build local east/north offsets from `Latitude` / `Longitude`; use TVD/depth as vertical axis and label vertical scale/exaggeration clearly.
- If the first survey station MD is above 0, surface-to-first-survey is only a visual guide unless source data provides that segment.
- `df_azimuth.parquet` preserves `TVD`, `Latitude`, `Longitude`, `Neg TVD`, `webmerc_easting_ft`, and `webmerc_northing_ft` for auditability.

## Trajectory Type

- `horizontal`: max inclination is at least 80 degrees from vertical.
- `vertical`: MD-weighted average inclination is at most 3 degrees.
- `directional`: remaining non-horizontal, non-vertical wells.

## Answer Checks

Always report:

- metric column or alias used
- metric value and units
- API number
- trajectory type
- point and azimuth station counts when available
- `metric_status`

