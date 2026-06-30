# Decommissioning Rules

Use for decommissioning cost and inventory questions.

## Commands

- Lease: `conda run -n codex_env python $script --decom-lease <lease> --data-dir $data`
- API: `... --decom-api <api> --data-dir $data`
- Area/block/cost: `... --decom --decom-area <area> --decom-block <block> --decom-min-cost <amount> --decom-cost-case p90`

Options: `--decom`, `--decom-lease`, `--decom-api`, `--decom-area`, `--decom-block`, `--decom-min-cost`, `--decom-cost-case p50|p70|p90|dtr`, `--decom-pa-adjustment Y|N`.

Use `--describe-table decom_spud_well` or `--describe-table decom_totals` when ranking columns are unclear. Aliases: `decom_cost`, `p50_cost`, `p70_cost`, `p90_cost`.

Report filters, cost case, units, row counts, sum/max costs, and whether rows came from lease estimates, installed wells, proposed wells, or totals.
