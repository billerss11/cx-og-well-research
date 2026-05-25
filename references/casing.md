# Casing Rules

Use this reference for APD planned casing, WAR actual casing/tubular records, and global casing searches.

## Core Rule

Keep planned APD casing separate from actual WAR casing/tubular evidence. Do not merge them into one "actual casing" claim.

## Commands

Global casing search:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --casing-sizes "13.375,9.625" --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

WAR-only search filtered to field/operator/name:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --casing-sizes "13.375,9.625" --casing-source war --filter MADISON --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

API dossier with comparison:

```powershell
conda run -n codex_env python C:\Users\17999\.codex\skills\cx-og-well-research\scripts\build_well_research.py --api 608054000500 --casing-compare --data-dir J:\cx_coding_project_unsyc\python\CX_O-G_APP\data
```

## Options

- `--casing-source any|apd|war`: choose planned APD, actual WAR, or either.
- `--casing-match all|any`: require every requested size or any requested size.
- `--casing-tolerance`: numeric tolerance in inches.
- `--casing-latest-only`: search only latest APD/WAR casing version per well.
- `--filter`: restrict by field/operator/well text.

## Answer Checks

Report:

- requested sizes and tolerance
- casing source used
- APD versus WAR distinction
- number of wells matched
- representative casing records with depths and units

