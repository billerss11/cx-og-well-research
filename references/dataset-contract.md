# Dataset Contract

Use `doctor` when the data path is uncertain; `tables list` for availability; `tables describe <table>` for columns/units/aliases; `tables rank <table> <alias-or-column> --direction asc|desc` for reproducible rankings.

The catalog defines each Parquet key, filename, family, required flag, expected columns, identifiers, units, and aliases. Missing/invalid required data makes a command unavailable; missing optional data yields partial `coverage` plus a warning.

For rankings, report requested alias, resolved column, direction, units, count, and sampled rows; inspect the leading API/asset before strong claims. Preserve scalar latitude/longitude columns and units. Map payloads, geometry, GeoJSON, bathymetry, shelf layers, and map-only coordinate systems are excluded.
