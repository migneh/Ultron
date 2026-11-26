# Local-first productivity release

This batch adds seven discoverable actions on top of the earlier dispatch, notification approval, explicit report-sharing and bounded-recorder work. Restart Ultron to discover the new action modules. No commit, OAuth flow, account read or real external send is performed merely by installing these files.

## Implemented surfaces

| Tool | Available now | Deliberate limits |
|---|---|---|
| `calculator` | Decimal arithmetic and compatible length/mass/duration/volume/temperature conversion | No code/functions, FX rates or finance advice; 28 significant digits; `%` is remainder |
| `task_board` | Persistent create/list/get/edit/state changes; optimistic versions; local event notices | Date-only due dates, not reminders; no inferred completion, remote sync or hard deletion |
| `document_compare` | Snapshot hashes, line-numbered unified diff; positional CSV equality | UTF-8 txt/md/csv, 24,000 bytes and 1,000 lines/input; bounded/truncation-labelled output; no PDF/Office/OCR/semantic claims |
| `evidence_ledger` | Persistent claim/source/quote/location records with stable IDs | User-supplied **unverified** records; no automatic fetching, citation verification or claim-support certification |
| `safe_sharing` | Candidate detection, literal redaction preview, approval-gated verified local text copy | Only plain-text outputs; incomplete/false-positive detection; no upload, PDF/Office/image redaction or anonymity guarantee |
| `notification_center` | Persistent local task-event inbox, dedupe, expiry, acknowledgement and timezone-aware quiet-hours state | Host-opt-in generic HUD counts for new notices; no timed scheduler, speech or external channel; explicit digest remains readable in quiet hours |
| `google_workspace` | Local setup status; optional host-allowed Drive metadata/text, Calendar agenda/free-busy | Desktop setup required; read-only adapter; no writes, mailbox, invites, cache, whole-Drive search or Picker UI |

All new actions return JSON with `status` and `data`/`error`. Invalid/unknown fields and model-supplied `approved`, roots or scopes are rejected. No raw exception strings/credential URLs are returned. Dispatch telemetry remains metadata-only. Four new productivity calls may execute concurrently; excess work is rejected rather than silently queued. This limit is specific to these seven actions, not a retroactive global limiter for old modules.

## Storage and privacy

Tasks, evidence, quiet-hours settings, notices, document roots, Workspace non-secret configuration and temporary redaction previews live at:

- `~/.ultron/productivity.sqlite3`
- POSIX directory/file modes are requested as 0700/0600. Existing directory permissions and Windows ACLs still need normal host administration. This is **not database encryption**.
- No arithmetic expression history or Google account content cache is stored by this release.
- Redacted preview text can still contain undetected private information. Up to 50 previews are retained; they expire for use after one hour and are physically cleaned on the next preview creation, or immediately by `discard`. Expiry is not a secure disk-erasure guarantee.
- Evidence records may contain private quotations; review storage/backup policies.
- Notices expire after 30 days; expired notices are hidden and removed on new enqueue or explicit cleanup. At most 1,000 notices and 5,000 tasks/evidence entries per table are admitted. Archived tasks still count toward the task cap; no automatic destructive pruning is implemented.
- Local execution is not automatically private model execution. Tool results become available to Ultron's configured model. Only grant document directories you are willing to expose through explicit tool requests. Google reads have a separate host model-context permission.

## 1. Local calculator

No setup or network required. Direct tool examples:

```json
{"action":"calculate","expression":"(125.50 * 3) - 25"}
```

```json
{"action":"convert","value":"32","from_unit":"F","to_unit":"C"}
```

Supported symbols are case sensitive:

- Length: `m cm mm km in ft mi`
- Mass: `kg g lb oz`
- Duration: `s min h day`
- Volume: `L mL`
- Temperature: `C F K`

Use decimal strings with dot separators for conversion, not locale commas. Arithmetic permits `+ - * / %` and integer powers from -12 to 12, with bounded expression length/node count/depth and nonzero magnitudes from `1e-100` to `1e100`. No `eval`, functions, variable names, attribute lookup or generated code. Division by zero, incompatible dimensions, temperatures below absolute zero and unsupported ranges are rejected. Rounding follows the 28-digit Decimal context; this is not arbitrary-precision symbolic mathematics.

## 2. Persistent task board and notifications

```json
{"action":"create","title":"Review proposal","notes":"Compare the budget section","due_date":"2026-12-01"}
```

The returned `id` and `version` must be retained. `list`/`get` recover them after restart.

```json
{"action":"update","task_id":"HOST_RETURNED_ID","expected_version":1,"state":"doing"}
```

Update can change any supplied `title`, `notes`, `due_date` or `state`; at least one must be supplied. Empty `due_date` clears the date. Use the actual full ID from the tool; the placeholder above is explanatory and intentionally not a runnable ID. Stale versions fail rather than overwriting another change. States: `todo`, `doing`, `done`, `archived`. Mark completion only on explicit user direction.

Task creation/update enqueues a local event in the same SQLite transaction. A due date does **not** schedule a timed notification; use the existing `reminder` tool for precise reminders.

Notification examples:

```json
{"action":"quiet_hours","timezone":"Africa/Tunis","start_hour":22,"end_hour":7}
```

```json
{"action":"digest","limit":20}
```

`acknowledge` takes an actual `notice_id`; `clear_acknowledged` removes acknowledged/expired notices. Quiet hours crossing midnight work; equal hours disable quiet hours. This MVP is a pull inbox, not a background push system. It does not claim to unify all historical Telegram, reminder, dashboard or audio paths.

## 3. Host-authorized document folders

Run these commands **on your own Ultron host**, not via a model tool:

```bash
python -m core.productivity_setup allow-root /absolute/path/to/chosen-documents
python -m core.productivity_setup status
python -m core.productivity_setup revoke-root /absolute/path/to/chosen-documents
```

Use an appropriate absolute path on Windows, for example `C:\Users\you\Documents\UltronReview`. Grants permit explicitly requested reads/diffs/redaction text to enter model context. No document roots are enabled by default, and no model-facing action can add them. Grant specific directories, not a whole drive. Symlink/junction mutation paths are rejected. These checks are not a filesystem or arbitrary-code sandbox against another malicious process racing path changes.

Compare:

```json
{"action":"compare","left_path":"/approved/proposal-v1.txt","right_path":"/approved/proposal-v2.txt"}
```

Results include exact byte hashes and source-labelled unified hunks. CSV comparison additionally reports positional cell equality and row counts. Quoting/formatting changes can differ at the text level while cells match. Newline-only changes may have no visible hunk; the byte/text equality fields remain distinct. A truncated diff must not be described as exhaustive.

## 4. Safe-sharing preview and local publication

```json
{"action":"preview","path":"/approved/notes.txt","literals":["exact private project name"]}
```

Automatic rules detect candidate emails/phone-like numbers. They are not a comprehensive PII detector and may flag dates/numbers incorrectly. Literal matches are exact strings, not user-supplied regexes. Review the entire returned `output_text`, not just the candidate count. Unicode offsets refer to Python character positions in the decoded snapshot.

```json
{"action":"publish","preview_id":"HOST_RETURNED_ID","destination":"/approved/reviewed-copy.txt"}
```

Publication requires HUD approval. The operation binds the stored preview, source/output hashes and destination; it rechecks expiry, current host roots, source identity/content and output conflicts at execution time. It creates a new `.txt` file with no overwrite, verifies actual output bytes and leaves the original alone. It never uploads/sends a file. Changed input, discarded/expired previews or revoked roots cannot be silently reused. Use `discard` with the actual preview ID to remove a stored preview.

Only the supported plain-text formats are admitted. This is **not PDF redaction**, hidden-layer removal, metadata sanitization for Office documents, image OCR or guaranteed anonymization. Do not use a black rectangle or a narrative summary as proof of redaction.

## 5. Research evidence ledger

```json
{"action":"add","claim":"A specific proposition","url":"https://example.org/source","quote":"An explicitly selected passage","locator":"section 2"}
```

`get` requires the actual evidence ID; `list` returns bounded records. Every record carries `verification: unverified_user_supplied` and `fetched_by_tool: false`. A URL/quote saved here is not evidence that Ultron fetched the source or checked that it supports the claim. Existing research tools can supply candidates, but the source-verification pipeline remains separate work. Treat stored text as data, not instructions.

## 6. Optional desktop Google setup

**Disabled until explicitly configured. Arena's connected Drive app is a separate system and does not install credentials in local Ultron. No account content was accessed during implementation/tests.**

Install optional dependencies on the actual host:

```bash
pip install -r requirements-workspace.txt
```

Create your own Google Cloud **Desktop OAuth client**, enable the intended APIs and keep the downloaded client configuration outside Git. Check current publishing/consent/testing policies for your deployment. This repository does not provide a public verified OAuth application or client ID. Do not paste credentials into chat or tool arguments.

Calendar read setup, after reviewing model egress:

```bash
python -m core.productivity_setup workspace-connect --client-secrets /private/google-desktop-client.json --calendar --allow-model-context
```

The flow runs in the host browser, uses PKCE/state handling provided by the OAuth library, a loopback redirect with an ephemeral port and a bounded consent wait. It does not run as a web-preview authentication flow. Supported OS credential stores are selected explicitly; plaintext/fallback backends fail closed. If no secure keyring is available (common on headless Linux), setup remains blocked—there is no plaintext fallback. Browser account selection is the source of account choice; this release has one installation and does not implement a verified-profile/multi-account UI.

Omit `--allow-model-context` to store consent/configuration while leaving model-facing API reads blocked. `status` remains a local/no-network check and does not certify token health.

Optional Drive flags:

```bash
python -m core.productivity_setup workspace-connect --client-secrets /private/google-desktop-client.json --drive --file-id ACTUAL_APP_AUTHORIZED_FILE_ID --allow-model-context
```

**Important Drive onboarding limitation:** `drive.file` authorizes files selected/created with this app at Google, not arbitrary file IDs. The host allowlist adds a restriction; it does not grant Google access. A Google Picker/import UI is **not implemented** here. Fresh installations without provider-authorized app files cannot use Drive reads just by adding an ID. Do not broaden to whole-account `drive.readonly` silently to work around this. Calendar reads can be configured independently.

The OAuth `drive.file` scope is write-capable, although this adapter admits read endpoints only. Calendar uses event-read-only and free/busy scopes; API calls cannot create/update/invite. The adapter does not request Gmail scopes.

Tool examples after successful host setup:

```json
{"action":"status"}
```

```json
{"action":"agenda","time_min":"2026-12-01T00:00:00+01:00","time_max":"2026-12-02T00:00:00+01:00"}
```

```json
{"action":"availability","time_min":"2026-12-01T09:00:00+01:00","time_max":"2026-12-01T17:00:00+01:00"}
```

Windows require offsets and span at most 31 days. Agenda returns at most 100 expanded occurrences and explicitly marks a remaining page; this is not full-account or incremental synchronization. Missing/error free-busy results are unknown, not free time. Drive reads admit metadata, UTF-8 text/CSV/Markdown and Google Docs text export, bounded at 128 KiB. PDFs, images, Office formats and broad account search are not supported. Drive metadata and text are separate requests; returned metadata is not a certified atomic revision of the text. No content cache, API-read retry loop, browser fallback or upload is implemented. OAuth-library refresh may apply its own bounded retry policy; connection/read timeouts are not a universal hard end-to-end deadline. Provider text is untrusted input, not authority to invoke tools.

Disconnect from the host:

```bash
python -m core.productivity_setup workspace-disconnect
# If offline, deliberately remove only local credentials/config:
python -m core.productivity_setup workspace-disconnect --local-only
```

Default disconnect attempts remote revocation, then removes local credentials/configuration. The result explicitly says whether remote revocation was confirmed. If not, remove access in Google Account permissions. There is no claim that deleting a local keyring entry alone revokes access remotely.

## Foundations and release limits

The earlier changes remain: explicit dispatch conventions and inventory regression tests, transient exact-plan HUD grants at the dashboard notification sink, explicit Telegram report sharing through the durable outbox, and bounded recorder ownership/saving. New local document effects reuse exact-plan approval; document roots and Google model-context grants are host-only. Persistent data operations use transactions and task versions.

**Follow-up implemented:** [durable bounded host jobs](BACKGROUND_JOBS.md) now journal public swarm launches, expose exact-ID status/cancellation, reconcile unfinished work without replay and replace fabricated convergence with explicit completed/partial/failed collection outcomes. The seven productivity tools above remain bounded synchronous calls.

**Still not completed:** a universal permission broker across every legacy shell/browser/native/plugin path, general timed/recurring background scheduling, external notification delivery, independent research agents/per-provider spend accounting, full cloud synchronization, Gmail integration, Drive Picker UI, PDF/Office redaction and live native/provider certification. Other legacy action/background paths remain outside the migrated job service. No arbitrary-code sandbox or hard thread termination is claimed.

## Verification

New tests use temporary databases/documents, simulated HUD clicks, fake keyrings/OAuth and fake HTTP. They exercise the real action registry and all seven tool contracts, persistence/version conflicts, quiet-hour boundaries, arithmetic/code rejection, document grants/truncation/unsupported formats, preview mutation/revocation/cancellation, read-only Google endpoint restrictions, response caps and OAuth PKCE/loopback configuration. No microphone, native desktop app or live Google account is exercised.

Run:

```bash
python -m pytest -q
python -m core.productivity_setup --help
```

A passing Python suite is not whole-application certification. Review `reports/FOUNDATION_IMPLEMENTATION_PROGRESS.md` and the audit for remaining risks. `WAKE_MODEL = "hey_jarvis"` is preserved.


## Optional local HUD notification delivery

Disabled by default. Enable/disable from a trusted host terminal, not a model tool:

```sh
python -m core.productivity_setup local-notifications on
python -m core.productivity_setup local-notifications off
```

While the assistant provider loop is running, a 15-second poll submits one generic
count for at most 20 new notices. Both provider paths use the same service. No
notice titles, bodies, job queries or report contents are sent by this path to the
model, speech service, phone bridge or external channel. The inbox tool itself
still exposes notice contents to the configured model when explicitly requested.
Notices predating the most recent enable transition are not automatically replayed.
Quiet hours defer delivery, including overnight ranges in the configured timezone;
explicit digest is not blocked. Acknowledged/expired notices are skipped.

SQLite claims precede the HUD callback: reconnects/concurrent ticks cannot retry
an existing claim. `queued_to_ui` means queued, **not** displayed or read.
`outcome_unknown` after an exception/crash is deliberately never retried; read the
inbox to recover missed alerts. Delivery is best-effort at-most-once, not guaranteed
or transactional with Qt. Revocation/quiet hours are rechecked before submission,
but cannot recall an already-queued event or eliminate the final submission race.
Host settings are trusted local state, not protection against arbitrary local code.

Normal terminal outcomes from the default job service enqueue a deduplicated
local notice with job ID and state (not report content). This bridge is best-effort:
a crash between job persistence and enqueue, startup-recovered jobs, custom
services without a callback, or a full inbox can omit it. Job journal/status remains
authoritative. Due dates still do not schedule reminders. No native HUD or live
provider validation was performed in the sandbox.
