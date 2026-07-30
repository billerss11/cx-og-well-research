---
name: cx-og-well-research
description: Research Gulf of Mexico wells, regulatory evidence, fields, leases, production, approvals, platforms, pipelines, casing, decommissioning, and local CX O&G Parquet datasets. Use for exact or fuzzy discovery, incident evidence, full well dossiers, asset details, comparisons, audits, rankings, and source-backed explanations.
---

# CX O&G Research

Use the standalone CLI. Do not import the application backend or require its server.

```powershell
$script = "C:\Users\17999\.codex\skills\cx-og-well-research\scripts\cx_og_research.py"
$repo = "J:\cx_coding_project_unsyc\python\CX_O-G_APP"
conda run -n cxstreamlit python $script --repo $repo doctor
```

Put global options before the command: `--repo`, `--data-dir`, `--format json|markdown`, `--output`, and `--sample-limit`. JSON is the default.

## Route

- Unknown well, field, operator, or API: `wells search`.
- Incident or phrase evidence: `evidence search`; inspect one result with `evidence detail`.
- Known API: `well dossier`; use `--sections` only when the full dossier is unnecessary.
- Field/lease research: `fields list|compare|leases`.
- Production comparison: `production compare`.
- Regulatory approvals: `approvals search|options`.
- Platform or pipeline research: `platforms search|detail` or `pipelines search|detail`.
- Multi-well evidence inventory: `bulk files|war`.
- Casing-size discovery: `casing search`.
- Decommissioning inventory/cost: `decommissioning search`.
- Dataset inspection/ranking: `tables list|describe|rank`.

## Common Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo wells search "MADISON"
conda run -n cxstreamlit python $script --repo $repo wells search "MADSN" --match-mode fuzzy --threshold 75
conda run -n cxstreamlit python $script --repo $repo evidence search --incident stuck-pipe
conda run -n cxstreamlit python $script --repo $repo evidence detail <api> --incident stuck-pipe
conda run -n cxstreamlit python $script --repo $repo well dossier <api>
conda run -n cxstreamlit python $script --repo $repo --sample-limit 5 well dossier <api> --sections relationships,ownership,production,timeline
conda run -n cxstreamlit python $script --repo $repo production compare <api-1> <api-2> --group-by well
conda run -n cxstreamlit python $script --repo $repo approvals search --asset-type well --asset-identifier <api>
conda run -n cxstreamlit python $script --repo $repo platforms search --company "<operator>"
conda run -n cxstreamlit python $script --repo $repo pipelines search --status <code> --product <code>
conda run -n cxstreamlit python $script --repo $repo casing search "13.375,9.625" --source war
conda run -n cxstreamlit python $script --repo $repo decommissioning search --lease <lease> --cost-case p90
conda run -n cxstreamlit python $script --repo $repo tables describe production
conda run -n cxstreamlit python $script --repo $repo tables rank production oil_volume
```

Empty searches are valid. Treat warnings and `coverage` as part of the answer; a missing optional dataset means partial coverage, not zero records.
`--sample-limit` bounds dossier and representative samples. Use `--page-size` to bound paginated search/detail rows.

## Guardrails

- Confirm fuzzy matches with exact API or asset identifiers before making a strong claim.
- Keep planned APD casing separate from actual WAR casing/tubular evidence.
- Do not equate production completion names with EOR completion identifiers.
- Do not label lease assignment parties as buyers or sellers without separate evidence.
- Distinguish exact regulatory asset links from unresolved or grouped links.
- Return document metadata and resolved local paths only. Do not copy or open files automatically.
- Do not produce geometry, coordinates, GeoJSON, bathymetry, continental-shelf, or other map output.

## References

Load only the relevant file:

- `references/regulatory.md`: applications, timelines, documents, approvals, and link confidence.
- `references/assets.md`: platform and pipeline search/detail rules.
- `references/casing.md`: casing search and APD/WAR interpretation.
- `references/lease.md`: ownership and assignment-history interpretation.
- `references/trajectory.md`: trajectory and DLS rules without map output.
- `references/decommissioning.md`: decommissioning cost and inventory rules.
- `references/dataset-contract.md`: catalog, coverage, units, identifiers, and ranking.
- `references/output-rules.md`: canonical envelope, bounded output, and answer format.
