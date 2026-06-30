# Output Rules

Use for full dossiers, JSON handoff, and answer formatting.

## Dossiers

Report available record counts and evidence for: borehole identity, lease/block/owners, EOR/BHP/perf/markers, wellpath/DLS/metrics, APD casing, WAR casing/text/logging, APD/APM attachments, and FRS files.

Optional flags:

- `--include-production`: production range, totals, peaks, status, completion count.
- `--production-group-by ...`: monthly plot data by completion/product/interval.
- `--completion-reconcile`: production completion IDs vs EOR physical completions.
- `--casing-compare`: latest planned APD casing vs latest actual WAR casing.
- `--timeline`: chronological well evidence.
- `--field ... --audit`: data-availability ranking.

## Answer Rules

- Start with summary and data availability.
- State absent records plainly.
- Preserve source fields, units, dates, and section counts.
- Keep APD planned casing separate from WAR actual casing.
- Do not equate production `Completion Name` with EOR completion IDs.
- Do not present lease assignment history as explicit buyer/seller pairs without separate proof.
- For plots/apps/reports, prefer `--format json --output ...`; add `--full` for broad exports.
