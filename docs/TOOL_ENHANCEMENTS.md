# Assistant tool enhancements — timers, search, reminders and messaging

## Direction

The repository currently has **52 static bundled `TOOL` declarations**, including the new file search. This is an inventory count, not a runtime availability guarantee: imports, OS, hardware and credentials still determine what is usable.

These batches take frequent tasks beyond fire-and-forget execution. Detailed implementation review and tests focus on `quick_timer`, file search, persistent `reminder` scheduling, the `send_message` outbox, the shared confirmation gate, the existing file-controller search entrypoint, and their action-registry contracts. Other tools were inventoried, not all enhanced or revalidated.

## 1. Manageable session timers (`quick_timer`)

Old behavior: start a sleeping daemon thread and eventually announce. No ID, listing, cancellation or pause support.

New behavior:
- `start`, `list`, `status`, `pause`, `resume`, `cancel` actions.
- Every timer has a returned ID, label, state and rounded-up remaining seconds.
- Prefer IDs. Exact case-insensitive unique active labels also work; ambiguous requests are rejected rather than affecting an arbitrary timer.
- Monotonic deadlines, thread-safe state changes and generation checks suppress stale cancelled/paused callbacks.
- Logging and speech notifications fail independently.
- Limit: 32 running/paused timers; 1 second–7 days each; last 100 terminal records retained in memory.
- Pause/resume/cancel on an already incompatible state is idempotent: returns actual state without inventing success.
- No duration fields retains the old 60-second default. Explicit zero, negative, fractional, boolean or invalid durations are rejected. Whole-number strings remain accepted for existing callers.
- Existing `start_countdown_timer()` and duration-only tool calls remain available.
- These are **session-only**: they do not survive process exit, and completion can be delayed while the computer sleeps. Use `reminder` for OS-scheduled notifications. No new native notification guarantee is introduced; completion uses the supplied speech/log callbacks.

Examples of model tool arguments:

```json
{"minutes": 5, "message": "tea"}
{"action": "list"}
{"action": "status", "message": "tea"}
{"action": "pause", "timer_id": "<ID returned by start or list>"}
{"action": "resume", "timer_id": "<same ID>"}
{"action": "cancel", "timer_id": "<same ID>"}
```

## 2. New read-only tool (`file_search`)

A bounded alternative to recursive shell `find`/`grep` calls. It never writes, deletes, indexes persistently, launches programs or requests network access.

Filters:
- `path`: directory or existing file-controller shortcut; default `documents`.
- `query`: literal case-insensitive filename substring, not glob/regex.
- `extension`: final suffix, e.g. `pdf` or `.py`.
- `min_size_bytes`, `max_size_bytes`, `modified_within_days`.
- `content`: optional literal case-insensitive phrase in small UTF-8 text files. Returns the first matching line number and up to 180 characters from that line.
- `max_results`: 1–50, default 20.
- `max_depth`: 0–12, default 6; zero means root-level files only.

Safety and coverage:
- Uses configured file-controller safe roots (home by default).
- Excludes symbolic links, hidden paths, dependency/build directories, and common credential-like names/extensions. These heuristics are **not secret detection or DLP**. A normally named document can still contain sensitive text.
- Content search is opt-in. Returned snippets can enter the conversation with the configured AI provider; the tool does not itself send network requests.
- Reads only regular files from an explicit text-extension allowlist; skips binary/non-UTF-8 files. It does not parse PDF/Office documents; use `file_processor` for those.
- Per search: at most 10,000 entries, 500 directories, a three-second best-effort traversal deadline, 256 KiB per content file and 4 MiB of content bytes read. Filesystem calls themselves cannot be forcibly interrupted by this deadline.
- Results are sorted newest-first **within the scanned scope**, not guaranteed globally newest across an entire drive.
- Reports depth/time/entry/directory/content-byte/result caps and skipped errors/content files. Zero results must not be described as proof a file does not exist.
- Path checks and no-follow opens are safeguards, not an adversarial multi-user filesystem sandbox; concurrent ancestor/path replacement needs OS-level capability isolation for a hard boundary.

Examples:

```json
{"path": "downloads", "query": "invoice", "extension": "pdf", "modified_within_days": 30}
{"path": "documents", "extension": ".md", "content": "release checklist", "max_results": 10}
{"path": "desktop", "min_size_bytes": 10485760, "max_depth": 2}
```

Existing `file_controller` calls with `action="find"` now delegate to this engine, preserving their name/extension/path arguments while gaining bounded traversal and coverage reporting. This deliberately changes legacy coverage: dependency/hidden/credential-like paths are no longer searched. The legacy tool schema now advertises its already-supported `max_results` field.

## 3. Persistent reminder management (`reminder`)

The existing date/time/message call still creates a reminder. New actions are `create`, `list`, `status`, and `cancel`; management operations no longer require creation fields in the tool schema.

- Returns a unique 32-character `reminder_id`; reminders at the same time do not overwrite each other.
- Registry: `~/.ultron/reminders/registry.sqlite3`. Message text is stored locally in plaintext with owner-only database permissions on POSIX, not encrypted.
- Tracks `registering`, `scheduled`, `firing`, `notified`, `notification_failed`, `scheduling_failed`, and `cancelled`, plus registration/delivery/cleanup errors.
- Default list shows active registry records; `include_finished=true` includes terminal records. `limit` is 1–100 (default 50), ordered by scheduled UTC time. A list is capped, not a complete history export. At most 100 active reminders; terminal history is retained until manually archived outside this tool.
- Cancellation updates SQLite before attempting native removal, suppressing a late queued runner even if scheduler cleanup fails. Repeating `cancel` retries pending cleanup. A notification already claimed as `firing` cannot be recalled.
- An atomic SQLite claim prevents duplicate workers from notifying twice. This is **at-most-once attempted delivery**, not exactly-once delivery: a worker crash after claiming may lose the alert and leave `firing`. A failed notification is recorded and not automatically retried; create another reminder if needed.
- `notified` means the OS notification command returned success, **not proof that the user saw it**. Do Not Disturb, session state, hardware and OS policies may suppress notifications.
- Status is registry state, not a live scheduler health query. External deletion or editing of native jobs is not automatically reconciled. An interrupted registration stays visibly `registering` until inspected/cancelled; do not assume it was installed.

### Dates, timezone and DST

Use a valid `YYYY-MM-DD` date and `HH:MM` wall time. The requested instant must be at least 60 seconds ahead to allow OS registration. For shorter relative waits, use `quick_timer`.

Optional `timezone` accepts IANA names such as `Africa/Tunis` or `America/New_York`; otherwise resolve in the host computer's local timezone at creation. Nonexistent spring-forward times are rejected. Repeated fall-back times require an explicit `fold`: 0 selects the earlier occurrence, 1 the later occurrence. The chosen instant is stored in UTC and does not shift when the user later changes the computer's timezone. `tzdata` is now a runtime dependency so named zones work on Windows and systems without a zone database.

```json
{"date": "2027-01-15", "time": "10:00", "timezone": "Africa/Tunis", "message": "Review project plan"}
{"action": "list"}
{"action": "status", "reminder_id": "<full ID returned by create/list>"}
{"action": "cancel", "reminder_id": "<same full ID>"}
{"action": "list", "include_finished": true, "limit": 20}
```

### Native scheduling and limitations

Native jobs invoke the shared stdlib-only `ultron/core/reminders.py` runner with the database path and ID. Reminder text is data fetched from SQLite, not executable source or shell interpolation. OS commands use argument arrays and bounded subprocess timeouts.

| Platform | Adapter | Requirements / behavior |
|---|---|---|
| Windows | Task Scheduler with XML-escaped configuration and UTC boundary | Current user's interactive session; native PowerShell/WinForms notification; registration/notification still needs live Windows acceptance testing. |
| macOS | Per-user LaunchAgent with a 60-second due-time poll | Logged-in GUI user. Polling avoids unsupported yearly/UTC calendar assumptions and can delay notification by roughly a minute or longer under OS scheduling/sleep. Job unregisters after its terminal attempt. |
| Linux | On-disk systemd user `.timer`/`.service`, enabled with `systemctl --user`, `Persistent=true` | Working systemd user manager and `notify-send` in a desktop session. Jobs are on disk, not transient `systemd-run` units. User login/manager lifetime controls when missed jobs can run. Custom environment/session PATH must resolve native commands. |

Jobs survive closing Ultron; execution while logged out or powered off is **not guaranteed**. The Python interpreter, repository/runner path and registry must remain at their registered locations. Frozen executable builds are explicitly unsupported for creation until a separately packaged runner exists; management remains available.

Compatibility boundaries:
- Earlier reminder jobs have no registry IDs and are deliberately not imported or deleted. Manage them in the native OS scheduler. `list` only covers this version's jobs.
- Linux `at` fallback was removed: anonymous/untracked fallback jobs cannot provide the new cancellation contract. Missing/unavailable systemd user scheduling is reported as a registration failure, not silently downgraded to a session timer.
- Native cleanup failures are retained on the record and reported. Notification failure does not falsely become successful delivery.
- This is not a migration or adversarial local-user sandbox. Do not point the runner at an untrusted registry or allow other users to modify the runner/database. Windows filesystem ACLs remain governed by the user's profile.

## 4. Verified, consent-gated messaging (`send_message`)

### Deliberate compatibility change

Blind desktop sending was removed, not made to look more reliable. The old tool typed contact names and pressed Enter without a verified chat or send receipt. Its supposed WhatsApp verification plugin is absent from this repository. This version supports **Telegram Bot API sending only**; WhatsApp, Signal, Discord, Instagram, Messenger and arbitrary platform names are rejected without launching apps or typing.

Telegram sends come **from the displayed bot**, not the user's personal account. The bot must already be allowed to access/send to the target chat (a private user generally needs to have started the bot; groups/channels need appropriate bot permissions). An exact numeric chat ID is required; contact-name/username guessing is disabled.

Configure Telegram through the existing settings (`telegram_enabled` and `telegram_bot_token`), or explicitly opt in using the `TELEGRAM_BOT_TOKEN` environment variable. An environment token overrides those file settings for this outbound transport. Do not put credentials in tool parameters or chat messages.

### Preview → approval → receipt

- `preview` verifies the bot and chat using Telegram `getMe`/`getChat`, then creates/reuses a persistent draft. These metadata requests contact Telegram but do not send the message.
- `send` requests a HUD approval. Existing receiver/message_text/platform calls still use this default operation, but never send immediately. Passing a valid `message_id` reuses the immutable draft; recipient/body overrides alongside an ID are rejected.
- The HUD shows the numeric recipient ID, account identity, chat type, full plain-text body and a group/channel warning. Long details are scrollable, not truncated at 300 characters. Remote names have control characters escaped; HTML-like content is displayed as text.
- Only resolving the current HUD request starts a send callback. The callback atomically claims the outbox row and rechecks the configured bot and exact chat before a **single** plain-text `sendMessage` attempt.
- `sent` requires a matching API message ID, chat ID and returned message text. It means Telegram accepted the message, **not delivery or read confirmation**.
- Explicit API rejection becomes `failed`. Timeouts, interrupted requests, malformed/unmatched responses and uncertain server errors become `outcome_unknown`. There is no automatic resend or Markdown/HTML fallback send.
- Use `status`, `list` or `cancel` for management. List results omit bodies. Cancellation prevents unclaimed drafts/approvals from sending; in-flight, unknown and already sent messages cannot be recalled by this tool.

```json
{"action": "preview", "platform": "telegram", "receiver": "<numeric Telegram chat ID>", "message_text": "The exact text the user requested."}
{"action": "send", "message_id": "<full ID returned by preview>"}
{"action": "status", "message_id": "<same full ID>"}
{"action": "cancel", "message_id": "<same full ID>"}
{"action": "list", "limit": 20}
```

Send approval is not a model parameter: `confirmed`, `approved`, `force` or other undocumented fields are rejected. Bodies are never automatically split or reformatted. The limit is 4000 UTF-16 code units, conservatively below Telegram's message-size boundary; text is stored/sent exactly as supplied, including whitespace.

### Durable duplicate protection and limits

Registry: `~/.ultron/message_outbox.sqlite3`, owner-only database permissions on POSIX. It stores **plaintext recipients and message bodies**, not encrypted content. Tokens are not stored there. Application result/log handling suppresses credential-bearing HTTP exception strings and does not automatically log message bodies. Independently enabled verbose HTTP/debug logging is outside this sanitization guarantee.

States: `draft`, `awaiting_confirmation`, `sending`, `sent`, `failed`, `cancelled`, `expired`, `outcome_unknown`.

- Fingerprints include the sending bot ID, numeric recipient ID and exact body. Exact duplicates reuse drafts/active attempts and block a second send for 24 hours after an acknowledged send. This is not semantic duplicate detection; edits/whitespace changes can produce a new draft and still require fresh approval.
- In-flight/unknown outcomes block identical automatic retries indefinitely, including after an app restart. A crash after claiming but before recording a receipt remains `sending` and must be treated as uncertain. There is **no force-resend path** in this version; inspect Telegram manually.
- Definitely failed, cancelled or expired attempts may be prepared again, but each new attempt requires another HUD approval. No stored approval is restored or replayed on restart.
- At most 100 draft/awaiting/in-flight entries. Drafts must be cancelled to free their slots; no silent draft deletion. Terminal history is retained locally. `list` returns at most 1–50 recent entries (20 by default), not a full export.
- Approval has the shared 90-second lifetime; expiration is checked on gate interactions and outbox access. A stale banner can remain visible until interaction but cannot execute an expired request. Wall-clock jumps can conservatively expire an outbox approval; gate acceptance also uses monotonic time.

### Shared confirmation fixes

New requests no longer overwrite a waiting action. The HUD receives an internally generated request identity on show/hide/answer; delayed events for an older banner cannot approve or dismiss its replacement. Expiry, cancellation and unavailable/busy UI callbacks update the outbox safely. Legacy two-argument confirmation bindings remain compatible, but only the updated main HUD uses the request-ID stale-event protection.

This is a consent UX and duplicate-suppression mechanism, **not a security sandbox against other local code, filesystem edits, or separate computer-control automation**. Other tools and the existing `ultron/core/telegram_bot.py` remote-command/status response path are not routed through this outbox. Do not interpret this change as an audit of every possible messaging pathway or proof of physical human presence.

Native Telegram delivery and Qt rendering have not been exercised here: tests mock all HTTP/transports and source-check the headless UI contract. Live acceptance testing must verify real bot permissions, supported GUI layout, expiry/cancel behavior and the intended account/chat before production use.

## Verification

Current run: **228 tests passed** (72 baseline + 46 timer/search cases + 40 reminder cases + 70 messaging/confirmation cases), with one upstream Starlette/httpx deprecation warning. The seven focused tool/backend/gate modules pass mypy; new code/tests pass configured Ruff checks, and repository-wide runtime-failure lint checks pass.

- Regression tests exercise timer state, stale callbacks, callback failures, duplicate labels, concurrent starts, resource bounds and action-registry dispatch without real notifications.
- Filesystem tests use temporary safe roots: filters, text matches, depth/time/entry/directory/content limits, symlink loops/escapes, exclusions and compatibility with legacy find.
- Reminder tests use temporary registries and mocked native jobs/notifications: reopening state, cancellation races, concurrent claims, registration and cleanup failure, UTC/DST validation and adapter configuration.
- Generated Linux unit syntax also passed offline `systemd-analyze verify`; no units were installed or started. Native OS execution/notifications are not acceptance-tested.
- Messaging tests mock all transport/HTTP activity and exercise previews, late/stale clicks, cancellation and expiry, immutable payloads, exact deduplication, concurrent claims, failure/uncertainty states, matching API receipts and secret-safe errors.
- No real desktop actions, messages, notifications, model calls, or user-file searches were run to test these batches.

Run:

```sh
.venv/bin/python -m pytest tests/test_quick_timer.py tests/test_file_search.py tests/test_reminder.py tests/test_reminder_adapters.py tests/test_confirmation.py tests/test_send_message.py tests/test_message_transport.py -q
.venv/bin/python -m pytest -q
.venv/bin/ruff check ultron/actions/quick_timer.py ultron/actions/file_search.py tests/test_quick_timer.py tests/test_file_search.py
.venv/bin/mypy ultron/actions/quick_timer.py ultron/actions/file_search.py ultron/actions/reminder.py ultron/core/reminders.py ultron/actions/send_message.py ultron/core/messaging.py ultron/core/confirm.py --ignore-missing-imports
```

## Future candidates

Future candidates rather than implementations: a persistent task/checklist tool, user-approved workflow recipes and document comparison. Prefer these specific, testable capabilities over overlapping tools with broad autonomous claims.


## Web research quality (implemented)

- Shared four-worker cap and monotonic caller budgets bound provider wait time and prevent abandoned-thread accumulation. Search/comparison gets a 30-second overall logical budget; DDGS waits up to six seconds with SDK timeout five, Gemini waits up to twelve seconds with per-request timeout eight. Running DNS/provider threads cannot be killed: timed-out work occupies its slot until finished. No automatic retries of model calls.
- Gemini synthesis requires grounding URLs; unsourced synthesis is discarded. DDGS fallback and news-to-general-search fallback are labeled. Full source URLs, UTC retrieval times, and provider-reported publication dates (or unknown) accompany results. Dates are not independently verified; retrieval time is not publication time. Gemini grounding links do not constitute a sentence-level citation audit.
- Direct page downloads require public HTTP(S) URLs, no credentials, standard ports, public-only DNS answers on every redirect, and connections pinned to validated IPs with original-host TLS verification. Environment proxies are not used. HTTPS downgrades are blocked. This protects this page-fetch path, not all networking in Ultron or provider SDK internals.
- Downloads default to 512 KiB, three redirects, one retry, twelve seconds caller budget, three-second connect/four-second read timeouts. Retry only transient network errors or 502/503/504; long/dated Retry-After stops retry. Unsupported media and compressed responses are rejected; streams/connections close on exit. A declared oversized body is rejected; unknown-length bodies return labeled bounded excerpts.
- Page action returns leading text excerpts up to 6,000 characters, not a synthesized summary, full-site crawl or persistent memory ingestion. Dynamic/paywalled pages may yield little text. Search results are untrusted data, not execution instructions or verified live prices. Removed raw provider exception/query logging and unbounded direct-DDG HTML fallback.
- Flight helper no longer fabricates routes, airport codes, carriers, durations or dates. Produces a search link, never a reservation; browser launch is opt-in and its reported success is not proof of page load. Legacy helper list return shapes remain compatible with background monitoring; rich public reports retain diagnostics that list-only helpers cannot express.
- Offline verification: **259 tests passed**, including **31 new web cases**; one upstream Starlette warning. Tests mock downloads/providers/DNS/browser behavior. No live websites, model calls, real TLS sessions or desktop browser launches were tested. Earlier compilation/type-check totals refer to their respective batches, not a whole-app runtime guarantee.


## File-operation safety (implemented)

### Transfers and organization

- Move/copy/rename refuse existing targets (including dangling symlinks), never merge directories, recheck the final path when the destination is a directory, and reject symlink/junction path components and paths outside configured safe roots. Rename accepts a single filename, not a path.
- Transfers are deliberately limited to regular files up to **64 MiB**, with an existing destination parent. Directory transfers are disabled. Same-volume move/rename uses atomic no-clobber hard-link creation followed by unlink; unsupported filesystems/cross-volume moves fail without an unsafe fallback. This is not an atomic rename: interruptions can leave both links. Copy uses exclusive destination creation and bounded streaming; mode/timestamps are not preserved by copy.
- `dry_run=true` previews move/copy/rename without creating paths or undo records; default for these single-file operations remains false. It is a point-in-time check, not approval or a reserved plan. Unsupported actions reject any supplied `dry_run` rather than accidentally executing a supposedly previewed operation.
- `organize_desktop` now defaults to preview. Set `dry_run=false` to apply a newly computed plan. Hidden files, symlinks and directories are skipped. More than 500 directory entries causes refusal before mutation. Conflicts/failures are listed individually; execution is best-effort, **not transactional**. Successful transfers are journaled even if later files fail. Undo is one batch, reports restored/conflicted counts, and removes only newly created, still-empty category folders.
- Transfer undo captures inode/device, size, mtime, mode and SHA-256 after the change. Missing, edited or replaced targets and occupied original paths are refused, not overwritten. Changed entries remain in place. Undo history remains session-only, ten entries; an attempted undo consumes its entry even on conflict (existing shared stack semantics).

### Create/write undo

- Create now uses exclusive creation and refuses overwrite. Text input capped at 1 MB. Write/append require existing and resulting data at most 1 MB; previous content is preserved as exact bytes rather than lossy decoded text. Larger writes are refused rather than executed without a usable undo snapshot.
- Undo for create/write/download checks the post-operation target fingerprint; later edits/replacements are left alone. Folder-create undo checks identity and still requires an empty directory. Files too large to snapshot safely produce an explicit unavailable undo rather than deleting unchecked content.
- These guards are **not a filesystem security sandbox**. A shared in-process lock serializes this batch's transfers/writes/undo, not other processes or all legacy operations. External mutations can race validation and I/O. Write/append and its restoration still write in place: disk/process failure can leave partial content. Automatically created parent directories are not included in create/write undo. No native trash restore, power-loss recovery, adversarial concurrent-process stress, Windows/macOS filesystem behavior or real personal files were tested.
- Legacy delete/trash restore, read/list/largest and folder creation were not redesigned in this batch. Download transport/publication was still legacy at this point, but is superseded by the download-safety batch below. Do not treat the entire file tool as hardened because individual paths improved.

### Verification

**293 tests passed**, including **34 new temporary-directory file-operation cases**, with one upstream Starlette warning. Covered transfer/undo, dry runs, name conflicts, later edits/replacements, occupied origins, invalid rename paths, symlink targets/category folders, directory refusal, unsupported/cross-device link failure, destination-creation race, size limits, partial organization journaling, category ownership and byte-exact write restoration. Focused Ruff and mypy checks pass for `ultron/core/file_safety.py` and `ultron/actions/file_controller.py` (Ruff also covers the new tests). No enhancement commits made.


## Download safety (implemented)

- `file_controller` download now uses a separate bounded binary receiver with the shared public-HTTP(S) validation, public-only DNS answers, pinned numeric-IP connections, original-host TLS verification, no environment proxies, and DNS validation on every redirect. Only standard ports, no embedded credentials, no private/loopback/link-local destinations, maximum three redirects; HTTPS downgrades refused.
- **16 MiB hard body cap**, **20-second logical caller/network budget**, connect up to three seconds and reads up to four seconds. No automatic retries or resume. Accepts binary data but rejects HTTP content compression, ambiguous framing, malformed/oversized Content-Length, non-200 responses and mismatched lengths. A gzip/zip *file* sent without HTTP Content-Encoding remains ordinary binary data; nothing is unpacked.
- Network work shares the four-worker cap with web research and returns bounded in-memory bytes, never filesystem writes. Timed-out DNS/SDK/socket work cannot be forcibly killed and may retain its worker slot/buffer until it ends, but **cannot publish a late download**. Simultaneous completed downloads also temporarily allocate buffers; this is not a total process-memory guarantee. The network caller deadline does not bound disk flush/publication time.
- Requires an **existing destination directory** under allowed roots, with no symlink/junction components. Destination-file arguments and automatic directory creation are no longer supported. Explicit name wins; otherwise use the original URL's decoded last path segment or `downloaded_file`. Server Content-Disposition names and redirect-path names are deliberately ignored, so a server cannot silently change the chosen target.
- Filename validation rejects traversal, separators, Windows-invalid characters/device names, controls/format characters, trailing dot/space, and names over 180 UTF-8 bytes. Existing destinations, including dangling links, are refused; there is no silent overwrite or automatic numbered suffix. Supply a different explicit name when needed.
- Completed data is staged privately in the destination directory, flushed/fsynced, then published by an atomic no-clobber hard link. On POSIX the final file inherits staging mode 0600 (not executable); Windows permissions depend on platform semantics. Unsupported hard-link filesystems fail closed; no overwrite-prone fallback. Staging files are removed on ordinary failure/success. Cleanup failure after publication reports **saved with a warning** and registers undo, rather than falsely reporting an absent download.
- Undo uses the existing conflict-aware fingerprint: later edits or replacement files are not deleted. No downloaded file is opened, executed, extracted or malware-scanned. Content length is a framing check, not a cryptographic integrity/authenticity check; HTTP remains unencrypted when explicitly requested. The result includes UTC retrieval time; signed source URLs are not logged in provider errors.
- Limitations: path checks are not a sandbox against adversarial concurrent local processes. Process/OS interruption may leave private `.ultron-download-*.part` files, including a second hard link after publication; no startup cleanup or crash-atomic undo journal is provided. Directory entries are not fsynced, so this is not a power-loss durability guarantee. Download retries are explicit user actions, not automatic.
- Verification: **340 tests passed**, including **47 new offline download cases**, one upstream Starlette warning. Covered binary/empty bodies, names, credentials/private URL rejection, redirects/DNS revalidation, byte/framing limits, interrupted streams, destination races, busy workers, caller timeouts with no late publication, disk flush failure, staging cleanup warnings, POSIX permissions and conflict-aware undo. All network behavior is mocked; no live downloads, real TLS sessions or native Windows/macOS filesystem behavior tested. Focused Ruff/mypy and repository runtime-failure lint pass; **110 Python files compile in memory**. All enhancements remain uncommitted.


## Tool observability (implemented)

### Shared dispatch telemetry

- `ActionRegistry.run` and `PluginRegistry.run` now share a thread-safe observer. Every finished dispatch records kind, validated tool name (or `unknown`), monotonic elapsed milliseconds, UTC finish timestamp and a stable outcome code. Only the **last 100** events are retained, with fixed-size per-code counters and an active-dispatch count. All state is in process memory and resets on restart; there is no new disk log/database or network export.
- Stable codes: `HANDLER_RETURNED`, `TOOL_EXCEPTION`, `DEPENDENCY_MISSING`, `INVALID_ARGUMENTS`, `UNAVAILABLE`, `DISABLED`. Uncaught Python import failures are categorized as dependency-missing; it is not a complete native-dependency diagnosis. Other thrown handler errors indicate a potentially partial/unknown effect—no automatic retry occurs.
- **No success inference from free-form text.** Legacy handlers that catch failures and return strings still produce `HANDLER_RETURNED`. Likewise confirmation requests and queued work count as returned; subsequent approval/background execution is not timed. Handler output remains unchanged for successful returns, including the existing `None`/empty-string `Done.` compatibility behavior. Error returns from the dispatcher now include stable codes and deliberately omit raw exception details.
- Logger failures cannot mask a result or invoke the handler twice. Parameters must be dictionaries before the registry invokes a handler; this is shape validation, not per-tool JSON-schema validation. Unknown/malformed names are sanitized in telemetry/error replies. Metadata does not include arguments, results, raw exception messages, file paths or credentials. Tool names/timings themselves remain visible to callers; this is not an authenticated admin interface.

### Read-only diagnostics

- Added auto-discovered `tool_status`: `section=summary|recent|dependencies|registry`, optional `limit=1..100` (default 20). Registry state distinguishes registered/rejected action records and enabled/disabled/rejected/configuration-unknown plugins, capped at 200 entries each. Main startup binds the live registries; direct library users see `not_bound` until explicitly bound. The diagnostic call itself appears active while it builds its snapshot and is recorded only after it returns.
- Fixed allowlist dependency checks use top-level module discovery and executable PATH lookup only. No provider module imports, shell commands, network probes, credentials inspection, installation or repair. Reports presence/missing/unknown—not importability, compatible versions, permissions, native platform support or successful service connectivity. Missing optional/platform-specific packages need not be errors. These checks do not claim to cover every dependency used by every tool.
- Action/plugin discovery now omits raw import exception text/tracebacks while retaining validated missing-package/helper hints for plugins. Main's generic sync/async tool-dispatch console lines and task-detail fields no longer interpolate arguments or returned content. Sync unknown-tool fallback no longer falsely says it executed something.
- **Scope limits:** inline core tools, direct helper invocations and later worker/approval callbacks are not measured. This is not a whole-application privacy scrub: individual tools, model/chat transcripts, existing audit logs, content panels and other main/UI exception paths can still contain sensitive data. Existing plugin `_notify` runtime-crash messages are replaced by the shared metadata console event; no new GUI diagnostics panel was exercised. No automatic timeout, cancellation, retry or background-work success tracking is added by observability.

### Verification and current aggregate

**370 tests passed**, including **30 new observability cases**, one upstream Starlette warning. Offline tests cover redaction, exception codes, context/empty-result compatibility, bounded immutable snapshots, active counters/concurrent dispatch, exact monotonic timing, broken log sinks, disabled plugins, discovery errors, local dependency-probe failures, registry status and diagnostic-tool discovery/dispatch. Focused Ruff and mypy pass for the four observability/registry modules; Ruff covers the new tests. Repository runtime-failure lint and patch-whitespace checks pass; **113 Python files compile in memory**. No live provider calls, full application/Qt startup, native dependency execution or GUI rendering was tested. All enhancement batches remain uncommitted.
