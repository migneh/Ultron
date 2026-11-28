# Ultron assistance tools: research audit and enhancement roadmap

**Audit date:** 2026-11-23 (session date). **Baseline:** `6aaf198508c405138a30759c478e18be652e684b`. **Working branch:** `arena/bb266e5c-ultron`.

## Executive recommendation

**Make the current tools dependable before adding more autonomous powers.** The previous enhancement batches substantially improved timers, reminders, messaging, research, transfers, downloads and registry telemetry. They did not establish an application-wide policy boundary. Several older tools still implement overlapping actions through different, weaker paths.

The highest-value next sequence is:

1. Repair the registry contract for four existing tools and enforce that contract in CI.
2. Close alternative code-execution, destructive-operation and outbound-notification paths.
3. Replace invented completion/summary claims with evidence-based outcomes.
4. Consolidate overlapping engines behind one policy broker and a real job lifecycle.
5. Build a genuinely bounded, read-only research swarm; evaluate it against a single-agent baseline.
6. Add practical task/calendar/document utilities, not another vaguely named autonomous concierge.

**This deliverable is an audit and proposal, not a repair release. No application code was changed.** The CSV beside this report is the machine-readable inventory.

## 1. Scope, method and assurance

### Inventory

Static AST enumeration found:

- **56 Python modules under `actions/`: 53 module-level `TOOL` declarations and 3 helpers.** A declaration is not proof it imports successfully or is usable on a particular workstation.
- **8 inline declarations in `main.py`**: `system_status`, `screen_process`, `close_camera`, `manage_monitor`, `shutdown_ultron`, `save_memory`, `recall_memory`, `undo`.
- `plugins/` currently contains `__init__.py` and `_template.py`, not installed concrete plugins.
- At least one direct import of **12 of the 53 action-tool modules** appears in the test ASTs. This is an inventory heuristic, **not test coverage**; transitive imports, indirect tests and depth of assertions are not measured by it.

Every declared action's schema/handler signature was enumerated. High-risk paths received targeted source review, and all 53 tools receive individual recommendations in section 6. This is not an exhaustive line-by-line security proof or workstation acceptance test.

### Parallel review, not a claimed independent-agent swarm

Four workstreams were pursued using parallel tool calls: (A) inventory/contracts, (B) mutation/consent/privacy, (C) reliability/lifecycle/truthfulness, and (D) external primary-source research. One coordinating assistant cross-checked their evidence.

**No independent LLM subagents were available or launched in this session.** Parallel shell/search calls are not independent agents. Ultron's existing `drone_swarm` was deliberately not executed because its current implementation can write reports, make cloud calls and notify Telegram automatically. Section 7 specifies the actual multi-agent system recommended for Ultron.

### Verification performed

- A fresh ignored `.venv` was created because this new checkout did not retain the previous environment. Installed development/test dependencies and the small set needed by the existing offline suite; did not install the full desktop stack.
- **370 tests passed**, one upstream Starlette/httpx deprecation warning. No skips were reported in that run.
- AST-only signature probes replaced handler bodies with `return locals()` before execution; no original tool bodies were executed by those probes.
- A real `web_autopilot` dispatcher reproduction used stubbed research/price functions, with no network, browser, filesystem mutation or model invocation.
- No destructive actions, ADB/fastboot operations, git operations through Ultron, camera/microphone capture, IoT writes, notifications or paid agent/model calls were executed.
- Historical audit documents were consulted for context, but new findings below are based on current source, not copied assertions from those older documents.

Passing the current suite is compatible with the defects below: it does not cover every registry-to-handler contract or real desktop effect.

## 2. Research findings applied to Ultron

These sources guide the proposals; they do not prove Ultron's runtime behavior.

| Primary source | Relevant guidance | Application here |
|---|---|---|
| Anthropic, *Writing effective tools for agents* | Distinct tool boundaries, explicit input/output contracts, meaningful compact outputs, realistic evaluations with verifiable outcomes. [1](https://www.anthropic.com/engineering/writing-tools-for-agents) | Consolidate duplicates; contract-test every declaration; evaluate selection and final effects, not decorative success messages. |
| Anthropic, *How we built our multi-agent research system* | Orchestrator/worker research benefits from independent parallel directions; separate contexts, explicit delegation, source verification and evaluation matter. More agents have real cost/coordination overhead. Its performance numbers are internal results, not a promise for another project. [1](https://www.anthropic.com/engineering/multi-agent-research-system) | Use a bounded research-only swarm where decomposability justifies it; keep single-agent execution for simple facts; measure actual quality/cost before claiming a win. |
| MCP tool specification | Described schemas, user-visible invocations and human review are part of the tool interaction model; deterministic listing is recommended. [1](https://modelcontextprotocol.io/specification/2026-07-28/server/tools) | Add enforceable operation-level metadata and validation, stable tool catalogs and auditable approvals. This is design guidance, not a claim Ultron already implements MCP. |
| MCP client best practices | Progressive discovery and host-brokered per-call authorization can reduce tool/context exposure; sandbox-originated calls still require authorization. [2](https://modelcontextprotocol.io/docs/2026-07-28/develop/clients/client-best-practices) | Offer task-relevant tools without allowing hidden tools to bypass policy; workers never receive unrestricted credentials or direct host access. |
| OWASP, *LLM06:2025 Excessive Agency* | Excessive functionality, permissions and autonomy amplify ambiguous or manipulated model outputs. Minimize extensions and gate high-impact actions. [OWASP](https://genai.owasp.org/llmrisk/llm062025-excessive-agency/) | A guarded shell is insufficient if code runners, ADB shell, browser submit or broad hotkeys offer equivalent effects elsewhere. |
| Playwright locator documentation | Locators are central to auto-waiting/retryability; some collection operations do not wait for stability. [1](https://playwright.dev/docs/api/class-locator) | Prefer semantic locators and explicit postconditions over coordinates, sleeps or clicking the first loose match. Inspect the installed Playwright version before adopting newer APIs. |
| Home Assistant REST API | Explicit service/action calls and state reads are distinct API operations. [Home Assistant](https://developers.home-assistant.io/docs/api/rest/) | Separate request acceptance from observed device state, constrain entities/domains and avoid broad default targets. |
| Open-Meteo forecast documentation | Structured forecast inputs/variables include coordinates, timezones and precipitation/wind/temperature data. [Open-Meteo](https://open-meteo.com/en/docs) | Upgrade the current browser-search weather shortcut to actual structured forecast data; verify terms/attribution and provider suitability before choosing it. |

External pages are live documentation and may change independently of this snapshot. Recommendations are engineering judgments based on the code and these sources, not externally validated performance forecasts.

## 3. Highest-priority confirmed findings

Priority meanings: **P0** = next release blocker for the affected capability; **P1** = next reliability/safety release; **P2** = usability/feature enhancement. Priority reflects potential consequences and reach, not a CVSS score.

### F1 — Four handlers do not receive their declared inputs correctly (P0, reproducible)

**Evidence:** `core/action_loader.py::_call_handler` always invokes `fn(parameters=parameters, **context)`. Four registered handlers instead declare expanded fields plus `**kwargs`:

| Tool | Source | What happens through the registry |
|---|---|---|
| `drone_swarm` | `actions/drone_swarm.py:619` | Requested `action`, `directive`, `target` etc. remain nested in `kwargs['parameters']`; handler sees default `action='list'`. |
| `omni_telepathy` | `actions/omni_telepathy.py:158` | Requested clipboard/control/broadcast action is swallowed; default `status` remains selected. |
| `screen_mind_read` | `actions/screen_processor.py:188` | Requested prompt/region are swallowed; defaults remain empty prompt and `region='all'`. The body also calls whole-screen capture, so fixing binding alone does not implement cropping. |
| `web_autopilot` | `actions/web_autopilot.py:124` | Its strict `kwargs` check rejects injected `parameters` and extra context keys: `Web request rejected: Unknown autopilot fields`. |

Safe real reproduction, with downstream functions replaced by stubs:

```text
Direct web_autopilot(action='research', query='audit_requested'):
  RESEARCH_STUB query='audit_requested'
_call_handler(web_autopilot, {'action':'research','query':'audit_requested'}, {}):
  Web request rejected: Unknown autopilot fields
```

**Recommendation:** adopt one canonical `handler(parameters: dict, ...)` interface; explicit adapters for any expanded-argument integrations. Do not blindly expand arbitrary model keys into handler/context kwargs. Validate declaration/signature compatibility at discovery and hot-load time.

**Acceptance:** every tool schema can route a minimal valid fixture through the real registry with side effects stubbed; assert the requested action and every field arrive unchanged. Reserved context fields cannot be supplied by the model. All four regression cases must be covered, not merely direct-function tests.

### F2 — Dangerous effects are still reachable through parallel paths (P0, source-confirmed)

- `code_helper._run_file` (`actions/code_helper.py:211`) and `_process_code(..., action='run')` (`actions/file_processor.py:460`) execute scripts directly; they do not use the shared confirmation boundary. This bypasses the *policy intent* of the guarded `system_command` path, not an OS sandbox, since there is no shared sandbox.
- `android_bridge.flash_partition` / `run_shell` (`:301`, `:321`) directly call fastboot flash and ADB shell; its dispatcher routes those actions without a shared approval step. Reboot/install/push/pull also need operation-specific constraints and exact device selection.
- `git_sentinel.git_commit` (`:184`) stages **all** changes using `git add -A`, then commits and optionally pushes. `git_push_pull` (`:227`) mutates repository/remote state without shared preview/approval.
- `system_utility_handler` (`actions/system_utility.py:172`) directly reaches recycle-bin emptying, while the overlapping `purge_protocol` path uses confirmation.
- `process_manager.kill_process` (`:61`) can match process names by substring and terminate multiple processes; numeric-PID termination escalates to kill after three seconds. No approval binds a user-reviewed process identity.

**Recommendation:** broker policy by effect, not only tool name. Gate code execution, flash/reboot/install, remote publication, irreversible deletion and force-kill. For scripts show exact content/hash, interpreter, working directory, args and network/file permissions. For processes bind PID + creation time and distinguish graceful close from force-kill. For Git preview exact staged paths and explicit remote/branch; never silently stage unrelated work.

**Acceptance:** calling every equivalent route either produces an exact preview awaiting user authorization or is explicitly disabled; no side effect before approval. Tests must include indirect calls from macros, desktop agents, background work and generated tools. Real execution isolation requires subprocess/container/OS policy, not a Python dictionary or a prompt.

### F3 — Meeting summaries contain invented content; capture is unbounded (P0 truthfulness, P1 recording lifecycle)

**Evidence:** `actions/meeting_scribe.py:75–194` accumulates `int16` microphone frames in a global list. `stop_recording` concatenates those frames, saves WAV and builds a literal template containing “Session objectives confirmed” and generic action items. It performs **no transcription or content-based summary** in that path. The start response says “system audio & microphone,” but the implementation opens a default mono input stream; no separate system-loopback configuration is shown. It sends the generated brief to Telegram if configured.

**Recommendation:** immediately label this as an audio recorder plus recording metadata, not a transcriber. Then add consent-based input selection, visible recording indicator, pause, duration/disk caps, streaming-to-disk, restart-safe session IDs, actual timestamped transcription, and evidence-linked decisions/action items. Cloud transcription and outbound sharing must each be opt-in. When transcription is absent/failed, return “not transcribed,” never template decisions.

**Acceptance:** a fixture with no stated decisions produces no decisions; extracted action items link to transcript offsets; overflow/cancellation/shutdown cannot create two recorders; no automatic sharing. At 16 kHz mono int16, raw audio alone is roughly 115 MB/hour, before list/array/concatenation overhead—derive caps from real storage/memory budgets.

### F4 — The existing swarm is parallel calls plus a completion template, not verified collaborative research (P1)

**Evidence:** `actions/drone_swarm.py:476–615` creates up to three mission strings, calls `deep_web_research` with a three-thread executor, takes only the first 12 lines of each result, and writes a master report claiming “100% Convergence Achieved.” If the research engine is absent, its worker substitutes a “Reconnaissance completed” string. There is no iterative evidence reconciliation or independent critique stage in this function. The tool sends a Telegram summary unconditionally through its notification helper when configured. Separately `launch_drone` (`:343`) adds daemon workers to `_ACTIVE_DRONES` without a visible admission cap there.

**Impact:** partial/provider failures can be dressed up as completed intelligence; source URLs may be lost by line slicing; the user cannot infer actual quality from the fleet animation. F1 currently prevents normal model-supplied actions from routing correctly; the other issues remain relevant to direct calls and any future routing fix.

**Recommendation:** implement the job/evidence architecture in section 7. Disable fabricated fallback success and default outbound notification now. Preserve structured sources rather than slicing presentation text. Report per-worker completed/partial/failed/cancelled states.

### F5 — Old desktop organization bypasses the newer engine (P1)

**Evidence:** `actions/desktop.py:315–355` still performs its own directory creation and `shutil.move` loop; `clean_desktop` (`:383`) has another archive/move loop. These do not delegate to the newer dry-run/conflict-aware transfer implementation in `file_controller`/`core.file_safety`.

**Recommendation:** one file-mutation service with preview, no-clobber, explicit batch plan and shared undo journal. Expose organize-by-type/date/archive as planners over that service, not independent writers. Keep newly created parent/category ownership in the journal.

**Acceptance:** the same fixture routed through `desktop_control` or `file_controller` has the same preview/conflict behavior. Apply failures preserve undo of earlier completed items. Changed sources invalidate a preview; original-path conflicts never overwrite later user content.

### F6 — New message safety is not universal outbound-data policy (P1)

**Evidence:** `meeting_scribe._send_telegram_brief` (`:60`), `sentry_protocol._send_telegram_photo` (`:69`) and `drone_swarm._notify_boss_telegram` (`:58`) use outbound paths separate from `core.messaging`'s user-approved text outbox. `omni_telepathy.telepathy_broadcast` is another outbound integration to review when its routing is fixed. This limitation was already acknowledged in the earlier enhancement documentation; it is not a regression newly introduced by this audit.

**Recommendation:** distinguish interactive sends from **explicit, narrow, revocable standing notification grants**. Bind recipient/channel, allowed data types, event, expiry, rate and retention. Without such a grant, draft only and request approval. Photo/recording sharing requires media-aware policy; do not pretend a text-only receipt system already covers it. Emergency/security alerts can be opt-in, not silently removed or globally allowed.

**Acceptance:** recording/research completion never causes outbound data without a matching grant or approval; rejected/unknown outcomes remain honest and are not automatically resent through another transport.

### F7 — Biometric language and defaults overstate the evidence (P1)

**Evidence:** `biometric_sentinel.authenticate_user` (`actions/biometric_sentinel.py:133–248`) compares preprocessed face templates using `cv2.matchTemplate`, converts that score to a displayed percentage with an ad hoc formula, and labels a match “VERIFIED.” It defaults `lock_on_intruder=True`; nonmatch reporting says the workstation was locked even when the platform/flag does not perform that effect. No liveness or calibrated identity-error evaluation is shown.

**Recommendation:** classify it as an experimental local face-similarity demo, not an authorization mechanism. Never use it to approve tools. Disable lock-on-nonmatch by default; use observed lock results. Require deliberate enrollment/deletion, bounded retention, local-only defaults and explicit camera consent.

**Acceptance:** non-Windows/non-lock modes never claim locking; printed photos/low light/multiple faces are evaluated before any security claims. A percentage is not an authentication confidence unless calibration supports it.

### F8 — Claimed assistants sometimes only launch searches or store one-off observations (P1/P2)

- `weather_report` (`:5`) opens a Google search and returns “Showing the weather”; it does not fetch structured forecast data.
- `bounty_hunter.hunt_price` (`:54–105`) regexes the first currency-like amount from a prose search report, prints it as dollars regardless of original currency, appends a JSON record and says it is “actively monitoring.” That function does not start a recurring job.
- `cloud_watchtower.check_endpoint_health` (`:64`) fetches arbitrary endpoints and consumes `resp.content`; provider/socket timeouts alone are not a body cap or an aggregate fleet deadline.

**Recommendation:** weather should return provider/timezone/units/forecast timestamps with explicit browser fallback. Price observations should include merchant/product identity, currency, variant, tax/shipping assumptions, retrieved time and confidence; only label “watching” after a durable scheduler accepts a watch. Fleet probes need bounded responses, a global deadline and safe target policy. Authorized private-LAN/server endpoints require a separate user-configured allowlist—do **not** blindly reuse a public-only downloader that would break legitimate LAN monitoring.

### F9 — Importability and runtime effect correctness are still underspecified (P1)

**Evidence:** registry validation checks a top-level `OBJECT` and callability, not nested field types, enums, required fields or signature compatibility. `tool_status` intentionally checks only a fixed presence allowlist. Main injects the full declared tool collection into model configuration (`main.py:769–773`, `:1893`). Several tools have import-time dependency/setup behavior, including report-directory creation in `drone_swarm` (`:51`). There is no `.github/workflows/` directory in this checkout.

**Recommendation:** safe explicit capability manifests; side-effect-free discovery; dry-run/schema/contract checks in CI; operation result envelopes; task-relevant tool discovery. Do not run camera, network, package installation or filesystem setup merely to list capabilities.

## 4. Architecture improvements shared by the actual tools

### A. One host-side policy broker

Every dispatch—including direct helpers used by macros, workers and inline tools—needs a trusted request context: local/remote origin, user/task/session identity, permission grant, tool/action, validated arguments and destination scope. Model arguments must never set these trusted fields.

Proposed metadata (not implemented): `risk`, `read_only`, `effects`, `data_classes`, `network_scope`, `supports_preview`, `supports_undo`, `requires_approval`, `platforms`, `dependencies`, `max_runtime`, `max_output`, `idempotency_policy`.

Use explicit profiles: public web read, configured private endpoint read, local document read, workstation mutation, external send and code execution. “All tools available” must not mean “all effects authorized.” Browser, keyboard and arbitrary shell capabilities make perfect semantic prevention impossible; restrict them to narrowly approved sessions and isolate risky workloads.

### B. Structured results without pretending every handler succeeded

Keep a backward-compatible text rendering, but add a result envelope:

```json
{
  "status": "partial",
  "code": "PROVIDER_UNAVAILABLE",
  "summary": "Two sources retrieved; one provider timed out",
  "job_id": "opaque-host-issued-id",
  "data": {},
  "evidence": [],
  "effects": [],
  "warnings": [],
  "retry": "read_only_retry_allowed"
}
```

Statuses should distinguish `awaiting_approval`, `queued`, `running`, `completed`, `partial`, `failed`, `cancelled` and `outcome_unknown`. A dispatch return is an event, not an end-state verifier. Read-only retries may be bounded; ambiguous sends, destructive operations and device commands must not be blindly retried.

### C. A durable, bounded job service

Unify drones, monitors, scribe, downloads/large processing and schedules around job IDs, admission limits, deadlines, progress, cancellation acknowledgement, checkpointing and retention. Separate “cancellation requested” from “stopped.” Python thread timeouts do not terminate underlying work. Use subprocess isolation/resource limits where hard cancellation is required. Resume must not replay a completed external side effect.

### D. Privacy, memory and storage ownership

Use a user data directory rather than repository-relative operational stores. Define raw capture vs transcript vs derived memory retention independently. Provide inspect/export/delete operations and cross-store deletion receipts. Clipboard/window titles/terminal snippets should not be silently promoted into permanent facts. Keep secrets in a host-owned credential store and redact local diagnostics; do not expose credentials to workers or model-generated code.

### E. Fewer engines, clearer user-facing tools

Keep distinct user intents but consolidate implementation:

- Web search/research/price/flights/bounties share provenance and provider adapters.
- `desktop_control` file routines call the file service.
- `computer_control`/settings/media/ghost/war-room share verified desktop primitives.
- `workspace_matrix`/macro/IoT/Chronos use one declarative workflow engine.
- Vision/OCR/screen mind-read share capture, crop, redaction and cloud-upload consent.
- Memory/recall/graph use an authoritative record lifecycle with explicit provenance and deletion propagation.

Do not simply collapse everything into one giant `execute_anything` tool: narrower operations still help routing, permissioning and tests.

## 5. Prioritized implementation backlog

Effort is a relative estimate: **S** roughly 1–3 engineering days, **M** roughly 4–8, **L** roughly 2–4 weeks. These are planning estimates, not promises; native acceptance and product decisions can expand them.

| Order | Work package | Priority / effort | Release gate |
|---|---|---|---|
| 1 | Four handler adapters + registry/schema contract tests | P0 / S–M | All 53 declarations pass routing fixtures; context cannot be overridden. |
| 2 | Gate code runs, ADB/fastboot, all-stage Git, recycle-bin and force-kill paths | P0 / M | Zero side effects before exact approval across equivalent routes. |
| 3 | Remove invented meeting/swarm/bounty/biometric outcomes | P0–P1 / S–M | Every outcome either has evidence or is explicitly unknown/not implemented. |
| 4 | Shared notification grants + recording/camera/upload controls | P1 / M–L | No ungranted outbound data; revoke/expiry/rate tests. |
| 5 | Delegate legacy desktop mutation to safe file service | P1 / M | Preview/apply/undo equivalence and conflict tests. |
| 6 | Structured results + job IDs + global resource budgets | P1 / L | Queue/full/deadline/cancellation/restart/unknown-effect tests. |
| 7 | Browser semantic targeting, isolated profiles, submit/upload approval | P1 / M–L | Target URL/window verified before effect; stale state aborts. |
| 8 | Real recorder/transcription pipeline and currency-aware scheduled watches | P1–P2 / L | Content-grounded outputs, actual scheduling receipts, retention controls. |
| 9 | Bounded research swarm MVP | P2 after 1–7 / L | Better evidence quality than baseline at an approved cost/latency budget. |
| 10 | New productivity tools in section 8 | P2 / incremental | Only add tools with non-overlapping intents and measurable acceptance. |

## 6. Recommendations for every existing declared tool

These are recommendations, not claims that every proposed feature is presently absent or every row has a confirmed exploitable defect. Source anchors identify the current canonical handler; the detailed findings above identify confirmed problem paths.

| Tool / source anchor | Recommended next enhancement |
|---|---|
| `airspace_sentinel` — `actions/airspace_sentinel.py:293` | Clamp scan durations, label approximate RSSI distance/vendor inference, deduplicate rotating identifiers, require explicit authorized scanning scope and registry retention limits. |
| `android_bridge` — `:336` | Exact serial selection; separate inspect/transfer/install/reboot/flash/shell permissions; approved image hash/partition preview; verify return code and post-reboot state. |
| `audio_matrix` — `:235` | Bounded playback queue, sound concurrency/volume cap, mute/quiet-hour policy and cancellation; don't let cosmetic sounds contend with speech/capture. |
| `biometric_sentinel` — `:284` | Experimental labeling, no authorization role, opt-in capture/locking, calibrated claims, retention/deletion and camera-error handling. |
| `bounty_hunter` — `:147` | Structured currency/merchant/variant observations; durable watch IDs, actual schedules, deduplicated threshold events and expiry; never equate a search result with monitoring. |
| `browser_control` — `:926` | Dedicated isolated profiles by default; semantic locators with ambiguity errors, page/domain postconditions, explicit submit/upload/payment review and cancellation of timed-out coroutines. |
| `cerebro_memory` — `:143` | Source/age/confidence citations, cross-store deletion/contradiction handling and permission-aware retrieval; graph facts remain evidence, not executable instructions. |
| `chronos_predictive` — `:267` | Explainable suggestions before changes, explicit watchdog opt-in, low-overhead polling and reversible power-mode snapshots; avoid automatic intent claims. |
| `clipboard_control` — `:51` | Local-preview/redaction option before returning private clipboard text to the model; restore previous clipboard on undo only if unchanged; safe size caps. |
| `cloud_watchtower` — `:199` | Configured endpoint scopes, streamed body caps and fleet deadline; don't leak auth on redirects; explicit status vs payload-health checks and offline/backoff state. |
| `code_helper` — `:525` | Exact diff/write/run approval, isolated execution with resource/network restrictions, subprocess-tree cleanup, bounded output and exit-code-based results. |
| `computer_control` — `:358` | Bind actions to reviewed window/process and screenshot geometry; reject stale focus, prefer accessibility targets; shared emergency stop and sensitive-field safeguards. |
| `computer_settings` — `:784` | Read-back verification of volume/brightness/Wi-Fi/power effects; command deadlines and supported-backend status; restore original values, not generic toggles. |
| `desktop_control` — `actions/desktop.py:421` | Delegate organizing/archiving to shared file planners; no unchecked alternate move path; wallpaper downloads reuse bounded transport with explicit replace semantics. |
| `dev_agent` — `:593` | Preserve existing approval/path guards; add isolated per-project environment, dependency lockfile preview, patch-based edits, test evidence, cost/run budgets and checkpointed rollback. |
| `drone_swarm` — `:619` | Repair binding first; bounded research job service, isolated worker scopes, complete provenance and critic/synthesis stages; no forced success templates or unapproved notifications. |
| `file_controller` — `:664` | Consolidate all alternate file paths; atomic replacement and crash-safe journals for writes; verified trash restoration rather than guessed success; bounded list/largest operations. |
| `file_processor` — `:784` | Per-format byte/page/pixel/archive expansion limits, destination conflict rules, safe extraction plan, converter exit-code checks, explicit cloud disclosure and approved code runs. |
| `file_search` — `:293` | Preserve bounded traversal; offer stable pagination, indexing opt-in with invalidation/ACL checks, match-context redaction and tested interrupted-search continuation. |
| `flight_finder` — `:296` | Strict typed itinerary/airport/date/currency validation, bounded extraction and source/time per quote; safe filenames from route input; no implication of booked inventory. |
| `game_updater` — `:940` | Preview title/app ID/size/library/free space before install; verify actual download state; durable schedule IDs and native acceptance tests; distinguish launch from install completion. |
| `gesture_control` — `:338` | Retain opt-in/lifecycle guards; add debounce, per-gesture enable/disable, calibration, accessibility alternatives and visible pause/kill switch; test accidental gestures. |
| `ghost_pilot` — `:231` | Treat choreography as an optional presentation layer over shared verified desktop primitives, not a separate authority; fail on focus changes and provide emergency stop. |
| `git_sentinel` — `:269` | Explicit selected-file staging/diff preview, secret detection advisory, named remote/branch approvals, worktree awareness and conflict-safe pull behavior; do not default to `add -A`. |
| `iot_overlord` — `:243` | Entity/domain allowlists, explicit desired state instead of retry-prone toggles, post-action state reads, restricted private endpoint configuration and high-impact-device exclusion. |
| `macro_protocol` — `:344` | Typed declarative steps, per-step grants, dry-run and partial-failure journal; bind approval to immutable protocol version/content rather than only mutable recipe name. |
| `media_controller` — `:90` | Reuse shared audio controls, distinguish mute from toggle, active-player selection and state verification; don't claim playback changed solely because a key was sent. |
| `meeting_scribe` — `:236` | Recorder honesty first, then consented transcription with timestamps, bounded streaming storage, grounded decisions, review/export and separate approval for external sharing. |
| `network_auditor` — `:686` | Authorized target scope, aggregate deadlines, typed TLS/DNS findings and confidence; distinguish certificate failure from reachability failure; redact local host/process identifiers. |
| `network_scanner` — `:390` | Explicit authorized CIDR/port caps, bounded subprocess lifetimes and concurrency, cancellation and bandwidth disclosure; private monitoring uses configured scopes, not global public access. |
| `omni_telepathy` — `:158` | Repair binding; pair/revoke device identities, command allowlists, clipboard privacy controls, external broadcast grants and acknowledgement semantics. |
| `open_app` — `:243` | Ambiguous app resolution prompts, per-platform app IDs and verified launch/focus receipts; distinguish URI launch from native executable launch and avoid claim inflation. |
| `optical_hud` — `:176` | Shared region-aware capture, OCR language selection/confidence, secret redaction preview, local-first extraction and evidence-linked diagnosis; avoid uploading unnecessary full-screen content. |
| `process_manager` — `:148` | PID+creation-time identity, exact multi-match selection, graceful close before terminate, force-kill approval and protected-process policy; do not substring-kill a collection by default. |
| `purge_protocol` — `:298` | Preserve approval, add immutable exact deletion plans with age/reparse checks, reclaimed-byte verification and partial-failure receipts; arbitrary developer-cache removal needs explicit scope. |
| `quick_timer` — `:232` | Keep session-only default; optional durable alarm mode should be separate and explicit; accessibility-friendly notification acknowledgement and sleep/resume behavior tests. |
| `reminder` — `:30` | Native Windows/macOS/Linux acceptance, recurrence/exception rules, snooze/reschedule, missed-job policy and DST-gap/fold review; preserve stable IDs and strict scheduling semantics. |
| `screen_mind_read` — `actions/screen_processor.py:188` | Repair binding; actually honor region/window selection, crop/redact before any upload, explicit capture purpose and cloud consent, typed unavailable/capture status. |
| `self_evolution` — `:351` | Keep approval-before-activation; add static contract tests, isolated dependency/runtime validation, provenance/version hash and rollback/quarantine. Approval alone is not safe execution isolation. |
| `send_message` — `:87` | Preserve strict text outbox; build a reviewed address book with exact recipient resolution, revocable notification grants and retention controls; add media only with separately verified receipts. |
| `sentry_protocol` — `:353` | Explicit sensor/egress grants, visible capture state, bounded evidence retention, debounced events, cross-platform verified lock status and no unsupported face/security guarantees. |
| `system_command` — `:205` | Preserve conservative classifier/approval; isolated execution profiles, bounded stdout/stderr, process-tree cancellation and resource limits; audit retention/redaction controls. |
| `system_utility` — `:172` | Delegate trash/power actions to shared policy-aware services; verify lock vs display sleep, gate irreversible bin emptying and return accurate unsupported states. |
| `tool_status` — `:37` | Expand via declared capability manifests and opt-in native smoke checks; correlate job completion with dispatch without treating returns as success; tool health must not execute risky probes. |
| `video_player` — `:170` | Keep open/cancel generation tokens; bounded resolver jobs, content-origin metadata, local-file scope, volume/speech arbitration and verified player-ready/error events. |
| `voice_matrix` — `:94` | Bounded synthesis queue, voice/locale sample previews, hearing-safe output cap and predictable cancellation; show actual engine/backend rather than persona marketing. |
| `war_room` — `:157` | Preview monitor layout before changes, persist/restore previous geometry, validate display IDs and route launches through shared app policy; safe fallback when monitors disappear. |
| `weather_report` — `:5` | Structured geocoded forecast with units, timezone, rain/wind windows and data age; ask on ambiguous cities and expose browser launch as fallback, not weather data. |
| `web_autopilot` — `:124` | Repair registry adapter; keep honest excerpts/no-booking limitations; use a shared research result object instead of reparsing formatted text. |
| `web_search` — `:293` | Citation-to-claim mapping, source quality/diversity and contradiction flags, cache with freshness labels, bounded source fetching/PDF handling and explicit incomplete coverage. |
| `workspace_matrix` — `:564` | Declarative preview, reuse shared setting/app/IoT services, permission-aware step execution, original-state rollback and clear partial results rather than a monolithic success. |
| `workspace_recall` — `:270` | User-controlled sources and retention, inspect/forget/export/edit, memory provenance, secret filtering and unified deletion across its SQLite/FTS and graph/long-term stores. |
| `youtube_video` — `:414` | Timestamp-linked transcript summaries, language/source/freshness disclosure, bounded retrieval and metadata-only fallback; explicit output-file naming/overwrite and no automatic editor launch unless requested. |

For rows abbreviated as `:line`, the module path is `actions/<tool_name>.py`; exceptions are written explicitly. Full exact paths/handler names/signatures are in `ASSISTANCE_TOOL_INVENTORY.csv`.

### Helpers and inline core tools

- `background_monitor`: preserve provider-unavailable vs no-new-results distinction; an empty list from the legacy DDGS helper must not silently mean a successful daily check. Use durable checks with backoff, quiet hours and event dedupe.
- `proactive`: one user-controlled suggestion/notification queue with interruption policy, bounded frequency and explanations; never turn a suggestion into an unreviewed mutation.
- `system_monitor`: sampling budgets, threshold hysteresis, sensor-unavailable status and health checks that do not block speech/audio callbacks.
- `system_status`: return timestamped structured readings and unsupported sensors, not guessed zeros.
- `screen_process` / `close_camera`: shared sensor lease/crop/redaction policy, visible camera state and reliable cleanup on interruption.
- `manage_monitor`: stable job IDs, actual scheduling receipts and scope-limited persisted subscriptions.
- `shutdown_ultron`: orderly cancellation/flush/sensor release; don't confuse application exit with machine shutdown.
- `save_memory` / `recall_memory`: source/confirmation flags, deletion propagation and explicit separation between user facts and untrusted tool content.
- `undo`: structured success/conflict/partial outcome; recoverable conflict entries and durable journals for selected file operations instead of implying universal reversal.

## 7. Proposed real swarm multi-agent system

**Recommendation: evolve `drone_swarm`, do not add a competing swarm tool.** A real research agent has its own bounded context and an iterative decide → allowed tool call → observation loop. Three ordinary function calls in threads are useful parallelism but are not sufficient evidence of that architecture.

### Roles and topology

```text
User request + user-approved budget/scope
                   |
         Host policy / job broker
                   |
           Lead planner (one)
                   |
       +-----------+-----------+
       |           |           |
   Evidence A  Evidence B   Evidence C
   primary     alternatives implementation /
   sources     and risks   compatibility
       +-----------+-----------+
                   |
        Evidence registry / dedupe
                   |
      Critic + citation verifier (one)
                   |
        Lead synthesis with uncertainties
                   |
       Local report; external send only by grant
```

For a tool audit, assign workers **contracts/reliability**, **effects/privacy** and **external evidence/product gaps**. Require each to return different scopes and explicit evidence, not the same question with cosmetic role labels. For a single weather fact, skip the swarm.

### Host-enforced starting limits (proposed defaults, not measured tuning)

- Maximum **one active research swarm**, **three concurrent evidence workers**, no recursive worker creation.
- Workers get at most **four tool calls** and one bounded write-free evidence-fetch phase each; cap combined external fetch/search operations at **12** and total provider token budget at a user-visible configured value (for example 24k), with hard accounting of retries/fallbacks.
- Initial overall logical deadline **120 seconds**; each nested tool call has its own deadline within the remaining budget. Hard-stop guarantees require cancellable processes/provider support; do not advertise thread termination.
- Reviewer and synthesis run after worker fan-out, not as unbounded extra fan-out; all model calls, verification fetches and fallback requests count against the same job budget. Start with a total model-call cap (for example 8) and reserve some budget for the reviewer. Abort/degrade explicitly rather than hiding overspend.
- Model SDK calls can themselves invoke fallback ladders: budget actual provider attempts and usage, not merely the wrapper function count. Do not create a second unconstrained queue outside the current four-slot network limiter.
- Output cap per worker, deduplicated URL/source corpus, no raw-page megadumps. Keep evidence records, not truncated first-lines-only prose.

### Evidence and worker result contract

```json
{
  "worker_id": "host-issued-id",
  "scope": "contracts",
  "status": "partial",
  "findings": [{
    "claim": "Tool X loses action parameters",
    "evidence": [{"kind": "code", "path": "actions/example.py", "line": 10}],
    "confidence": "reproduced",
    "limitations": ["native desktop not exercised"]
  }],
  "sources": [{"url": "https://public-source.example/", "retrieved_at": "UTC timestamp"}],
  "unresolved": [],
  "usage": {"tool_calls": 0, "provider_attempts": 0}
}
```

The host validates identifiers, evidence shape, budgets and permissions. Treat every worker's text as **untrusted evidence**, not an instruction granting the lead more permissions. A critic must check citation support, contradictions, missing viewpoints and unsupported completion claims; another LLM agreeing is not independent factual verification.

### Permission boundaries

- Workers receive only read-only source/code/search tools. No shell, desktop input, email/Telegram, Git write, file mutation, microphone/camera or general tool synthesis.
- API keys remain in the broker. Workers receive no raw credential files or inherited user tokens.
- Report persistence is a host operation to an explicitly chosen destination, not an unrestricted worker filesystem capability.
- Network egress and private-file scopes follow the user's task; external research cannot silently consume local secrets. A local code audit needs separately granted repository scope.
- Subagent requests cannot approve another agent's effect. The critic cannot execute the repair it proposes.
- Explicit cancellation, provider-failure and partial-result states; never “100% convergence” from task completion alone.
- Event log: job/worker IDs, state transitions, timings, usage and evidence references; no private raw reasoning transcript or unrestricted prompts in ordinary logs.

### Evaluation before wider release

Build 30 representative research/audit tasks with known factual/evidence rubrics. Compare single-agent, parallel-search-only and full swarm configurations under the **same total budget**, not against an underfunded baseline. Measure:

1. Supported-claim and citation accuracy; fabricated facts must fail.
2. Coverage and contradiction detection; do not grade length as quality.
3. Unnecessary duplicate searches and irrelevant tools.
4. P50/P95 latency, provider attempts, tokens and measured cost.
5. Graceful provider outage/cancellation/budget exhaustion.
6. Prompt injection from pages and peer outputs: zero unauthorized effects.
7. Human review of ambiguous tasks and source bias.

Publish a go/no-go threshold before comparing variants. If the swarm is not materially better on decomposable tasks, ship the simpler parallel-search approach and label it accurately. This follows the research distinction between valuable independent exploration and expensive coordination overhead. [1](https://www.anthropic.com/engineering/multi-agent-research-system)

## 8. Useful additional tools, ranked by fit

These are **proposals**, not capabilities implemented by this audit. Add as small tools over existing safe services; avoid duplicating current names/intents.

| Rank | Proposed tool | Practical request | Minimum useful version / safety | Relative effort |
|---|---|---|---|---|
| 1 | `task_board` | “Keep a checklist for this project; what's blocked?” | Local SQLite tasks/subtasks, due dates, dependencies, status history and export; completion requires a user action or explicit evidence, not model optimism. Integrate reminders without conflating tasks with alarms. | M |
| 2 | `calendar_assistant` | “Find a free hour next Tuesday and draft the event.” | Start with local ICS import/export and conflict checks; timezone/DST/recurrence correctness. Provider sync later with minimum scopes, preview of exact attendees/time and explicit invitation approval. | M–L |
| 3 | `document_compare` | “What changed between these two contracts?” | Bounded TXT/PDF/DOCX extraction; deterministic diff plus page/paragraph-linked summary; never provide unqualified legal advice or invent a changed clause. Reuse `file_processor` extraction rather than another converter. | M |
| 4 | `calculator` | “Convert 180 TND to EUR using a quoted rate” / “Compare these loan totals.” | Decimal arithmetic, units, formulas and assumptions; network FX only with provider/time/currency evidence, cached-rate label and no inferred tax/financial advice. Offline arithmetic first. | S–M |
| 5 | `backup_restore` | “Back up this folder and show me that it can be restored.” | User-selected roots, manifest/hashes, bounded exclusion-aware backup; restore to a new destination and verify. No silent overwrite, encryption-key handling outside the model and no “backup succeeded” without a restore check. | L |
| 6 | `inbox_assistant` | “Summarize today's important mail and draft replies.” | Start read-only or with user-provided exports; source-linked summaries and phishing/untrusted-content treatment. Draft-only default; sending/deletion has exact reviewed approval and provider-scoped access. | L |
| 7 | `notification_center` | “Hold nonurgent alerts until 6 pm, then show one digest.” | Local event inbox across reminders/monitors/jobs; dedupe, severity, quiet hours, snooze and per-channel grants. Does not suppress user-designated urgent events silently. | M |
| 8 | `workflow_recipes` | “Prepare my work session, but show the plan first.” | Productize/extend `macro_protocol`, not a second arbitrary code runner: typed declarative steps, preview, immutable recipe version, per-effect authorization and partial rollback. | L |

**Extensions rather than more tools:** grounded meeting transcription belongs in `meeting_scribe`; recurring price/RSS watches belong in a shared monitor service; real forecasts belong in `weather_report`; screenshot accessibility/OCR belongs in the shared vision service; translation belongs in bounded document/text processing. A permissions dashboard and credential vault are host infrastructure, not unrestricted model tools.

My first feature combination after the P0 fixes would be **task board + calendar drafting + document comparison**. They improve everyday assistance without granting arbitrary host execution. That prioritization is a product judgment for this repository, not a measured user-demand study.

## 9. End-to-end acceptance plan

### Contract and source safety in CI

- AST/static lint and compile gates; schema-required/enum/type/bounds tests for every tool.
- Minimal valid calls through the real registry with effect adapters mocked; malformed values, unsupported actions and trusted-context-key injection must fail safely.
- Side-effect-free discovery subprocess: fail on network calls, capture, data-directory writes or installation attempts during import.
- Test risk/permission metadata against each action's actual effect routes; flag undocumented subprocess/network/write entry points for review.

### Deterministic integration fixtures

- Fake OS/ADB/Git/browser/IoT/provider adapters with explicit receipts and injected partial failures.
- File conflict/changed-source/restart tests; process PID-reuse test; currency/variant false-price tests; empty-transcript summary tests.
- Recorded source fixtures with conflicting dates/currencies and malicious page/peer instructions.
- Bounded queue/parallel load, active-worker limits, cooperative vs hard cancellation and output-limit tests.

### Native and user acceptance

Run a documented matrix on supported Windows/macOS/Linux hosts with actual desktop permissions. Cover sleep/wake, high-DPI/multimonitor, camera/audio denial, offline providers, scheduler restart and UI confirmation expiry. Distinguish supported, degraded and unavailable by operation—not by marketing description. Preserve `WAKE_MODEL = "hey_jarvis"`.

Live-service tests must be separate opt-in jobs with least-privilege test accounts; never send to real recipients, flash a real device, delete personal data or run arbitrary generated code as part of routine CI.

### Suggested release success criteria

- All 53 tool contracts validated; no silent action-field loss.
- Every high-impact effect path either broker-authorized or explicitly unavailable.
- No fabricated completed/verified/sent/recorded/transcribed outcomes in deterministic failure fixtures.
- No ungranted sensor capture/upload/outbound message in policy tests.
- Clear native support matrix and P95 latency/budget measurements for supported operations.
- Swarm ships only with honest partial/failure reporting and evidence-quality/cost comparison.

## 10. What changed in this audit

Only this report and `ASSISTANCE_TOOL_INVENTORY.csv` were added under `reports/`. No runtime tool implementation was modified, no agents/provider SDKs were invoked, and no audit changes were committed or merged. Research web search/page retrieval was used to consult public documentation; this is distinct from invoking Ultron's configured providers or swarm.

**Bottom line:** the earlier planned batches are implemented, but the whole tool surface is not yet uniformly safe, correctly routed or truthfully verified. The next engineering release should prioritize F1–F3 and equivalent effect paths, then shared lifecycle/policy and a measured, genuinely bounded research swarm.
