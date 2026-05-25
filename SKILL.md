---
name: cx-og-well-research
description: Use when the user asks to find, rank, research, summarize, audit, or explain Gulf of Mexico wells from local CX O&G Parquet data, including API well dossiers, keyword discovery, field audits, WAR/APD/APM/FRS evidence, trajectory, DLS, EOR, BHP, perforations, casing, production, logging, or decommissioning.
---

# CX O&G Well Research

Use the bundled CLI as the evidence source. Do not invent missing records.

Runtime needs the ready Parquet data folder. Repo discovery is only a convenience when running from the CX O&G APP root.

## Core Command

Use the shared env if default Python lacks DuckDB:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --check-data-dir --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

## Decision Workflow

1. Vague topic or incident: run discovery first with `--keyword` or `--incident`.
2. Known API number: run dossier mode with `--api`.
3. Field/operator/name question: use `--field`; add `--audit` for data-completeness ranking.
4. Ranked question: use `--describe-table` if column names are unclear, then `--rank-table` and `--rank-by`.
5. Many wells returned: ask which API to inspect before building a full dossier.
6. Plots, reports, or renderers: export JSON with `--format json --output ...`.

## Common Commands

Full dossier:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Keyword discovery:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --keyword "stuck pipe" --filter MADISON --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Describe available columns, aliases, units, and sample rows:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --describe-table wellpath_metrics --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Rank a table by a real column or metric alias:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --rank-table wellpath_metrics --rank-by horizontal_departure --limit 10 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Full JSON for handoff:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --full --format json --output well_608054000500_full.json --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

## Metric Aliases

Use aliases when the user speaks in plain English. Run `--describe-table <table>` to see aliases supported by that table.

Important aliases:

- `wellpath_metrics`: `horizontal_departure`, `horizontal_distance`, `source_horizontal_departure`, `lateral_length`, `max_dls`, `avg_dls`, `trajectory_type`, `closure_azimuth`, `max_inclination`.
- `boreholes`: `total_depth`, `measured_depth`, `tvd`, `water_depth`.
- `production`: `production_oil`, `oil_volume`, `production_gas`, `gas_volume`, `production_water`, `water_volume`, `days_on_prod`.
- `decom_spud_well` / `decom_totals`: `decom_cost`, `p50_cost`, `p70_cost`, `p90_cost`.

## Workflow Recipes

Furthest horizontal well:

1. Rank `wellpath_metrics` by `horizontal_departure` descending.
2. Take the top `API Number`.
3. Run dossier mode for that API.
4. State metric, value, API, trajectory type, station counts, and metric status.

Deepest well:

1. Rank `boreholes` by `total_depth` descending.
2. Take `API_WELL_NUMBER`.
3. Run dossier mode.

Highest DLS:

1. Rank `wellpath_metrics` by `max_dls` descending.
2. Inspect `metric_status`, station counts, and spacing before making a strong claim.
3. Run dossier mode for the top API.

Field audit:

1. Run `--field <name> --audit`.
2. Report data score and availability counts.
3. Ask for an API before creating a full dossier if many wells match.

APD planned vs WAR actual casing:

1. Run dossier mode with `--casing-compare`.
2. Keep planned APD casing separate from actual WAR casing/tubular evidence.

Production vs EOR completion reconciliation:

1. Run dossier mode with `--completion-reconcile`.
2. Do not treat production `Completion Name` and EOR completion identifiers as identical.

## References

Load only when needed:

- `references/trajectory.md`: trajectory, DLS, map coordinate, and wellpath metric rules.
- `references/casing.md`: casing search and APD/WAR comparison rules.
- `references/decommissioning.md`: decommissioning cost/inventory workflows.
- `references/output-rules.md`: dossier sections, answer format, JSON/HTML handoff rules.

