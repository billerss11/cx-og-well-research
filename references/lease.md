# Lease Rules

Use for lease/block/current-owner, ownership percentage, and assignment-history questions.

## Sources

- `df_boreholes`: surface/bottom lease, area, block for the API.
- `df_lease_data`: lease status, dates, area, royalty.
- `df_lease_owner_designated_operator`: current owner %, designated operator; current rows use `ASGN_STATUS_CODE = C`.
- `df_lease_owner`: assignment history; `C = Current`, `T = Terminated`.
- `df_lease_owner_remarks`: assignment %, aliquot code/description/area; no current/terminated status.
- `df_company_all`: company names.

## Commands

- Dossier: `conda run -n codex_env python $script --api <api> --data-dir $data`
- Describe detail table: `... --describe-table lease_owner_remarks --data-dir $data`
- Rank by interest: `... --rank-table lease_owner_remarks --rank-by assignment_pct --limit 10 --data-dir $data`

## Interpretation

- Report `lease_summary` for lease role, lease number, area, block.
- Report `current_owners` for current owner %, company, and designated operator.
- Use `ownership_detail` for aliquot/interest detail.
- Use `assignment_history` for current/prior terminated owners.
- Do not call a terminated owner a seller, or a current owner a buyer, unless separate evidence proves the transaction.
