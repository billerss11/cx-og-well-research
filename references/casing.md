# Casing Rules

Use for APD planned casing, WAR actual casing/tubular records, and global casing searches.

Core rule: keep planned APD casing separate from actual WAR casing/tubular evidence. Do not merge them into one "actual casing" claim.

Common commands:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --casing-sizes "13.375,9.625" --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --casing-sizes "13.375,9.625" --casing-source war --filter MADISON --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --casing-compare --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

Options: `--casing-source any|apd|war`, `--casing-match all|any`, `--casing-tolerance`, `--casing-latest-only`, `--filter`.

Report requested sizes/tolerance, source used, APD/WAR distinction, wells matched, and representative casing depths with units.
