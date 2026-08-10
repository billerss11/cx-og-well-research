# Casing

Commands: `casing search <sizes> [--source any|apd|war] [--match all|any] [--tolerance N] [--filter text] [--latest-only]`; `well casing <api>`; `well casing-versions <api>`; `well casing-analysis <api> --source apd|war --version N --units feet|meters`; `well dossier <api> --sections casing,apd_casing,war_casing,casing_comparison`.

APD is planned; WAR/tubular is reported actual. Never merge their claims. Report requested sizes/tolerance, source, match mode, API count, representative depths, and units.

Comparison uses latest APD and WAR snapshots. Older WARs may contain strings absent from the latest; use full `war_casing` for all reported installed strings.
