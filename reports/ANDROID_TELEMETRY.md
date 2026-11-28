# Android telemetry — scoped privacy and bounded queries

## Contract

`info`/`telemetry` and the public `get_device_info` helper now require an explicit
serial and exact selected-field host approval. `battery` defaults to battery only.
No first-device selection or fastboot/other-device fallback. Existing direct callers
without serial fail closed. Discovery via `devices`/`list`/`status` is a separate
legacy listing path and is NOT covered by this migration.

Default fields: model, brand, Android version, security patch, battery. Codename,
storage and Wi-Fi IPv4 can be explicitly selected using `telemetry_fields`. Storage
and IP are never added through model intent inference or a failed field fallback.
At most eight unique allowlisted fields; no arbitrary shell/getprop input. Even
basic telemetry can be private: preview warns that results may enter the configured
assistant/model/UI/log paths, not guaranteed local/private inference. The adapter
itself stores no telemetry, but does not redact/control existing result consumers.

## Enforcement / output

- Immutable plan binds exact fields and device/executable/transport snapshot;
  effect sink consumes a single-use grant. Field-list mutation cannot broaden it.
- Each query uses a constant command, explicit local ADB server and transport ID.
  Executable/transport are rechecked before each query and after the group. A
  failed/changed final snapshot discards all results, not just the last field.
- Per-query receiver cap: 64 KiB / at most 5 seconds, bounded pipe queue. A 20-second
  query budget stops issuing further queries. This is NOT a hard end-to-end bound:
  binary fingerprinting/ADB enumeration (up to 5s per probe), final identity checks
  and bounded child cleanup can extend it. At most eight fields, no retries.
- Raw dumps, stderr, partial failed stdout and exceptions are not returned. Property
  strings are bounded to 200 characters with controls rejected. UTF-8 decode errors
  fail that field. Successful strings remain untrusted device data, not authority.
- Battery percent uses validated level AND scale; missing/malformed values do not
  become 0. Valid measured zero remains zero. Charge state is an enumeration or
  unknown. Storage is `df -k /sdcard` filesystem data in KiB, not whole-device capacity.
  Wi-Fi address must parse as IPv4; absence/error does not imply disconnected/secure.
- Results distinguish reported/partial/unavailable, individual field errors and
  deadline-not-queried. They are device-reported, not independent verification.

## Residual risks

No cryptographic device identity, atomic lock over all reads, native command
compatibility certification or prompt-injection-proof data is claimed. Repeated
snapshots reduce reconnect mistakes but cannot defeat malicious same-user/device
races or serial/transport reuse. Fixed query stdout is bounded, but existing bridge
snapshot/discovery helpers and other application paths are separate. Direct-child
receiver cleanup is not process-tree/OS resource isolation; see Android file-transfer
engineering record for descendant-pipe behavior. Host runtime dependencies remain
trusted. Existing assistant/UI/log infrastructure may retain returned values.

## Verification

30 fake-only tests: headless/deny/replay, full local transport/fixed queries,
explicit sensitive fields, immutable selection, mid/final device changes, invalid
fields/properties, partial failures, scaled/zero/malformed battery, deadline skips,
alias dispatch, missing serial and direct-sink refusal. No real phone, provider or
telemetry query ran. Full suite: 841 passed, one existing warning; targeted Ruff/diff
clean. Wake word unchanged; no commit/push. Next: GUI-input boundary, plus a separately
tracked discovery-output/local-server review.
