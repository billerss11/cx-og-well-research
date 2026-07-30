# Output Rules

Every successful JSON result contains:

- `schema_version`
- `command`
- `query`
- `data`
- `provenance`
- `coverage`
- `warnings`

Use `--sample-limit` to bound dossier and representative rows. It does not replace pagination: use `--page-size` for search/detail rows and the command-specific history page size for history. Empty search results are successful.

Exit codes:

- `0`: success, including an empty search
- `2`: invalid input
- `3`: required data unavailable
- `1`: unexpected failure

## Answer Rules

- Start with the result and important coverage limits.
- Preserve source identifiers, dates, units, counts, ordering, and warnings.
- Say “no matching records” only when required data was available.
- Say “coverage is partial” when optional data is missing.
- Confirm fuzzy matches with exact identifiers.
- Keep APD planned casing and WAR actual casing separate.
- Keep production and EOR completion identifiers separate.
- Do not infer legal buyers/sellers from assignment status.
- Distinguish exact regulatory asset links from unresolved links.
- List document metadata and resolved local paths only; never copy or open documents automatically.
- Do not include map fields or map-oriented datasets.

For a durable handoff, place global output flags before the command:

```powershell
conda run -n cxstreamlit python $script --repo $repo --format json --output <result.json> <group> <command> ...
```
