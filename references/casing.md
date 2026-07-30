# Casing Rules

Use for global casing-size searches and API-level casing reconciliation.

## Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo casing search "13.375,9.625"
conda run -n cxstreamlit python $script --repo $repo casing search "9.625" --source war --filter MADISON
conda run -n cxstreamlit python $script --repo $repo well dossier <api> --sections casing,apd_casing,war_casing,casing_comparison
```

Options: `--source any|apd|war`, `--match all|any`, `--tolerance`, `--filter`, and `--latest-only`.

APD casing is planned. WAR casing/tubular data is reported actual work. Keep both source families separate even when size and depth appear to reconcile.

Report requested sizes and tolerance, source family, match mode, well/API count, representative depths, and units.

The casing comparison uses the latest APD submission and latest WAR report as snapshots. Older WAR reports can contain additional strings absent from the latest report; use the full `war_casing` section when researching all installed strings.
