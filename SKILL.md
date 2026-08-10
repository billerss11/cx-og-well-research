---
name: cx-og-well-research
description: Query current CX Gulf of Mexico O&G data for wells, fields, leases, production, regulatory evidence, approvals, platforms, pipelines, casing, decommissioning, and raw tables. Use for non-map Vue-equivalent queries, exact/fuzzy discovery, drill-downs, comparisons, audits, rankings, dossiers, and source-backed answers.
---

# CX O&G Research

Use the bundled standalone CLI; never import or run the app backend.

```powershell
$script = "C:\Users\17999\.codex\skills\cx-og-well-research\scripts\cx_og_research.py"
$repo = "J:\cx_coding_project_unsyc\python\CX_O-G_APP"
conda run -n cxstreamlit python $script --repo $repo <command...>
```

Global options precede the command: `--data-dir`, `--format json|markdown`, `--output`, `--sample-limit`. JSON is default. Use `<group> -h` or `<group> <action> -h` for syntax.

## Route

- Discovery/evidence: `wells search|suggestions|filter-options`; `evidence search|detail`.
- Known API: `well identity|summary|availability|relationships|ownership|lease-activity|production|trajectory|trajectory-analysis|wellbore|casing|casing-versions|casing-analysis|war|war-record|war-report-text|permits|files|applications|documents|timeline|timeline-detail|raw|dossier|batch`.
- Fields/production: `fields list|wells|compare|trajectory-comparison|leases|lease-context`; `production compare`.
- Infrastructure/regulatory: `platforms search|detail`; `pipelines search|detail`; `approvals search|options`.
- Bulk/global: `bulk files|war`; `casing search`; `decommissioning search|authorities|authority|well|pipeline|platform`; `tables list|describe|rank`; `doctor`.

## Rules

- Treat `coverage` and `warnings` as results. Missing optional data means partial coverage; empty searches are valid.
- Confirm fuzzy matches with exact identifiers. Preserve IDs, dates, units, counts, ordering, and source/link confidence.
- Separate APD planned from WAR actual casing; production completion names from EOR IDs; current/terminated owners from inferred buyers/sellers.
- Return document metadata/paths only unless file reading is separately requested.
- Exclude maps, geometry, coordinates, GeoJSON, bathymetry, and shelf layers.
- Use `--page-size` for pages/history and `--sample-limit` for dossier/representative samples.

## References

Load only what applies:

- `references/api-parity.md`: command coverage, special forms, exclusions.
- `references/regulatory.md`: applications, evidence, documents, approvals.
- `references/assets.md`: platform/pipeline detail, cathodic protection.
- `references/casing.md`, `lease.md`, `trajectory.md`, `decommissioning.md`: domain interpretation.
- `references/dataset-contract.md`: availability, schemas, units, rankings.
- `references/output-rules.md`: envelope, exit codes, answer contract.
