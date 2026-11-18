# Plan — provider choice, an `ultron` command, and model selection

Written before the work, from four questions answered by the user. It is the record of what was
agreed; `docs/HISTORY.md` records what was actually found while building it.

## Decisions taken

| Question | Answer | Consequence |
|---|---|---|
| What is `ultron`? | A launcher script in the repo (`.bat` on Windows) | No packaging, no `pip install -e .`. The command runs from the checkout, using `.venv` when present. |
| Launch behaviour | Straight in with the last-used model | No terminal questionnaire. The picker lives in the HUD. |
| `--pick` | Kept, but means "open the AI MODEL panel" | One flag, no terminal UI. |
| Flags | `--pick`, `--provider`, `--model`, `--doctor` | Unknown flags fail loudly instead of being ignored. |
| Multi-provider for voice | Non-Gemini providers speak through the local loop | Gemini Live stays Gemini-only. Everything else: STT → provider → edge-tts. |
| Model lists | Curated, plus a typable custom name | No API calls at selection time; any model name is accepted. |
| Mid-session change | Reconnect only when Gemini Live is involved | Non-Gemini providers read the model per utterance, so the next sentence already uses it. |
| Leftovers | All eight backlog items | Three of them cannot be verified here and will be marked as such rather than claimed. |
| Target OS | Windows (the user's machine) | The `.bat` is the first-class launcher; POSIX paths still work. |

## Phase A — one catalogue, one writer

**Why:** the provider list existed as a dropdown in `ui.py`, a key-field map in
`memory/config_manager.py`, and a branch structure in `core/llm_client.py`. The copies drifted:
the setup screen could store a key under a name nothing read (`anthropic_api_key` for `claude`),
and `save_ai_provider()` had no callers at all, so nothing could change the provider after the
first run without hand-editing JSON.

- `core/providers.py` — the catalogue (`PROVIDERS`, 9 entries), `KEY_FIELDS`, `REALTIME`,
  `DOCS`, `ALIASES`, and pure helpers: `normalise`, `models`, `default_model`, `key_field`,
  `needs_key`, `is_realtime`, `resolve_model`.
- `memory/config_manager.py` — `save_ai_choice()` becomes the only writer of `ai_provider`;
  `set_ai_model()` changes the model alone; `forget_key()`; `save_ai_provider()` kept as a
  deprecated alias.
- `ui.py` — the catalogue block is replaced by an import; the setup screen writes through
  `save_ai_choice()`.

**Tests:** the catalogue is consistent with what the client implements; every provider has a key
field and a docs link; aliases resolve; `resolve_model` never returns a placeholder; saving keeps
other keys; corrupt config is rewritten rather than silently dropped.

## Phase B — the `ultron` command

- `ultron.bat` — prefers `.venv\Scripts\python.exe`, falls back to `python`, quotes the path,
  forwards `%*`.
- `main.py` — `parse_args()` (pure, testable) and the four flags. `--provider` / `--model` are
  session overrides: they do not rewrite the user's config.
- `--doctor` runs `scripts/doctor.py` and exits with its status.

**Tests:** argument matrix including unknown flags; `--provider` does not touch the config file;
the `.bat` uses the venv when present and forwards arguments.

## Phase C — model selection in the HUD

- New `AiModelOverlay` in `ui.py`, following the existing `_HudOverlay` pattern: current
  provider/model at the top, provider combo, editable model combo (curated list + any typed name),
  key/url fields shown only when the provider needs them, an "Apply" that reports what happened.
- Decision logic lives in `core/providers.apply_choice()` so it can be tested without Qt:
  it returns `{reconnect: bool, message: str}` — reconnect iff Gemini Live is involved.
- A button beside WAKE WORD / TELEGRAM opens it. `ultron --pick` opens it at startup.

## Phase D — multi-provider voice that tells the truth

- `run()` routes every non-Gemini provider to the local loop (already partly true) and says so in
  the HUD instead of pretending Live is coming.
- Remove the `"default"` model placeholder; use `providers.resolve_model`.
- Ollama unreachable gets a plain-language message, not a stack trace.
- `core/gemini.py`'s text fallback already calls `llm_client`, so tools keep working.

## Phase E — the eight backlog items

Optical HUD's Windows OCR stub · blocking I/O in async paths · dead locals · `bounty_hunter`'s `$`
· the "Hey Jarvis" wake model · legacy `jarvis_*` dashboard keys · `pygetwindow` on Linux ·
`browser_control` incognito.

Three cannot be verified in this environment — the PowerShell OCR path (no Windows), incognito
(no browser binary), Linux window geometry (no Linux desktop). They will be implemented and
marked unverified in `docs/HISTORY.md`, never described as working.
