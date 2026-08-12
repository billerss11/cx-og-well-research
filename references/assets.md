# Platforms and Pipelines

Commands: `platforms search [filters]`; `platforms detail <complex> <structure>`; `pipelines search [--status code] [--product code] [--company text]`; `pipelines detail <segment> --history-page N --history-page-size N`.

Platform detail covers attributes, approvals, removal history. Pipeline detail covers latest permit, permit/submittal history, endpoint connections, matched platforms, and approvals.

For engineering/regulatory questions inspect `segment` and `permit_history.rows`. Preserve `cathodic_code`, MAOP, water depth, ROW/authority/bidirectional codes, lifecycle dates, endpoints, status, size, product, and operator. Cathodic code is raw: null = “not reported”; never infer/decode without an authoritative source.

Preserve exact complex/structure/segment IDs. Keep complex-level approvals separate from structure matches. If source and latest-permit statuses differ, report both with provenance. Missing enrichment means partial coverage. Keep asset queries attribute-only; exclude geometry, rendered maps, and map-only coordinate fields.
