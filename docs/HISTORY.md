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

---

# Pass 6 — the memory store, i.e. the one file that is not replaceable

`scripts/doctor.py` was run first, on a genuinely broken machine (no PortAudio, no DISPLAY, no
libGL): it reported 4 FAILs, 17 WARNs and named every action file that failed to import, one per
line. It is honest, so the first-run path was not where the bugs were. The memory store was.

Everything below was reproduced against a temporary `long_term.json` before it was fixed.

## A fact could be written, and then be invisible

`save_memory` takes its category from the model as free text, and the handler passed it straight
into `update_memory()`. Any category outside the six known ones became a new top-level key — and
`format_memory_for_prompt()` reads only the known categories, for both the shown entries *and* the
`[ALSO REMEMBERED]` index. Measured: `{"work": {"employer": ...}}` was written to disk, never
appeared in the prompt, never appeared in the index, and could not be recalled unless the model
happened to guess the keyword. The tool answered "ok". `remember()` had always clamped an unknown
category into `notes`; `update_memory()` — the path the model actually reaches — did not.

Now `update_memory()` canonicalises at the choke point (`_canonical_update`), so an invented
category is kept as a `notes` entry: visible, indexed and recallable instead of silently dead.
Both `main.py` handlers go through `remember()` as well.

## `category="sessions"` destroyed the session summaries

`sessions` is a *list* in the same file. Writing a dict into it replaced the list, and the next
`save_session_summary()` saw a non-list, reset it to `[]`, and the previous summaries — the thing
that makes the assistant remember yesterday — were gone. Reproduced: "Talked about the rover
project" disappeared after one stray save. Canonical routing sends that key to `notes`, so the
list cannot be overwritten.

Related: a bare string for a whole category (`{"notes": "hates cilantro"}`) replaced that entire
category. It now becomes a `note` entry and the rest of the category survives.

## `recall_memory("sister_name")` answered "Nothing stored"

The schema tells the model that keys are snake_case, and the prompt's index shows them humanised
("sister name"). `search_memory()` split the query on non-word characters — and `_` counts as a
word character — so the exact key scored zero against every entry:

    recall('sister_name') -> "Nothing stored about 'sister_name'."
    recall('sister')      -> "relationships/sister name: Ada"

The lookup that exists to stop the assistant saying "I don't know" could be defeated by using the
key it was handed. Underscores are now word separators in the query.

## An unreadable store was deleted by the next save

`load_memory()` returns empty memory when the JSON cannot be parsed — correct, the app must start
— but the following save then wrote a fresh file over it. Any chance of salvaging the bytes by
hand was gone. The unreadable file is now renamed to `long_term.corrupt-<timestamp>.json` and
named in the log; a valid-but-wrong-shaped file (a list, a string) is treated the same way.
`.gitignore` covers the backups because they are still personal data.

## Guards added

- `tests/test_memory_manager.py` (23) — category routing, session-list survival, bare-string
  categories, key-vs-humanised recall, empty/wrong-shaped/corrupt stores, trim order and its
  notification, `remember()`/`forget()`.

Suite: 102 tests.

---

# Pass 7 — the first five minutes: config, keys and the setup gate

The README's quickstart says `cp config/api_keys.json.example config/api_keys.json` and paste your
key. Reproduced exactly that: the resulting file left `get_ai_provider()` returning `""` and
`is_configured()` returning `False`. Following the instructions produced a config the app does not
believe in.

## The example file and the README described a schema nothing reads

They said `"provider": "gemini"` and `"model": ...`. The code asks for `ai_provider` and
`ai_model`. There is no alias — the example was simply wrong, which is why the setup overlay
appeared even after a correct-looking copy. Both the file and the README block now carry the real
names, and say plainly that they are not aliases.

`ui._on_setup_done()` also wrote its overlay's transport keys (`provider`, `model`) into the config
alongside the canonical ones, which is how a second name for the same setting got established in
the first place. They are dropped before the file is written.

## A placeholder counted as a working key

The "may we start?" test was `len(key) > 3`, so the shipped placeholder
`YOUR_GEMINI_API_KEY_HERE` passed it. The app started normally, then met "API key not valid" out
loud — mid-sentence, after the greeting. `looks_like_placeholder()` now recognises the strings we
ship and the shapes people type (`your_…`, `<…>`, `changeme`, `xxxxxx`, `example`), so an
untouched key means "not configured" and the setup screen appears instead.

## Three providers could never be configured

`get_provider_key()` derived the field name as `f"{provider}_api_key"`. The setup screen writes
`anthropic_api_key` for Claude, `nvidia_api_key` for NVIDIA NIM and `opencode_api_key` for
OpenCode Zen. So for those three the key was saved, never found, the config reported itself
unconfigured on every launch — and every request would have gone out with an empty key. A
`_PROVIDER_KEY_FIELDS` map now matches what is written, and `llm_client` (which calls the same
function) is fixed by the same change.

## The gate demanded `os_system`, which nothing needs

Every consumer already falls back to platform detection (`config.get_os()`,
`actions/computer_control.py`, `screen_processor`, `send_message`). Requiring it in the gate meant
a good config without that key re-opened the setup overlay *on every launch*. It is no longer
required.

## One rule, three copies — and they had drifted

`config_manager.is_configured()`, `ui._check_config()` and `scripts/doctor.py` each implemented
"is this configured?" separately. `is_configured()` had no callers at all; the other two had
diverged from it (one demanded `os_system`, the other read the wrong key field for exactly the
three providers above — a correctly configured Claude user was told their key was missing). Now
`ui._check_config()` delegates to `is_configured()`, and `doctor.py` delegates to
`is_configured()` + `looks_like_placeholder()`. Verified on a real run: a copied example reports
`FAIL gemini API key — missing or still the placeholder` plus `WARN not usable yet`, and a Claude
config reports `PASS claude API key — present`.

## Two smaller ones on the same path

- `get_ai_model()` returned `""` for a whitespace-only `ai_model` (the truthiness test ran before
  `.strip()`), which put an empty model name on a provider that has a default.
- `main.py`'s unified and Telegram paths fell back to `"ollama"` when no provider was set, while
  `llm_client` and `get_provider_key()` fall back to `"gemini"`. A user with a Gemini key and no
  provider name was silently pointed at a local server that is not running. Both sites now say
  `"gemini"`.

## Guards added

- `tests/test_config_manager.py` (15) — the shipped example is a config the code understands and
  is not mistaken for a working key; the configured/unconfigured matrix; per-provider key lookup
  for all eight providers the setup screen offers; placeholder recognition; whitespace model
  names; and an assertion that `main.py` and `llm_client` agree on the default provider.

Suite: 117 tests.

---

# Pass 8 — the dashboard's certificate: existence is not proof

Every install generates its own self-signed TLS pair on first run. Reproduced what a crash during
that generation leaves behind — `ultron.crt` written halfway:

```
_ssl_enabled()  -> True      # the QR code keeps saying https://
_ensure_certs() -> True      # nothing thinks there is a problem
load_cert_chain -> SSLError: [SSL] PEM lib
```

uvicorn then refused to bind, the failure was a single stdout line (`Server on port 8000
unavailable`), and the Remote Control panel went on handing out a URL for a port that answered
nothing — for the rest of the session. Both checks asked `Path.exists()`.

## What changed

`_tls_pair()` is now the single answer to "is HTTPS available?": it finds a key/cert pair and
proves it works with `ssl.SSLContext.load_cert_chain` — the same call uvicorn makes, so a True
here means the server actually starts. `_ssl_enabled()`, `get_url()`, `get_manual_url()`,
`_ensure_certs()`, `serve()` and the alias server all go through it, so the UI cannot advertise a
port the server never bound.

`_ensure_certs()` keeps a pair only if it loads, and regenerates otherwise — including when the
certificate has expired. Expiry is a second, quieter failure: a pair can load perfectly and still
be rejected by Chrome with `NET::ERR_CERT_DATE_INVALID`, which is indistinguishable from "the
dashboard is broken" from the phone. Generated certs last ten years, so this only bites a
hand-supplied certificate, but checking costs one parse.

The legacy `jarvis.*` pair is still honoured, and now validated: if it is broken, `ultron.*` is
generated beside it rather than handed to uvicorn.

Also: the module docstring still described a plain-HTTP-only server. It now says what the code
does.

## Guards added

- `tests/test_dashboard_certs.py` (14) — first run produces a pair that loads, 0600 on the key,
  SAN covering `localhost` and `127.0.0.1`, a validity measured in years; half-written cert and
  half-written key are neither trusted nor left in place; an expired certificate is replaced; the
  legacy pair is honoured without generating a second one; and the URL helpers say `http://` when
  the pair cannot be used.

Suite: 131 tests.

---

# Pass 9 — one provider catalogue, an `ultron` command, and a model panel

Planned first (`docs/PLAN.md`) from four answers: a launcher script rather than a package, launch
with the last-used model, non-Gemini providers speaking through the local voice loop, curated
model lists with a typable custom name, and all eight backlog items.

## Three lists of providers became one

`ui.py` had the catalogue, `memory/config_manager.py` had a key-field map, and
`core/llm_client.py` had the branches. `core/providers.py` now holds all of it — nine providers,
their curated models, defaults, key fields, docs links, aliases, and the realtime set — and
`ui.py` imports it. `save_ai_choice()` is the only writer of `ai_provider`; `set_ai_model()` and
`forget_key()` cover the rest, and `save_ai_provider()` remains as a deprecated alias.

The drift this removes was not hypothetical: the setup screen stored `anthropic_api_key` for
Claude while the reader derived `claude_api_key`, so three providers could never be configured
(pass 7), and `save_ai_provider()` had no callers at all — nothing could change the provider after
the first run without hand-editing JSON.

## `ultron` — and a doctor that works in a broken environment

`ultron.bat` (Windows, first-class) and `ultron` (POSIX, so the same command exists everywhere)
prefer `.venv` and fall back to `python`, forward every argument, keep the window open when the
app exits non-zero, and return the child's exit code.

Four flags: `--provider`, `--model` (session-only — a one-off launch must not rewrite the saved
choice), `--pick` (opens the AI MODEL panel), `--doctor`.

`--doctor` needed one structural change to be honest: `main.py` imports sounddevice and PyQt6 at
module level, so on a machine missing PortAudio the *diagnostic* died of the very problem it was
called to describe — reproduced here, exactly that traceback. The flag is now answered at the top
of `main.py`, before those imports. Verified in this sandbox, where PortAudio is genuinely absent:
`./ultron --doctor` produces the full report.

## Model selection in the HUD

New **◈ AI MODEL** panel: the current provider and model, a provider list, an editable model list
(curated suggestions, any typed name accepted), key and URL fields only where the provider needs
them, and a line explaining which voice path that provider uses. The stored key is never printed
back — the field is for replacing it.

Apply's behaviour lives in `core/providers.apply_choice()`, not in the widget, so the rule is
tested without Qt: switching to or from Gemini reconnects (the live session carries the model),
two non-Gemini providers do not (they are asked per utterance). The panel reports the decision
rather than deciding it.

## Multi-provider voice, said out loud

Live audio is a property of the *model*, not of Gemini alone: Gemini with a normal model already
ran the same local loop as everyone else. What was missing was honesty and a placeholder — the
loop was told `"default"` as a model name whenever none was set. `providers.resolve_model()` now
turns every empty or placeholder value into the provider's real default, and the session logs
which path is running (`Voice: local speech loop — mic → OLLAMA (llama3.2) → neural TTS`).

An unreachable Ollama now says *"Ollama is not reachable at http://localhost:11434. Start it
(ollama serve) or switch provider in the AI MODEL panel."* instead of surfacing a
ConnectionError.

## Bug found while wiring it

`_on_setup_done()` read the config file, wrote it, and only then stored the key — so the write
that came second was based on a snapshot taken before the first, and the provider's key field was
erased. The order is now: surrounding settings first, `save_ai_choice()` last, then re-read.

## Guards added

- `tests/test_providers.py` (34) — catalogue completeness, catalogue vs `llm_client` branches via
  AST, aliases, model resolution, session overrides, the single writer (including the corrupt
  config path), the CLI parser, `apply_choice`'s reconnect rule, and the Ollama message.
- `tests/test_launcher.py` (11) — both launchers forward arguments and prefer the venv, the window
  stays open on failure, `--doctor` is answered before `sounddevice` is imported, and a real
  subprocess run of it produces a report with no traceback.

Suite: 176 tests.

# Pass 9, part two — the backlog, item by item

Eight deferred items. Each is either fixed with a test or closed with the reason it is not a bug.

**1. `bounty_hunter` printed every price in dollars.** The detector's own pattern accepted
`$ € £ ₹ Rs`, then the report said `$80,000.00` for a page quoting `Rs 80,000` — right digits,
wrong money, stated as fact. `core/ui_currency.py` now owns that decision: a symbol found in the
source wins, otherwise the configured `currency_symbol` (default `$`), otherwise `$`. The symbol is
stored with the bounty, so the list view stays right weeks later. A Tunisian user can set `DT`.

**2. Dead locals.** `code_helper` base64-encoded every screenshot and threw the string away —
megabytes of work per screen-debug call. `bounty_hunter`'s `detected_title` and `android_bridge`'s
`lines` were never read. `quick_timer`'s had already gone. All removed.

Removing the first one deleted `_VALID_INTENTS` along with it (a slice from one `def` to the next
swallowed the constant between them). ruff's F821 caught it; `actions/code_helper.py` now holds the
set with a comment saying why it is checked.

**3. Legacy `jarvis_*` dashboard keys.** `login.html` wrote the token under *both* names, twice
each, in two places. It now writes `ultron_key`/`ultron_token` only. `app.html` still *reads*
`jarvis_token` so a phone paired before the rename is not logged out.

**4. Blocking I/O inside async code.** The upload handler wrote each 64 KB chunk to disk on the
event loop; a 500 MB upload is ~8000 blocking writes, which is a phone freezing while it saves its
own file. Writes go through `asyncio.to_thread` now. The other four ruff ASYNC hits were measured
and left alone: `Path.exists()`, a buffered single-write `open()`, and `os.system("rundll32 ...
SetSuspendState")` on an explicit *suspend the machine* request — where blocking the loop is the
correct behaviour, because the loop is about to stop existing. Changing them would be lint-driven
churn around microsecond calls.

**5. The wake phrase said "Hey Jarvis".** It has to: openwakeword's pretrained model *is*
`hey_jarvis`, and a model file cannot be renamed into a phrase. So both halves are settings —
`wake_model` and `wake_phrase` — saved together by `save_wake_word()`, with the built-in pair as the
fallback so an empty save cannot freeze the current value in. Point them at a custom model and the
assistant stops asking for a phrase nothing listens for.

**6. `pygetwindow` on Linux.** Already guarded; closed as fixed in pass 7 (the import sat outside
its `try`, which made `chronos_predictive` unimportable off Windows).

**7. Browser privacy.** `browser_control` could only ever drive the user's real profile or the
persistent ULTRON one — there was no way to browse without touching their cookies. `private: true`
now opens a throwaway profile via `mkdtemp`, deletes it on close, and deliberately has **no**
fallback to the real profile: quietly browsing with someone's cookies is the one thing a private
session must never do, so a failure is reported instead of retried.

**8. Windows OCR.** `_extract_text_from_image` built a PowerShell script, discarded it inside a
`try` block that could not fail, and returned `""` — so on Windows (where pytesseract is almost
never installed) every screen triage reported "no text" and then "no errors found". The
`Windows.Media.Ocr` recogniser is now actually run, with the `AsTask`/`Await` bridging, a 20 s
internal and 30 s process timeout, and `""` on any failure.

## Verified / unverified

Verified by execution here: currency parsing and formatting, the stored symbol, the launch
ordering, deletion of a private profile, OCR's non-Windows and failing-recogniser paths, and every
test in `tests/test_backlog.py` (26). Suite: 201 tests.

**Unverified, by necessity:** the PowerShell OCR script has never been run (no Windows), and
`private: true` has never opened a browser (no Playwright/Chromium here). Both are implemented and
reviewed, not exercised. Treat them as "written, not proven".

# Pass 9, part three — checking the wiring without Qt

The AI MODEL button was wired in `MainWindow`, but Qt could not be started here to prove it. A
wrong guess (the handler on a sibling widget class) would have raised `AttributeError` on the first
click and nothing earlier, so the wiring is now checked by reading the file, in
`tests/test_ui_wiring.py` (9 tests):

- every `self._x.connect(self._y)` in `ui.py` names a method that exists — private names only,
  skipping widgets assigned in `__init__` and inherited Qt slots like `.hide`;
- the AI MODEL button and its handler are in the same class body (`MainWindow`), not merely
  somewhere in the file;
- `on_ai_provider_change` is initialised before `if reconnect and self.on_ai_provider_change`;
- `_ai_model_sig` exists, is connected, and the overlay keeps a strong reference
  (`self._ai_overlay`) so it is not garbage-collected mid-click;
- no `UltronUI` wrapper emits a signal `MainWindow` never declares;
- the panel reads `core.providers` and does not carry a second copy of the catalogue.

The tests were checked against a deliberately broken copy of `ui.py` (`_open_ai_model_TYPO`): the
handler test failed and named the line. They are not a substitute for opening the window — nothing
here claims the GUI was rendered.

Suite: 211 tests, `compileall` clean, ruff bug-rules clean.
