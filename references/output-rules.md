# Output Rules

Use for full dossiers, JSON handoff, and answer formatting.

## Dossiers

Known API dossiers should report available record counts and evidence from:

- borehole identity, EOR main report, BHP, perforations, geological markers
- raw wellpath, azimuth/deviation, DLS, and `df_wellpath_metrics.parquet`
- APD casing by submission version and WAR casing by report version
- open-hole logging, WAR remarks, APD/APM attachments, and FRS files

Optional flags:

- `--include-production`: production range, totals, peaks, status codes, completion count.
- `--production-group-by ...`: monthly plot data by completion, product, or interval code.
- `--completion-reconcile`: compare production completion identifiers against EOR completion records.
- `--casing-compare`: latest planned APD casing versus latest actual WAR casing.
- `--timeline`: chronological borehole/APD/WAR/casing/logging/BHP/EOR/perf/production events.
- `--field ... --audit`: rank wells by data availability.

## Handoff

- Do not render HTML unless explicitly asked.
- Prefer `--format json --output ...` for plots, reports, apps, and front-end handoff.
- Add `--full` for trajectory viewers or broad exports.
- Preserve source fields, units, dates, availability counts, and absent-record notes.
- Markdown output is fine for Markdown-first reports.

## Answers

- Start with an executive summary and data availability counts.
- Then give section-by-section evidence.
- State absent records plainly.
- Keep planned APD casing separate from actual WAR casing/tubular records.
- Do not equate production `Completion Name` with EOR `SN_EOR_WELL_COMP` or `INTERVAL`.
- For large tables, summarize and offer `--full` or JSON.
- Keep source units; trajectory/casing depths are feet.
