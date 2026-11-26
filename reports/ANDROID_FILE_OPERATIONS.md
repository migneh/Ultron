# Android file operations — engineering record

## Scope and acceptance

Migrate public push/pull/install entry points to exact-content operation-policy
approval. Keep legacy tool names; require explicit serial and host-root local
paths. Support one regular file up to 64 MiB. No directories, default-device
selection, arbitrary remote overwrite, implicit APK replacement, or retries.
Mirror/screenshot/telemetry are deliberately not included.

| Requirement | Implementation | Evidence |
|---|---|---|
| No transfer/install before consent | Public wrappers create a plan; `_execute` consumes the exact grant | Headless, cancellation, direct-sink and replay tests |
| Explicit authorized device | Reuse serial/transport/executable snapshot; recheck before effect and after staging/remote validation | Existing transport tests plus transfer reconnect tests |
| Approved bytes sent | Root checks and fingerprint; bounded private staging; verify staged bytes against approved identity/SHA | Source-change, staging-failure, revocation and snapshot tests |
| APK replacement explicit | Strict boolean, default false; only explicit true adds `-r` | Replacement false/true and invalid-flag tests |
| No planned remote overwrite | Strict Download base; fresh random directory, `mkdir` must succeed before push | Destination restriction and mkdir-conflict tests |
| Bounded pull | Private local staging, bounded pipe queue, byte/size checks, deadline and direct-child termination | Real small subprocess overflow/truncation/nonzero/deadline/empty tests |
| Approved remote content | Regular-file size and SHA snapshot, recheck before receive, checksum before publication | Changed-source, checksum-mismatch and partial-receive tests |
| No local replacement | Exact new file with existing parent; same-filesystem exclusive hard link, never replace | Existing target and publication-race tests |
| Failure has no blind replay | Policy single use; unknown/partial status; remote leftovers retained for manual inspection | Deny/replay/install-error/partial cleanup tests |

## Implementation

- `actions/android_bridge.py`: compatible public wrappers and updated schema,
  including `serial` and `replace_existing`.
- `core/android_files.py`: preview validation, effect sink, immutable local staging,
  remote metadata snapshots, bounded receiver and no-clobber local publication.
- `tests/test_android_files.py`: 40 tests. Device/ADB operations are mocked;
  bounded pipe tests run only tiny trusted local Python fixtures.

## Important limits / residual risks

This is scoped in-process permission enforcement, not OS/device isolation. An
approved ADB shell command can still do destructive work through a separate path.
ADB executable, host server state and device serial/transport are not cryptographic
identity and cannot be atomically locked with effects. Path/parent symlink races
on host/device remain possible under hostile same-user/device mutation. Remote
Download restrictions are lexical, not a proven remote filesystem jail.

The remote mkdir/push sequence intentionally never reuses a planned destination,
but is not an atomic remote filesystem transaction. Changes after checks can
produce uncertain/partial effects. Remote directories are not auto-deleted.
Local staging is private and cleaned on normal returns/exceptions, not guaranteed
after crashes. Destination grants and checks are revalidated, not a descriptor-
relative filesystem sandbox. Downloading into auto-executed locations is unsafe;
root grants should exclude those locations. Files/content are not safety-certified.

The receiver bounds bytes written and queue memory. Timeout kills the direct
child, not an arbitrary process tree; a descendant retaining stdout can keep a
bounded daemon reader/pipe alive until EOF. That reader never owns the destination
file handle. No hard CPU/memory/disk/child-process OS sandbox is provided.

Android toybox `stat`/`sha256sum`, ADB versions, macOS/Windows filesystems and actual
APK/device behavior have not been natively certified. Missing remote commands or
unsupported local hard links fail closed. `Success` is an ADB installation report,
not malware/signature verification. Zero exit without checksum is not verified push.

## Validation

Full suite: 761 passed, one existing Starlette deprecation warning. Targeted Ruff
and `git diff --check` clean. No real ADB/phone/app installation, commit or push.
Wake model remains `hey_jarvis`. Remaining work is tracked in
`PRIVILEGED_SINK_TODO.md`.
