# Output Rules

Use this reference for full dossiers, JSON handoff, and answer formatting.

## Dossier Sections

For known API output, include:

- borehole details
- EOR main report
- raw wellpath survey data
- azimuth/deviation data
- DLS metrics and MD spacing issues
- derived per-well wellpath metrics from `df_wellpath_metrics.parquet`
- standard wellpath metrics
- calculated path metrics
- geological markers
- BHP survey records
- perforation intervals
- APD casing by submission version
- WAR casing by report version
- open-hole logging runs/tools

Also include discovery evidence when relevant:

- WAR keyword hits
- APD/APM attachment records
- FRS file records

## Optional Sections

- `--include-production`: production date range, totals, peak months, status codes, completion count.
- `--production-group-by ...`: plot-ready monthly production time series grouped by `Completion Name`, `Product Code`, or `Production Interval Code`.
- `--completion-reconcile`: side-by-side production completion identifiers vs EOR physical/reservoir completion records.
- `--casing-compare`: latest APD planned casing vs latest WAR actual casing/tubular evidence.
- `--timeline`: chronological events from borehole, APD, WAR, casing, logging, BHP, EOR, perforations, and production.
- `--incident`: preset keyword bundles such as `stuck-pipe`, `lost-circulation`, `kick`, `fishing`, `cementing`, and `logging`.
- `--field ... --audit`: rank matching wells by data availability across WAR, production, trajectory, APD, BHP, EOR, attachments, and FRS.

## JSON And HTML Handoff

Do not render HTML inside this skill unless the user explicitly asks.

Preferred workflow:

1. Generate evidence as JSON with `--format json --output ...`.
2. For trajectory plots/viewers, add `--full`; default JSON can contain preview/sample rows.
3. Pass JSON to a separate HTML/report/front-end skill or app.
4. Preserve source fields, units, dates, data availability counts, and absent-record notes.

Markdown can be saved with `--format markdown --output ...` when the renderer is Markdown-first.

## Answer Rules

- Start with an executive summary and data availability counts.
- Then provide section-by-section evidence.
- State when records are absent.
- Keep planned APD casing separate from actual WAR casing/tubular records.
- Do not treat production `Completion Name` and EOR `SN_EOR_WELL_COMP`/`INTERVAL` as identical.
- Use `--completion-reconcile` when users ask how production and EOR completions relate.
- For large tables, summarize by default and offer `--full` or JSON.
- Dates and depths should keep source units from the data; trajectory/casing depths are feet.
- For plotting, use `--format json --output ...`; production time series fields include `period_start`, `group`, `oil_volume`, `gas_volume`, `water_volume`, `days_on_prod`, and derived daily rates.

