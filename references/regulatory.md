# Regulatory Evidence

Commands: `evidence search <phrase>`; `evidence detail <api> --incident stuck-pipe`; `well dossier <api> --sections timeline,applications,permits,documents,approvals`; `approvals options`; `approvals search --asset-type well --asset-identifier <api>`.

- Keep APD and APM separate; preserve IDs, dates, status, operator, and document counts.
- Call approval links exact only when normalized asset type/ID match; preserve grouped, name-based, or unresolved labels.
- Documents are metadata. Return local paths when present; do not open/copy/read content without a separate request.
- Missing optional event/attachment data means partial coverage, not no activity.
- Incident presets are broad. Say “evidence” until individual WAR text confirms the event.
- Use `--page-size` for pages; `--sample-limit` for dossier samples.
