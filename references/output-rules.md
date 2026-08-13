# Output Contract

Successful JSON keys: `schema_version`, `command`, `query`, `data`, `provenance`, `coverage`, `warnings`.

Exit codes: `0` success/empty search; `1` unexpected failure; `2` invalid input; `3` required data unavailable.

Answer with the result first, then material limits. Preserve IDs, dates, units, counts, ordering, provenance, warnings, and scalar latitude/longitude fields. Say “no matching records” only with available required data; otherwise say coverage is partial. Confirm fuzzy IDs. Keep APD/WAR casing, production/EOR completion IDs, ownership/legal-party claims, and exact/unresolved links distinct. Return document metadata/paths only. Exclude rendered maps, geometry, GeoJSON, bathymetry, shelf layers, and map-only coordinate systems.

Use `--page-size` for paginated/history rows and `--sample-limit` for samples. Put durable-output flags before the command:

```powershell
conda run -n cxstreamlit python $script --output <result.json> <command...>
```
