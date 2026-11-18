# Provenance & what changed

This file records where the code came from, so the credit stays findable and future
decisions are made with the real history in view. Required attribution is in
[`../LICENSE`](../LICENSE).

---

## Lineage

```
FatihMakes / Mark-LVII  ("MARK 56 — JARVIS")
        │  CC BY-NC 4.0 · Copyright (c) 2026 FatihMakes
        ▼
AbuZar-Ansarii / Ultron      (fork; no LICENSE file — README claimed MIT)
        ▼
migneh / Ultron              (this repository)
```

### Evidence of derivation (not just inspiration)

- `core/prompt.txt` documented the identical persona/rules layering that Mark-LVII used.
- `.jarvis_profiles/` browser-automation directories and `config/jarvis.ico`.
- The footer of `ui.py` read **"By FatihMakes"**.
- `setup.py` still said **"MARK LIV"** in its header, help text and banner.
- Wake word `"Hey Jarvis"` (`openwakeword` model `hey_jarvis`), `com.jarvis.assistant`
  launch agents, and `jarvis_token` dashboard session keys.

This is a derivative work, which is why `LICENSE` carries CC BY-NC 4.0 rather than MIT.

### The MIT question

The upstream fork's README said MIT, but it shipped **no LICENSE file**. A MIT claim
appended to CC BY-NC 4.0 code does not relicense that code — a downstream reader can only
rely on what the original author actually granted. So this repository documents the
inherited licence (CC BY-NC 4.0) and notes the discrepancy rather than repeating a claim it
cannot substantiate.

**Practical consequence:** personal and non-commercial use is fine. Selling it, or shipping
it inside a paid product, is not — unless the Mark-LVII-derived parts are replaced with an
independent implementation, or permission is obtained from FatihMakes.

---

## What the de-fork pass changed (2026-11)

**Identity**

- Leftover `MARK LIV` strings in `setup.py` and `memory/config_manager.py` → `Ultron`.
- `JARVIS` / `Jarvis` → `ULTRON` / `Ultron` across **32 files** (log prefixes, HUD labels,
  console output, docstrings, dashboard pages, plugin template).
- Class names `JarvisUI` / `JarvisLive` → `UltronUI` / `UltronLive`.
- Footer credit `By FatihMakes` → `migneh`; attribution moved to `LICENSE` + this file +
  README `Credits` (which satisfies the licence's attribution requirement more durably
  than a 22px label did).
- Filesystem identifiers: `.jarvis_profiles` → `.ultron_profiles`, `com.jarvis.*` →
  `com.ultron.*`, `config/jarvis.ico` → `config/ultron.ico`, screenshot/temp filenames
  `jarvis_*` → `ultron_*`.
- Dashboard session keys now written as `ultron_*`; legacy `jarvis_*` keys are still
  **read** so an already-paired phone keeps working.
- Tool `shutdown_jarvis` → `shutdown_ultron` (and `core/prompt.txt` updated to match).
- Removed a dead `UltronLive = UltronLive` self-alias left behind by an earlier rename.

**Deliberately not changed**

- `WAKE_MODEL = "hey_jarvis"` and the spoken phrase **"Hey Jarvis"**. That string is the
  name of a pretrained `openwakeword` model — renaming it breaks detection. See
  [`PERSONALIZING.md`](PERSONALIZING.md#wake-word) to swap or train a different phrase.
- Legacy dashboard token/cert keys that are still *read* for compatibility.

**Fixed**

- `actions/chronos_predictive.py` caught only `ImportError` around `import pygetwindow`, but
  that library raises `NotImplementedError` on Linux. The whole module—and therefore the
  Chronos tool—failed to load on Linux. Now degrades instead of vanishing. Verified: tool
  discovery went 40 → 41 in a headless Linux check, where the other ten failures are the
  expected "no X server here" ones.

**Moved**

- `Prompt.txt` (a planning brief for the Mark-LVI reverse-engineering exercise) →
  [`archive/reverse-engineering-brief.md`](archive/reverse-engineering-brief.md). It is
  project history, not application code.

---

## Bug-fix pass (2026-11)

Six defects fixed in four files, each reproduced before the fix and covered by a regression
test afterwards (`tests/test_regressions.py`).

**Cerebro memory engine (`memory/cerebro_graph.py`) — the two serious ones**

1. `link_entities()` called `upsert_node()` with default arguments, and the upsert's
   `ON CONFLICT DO UPDATE` overwrote `label` and `properties`. The natural flow — "remember my
   flight and link it to my trip" — therefore **erased the flight details as its last step**.
   Reproduced: `('IndiGo 6E-204 Delhi to Mumbai', '{"airline":…}')` → `('flight:del_bom', '{}')`.
   Fixed with `_ensure_node()`, which never rewrites an existing node.
2. Embeddings were built against a dynamic vocabulary (top 800 tokens by frequency, rebuilt on
   every insert) with nothing recording *which* vocabulary. Once new nodes reshuffled the
   token→index mapping, old vectors failed `np.dot` or scored garbage, and the
   `except Exception: continue` swallowed it. **The memory quietly forgot as it grew** — after
   40 unrelated inserts the original memory was unfindable at 0.0.
   Fixed by stamping each vector with a `vocab_sig` fingerprint and having `semantic_query()`
   rebuild stale vectors from the node's own text and persist the repair. Existing databases
   migrate in place (`ALTER TABLE`) and heal on first query.

**Crashes from missing imports**

3. `actions/workspace_recall.py` used `re.findall` with no `import re` → memory search raised
   `NameError` on every query. (`subprocess` was missing too, so macOS/Linux active-window
   capture silently never ran.)
4. `main.py`'s shutdown handler called `os._exit(0)` with no `import os` → it said farewell and
   the process kept running, because the `Timer` thread died with `NameError`.
5. `actions/web_autopilot.py` referenced `datetime`/`timedelta` in its flight-date fallback
   without importing them.

**Housekeeping**

- `requirements.txt` listed four packages for tools that do not exist in this build
  (`gmail_control`, `calendar_control`, `home_assistant`, `printer_control`). They are now
  commented out with an explanation; install is smaller and the comments no longer point at
  modules you will not find.
- Verified-and-cleared false positives: the `B023` lambda-capture warnings (every lambda is
  passed straight to `run_in_executor` and awaited, so no rebinding window) and the FastAPI
  `File(...)` default.
- Known-but-open issues moved to [`BACKLOG.md`](BACKLOG.md) rather than half-fixed.

---

## If you ever want to go fully independent

The non-commercial restriction only binds the *derived* code. A clean-room path exists:
rewrite `core/prompt.txt`, the HUD, and the action modules from scratch against the same
interfaces, keeping none of the Mark-LVII-derived implementation. That is a large project —
worth doing deliberately, not accidentally.

## Debug pass two (2026-11)

Three more defects, all of them the same species: a feature that reports success while doing
nothing, because nothing throws. Found by executing modules rather than reading them.

**Silently dead features (two headline capabilities)**

1. `actions/iot_overlord.py` — the lockdown protocol imported `arm_sentry`, which does not
   exist (`sentry_protocol` exposes `activate_sentry`). The `except Exception` printed
   "Perimeter Sentry: Standby." every time, so *crimson lockdown never armed the sentry* and it
   read as a deliberate design choice.
2. `actions/workspace_matrix.py` — the cyber-audit preset imported `run_security_audit`, which
   does not exist (`network_auditor` exposes `audit_security_posture`). The fallback text claimed
   "Cyber Audit: Network telemetry online." while no audit had ever run.
   Both now call the real entry point, and both failures print a reason instead of a
   reassuring sentence.

**Wrong output (`actions/git_sentinel.py`)**

3. Branch names were scraped with `^##\s+([^\s\.]+)`, which was wrong in three real cases:
   a repo with no commits reported the branch **"No"** (from `## No commits yet on master`), a
   dotted branch was truncated (`feature/v1.2` → `feature/v1`), and detached HEAD was reported
   as `HEAD`. Now parsed by prefix, with tests for all three.

**Contract violation (`actions/quick_timer.py`)**

4. `quick_timer_handler` called `int()` on model-supplied arguments, so `{"seconds": "abc"}`
   raised `ValueError` straight out of a tool handler — the loader can only report that as a
   failure, never as speech. Arguments are now coerced ("90", 1.5, " 90 " are accepted; booleans
   and junk get a spoken explanation). A call with no duration now asks for one instead of
   silently starting a one-minute timer nobody requested.

**New guard**

`tests/test_imports.py` statically resolves every `from <local module> import <name>` and fails
if the name does not exist, so this bug class cannot ship again. Verified by planting a broken
import: the suite fails with the exact file and line.

Suite: 22 tests, stdlib only, no display, no network.

## Debug pass three (2026-11) — the phone dashboard never worked

The single worst bug found so far, because it removed a whole feature without a trace.

`dashboard/server.py` contained:

```python
_GLOBAL_DASHBOARD: "DashboardServer" | None = None
```

That module has no `from __future__ import annotations`, so the union was evaluated **at import
time**, and `"DashboardServer" | None` is `str | None` → `TypeError: unsupported operand
type(s) for |: 'str' and 'NoneType'`. The second one hid in a return annotation
(`def get_dashboard() -> "DashboardServer" | None`).

So `import dashboard.server` always failed. `main.py` starts the dashboard inside a
`try/except Exception` that only printed `[Dashboard] Disabled: …` to the console — which reads
like "you didn't install fastapi", not like a bug. Result: **QR pairing, phone uploads,
clipboard sync, remote commands and the phone websocket had never worked at all.**

Fixed by quoting the whole annotation (`"DashboardServer | None"`), which is the rule: a string
is only lazy when the *entire* annotation is a string.

While there:

- `POST /api/clipboard` returned a bare **500** with the raw exception text when the machine has
  no clipboard backend (headless Linux). It now answers `{"ok": false}` with 503, matching the
  GET twin, and does the blocking clipboard write off-thread.
- `main.py` now writes the dashboard failure to the log panel as well as the console. A broken
  feature should be visible to the person using it, not just in a terminal they may not be
  reading.

**Verified sound while auditing** (no changes needed): all 10 protected endpoints refuse
anonymous callers; forged bearer tokens rejected; pairing PINs are single-use and expiry-checked;
uploads sanitize path components and stay inside the uploads directory; download traversal is
blocked; the phone websocket rejects missing and bogus tokens.

**New guards**

- `tests/test_dashboard.py` — 11 tests over import, auth matrix, PIN lifecycle, upload
  containment and websocket auth (skips cleanly if fastapi is absent).
- `tests/test_imports.py` — new test failing any runtime-evaluated annotation containing a
  string union. Proved it catches the original bug by re-planting it.
- `PlatformImportTests` — asserts `chronos_predictive` imports on every OS (closes the last of
  the six bugs reported by the external audit with a test of its own).

Suite: 35 tests.

## Debug pass four (2026-11) — async correctness, then documents

### The 29 `create_task` sites: premise tested, not assumed

Ruff flags every `asyncio.create_task(...)` whose result is not stored (`RUF006`), and the usual
claim is that such tasks are garbage-collected mid-flight. **Measured, and it is not what happens
here:** an unreferenced task awaiting `sleep()` completed normally (the loop's handles keep it
alive). What *is* real is that an exception inside one is only reported when the Task object is
finally collected — possibly minutes later, at shutdown, or never — and the message carries no
context about what the task was for.

Audited all 29 sites. The ones that matter are already defensive: the dashboard command pump
wraps each command in `try/except` inside its `while True` (one bad command cannot kill remote
control), and `broadcast()` swallows per-client send errors and prunes dead sockets.

Three genuinely unguarded sites remained, so `core/tasks.py` adds `spawn()` — keeps a strong
reference, reports failures immediately with the task's name, releases on completion:

- `_cam_close()` in `main.py` — a failure left the camera streaming, silently
- `_save_session_summary()` — a failure lost the session memory, silently
- `dashboard._serve_alias()` — the port+1 fallback phones are told to type manually; if it fails
  to bind, the URL silently never answers

Not applied wholesale: rewriting 29 call sites would have been churn with real regression risk
for no behavioural gain.

### `file_processor`: three broken branches

1. **Every CSV action failed.** `pd.read_csv(..., errors="replace")` — pandas has no `errors`
   parameter (it is `encoding_errors`), so `info`, `stats` and `analyze` all returned
   "Could not read file: read_csv() got an unexpected keyword argument 'errors'". Untested
   because pandas is an optional dependency that was not installed in this environment.
2. **Asking a text file for its text wrote a copy next to it.** The branch compared
   `file_type != "txt"`, but `_detect_type()` returns `"text"` for `.txt/.md/.log`, so the inline
   return was unreachable and the tool wrote `notes_extracted.txt` instead of answering.
3. **An unknown action sent the model a prompt with no task in it** — literally
   `"\n\n<document>"` — and `translate` was implemented nowhere (the map only had
   `translate_hint`, which summarises rather than translates). The action is now resolved
   *before* the prompt is formatted, `translate` exists (using the instruction as the target
   language, defaulting to English), and anything unrecognised still passes its verb through.

Also: `word_count` counted newlines rather than lines, so a file without a trailing newline
reported one line fewer than it has.

Note: CSV/Excel still require `pip install pandas` — it stays optional by design, and the tool
says so plainly.

### Guards added

- `tests/test_tasks.py` (5) — failure is reported with context, successful tasks release,
  spawned work survives `gc.collect()`, `on_error` fires, `cancel_all()` cancels.
- `tests/test_file_processor.py` (10) — real `.txt`/`.csv`/`.xlsx`/`.docx` fixtures, prompt
  construction captured through a fake model, type detection for `.txt/.md/.log`.

Suite: 50 tests.

---

# Pass 5 — `browser_control`, and the persona's leftover language

## What was tested, and what could not be

`playwright install chromium` fails here: the browser binary is fetched from
`cdn.playwright.dev`, which this sandbox cannot reach. So **no browser was ever launched** and
nothing below claims otherwise. The session layer was reviewed by reading it (one asyncio loop per
browser in a daemon `BrowserThread-<name>`; `run()` marshals coroutines over
`run_coroutine_threadsafe(...).result(timeout)`); everything that decides *what* is launched was
tested with a faked session instead.

## `_normalize_url` mangled two URLs that matter

It prefixed `https://` and appended `.com` based on the presence of a dot alone:

- `localhost:8000` → `https://localhost:8000.com` — the address of this repo's own dashboard.
- `about:blank` → `https://about:blank.com`, which also made `_open_native`'s
  `if url == "about:blank"` guard unreachable.

Now any URL that already carries a scheme is returned untouched, and loopback/private hosts
(`localhost`, `127.x`, `10.x`, `192.168.x`, `172.16–31.x`) keep plain `http` with their port.

## `_SessionRegistry.close_one` ignored aliases — and could raise

`has()`, `get()` and `switch()` all resolved `_ALIASES` (`"google chrome"` → `"chrome"`).
`close_one()` passed the raw name to `dict.pop`, so:

- `has("google chrome")` said *yes*, `close("google chrome")` answered
  "No active session for: google chrome" and left the session running, still holding its thread
  and its profile lock;
- `sess.close()` was called outside any `try`, so a browser that hung on close
  (`concurrent.futures.TimeoutError`) escaped `browser_control()` entirely and left
  `_active_browser` pointing at a session that no longer existed.

Both fixed: the name is canonicalised like everywhere else, the session is deregistered before it
is closed, and a failing close is reported instead of raised.

Note: the registry lock is still held across `_BrowserSession.start()` (up to a 20 s readiness
wait). That is a latency smell, not a correctness bug, and is left in the backlog.

## The schema advertised an `incognito` parameter nothing read

`TOOL["parameters"]["properties"]["incognito"]` existed and no code path ever looked at it. A model
asked for "open this in incognito" would have been handed the user's **real, logged-in profile**,
silently — the opposite of what was asked, with no error to notice. Implementing a second launch
path (`launch()` + `new_context()` instead of `launch_persistent_context()`) could not be verified
here without a browser binary, and shipping unverified launch code as "incognito works" would be
exactly the kind of claim this log exists to avoid. The parameter is removed so the schema cannot
promise what the code does not do; the feature request is in `docs/BACKLOG.md`.

A test now enforces the general rule: every declared parameter must be read somewhere, and every
action the description advertises must be routed.

## Foreign-language residue in the persona

The Hindi speech protocol was concatenated into **every** system prompt, and the address line
always carried "(or 'बॉस' in Hindi)". Every user paid those tokens and was told to answer in a
language most of them had not chosen — the fork author's, baked into the assistant's persona.

The language-dependent text now lives in `core/persona.py` as pure functions
(`normalize_language`, `speech_protocol`, `address_line`), driven by
`memory.identity.language`; English users get no extra block and no other script. The Hindi
*feature* is intact — a user who sets their language to Hindi still gets the protocol and the
localised greeting — and adding another language is one dictionary entry.

Also swept: a Turkish error string in `browser_control` ("bu platformda … desteklenmiyor"), three
Turkish trigger examples in `video_player`'s tool description, and a Turkish sample word in a
`main.py` comment. Kept deliberately: `core/viseme.py`'s Turkish phoneme mappings, Steam's
localised dialog labels in `game_updater`, and the multilingual keyword list in
`background_monitor` — those are locale support, not residue.

## Guards added

- `tests/test_browser_control.py` (17) — URL normalisation table, registry state machine with a
  faked session (alias close, hung close, listing, single-use native URL), schema/route
  consistency, and the persona delegation.
- `tests/test_persona.py` (12) — language aliases, English gets no protocol, Hindi does, address
  line composition with and without a user name.

Suite: 79 tests.
