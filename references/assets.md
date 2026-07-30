# Platform and Pipeline Rules

Use for non-map platform and pipeline attributes, history, relationships, and approvals.

## Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo platforms search --status active --company "<operator>"
conda run -n cxstreamlit python $script --repo $repo platforms detail <complex-id> <structure-number>
conda run -n cxstreamlit python $script --repo $repo pipelines search --status <code> --product <code> --company "<operator>"
conda run -n cxstreamlit python $script --repo $repo pipelines detail <segment-number> --history-page 1 --history-page-size 25
```

Platform detail may include structure attributes, approvals, and removal history. Pipeline detail may include the latest segment attributes, permit history, submittals, endpoint connections, matched platform records, and approvals.

Preserve exact complex/structure and segment identifiers. Keep status/product/company filters explicit. Treat missing enrichment datasets as partial coverage.
Approval identifiers use published forms such as `complex:<complex-id>` for a platform complex and usually the bare segment number for a pipeline. Keep complex-level approval links separate from structure-specific matches.

If a source attribute status and the latest permit status differ, report both with their source context; do not silently choose one.

Do not return geometry, coordinates, GeoJSON, endpoint shapes, bathymetry, or continental-shelf data.
