# Vue Query Parity

The skill bundles query code and reads published files directly: no `backend` import, FastAPI client/server, or Vue runtime.

## Coverage

- Discovery/evidence: `wells search|suggestions|filter-options`; `evidence search|detail`.
- Well: `well identity|summary|availability|relationships|ownership|lease-activity|production|trajectory|trajectory-analysis|wellbore|casing|casing-versions|casing-analysis|war|war-record|permits|files|applications|documents|timeline|timeline-detail|raw`.
- Bulk/comparison: `well batch`; `bulk files|war`; `production compare`.
- Fields: `fields list|wells|compare|trajectory-comparison|leases|lease-context`.
- Assets/regulatory: `pipelines search|detail`; `platforms search|detail`; `approvals search|options`.
- Decommissioning: `decommissioning search|authorities|authority|well|pipeline|platform`.

Special forms: `fields trajectory-comparison <fields...> --api <api> [--api <api>...]`; `production compare <apis...> --group-by well|completion|product|interval`; `well casing-analysis <api> --source apd|war --version N --units feet|meters`; authority types `LSE|ROW|RUE`.

For cathodic protection use `pipelines detail <segment>`; inspect `data.segment` and `data.permit_history.rows`; null means not reported.

Scalar latitude/longitude fields are included in well search, summary, field-well, raw-table, and dossier results. Excluded: Vue/HTTP presentation, rendered maps, geometry, GeoJSON, bathymetry/marine layers, map-only coordinate systems, browser interactions, export buttons, and semantic/vector WAR search. Use JSON `--output` for export and `evidence search` for exact/fuzzy text.
