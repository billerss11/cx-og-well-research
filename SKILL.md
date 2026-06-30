---
name: cx-og-well-research
description: Use when the user asks to find, rank, research, summarize, audit, or explain Gulf of Mexico wells from local CX O&G Parquet data, including API well dossiers, lease/block/current ownership and assignment history, keyword discovery, field audits, WAR/APD/APM/FRS evidence, trajectory, DLS, EOR, BHP, perforations, casing, production, logging, or decommissioning.
---

# CX O&G Well Research

Use the bundled CLI as the evidence source. Do not invent missing records.

Set these once:

```powershell
$script = "C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py"
$data = "J:\cx_coding_project_unsyc\python\CX_O-G_APP\data"
conda run -n codex_env python $script --check-data-dir --data-dir $data
```

## Route

- Unknown topic/incident: use `--keyword` or `--incident`.
- Known API: use `--api`; API dossiers include `lease_information` when lease parquet files exist.
- Field/operator/name: use `--field`; add `--audit` for data-completeness ranking.
- Ranked metric/table: use `--describe-table <key>` if columns are unclear, then `--rank-table <key> --rank-by <alias-or-column>`.
- Casing-size search: use `--casing-sizes`, plus `--casing-source`, `--casing-match`, `--casing-latest-only` as needed.
- Production/chart/timeline: add `--include-production`, `--production-group-by`, or `--timeline`; use JSON for handoff.
- Decommissioning: use `--decom`, `--decom-api`, `--decom-lease`, `--decom-area`, `--decom-block`, or cost filters.
- Many wells returned: ask which API to inspect before building a full dossier.

## Command Patterns

```powershell
conda run -n codex_env python $script --api <api> --data-dir $data
conda run -n codex_env python $script --keyword "<text>" --filter <field-or-operator> --data-dir $data
conda run -n codex_env python $script --incident stuck-pipe --filter <field-or-operator> --data-dir $data
conda run -n codex_env python $script --describe-table <table> --data-dir $data
conda run -n codex_env python $script --rank-table <table> --rank-by <alias-or-column> --limit 10 --data-dir $data
conda run -n codex_env python $script --api <api> --full --format json --output <file.json> --data-dir $data
```

Useful flags: `--rank-direction asc`, `--min-step <ft>`, `--completion-reconcile`, `--casing-compare`, `--production-group-by interval|completion|product`, `--decom-cost-case p50|p70|p90|dtr`, `--decom-min-cost <amount>`, `--decom-pa-adjustment Y|N`.

## Aliases

- `wellpath_metrics`: `horizontal_departure`, `horizontal_distance`, `source_horizontal_departure`, `lateral_length`, `max_dls`, `avg_dls`, `trajectory_type`, `closure_azimuth`, `max_inclination`.
- `boreholes`: `total_depth`, `measured_depth`, `tvd`, `water_depth`.
- `production`: `production_oil`, `oil_volume`, `production_gas`, `gas_volume`, `production_water`, `water_volume`, `days_on_prod`.
- `decom_spud_well` / `decom_totals`: `decom_cost`, `p50_cost`, `p70_cost`, `p90_cost`.
- `lease_owner`, `lease_owner_designated_operator`, `lease_owner_remarks`: `assignment_pct`, `ownership_pct`, `owner_percent`, `interest_pct`.
- `lease_data`: `royalty_rate`, `current_area`.

## Guardrails

- For ranking questions: rank first, then run a dossier on the top API before making a strong claim.
- For lease buyer/seller questions: BSEE assignment rows show current/terminated owners, not explicit legal buyer/seller pairs.
- Keep APD planned casing separate from WAR actual casing/tubular evidence.
- Do not treat production `Completion Name` and EOR completion identifiers as identical.
- Use `decom_totals` for lease/category totals, not single-well ranking.

## References

Load only when needed:

- `references/trajectory.md`: trajectory, DLS, map coordinate, and wellpath metric rules.
- `references/casing.md`: casing search and APD/WAR comparison rules.
- `references/decommissioning.md`: decommissioning cost/inventory workflows.
- `references/lease.md`: lease/block ownership, current owner, and assignment-history interpretation.
- `references/output-rules.md`: dossier sections, answer format, JSON/HTML handoff rules.
