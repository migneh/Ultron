# Android mirroring — consent and owned lifecycle

## Scope

`android_bridge` mirror/scrcpy/screen_mirror now request host approval for an
explicit device serial and a 5–300 second requested session (default 60). The
native tool shows live sensitive screen contents on the desktop. It deploys/runs
scrcpy's server on the phone; it is not a passive/no-effect device read.

| Acceptance | Implementation / evidence |
|---|---|
| No launch without consent | Immutable device/scrcpy/duration plan, grant consumed at `_execute`; headless/deny/replay/direct-sink tests |
| Stable preview identity | ADB executable/serial/transport and scrcpy binary fingerprint checked before launch; mutation tests |
| View only | `--no-control`, `--no-audio`, `--no-clipboard-autosync`, `--no-power-on`; no recording flags |
| Explicit local ADB | Explicit scrcpy serial; ADB binary and local server socket set in subprocess environment |
| Bounded request | 5–300s strict integer; native `--time-limit`, host watchdog, bounded termination waits |
| Owned process only | Retained Popen object; exact opaque session ID; never process-name/PID searches; stale-ID/watcher tests |
| Bounded concurrency | One active process per live owner; thread lock and OS owner lock; concurrency/busy/lock-refusal tests |
| Fail closed | No fallback to control/audio/recording, no automatic relaunch after native failure |
| Retain uncertainty | Failed termination retains slot and owner lock until exit observed; no claimed successful stop |
| Shutdown | Stops owned process, closes admission; even pending approval cannot start after idle shutdown |

## Interface

- `mirror(serial, seconds=60)`: request approval. Callback reports a generated
  `mirror_id` and process start, **not** proof of a rendered window/device stream.
- `mirror_status`: metadata of the current owned process or most recent exit;
  no native launch, image content or device probe. Not persisted across restarts.
- `mirror_stop(mirror_id)`: stop only that exact currently owned process. No new
  permission needed to reduce an owned display session. Invalid/stale IDs cannot
  target another session. Terminate then kill escalation applies only to this
  owned scrcpy process, not user-selected processes or the ADB server.
- App UI exit calls `shutdown_mirrors` before durable-job shutdown, with bounded
  direct-child stop attempts. Shutdown failure does not skip job shutdown.

## Trust / residual risk

Native flags, local windows, server cleanup and real Android behavior are not
certified by mocked tests. Unsupported scrcpy versions may exit; no option
removal or retry weakens the requested policy. Keep host ADB/scrcpy and their
bundled libraries/server dependencies trusted: the binary fingerprint is not a
package/supply-chain certification. Host runtime environment remains trusted.

Scrcpy selects a **serial**, not the preview's ADB transport ID. Snapshot checks
are immediately before launch, not a cryptographic identity or continuous device
lock. Reconnect/serial reuse, executable/dependency replacement and malicious
same-user/device races remain. No OS/device filesystem/network sandbox exists.
The view-only policy depends on native flag enforcement, not independent proof.

The time limit is requested in scrcpy and the host watchdog, not an absolute
termination guarantee. Timeout allows bounded terminate/kill attempts; a stuck
process retains its live slot, may keep displaying and requires manual inspection.
Only the direct owned process is stopped; the ADB server and descendants are not
arbitrarily killed. Closing/crashing the app cannot guarantee phone-server or
child cleanup. An app crash releases the OS owner lock even if a child survives;
a later runtime may not discover/own that child. Native `--time-limit` is an
additional safety mechanism, not verified crash recovery. Never recover by killing
all scrcpy/ADB processes. No unattended startup/replay is implemented.

Other desktop software or synced/recording environments can capture the displayed
screen. This path requests no recording/cloud/model upload, but cannot constrain
independent software. No claim of private display, encryption or content redaction.
Android telemetry remains the next unselected-device/privacy path to migrate.

## Validation

26 new fake-process tests, plus updated isolated main-shutdown integration variants (success/failure).
Coverage includes headless/cancel/replay, full flags/env, executable/transport
change, concurrent launch, other-owner refusal, exact/stale IDs, watchdog,
unstoppable child, native exit/start failure, watchdog start failure, shutdown,
late approval after shutdown, invalid duration, dispatch and non-creating status.
No scrcpy/ADB/real windows/phone interaction. Full local suite: 811 passed, one
existing Starlette warning; targeted Ruff/diff clean. No commit or push.
