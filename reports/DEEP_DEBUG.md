# Repository-wide deep debug pass

Date: 2026-11-23. Version remains 0.1.0. No commit, push, release, or provider/native effects performed.

## Scope and findings

Ran the entire automated suite, compilation, dependency consistency, CLI diagnostics, version consistency and wheel/resource checks. Inspected high-risk wake lifecycle, configuration readers, logging replacement and deferred tool dispatch. This is not whole-desktop certification.

Implemented:
- Serialized wake starts; isolated worker-generation model, queue and stop event; reject restart while a stopped worker remains alive. Stop signals the worker, joins for a bounded interval and avoids self-join. Suppress detections after stop during inference; clear readiness on worker exit/start failure; tolerate malformed scores.
- Wake enable no longer persists success when detector startup fails. Disable stops the detector. UI reports startup failure, including after successful download rather than incorrectly reporting readiness.
- Configuration readers tolerate non-object JSON and invalid boolean/provider/platform values; non-string Gemini keys fall back safely.
- Close replaced logging handlers to avoid leaking descriptors.
- Explicitly capture deferred loop values in tool callbacks. Six B023 warnings removed; these were preventive corrections, not demonstrated runtime failures (callbacks were immediately awaited).
- Added `python -m ultron doctor [--profile desktop|test|workspace] [--json]`, with meaningful process exit status. Checks dependency metadata, bundled resources and bounded JSON configuration shape, not values. Refuses special configuration files and does not invoke optional feature modules, models, services or credential validation. Missing config is normal first-run setup, not proof of usable credentials.

## Reproducible validation

- `python -m pytest -q`: **1,196 passed**, one existing Starlette/httpx deprecation warning. This pass adds 34 regressions in `tests/test_deep_debug.py` over the 1,162 baseline.
- `python -m compileall -q ultron tests scripts main.py`: passed.
- `python -m pip check`: passed.
- `python scripts/version.py --check`: passed, 0.1.0.
- Ruff undefined-name and loop-binding rules F821/F822/F823/B023 over runtime/scripts: passed. Targeted newly added/debug modules also pass configured Ruff rules.
- Wheel built without dependency downloads; diagnostics module and all diagnostic-listed resources present in archive.
- Test-profile doctor exits 0. Desktop-profile doctor exits 1, correctly reporting missing PyQt6, sounddevice, google-genai, edge-tts and miniaudio in this sandbox.
- Last broad runtime/scripts Ruff scan: **425 outstanding findings**, down from 431. Mostly unused imports, compact statements and import ordering, plus exception-chaining/zip strictness warnings. Broad lint is NOT clean.

## Remaining acceptance gates

- Desktop startup, actual Qt UI behavior and teardown, microphone/speaker behavior, real model inference, wake false positives/negatives and platform permissions require supported native environments. UI modifications were compiled and source-reviewed, not exercised with Qt here.
- Bounded stop cannot forcibly terminate blocked native inference; restart intentionally refuses until the previous worker exits. A callback already at its final dispatch boundary may race stop. This is not a hard cancellation barrier.
- Doctor verifies prerequisite presence only: metadata is not an import/runtime health check; credentials, provider connectivity, models, device access, native libraries and complete optional-feature dependencies are not certified. Configuration path checks are not an adversarial filesystem sandbox.
- No claim of complete static typing, coverage, security proof, process isolation or all-platform integration certification. Existing privileged-operation, plugin/macro and integration gates remain tracked separately.
- No broad mechanical lint rewrite was attempted during lifecycle debugging, to avoid hiding functional changes in unrelated churn.
