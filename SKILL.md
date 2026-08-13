---
name: cx-og-well-research
description: Query current CX Gulf of Mexico O&G data for wells, fields, leases, production, regulatory evidence, approvals, platforms, pipelines, casing, decommissioning, and raw tables. Use for non-map Vue-equivalent queries, exact/fuzzy discovery, drill-downs, comparisons, audits, rankings, dossiers, and source-backed answers.
---

# CX O&G Research

Use the bundled standalone CLI; never import or run the app backend. Resolve
`scripts/cx_og_research.py` relative to this `SKILL.md`; never hard-code the
skill installation path. Set `$skillRoot` to the directory containing this
loaded `SKILL.md`.

```powershell
$script = Join-Path $skillRoot "scripts\cx_og_research.py"
conda run -n cxstreamlit python $script <command...>
```

The CLI reads only CX Parquet datasets. It does not require the CX application
repository. Global options precede the command: `--data-dir`, `--format
json|markdown`, `--output`, `--sample-limit`. JSON is default. Use `<group> -h`
or `<group> <action> -h` for syntax.

## First-run data setup

Run the requested query normally. If the CLI reports that the data folder is
not configured or unavailable:

1. Ask the user: "Please provide the folder containing the CX Parquet files."
2. Do not ask them to set an environment variable or find the application repository.
3. Run `configure <folder>` with their answer. This validates and saves the path locally for that machine.
4. If no recognized Parquet files are found, explain that the selected folder is incorrect and ask again.
5. Retry the original query after configuration succeeds.

Use `--data-dir` only for a one-query override. `CX_OG_DATA_DIR` is an optional
advanced override; never require the user to understand or configure it.

## Route

- Discovery/evidence: `wells search|suggestions|filter-options`; `evidence search|detail`.
- Known API: `well identity|summary|availability|relationships|ownership|lease-activity|production|trajectory|trajectory-analysis|wellbore|casing|casing-versions|casing-analysis|war|war-record|permits|files|applications|documents|timeline|timeline-detail|raw|dossier|batch`.
- Fields/production: `fields list|wells|compare|trajectory-comparison|leases|lease-context`; `production compare`.
- Infrastructure/regulatory: `platforms search|detail`; `pipelines search|detail`; `approvals search|options`.
- Bulk/global: `bulk files|war`; `casing search`; `decommissioning search|authorities|authority|well|pipeline|platform`; `tables list|describe|rank`; `doctor`.

## Rules

- Treat `coverage` and `warnings` as results. Missing optional data means partial coverage; empty searches are valid.
- Confirm fuzzy matches with exact identifiers. Preserve IDs, dates, units, counts, ordering, and source/link confidence.
- Separate APD planned from WAR actual casing; production completion names from EOR IDs; current/terminated owners from inferred buyers/sellers.
- Return document metadata from Parquet. Do not discover or return local document paths.
- Preserve scalar latitude/longitude fields in query results. Exclude rendered maps, geometry, GeoJSON, bathymetry, shelf layers, and map-only coordinate systems.
- Use `--page-size` for pages/history and `--sample-limit` for dossier/representative samples.

## References

Load only what applies:

- `references/api-parity.md`: command coverage, special forms, exclusions.
- `references/regulatory.md`: applications, evidence, documents, approvals.
- `references/assets.md`: platform/pipeline detail, cathodic protection.
- `references/casing.md`, `lease.md`, `trajectory.md`, `decommissioning.md`: domain interpretation.
- `references/dataset-contract.md`: availability, schemas, units, rankings.
- `references/output-rules.md`: envelope, exit codes, answer contract.
