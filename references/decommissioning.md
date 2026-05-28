# Decommissioning Workflows

Use for decommissioning cost and inventory questions.

Common commands:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --decom-lease G34454 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --decom-api 177174027700 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --decom --decom-area GC --decom-block 100 --decom-min-cost 1000000 --decom-cost-case p90 --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Options: `--decom`, `--decom-lease`, `--decom-api`, `--decom-area`, `--decom-block`, `--decom-min-cost`, `--decom-cost-case p50|p70|p90|dtr`, `--decom-pa-adjustment Y|N`.

For unclear ranking columns, run `--describe-table decom_spud_well` or `--describe-table decom_totals`. Common aliases: `decom_cost`, `p50_cost`, `p70_cost`, `p90_cost`.

Report filters, cost case, units, section row counts, sum/max costs, and whether rows came from lease estimates, installed wells, proposed wells, or totals.
