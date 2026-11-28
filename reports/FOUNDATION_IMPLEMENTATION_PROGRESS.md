# Foundation implementation — batch 1

## Implemented

- Added explicit internal `TOOL["argument_mode"] = "keywords"` support for named-field handlers. The original `parameters` dictionary convention remains the default.
- Opted in `drone_swarm`, `omni_telepathy`, `screen_mind_read` and `web_autopilot` to fix audited argument-routing mismatches without changing their direct-call interfaces.
- Named-field dispatch injects only explicitly declared host context, rather than leaking `response`, `session_memory` and other context into validated `**kwargs` option bags.
- Reject unknown/missing required named fields and attempts to inject reserved host arguments before handler execution. This is a field-shape check, not complete JSON Schema/type validation.
- Discovery binds declared fields to handler signatures without executing handlers, rejecting incompatible conventions early.
- Internal argument-mode metadata is not included in model-facing declarations.
- Updated invalid-argument telemetry wording to cover contract failures, rather than incorrectly saying every failure means a non-object input.

## Verification

`python -m pytest -q` using `.venv/bin/python`: **389 passed, one warning** (existing Starlette/httpx deprecation).

New tests cover original dict-style compatibility, host-context isolation, unknown/reserved/missing fields, discovery rejection, four real handlers with effects stubbed, and signature binding for every bundled TOOL declaration via AST-derived inert stubs. The inventory test does not import or certify native dependencies.

`git diff --check` passed. No live screen capture, message transmission, swarm launch or web research was performed by these regression tests. No account access or commits. Wake-word configuration remains unchanged.

## Important limits

This batch repairs routing; it does **not** make existing action effects safe or implement the proposed global permission broker. Correct dispatch means an explicitly requested operation can now reach its existing implementation. Existing swarm resource/notification issues and ignored screen region remain separate audit findings; do not interpret these fixes as authorization or whole-application certification.

## Next foundation batch

A single check at the action registry is insufficient: `main.py` has synchronous and asynchronous dispatch, inline tools, plugin dispatch and actions that call other actions directly. The permission boundary must cover effect primitives as well as registries, or alternate browser/shell/code/native routes can bypass it.

1. Inventory these entry points and the existing confirmation/file/message/download gates.
2. Define immutable operation plans with resource/destination scopes and host-issued approval identities; reuse the human-only confirmation mechanism.
3. Integrate one effect family end-to-end with rejection, expiration, changed-plan and alternate-route tests before claiming global enforcement.
4. Add structured unknown-outcome results and durable bounded jobs separately.
5. Then ship local task board/calculator/document comparison and scoped Google adapters as independent batches.

---

# Foundation implementation — batch 2

## Implemented: scoped notification approval boundary

Added `core/operation_policy.py`, a reusable **host-only in-process primitive**, and integrated it into dashboard/phone telepathy notifications:

- Host-issued operation identity, canonical JSON payload snapshot, sorted exact resource IDs and SHA-256 fingerprint.
- Process-local expiry, single submission and single callback consumption; a cancelled/unavailable/busy plan cannot later execute through its saved callback.
- Only a HUD callback establishes the transient execution grant. The effect sink consumes that exact plan's grant once. A new/changed plan or direct sink call has no approval.
- A locked grant remains single-use when execution crosses copied contexts/async tasks. This is application control flow, not protection from arbitrary malicious Python executing in-process.
- Preview names **opaque authenticated connection IDs**, not falsely verified device owners. Message controls/newlines are JSON-escaped in the HUD preview.
- Dashboard snapshots and writes run on its owning event loop, reached from host worker threads using a bounded bridge. The previous attempt to obtain an event loop from the tool worker thread is removed for this path.
- Recheck token expiry/revocation and exact connected destinations before any write, then recheck each destination before writing to it. Changed connections require a new preview.
- Private notifications do not enter shared history and are not replayed to clients that connect later.
- The legacy generic broadcast method rejects the standardized telepathy notification payload; direct calls to the new notification effect sink require the transient grant.
- Socket writes have timeouts; partial and uncertain results are explicit. Cancellation does not falsely certify that no bytes were written. No automatic retries. A completed socket write does not mean the device displayed/read the notification.

Both direct `telepathy_broadcast()` calls and registry dispatch reach `DashboardServer.request_notification()` and the same sink. The `omni_telepathy` declaration now describes the approval requirement.

## Scope inventory and exclusions

| Entry/effect path | Status after this batch |
|---|---|
| Main synchronous and asynchronous action registry paths | Share the repaired registry; notification action reaches the new boundary |
| Direct telepathy notification helper | Requires the same preview and approval |
| New private notification sink | Rejects ordinary direct calls without the matching grant |
| Legacy standardized `[TELEPATHY]` sys broadcast | Rejected; must use approved path |
| Other dashboard system messages/history | Existing behavior, not migrated |
| Dashboard audio, clipboard synchronization, photos and uploads | Not migrated |
| Telegram bot alerts, swarm/meeting notifications | Not migrated; existing audit findings still apply |
| Verified Telegram outbox | Existing dedicated approval mechanism remains separate |
| File/download operations | Existing dedicated safety mechanisms remain separate |
| Plugins, inline main tools, shell/code/native automation | No new global policy enforcement claim |

Do not interpret a notification-specific check as universal outbound-data protection. Generic Python, desktop/browser control or another transport could perform other outbound effects; a future global policy needs migration of those primitives or stronger process isolation.

## Verification and next steps

Full suite: **416 passed, one existing Starlette/httpx deprecation warning**. New tests exercise immutable snapshots, changed plans, missing approval, duplicate submissions, callback replay, concurrent copied-context grant consumption, cancellation, expiry, unavailable/busy HUD, direct helpers, changed/revoked connections, partial writes, unknown failures and bounded bridge timeout. One in-process TestClient WebSocket test exercises actual registration, the worker-to-loop bridge, grant propagation and disconnection cleanup. No real phone/network messages sent.

Targeted lint passes for the new policy/tests, and `git diff --check` passes. The whole dashboard's historical lint backlog was not reformatted. No account access, commits, or wake-word changes.

Next useful batch: migrate additional outbound effect families explicitly (especially automatic swarm/meeting alerts) and add truthful structured/durable job results. Local productivity tools can then use the shared primitives without pretending existing broad automation is already contained.

---

# Foundation implementation — batch 3

## Local completion and explicit Telegram sharing

Removed the legacy Telegram credential lookup/direct HTTP sender from `meeting_scribe` and the bot helper/automatic alert calls from swarm single-research, market and parallel-report completion. Completion does not send or queue a confirmation automatically.

Added explicit operations:

- `drone_swarm(action="share_report", report_name="exact.md", receiver="123")`: read a bounded exact local Markdown report, then request sharing through the existing verified message outbox.
- `meeting_scribe(action="share", filename="exact.wav", receiver="123")`: select a unique indexed recording and request sharing of its saved recording metadata, **not the audio**.

Both require an explicit numeric recipient; neither uses the configured chat as an implicit destination. Neither accepts approval flags. The existing outbox verifies sender/recipient, previews exact text, requires HUD confirmation and handles expiry/cancellation, deduplication and uncertain delivery. These paths deliberately reuse that durable mechanism rather than introduce a second Telegram transport or claim that the new in-memory dashboard policy has replaced the outbox.

The report-sharing helper rejects path components, fuzzy/glob selection, symlinks, unsupported file types, nonregular inputs and oversized/invalid text. Reads are bounded, with `O_NOFOLLOW` where supported; this is not a guarantee against arbitrary malicious filesystem/process manipulation on every platform. Full text is snapshotted into the outbox before approval. Later edits to the report cannot alter the approved payload. Oversized messages are rejected without automatic truncation, splitting or attachments; use explicitly selected text through `send_message` instead.

Meeting recordings now return factual recording metadata, explicitly state that no transcription/content analysis was performed, and do not invent decisions, speakers or action items. New index entries store this metadata for later explicit sharing. Older entries lacking a summary are rejected for sharing rather than reconstructing the old fabricated content. Recording start describes the default audio input instead of promising system/call audio capture. An index-write failure is surfaced rather than silently implying that metadata was indexed.

## Verification and remaining scope

Full suite: **440 passed, one existing Starlette/httpx warning**. Targeted lint and `git diff --check` pass. Added 24 tests for local-only completion (meeting, research, market and parallel paths with fake sources), exact previews, immutable post-preview snapshots, explicit numeric recipients, cancellation, expiry, uncertain-outcome deduplication, path/symlink selection rejection, size/Unicode limits, legacy/ambiguous meeting entries and absence of legacy sender calls in the migrated modules.

No real microphone recording, research requests, market requests, Telegram sends or account access were used. No commits; wake word unchanged.

Important remaining findings: recording duration/memory bounds and shutdown races, durable job/cancellation semantics, swarm admission/resource limits and misleading convergence claims are not solved by removing notifications. The legacy Telegram bot, security alerts, photos and other transports still have separate paths and are not globally migrated. Generic code/native automation is not sandboxed. This batch does not certify the whole application or a global outbound permission boundary.

---

# Foundation implementation — batch 4

## Bounded meeting capture and session ownership

Extracted capture lifecycle into `core/meeting_recording.py` and connected the existing meeting actions to one recorder instance:

- Default limits: 900 seconds, 32 MiB of retained PCM, and a bounded number of NumPy chunks. The actual sample cap is the smaller duration/byte budget; tiny driver reads cannot create unbounded object overhead.
- Each session owns its stop event, worker, title, buffer, counters and unique ID. An active, stopping, ready-but-unsaved, saving or save-failed session blocks replacement. No global boolean/buffer can be reused by a stale worker.
- Start reports STARTING, not successful microphone acquisition. Status exposes RECORDING, STOPPING, READY, SAVING and SAVE_FAILED and sanitized input-failure/overflow information.
- Stop requests cooperative cancellation and joins outside the state lock. If open/read/close remains blocked after the join deadline, return STOPPING without saving, clearing ownership or starting another session. Data returned after stop is not appended.
- Limit-ended and failed partial captures remain available for explicit stop/save. Save failures retain the buffer for explicit retry. Concurrent stop calls do not archive the same session twice.
- Save writes chunks directly to an exclusively created WAV; no full-audio concatenation/copy, no same-second filename collisions and no overwrite of an existing recording. A failed partial WAV is removed while the buffer remains available.
- Recording metadata distinguishes session elapsed time from captured PCM duration and records driver overflow/failure/limit notes.
- Index reads/output are bounded at 2 MiB; new index contents use temporary-file replacement instead of in-place truncation. Corrupt/full/unreplaceable indexes are preserved and the successful audio save returns a warning. Saving/indexing remains local; existing explicit sharing behavior is unchanged.

## Verification

Full suite: **469 passed, one existing Starlette/httpx warning**. Targeted lint and `git diff --check` pass. Added 29 fake-stream/archive regression cases: exact buffer limits and partial final chunks, tiny-read overhead, blocked open/read/close, late frames, input failure and malformed PCM, overflow notes, elapsed deadline checks, retained buffers on save failure, concurrent stop/save, thread-start failure, title validation, exact WAV frames, unique filenames, overwrite rejection, corrupt/atomic-failure index preservation, partial-file cleanup and archive availability before opening input.

No native microphone or real recording was used. No account access, external sends, commits or wake-word changes. Development environment dependencies were recreated because the prior virtual environment was absent in this turn.

## Limits and next work

This is cooperative thread cancellation, **not** hard termination of a blocked native driver. Duration is checked between native calls; a blocked native call can outlive the duration cap, while session ownership remains blocked. A process-isolated recorder would be needed for stronger termination guarantees. PCM buffer bounds do not constitute a total process-memory or archive-disk quota. Unsaved audio is memory-only and can be lost on crash; no crash-durable streaming capture is claimed.

Recording consent/visible persistent UI indicators, input-device selection, transcription, global shutdown integration, archive retention and a general durable job service remain separate work. Swarm resource/admission and convergence findings remain open. Local deterministic productivity tools can now be added in independent batches without waiting for a claim of complete application containment.

---

# Integrated local-first release batch

User selected the complete first-release scope rather than the full 36-capability roadmap. Implemented seven discoverable tools together, with shared strict field contracts, structured outcomes, four-slot synchronous admission, host-managed document roots and local SQLite persistence. Setup/examples/security limits are in `PRODUCTIVITY_RELEASE.md` and linked from README.

## Implemented and tested

- `calculator`: bounded Decimal AST interpreter (no eval/exec/code), 28-digit arithmetic and allowlisted compatible unit conversions.
- `task_board`: persistent create/get/list/edit/state updates with version conflicts, explicit date semantics and transactional local notices.
- `document_compare`: bounded authorized UTF-8 text/CSV reads, snapshot hashes, unified line diff, explicit truncation and positional CSV equality.
- `evidence_ledger`: persistent source-linked claims/quotes with host-issued IDs; every entry is explicitly unverified and not fetched by this tool.
- `safe_sharing`: candidate/literal plain-text redaction preview, one-hour preview validity, original preservation and exact-plan HUD-approved new-file publication with revalidation and output-byte verification.
- `notification_center`: bounded persistent local task-event pull inbox, dedupe/expiry, acknowledgement/cleanup and timezone-aware quiet-hours state. No background pushes or external channels are claimed.
- `google_workspace`: optional disabled-by-default read-only adapter, local/no-network status, fixed-host bounded reads, host file allowlist, Calendar agenda/free-busy and separate host model-context grant. Desktop OAuth uses the optional maintained library's PKCE/loopback flow; tokens are stored only in supported OS keyring backends. Disconnect distinguishes local removal from confirmed remote revocation.

Added host CLI `python -m core.productivity_setup` for root grants/revocation, status and optional Workspace connect/disconnect. Model-facing tools cannot add roots, connect accounts, supply credentials/scopes or forge approval. Added `requirements-workspace.txt`. Optional imports are lazy so missing Workspace dependencies do not prevent other tools from starting.

## Validation

**560 tests passed, one existing Starlette/httpx deprecation warning.** The 91 new release tests use temporary documents/databases and fake HUD, OAuth, keyring and HTTP. They exercise all seven real action contracts through dispatch, arithmetic/code rejection, persistence/conflicts, root rejection/revocation, diff truncation and formats, redaction output/cancellation/source changes/expiry, local inbox semantics, Google endpoint/write refusal, response limits, free/busy uncertainty and OAuth loopback/PKCE configuration. Targeted lint, setup CLI help and `git diff --check` pass. Inventory signature regression now requires at least 60 built-in TOOL declarations; the earlier 53-tool CSV remains a historical audit baseline, not a current inventory.

No real Google account/credential lookup, OAuth browser, document-directory grant on the user's machine, external message, native microphone or whole-app UI session was used. Optional dependencies were installed only to exercise the OAuth-library interface with fakes. No commits. Wake word unchanged.

## Honest release boundary / incomplete wider foundation

The implemented local MVP surfaces are not a claim that the entire proposed first release is production-certified. The global legacy effect broker, general durable background job service and unified automatic notifications remain incomplete; the older audit findings still apply. New operations are bounded synchronous calls with explicit persistence/approval where needed, not a hidden autonomous job runner.

Google activation needs actual host setup, consent and an OS credential store. Calendar reads are implemented but not live-provider tested. Drive reads additionally need provider-authorized app files under `drive.file`; there is no Google Picker/import UI in this batch, so fresh installations cannot authorize arbitrary files just by adding IDs. Do not silently request broader Drive scopes. There are no Google writes/invitations, Gmail integration, incremental Calendar cache or account content cache.

Redaction is only plain text, not PDF/Office/image sanitization; detection is fallible. Evidence storage is not source verification. The notification inbox handles new productivity task events, not every historical alert. Quiet-hours state does not imply a background scheduler. Local SQLite permissions are not encryption or secure deletion. Filesystem path checks are not protection against arbitrary malicious in-process Python or hostile filesystem races. These limitations are documented rather than masked by a blanket “everything verified” assertion.

---

# Durable jobs and swarm migration follow-up

Implemented `core/background_jobs.py` and the discoverable `background_jobs` inspector/canceller. Migrated all public swarm launch/collection/status/cancellation paths to the shared service, with startup reconciliation and bounded shutdown hooks in `main.py`.

## Completed in this batch

- Persist admission before worker start, with exact host-issued IDs, state transitions, logical deadlines/call counters and bounded result metadata.
- Default two admitted host workers; no unbounded pending queue. Cancelled/overdue blocked calls retain their slots. Finite 1–10 sampling iterations; no infinite monitoring. Fixed supported market tickers, bounded response reads, no fabricated fallback prices or hardware zeros.
- OS advisory journal owner lock prevents another runtime independently exceeding admission. Other runtimes may inspect/request cancellation. Lock is retained during stopping workers and released when the last worker exits, or by the OS on process exit.
- Atomic cancellation/terminal transitions; possible output effects are marked before file creation. Late provider results cannot publish after a checkpoint acknowledges stop. Uncertain effects are not described as rolled back.
- After ownership transfer, queued jobs become interrupted and previously running/cancel-requested jobs become outcome_unknown. No callable/payload persistence, automatic replay, retry or effect compensation.
- Exact-ID status/cancel; removed fuzzy IDs and implicit kill-all. Added explicit terminal metadata cleanup without touching report files. Journal admission caps at 1,000 records by default.
- Replaced the old parallel one-shot/forced-convergence path with accurately described sequential up-to-three-question source collection. Full bounded source-linked sections are retained instead of first-twelve-line truncation; missing evidence/fallbacks/truncation produce failed/partial results. No autonomous-agent, consensus or independent fact-check claim.
- Unique no-overwrite report files, private file permissions, source/timestamp retention and output hashes. Report listings and reads are bounded and exact-name-only. Reports remain local; explicit Telegram sharing still uses the verified approval-gated outbox.
- `main` reconciles on startup and requests cooperative shutdown after the UI loop exits, with a two-second total wait and honest pending-worker reporting. No native thread-kill claim.

## Verification

Full suite: **594 passed, one existing Starlette/httpx warning**. Added 34 job tests, including actual child-process exit/recovery without replay, cross-runtime ownership/cancellation, blocked worker capacity/deadline truthfulness, effects/uncertainty, budget/history limits, malformed results, constructor/start failure, source/sample outcomes, late-result suppression, exact-path selection and registry routing. A stubbed main-function lifecycle test checks startup/shutdown wiring without native UI/audio. Updated prior report-sharing tests to exercise the new job-backed paths with fake collectors and temporary journals, preserving no-send assertions. Targeted lint and `git diff --check` pass. Current inventory has at least 61 action declarations; prior inventories remain historical baselines.

No live research, account reads, market calls, hardware samples, microphone access or external sends. No commits. Wake word unchanged. See `BACKGROUND_JOBS.md` for operational semantics and compatibility changes.

## Still remaining

This is a durable **on-demand host job service**, not a general timed scheduler or execution sandbox. Cancellation is cooperative and physical provider attempts/token spend inside research fallbacks are not individually metered by the logical-call counter. Independent evidence agents, source-support verification, global privacy/effect enforcement across legacy native/shell/browser/plugin paths, automatic notification delivery, remaining legacy background migrations and Drive Picker/live native/provider validation remain open. The previous internal detached SubUltronDrone class is removed; public tool aliases remain with documented safer semantics.


### Opt-in local notification continuation

Added host-only local-notifications on/off consent, generic HUD count polling in
both provider loops, quiet-hours/expiry/ack checks and durable claim-before-submit
deduplication. Digest exposes queued/uncertain states; no automatic uncertain retry.
Default job service terminal events use a best-effort metadata-only inbox bridge.
No private notice body is automatically forwarded to model/speech/external sinks.
Native display/read receipts and guaranteed delivery are not claimed. Requested
`/artifacts/ULTRON_TOOL_REVIEW.md` and appendices could not be located locally or
by report/Ultron filename searches in connected Google Drive; no review claimed.


### P0 generated-code containment after uploaded review

Removed same-process desktop generated-Python execution and provider-generation
fallback; retained fail-closed compatibility stubs. Changed self-evolution from
in-process activation to approval-gated, exclusive owner-private inert source
drafts under ~/.ultron/source_drafts, with no registry mutation or execution.
Disabled legacy test/run/execute aliases. Existing installed modules are untouched;
this is not OS isolation or universal execution containment. Added seven isolated
regressions covering action/plugin drafts, no import, write failures, duplicate
writes, source bound, direct execution aliases and desktop generation bypasses.
Validation: 611 tests passed, one existing Starlette warning; targeted Ruff and
diff checks clean. No native/provider execution, commit or push.


### P0 privileged consent continuation

Removed automatic shell/Git inspection authorization from system_command: all
non-refused commands now need host approval. Full bounded command/shell/cwd/timeout
are captured; no 400-character command truncation. Added input validation and
metadata/hash-only new audit records, with approval cancellation states. Existing
raw audit files remain untouched. Gated public system_utility recycle/sleep helpers
and checked native error/exit statuses. Approved shell is still trusted account-
privilege execution: configured Git helpers, environment, binaries and descendants
are not sandboxed. Other tools are outside this gate. No universal broker claimed.

Validation: 623 tests passed, one existing Starlette warning; targeted Ruff/diff
checks clean. Twelve new consent regressions use fake effects and cover headless
Git/inspection, immutable full-plan approval, deny/one-shot behavior, metadata
privacy, utility helper/dispatcher and unsupported-platform behavior. No native
sleep/recycle, provider call, commit or push. Wake model remains hey_jarvis.


### Workspace wiring and capability truthfulness continuation

Fixed workspace audit import/signature; failure now reports posture not established.
Removed unsupported Android DND calls from workspace and IoT focus presets. Replaced
media false successes with checked scalar volume/readback on Windows, checked bounded
macOS submission and explicit unsupported Linux absolute-volume status. Preserved zero,
validated integer range, retired secret mute/unmute toggles and report key submission
rather than playback state. Workspace volume delegates to that backend. Lighting
preset/theme/focus/toggle statuses now distinguish HTTP acceptance from physical
verification; failed toggles do not pretend to queue. Other brightness, browser/app,
lockdown/native and legacy permission gaps remain; network audit score is not certified.

Added 29 fake-adapter tests. Recreated the excluded local venv after environment
reset and installed optional Workspace test dependencies (no OAuth flow or account
connection); final validation: 652 passed, no skips, one existing Starlette warning.
Targeted Ruff and git diff checks clean. No live audio/lighting/ADB/provider calls,
commit or push. WAKE_MODEL remains hey_jarvis.


### Process-control permission boundary continuation

Migrated process_manager termination to immutable exact PID/name/creation-time
snapshots and scoped operation-policy consent/consume at the effect sink. Bounded
20-process batch and 4,096-name-scan cap, protected init/self/ancestor PIDs, full
preflight plus per-process identity checks. Removed substring termination and
forced-kill escalation; shared bounded wait reports observed exit vs unknown.
Partial sequential outcomes and other legacy signal paths remain outside atomic
or global guarantees. Fixed focus-window PowerShell interpolation by carrying the
query as environment data into a constant script; distinguishes API acceptance
from verified foreground state. No new OS sandbox or global audit claimed.

Validation: 673 tests passed, one existing warning, targeted Ruff/diff clean.
Twenty-one new fake-only tests cover headless/deny/single-use grant, PID reuse,
new matches, batch/preflight protection, timeout/no escalation, protected/invalid
targets, access denial and focus query injection/nonzero exit. No real host
process terminated, native focus exercised, commit or push. Wake word unchanged.


### Privileged inventory and developer tools continuation

Added reproducible AST-only call-site inventory script plus CSV (826 manual-review
leads, not exhaustive coverage/vulnerability counts) and a manually traced grouped
migration queue in PRIVILEGED_SINK_REVIEW.md. Narrowed dev_agent to reviewed project
plan drafts and code_helper to proposals/explanations. Removed arbitrary generated
source writes, execution/install/fix loops, editor launch and screenshot path;
selected source reads require host-approved roots and bounded regular UTF-8 files.
New core/source_drafts saves exact-content immutable single-use approval snapshots
to exclusive inert .txt outside auto-discovery. Explicit output_path rejected;
source exposure to configured model documented. No source promotion, isolation,
global broker or complete legacy protection claimed. Remaining P0 Android/GUI/IoT
and file/Git/callback inventory traces documented rather than marked fixed.

Validation: 693 tests passed, one existing warning. Twenty new fake-only tests
cover approval/headless/deny/replay, legacy helper refusals, source read grants,
original-file preservation, symlink/conflict, size/input validation, plan-only
workflow and AST inventory. Targeted Ruff/diff clean; no live model, project install,
generated execution, native effects, commit or push. Wake word unchanged.


### Android shell/reboot permission boundary continuation

Gated public shell/reboot helpers with operation-policy exact-content approval and
consume at _execute_device_plan. Requires explicit serial, unique authorized
local ADB transport ID and executable fingerprint; revalidates both before -t
execution with explicit local server host/port. No silent default/fastboot fallback.
Disabled dedicated flash and EDL/sideload reboot; approved shell remains full
privilege and can itself perform dangerous operations, not a firmware sandbox.
Errors/outcomes uncertain, no retries. Existing transfer/install/capture/telemetry
paths remain unprotected by this scoped gate. Updated docs and static inventory.

Validation: 721 tests passed, one existing warning; targeted Ruff and diff clean.
Twenty-eight fake-ADB tests cover full command, headless/deny/replay, transport/
executable mutation, authorization/serial/input checks, reboot targets, effect-sink
grant and fail-closed flashing. No physical device/firmware/native/provider calls,
commit or push. Wake model unchanged.


### Android file transfer/APK engineering pass

Added core/android_files.py with effect-sink grants for push/pull/install, explicit
serial/transport and executable revalidation, host-root regular-file snapshots,
64 MiB cap and private approved-byte staging. APK -r requires explicit boolean
replacement consent. Push only uses fresh generated Download directories; failed
mkdir blocks upload, checksums distinguish readback from unverified acceptance.
Pull requires remote regular-file size/SHA, bounded queue/deadline/byte-limited
receipt, matching digest and exclusive local hard-link publication. No overwrite,
automatic retry or remote cleanup after uncertain partial effects. Local temporary
files cleaned normally; host/device races and process-tree/crash cleanup are not
sandbox guarantees. Legacy mirror/screenshot/telemetry remain explicitly open.

Added ANDROID_FILE_OPERATIONS.md engineering record and persistent TODO acceptance
table; refreshed static inventory to 835 unclassified leads. Forty new fake-ADB/
small trusted local-pipe tests; full suite 761 passed, one existing warning.
Targeted Ruff/diff clean. No real ADB/device effects, project installs, live model,
commit or push; wake word unchanged.


### Android single-frame screenshot continuation

User stopped PR preparation and explicitly directed no push; no commit/push had
occurred and branch HEAD remains baseline. Returned to implementation: screenshot
public helper/dispatcher now require exact new .png and explicit device approval.
core/android_capture.py consumes the sink grant, rechecks host root/transport,
receives one screencap via bounded 15s/16MiB stream, checks PNG signature/chunks/
CRCs/dimensions (40MP cap), rejects animation and publishes by exclusive hard link.
No overwrite, implicit Downloads path, cloud/model image upload or display. Partial
local staging cleaned on normal failure. No pixel decoding, native certification,
OS sandbox, atomic host/device lock, encrypted storage or crash cleanup guarantee.
Mirroring and telemetry still open; updated TODO and refreshed static inventory
(834 leads). Generalized bounded receiver for capped unknown-length PNG streams
without removing exact-size transfer checks.

Validation: 784 tests passed, one existing warning; 23 new fake-capture/pipe tests
cover headless/deny/replay, explicit-device dispatch, root/device changes, capture
limits, malformed/truncated/animated/CRC-invalid PNG, publication conflicts and
partial cleanup. Targeted Ruff/diff clean. No actual phone capture, commit or push;
wake word unchanged.


### Android finite owned mirroring continuation

Added core/android_mirror.py: exact immutable view-only mirror consent, explicit
serial and binary/transport preflight, no-control/audio/clipboard/power-on native
flags, 5–300s request plus host watchdog/native time limit. One owned live process
per live runtime owner (OS lock), metadata-only status, exact opaque-ID stop and
slot retained on failed direct-child termination. No arbitrary PID/name killing,
auto-relaunch or degraded-option fallback. Scrcpy runs device-side server and
uses serial (not locked transport); crash/descendant/package-dependency/platform
limits explicitly documented. Main shutdown closes mirror admission (including
idle late-approval race) and tries cleanup without skipping job shutdown on errors.
Telemetry remains unselected-device legacy path; broader GUI/IoT work still open.

Validation: 811 full-suite tests passed, one existing warning; 26 new fake-process
mirror regressions plus two main-lifecycle integration variants (success/failure).
Targeted Ruff/diff clean. Static inventory refreshed to 837 unclassified leads.
No real scrcpy/ADB/windows/phone, commit or push; WAKE_MODEL unchanged. Engineering
record ANDROID_MIRROR_LIFECYCLE.md and persistent TODO updated.


### Explicit selected-device Android telemetry continuation

Replaced implicit get_device_info/get-state/fallback chain with scoped telemetry
service and single-use selected-field/context-disclosure approval. serial required;
battery alias selects battery alone. Fixed-query allowlist; storage/IP explicit,
no arbitrary shell/query injection. 64KiB/5s output cap per query and20s issuance
budget; identity probes/cleanup can extend overall duration. Revalidation before
each query/after group; device changes discard all values. Parsing validates bounded
properties, battery level/scale, storage units and IPv4; failures unavailable, not
fake zeros. Values untrusted; adapter no persistence is not a guarantee about
existing assistant/UI/log consumers. Discovery remains separately open.

Validation: 841 tests passed, one existing warning; 30 new fake telemetry tests.
Targeted Ruff/diff clean. No real phone/provider/telemetry, commit or push; wake
word unchanged. Engineering record ANDROID_TELEMETRY.md and TODO updated; GUI-input
boundary next. Refreshed static inventory remains 837 unclassified call-site leads.

## Ghost Pilot narrowed GUI boundary

Windows pointer-only approval and sink enforcement, bounded steps/duration/primary geometry, held-input and fail-safe checks, owned cancellation/status, shutdown admission closure. Blind typing/search/click/app launch disabled including direct helpers. 46 fake tests; full suite 887 passed (one existing Starlette warning). Not target-verified GUI automation or native desktop certification. See [DESKTOP_POINTER_SAFETY.md](DESKTOP_POINTER_SAFETY.md). Inventory regenerated: 827 static leads, unclassified and not coverage evidence. No commit/push; wake word unchanged.

## IoT / bundled surveillance narrowed

Implemented core/iot_lighting.py approval-bound single-light HTTPS transport, config revalidation and strict fixed services/settings. Disabled raw/broadcast HA helper, implicit workspace lighting, IoT/macro lockdown and all sentry activation/worker/dispatch/lock/voice effects. Historical snapshots untouched. 53 fake tests added; full suite 940 passed (existing Starlette warning); targeted Ruff/diff clean. No physical/provider/native certification. See IOT_LIGHTING_SAFETY.md. File mutation/undo review next; no commit/push; hey_jarvis unchanged.

## Exact file transfers and session undo

Approved move/copy/rename sink, source/parent fingerprints and exact destination; private staged/fsynced no-clobber copy; uncertain move failure retains destination instead of deleting it. Undo approval binds one immutable top entry and revalidates transfer reversal conditions. Bulk desktop organize/clean disabled (read-only file_controller preview remains). 30 new tests; 970 full-suite passed, existing Starlette warning; targeted Ruff/diff checks clean. No user/native Trash/files touched. Remaining mutation sinks explicitly open; see FILE_TRANSFER_UNDO_SAFETY.md. No commit/push; wake unchanged.

## Configurable wake model / full namespace organization

Runtime moved to canonical ultron package (app/ui/actions/core/memory/dashboard/plugins/assets), pyproject CLI/package resources, root compatibility launcher, docs/notes separation and stable deployment paths. Source imports/dynamic loaders/tests migrated; existing config/memory/log state paths retained. Wake settings validate builtin or absolute trusted ONNX selection, threshold and label; exact-model score matching; default hey_jarvis unchanged. CLI edits preserve other config keys and do not enable microphone or download models. 47 new tests; 1017 full-suite passed, existing Starlette warning. Wheel build/install/CLI/config/resources/secret exclusion smoke passed from /tmp. Native/frozen/GUI/model/shortcut/scheduler validation remains open; legacy repository-wide lint not clean. See docs/PROJECT_STRUCTURE.md and docs/WAKE_WORD.md. No commit/push.

## Scoped small-file writes and folders

New ultron/core/file_mutations.py exact 16000-byte before/after plan, staged/fsynced publication, parent/target checks and private inverse requiring exact-entry session undo context. Public create_file/create_folder/write_file route through approvals; no recursive parents. Legacy raw write inverse disabled. Existing-file os.replace disclosed as metadata/hardlink-changing, best-effort precondition checking not atomic CAS. 40 new tests; full suite 1057 passed, existing Starlette warning; targeted Ruff/diff clean. No user/native files/Trash/network actions. Delete/Trash/download publication next. See FILE_WRITE_SAFETY.md. No commit/push, default wake constant unchanged.

## Scoped single-file Trash + disabled guessed restoration

Added ultron/core/file_trash.py exact plan/sink/native-boundary revalidation and sanitized submission/absence/unknown states. Public and direct file-controller Trash helpers gated; directories/special files/large files refused. Legacy COM name/parent scan/UNDELETE removed; restoration disabled and no automatic undo without a stable receipt. 30 new fake tests; full 1087 passed, existing warning; targeted Ruff/diff clean. No real native Trash/user files effects. Native/race/receipt limitations in FILE_TRASH_SAFETY.md. Downloads next; no commit/push, default wake unchanged.

## Two-stage download consent and checked inverse

Explicit URL/network receipt approval followed by independent received hash/size/path save approval. No redirects; worker fetch context does not authorize save; timeout workers only return bytes. Destination/root/parent preconditions revalidated at each phase, staged fsynced no-clobber publication validates final identity; private inverse uses exact-entry undo context and rejects changed file/parent. Legacy raw _undo_create removed. 22 new tests plus 47 download regressions; full suite 1109 passed (existing Starlette warning), targeted Ruff/diff clean. Fake HTTP/temp files only. Limits in DOWNLOAD_CONSENT_SAFETY.md. No commit/push, configurable wake default unchanged.

## Git Sentinel narrowing and application versions

33 fake Git inspection tests: single-use approved fixed vectors, repository/config/binary checks, known-helper suppression, bounded output/time checkpoints; all auto-stage/commit/checkout/create/stash/remotes and former argv helper disabled. Other macros/plugins/inline producers remain open. Version centralized in ultron/_version.py (existing 0.1.0 retained), dynamic wheel metadata, --version/version --json CLI, CHANGELOG and preview-first developer script (20 tests). No production bump/write, commit/tag/push/release occurred. Wheel metadata/source consistency checked. Full suite 1162 passed; existing Starlette warning; targeted Ruff/diff/version check clean, not native/global certification. See docs/VERSIONING.md and GIT_INSPECTION_SAFETY.md.
