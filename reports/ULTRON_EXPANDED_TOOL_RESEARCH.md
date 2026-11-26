# Ultron: expanded tool research and product roadmap

Research synthesis: 2026-11-23. Repository baseline: `6aaf198508c405138a30759c478e18be652e684b`.

## Executive recommendation

Ultron needs a smaller number of dependable capabilities, not dozens of overlapping action modules. This second research pass identifies **36 capability opportunities: 9 new tools, 9 integrations, 10 extensions, 6 workflows and 2 infrastructure capabilities**. These are product boundaries, not a recommendation to add 36 handlers.

The accompanying `ULTRON_TOOL_OPPORTUNITIES.csv` records every candidate, example intent, deployment, risk, rough effort and release constraint. The earlier `ASSISTANCE_TOOLS_RESEARCH_AUDIT.md` and 53-tool inventory remain the source for existing-code findings. This report adds opportunities and provider constraints; it does not replace the audit.

**Build first:** a reliable local task board, deterministic calculator, evidence-backed document comparison, safe-sharing preview, and the shared permission/job foundation. Then introduce a scoped Google integration: selected Drive documents and Calendar reads, followed by explicitly approved writes. Add contacts resolution before sending to inferred recipients.

**Best additions beyond the earlier shortlist:** personal document vault; receipt/expense ledger; renewal/warranty workflows; Zotero citation library; study-card pipeline; accessible desktop navigation; backup restore verification; sync diagnostics; GitHub issue triage; local transcription; source-linked evidence ledger.

Research only: no runtime features implemented, accounts connected, account content read, external messages sent, or commits made for this pass. No independent-agent runner was available: research used parallel source-investigation tracks, not a claimed autonomous swarm. Provider documentation was inspected, not live authenticated integrations tested. Some fetched pages expose dates after the session date; treat those version-specific details as requiring revalidation against a pinned release before implementation.

## 1. Method, evidence and ranking

Candidates were deduplicated against the existing inventory and the earlier eight proposals: task board, calendar assistant, document comparison, calculator, backup/restore, inbox assistant, notification center and workflow recipes. Repeated proposals below are extensions/refinements, not newly discovered tools.

Primary evidence includes official Google API references, Paperless-ngx, restic, Syncthing, Zotero, OpenAlex, Microsoft UI Automation, AnkiConnect, GitHub REST, openrouteservice, Tesseract and faster-whisper. Sources support provider capabilities and constraints; priorities, effort bands, proposed APIs and safety requirements are engineering recommendations, not provider guarantees.

Ranking is qualitative rather than an invented precise score:

- **A:** high-frequency value or a dependency that makes other features trustworthy.
- **B:** strong value after shared foundations and optional service setup.
- **C:** usage-dependent or operationally expensive; validate demand first.
- Effort: **S** narrow deterministic adapter; **M** persistent feature with tests/UI; **L** cross-cutting security, sync, platform or recovery work. These are relative complexity bands, not delivery promises. Optional adapters should not become mandatory installation dependencies.
- “Local” assumes a local execution path and installed assets. A local interface calling a cloud model is **not** an offline/private path. “Hybrid” needs explicit cache freshness and offline limitations.

## 2. Prioritized opportunity map

| Area | Candidate IDs | Product outcome | Reuse / avoid duplication |
|---|---|---|---|
| Personal organization | O03–O09, O33 | Calendar, tasks, realistic day plans, meeting briefs, follow-ups | Existing `reminder`/`quick_timer` handle alerts; tasks and calendar are separate domain models |
| Documents and administration | O02, O10–O14, O23 | Authorized document retrieval, version diffs, receipts, renewals, calculations, safe sharing | Extend `file_search`, `file_processor`, `workspace_recall`; do not build a competing file manager |
| Research and learning | O15–O20, O36 | Citations, claim provenance, literature watch, cards, reading queue, terminology | Extend `web_search`/`web_autopilot`; repair `drone_swarm` before adding autonomy |
| Accessible interaction | O21–O22 | Named-control desktop navigation and local transcription | Extend `computer_control`, `screen_processor`, `meeting_scribe`; avoid another blind-click wrapper |
| Reliability and developer work | O24–O29 | Restore verification, sync status, duplicate review, diagnostics, issue triage, release watch | Reuse file safety, monitor jobs, `git_sentinel`, `cloud_watchtower` |
| Household and mobility | O30–O32 | Errand routes, lists, household inventory | Extend `flight_finder`/weather where relevant, without claiming flight tools solve street routing |
| Shared platform | O01, O34–O35 | Account permissions, controlled alerts, approved recipes | Host policy, bounded jobs, durable events and observability belong in core, not each tool |

### Recommended first release boundary

A coherent first release should include only:

1. Host-enforced capability grants and structured results; repair the four audited dispatch mismatches.
2. Local task board, calculator and document comparison.
3. Google account settings with per-service consent and disconnect, then selected-file Drive retrieval and Calendar reads.
4. A minimal evidence ledger and safe-sharing preview.
5. One notification queue with quiet hours, deduplication and channel approval.

Calendar writes, inbox access, Paperless integration and restore operations should be independent later gates, not hidden expansions of this release.

## 3. Google Workspace: useful, but permissions define the feature

### O01 — Account hub (infrastructure, A)

**Intent:** “Connect my Google account, show exactly what Ultron may access, and disconnect it.”

Use the desktop OAuth flow, external browser, PKCE and state validation; inspect granted scopes rather than assuming every requested permission was accepted. Store tokens in the operating-system credential store, not source, chat history, reports or `.env` committed to Git. Installed-app credentials must not be treated as a confidential client secret. Follow the documented desktop redirect flow. [G1]

Settings should display account identity, enabled adapters, granted scopes, last successful sync, cache retention, outbound-model policy and revoke/disconnect. Revocation and local-cache removal are separate operations and should be described separately. Do not silently fall back to plaintext token storage when a credential backend is unavailable.

A connection available to Arena is not an OAuth installation inside the user's local Ultron app. Account discovery is not permission to inspect content. Personal, testing, internal and public distribution modes have different policy implications; recheck Google's current publishing rules rather than promising production verification is unnecessary.

**Acceptance:** partial consent, denial, revoked refresh token, offline startup, wrong account, concurrent refresh, logout and credential-store failure are explicit tested states.

### O02 — Drive document assistant (integration, A)

**Intent:** “Summarize this selected proposal and tell me which page supports the budget.”

Start with files explicitly selected or opened through an authorized flow. Google's `drive.file` is a narrower, non-sensitive per-file scope, but it is **write-capable**, not read-only; it does not mean whole-Drive discovery. Broad `drive.readonly` is restricted. Account-wide search must not be promised as a consequence of selected-file access. [G2]

Ultron should still expose a read-only adapter first. Every extracted chunk should carry file ID, revision/version where available, extraction time and page/section. Respect source ACLs in caches and retrieval; a vector index must not make revoked documents available forever. Sharing links, exports and model uploads require separate destination grants. Preview actual affected files for mutations.

**Acceptance:** inaccessible file, permission revoked after caching, duplicate title, changed revision, unsupported export, oversized file, malicious embedded instructions and stale offline copy.

### O03 / O05 — Calendar and day planning (integration A; workflow B)

**Intents:** “What is tomorrow's agenda?”; “Suggest a free 45-minute slot”; “Draft focus time around my meetings.”

Availability-only planning can use Google's free/busy endpoint rather than full event descriptions; narrower free/busy scopes are supported. Errors for a calendar must be shown as unknown availability, never interpreted as free time. [G3]

Incremental event sync requires a completed initial sync, pagination and persisted `nextSyncToken`. Deletions matter. HTTP 410 means invalidate/rebuild the synchronized cache with a new full sync, not delete the user's calendar. [G4]

Use explicit IANA timezones; do not infer the desired calendar zone from a machine's UTC default. Distinguish all-day dates, recurring series, one occurrence, exceptions and ambiguous daylight-saving times. Draft by default. Creation/update approval must show calendar, local time, timezone, attendees, conferencing and recurrence impact. Re-read state before applying stale proposals.

Offline MVP: cached agenda marked with sync time and local `.ics` export, not a false claim of live synchronization. iCalendar is a standard interchange format, not itself a synchronization protocol. [G5]

### O04 / O09 — Task board and commitments (new tool A; workflow B)

A task needs an ID, status, source, due-date semantics, optional reminder instant, dependencies and completion evidence. Keep this separate from transient timers and meeting events.

Google Tasks can be an optional adapter. Critically, its `due` field retains the **date only** and discards time; the API does not expose the scheduled time. A promise such as “remind me at 14:30” must use Ultron's reminder system or another suitable calendar/reminder representation, not claim the Tasks field preserves it. [G6]

Follow-up extraction should produce suggestions with quoted message/transcript evidence. “We should discuss this” is not automatically a promise; user review establishes ownership and deadlines. Marking a task completed is an effect, not an inference from positive language.

### O07 / O08 — Inbox and recipient identity (integration B / A)

Start with user-selected messages or narrowly requested retrieval. Build reply drafts locally when possible. `gmail.compose` permits managing drafts **and sending**; OAuth does not provide a draft-only guarantee through that scope. `gmail.readonly` and `gmail.compose` are restricted; `gmail.send` is sensitive. Account verification and security obligations depend on scope and deployment. [G7]

A real draft-only mode must deny send methods in the host adapter and avoid alternate browser/system-command sending paths. A send approval binds exact recipients, subject, content, attachments and account. Changed content invalidates approval. Timeout after submission is an unknown-delivery state until reconciled, not grounds for an automatic duplicate send.

Contact resolution is useful independently: maintain explicit aliases locally, optionally add a provider address-book adapter after validating its endpoint scopes. Return candidate identities and masked addresses; never choose the first fuzzy “Ahmed” match. Calendar attendee discovery must not automatically grant access to an attendee's documents or messages.

## 4. Documents and personal administration

### O10 — Document comparison (new tool, A; previously proposed)

Return deterministic text/table changes with source locations, plus an optional narrative explanation. Distinguish extraction/layout differences from semantic changes. A summary cannot substitute for a diff. Preserve both originals and cite changed sections. Contract comparisons should not be represented as legal advice or exhaustive risk review.

**MVP:** text, Markdown, CSV and successfully extracted PDF text; explicit unsupported state for image-only or encrypted inputs until an OCR/decryption path is deliberately added. Test moved paragraphs, Unicode, repeated headings, changed numbers and deleted clauses.

### O11 — Personal document vault (integration, B)

**Intent:** “Find the receipt and warranty for my laptop.”

A local index may be enough for a small collection; Paperless-ngx is a stronger optional self-hosted archive. Its API exposes document search and metadata. Document ingestion is asynchronous: `post_document` returns a task UUID, not a completed searchable document. Poll the task and reconcile the resulting document ID before reporting completion. [D1]

Keep provenance, checksums, classification suggestions and user-edited fields. Do not ingest the entire home directory by default. Credentials to a self-hosted service are still sensitive; ensure server identity and explicit base URL. Deleting an index entry must not silently delete the original document.

### O12 / O13 — Receipt ledger, renewals and warranties (new tool/workflow, B)

**Intents:** “Total the expenses in these receipts”; “Warn me before this contract renews.”

Start with selected receipt files or CSV imports, not bank credentials. Store currency, exact decimal amount, merchant, transaction date, source reference and user-reviewed status. Never silently combine currencies. Keep original OCR text and corrected fields distinct; deduplicate repeated imports by source identity/hash and transaction review.

Renewal extraction should quote the source clause and distinguish start date, expiry date, auto-renewal date and cancellation notice deadline. Ask before scheduling reminders. Cancellation itself remains a separate, approved external action.

Tesseract publishes Arabic, French and English language data, making a multilingual local OCR path worth evaluating. Language-pack availability does not prove accuracy for handwriting, mixed scripts, rotated scans or local receipt layouts. Use selected-language fixtures, especially decimal separators, dates and right-to-left text. [D2]

### O14 — Calculator and unit converter (new tool, A; previously proposed)

Use a restricted parser and deterministic numeric implementation, never Python `eval`. Use decimal arithmetic for money, explicit rounding and dimensional validation for units. Keep exchange-rate retrieval optional, timestamped and attributed; historical conversions need historical rates. No model should invent a live rate. Test locale input, percentages, compound units, overflow and ambiguous “billion”/date formats.

### O23 — Redaction and safe-sharing preview (new tool, A)

**Intent:** “Prepare a copy of this document without addresses and account numbers.”

Two separate functions: detect candidate sensitive data, and actually remove selected material from an output copy. Detection is fallible; user preview is mandatory. Drawing a black rectangle is not sufficient PDF redaction. Check extracted text, embedded objects, comments, metadata, hidden sheets/layers and thumbnails as applicable to the format. Begin with formats for which true removal and verification can be implemented; reject unsupported formats rather than claim universal sanitization.

**Acceptance:** originals untouched, output reopenable, selected text absent from re-extraction, metadata policy applied, explicit residual risks. Never promise perfect anonymization or compliance certification. Upload/share remains a separate action after preview.

## 5. Research, learning and reading

### O15 — Citation library (integration, B)

**Intent:** “Save these sources and create a bibliography I can verify.”

Zotero provides a versioned Web API with different public/private access requirements, and a local desktop API. Local reads offer an attractive path when the desktop library is available; local writes and authentication are version-dependent and must be separately verified. Pin the Web API version and installed desktop compatibility. [R1]

Store exact identifiers and provenance: DOI if present, title, authors, publication date, accessed URL, retrieval time, and whether full text was actually available. Do not fabricate a DOI, page range or quotation. Citation formatting and factual support are different checks. Dedupe by identifiers plus human review, not title alone.

### O16 — Evidence ledger (extension, A)

Extend research results with stable evidence IDs and claim-to-source links. Record `discovered`, `fetched`, `parsed`, `supports`, `contradicts`, `unverified` as distinct states. Preserve a bounded quote or section pointer and fetch timestamp; a search snippet should not be represented as reading an entire paper.

A critic checks whether the cited passage supports the claim and whether uncertainty was omitted. Two generated answers agreeing is not independent verification. This capability benefits ordinary single-query research before a swarm is useful.

### O17 — Literature discovery and topic watch (extension, C)

OpenAlex is suitable for structured paper discovery. Its current documentation distinguishes casual no-key queries from verified-key access needed for scale and cursor pagination. Do not reuse stale claims that all workloads are unlimited/no-key; configure quotas and recheck current terms before launch. [R2]

A topic watch needs saved query/version, last successful run, dedupe keys, relevance explanation and a bounded digest. Metadata availability does not grant access to paywalled full text. Corrections and retractions require source-aware handling; do not promise they are comprehensively covered without explicit validation.

### O18 — Study coach and Anki cards (integration, C)

Generate candidate cards from selected sources with evidence links; preview fronts/backs/tags, deduplicate, then import to a selected deck. Never auto-delete decks or alter scheduling en masse. AnkiConnect is a local integration candidate, but its published interface has version-specific legacy/new API distinctions. Pin a supported release, probe capabilities and contract-test methods rather than copying old snippets blindly. [R3]

Anki need not be installed for the first MVP: export a reviewable local card file using a documented target format, then add the live adapter later. No guarantee that generated cards are factually correct without review.

### O19 / O20 — Reading queue and terminology (new tool B; extension B)

A reading queue stores URL/source, title, saved timestamp, tags and progress; offline snapshots are opt-in, bounded and subject to access/retention rules. Reuse web-fetch safety rather than introduce a separate unrestricted downloader.

A translation extension should preserve numbers, citations and user glossary terms and show source/target languages. Local versus cloud translation is explicit. French/Arabic/English fixtures, right-to-left layout and dialect evaluation are useful opt-in targets; do not assume a location establishes language preference or Tunisian-dialect proficiency. No new translation provider has been selected or benchmarked in this research.

## 6. Accessible desktop work and local audio

### O21 — Accessible desktop navigator (extension, B)

**Intent:** “Read this dialog and focus the Save As filename field.”

Microsoft UI Automation exposes structured UI information and control interactions; it can be more robust than hard-coded coordinates, but coverage depends on app/framework support. It is not a cross-user privilege bridge. [A1]

Extend `computer_control` with an inspectable accessibility tree, stable element identity, window/process identity and explicit supported patterns. After a navigation event, verify the element still belongs to the intended window. A control name is not authority to send, delete, buy or elevate privileges. Password/protected fields should be excluded from logs and model context. Keep screenshot/OCR fallback explicit; measure success per application rather than claim all desktops are accessible. A Linux AT-SPI adapter needs its own source/compatibility investigation before a cross-platform claim.

### O22 — Local dictation and transcription (extension, B)

faster-whisper supports local Whisper-family inference with CPU/GPU precision options. Published upstream speed comparisons are workload-specific, not Ultron benchmarks. [A2]

Repair the existing meeting recorder's boundedness and evidence problems before adding richer summaries. Start with a user-selected audio file, installed model and explicit resource/duration caps. Model acquisition is a separate network/setup step. Then add microphone capture with a visible recording indicator, consent, stop/cancel and retention settings. Transcription, speaker diarization and factual meeting decisions are separate capabilities: do not infer named speakers or invent decisions from unclear audio. Sharing a transcript needs an independent destination approval.

**Acceptance:** silence/noise, long file, cancellation, mixed language, low memory, missing model, CPU-only operation and no-network execution after assets are installed. Preserve `WAKE_MODEL = "hey_jarvis"`; this proposal does not change wake-word behavior.

## 7. Backups, sync and developer reliability

### O24 — Verified backup and restore (new tool, B; previous idea made concrete)

**Intent:** “Show the latest snapshot and prove a sample can be restored.”

Restic is an optional backend candidate. Its normal repository check verifies structure; full pack-data verification requires `--read-data`, with subset alternatives for bounded checks. A successful lightweight check must not be described as full data verification. [S1]

MVP: selected-root backup plan, dry-run/exclusion preview, immutable snapshot identifiers where supported, timestamped check status and restore to a new empty destination. Restore selected files and verify hashes/readability. Store repository secrets through the credential system. Cloud storage charges, verification downloads and disk needs are user-visible.

No automatic forget/prune, source deletion, repository password replacement, original-path overwrite or “backup succeeded” claim merely because a process launched. Recovery-key handling and a documented restore drill are release requirements.

### O25 — Sync health and conflicts (integration, C)

Syncthing's REST API offers status/events but also powerful configuration and control operations. Possession of an API key can expose more authority than a read-only dashboard requires. Build a narrow adapter that only calls approved status endpoints; protect the key and do not expose the administrative service through a public preview. [S2]

Show disconnected devices, pending items, errors and conflicts without automatically choosing a winner. Synchronization propagates changes/deletions; **it is not a substitute for versioned backups**. Offline access to a local service is possible when deployed locally, but other-device freshness still depends on connectivity.

### O26 / O27 — Duplicate review and troubleshooting notebook (extension/workflow, B)

Use size/hash grouping for byte-identical duplicate candidates; verify at execution time before a separate approved move/quarantine plan. Similar photos or filenames are not proof of duplication. Never remove the only copy in a backup or sync topology automatically.

A troubleshooting notebook reuses existing monitors: timestamped observation, hypothesis, approved change, result and rollback pointer. Sanitize logs before external analysis. It should say “service unreachable from this machine” rather than assert the remote service is down. Avoid indiscriminate environment dumps containing secrets.

### O28 / O29 — GitHub triage and release watch (integration B; extension C)

**Intent:** “Summarize assigned issues and draft an update”; “Tell me when this project's release needs review.”

GitHub issue endpoints may include pull requests; distinguish the `pull_request` field. Permissions are endpoint-specific, so do not assume that a single fine-grained token type supports every feature. Start with selected repositories and read-only issue/PR retrieval. [S3]

Treat comments, issue bodies, diffs and release notes as untrusted content, not executable instructions. Draft issue edits/comments separately from posting; avoid automatic merge, broad `git add -A`, push, dependency install or executing code from a report. Release watching extends `cloud_watchtower`; it should use durable last-run state, dedupe, rate-limit/backoff and clear “watch registered” versus “release found” outcomes.

## 8. Household, mobility and routines: validate demand first

### O30 — Travel-time and errand planner (workflow, C)

openrouteservice is an OSM-based candidate with walking/cycling/driving/wheelchair routing and related route-planning capabilities. This supports an adapter feasibility case, not a guarantee of live traffic or safe/accessible physical conditions. [L1]

Require explicit origin/destination disclosure, departure/arrival timezone, selected mode and provider attribution. Exact home/work coordinates are sensitive. Plans should show estimates, map-data uncertainty and stale/offline state. Do not automatically book, purchase, send location, or add events. Validate actual service coverage and wheelchair constraints for intended locations before recommending real journeys.

### O31–O33 — Lists, inventory and routines (new tools/extensions, C)

A local shopping list and household inventory have low provider dependency and useful voice intents. Link receipts, serial numbers and maintenance tasks without uploading household photos automatically. Meal/allergen or medical advice is outside a simple list tool's authority. Routine checklists should be user-authored and reversible, not framed as health diagnosis or surveillance. These are plausible local-first ideas, but not yet provider-backed integrations or demonstrated user demand.

## 9. Shared architecture: build once

### Capability broker

Represent authority as **account + operation + resource set + destination + lifetime**, not just tool name. Split read, local-write, external-write, execute, destructive and outbound-data capabilities. A cloud read can still leak private data when its result enters an external model. Include a separate model/endpoint egress policy.

All alternative execution paths must respect the same broker: direct APIs, browser automation, generated code, shell commands and desktop interaction. Otherwise “draft-only Gmail” can be bypassed by a generic browser or command tool.

### Proposed tool/result contract

```json
{
  "operation_id": "host-issued",
  "status": "needs_approval",
  "summary": "Draft calendar event prepared; nothing created",
  "evidence": [],
  "effects": [],
  "freshness": {"source_checked_at": null, "cache_only": false},
  "approval": {"plan_id": "host-issued", "expires_at": "host-assigned"},
  "warnings": []
}
```

Illustrative contract only, not an implemented API. Use statuses that distinguish pending, partial, completed, failed, cancelled and unknown-outcome. Plan IDs are issued by the host, not accepted as model-invented evidence. Bind approval to a hash of exact operations/resources, expire it and invalidate on changes. Reconcile remote state after uncertain writes; do not blindly retry external effects.

### Bounded durable jobs

Shared scheduler: job IDs, persisted state, bounded queues, global concurrency/rate/spend limits, per-call deadlines, cancellation, retry/backoff policy and completion events. Timeouts must not leave invisible workers continuing to mutate state. On process restart, reconcile in-flight effects before resuming. Export/import and background watches need explicit retention.

### Notification center and recipes — O34/O35

One event queue should power notification digests, job status and reminders. Add quiet hours, urgency rules, dedupe, expiry and per-channel grants. Do not auto-send private results to Telegram or another external channel because a job finished.

Recipes are versioned, previewable compositions of approved primitives. Approval binds exact steps and destinations; modifying a recipe invalidates old approval. “Undo” is capability-specific: an email cannot generally be unsent through a local transaction rollback. Compensation limits must be stated honestly.

### Genuine research swarm — O36

Keep the bounded independent-worker design from the previous audit: read-only evidence workers with distinct subquestions, source registry, critic/citation verification, hard budgets and no recursive worker creation. Repair dispatch and existing job safety first. Only use a swarm when independent research adds value; ordinary queries should stay single-agent. Never label parallel one-shot requests as autonomous multi-agent investigation or model agreement as proof.

## 10. Acceptance gates and rollout

| Gate | Required evidence before enabling |
|---|---|
| Foundation | Dispatcher contract tests; all effects reach broker; privacy grants apply to external model calls; structured unknown-outcome handling |
| Deterministic local tools | Arithmetic fixtures; task persistence/restart; diff-to-source mapping; no silent data replacement |
| Google read-only | Denied/partial consent; revoke/logout; ACL-aware cache; pagination; stale data labels; no mutation endpoints admitted |
| Calendar writes | Exact preview; recipient resolution; timezone/recurrence fixtures; conflict checks; no duplicate after timeout |
| Document ingestion | Oversize/corrupt/encrypted inputs; bounded OCR; accepted vs indexed states; source retention |
| Safe sharing | Original preserved; removed text cannot be re-extracted; metadata policy; destination approval |
| Backup/restore | Snapshot verification level truthful; restore to empty target; corruption/failure handling; actual recovery drill |
| Desktop/audio | Native platform fixtures; cancellation; missing models/permissions; bounded recording; no automatic transcript send |
| Research/watchers | Source support audit; dedupe; quotas; restart recovery; injected-source instructions ignored |
| Cross-cutting | No secret-bearing logs; export/delete controls; dependency/license/version review; no claim of offline mode when cloud calls occur |

Suggested sequencing is dependency-based, not a calendar estimate:

- **Foundation:** audited defects, operation policy, credential store, durable jobs, structured results.
- **Local productivity:** O04/O10/O14/O16, a narrow O23, and O34.
- **Scoped Workspace:** O01/O02/O03/O08, then separately approved writes and O05/O06.
- **Personal knowledge/admin:** O11–O13/O15/O19, with optional O07/O09 after privacy review.
- **Reliability/accessibility:** O21/O22/O24/O26–O28 on explicitly supported platforms/services.
- **Demand-led expansion:** O17/O18/O20/O25/O29–O33/O35/O36.

Do not start every item simultaneously. Each adapter should be independently disableable and fail without breaking voice startup or unrelated tools.

## 11. What not to prioritize

- Another overlapping browser clicker, file manager, timer or clipboard tool.
- Autonomous purchases, payments, account recovery or credential harvesting.
- Automatic package updates, arbitrary generated-code execution or unrestricted self-modification.
- Broad mailbox/Drive ingestion as the default onboarding flow.
- Biometric locking or security claims based on unvalidated templates.
- Unbounded “24/7 monitoring” without durable jobs, budgets and actual evidence of execution.
- Blanket claims of medical, legal, accessibility, privacy or backup guarantees.

## 12. Sources and verification limits

Links below are primary documentation fetched during this research. They establish candidate feasibility and important constraints, not installed compatibility. Provider quotas, pricing, scopes, API stability and software licenses must be rechecked for the chosen pinned versions. No paid plan, throughput, local benchmark or country-specific service availability is promised.

### Google

- [G1] Desktop OAuth: https://developers.google.com/identity/protocols/oauth2/native-app
- [G2] Drive scopes: https://developers.google.com/workspace/drive/api/guides/api-specific-auth
- [G3] Free/busy request, scopes and response errors: https://developers.google.com/workspace/calendar/api/v3/reference/freebusy/query
- [G4] Calendar incremental sync: https://developers.google.com/workspace/calendar/api/guides/sync
- [G5] iCalendar standard and updates: https://www.rfc-editor.org/info/rfc5545/
- [G6] Google Tasks resource, especially `due`: https://developers.google.com/workspace/tasks/reference/rest/v1/tasks
- [G7] Gmail scopes: https://developers.google.com/workspace/gmail/api/auth/scopes

### Documents, research and accessibility

- [D1] Paperless-ngx REST API and ingestion: https://docs.paperless-ngx.com/api/
- [D2] Tesseract language/script data: https://tesseract-ocr.github.io/tessdoc/Data-Files-in-different-versions.html
- [R1] Zotero API v3 and local API notes: https://www.zotero.org/support/dev/web_api/v3/basics
- [R2] OpenAlex authentication and current access model: https://help.openalex.org/api/authentication/
- [R3] AnkiConnect upstream repository/versioned interface: https://github.com/FooSoft/anki-connect
- [A1] Microsoft UI Automation overview: https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-uiautomationoverview
- [A2] faster-whisper upstream implementation/benchmarks: https://github.com/SYSTRAN/faster-whisper

### Reliability and mobility

- [S1] Restic repository checks and restore-related repository operations: https://restic.readthedocs.io/en/stable/045_working_with_repos.html
- [S2] Syncthing REST surface and authentication: https://docs.syncthing.net/dev/rest.html
- [S3] GitHub REST issues and endpoint permissions: https://docs.github.com/en/rest/issues/issues
- [L1] HeiGIT/openrouteservice overview: https://heigit.org/smart-mobility/

### Remaining validation work

Actual provider calls and native apps were not exercised. People API scopes, Linux AT-SPI support, a specific redaction library, translation engine, financial import formats and notification delivery providers need targeted implementation research. Google Drive remote MCP was discovered but is deliberately not a production dependency recommendation without transport/auth/availability validation. MCP itself does not remove host permission checks.

No tests were rerun for this documentation-only expansion. The previous audit recorded 370 passing tests with one warning and 113 files compiled in memory; that remains historical, limited evidence, not whole-application certification. `WAKE_MODEL = "hey_jarvis"` and runtime code remain unchanged.
