# Regulatory Evidence

Commands: `evidence search <phrase>`; `evidence detail <api> --incident stuck-pipe`; `well dossier <api> --sections timeline,applications,permits,documents,approvals`; `approvals options`; `approvals search --asset-type well --asset-identifier <api>`.

For timeline research, run `well timeline <api>` first and pass the chosen `event_id` to `well timeline-detail <api> <event-id>`. Detail output contains the exact event, its narrative, and source-specific linked sections such as APD/APM questions and responses, procedural narratives, verbal communications, resubmittals, casing, WAR text, EOR records, approvals, and attachments when available.

- Keep APD and APM separate; preserve IDs, dates, status, operator, and document counts.
- Call approval links exact only when normalized asset type/ID match; preserve grouped, name-based, or unresolved labels.
- Documents are metadata. Return local paths when present; do not open/copy/read content without a separate request.
- Missing optional event/attachment data means partial coverage, not no activity.
- Incident presets are broad. Say “evidence” until individual WAR text confirms the event.
- Use `--page-size` for pages; `--sample-limit` for dossier samples.
