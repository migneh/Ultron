# Privileged-path TODO / acceptance tracker

Current full local baseline: 1162 passed, one existing warning. This is not native
or whole-app certification. No commit/push; wake word remains hey_jarvis.

| Priority | Workstream | Status | Next acceptance gate |
|---|---|---|---|
| P0 | Android push/pull/install | Scoped implementation complete; native validation pending | 40 new tests pass; exact device/content approval, bounded receipt, no-clobber publish; review residual risks in ANDROID_FILE_OPERATIONS.md |
| P0 | Android single screenshot | Scoped implementation complete; native validation pending | Exact device/new-file approval, bounded receive and structural PNG checks, exclusive local publication; 23 new tests |
| P0 | Android mirroring | Scoped implementation complete; native validation pending | View-only approval, requested duration, owned stop/watchdog/shutdown, concurrency and stale-ID protection; 26 new tests |
| P0 | Android telemetry | Scoped selected-field implementation complete; native validation pending | Explicit device/context approval, fixed bounded queries, changed-device discard; 30 new tests |
| P1 | Android discovery | Legacy listing path, separate from telemetry | Bound listing output and make local-server/binary/error handling consistent; no implicit authorization |
| P0 | GUI input / ghost_pilot | Partial, narrowed | Approved bounded pointer-only sink; direct blind typing/click/search/app-launch disabled; 46 fake tests. Native certification and target-verified keyboard/click adapter remain open; see DESKTOP_POINTER_SAFETY.md |
| P0 | IoT lockdown / sentry | Narrowed scoped lighting; bundled surveillance/lockdown disabled | 53 fake tests; explicit allowlisted light/HTTPS private IP and sink approval; no LAN probes, implicit workspace lighting or macro lockdown. Native/physical testing and future capture/retention/lifecycle remain open (IOT_LIGHTING_SAFETY.md) |
| P0 | File mutations / undo | Transfers, small writes/folders, exact-entry undo and single-file Trash and two-stage downloads scoped; native/global coverage open | 30 new temp-file/fake-approval tests; move/copy/rename sink approval, source/parent fingerprints, staged copy; bulk desktop apply disabled. Create/folder/write/append/overwrite now scoped with 16000-byte exact snapshot, staged publication and protected inverse (40 new tests). Single-file Trash approval now implemented (30 tests); automatic restore disabled, no stable item receipt. Download receipt/exact hash-size save approvals and private checked inverse now scoped (22 new tests), legacy raw create/download inverse disabled. Native Trash/receipt design, races, lifecycle and unrelated file producers remain open; see DOWNLOAD_CONSENT_SAFETY.md. See FILE_TRANSFER_UNDO_SAFETY.md and FILE_WRITE_SAFETY.md |
| P0 NEXT | Git/macros/plugins/inline tools | Git Sentinel narrowed to approved fixed reads; mutations disabled; other paths open | Trace helpers/hooks/direct calls/background callbacks; sink-level consent and explicit execution trust |
| P0 | Full permission coverage graph | Initial static inventory only | Manually classify leads, aliases/FFI and transitive paths; do not treat registry gate as universal |
| P1 | Durable private audit | Partial specialized records only | Lifecycle coverage, metadata privacy, retention, rotation and failure policy |
| P1 | Real execution isolation | Not implemented; generated execution disabled | OS-enforced filesystem/identity/network/resource limits, fail closed on unsupported hosts |
| P1 | Browser/network/capture safety | Partial migrated sinks only | SSRF/redirect/egress and source disclosure; screenshot/clipboard consent and retention |
| P1 | Legacy truthful outcomes | Partial | Weather, brightness, launches and remaining native simulations must distinguish submission/verification/failure |
| P1 | Native/live platform validation | Not completed | Opt-in tests on actual Windows/macOS/Linux/device/provider hosts, not mocked certification |
| P1/P2 | Platform expansion | Deferred behind safety | Tool routing evaluation, safe scheduler/reconciliation, constrained MCP, hybrid memory, independent-agent evaluation |
| Pending input | Uploaded review appendices | Missing | Obtain 10 appendices and README; only main report reconciled |
| Release | Cumulative integration/review | Pending | Review compatibility changes and final test matrix; commit/merge only with user authorization |

## Completed scoped migrations (not global guarantees)

Exact-plan operation primitive and selected document/sharing sinks; process
termination; all-command approval in system_command; Android shell/reboot and now
single-file transfer/install, single-frame screenshot and finite owned view-only mirroring; disabled dedicated flash/EDL paths; review-only
self-evolution/developer drafts; bounded durable jobs; opt-in generic local HUD
notices. Each path retains the documented trust/race/platform limitations.

## Latest GUI batch

Ghost Pilot narrowed to approved pointer-only motion; blind keyboard/click workflows fail closed. Full suite 887 tests; fake effects only. See DESKTOP_POINTER_SAFETY.md. IoT sink review is the next implementation batch; GUI target-verified adapters/native tests remain open.

## Latest IoT batch

Scoped single-light approval and config-bound HTTP sink; legacy raw service helper fails closed. IoT/macro lockdown and sentry effects disabled, no network discovery. Full suite 940 passed; 53 new fake-only tests. File mutations/undo next. See IOT_LIGHTING_SAFETY.md for provisioning and residual risks.

## Latest transfer/undo batch

Exact transfer sink approval and separate exact-entry undo approval; staged copy, no unsafe destination cleanup on uncertain move failure. Both desktop bulk organizers disabled (file-controller preview retained). 30 new tests; full suite 970 passed. Other create/write/delete/download producers remain open; this is not universal file permission enforcement.

## Runtime package migration and configurable wake model

Runtime sources now live under `ultron/`; historical source references map through docs/PROJECT_STRUCTURE.md. Wake model/threshold/label configurable via `python -m ultron wake-config`; default constant remains hey_jarvis. 47 new fake/model/package tests; full suite 1017 passed with existing warning. Wheel installed/CLI/resources checked outside checkout. Native GUI/audio/models/shortcuts/schedules still unverified. Remaining file mutation work stays P0 NEXT; reorganization is not permission-coverage completion.

## Latest small-file mutation batch

Create/one-level folder/write/append now request exact snapshot approval and revalidate at the sink; staged writes and separately approved inverse checks. Legacy direct _undo_write disabled. 40 new tests; full suite 1057 passed, existing warning. 16000-byte cap and metadata/replace race compatibility limits in FILE_WRITE_SAFETY.md. Delete/Trash restore/download publication remain P0 NEXT.

## Latest Trash batch

Exact snapshot-bound one-file native Trash submission, no permanent-delete fallback/retry; directories refused. Name/path-guess restore removed, no automatic deletion undo. 30 new fake-only tests; full suite 1087 passed with existing warning. Receipt/recoverability/native behavior not certified. Downloads publication/legacy inverse next; see FILE_TRASH_SAFETY.md.

## Latest download batch

Two-stage URL fetch and exact hash/size/path save approvals; no redirects, raw receipt/save guarded, staged publish and private exact-entry inverse. Legacy raw _undo_create disabled. 22 new tests; full suite 1109 passed with existing warning. Scoped file migrations are not global permission/isolation/native certification. Git/macros/plugins/inline effect tracing next. See DOWNLOAD_CONSENT_SAFETY.md.

## Latest Git and version-system batch

Git Sentinel approved fixed inspection (33 fake tests), all direct mutation/raw runner routes disabled; macros/plugins/inline and other subprocess producers remain NEXT. Version single source ultron/_version.py, CLI/package consistency, CHANGELOG and preview-first developer bump/check script (20 tests), no Git/release operations. Full suite 1162 passed with existing warning; native/platform/global safety gates remain open. See GIT_INSPECTION_SAFETY.md and docs/VERSIONING.md.
