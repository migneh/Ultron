# Ultron engineering verification and debugging

Date: 2026-11-23  
Branch: `arena/1a640740-ultron`

## Scope and assurance

Repository-wide syntax and undefined-name analysis; broad type-checking; targeted source review of assistant dispatch, tool execution, confirmation, memory/graph persistence, dashboard authentication, UI integration and gesture lifecycle. Confirmed defects were repaired and targeted regression tests added.

This is **not an end-to-end certification or an exhaustive security audit**. Many tools require Windows, a desktop session, microphones/cameras, credentials, third-party programs or external services. No destructive tools, real generated-code payloads, credentialed model calls or live workstation operations were exercised. GUI changes were source-reviewed, not runtime-tested: PyQt6 is not installed in the current sandbox.

## Confirmed defects repaired

| Area | Failure | Repair |
|---|---|---|
| Shell execution | A read-only executable prefix allowed shell chaining, substitutions, redirection and state-changing options without consent | Conservative shell-syntax checks; restricted Git options; mutations to date/time/hostname/network tools require confirmation |
| Synthesized tools | Unapproved generated code was written into auto-discovered directories, enabling execution after restart; activation referenced undefined `module_name` | Compile in memory; write exclusively only inside the approval callback; refuse existing files/modules; define import identity; remove unreachable success reporting |
| Generated desktop code | A Python dictionary labelled a sandbox still allowed privileged operations and ran without consent | Require explicit HUD confirmation before executing generated Python; dictionary is not claimed as process isolation |
| Developer agent | Generated projects could install packages/run code without confirmation; generated file paths could escape the project | Gate project build/run with human confirmation; resolve and check write/fix paths against project root |
| Windows launch paths | App names and project paths were interpolated into shell commands | Use argument arrays, `cwd`, or `os.startfile`; remove shell fallback in macro app launch |
| Memory updates | Bare strings raised `AttributeError`; feedback-only updates were ignored; edits reset feedback/correction history | Normalize update input; preserve metadata/history; compare complete entries |
| Persistence | Locks covered individual reads/writes but not transactions, losing concurrent updates; direct file writes risked partial JSON | Reentrant transaction lock around mutation workflows; atomic temporary-file replacement with flush/fsync |
| Review isolation | Lexical recall and ordinary memory rows included unconfirmed pending facts | Exclude `_pending` from those paths; retain explicit review UI |
| Imports | Malformed imported entries could poison memory operations and crash UI/feedback | Validate categories, values, confidence, source/date metadata and feedback before changing the store |
| Graph integration | Incorrect import silently disabled graph sync | Use package-qualified graph import |
| Graph search | Vocabulary changes made persisted vectors incompatible or silently misaligned | Build query and candidate vectors from one current vocabulary snapshot; exclude zero-similarity results |
| Graph integrity | UPSERT identity handling was unreliable; linking reset node properties; multi-hop depth was ignored | Select node identity explicitly; preserve linked nodes; bounded breadth-first traversal with exact-entity relationship lookup; enable SQLite foreign keys |
| Forgotten memory | Graph snapshots could retain/retrieve deleted or replaced facts | Delete graph node on forget; check semantic results against the authoritative current JSON store |
| Dashboard startup | `"DashboardServer" | None` was evaluated at import and raised `TypeError` | Postpone annotation evaluation |
| Dashboard expiry | TTS, downloads and WebSockets checked token presence rather than expiry | Enforce expiry at entry and recheck connected WebSockets on each received message |
| UI runtime | Missing `_lighten` and follow-up imports; overlay referenced input/send/toast methods it did not own; shortcut handler lived on non-widget wrapper | Correct imports; emit follow-up signal to MainWindow; render overlay toasts correctly; relocate keyboard handler |
| Qt threading | Worker gesture callbacks and assistant toast calls directly manipulated widgets | Marshal notifications through MainWindow signals; add signal-based MainWindow activity logging |
| Avatar integration | Wrapper referenced nonexistent `_avatar`, silently discarding gaze requests | Delegate through `MainWindow.hud` |
| Gesture badge | Gesture name overwritten immediately; stale timer could overwrite stopped state | Owned single-shot timer; cancel on state change; preserve detected name |
| Gesture lifecycle | Rapid stop/start could leave competing capture loops; failed capture fallback leaked handle | Serialize lifecycle changes; use stop event; bounded join; refuse restart while previous worker lives; release failed capture handle |
| Gesture privacy/degradation | Camera started automatically; invalid camera index raised outside handler; overlay import failed without OpenCV | Opt-in `gesture_auto_start` (default false); validate index; show unavailable-engine overlay; wire open palm callback to wake handler |
| Other runtime names | Missing `os` in main and datetime imports in web autopilot | Add imports |
| Action loader | Optional handler was not checked and non-string tool output violated registry return contract | Check handler and normalize returned values |
| Lint configuration | Rules were under `[tool.lint]`, not Ruff's configuration namespace | Move to `[tool.ruff.lint]` and `[tool.ruff.lint.isort]` |

## Verification results

- All **94 Python source files** compiled, excluding virtual environment/cache folders.
- **72 tests passed**, up from 25; one upstream Starlette/httpx deprecation warning.
- Ruff runtime-failure subset passed: `E9,F63,F7,F82` (includes undefined names).
- Focused mypy passed on `ultron/memory/memory_manager.py`, `ultron/memory/cerebro_graph.py`, `ultron/core/action_loader.py`, `ultron/core/confirm.py`.
- Broad mypy with explicit package bases: **337 diagnostics across 56 files**, checking 86 application source files. The minimal sandbox lacks many runtime dependencies/stubs, and this number is not a count of proven runtime bugs.
- Broader Ruff `F` analysis still reports **217 findings**: unused imports, unused variables and redundant f-string prefixes. Those were not auto-fixed in this functional patch.
- `pip check`: no broken requirements in the verification environment.
- `git diff --check`: passed.

Regression tests use temporary JSON/SQLite stores and mocked confirmation boundaries. Dashboard tests use in-process ASGI clients, not a public server.

### Reproduce

```sh
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
# Dependencies for graph and in-process dashboard tests:
.venv/bin/pip install numpy psutil requests fastapi uvicorn httpx python-multipart
.venv/bin/python -m pytest -q
.venv/bin/ruff check . --select E9,F63,F7,F82
.venv/bin/mypy memory/memory_manager.py memory/cerebro_graph.py ultron/core/action_loader.py ultron/core/confirm.py --ignore-missing-imports
.venv/bin/mypy --explicit-package-bases main.py ui.py actions core memory dashboard plugins --ignore-missing-imports
```

Use `python -m pytest`, rather than relying on the console script's import-path behavior. Graph/dashboard tests explicitly skip when their optional dependencies are absent; the reported 72-test run had those dependencies installed. The reproduction commands above are POSIX; use the equivalent virtualenv executables on Windows.

## Remaining risks and required follow-up

1. **Desktop acceptance testing required:** run PyQt6 under a real event loop; validate memory edit/feedback/import/export, keyboard shortcuts, thread delivery, missing-engine fallback, wake and shutdown behavior. Signal-based repairs have not been verified on a GUI here.
2. **Privileged generated Python remains privileged:** user confirmation is a consent boundary, not a sandbox. Once approved, code can access the user's account. Use subprocess/container isolation and a capability broker before treating generated execution as untrusted-safe.
3. **Dashboard transport/auth hardening remains:** plain HTTP fallback exposes bearer credentials and unauthenticated CBC encryption is not a transport-security substitute. Require TLS for remote access, review login rate limits/session revocation, and review download/upload symlink and concurrency boundaries. Do not expose this service directly to the public internet.
4. **Broad static typing remains unresolved:** optional SDK/Windows APIs, dynamically populated attributes and large untyped orchestration/UI functions need gradual typing with real dependency stubs. A clean undefined-name scan does not establish a clean type check.
5. **Memory locking is process-local:** atomic replacement protects file integrity, but two independent assistant processes can still overwrite each other's updates. Enforce a single instance or move authoritative memory transactions to SQLite. Corrupt-file recovery/migration and all imported metadata variants need additional testing.
6. **Graph synchronization is best-effort:** graph errors intentionally do not block JSON persistence. Authoritative-store filtering protects the memory recall path from stale entries, but direct graph tools can retain older snapshots after wholesale replacement; add explicit reconciliation and migration tests.
7. **Hardware/service integrations unverified:** microphones, echo cancellation, TTS playback, wake-word models, webcam capture, gesture recognition accuracy, Gemini/local-model streaming, cancellation/reconnection and platform-specific workstation actions require dedicated integration environments. Gesture status may still briefly race asynchronous camera failures; stop may wait up to two seconds for capture.
8. **Coverage is targeted, not comprehensive:** the new tests cover reproduced defects; they do not cover every tool or lifecycle path. Add contract tests for every discovered action/plugin, UI tests, provider failure simulations and Windows/macOS/Linux CI before declaring production readiness.

Changes are left uncommitted for review. No pull request was opened in this debugging pass.
