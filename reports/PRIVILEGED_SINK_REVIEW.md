# Privileged sink review — initial coverage and migration queue

## Scope

`PRIVILEGED_SINK_INVENTORY.csv` contains 837 static call-site leads across actions,
core, plugins, main/UI and dashboard. Reproduce from the repository root:

```sh
python scripts/audit_privileged_sinks.py > reports/PRIVILEGED_SINK_INVENTORY.csv
```

The script parses ASTs only: no application imports or native/provider calls. It
records file/line/enclosing function/category/callee, not code arguments or secrets.
Every row is deliberately `unclassified_manual_trace_required`: a grep/AST match
cannot prove authorization. Many rows are harmless reads, internal writes or false
positives; aliases, wrappers, generated code strings, FFI, indirect calls and native
APIs can be missed. This is a starting inventory, NOT a complete effect graph,
837 vulnerabilities, or a claim that all callers/sinks are covered. Line numbers
are snapshot evidence and should be regenerated after code changes.

## Manually traced high-priority groups

| Group | Entry/effect chain | Current scoped status | Next review |
|---|---|---|---|
| Developer project builder | dev_agent → former build/write/install/run/fix loop | Changed this batch: project-plan draft only, exact-content single-use save approval; no project creation/install/run/editor launch | If restored, separately authorize immutable source tree, environment and execution with OS isolation |
| Coding helper | code_helper → former arbitrary _save_file/_run_file/screenshot and iterative builds | Changed this batch: source proposals/explanations; exact-content inert .txt draft saves; selected-file reads require host roots; run/build/capture disabled | Safe source promotion/overwrite needs explicit destination/content-conflict handling; not implemented |
| Source draft sink | code_helper/dev_agent → source_drafts.request → policy grant → _save | Approval bound to immutable full content; consume at sink; fixed host draft directory, exclusive .txt, no auto-discovery or execution | Local filesystem races/concurrent capacity, trusted-host ACLs and retention are not sandbox guarantees |
| Shell | system_command → confirmation → _run_command | Prior batch requires all commands approved; metadata-only new audit records | Account-privileged shell and configured helpers remain unisolated; direct arbitrary Python is outside trust boundary |
| Process termination | process_manager → snapshot → policy request/consume → psutil.terminate | Prior batch exact identities, bounds/revalidation, no force-kill | Other modules' independent signal/process-control paths need tracing |
| Generated module loading | self_evolution → review-only source_drafts directory (separate legacy draft implementation); desktop generated task path | Prior batch execution disabled; legacy installed modules not retroactively removed | Registry/plugin auto-discovery still imports trusted host-installed code |
| Android | android_bridge dispatcher → reboot_device/install_apk/flash_partition/run_shell → subprocess | Shell/reboot now use exact-content single-use grants, explicit local ADB transport and executable revalidation; dedicated flash/EDL/sideload disabled | Single-file push/pull/install and single-frame screenshot now migrated; Finite view-only mirroring is now scoped; Selected-field telemetry is now scoped; discovery remains separate. Approved shell is full privilege, not a firmware sandbox |
| GUI input | ghost_pilot public handler/helpers → desktop_motion → pointer only | Partial, narrowed | Single-use approval + bounded pointer steps/geometry, Windows held-input guard, owner lock/cancel/shutdown; blind typing/click/app/search disabled. Races/hover remain; no native certification or global GUI coverage. See DESKTOP_POINTER_SAFETY.md |
| IoT/lockdown | iot_overlord → iot_lighting approved fixed single-light POST | Narrowed; legacy bundled effects disabled | Exact endpoint/entity/settings approval, config revalidation, HTTPS private-IP/no-proxy/no-redirect transport. Sentry and IoT/macro lockdown disabled; native/physical verification and future capture lifecycle remain open. See IOT_LIGHTING_SAFETY.md |
| Filesystem | file_controller create/write/delete/transfer/undo; desktop organize/clean; downloads | Existing roots, checks and individual gates vary; no blanket approval assertion | Trace all mutations and undo callbacks; exact destination and source preconditions; no overwrite/recursive escalation by inference |
| Git | git_sentinel → _run_git; macros/developer shell paths | Separate from system_command gate | Audit config helpers, hooks, add/commit/push effects and credentials; no automatic authorization inheritance |
| Browsing/capture/communication | browser_control/web_autopilot, screen paths, plugins, main inline tools, dashboard/phone bridges | Earlier migrated sinks have scoped protections; unreviewed paths remain | Follow actual reads, uploads, callbacks and external sends; transport/model context is a privacy effect too |

## Compatibility changes in this batch

- `dev_agent` is now a review-only project planner. Its old broad approval could
  not show generated source/dependencies/run commands, so it no longer builds,
  auto-installs missing modules, opens editors or iteratively runs/fixes projects.
- `code_helper` write/edit/optimize generate proposals in memory; approval saves
  inert `.txt` to `~/.ultron/review_drafts`, never an arbitrary output_path or the
  original source. Explicit arbitrary output paths are rejected, not ignored.
- `explain` returns an unverified model explanation without saving. `auto` uses
  deterministic structural selection (source → explain; otherwise → write), never
  model-selected permission escalation. Explicit file inputs require host document
  roots and bounded regular UTF-8 reads; these reads expose source to the configured
  model. Inline source is explicitly supplied model input. Prompt wrapping is not
  a prompt-injection security boundary.
- Legacy execution/write/install helper names either fail closed or were removed;
  they do not retain an alternate build loop. Tool names/public argument conventions
  remain discoverable, but old execution behavior intentionally does not.
- Draft content is not safety-certified. It can still contain malicious instructions
  or code: do not copy it into trusted/autoload locations or run it without review.
  A failed write may leave an inert partial `.txt`; uncertain writes are not retried.
- There is no OS sandbox, global permission broker, dependency environment manager,
  universal audit, atomic filesystem sandbox, or native/provider certification here.

## Validation

693 tests passed, one existing Starlette warning. Twenty new developer/draft tests
use fake model responses and isolated files; no dependency installs on behalf of
a generated project, native effects, screen capture or generated execution. Targeted
Ruff and diff checks clean. WAKE_MODEL remains hey_jarvis. No commit or push.


## Android continuation

Refreshed the AST inventory after Android changes (still 826 call-site leads).
Shell/reboot effect sinks now consume exact grants and recheck explicit serial,
transport and binary identity; no first-device/fastboot fallback. Flash and
EDL/sideload reboot paths fail closed. This is not cryptographic identity or OS
isolation, and approved shell may still modify firmware/data. Other Android
features remain outside the migration. Added 28 fake-ADB tests; current full
suite 721 passed, one existing warning; targeted Ruff/diff clean. No real ADB,
fastboot, phone reboot/flash/shell, commit or push.


## Android single-file continuation

Push/pull/APK install now use scoped exact-content grants and explicit device
identity, host-root local files, private approved-byte staging, explicit replacement
flags, bounded checked pull and no-clobber local publication. Remote push creates
a fresh operation directory and checks SHA readback when available. See
ANDROID_FILE_OPERATIONS.md for design/tests/residual risks and PRIVILEGED_SINK_TODO.md
for the current queue. Refreshed static snapshot now contains 835 leads (not a
coverage/vulnerability count); earlier sections describe previous snapshots.
Forty new tests, full suite 761 passed, one existing warning. No physical device
operations, signing/malware certification, OS sandbox, commit or push.


## Android screenshot continuation

Single-frame screenshot capture now uses explicit-device/exact-new-file consent
and a sink grant, bounded unknown-length receipt (15s/16MiB), structural PNG/CRC/
dimension checks and exclusive publication. No automatic upload/display or model
image context. Animated/invalid/partial images fail closed; this is not pixel
decoding or complete image-safety certification. Manual retention, no encryption,
host/ADB filesystem races and native validation limits remain. Mirroring/telemetry
are still legacy. Refreshed static inventory: 834 leads, not complete coverage.
Added 23 tests; full suite 784 passed, one existing warning. No real screen/device
capture, commit or push. PR preparation was stopped before any commit/push.


## Android mirroring continuation

Migrated mirror launch to exact host approval, ADB/scrcpy snapshot revalidation,
view-only/no-audio/no-clipboard/no-power-on flags and 5–300s requested lifetime.
New owned service tracks only its Popen/session ID, one live owner/process,
watchdog/stop and bounded shutdown; failed stop retains slot. Stale IDs/watchers
cannot kill a newer or unrelated session. Idle shutdown blocks late approvals.
Main shutdown attempts mirror cleanup before jobs even after mirror errors.
Serial-based native selection is not transport locking/cryptographic identity;
crash-surviving children, native versions and auxiliary dependencies remain outside
certification. See ANDROID_MIRROR_LIFECYCLE.md. Refreshed inventory: 837 leads,
not permission coverage. Full suite 811 passed; 26 new mirror tests and successful/
failing isolated shutdown integration variants. No scrcpy/ADB/phone calls, commit
or push. Telemetry remains next; broader GUI/IoT/file/Git work is still open.


## Android telemetry continuation

Explicit selected-device/model-disclosure consent for info/battery/telemetry.
Fixed allowlisted queries; default excludes storage/IP, immutable field selection,
64KiB/5s per-query receiver bounds and 20s query-issuance budget (not a hard total
deadline). Device changes discard whole result; failed/malformed fields unavailable,
no raw dumps or fabricated zeros. Adapter does not persist values; existing UI/log/
model consumers may. Discovery is still a separate legacy listing path. Thirty
new fake tests, full suite 841 passed, one existing warning; no device/provider
calls, commit or push. See ANDROID_TELEMETRY.md. Static inventory still 837 leads,
not full permission coverage. GUI-input boundary is next P0 workstream.

Latest scoped batch: IoT/sentry narrowed, 53 new fake tests; full suite 940 passed with existing warning. No live-provider or physical validation; global permission coverage remains incomplete.

## Scoped file transfer / session undo migration

Move/copy/rename now reach approval-consuming core.file_safety sink with exact source fingerprint, destination and immediate parent identity checks; copy stages before publication. Generic session undo binds/consumes one exact immutable entry, fails on changed stack, pops before callback and does not claim unconditional reversal. Bulk organization/clean disabled in file_controller and desktop; file_controller bounded preview retained. 30 new temp-file/fake-consent tests; full suite 970 passed (existing warning). **Create/write/append/overwrite/delete/Trash restore/download publication and direct legacy inverse helpers remain unmigrated P0 work.** See FILE_TRANSFER_UNDO_SAFETY.md for all race, lifecycle, callback trust and compatibility limits.

## Small-file create/write/append / one-level folders

Scoped effect sink now consumes exact content/target/parent approval, revalidates vacancy or existing identity, stages/fsyncs and publishes without destination cleanup after uncertain failure. 16000-byte before/after cap; existing replacement changes metadata/hardlink semantics and is not atomic CAS. Separate exact-entry inverse verifies published fingerprint/parent, restores previous bytes or removes unchanged new file/empty directory. Direct legacy _undo_write disabled; delegated helper requires consumed grant context. 40 new temp-file tests; full suite 1057 passed. Delete/Trash restore/download and legacy download inverse remain open, as do unrelated writers/global permission graph. See FILE_WRITE_SAFETY.md.

## Scoped native Trash submission

file_controller delete/_safe_trash now reach core/file_trash approval-consuming sink; exact fingerprint/hardlink-count/parent/root/backend revalidation and one native call only. Regular files <=64 MiB, no directories/permanent-delete fallback/retry. Former name/path-based COM UNDELETE removed; restore disabled and no automatic undo registration without stable native receipt. Source absence is not recoverability proof. 30 fake-only tests; 1087 full suite passed (existing warning). Native certification/global deletion graph remain open; downloads publication next. See FILE_TRASH_SAFETY.md.

## Scoped two-stage downloads

file_controller download now routes to separate immutable URL receipt and exact received SHA256/size/path save approvals, destination/parent/root rechecks before/after network and publication, no redirects, guarded receive worker and publication, private verified staging and exact-entry inverse. Old raw _undo_create disabled. 22 new fake/temp tests; 1109 full suite passed, existing warning. Network late workers cannot publish; receipt memory/timeout/native races/retention limits and remaining unrelated file/network producers documented in DOWNLOAD_CONSENT_SAFETY.md. Git/macros/plugins/inline sinks next; global coverage still incomplete.

## Git inspection narrowed + release versioning

Git Sentinel exact-plan fixed local inspection now gates process sink and independently rejects noninspection vectors, with root/config/binary checks and known-helper suppression; raw/mutation/remote helpers disabled. 33 fake tests. Other subprocess/Git/macros/plugins/inline paths remain uncovered. Added single-source release metadata/CLI/changelog and developer preview/check/write-only version helper (20 tests), no Git/release automation. 1162 full-suite passed with existing warning. See GIT_INSPECTION_SAFETY.md and docs/VERSIONING.md; no native/whole-app certification.
