# Casing Rules

Use for APD planned casing, WAR actual casing/tubular records, and global casing searches.

Core rule: keep planned APD casing separate from actual WAR casing/tubular evidence. Do not merge them into one "actual casing" claim.

## Commands

- Global search: `conda run -n codex_env python $script --casing-sizes "13.375,9.625" --data-dir $data`
- WAR-only filtered search: `... --casing-source war --filter MADISON`
- API comparison: `... --api <api> --casing-compare --data-dir $data`

Options: `--casing-source any|apd|war`, `--casing-match all|any`, `--casing-tolerance`, `--casing-latest-only`, `--filter`.

Report requested sizes/tolerance, source used, APD/WAR distinction, wells matched, and representative casing depths with units.
