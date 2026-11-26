# Scoped IoT lighting and disabled bundled surveillance

## Changed boundary

`iot_overlord` now supports one explicit operator-provisioned HA light per immutable host-approved request. `core/iot_lighting.py` consumes the single-use grant at its HTTP sink, re-reads config, requires its content digest and canonical controller to match the preview and validates entity/service/settings again. Exactly one POST: fixed `light/turn_on` or `light/turn_off`, explicit entity, fixed theme settings or no settings. No toggle, implicit all targets, arbitrary service/domain/settings, switch/plug control, rollback or retry. A successful HTTP status means acceptance only, never observed device state.

The legacy `_call_ha_service` helper returns False without network access, including direct callers. Workspace implicit lighting is disabled. IoT focus is an approved amber request for an explicit entity, not Android DND. IoT lockdown and macro lockdown/stealth implementations are disabled before all effects. IoT discover/scan is disabled; status does not probe LAN or query HA.

Sentry is deliberately disabled, not permission-migrated surveillance: worker, activation, instant lockdown and direct capture-adjacent dispatch/voice/lock helpers contain no effects. Optional OpenCV/PyAutoGUI/requests imports removed from that module. Gallery does not read files; status does not read credentials/gallery. Historical snapshots are NOT deleted, migrated or uploaded. Restart the application to load these changes; this is not a hot-patch mechanism for an already running old worker. Other camera/screenshot/lock tools remain outside this scoped change.

## Operator setup and compatibility

Existing `config/api_keys.json` (never put actual secrets in documentation/tests/chat) must contain:

- `home_assistant_url`: HTTPS literal RFC1918 IPv4, optional port, no credentials/path/query/fragment. Example: `https://192.168.1.2:8123`.
- `home_assistant_token`: valid bearer credential, held only in config and transport, excluded from approval preview/error text.
- `home_assistant_light_entities`: unique list of 1–32 explicit `light.*` entity IDs. No `light.all`/`light.none`; no default targets. The operator must verify these are safe physical lights, not groups or unrelated appliances/automations.

TLS verification is mandatory. The controller needs an IP-SAN certificate trusted by the host default CA store; self-signed/default HTTP/hostname setups fail closed until properly provisioned. No insecure fallback, environment proxy or environment CA override (`Session.trust_env=False`); redirects disabled. No new token acquisition/config write API. URLs are not model-supplied. Model/tool input selects only a preprovisioned entity and deterministic operation/theme.

The six theme names remain; unknown themes no longer silently become cyan. Stealth only requests off for the explicit entity, not the whole room. `turn_on`/`turn_off` aliases now bind their named operation regardless of a contradictory `state`; generic control requires explicit on/off. Legacy raw helper Boolean is always False; approved high-level wrappers return pending confirmation/results, not synchronous physical success.

## Transport and residual limits

Requests uses a new default Session (no configured retries), TLS certificate checking, `(3,4)` connect/read timeouts, `stream=True` and closes response/session without consuming a body. Response contents/stderr/exceptions are not exposed. Redirect/nonacceptance reports physical outcome unverified; errors are unknown and never retried. These are native socket timeout bounds, NOT a total wall-clock kill deadline. Host OS/TLS/requests, HA credentials/config, controller, HA entity semantics and any downstream automations remain trusted. Private IP restriction is egress narrowing, not a network sandbox: an operator can still configure a wrong private service. Static IP avoids DNS rebinding, not routing/ARP changes. TLS authenticates only according to the trusted CA store. HTTP acceptance does not establish device identity, state, safe use or action completion. Config path checks/fingerprints reduce changes but are not atomic filesystem isolation or protection against malicious in-process code.

Generic fingerprint helper may read up to its 64 MiB cap before rejecting an oversized config; the actual JSON read is capped at 64 KiB. No per-device global lock/state reconciliation, remote cancellation, rate limit or cross-process serialization; an accepted request cannot be recalled. Independent approved requests can execute concurrently. Changing config after revalidation can still race, but only the already approved snapshot credential/endpoint/entity is sent. Config digest is internal approval metadata, not a credential or proof of trusted operator provenance. Existing model/UI logs outside this adapter are unchanged. Physical safety and downstream automation validation remain operator responsibilities; broader permission graph review is still open.

## Validation

53 new fake-only tests cover absent/denied/expired/replayed approval, direct sink refusal, immutable payload, changed endpoint/token/allowlist, invalid provisioning/missing config, unsafe URLs/port zero, explicit targets/settings, no body reads, TLS/proxy/redirect/timeout options, request resource closure, rejected/error responses without retry, deterministic alias binding, raw/workspace bypass refusal, disabled IoT/sentry helpers and macro lockdown. Existing HTTP-truthfulness test updated to assert that the removed implicit raw path cannot execute. No live devices, network, locks, webcam, screenshots, Telegram, voice or dashboard dispatch used. Full suite: 940 passed, one existing Starlette warning. Targeted Ruff and diff checks clean. No native/provider/physical certification.

Next: file mutation/undo sink review. Remaining IoT gates: separately designed bounded surveillance/capture/retention/recipient approval and lifecycle before re-enabling; native HTTPS/provider tests; physical identity/automation review; global call graph/egress coverage.
