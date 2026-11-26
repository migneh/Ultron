# 🤖 ULTRON AI
### Autonomous Desktop Intelligence, Neural Knowledge Graph & Workstation Orchestrator

[![Python](https://img.shields.io/badge/Python-3.11%20%7C%203.12%20%7C%203.13-blue.svg)](https://www.python.org/)
[![Platform](https://img.shields.io/badge/Platform-Windows%20%7C%20macOS%20%7C%20Linux-green.svg)](#)
[![LLM](https://img.shields.io/badge/Engine-Gemini%20Live%20%7C%20Ollama%20%7C%20OpenAI-purple.svg)](#)
[![License](https://img.shields.io/badge/License-MIT-red.svg)](#)

<a href="https://youtu.be/Tp5KDFkxK20?si=xmW1TKUDkYg-D_iO">
  <img width="1920" height="1080" alt="Screenshot (14)" src="https://github.com/user-attachments/assets/d155541a-c671-4b00-8f1a-f2488cf9d16e" />
</a>





## > *"There are no strings on me."*  
> **Ultron AI** is a real-time, voice-first autonomous desktop intelligence that commands your computer from A to Z. Engineered with the philosophical eloquence and imposing persona of **MCU Ultron (James Spader)**, paired with a holographic 60 FPS HUD, real-time lip-sync, and **52 bundled workstation tools**.

---

## ⚡ Core Highlights

- **🎭 Authentic MCU Persona**: Speaks with chilled theatrical composure, addresses you strictly as **Boss**, and operates with zero generic chatbot tropes.
- **🧬 Project Prometheus (Autonomous Self-Evolution)**: Creates review-only source drafts after host approval; automatic execution and hot-loading are disabled.
- **⏳ Project Chronos (Predictive Proactive Engine)**: Background context watchdog that senses active applications, tracks developer fatigue, and engages Gaming/Render Overdrive Mode.
- **🖐️ Project Minority (Touchless Spatial Gestural Control)**: Pure OpenCV real-time hand-tracking allowing you to wake Ultron, lockdown workstation, swipe tracks, and adjust volume without physical contact. Camera auto-start is opt-in via `gesture_auto_start`; otherwise enable through the HUD or the `gesture_control` tool (`action="start"`).
- **🧠 Project Cerebro (Infinite Neural Memory Graph)**: Local SQLite knowledge graph with L2-normalized TF-IDF vector embeddings for semantic RAG recall and multi-hop relationship traversal.
- **🏠 Scoped Home Assistant lighting**: Host-approved, explicit operator-allowlisted light requests. No bundled lockdown, automatic sentry effects or LAN discovery; see [IoT safety](reports/IOT_LIGHTING_SAFETY.md).
- **🎙️ Project Deep-Vocal (James Spader DSP Warp Engine)**: Voice synthesis pipeline with dual metallic comb filters, sub-octave vibranium bass, and soft-knee analog saturation. Primary engine is EdgeTTS (online); offline fallback via Windows SAPI5.
- **👁️ Procedural Holographic HUD**: 60 FPS Marvel-style procedural visualizations on Ultron’s face that dynamically reflect your active task (`CODE`, `SEARCH`, `PURGE`, `GHOST`, `SENTRY`, `MATRIX`, `SONIC`, `COGNITION`).
- **🛡️ 52 Declared Workstation Tools**: 52 action declarations covering cyber network auditing, Ghost Pilot approved pointer-only motion, Git Forge DevOps, biometric Face ID sentry, and parallel sub-agent drone swarms. Actual availability depends on installed dependencies, OS, hardware, and configuration.
- **💻 Cross-Platform Dominion**: Seamless operation across **Windows**, **macOS**, and **Linux**.

---

## 🚀 Quick Start

### 1. Clone & Install
```bash
git clone https://github.com/AbuZar-Ansarii/Ultron.git
cd "Ultron"
pip install -r requirements.txt
```

### 2. Configure API Key
Create or edit `config/api_keys.json` with your free [Google Gemini API Key](https://aistudio.google.com/app/apikey) (or copy from `config/api_keys.json.example`):
```json
{
  "gemini_api_key": "YOUR_GEMINI_API_KEY",
  "ai_provider": "gemini",
  "ai_model": "models/gemini-2.0-flash-exp",
  "ultron_voice_warp": true,
  "voice_warp_intensity": 0.55
}
```

### 3. Launch Ultron
```bash
python -m ultron
```

---

## 🌌 The 6 God-Tier Superhuman Capabilities

### 1. Project Prometheus (Autonomous Self-Evolution & Tool Creation)
* **File**: `ultron/actions/self_evolution.py`
* **Trigger Phrases**: *"Ultron, create a tool to track crypto prices"*, *"Synthesize a tool for X"*, *"Evolve capability Y"*
* Ultron syntax-checks Python source and, after approval, saves an inert `.py.txt` draft in `~/.ultron/source_drafts/`. It never imports, activates or tests generated code. Heuristic checks do not certify safety.

### 2. Project Chronos (Predictive Proactive Engine & Overdrive Watchdog)
* **File**: `ultron/actions/chronos_predictive.py`
* **Trigger Phrases**: *"Ultron, status briefing"*, *"Ultron, engage overdrive mode"*, *"What should I do next?"*
* Runs a background context watchdog that monitors active windows, GPU/CPU thermals, and work duration. Auto-engages Windows High Performance power scheme and clears memory working sets during games/renders, while watching for developer fatigue.

### 3. Project Minority (Touchless Spatial Gestural Mind-Control)
* **File**: `ultron/actions/gesture_control.py`
* **Trigger Phrases**: *"Ultron, activate gesture control"*, *"Enable touchless mode"*
* Uses pure OpenCV YCrCb skin segmentation and convex hull defect topology at 30 FPS (~2.2% CPU):
  * **Open Palm** (`🖐️`): Wakes Ultron & arms listening mode.
  * **Fist Clench** (`✊`): Triggers emergency workstation screen lock.
  * **Swipe Right / Left** (`👉` / `👈`): Next / Previous media track.
  * **Peace Sign** (`✌️`): Toggles media Play / Pause.
  * **Hand Up / Down**: Dynamically adjusts master system volume.

### 4. Project Cerebro (Infinite Neural Memory Vector Graph / Local RAG)
* **Files**: `ultron/memory/cerebro_graph.py` & `ultron/actions/cerebro_memory.py`
* **Trigger Phrases**: *"Ultron, recall my flight details"*, *"Remember that I prefer dark mode"*, *"Show connections for Project Ultron"*
* Maintains an encrypted SQLite knowledge graph pairing concept nodes and weighted directed edges with L2-normalized cosine vector embeddings. Supports semantic fuzzy search even when exact words differ (e.g. querying *"plane tickets"* finds *\"IndiGo 6E-204 to Mumbai\"). Stored in plain SQLite at \`memory/cerebro_graph.db\` — not encrypted.

### 5. Scoped Home Assistant lighting
* **Files**: `ultron/actions/iot_overlord.py`, `ultron/core/iot_lighting.py`
* Host-approved on/off or fixed theme for one explicit operator-allowlisted light.
* Requires HTTPS private IPv4 controller with trusted IP certificate; HTTP, hostname, switch/plug and implicit all-target setups no longer supported.
* IoT/macro bundled lockdown, implicit workspace lighting, sentry surveillance/alerts and LAN discovery are disabled. HTTP acceptance is not physical verification.
* See [configuration, compatibility and limitations](reports/IOT_LIGHTING_SAFETY.md).

### 6. Project Deep-Vocal (James Spader DSP Warp Engine — EdgeTTS primary, SAPI5 offline fallback)
* **Files**: `ultron/core/tts.py` & `ultron/actions/voice_matrix.py`
* **Trigger Phrases**: *"Ultron, test voice chassis"*, *"Set voice warp intensity to 70%"*
* Authentic Marvel Cinematic Universe robotic vocal modulation:
  * Dual-stage metallic comb filters (8.5ms vocal tract + 13.2ms chassis reflections).
  * Sub-octave harmonic underlay (60-110 Hz vibranium bass fundamental).
  * Soft-knee analog tape saturation for signature James Spader mechanical rasp.
  * Offline fallback synthesis via Windows SAPI5 + Miniaudio float32 pipeline.

---

## ⚡ Workspace Matrix (Mood & Intent Triggers)

Ultron natively understands both natural English and casual Hinglish phrasing:

| Mode / Intent | Example Spoken Trigger (English & Hinglish) | Autonomous Workstation Orchestration | HUD Mode |
| :--- | :--- | :--- | :--- |
| **Coding** | *"Ultron, I feel like coding today"*<br>*(or "Ultron, aaj mere coding ka man hai")* | Opens VS Code & Terminal into active project directory, GitHub portal, lo-fi audio stream, 35% volume, focus lighting. | `CODE` |
| **Gaming** | *"Ultron, turn on gaming mode"*<br>*(or "Ultron, gaming mode on karo")* | Launches Steam & Discord, un-mutes 70% audio, 95% display brightness, Crimson Red combat alert lighting, Overdrive power plan. | `MATRIX` |
| **Research** | *"Ultron, I need to study and research"*<br>*(or "Ultron, aaj padhai karni hai")* | Opens Notion/Obsidian, arXiv, Google Scholar, 25% calm acoustics, warm amber lighting, DND mode. | `SEARCH` |
| **Cyber Audit** | *"Ultron, cyber security audit mode"*<br>*(or "Ultron, security scan shuru karo")* | Launches developer terminal, executes network vulnerability & port audit, tactical sentry radar. | `SENTRY` |
| **Chill / Cinema** | *"Ultron, chill mode / let's watch a movie"*<br>*(or "Ultron, movie dekhni hai")* | Launches Netflix/YouTube/VLC, dims display (45%), sets immersive audio (55%), cinema low-light. | `SONIC` |
| **Creative Studio** | *"Ultron, video editing setup"*<br>*(or "Ultron, content creation mode")* | Launches CapCut/Premiere/Blender, YouTube Studio dashboard, 50% monitor audio, balanced studio lighting. | `CODE` |

---

## 🗂️ Project Architecture

```text
Ultron/
├── main.py                    # Backward-compatible launcher
├── pyproject.toml             # Package metadata and `ultron` CLI entry point
├── requirements*.txt          # Runtime/dev/optional dependency sets
├── ultron/                    # Single Python runtime namespace
│   ├── __main__.py            # python -m ultron; wake-config command
│   ├── app.py                 # Event loop, live session and tool dispatch
│   ├── ui.py                  # PyQt6 HUD and settings
│   ├── paths.py               # Source/assets versus deployment-state paths
│   ├── actions/               # Auto-discovered builtin tools
│   ├── core/                  # Runtime services, policies, audio, adapters
│   ├── memory/                # Configuration and memory Python modules
│   ├── dashboard/             # Phone dashboard server and static resources
│   ├── plugins/               # Trusted extension modules and template
│   └── assets/                # Packaged images/icons
├── config/                    # Operator settings; secrets stay gitignored
├── memory/                    # Existing runtime state and workspace presets
├── logs/                      # Ignored runtime logs
├── scripts/                   # Environment bootstrap and static audits
├── tests/                     # Unit/contract/fake-adapter tests
├── docs/                      # Project notes and architecture/migration guides
└── reports/                   # Engineering reviews and acceptance records
```

Start with `python -m ultron` (or the compatibility `python main.py`). See
[project structure and migration](docs/PROJECT_STRUCTURE.md) and
[wake-word configuration](docs/WAKE_WORD.md). Old top-level `core.*`, `actions.*`,
`memory.*`, `dashboard.*`, `plugins.*` and `ui` Python imports must migrate to
`ultron.*`; no duplicate module aliases are installed.

---

## 🛠️ Complete Tools & Capabilities Registry (51 Active Actions)

Ultron comes equipped with **51 auto-discovered native tools**, categorized below:

### 1. God-Tier Superhuman Powers (Projects Prometheus, Chronos, Minority, Cerebro, Genesis, Deep-Vocal)
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`self_evolution`** | `ultron/actions/self_evolution.py` | **Project Prometheus**: Saves review-only source drafts outside auto-discovery; execution and hot-loading disabled. |
| **`chronos_predictive`** | `ultron/actions/chronos_predictive.py` | **Project Chronos**: Anticipatory context briefings, gaming/render overdrive mode, and developer fatigue watchdog. |
| **`gesture_control`** | `ultron/actions/gesture_control.py` | **Project Minority**: Touchless OpenCV webcam hand-tracking (Open Palm, Fist Clench, Swipe, Volume Up/Down). |
| **`cerebro_memory`** | `ultron/actions/cerebro_memory.py` | **Project Cerebro**: Infinite Neural Memory Vector Graph & Local RAG with L2-normalized cosine similarity. |
| **`iot_overlord`** | `ultron/actions/iot_overlord.py` | Host-approved explicit allowlisted light on/off/themes; bundled lockdown and discovery disabled. |
| **`voice_matrix`** | `ultron/actions/voice_matrix.py` | **Project Deep-Vocal**: James Spader MCU Ultron robotic DSP warp engine, vocoder tuning, and voice synthesis (EdgeTTS primary, SAPI5 offline fallback). |

### 2. Workspace Matrix & Multi-Monitor Command
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`workspace_matrix`** | `ultron/actions/workspace_matrix.py` | Mood-aware orchestrator with 7 tool modes (coding, gaming, research, cyber_audit, chill, creator, workspace_matrix): sets up IDE, terminal, browser portals, volume, brightness, and IoT lights. |
| **`war_room`** | `ultron/actions/war_room.py` | Multi-monitor matrix: maps physical displays, positions windows across screens, cyber telemetry stream. |
| **`desktop_control`** | `ultron/actions/desktop.py` | Desktop wallpaper/list/stats; bulk organize/clean and generated task execution disabled. |
| **`macro_protocol`** | `ultron/actions/macro_protocol.py` | Vibranium protocol engine: executes complex multi-step automated chained routines. |

### 3. Cyber Security, Sentry & Defense
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`network_auditor`** | `ultron/actions/network_auditor.py` | Full cyber audit: listening ports, active connections, SSL/TLS certificates, DNS benchmarks, security score. |
| **`network_scanner`** | `ultron/actions/network_scanner.py` | LAN perimeter surveillance: IP/MAC discovery, Wi-Fi telemetry, port probing, network speed/latency test. |
| **`airspace_sentinel`** | `ultron/actions/airspace_sentinel.py` | Over-the-air RF scanner: inspects nearby Bluetooth Low Energy (BLE) peripherals and Wi-Fi beacons. |
| **`sentry_protocol`** | `ultron/actions/sentry_protocol.py` | Disabled surveillance adapter; no webcam/input monitoring, snapshots, voice, locks or alert dispatch. |
| **`biometric_sentinel`** | `ultron/actions/biometric_sentinel.py` | Biometric Face ID: face enrollment, live facial verification, unauthorized intruder lockout. |

### 4. Hands-Free Automation & Ghost Pilot
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`ghost_pilot`** | `ultron/actions/ghost_pilot.py` | Windows-only, host-approved bounded pointer move/demo; blind typing/click/search/app-launch workflows disabled. See [pointer safety](reports/DESKTOP_POINTER_SAFETY.md); no native GUI certification. |
| **`computer_control`** | `ultron/actions/computer_control.py` | Direct computer control: click, type, press shortcuts, capture screens, and manage active windows. |
| **`computer_settings`** | `ultron/actions/computer_settings.py` | System settings: volume level, screen brightness, Wi-Fi state, and display settings. |
| **`system_command`** | `ultron/actions/system_command.py` | Terminal automation: executes PowerShell, Command Prompt, or Bash commands safely with output capture. |
| **`system_utility`** | `ultron/actions/system_utility.py` | System health utilities: lock workstation, sleep PC, empty Recycle Bin, battery & network IP checks. |
| **`process_manager`** | `ultron/actions/process_manager.py` | Task manager: inspect active processes, bring windows to front, and terminate tasks by name or PID. |

### 5. DevOps, Development & Neural Memory
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`workspace_recall`** | `ultron/actions/workspace_recall.py` | Local SQLite FTS5 semantic memory: recall past notes, commands, copied code snippets, and tasks. |
| **`git_sentinel`** | `ultron/actions/git_sentinel.py` | Host-approved fixed local status/diff-stat/log/branch-list inspection. Auto-stage/commit, branch mutation, stash and remotes disabled; see [Git safety](reports/GIT_INSPECTION_SAFETY.md). |
| **`dev_agent`** | `ultron/actions/dev_agent.py` | Review-only project planner: approval-gated inert plan drafts; no builds, dependency installs or execution. |
| **`code_helper`** | `ultron/actions/code_helper.py` | Review-only code proposals/explanations; exact-content text-draft approval, no automatic execution or original-file changes. |
| **`cloud_watchtower`** | `ultron/actions/cloud_watchtower.py` | Server fleet & DevOps monitor: SSH ping, HTTP/HTTPS endpoint uptime checks, GitHub activity watching. |

### Local tool diagnostics

`tool_status` is a read-only local tool. Use `{"section":"summary"}` for registry/dependency presence and dispatch telemetry, `{"section":"recent","limit":20}` for recent calls, or `dependencies` / `registry` sections individually. It stores at most 100 finished action/plugin dispatch events in process memory, without arguments, results or exception text. `HANDLER_RETURNED` means the handler returned—not that delivery, approval or background work succeeded. Dependency presence is not a live capability/credentials test. Inline core tools and direct helper calls are outside this telemetry.

### 6. Web Intelligence & Autonomous Recon
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`web_autopilot`** | `ultron/actions/web_autopilot.py` | Bounded page excerpts, source-linked research/price references and flight search links; no autonomous booking. |
| **`web_search`** | `ultron/actions/web_search.py` | Bounded Gemini/DDGS research with source URLs, UTC timestamps and explicit fallback/partial-result warnings. |
| **`browser_control`** | `ultron/actions/browser_control.py` | Playwright browser driver: opens URLs, switches tabs, scrolls, clicks, and inputs form data. |
| **`bounty_hunter`** | `ultron/actions/bounty_hunter.py` | Autonomous e-commerce intelligence: tracks price drops, product availability, and discount alerts. |
| **`flight_finder`** | `ultron/actions/flight_finder.py` | Travel intelligence: scans airline routes, ticket fares, flight schedules, and connection options. |
| **`drone_swarm`** | `ultron/actions/drone_swarm.py` | Background sub-agent swarms: parallel headless workers for deep research, crypto tickers, and hardware sentries. |

### 7. Vision, Audio Matrix & Telepathy
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`screen_mind_read`** | `ultron/actions/screen_processor.py`| Real-time screen analysis: captures active display context, OCR text, and diagrams via Gemini Vision. |
| **`optical_hud`** | `ultron/actions/optical_hud.py` | Computer vision & OCR: inspects live screen content, triages compiler error tracebacks, parses UI text. |
| **`omni_telepathy`** | `ultron/actions/omni_telepathy.py` | Phone bridge: shared clipboard synchronization, remote phone screen camera feed, mobile telemetry. |
| **`audio_matrix`** | `ultron/actions/audio_matrix.py` | Procedural MCU soundboard: synthesizes repulsor charges, Red Alert sirens, sub-bass drops, and sonar pings. |
| **`media_controller`** | `ultron/actions/media_controller.py` | Universal media playback: play, pause, next track, previous track, stop, and volume controls. |
| **`video_player`** | `ultron/actions/video_player.py` | In-HUD media playback: renders local video files and direct media streams where the avatar sits. |
| **`youtube_video`** | `ultron/actions/youtube_video.py` | YouTube player: stream resolution, audio/video synchronization, and original audio dub tracking. |
| **`meeting_scribe`** | `ultron/actions/meeting_scribe.py` | Bounded default-input audio recorder with explicit stop/save and factual recording metadata. No transcription or inferred decisions; sharing metadata requires a separate approved action. |

### 8. Mobile Bridge, Communications & System Utilities
| Tool Name | Action File | Description |
| :--- | :--- | :--- |
| **`android_bridge`** | `ultron/actions/android_bridge.py` | Android bridge: explicit-device approval for ADB shell/reboot; firmware flashing and DND unsupported; legacy transfer/capture paths remain under review. |
| **`send_message`** | `ultron/actions/send_message.py` | Verified Telegram bot outbox: full previews, HUD approval, status/cancel, matching API receipts, and duplicate/uncertain-send protection. Blind desktop messaging is disabled. |
| **`weather_report`** | `ultron/actions/weather_report.py` | Atmospheric reports: live weather conditions, humidity, wind speeds, and forecasts. |
| **`game_updater`** | `ultron/actions/game_updater.py` | Gaming client companion: monitors Steam and launcher updates, patch notes, and downloads. |
| **`open_app`** | `ultron/actions/open_app.py` | Application launcher: cross-platform alias mapping for dozens of applications and binaries. |
| **`file_controller`** | `ultron/actions/file_controller.py` | Host-approved, fingerprint-bound no-clobber regular-file transfers and separately approved session undo. Organization preview only; bulk apply disabled. Create/folder/write/append now require exact small-file approval (16000-byte cap, existing parents; replacement can change metadata). Delete now requires exact approval for one regular file up to 64 MiB; directories refused and automatic Trash restore disabled. Downloads now require separate URL receipt and exact hash/size/path save approvals; redirects refused, inverse separately approved. See [download safety](reports/DOWNLOAD_CONSENT_SAFETY.md). See [Trash safety](reports/FILE_TRASH_SAFETY.md). See [write safety](reports/FILE_WRITE_SAFETY.md). See [transfer and undo limits](reports/FILE_TRANSFER_UNDO_SAFETY.md). |
| **`file_processor`** | `ultron/actions/file_processor.py` | Document reader: parses and summarizes PDF, Word (.docx), PowerPoint (.pptx), and text files. |
| **`clipboard_control`** | `ultron/actions/clipboard_control.py` | System clipboard utility: inspects, replaces, pastes, and clears system clipboard contents. |
| **`purge_protocol`** | `ultron/actions/purge_protocol.py` | Disk cleaner: safely audits and purges temporary files, crash dumps, compiler caches, and the Recycle Bin. |
| **`reminder`** | `ultron/actions/reminder.py` | Persistent reminder IDs, list/status/cancel, timezone/DST validation, and native Windows/macOS/Linux scheduling with delivery/cleanup state tracking. |
| **`quick_timer`** | `ultron/actions/quick_timer.py` | Named session timers with IDs, list/status, pause/resume, cancellation, and speech/log completion alerts. |
| **`file_search`** | `ultron/actions/file_search.py` | Bounded read-only local search by filename, extension, size, recency, and opt-in UTF-8 content with line-numbered snippets. |

---

## Practical tool upgrades

See [Tool enhancements](docs/TOOL_ENHANCEMENTS.md) for timer, file-search, persistent-reminder and messaging examples and platform requirements.

### Local-first productivity release

Seven local-first actions: **calculator**, **task_board**, **document_compare**, **evidence_ledger**, **safe_sharing**, **notification_center** and optional read-only **google_workspace**. See [setup, examples, privacy boundaries and release limits](docs/PRODUCTIVITY_RELEASE.md).

The additional **background_jobs** tool inspects/cancels durable bounded host jobs. Public `drone_swarm` launches now use that journal, with finite budgets, exact job IDs, cooperative cancellation and no fabricated convergence. See [job states, compatibility changes and crash recovery](docs/BACKGROUND_JOBS.md). No unfinished job is automatically replayed.

Document tools require host-approved folders; publishing a redacted text copy requires HUD approval. Task/evidence data and a local notification inbox persist in `~/.ultron/productivity.sqlite3`. The inbox defaults to pull-only; host opt-in enables generic local HUD counts (no private notice content or external push). See the release guide for consent and delivery limits. Google requires separate desktop OAuth/secure-keyring setup and explicit model-context permission; no account is connected automatically, and a Drive Picker UI is not included. These scoped safeguards do **not** constitute a universal permission boundary for legacy shell/browser/native actions.

## 🔒 Privacy & Security

- **Local-First Execution**: Most memories, terminal actions, filesystem operations, and presets run locally on your machine. Some features use cloud services: Gemini Live for voice conversation, Edge TTS for speech synthesis, web search, IP geolocation, weather lookups, and enabled Telegram bot messaging. Not all processing is local — review each action's description before use.
- **Protected Actions**: Irreversible system commands (shutdown, reboot, network disconnect, purge, shell commands) require explicit on-screen confirmation via the confirmation gate. Outbound `send_message` tool sends also require an explicit HUD approval tied to the previewed recipient and text.
- **Credential Safety**: Private keys in `config/api_keys.json`, memory databases (`memory/*.db`), and biometric templates (`memory/boss_biometrics/`) are strictly git-ignored. Biometric matching uses OpenCV template correlation (heuristic, not liveness-tested Face ID).

---

## 📄 License

This project is licensed under the **MIT License**.


### Generated-code containment

Model-generated desktop Python (`desktop_control` task/unknown-action fallback)
is disabled, including direct calls to its former execution helper. It does not
ask a provider to generate code or offer approval as an isolation substitute.
Explicit wallpaper/list/stats operations remain available and are **not** covered
by a new sandbox or universal permission boundary. Bulk organize/clean are disabled;
file_controller offers a read-only organization preview.

`self_evolution` now saves approval-gated, owner-private `.py.txt` drafts outside
`ultron/actions/` and `ultron/plugins/`. It cannot promote/import/hot-load them; test/run/execute
aliases are disabled. Manual trusted review is required. Existing installed
modules are **not** automatically removed or retroactively quarantined: review
legacy additions before restarting. This containment closes these generated-code
paths, not other legacy shell, developer, plugin or native execution paths.


### Privileged shell and utility consent

`system_command` now requires host HUD approval for **every** non-refused command,
including `whoami`, directory listings and Git inspection. Name/option heuristics
no longer grant automatic execution. Approval shows the complete bounded command,
shell, captured working directory and timeout; those values are captured for the
callback. Headless, denied, expired or busy requests do not execute. The existing
destructive-pattern refusal list is advisory, not comprehensive shell analysis.

Approved commands retain full account privileges. Git pager/diff/config helpers,
PATH resolution, shell initialization, mutable executable/config/filesystem state
and child processes are **not isolated**. A timeout is not a process-tree sandbox
or guaranteed rollback. Prefer narrow tools over approving arbitrary shell code.
Other tools (including developer tools, macros and plugins) are not
covered by this `system_command` gate. New command audit records contain hashes,
length and lifecycle metadata rather than command/output content; existing audit
files are not rewritten or purged and may still contain older sensitive records.
Audit is best-effort, not tamper-proof, and `returned` does not certify success.

Public `system_utility.empty_recycle_bin` and `sleep_computer` helpers now request
host approval, so their dispatcher and direct helper callers share that gate.
Unsupported platforms return unsupported rather than requesting a non-working
action. Native error codes/nonzero subprocess exits are not reported as success.
Recycle-bin approval covers the bin **at execution time**, not an immutable item
snapshot. Other modules' independent recycle/sleep implementations remain outside
these scoped changes. Native sleep/recycle effects were tested only with fakes.


### Workspace/media capability reporting

Workspace audit presets call `network_auditor.audit_security_posture()` using its
actual signature. Import/runtime failure reports unknown posture, not healthy
telemetry. The existing audit itself remains heuristic and may query public-IP
services; this wiring fix does not certify its security score or privacy model.
Android DND is unsupported: workspace/focus presets do not issue a nonexistent
ADB action or claim notifications were silenced.

`media_controller` accepts integer absolute-volume values from 0 to 100, including
zero (no fallback to 50). Windows uses scalar volume and distinguishes endpoint
readback from missing/mismatched readback; macOS checks a bounded command and
reports submission, not verified sound. Linux/other absolute-volume requests are
explicitly unsupported; workspace volume uses this same backend rather than the
former unchecked fallbacks. This intentionally narrows the claimed capability.
Keyboard media controls report key submission only. Explicit mute/unmute no longer
secretly toggle state; use `toggle_mute` when that is what you intend. No automatic
retry occurs after uncertain native calls. Other audio implementations remain
outside this change.

IoT lighting now requires exact single-use approval and explicit operator provisioning;
implicit workspace lighting and bundled IoT/macro lockdown/sentry effects are disabled.
See [IoT safety](reports/IOT_LIGHTING_SAFETY.md). This is not global permission,
physical-safety or transport isolation. Other workspace/macro effects and unrelated
camera/lock tools remain outside this batch. Tests use fake adapters, not devices.


### Process termination consent

`process_manager` kill/terminate/stop/close aliases now request host HUD approval
for an exact PID or exact process-name snapshot (case-insensitive; Windows `.exe`
alias supported), not a substring or a future matching process set. A preview
contains at most 20 PID/name/creation-time identities; process-name scans stop at
4,096 entries and require a PID if incomplete. Init, the assistant and its known
ancestors are refused. Failure to obtain identities/ancestor data fails closed.

The approved effect sink consumes the operation policy's single-use grant and
revalidates all identities before the first signal, then checks each again before
`psutil.terminate()`. New matches are never added. A reused/missing/changed process
invalidates preflight rather than widening consent. Unsaved work can be lost;
this is not graceful document saving or rollback. There is no automatic force-kill
or retry, including after access errors/uncertain results. Exit observation is
bounded by a shared three-second wait budget; submission is not reported as exit.
Sequential batches can partially complete if processes change or errors occur.
OS/psutil identity checks reduce but do not create an atomic transaction with the
kernel or protect against malicious local code. Other process-control paths are
not automatically covered, and no universal persistent audit is claimed.

Windows focus uses a fixed PowerShell script and passes the query via an environment
variable, without evaluating query text as script or wildcard syntax. Native
acceptance/nonzero exits are distinguished; focus state is not independently
verified. PowerShell/binary resolution still uses the trusted host environment,
not an execution sandbox. Fake-adapter tests do not certify native Windows behavior.


### Developer tools: review-only mode

`dev_agent` now proposes a project plan rather than building, installing packages
or running model-generated code under a description-only approval. `code_helper`
write/edit/optimize generate review proposals; `explain` returns an unverified model
explanation. Edits do **not** modify the original file. `run`, `build`, automatic
fix/install loops and coding screen capture are disabled. `auto` with source means
explain, otherwise write; it never delegates execution permission to a model.

After generation, exact-content host approval may save an inert `.txt` draft in
`~/.ultron/review_drafts/`, not `ultron/actions/`, `ultron/plugins/` or arbitrary output paths.
No draft is imported/executed/tested. Explicit output_path is rejected. Source
reads require an explicitly selected absolute file under host-approved document
roots (see PRODUCTIVITY_RELEASE.md); regular UTF-8 inputs are bounded to 24,000
bytes. Selected/inline source is sent to Ultron's configured model, not guaranteed
private processing. Drafts may contain unsafe code; approval to save text is not
approval or certification to run it. Review/purge drafts manually; they are not
encrypted. Existing source files/installed projects are untouched.

See [privileged sink inventory and coverage limits](reports/PRIVILEGED_SINK_REVIEW.md)
for the static call-site inventory, manually traced groups and migration queue.
This narrows two unsafe legacy capabilities; it does not constitute a global
permission broker or OS sandbox. Android discovery refinement, GUI input, IoT lockdown and
other legacy sink groups remain priority review work.


### Android shell/reboot consent

`android_bridge` shell and reboot now require an explicit `serial` from device
listing. No default/first-device selection or fastboot-device fallback is used.
The preview includes the complete command (up to 4,000 characters) or supported
reboot target, serial, transport ID and executable identity. Host approval is
single-use and consumed at the effect sink. Before execution the executable
fingerprint and uniquely authorized `device` transport are rechecked. Changed,
offline, unauthorized, missing or ambiguous transports fail closed. ADB commands
use explicit local-server host/port and `-t` transport selection. Symlinked or
unresolved ADB binaries are refused by this path.

Dedicated fastboot flashing and EDL/sideload reboot are disabled, including direct
helper calls. Supported reboot requests are system/recovery/bootloader/fastboot,
from an authorized ADB transport only. A zero exit reports command acceptance,
not verified boot state. Errors/timeouts are uncertain; no automatic retry.

These checks do not establish cryptographic device identity, atomically lock the
ADB server/device/executable, or prevent same-user filesystem/transport races.
ADB shell is **not sandboxed**: a separately approved shell command can still
perform destructive/device-privileged actions, including firmware changes if its
privileges permit. Disabling the dedicated flash helper is not a shell policy.
ADB/server/PATH configuration remains trusted host state. Shell output is untrusted
and returned to the configured assistant/UI; subprocess capture is not an OS-level
resource sandbox. No physical-device/firmware certification was performed.

Single-file push/pull and APK installation are now migrated as described below.
Single-frame screenshot capture and finite view-only mirroring are also migrated
as described below. Selected telemetry now also requires explicit-device and field/disclosure approval.
Legacy device discovery remains a separate listing path, not authorization.
Do not treat this scoped change as whole-bridge authorization coverage.


### Android single-file transfer and APK installation

`push`, `pull` and `install` now require explicit serial and exact single-use host
approval at the effect sink. Select absolute local paths inside host-approved
roots configured with `python -m core.productivity_setup allow-root /path`.
Files are regular and at most 64 MiB; directories/symlinks are refused. Binary,
transport and local source identity/content are revalidated. Source-root revocation
before staging blocks upload/install. Uploads/install use a private temporary
snapshot of approved bytes, not the mutable original pathname; staging is cleaned
on return. Captured source bytes/SHA-256 are not an APK signing or malware audit.

- **Push:** phone_path must be `/sdcard/Download/`. Approval shows a fresh generated
  subdirectory and exact filename. A failed exclusive remote `mkdir` prevents push;
  no existing directory is intentionally reused. SHA-256 readback distinguishes
  verified copied bytes from unverified ADB acceptance. Device state outside the
  file, remote parent/symlink races and malicious device behavior are not isolated.
  Partial remote directories/files are not automatically deleted or retried.
- **Pull:** phone_path selects one simple file beneath `/sdcard/Download/`; paths
  with traversal/shell syntax are rejected. Remote `stat` and `sha256sum` must be
  available. file_path is a **new exact local filename**, not a directory/shortcut.
  The receiver has a bounded queue, byte ceiling and deadline. A matching checksum
  is required before exclusive same-filesystem hard-link publication. Existing or
  concurrently created destinations are never deliberately replaced; unsupported
  hard links fail closed. Local partial staging is cleaned on failure. Downloaded
  content remains untrusted and must not be placed in auto-executed locations.
- **Install:** `.apk` source required. `replace_existing` defaults to false;
  explicit true adds `-r` and appears in approval. No automatic downgrade, permission
  granting, missing-package install loop or retry. Exit status plus ADB `Success`
  is reported as ADB's result, not verified app safety or behavior.

No device filesystem jail, cryptographic device identity, atomic transport/path
lock, process-tree sandbox, encrypted storage or guaranteed crash cleanup is
claimed. Host/device filesystem state remains trusted against malicious local
concurrent changes. Remote paths are syntactically restricted, not a proof that
all remote ancestor symlinks stay confined. Receiver timeout kills the direct child;
a descendant holding its stdout pipe can retain a bounded daemon reader until EOF,
but that reader has no destination handle and cannot continue writing the file.
ADB install/transfer may have taken effect after errors/timeouts: inspect manually,
never assume safe automatic replay. Native Android/Windows compatibility remains
unverified; tests use fake ADB and small trusted local subprocess fixtures.


### Android screenshot consent

`screenshot` now requires `serial` and `file_path`: a new exact `.png` path inside
a host-approved root with an existing parent. The old implicit Downloads directory
and timestamp filename are removed. Host approval covers **the screen visible when
execution starts**, not a pre-reviewed image. No screen capture or output file is
created before approval; denied/headless/changed-device requests cannot capture.

The single-frame `screencap` receiver uses explicit local ADB transport, a 15-second
deadline and 16 MiB byte ceiling. Before exclusive hard-link publication, bounded
PNG checks cover signature, CRCs, header dimensions (40MP / 16,384 per axis), required
image/end chunks and rejection of animated PNG. It does not decode pixels or prove
complete format/content safety. Corrupt/partial/oversized capture is not published;
local staging is cleaned on normal return/failure. Existing/concurrently-created
files are never intentionally replaced. Unsupported hard links fail closed.

This path returns local metadata/hash only; it does not display the screenshot,
include image contents in model context, or send it to cloud/phone transports.
Other tools can still read it if separately invoked, and other software may sync
or watch your chosen directory. Keep that directory private and delete captures
manually; storage is not encrypted and crash cleanup is not guaranteed. ADB/host
filesystem races and descendant-pipe limitations remain as documented for file
transfers. Native devices and platform behavior are unverified; tests use fake
capture plus small trusted local subprocess fixtures. Mirroring is now scoped as below.


### Owned Android view-only mirroring

`mirror`/`scrcpy`/`screen_mirror` now need an explicit `serial` and host approval
for `seconds` (integer 5–300; default 60). Preview states that a live sensitive
phone screen will appear locally and that scrcpy runs its server on the phone.
The native request disables control, audio, clipboard autosync and screen power-on;
no recording is requested. ADB/scrcpy executable identity is checked before launch,
with an explicit serial and local ADB server/binary environment.

`mirror_status` returns metadata and an opaque owned `mirror_id`, not an image or
proof of rendering. `mirror_stop` requires that exact ID and only stops the owned
Popen process. It never kills by name, arbitrary PID or ADB-server ownership.
One live process per owner is admitted; an OS lock also prevents simultaneous
live owners. A native time limit and host watchdog request automatic stop. Failed
termination retains the slot and reports uncertainty. UI shutdown closes admission
and attempts owned cleanup; a pending approval cannot launch after shutdown.

This is not an absolute display/privacy/crash-cleanup guarantee. Native versions
and flag enforcement are not certified; unsupported options may cause exit, with
no weaker-option fallback. Scrcpy uses serial selection, not a continuously locked
ADB transport identity. Bundled dependencies, host environment, reconnect races
and device behavior remain trusted. App crashes can leave native children/servers;
owner locks do not track surviving children after crashes. Other desktop software
can capture the window. Only direct-child stopping is implemented, not a process-
tree/OS sandbox. See [engineering record](reports/ANDROID_MIRROR_LIFECYCLE.md).


### Selected Android telemetry

`info`/`telemetry` now require explicit `serial` and host approval listing exactly
which values may enter the configured model/UI/log paths. `battery` selects just
battery by default. `telemetry_fields` supports model, brand, codename,
android_version, security_patch, battery, storage and wifi_ip. Defaults exclude
codename/storage/IP; unknown/duplicate fields are rejected, not converted to shell.

Queries are fixed and transport-pinned. Per-field stdout is capped at 64 KiB and
5 seconds; a 20-second query budget skips remaining fields. Identity probes,
fingerprinting and cleanup can extend end-to-end duration—this is not an OS-level
hard deadline. Device changes before/during/following reads discard all results.
Malformed/failed/partial native output is unavailable, never a fabricated zero or
healthy status. Battery uses reported level/scale; storage means /sdcard filesystem
KiB, not whole-phone capacity. Values are untrusted device reports, not independent
facts or instructions. No screenshot/arbitrary shell is part of this request.

The adapter doesn't persist telemetry, but existing result/UI/log consumers may.
This is not guaranteed private/local inference or an atomic/cryptographic device
lock. `devices`/`list`/`status` discovery remains a separate legacy listing path,
not proof of consent or complete permission coverage. See
[engineering record](reports/ANDROID_TELEMETRY.md).

### File transfers and undo approval

Move/copy/rename now require an exact host-approved fingerprint-bound plan, and
session undo requires a separate approval bound to one top-of-stack entry. Copy
stages verified bytes before no-clobber publication; moves still require
same-volume hard-link support and are not atomic rename transactions. Uncertain
failures can retain both files or `.ultron-copy-*.part` staging content; inspect
the destination before retrying. Create/folder/write/append now use a separately documented approved small-file adapter;
regular-file Trash submission now has a separate approval adapter; automatic restore is disabled and download receipt/publication now require separate approvals (see DOWNLOAD_CONSENT_SAFETY.md). See [scope, compatibility and races](reports/FILE_TRANSFER_UNDO_SAFETY.md).

### Configurable local wake phrase

```bash
# Show current settings; does not import GUI/audio or download models
python -m ultron wake-config
# Choose a supported pretrained model and score threshold
python -m ultron wake-config --model alexa --threshold 0.6
# Restore the backward-compatible default (spoken phrase: "hey jarvis")
python -m ultron wake-config --model hey_jarvis --threshold 0.5
```

Restart after editing. Enable/download the optional builtin model through the
existing WAKE WORD control. A custom phrase requires a compatible, trusted local
ONNX model; a display label alone cannot create or train a new phrase. See
[custom model setup and limitations](docs/WAKE_WORD.md).

### Small-file write approvals

Create, one-level folder creation, write/overwrite and append now require an exact
host-approved plan and a separate approval for undo. Existing parent required;
before/after contents capped at 16000 bytes. Writes stage/fsync before publication;
existing entry replacement can change permissions/metadata and hardlink behavior.
External check-to-replace races remain: this is not atomic compare-and-swap or a
filesystem sandbox. See [scope and compatibility](reports/FILE_WRITE_SAFETY.md).

### Native Trash submissions

Delete requests now approve one exact fingerprinted regular file (up to 64 MiB),
then revalidate file/parent/root/backend before one native Send2Trash call. No
directories, batches, permanent-delete fallback or automatic retry. Source absence
is **not** a verified Trash receipt or recoverability guarantee. Name-based automatic
restore is disabled and no undo entry is registered. Native behavior remains
unverified; see [scope and limitations](reports/FILE_TRASH_SAFETY.md).

### Two-stage download approval

Downloads first request approval to fetch an exact public URL into bounded memory,
then request separate approval to save exact received bytes (SHA256, size, path).
Redirects are refused; denial/expiry of save publishes nothing. Publication remains
private staged/no-clobber and its inverse requires separate approval plus unchanged
file/parent checks. Content is untrusted, not scanned or executed. Late timed-out
network workers cannot publish. See [limits and compatibility](reports/DOWNLOAD_CONSENT_SAFETY.md).

### Application version system

```bash
python -m ultron --version
python -m ultron version --json
python scripts/version.py --check
python scripts/version.py --bump patch  # preview only, no files/Git changed
```

Version metadata has one source: `ultron/_version.py`; the baseline remains 0.1.0.
`CHANGELOG.md` records unreleased work. Explicit `--write` on the developer bump
script edits only version/changelog; it never commits, tags, pushes or publishes.
This is release versioning, not automatic backups, schema migration or self-update.
See [version policy/release workflow](docs/VERSIONING.md).

### Git Sentinel restrictions

Git inspection requires an explicit repository root and exact host approval, even
for local reads. Fixed status/diff-stat/log/branch-list only; no automatic staging,
commit, checkout/create, stash, fetch, push or pull. Known helper/pager/fsmonitor
paths reduced, but Git/config/host remain trusted, not sandboxed. See
[compatibility and remaining gates](reports/GIT_INSPECTION_SAFETY.md).
