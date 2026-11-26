# Durable host jobs and bounded research collection

This batch adds a shared on-demand job journal and migrates the public `drone_swarm` paths onto it. It does not add arbitrary-code submission, timed scheduling or automatic replay.

## Submit and inspect

Existing swarm requests now return JSON containing `job.id` and the current job snapshot. A submission message is not proof of completion. Fast workers may already have a terminal snapshot when submission returns; inspect the actual state.

```json
{"action":"parallel_swarm","directive":"Compare local-first document archives","subtasks":["Find primary documentation","Identify limitations"]}
```

`parallel_swarm` and its historical aliases are retained for routing compatibility, but now mean **sequential, bounded source collection** in a background host job. They do not spawn independent reasoning agents or certify convergence. One to three explicit subquestions are accepted. Without subquestions, three bounded evidence/alternatives/implementation queries are constructed. Provider results retain source URLs and timestamps; web text is untrusted, not execution instructions.

Use either `drone_swarm` status/kill with an actual full `drone_id`, or the new `background_jobs` tool:

```json
{"action":"status","job_id":"ACTUAL_HOST_RETURNED_JOB_ID"}
```

```json
{"action":"cancel","job_id":"ACTUAL_HOST_RETURNED_JOB_ID"}
```

The placeholders are explanatory, not valid IDs. IDs are exact 32-character host-issued values; no fuzzy matching, partial IDs or implicit kill-all on empty input. `background_jobs` also supports `list` (optional limit 1–100) and explicit `clear_terminal` (journal metadata only, never report files). It cannot submit arbitrary functions, commands or job kinds.

## Budgets and admission

- Default two admitted workers across migrated research, market and system jobs, with no unbounded pending queue.
- Blocked/cancel-requested/overdue workers retain admission until their host worker returns.
- Default swarm logical deadline 120 seconds. The host service accepts budgets up to 300 seconds; tools cannot raise this.
- Research: at most three sequential collector calls. Sampling: 1–10 iterations, intervals 5–60 seconds, at most 90 seconds of planned waits.
- `iterations=0`/infinite monitoring is rejected. Unknown actions do not turn a stray directive into a launch.
- Context counters measure **logical collector/sample calls**, not every HTTP exchange. Existing research providers can perform bounded internal fallback/retries and use their existing shared network limiter. This is not a global token/spend budget or a per-provider-attempt accounting system.
- Reports are character-bounded and mark truncation. No automatic external notifications, browser opening, attachment or Telegram send occurs. Explicit `share_report` still uses the verified outbox and HUD approval.

Market jobs support BTC/ETH/SOL/DOGE observations from one fixed bounded source, not stocks or invented fallback prices. Missing quotes are unavailable, not `$0`. System sampling uses actual available CPU/RAM readings and warns that the first CPU sample may lack a meaningful interval. Neither feature predicts future values or guarantees live freshness. Partial and wholly missing samples have distinct outcomes.

## Journal and ownership

Journal: `~/.ultron/background_jobs.sqlite3`; owner lock: neighboring `background_jobs.lock`. POSIX private permissions are requested. Permissions are not encryption and existing parent/Windows ACLs remain host responsibilities. Callables and input queries are not persisted; migrated workers persist only bounded outcome notes and report artifact names/hashes, not report bodies. Reports remain in the existing ignored `memory/drone_reports/` archive with unique job-based filenames and no overwrite.

A process-lifetime advisory OS lock admits one job-owning runtime per journal. Another runtime can inspect or request cancellation in the same journal, but cannot independently start more workers. Cancellation is persisted and checked at checkpoints/waits. Native/provider calls already in flight cannot poll the flag until they return.

Main startup acquires/reconciles the journal without replaying work. On ownership transfer after exit/crash:

- Never-started `queued` records become `interrupted`.
- Previously running/cancel-requested records become `outcome_unknown`.
- Completed/partial/failed records remain historical outcomes, not a continuing guarantee that an artifact has not subsequently been edited/deleted.
- There is **no automatic restart, retry, compensation or effect replay**. Inspect artifacts/provider state before deliberately submitting new work.

The journal admits at most 1,000 records by default and rejects new submissions when full. Clear terminal metadata explicitly when appropriate; report retention is separate. This prevents silent destruction of results to make room.

## States and cancellation truthfulness

- `queued`, `running`: persisted admission/start, not success.
- `cancel_requested`: request recorded, not a claim of termination.
- `overdue: true`: wall-clock deadline display while a worker may still be blocked; enforcement uses monotonic checkpoints.
- `completed`: the bounded collection/sampling and local publication completed—not factual verification.
- `partial`: explicit provider issues, missing subresults or report truncation.
- `failed`: no successful result certified.
- `cancelled` / `deadline_exceeded`: worker acknowledged the stop before an output effect began.
- `outcome_unknown`: crash, interruption or cancellation after an output effect may have begun; check artifacts. No rollback or safe-retry claim.
- `interrupted`: admitted work never started before a prior owner ended.

Workers mark possible output effects before file creation. Late research responses are checked before report publication. Reports retain full bounded source-linked sections instead of silently taking only the first twelve lines. Blank/unavailable sources do not count as verified research. There is no unconditional "100% convergence", fabricated fallback telemetry or claim that another model agreeing establishes truth.

Application shutdown requests cancellation and waits for at most two seconds total. If a native/provider call remains blocked, it reports remaining workers and retains ownership until workers exit or the process terminates. A Python thread is **not forcibly killed**. This service is not a hard process sandbox. The next owner reconciles unfinished metadata as above.

## Compatibility and limits

The tool name and main action aliases remain. Deliberate changes: job IDs replace sequential DRONE-01 IDs; kill-all/fuzzy resolution is removed; parallel aliases return an on-demand job rather than blocking for a dossier; unknown types/actions/infinite loops are rejected. The old internal detached `SubUltronDrone` class is removed; no other runtime modules imported it. Automatic HUD animation/speech callbacks are not invoked from these worker threads.

The general permission broker, timed/recurring schedules, automatic notification delivery, independent research agents, per-provider spending controls, other legacy background modules and hard process-level cancellation are **not migrated/implemented by this batch**. Global shell/browser/native effect paths still require the remaining audit work.

## Verification

594 tests passed with one existing Starlette/httpx warning. The 34 new job tests cover persistent admission/outcomes, capacity and cancellation, second-owner exclusion and cross-runtime cancellation, overdue blocked workers, possible-effect uncertainty, call/history bounds, malformed/oversized results, sanitized failures, shutdown ownership, thread construction/start failure, real subprocess-crash recovery without replay, missing/partial research and market data, late-result rejection, exact report paths and the real action-registry contract. A stubbed main-function lifecycle test verifies startup/shutdown hooks without loading native UI/audio.

Existing report-sharing tests now run migrated jobs with fake collectors and temporary journals, preserving the no-automatic-send checks. Targeted lint and diff checks pass. No real provider, Google account, market endpoint, native microphone, hardware sample or external message was used. This is not whole-application or Windows/macOS native certification. No commits; wake-word configuration is unchanged.
