# Regulatory Evidence Rules

Use for APD/APM applications, timeline events, documents, approvals, API changes, directional surveys, and well-potential tests.

## Commands

```powershell
conda run -n cxstreamlit python $script --repo $repo well dossier <api> --sections timeline,applications,permits,documents,approvals
conda run -n cxstreamlit python $script --repo $repo approvals options
conda run -n cxstreamlit python $script --repo $repo approvals search --asset-type well --asset-identifier <api>
conda run -n cxstreamlit python $script --repo $repo evidence search "<phrase>"
conda run -n cxstreamlit python $script --repo $repo evidence detail <api> --incident stuck-pipe
```

Treat APD and APM as separate source families. Preserve application IDs, source dates, status, operator, and document counts.

Approval links are exact only when the normalized asset type and identifier match. Grouped, name-based, or unresolved links must remain labeled as such.

Documents are metadata records. Report resolved local paths when present, but do not copy, open, or summarize document contents unless the user separately requests file reading.

Missing optional event or attachment datasets mean partial timeline/document coverage, not no activity.

Incident presets are intentionally broad evidence terms. Describe results conservatively (for example, “stuck/fishing evidence”) until the individual WAR text confirms the incident. Use `--page-size` for search/detail pagination; `--sample-limit` controls dossier and representative samples.
