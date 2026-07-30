# Lease and Ownership Rules

Use for surface/bottom lease interpretation, current ownership, designated operators, and assignment history.

## Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo well dossier <api> --sections relationships,ownership
conda run -n cxstreamlit python $script --repo $repo fields leases <field-code-or-name>
conda run -n cxstreamlit python $script --repo $repo tables describe lease_owner
conda run -n cxstreamlit python $script --repo $repo tables rank lease_owner assignment_pct
```

## Sources

- Boreholes identify surface and bottom lease, area, and block.
- Lease data supplies status, effective/expiration dates, royalty, and production context.
- Designated-operator rows identify current owner percentages when status is current.
- Lease-owner and remark rows provide assignment history and aliquot/interest detail.
- Company data resolves company numbers and names.

## Interpretation

- State whether a lease is a surface or bottom relationship.
- Use current-owner rows for current interests and assignment history for earlier/current records.
- Compare percentages within owner groups; do not blindly sum across parallel groups.
- A terminated owner is not proven to be a seller, and a current owner is not proven to be a buyer.
- Treat missing ownership datasets as partial coverage, not no owners.
