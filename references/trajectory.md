# Trajectory Rules

Use for measured depth, TVD, inclination, azimuth, DLS, horizontal departure, and trajectory classification.

## Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo well dossier <api> --sections trajectory,wellpath_metrics,azimuth_dls
conda run -n cxstreamlit python $script --repo $repo fields compare <field-1> <field-2>
conda run -n cxstreamlit python $script --repo $repo tables rank wellpath_metrics horizontal_departure
```

Prefer `wellpath_metrics` for calculated horizontal distance/departure, TVD delta, closure azimuth, inclination, lateral length, DLS, trajectory type, and metric status.

- Calculated metrics use MD/inclination/azimuth stations and minimum curvature.
- Metrics exclude artificial plot-only MD=0 rows.
- Horizontal: maximum inclination at least 80 degrees.
- Vertical: MD-weighted average inclination at most 3 degrees.
- Directional: everything else.

Report API, metric alias and resolved column, value, units, station count, trajectory type, and metric status.

Map output is excluded. Do not return latitude, longitude, easting, northing, geometry, GeoJSON, bathymetry, or continental-shelf data.
