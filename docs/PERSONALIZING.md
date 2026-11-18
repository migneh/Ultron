# Personalising Ultron

Everything in this file is a supported way to change how Ultron behaves **without editing the
core**. If you find yourself patching `main.py` or `ui.py` for something on this list, you are
doing it the hard way.

---

## 1. Identity, colours, voice

`config/api_keys.json` (git-ignored) drives the basics. The setup screen writes it, but it is a
plain JSON file you can edit directly, then restart.

```json
{
  "assistant_name": "Ultron",
  "user_name": "Boss",
  "ui_color": "#ff0008",
  "voice_name": "Ultron",
  "voice_rate": "+15%",
  "ultron_voice_warp": true,
  "voice_warp_intensity": 0.55,
  "hud_style": "face"
}
```

| Key | Effect |
| :--- | :--- |
| `assistant_name` | Name used in the HUD title, window title, log tags and the persona prompt |
| `user_name` | How it addresses you ("Boss" by default) |
| `ui_color` | Primary HUD accent, hex |
| `voice_name` / `voice_rate` / `voice_pitch` | Voice selection and delivery pace |
| `ultron_voice_warp` / `voice_warp_intensity` | The DSP "chassis" filter — `false` for a clean voice |
| `hud_style` | `face` (animated head) or `core` (reactor) |

> `ui_color` and the rest are also editable from **⚙** in the app; the file and the UI write to
> the same place.

## 2. Personality

`core/prompt.txt` is the entire behavioural contract, in plain text. Four placeholders are filled
at startup: `{assistant_name}`, `{platform}`, `{capabilities}`, `{limits}`.

The useful pattern for making it yours:

- **Tone** lives in `[VOICE & CADENCE]` — rewrite freely.
- **Rules** live in `[JUDGEMENT & WORKING STYLE]` — add your own as bullets. Be explicit; vague
  instructions get ignored.
- **Ban list** — the "never say this" section is what kills chatbot voice. Extend it with
  anything that grates on you.

Keep `{capabilities}` and `{limits}` placeholders: they are substituted with the tools actually
discovered at runtime, so the model never claims a capability that is missing.

## 3. Your own tools

Two routes, both one file:

**Bundle a tool** — `actions/my_tool.py`:

```python
TOOL = {
    "name": "my_tool",
    "description": "What it does, and when to call it. This text is what routes the call.",
    "parameters": {"type": "OBJECT", "properties": {}},   # Gemini schema
    "handler": my_tool,
}

def my_tool(parameters: dict, player=None, speak=None) -> str:
    return "Done."     # returned text is spoken back
```

Restart, and it is registered. `open_app.py` is the reference implementation.

**Drop-in plugin** — copy `plugins/_template.py`, rename it so it does not start with `_`, fill
in `PLUGIN` and `run()`. Same discovery mechanism, kept separate from bundled actions.

Either way the loader validates the name, the schema and the handler, logs any problem, and
skips that one file rather than taking the app down.

## 4. Workspace moods

`memory/workspace_presets.json` maps a mood to apps, URLs, audio level, brightness and lighting.
Each entry has `aliases` (the phrases that trigger it — add your own, any language), `apps`,
`urls`, `volume`, `brightness` and `lighting`. Add a new key and it becomes a new mode.

## 5. Wake word

Default phrase is **"Hey Jarvis"**, because that is a pretrained `openwakeword` model
(`hey_jarvis`). Neither string is cosmetic — the model name must match a file on disk, and the
phrase must match what that model was trained on.

Both live together at the top of `core/wake_word.py`:

```python
WAKE_MODEL  = "hey_jarvis"     # the file openwakeword loads
WAKE_PHRASE = "Hey Jarvis"     # what the UI tells you to say
```

Every spoken message ("Say '…' to wake me") is interpolated from `WAKE_PHRASE`, so changing
these two lines is the whole job:

1. Pick or train a model with `openwakeword`; drop the `.onnx`/`.tflite` into
   `openwakeword/resources/models/`.
2. Point `WAKE_MODEL` at its file stem and set `WAKE_PHRASE` to the phrase it detects.

If you would rather not deal with models, leave wake word disabled (⚙ → WAKE WORD) and use the
hotkey or the push-to-talk path.

## 6. Memory

Memory lives in SQLite under `memory/` and is git-ignored: `cerebro_graph.db` (knowledge graph
with embeddings) and the workspace recall DB. To start clean, stop the app and delete those
files — a fresh one is created on next launch.

## 7. Phone dashboard

`dashboard/` serves a FastAPI app for the phone remote; pair it by scanning the QR from the app.
Certificates are generated locally into `config/certs/` on first use (self-signed; your phone
will warn once). Ports and alias behaviour are in `dashboard/server.py`.

## 8. What to edit where, at a glance

| Goal | File |
| :--- | :--- |
| Name, colour, voice, HUD | `config/api_keys.json` |
| Personality, rules, ban list | `core/prompt.txt` |
| New capability | `actions/<name>.py` or `plugins/<name>.py` |
| Moods and app sets | `memory/workspace_presets.json` |
| Wake phrase | `core/wake_word.py` |
| HUD animations per task | `core/task_animator.py` |
| Voice DSP chain | `core/tts.py` |
| Dashboard UI | `dashboard/static/*.html` |
