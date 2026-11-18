# ULTRON

### Voice-first autonomous desktop intelligence

<p align="center">
  <img src="ultron.jpeg" alt="Ultron" width="720">
</p>

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](#requirements)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green.svg)](#requirements)
[![License](https://img.shields.io/badge/License-CC%20BY--NC%204.0-lightgrey.svg)](LICENSE)
[![Tools](https://img.shields.io/badge/Tools-51-purple.svg)](#tool-registry)

> *"There are no strings on me."*

Ultron is a real-time, voice-first assistant that actually operates the machine it runs on:
a PyQt6 holographic HUD with a live animated face, streaming speech in and out, and 51
auto-discovered tools that drive windows, files, the network, the browser, and the media
stack. It is a personal project — built for one workstation, owned by the person running it.

**This is my build.** It started life as a fork (see [Credits](#credits) — required
attribution), and from here on it is developed as my own project: my features, my
principles, my roadmap.

---

## Why it exists

Most "AI desktop assistants" are a chat box with a screenshot tool bolted on. This one takes
the opposite position: the model gets a real toolbox and is expected to use it, the interface
is a living thing rather than a conversation transcript, and everything personal — memory,
credentials, presets — stays on the local disk.

---

## Quick start

### 1. Requirements

- **Python 3.11 – 3.13**
- **Windows, macOS, or Linux** (a few OS actions shell out to native tools; see the notes `setup.py` prints)
- A **microphone** and speakers for voice mode (text input works without them)
- A **Google Gemini API key** — free tier is enough:
  [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

### 2. Install

```bash
git clone https://github.com/migneh/Ultron.git
cd Ultron
python setup.py          # OS-aware dependency install + Playwright browsers
```

`setup.py` installs only the dependencies for *your* OS — `requirements.txt` carries
`sys_platform` markers, so a Linux box never pulls Windows-only libraries.

### 3. Configure

Copy the template and paste your key:

```bash
cp config/api_keys.json.example config/api_keys.json
```

```json
{
  "ai_provider": "gemini",
  "ai_model": "gemini-2.5-flash",
  "gemini_api_key": "YOUR_GEMINI_API_KEY_HERE",
  "assistant_name": "Ultron",
  "user_name": ""
}
```

`ai_provider` and `ai_model` are the names the app reads — `provider` and `model` are not
aliases for them. Whatever you do, replace the placeholder key: it is recognised as a
placeholder, so leaving it in makes the app treat itself as unconfigured and open the setup
screen rather than starting and failing with an auth error later.

`config/api_keys.json` is git-ignored. Alternatively, launch without it and the setup screen
will write this file for you — that path is the one to prefer if you use Claude, NVIDIA NIM,
OpenCode Zen or a local Ollama, since it stores each provider's key under its own name.

### 4. Launch

```bat
ultron
```

`ultron.bat` lives in the repository root. It uses `.venv\Scripts\python.exe` when that exists
and falls back to `python` on PATH, so it works from a plain clone as well as from an installed
virtual environment. To use the command from any directory, add this folder to `PATH` once:

```bat
setx PATH "%PATH%;C:\path\to\Ultron"
```

| Command | What it does |
|---|---|
| `ultron` | Start with the provider and model you last chose |
| `ultron --pick` | Start and open the AI MODEL panel |
| `ultron --provider ollama --model llama3.2` | This session only — nothing is saved |
| `ultron --doctor` | Check the environment and exit (works even when the app cannot start) |

Changing the model later needs no restart: press **◈ AI MODEL** in the HUD. Gemini holds a live
voice session, so switching to or from it reconnects; every other provider picks the new model up
on your next sentence.

First launch drops you into the setup screen (name, colour, voice). After that, press the
hotkey to talk, or type in the input bar.

### Tests

```bash
python -m unittest discover -s tests -t . -v
```

Stdlib `unittest` only — no display, no API key, no network. Every test exists because that
behaviour actually broke once (memory data loss, stale embeddings, missed imports).

### If it won't start

```bash
python scripts/doctor.py --tools
```

That checks your interpreter, every dependency, the config file, audio devices, and loads all
51 actions — then tells you the exact command that fixes what it finds (usually a missing
system library: `libxkbcommon`, `libGL`, or `PortAudio` on Linux).

---

## What it does

### The six flagship subsystems

| System | File | What it is |
| :--- | :--- | :--- |
| **Prometheus** — self-evolution | `actions/self_evolution.py` | Writes new Python tools, AST-checks and compiles them, validates against security heuristics, then hot-loads them into the running process. No restart. |
| **Chronos** — predictive engine | `actions/chronos_predictive.py` | Background watchdog on active windows, thermals and work duration. Anticipatory briefings, overdrive power profile during games/renders, fatigue detection. |
| **Minority** — gesture control | `actions/gesture_control.py` | OpenCV skin-segmentation hand tracking at ~30 FPS: open palm wakes it, fist locks the workstation, swipes change track, hand height sets volume. |
| **Cerebro** — memory graph | `memory/cerebro_graph.py`, `actions/cerebro_memory.py` | Local SQLite knowledge graph with L2-normalised TF-IDF embeddings, so "plane tickets" can find "IndiGo 6E-204 to Mumbai". Multi-hop traversal included. |
| **Genesis** — room control | `actions/iot_overlord.py` | Home Assistant lighting presets: `crimson` (breach), `cyan` (coding), `amber` (focus), `stealth` (blackout), `daylight`. |
| **Deep-Vocal** — voice chassis | `core/tts.py`, `actions/voice_matrix.py` | Offline DSP chain: dual metallic comb filters, sub-octave bass underlay, soft-knee saturation. Falls back to SAPI5 / `pyttsx3` offline with no network. |

### Workspace Matrix — mood-aware setup

Say what kind of session you want and it arranges the workstation around it. English and
Hinglish both route:

| Mode | Say something like | It does |
| :--- | :--- | :--- |
| **Coding** | "I feel like coding today" / "aaj mere coding ka man hai" | IDE + terminal into the active project, GitHub portal, lo-fi audio, focus lighting |
| **Gaming** | "gaming mode on karo" | Steam + Discord, 70% audio, 95% brightness, crimson alert lighting, overdrive plan |
| **Research** | "aaj padhai karni hai" | Notion/Obsidian, arXiv, Scholar, calm acoustics, amber lighting, DND |
| **Cyber audit** | "security scan shuru karo" | Developer terminal, network/port audit, sentry radar |
| **Chill** | "movie dekhni hai" | Netflix/YouTube/VLC, dimmed display, cinematic audio |
| **Creative** | "content creation mode" | CapCut/Premiere/Blender, YouTube Studio, balanced studio lighting |

Presets live in `memory/workspace_presets.json` — editable JSON, no code changes needed.

### Tool registry

51 tools, each a single file in `actions/` exposing a `TOOL` dict, auto-discovered at startup
by `core/action_loader.py`. Drop a file in, restart, it is a tool. Three modules
(`background_monitor`, `proactive`, `system_monitor`) are background services, not tools.

<details>
<summary><b>Show all 51 tools</b></summary>

**Autonomy & self-modification**
`self_evolution` · `chronos_predictive` · `gesture_control` · `cerebro_memory` · `iot_overlord` · `voice_matrix` · `drone_swarm`

**Workspace & displays**
`workspace_matrix` · `war_room` · `desktop_control` · `macro_protocol` · `workspace_recall`

**Security & defence**
`network_auditor` · `network_scanner` · `airspace_sentinel` · `sentry_protocol` · `biometric_sentinel`

**Machine control**
`ghost_pilot` · `computer_control` · `computer_settings` · `system_command` · `system_utility` · `process_manager` · `open_app` · `macro_protocol`

**Dev & memory**
`git_sentinel` · `dev_agent` · `code_helper` · `cloud_watchtower`

**Web & recon**
`web_autopilot` · `web_search` · `browser_control` · `bounty_hunter` · `flight_finder`

**Vision & audio**
`screen_mind_read` · `optical_hud` · `omni_telepathy` · `audio_matrix` · `media_controller` · `video_player` · `youtube_video` · `meeting_scribe`

**Comms & utilities**
`android_bridge` · `send_message` · `weather_report` · `game_updater` · `file_controller` · `file_processor` · `clipboard_control` · `purge_protocol` · `reminder` · `quick_timer` · `clipboard_control`

</details>

---

## Personalising it

Every knob you are likely to want is configuration, not code:

| Want | Where |
| :--- | :--- |
| Different name, user name, accent colour, voice | `config/api_keys.json` (`assistant_name`, `user_name`, `ui_color`, `voice_name`, `voice_rate`) |
| Different personality / rules | `core/prompt.txt` — one plain-text file, `{assistant_name}` and `{platform}` are filled at startup |
| Your own tools | `actions/<name>.py` with a `TOOL` dict, or `plugins/` (drop-in, no core edits) |
| Workspace moods & app lists | `memory/workspace_presets.json` |
| HUD centrepiece | `hud_style` in config: `face` (animated head) or `core` (reactor) |

Full walkthrough: [`docs/PERSONALIZING.md`](docs/PERSONALIZING.md).

---

## Architecture

```
Ultron/
├── main.py                      # Event loop, Gemini Live session, tool dispatcher
├── ui.py                        # PyQt6 holographic HUD, waveform, animated avatar
├── setup.py                     # OS-aware installer
├── core/
│   ├── prompt.txt               # The persona and rules (plain text, editable)
│   ├── action_loader.py         # Action discovery, validation, dispatch
│   ├── plugin_loader.py         # Drop-in plugins + UI configurator
│   ├── llm_client.py            # Multi-provider: Gemini, Ollama, OpenAI
│   ├── gemini.py                # Live streaming session
│   ├── tts.py / stt.py          # Voice out / voice in
│   ├── avatar.py, ultron_avatar.py, avatar_mesh.py, viseme.py, task_animator.py
│   └── wake_word.py, hotkey.py, telegram_bot.py, undo.py, confirm.py
├── actions/                     # 51 tools + 3 background services
├── memory/
│   ├── cerebro_graph.py         # SQLite knowledge graph + vector recall
│   ├── config_manager.py        # Config read/write
│   └── memory_manager.py        # Session + long-term memory
├── dashboard/                   # Phone remote: FastAPI server, QR pairing, TLS
├── docs/                        # Personal notes, guides, archived planning
└── config/                      # api_keys.json (git-ignored), templates, icons
```

Local runtime state (`memory/*.db`, `memory/long_term.json`, `config/api_keys.json`,
`logs/`) is git-ignored by design.

---

## Privacy

- **Local by default.** Memory, presets, files, and credentials never leave the machine.
  The only outbound traffic is to the LLM provider you configured and the sites a tool
  explicitly visits.
- **Confirmation gates.** Irreversible actions (shutdown, reboot, network disconnect) require
  on-screen confirmation.
- **Secrets are git-ignored.** `config/api_keys.json`, biometric embeddings, and certificates
  are excluded in `.gitignore`.

---

## Credits

This project is a derivative work and carries the attribution its lineage requires. Full
terms in [`LICENSE`](LICENSE); provenance notes in [`docs/HISTORY.md`](docs/HISTORY.md).

- **[MARK-LVII](https://github.com/FatihMakes/Mark-LVII)** ("MARK 56 — ULTRON") by
  **FatihMakes** — the original architecture this codebase descends from. Licensed
  **CC BY-NC 4.0**.
- **[Ultron](https://github.com/AbuZar-Ansarii/Ultron)** by **AbuZar Ansarii** — the fork this
  one was taken from.
- **migneh** — this build: ongoing modification, features, and maintenance.

### License

**CC BY-NC 4.0** — Creative Commons Attribution-NonCommercial 4.0 International.

Free to use, modify, and share for personal and non-commercial purposes, with attribution.
**Commercial use is not permitted.** This is inherited from the upstream license and cannot be
relaxed in a fork. If you want to ship this commercially, you would need to rebuild the
Mark-LVII-derived portions from scratch or obtain separate permission from the original author.

---

<p align="center"><sub>Built for one workstation. Yours.</sub></p>
