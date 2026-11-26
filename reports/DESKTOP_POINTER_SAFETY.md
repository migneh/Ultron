# Ghost Pilot: narrowed pointer-only surface

## Compatibility change

Blind search/browser launch, result clicks, app launch via Windows search/Run, note writing and arbitrary typing now fail closed, including direct public helper calls. Approval alone cannot verify foreground application/control identity or make terminal/chat/password-field typing safe. No fallback. A future target-addressed adapter needs verified control identity, exact bounded content/action approval, revalidation and observable outcomes before enabling keyboard/click workflows.

`move`/`glide` now require explicit integer primary-display coordinates and a finite 0.2–3 second duration. `demo` uses a fixed 25-point bounded primary-display path; move uses 20 linear steps, no random overshoot. Legacy `steps` is retained only for Python call compatibility and cannot increase effects. Aliases remain but no longer provide old autonomous behavior. The module lazily imports PyAutoGUI only for supported pointer requests; text content is not logged by this module. Existing model/UI logging outside it is not removed.

## Boundary

`actions/ghost_pilot.py` → `core/desktop_motion.py`: immutable single-use host approval, consume at sink, one in-process admission lock and existing OS OwnerLock convention. Approval binds coordinates/path, geometry, duration and pointer-only intent. Execution deliberately begins at current position after the approval HUD click, not the preapproval cursor position. No keyboard events, clicks, screenshots or app launch. Status exposes only the currently owned ID; exact ID cancellation requests stop at a checkpoint. Shutdown closes admission, cancels active motion and blocks late approval. Main cleanup keeps mirror/jobs cleanup independent if pointer cleanup fails.

Windows only: readable input desktop must match the calling thread desktop name; mouse buttons and shift/control/alt/Windows keys must not be held. Fail-safe remains enabled. Checks occur before every immediate move and at completion; geometry change, external pointer movement, held input, cancellation, fail-safe/native errors or deadline checkpoints stop without retry. Unsupported OS/session/dependency/guard state fails closed. Host approval absence/denial performs no movement. Returning success means final pointer coordinates were observed, NOT that an application action was verified.

## Limitations / remaining acceptance gates

This is risk reduction, NOT input isolation. Guard-to-move races remain: a button may be pressed just after sampling, another producer may move the pointer during a call, hover/dwell accessibility can activate controls, desktop names are not strong session identities and matching names alone do not establish trusted desktop provenance. Win32 reads, Python scheduling and PyAutoGUI may block: the deadline is a checkpoint, not a native-call kill bound. Shutdown/cancel do not interrupt a blocked call or restore the pointer. Approval HUD focus/release and Windows ctypes/PyAutoGUI integration require native certification. One owned slot does not serialize unrelated application tools or external input injectors. No focus identity verification, multi-monitor support, global GUI graph audit, OS sandbox or protection against malicious in-process code replacing dependencies. Runtime modules, PyAutoGUI, Windows APIs and home lock directory remain trusted. No shutdown join; cancellation is requested and reported as such.

Other GUI producers (computer control/browser/OS wrappers, plugins and macros) are NOT migrated by this change. Disabled legacy workflows are a compatibility restriction, not completed target-verified automation. Global discovery and missing review appendices remain open.

## Validation

46 fake-only tests in `tests/test_desktop_motion.py`: absent/denied/replayed approval, direct sink/helper calls, invalid bounds/nonfinite/huge durations, geometry changes, held input before/after approval and mid-motion, user intervention, fail-safe, native errors, owned cancellation, shutdown including pending approval, owner/admission refusal, fixed demo, deadline checkpoint, unsupported platform, status and fake Win32 input-desktop/handle-cleanup behavior. Main cleanup tested with success/failing mirror cleanup. No actual mouse, keyboard, desktop, browser, app, screenshot or native session used. Full suite: 887 passed, existing Starlette warning. Targeted Ruff and diff check clean.
