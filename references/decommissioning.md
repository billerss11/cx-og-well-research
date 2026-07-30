# Decommissioning Rules

Use for decommissioning inventories and cost research.

## Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo decommissioning search --api <api>
conda run -n cxstreamlit python $script --repo $repo decommissioning search --lease <lease>
conda run -n cxstreamlit python $script --repo $repo decommissioning search --area <area> --block <block> --min-cost <amount> --cost-case p90
```

Options: `--lease`, `--api`, `--area`, `--block`, `--min-cost`, `--cost-case p50|p70|p90|dtr`, and `--pa-adjustment Y|N`.

Use `tables describe decom_spud_well` or `tables describe decom_totals` when cost columns are unclear. Ranking aliases include `decom_cost`, `p50_cost`, `p70_cost`, and `p90_cost`.

Report filters, cost case, currency/units, record counts, sum/max costs, and whether evidence comes from lease estimates, installed/proposed wells, platforms, pipelines, or totals. Do not present lease/category totals as single-well estimates.
