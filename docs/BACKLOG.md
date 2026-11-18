# Backlog — known issues deliberately left open

Things that are genuinely imperfect, confirmed by reading the code, and not fixed yet. Each
entry says what it is, why it was deferred, and how to check it. Nothing here is a guess: if it
is on this list, the line was read.

Ordered roughly by payoff.

---

## 1. The Windows-native OCR fallback in `optical_hud` is a stub

`actions/optical_hud.py` builds a PowerShell script (`ps_script`) for Windows Runtime OCR but
**never executes it** — the string is assembled and discarded, so the function returns `""` on
Windows whenever `pytesseract` is unavailable.

- **Why deferred:** there is no Windows machine here, and OCR that "looks right" but silently
  returns empty is worse than one that reports failure. It needs a real Windows run to confirm
  the WinRT `Windows.Media.Ocr` invocation and template plumbing.
- **Test:** on Windows, uninstall/rename the tesseract binary, screenshot some text, call the
  tool, and see whether it returns text or an empty string.
- **Note:** `pytesseract` being pip-installed is not enough on any OS — the tesseract *binary*
  must be on `PATH`. `scripts/doctor.py` flags the import but cannot see the binary.

## 2. Blocking I/O inside `async def`

`actions/browser_control.py` and `dashboard/server.py` call synchronous `requests`/file APIs
directly inside coroutines (Ruff `ASYNC221/230/240`).

- **Why deferred:** it costs latency, not correctness, and only while another coroutine is
  waiting. Fixing it properly means `asyncio.to_thread` wrappers through several call paths —
  worth doing in a dedicated pass, not folded into a bug fix.
- **Risk if left:** a slow HTTP call stalls the dashboard's event loop for its duration.

## 3. Dead locals that waste real work

- `actions/code_helper.py`: `image_base64` is computed (a base64 encode of every screenshot)
  and then never used — pure per-call waste.
- `actions/bounty_hunter.py`, `actions/android_bridge.py`, `actions/quick_timer.py`: assigned-
  and-never-read locals (`detected_title`, `lines`, `action`).

- **Why deferred:** harmless and unrelated to any bug; fixing them in the same commit as the
  memory fixes would have muddied that diff.

## 4. `bounty_hunter` always prints `$`

Price matching handles `₹`/`€`/`£` input but the formatted output hardcodes a dollar sign.

- **Why deferred:** cosmetic, and the right fix is to carry the detected currency symbol through
  the comparison table rather than patch the output line.

## 5. The wake phrase is still "Hey Jarvis"

`WAKE_MODEL = "hey_jarvis"` / `WAKE_PHRASE = "Hey Jarvis"` in `core/wake_word.py`.

- **Why deferred:** that string is the name of a pretrained `openwakeword` model. It cannot be
  renamed without training or downloading a different model. It is now single-sourced, so
  changing it is a two-line edit whenever you pick a model — see
  [`PERSONALIZING.md`](PERSONALIZING.md#wake-word).

## 6. Legacy `jarvis_*` keys are still read by the dashboard

`dashboard/static/*.html` and `server.py` still accept `jarvis_token` / `jarvis.key` /
`jarvis.crt` as fallbacks behind the `ultron_*` names.

- **Why deferred:** deliberate. Harmless reads that keep an already-paired phone working. Drop
  them once you are sure no device is holding an old session.

## 7. `pygetwindow` has no Linux backend

Window geometry is Windows-only; on Linux the import raises `NotImplementedError`.

- **Status:** handled — imports are guarded (that was a real bug, now fixed), so affected tools
  degrade instead of failing to load. Restoring the *feature* on Linux would mean an
  `xdotool`/`wmctrl` shim.

---

## 8. `browser_control` has no incognito mode

The tool schema used to declare an `incognito` parameter that no code path ever read, so a
model asked for a private window would silently have got the user's real, logged-in profile. The
parameter was removed rather than left lying (see HISTORY pass 5); the capability does not exist.

- **Why deferred:** incognito cannot use `launch_persistent_context()` — it needs
  `launch()` plus `new_context()`, i.e. a second launch path in `_BrowserSession`, and a registry
  that can key two sessions for the same browser. Chromium cannot be downloaded in the sandbox
  where this was written, so such a path could not be verified even once.
- **How to add it:** give `_BrowserSession` an `incognito` flag; when set, launch ephemeral and
  create a fresh context; key the registry entry as `f"{name}:incognito"` so it cannot collide
  with the persistent one; then re-add the schema parameter. Test on a machine with a real
  browser: check `navigator.webdriver`-independent expectations, a clean cookie jar, and that the
  profile directory is untouched afterwards.
- **Related:** the registry lock is held across `_BrowserSession.start()` (up to a 20 s readiness
  wait), so `list_browsers` can block while a browser is starting. A latency smell, not a
  correctness bug.

---

## Fixed, for reference

Do not re-report these — each has a regression test in `tests/test_regressions.py`:

- `link_entities()` erasing node labels/properties (memory data loss)
- embeddings going stale as the corpus vocabulary grew (silent amnesia)
- `workspace_recall.search_memories()` raising `NameError: re`
- `main.py` shutdown calling `os._exit()` without `import os`
- `web_autopilot` flight-date fallback raising `NameError: datetime`
- `chronos_predictive` failing to load on Linux (`pygetwindow` raises `NotImplementedError`,
  not `ImportError`)
