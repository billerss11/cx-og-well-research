# Dataset Contract Rules

Use `doctor` before broad research when the data directory is uncertain. Use `tables list` for catalog availability, `tables describe` for columns/units/aliases, and `tables rank` for reproducible rankings.

The catalog records each Parquet source’s key, filename, family, required status, expected columns, identifier role, units, and aliases where defined.

## Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo doctor
conda run -n cxstreamlit python $script --repo $repo tables list
conda run -n cxstreamlit python $script --repo $repo tables describe <table>
conda run -n cxstreamlit python $script --repo $repo tables rank <table> <alias-or-column> --direction desc
```

Required data missing or invalid makes the command unavailable. Optional data missing produces partial `coverage` and a warning.

When ranking, report the requested alias, resolved source column, direction, units, row count, and sampled ranked records. Rank first, then inspect the leading API or asset before making a strong claim.

Map-oriented datasets and fields are outside this skill’s contract.
