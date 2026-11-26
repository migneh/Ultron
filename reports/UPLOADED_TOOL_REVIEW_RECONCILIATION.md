# Uploaded tool review — reconciliation with the working tree

## Scope and evidence

Reviewed the attached `ULTRON_TOOL_REVIEW.md` (349 lines) against selected current
source paths on `arena/bb266e5c-ultron`. This is a static reconciliation of the main
report, not an exhaustive re-audit or live/native certification. No application
code was changed for this review. Referenced appendices 01–10 and their README
were not supplied and have not been reviewed. The attachment's stated swarm
methodology and research citations cannot be independently verified from the main
report alone. Its 2026-11-25 date is later than this session's authoritative date
(2026-11-23); treat that date as document metadata, not verified chronology.

The report describes an older tree. Its 72-test and 51-action inventory should not
be used as the current release baseline. Latest completed local validation before
this review: 604 tests passed, one existing Starlette deprecation warning; targeted
Ruff and diff checks passed. These do not certify privileged/native behavior.

## Findings reconciled

| Report item | Current assessment | Source / reasoning |
|---|---|---|
| C1/C2: dead omni_telepathy/drone_swarm handlers | Addressed through an alternative valid contract | Both declare `argument_mode: keywords`; `core/action_loader.py` explicitly supports and validates this mode and prevents model arguments from overriding host context. Parameters-first is not the only valid fix. |
| C3: desktop Python sandbox | Still open, critical | `actions/desktop.py::_build_sandbox` exposes Python objects/modules, `Path`, `getattr`, and platform primitives. Removing a few names or adding a path check does not make arbitrary Python safe. |
| C4: self-evolution activation/persistence | Still open, critical; report needs nuance | `actions/self_evolution.py` compiles before approval and exclusively creates after approval, but then imports/executes in-process. Missing-spec, exceptions and validation-declined paths can leave code in auto-discovery directories. Compilation/exclusive creation do not isolate it. |
| C5: system_command three-keyword-only filter | Description stale; substantive exposure remains | Current classifier has a safe-command set, shell-syntax checks, Git option checks and approval for other commands. Git execution is not forced to disable pager, external diff, textconv or config helpers. Command-name classification is not a security boundary; full command/result audit content also raises privacy concerns. |
| C6: recycle/sleep confirmation bypass | Still open for system_utility | Dispatcher invokes `empty_recycle_bin` and `sleep_computer` directly, without a gate in that module. |
| C6: macro purge bypass | Overstated as a blanket claim | `macro_protocol.run_protocol` gates destructive built-ins including night/sleep before `_run_protocol_direct`; its helper calling `execute_purge` alone does not prove a public bypass. Internal-call and mutable-plan coverage still merits testing. |
| C7: swarm report path traversal | Addressed for migrated report access | `list_drone_reports`/sharing use `core/report_sharing.py::read_report`, with basename restriction, symlink refusal, resolved-parent confinement and bounded reads. Not a global filesystem sandbox. |
| C8: workspace audit import | Still open | `workspace_matrix.py` imports/calls `run_security_audit(quick=True)`; `network_auditor.py` exposes `audit_security_posture()` instead. Correct both symbol and call signature. |
| C9: DND wiring | Still open | workspace/iot callers request `dnd`; `android_bridge` dispatcher and schema have no such branch. Prefer an honest unsupported step until a permission-aware implementation exists. |
| C10: weather capability | Still open; browser search, not fabricated observations | `weather_report.py` opens a Google search and says it is showing weather; it does not return fetched, timestamped weather data. Description/result should distinguish those capabilities. |
| C11: media false success | Still open | Linux `media_volume_set` falls through to success without action; Windows exception fallback reports a volume value without verified effect. |
| C12/C13: meeting static brief/unbounded capture | Substantially addressed, not full transcription | Current bounded recorder and meeting metadata summary replace fabricated content claims. No actual transcription, diarization or content summarization is certified. |
| No audit/observability at all | Too absolute | Metadata-only bounded dispatch telemetry exists in `core/tool_observability.py`, plus specialized command/outbox/job records. There is not yet a universal durable privacy-reviewed audit trail. |
| No permission boundary | Still broadly applicable | Scoped operation policies protect migrated sinks, not legacy shell/browser/native/plugin paths. ActionRegistry is not the only execution path. |
| Swarm unbounded/fake convergence/in-memory-only | Old implementation superseded | Current `core/background_jobs.py` and migrated `drone_swarm` use bounded admission, durable outcomes, cancellation, deadlines and conservative restart behavior. Research remains sequential bounded collection, not independent autonomous agents or verified convergence. |
| General scheduler/retries/workflow missing | Still broadly applicable | Durable bounded jobs are not a general timer/cron/workflow service. Unsafe effects are not replayed automatically. |
| Notification delivery absent | Old baseline superseded | Host-opt-in generic HUD counts now exist with quiet hours and durable suppression; default is pull-only. No external delivery or guaranteed UI receipt. |

Optional-import, headless, SSRF, clipboard, file-controller and other per-tool claims
in the matrix remain leads, not independently revalidated conclusions in this
reconciliation. Do not treat every historical line number as current evidence.

## Architecture recommendations requiring revision

1. **No same-process Python sandbox.** A subprocess alone also is not isolation:
   it inherits user access unless OS-enforced filesystem, identity, network and
   resource restrictions actually apply. Unsupported platforms must fail closed
   or clearly offer trusted full-privilege execution, never a silent fallback.
2. **One registry hook is insufficient.** Inventory inline tools, plugins, direct
   helper calls, callbacks, timers and monitors. Enforce at sensitive sinks as well
   as dispatch. Bind approval to immutable exact plans and content, not names alone.
3. **Do not let a model grant itself permissions.** A permission tool may inspect
   or request a host-mediated grant; cannot directly elevate or mint consent.
   Risk must follow actual operation/data/destination, not merely read/write tiers.
4. **Tool retrieval is selection, not authorization.** No universal 30–50-tool
   accuracy cliff or 20–29 optimal cap is established by this main report. Measure
   routing quality and provider API compatibility before removing declarations.
5. **Injection wrapping/classification is defense-in-depth, not prevention.**
   Keep untrusted content separate from authority; constrain effects, secrets,
   egress and tool subsets independently of model judgement.
6. **Retries require reconciliation.** Calendar/email/publishing/device operations
   need operation-specific idempotency and uncertain-outcome handling. Never treat
   leases or workflow restart as permission to replay an external effect.
7. **MCP extends the trust boundary.** Connection approval/token auth are not enough:
   validate server identity, schema changes, tool provenance, local stdio execution,
   HTTP destinations and credential/egress scope. No automatic trust inheritance.
8. **Expand capabilities after containment.** The 35-tool list is a backlog, not an
   implementation mandate. Reuse current calculator/tasks/evidence/document and
   Google read-only adapters; do not duplicate them or broaden OAuth silently.

## Recommended next batches

1. **P0 execution containment:** quarantine self-evolution with no auto-discovery on
   any failure, and disable model-generated desktop Python until real isolation is
   available. Test fail-closed behavior without executing hostile host code.
2. **P0 privileged dispatch:** gate direct recycle/sleep, harden shell/Git execution
   against helpers/config/PATH and argument mutations, and audit all entry paths.
   Do not advertise arbitrary command parsing as a shell sandbox.
3. **Correctness:** repair workspace audit wiring, remove unsupported DND claims,
   return truthful unsupported media/weather outcomes; add fake-platform tests.
4. **Permission/audit spine:** inventory every sink and caller, host-managed grants,
   exact-plan approvals, durable metadata-only audit with retention and owner access.
5. **Then platform expansion:** measured tool selection, constrained MCP, safe fetch,
   workflow reconciliation, memory/evaluation. Independent swarm agents remain a
   separate unimplemented capability.

No commit or push performed. The user's `WAKE_MODEL = "hey_jarvis"` constraint
remains unchanged. Obtain the appendix bundle before claiming the full review is
complete or accepting its detailed schemas/research findings.
