---
name: cx-og-well-research
description: Use when the user wants to find, research, summarize, audit, or explain Gulf of Mexico wells in the CX O&G APP using keyword discovery plus full single-well dossier output from borehole, WAR, APD/APM attachments, FRS files, trajectory, DLS, EOR, geomarkers, BHP, perforations, casing, and open-hole logging datasets.
---

# CX O&G Well Research

Use this skill as the broad research workflow for local CX O&G APP data.

It combines:
- `Pages/1_GOM_Advanced_File_Search.py`: keyword discovery across WAR remarks, attachments, FRS, and bulk API lookup.
- `Pages/8_wellbore_info_dashboard.py`: full single-well dossier schema.

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

More rows:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --full --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Runtime needs the ready Parquet folder, not the full app source. Repo discovery is only a convenience when running from the CX O&G APP root.

## Dossier Sections

For known API output, include these sections from page 8:

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

Also include page 1 evidence:

- WAR keyword hits if a keyword was supplied
- APD/APM attachment records
- FRS file records

Optional analysis sections:

- `--include-production`: production date range, totals, peak months, status codes, completion count.
- `--casing-compare`: latest APD planned casing vs latest WAR actual casing/tubular evidence.
- `--timeline`: chronological events from borehole, APD, WAR, casing, logging, BHP, EOR, perforations, and production.
- `--incident`: preset keyword bundles such as `stuck-pipe`, `lost-circulation`, `kick`, `fishing`, `cementing`, and `logging`.
- `--field ... --audit`: rank matching wells by data availability across WAR, production, trajectory, APD, BHP, EOR, attachments, and FRS.

## Answer Rules

- Start with an executive summary and data availability counts.
- Then provide section-by-section evidence.
- Keep planned APD casing separate from actual WAR casing/tubular records.
- State when records are absent.
- For large tables, summarize by default and offer `--full`/JSON for more rows.
- Dates and depths should keep source units from the data; page 8 treats trajectory/casing depths as feet.
