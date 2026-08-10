# Decommissioning

Commands: `decommissioning search --api <api>|--lease <lease>|--area <area> --block <block>`; `decommissioning authorities --query <number> --type LSE|ROW|RUE`; `decommissioning authority <type> <number>`; `decommissioning well <api>`; `decommissioning pipeline <segment>`; `decommissioning platform <complex> <structure>`.

Search options: `--min-cost`, `--cost-case p50|p70|p90|dtr`, `--pa-adjustment Y|N`. Use `tables describe decom_spud_well|decom_totals` for columns; ranking aliases include `decom_cost`, `p50_cost`, `p70_cost`, `p90_cost`.

Report filters, scenario, USD units, counts, sum/max, installed/proposed status, and source level. Never present lease/category totals as one asset’s estimate. `authorities` discovers LSE/ROW/RUE; `authority` returns inventory/cost/assets; asset commands return exact estimates. Use `pipelines detail`, not decommissioning data, for cathodic protection/MAOP.
