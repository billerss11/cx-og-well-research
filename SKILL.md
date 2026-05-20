---
name: cx-og-well-research
description: Use when the user wants to find, research, summarize, audit, or explain Gulf of Mexico wells from local ready-to-use Parquet datasets, including keyword discovery, single-well dossiers, field audits, WAR, APD/APM attachments, FRS files, trajectory, DLS, EOR, geomarkers, BHP, perforations, casing, production, and open-hole logging data.
---

# CX O&G Well Research

Use this skill as the broad research workflow for local Gulf of Mexico well Parquet data.

Runtime needs the ready Parquet folder, not the full app source. Repo discovery is only a convenience when running from the CX O&G APP root.

## Quick Workflow

1. If the user gives a keyword or vague topic, run discovery mode first.
2. If the user gives an API number, run dossier mode.
3. If discovery returns many wells, ask the user which API to inspect before producing a full dossier.
4. Use script output as evidence. Do not invent missing records.

## Script Usage

Use the shared conda env when the default Python does not have DuckDB:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --check-data-dir --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Full dossier:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Keyword discovery:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --keyword "stuck pipe" --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Keyword discovery filtered to a field/operator/name:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --keyword casing --filter MADISON --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Incident preset search:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --incident stuck-pipe --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Full dossier with optional analysis sections:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --include-production --casing-compare --timeline --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Field data-completeness audit:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --field MADISON --audit --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

JSON:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --format json --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Save output for another renderer:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --include-production --casing-compare --timeline --format json --output well_608054000500.json --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Plot-ready production JSON:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --production-group-by "Production Interval Code" --format json --output production_608054000500.json --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Completion reconciliation:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 427064030600 --completion-reconcile --format json --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

More rows:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --full --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

## HTML Handoff

Do not render HTML inside this skill unless the user explicitly asks. Prefer this workflow:

1. Use this skill to generate evidence as JSON with `--format json --output ...`.
2. Pass that JSON file to a separate HTML/report/front-end skill or app.
3. The renderer should preserve source fields, units, dates, data availability counts, and absent-record notes.

Markdown output can also be saved with `--format markdown --output ...` when the renderer is Markdown-first.

## Dossier Sections

For known API output, include these sections:

- Borehole details
- EOR main report
- Raw wellpath survey data
- Azimuth/deviation data
- DLS metrics and MD spacing issues
- Standard wellpath metrics
- Calculated path metrics
- Geological markers
- BHP survey records
- Perforation intervals
- APD casing by submission version
- WAR casing by report version
- Open-hole logging runs/tools

Also include discovery evidence:

- WAR keyword hits if a keyword was supplied
- APD/APM attachment records
- FRS file records

Optional analysis sections:

- `--include-production`: production date range, totals, peak months, status codes, completion count.
- `--production-group-by ...`: plot-ready monthly production time series grouped by `Completion Name`, `Product Code`, or `Production Interval Code`.
- `--completion-reconcile`: side-by-side production completion identifiers vs EOR physical/reservoir completion records.
- `--casing-compare`: latest APD planned casing vs latest WAR actual casing/tubular evidence.
- `--timeline`: chronological events from borehole, APD, WAR, casing, logging, BHP, EOR, perforations, and production.
- `--incident`: preset keyword bundles such as `stuck-pipe`, `lost-circulation`, `kick`, `fishing`, `cementing`, and `logging`.
- `--field ... --audit`: rank matching wells by data availability across WAR, production, trajectory, APD, BHP, EOR, attachments, and FRS.

## Answer Rules

- Start with an executive summary and data availability counts.
- Then provide section-by-section evidence.
- Keep planned APD casing separate from actual WAR casing/tubular records.
- State when records are absent.
- Do not treat production `Completion Name` and EOR `SN_EOR_WELL_COMP`/`INTERVAL` as identical; use `--completion-reconcile` when users ask how they relate.
- For large tables, summarize by default and offer `--full`/JSON for more rows.
- For plotting, use `--format json --output ...`; the production time series uses neutral fields like `period_start`, `group`, `oil_volume`, `gas_volume`, `water_volume`, `days_on_prod`, and derived daily rates.
- Dates and depths should keep source units from the data; trajectory/casing depths are feet.
