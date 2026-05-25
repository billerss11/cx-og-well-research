# Decommissioning Workflows

Use this reference for decommissioning cost and inventory questions.

## Commands

By lease:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --decom-lease G34454 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

By API well:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --decom-api 177174027700 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Ranking/filter:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --decom --decom-area GC --decom-block 100 --decom-min-cost 1000000 --decom-cost-case p90 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

## Options

- `--decom`: search decommissioning cost and inventory tables.
- `--decom-lease`: lease/auth number, for example `G34454`.
- `--decom-api`: API well number.
- `--decom-area`: area code.
- `--decom-block`: block number.
- `--decom-min-cost`: minimum cost filter.
- `--decom-cost-case p50|p70|p90|dtr`: cost case used for filtering and ranking.
- `--decom-pa-adjustment Y|N`: filter lease estimate rows by PA adjustment flag.

## Metric Aliases

Use `--describe-table decom_spud_well` or `--describe-table decom_totals` before ranking if column names are unclear.

Common aliases:

- `decom_cost`
- `p50_cost`
- `p70_cost`
- `p90_cost`

## Answer Checks

Report:

- filters used
- cost case used
- cost units
- row counts by section
- sum/max cost where available
- whether results came from lease estimates, installed wells, proposed wells, or totals

