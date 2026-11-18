#!/usr/bin/env python3
"""
doctor.py — environment health check for Ultron.

Run this with the same interpreter you launch the app with:

    python scripts/doctor.py
    python scripts/doctor.py --tools     # also try to load every action

It answers the only question worth asking when the app misbehaves early:
"is this my code, or my machine?" Nothing here needs the app to start, and
nothing is modified — every check is read-only.

Exit code: 0 if nothing FAILED, 1 otherwise. Warnings never fail the run.
"""
from __future__ import annotations

import argparse
import importlib
import importlib.util
import os
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MIN_PY, MAX_PY = (3, 11), (3, 13)

# (import name, pip name, why it matters)
REQUIRED = [
    ("PyQt6.QtWidgets", "PyQt6", "the HUD"),
    ("sounddevice", "sounddevice", "microphone + speaker I/O"),
    ("numpy", "numpy", "audio buffers, HUD rendering"),
    ("google.genai", "google-genai", "the live model session"),
    ("edge_tts", "edge-tts", "neural voice"),
    ("miniaudio", "miniaudio", "voice playback"),
    ("pyttsx3", "pyttsx3", "offline voice fallback"),
    ("requests", "requests", "network tools"),
    ("psutil", "psutil", "system monitor"),
    ("cv2", "opencv-python", "camera, gesture control, vision"),
    ("mss", "mss", "screen capture"),
    ("playwright", "playwright", "browser automation"),
    ("pyautogui", "pyautogui", "mouse/keyboard control"),
]

OPTIONAL = [
    ("pytesseract", "pytesseract", "OCR (needs the tesseract binary too)"),
    ("pygetwindow", "pygetwindow", "window geometry — Windows only"),
    ("pynvml", "pynvml", "NVIDIA GPU meter"),
    ("bleak", "bleak", "Bluetooth LE scanning"),
    ("cryptography", "cryptography", "HTTPS for the phone dashboard"),
    ("yt_dlp", "yt-dlp", "video playback"),
]

# Maps the interesting part of a loader error to the package that fixes it.
SYSTEM_LIB_HINTS = [
    ("PortAudio", {
        "Linux": "sudo apt install libportaudio2",
        "Darwin": "brew install portaudio",
        "Windows": "usually bundled — try  pip install --force-reinstall sounddevice",
    }),
    ("libxkbcommon", {
        "Linux": "sudo apt install libxkbcommon0 libxkbcommon-x11-0",
    }),
    ("libGL.so", {
        "Linux": "sudo apt install libgl1 libglx-mesa0",
    }),
    ("libEGL", {
        "Linux": "sudo apt install libegl1",
    }),
    ("xcb", {
        "Linux": "sudo apt install libxcb-cursor0 libxcb-xinerama0",
    }),
    ("tesseract", {
        "Linux": "sudo apt install tesseract-ocr",
        "Darwin": "brew install tesseract",
        "Windows": "install the tesseract installer, then set pytesseract.pytesseract.tesseract_cmd",
    }),
]

RESET, BOLD = "\033[0m", "\033[1m"
GREEN, YELLOW, RED, DIM = "\033[32m", "\033[33m", "\033[31m", "\033[2m"
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    RESET = BOLD = GREEN = YELLOW = RED = DIM = ""

_counts = {"PASS": 0, "WARN": 0, "FAIL": 0}


def _emit(tag: str, label: str, detail: str = "", fix: str = "") -> None:
    color = {"PASS": GREEN, "WARN": YELLOW, "FAIL": RED}[tag]
    _counts[tag] += 1
    print(f"  {color}{tag:<4}{RESET} {label}" + (f" {DIM}— {detail}{RESET}" if detail else ""))
    if fix:
        for line in fix.splitlines():
            print(f"        {YELLOW}→{RESET} {line}")


def _hint_for(exc: BaseException) -> str:
    text = f"{type(exc).__name__}: {exc}"
    osname = platform.system()
    for needle, fixes in SYSTEM_LIB_HINTS:
        if needle.lower() in text.lower():
            return fixes.get(osname, "") or "\n".join(f"{k}: {v}" for k, v in fixes.items())
    if "display" in text.lower() and "cannot open" not in text.lower():
        return "No graphical session found. Run this from a desktop session, not SSH/headless."
    return ""


def check_python() -> None:
    print(f"\n{BOLD}Python{RESET}")
    v = sys.version_info[:2]
    label = f"{sys.version.split()[0]} at {sys.executable}"
    if v < MIN_PY:
        _emit("FAIL", label, f"needs {MIN_PY[0]}.{MIN_PY[1]}+",
              f"install Python {MIN_PY[0]}.{MIN_PY[1]}+ and re-run:\n"
              f"python{MIN_PY[0]}.{MIN_PY[1]} -m venv .venv")
    elif v > MAX_PY:
        _emit("WARN", label, f"newer than the tested {MAX_PY[0]}.{MAX_PY[1]} — probably fine")
    else:
        _emit("PASS", label)

    in_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    _emit("PASS" if in_venv else "WARN",
          "virtual environment" if in_venv else "system Python",
          "" if in_venv else "dependencies leak into the system interpreter",
          "" if in_venv else "python -m venv .venv && . .venv/bin/activate  (Windows: .venv\\Scripts\\activate)")

    _emit("PASS", f"platform {platform.system()} {platform.release()}")


def check_deps() -> None:
    print(f"\n{BOLD}Dependencies{RESET}")
    for mod, pip_name, why in REQUIRED:
        try:
            importlib.import_module(mod)
            _emit("PASS", f"{pip_name}", why)
        except ImportError as e:
            hint = _hint_for(e)
            _emit("FAIL", pip_name, f"{why} — not importable",
                  hint or f"pip install {pip_name}")
        except Exception as e:
            hint = _hint_for(e)
            _emit("FAIL", pip_name, f"{why} — {type(e).__name__}: {e}"[:120],
                  hint or "missing system library — see the note above")

    for mod, pip_name, why in OPTIONAL:
        try:
            importlib.import_module(mod)
            _emit("PASS", f"{pip_name} {DIM}(optional){RESET}", why)
        except Exception as e:
            _emit("WARN", f"{pip_name} {DIM}(optional){RESET}", f"{why} — unavailable",
                  _hint_for(e))


def check_config() -> None:
    print(f"\n{BOLD}Configuration{RESET}")
    cfg_file = ROOT / "config" / "api_keys.json"
    if not cfg_file.exists():
        _emit("WARN", "config/api_keys.json missing",
              "the setup screen will ask for your key on first launch")
        return
    import json
    try:
        cfg = json.loads(cfg_file.read_text(encoding="utf-8"))
    except Exception as e:
        _emit("FAIL", "config/api_keys.json is not valid JSON", str(e))
        return
    _emit("PASS", "config/api_keys.json parses")

    # The rules live in memory.config_manager — this used to be a third copy, and
    # it read the key as f"{provider}_api_key", which is the wrong field for
    # claude (anthropic_api_key), nvidia_nim (nvidia_api_key) and opencode_zen
    # (opencode_api_key). A correctly configured Claude user was told their key
    # was missing.
    try:
        sys.path.insert(0, str(ROOT))
        from memory.config_manager import (get_ai_provider, get_provider_key,
                                           is_configured, looks_like_placeholder)
    except Exception as e:
        _emit("FAIL", "cannot import memory.config_manager", str(e)[:100])
        return

    provider = get_ai_provider()
    if not provider:
        _emit("FAIL", "no ai_provider set",
              "the app cannot tell which provider to use",
              'set an "ai_provider" entry in config/api_keys.json, or'
              "launch and let the setup screen write it")
    elif provider == "ollama":
        _emit("PASS", "provider: ollama", "local — no API key needed")
    else:
        key = get_provider_key(provider)
        if looks_like_placeholder(key):
            _emit("FAIL", f"{provider} API key",
                  "missing or still the placeholder",
                  "get a key at https://aistudio.google.com/app/apikey (Gemini) "
                  "or re-run the setup screen")
        else:
            _emit("PASS", f"{provider} API key", "present")

    if not is_configured():
        _emit("WARN", "not usable yet",
              "the setup screen will open on launch instead of starting a session")

    name = cfg.get("assistant_name") or "Ultron"
    user = cfg.get("user_name") or "Boss"
    _emit("PASS", f"identity: {name} addressing you as {user}")

    devices = cfg.get("input_device") or "(system default)"
    _emit("PASS", f"microphone: {devices}")


def check_audio() -> None:
    print(f"\n{BOLD}Audio devices{RESET}")
    try:
        import sounddevice as sd
    except Exception as e:
        _emit("WARN", "cannot enumerate audio devices", str(e)[:80])
        return
    try:
        ins = [d for d in sd.query_devices() if d.get("max_input_channels", 0) > 0]
        outs = [d for d in sd.query_devices() if d.get("max_output_channels", 0) > 0]
    except Exception as e:
        _emit("WARN", "audio device query failed", str(e)[:80])
        return
    _emit("PASS" if ins else "WARN", f"{len(ins)} input device(s)",
          "voice input available" if ins else "no microphone — text mode only")
    _emit("PASS" if outs else "WARN", f"{len(outs)} output device(s)",
          "voice output available" if outs else "no speakers — text mode only")


def check_tools(deep: bool = False) -> None:
    print(f"\n{BOLD}Tools{RESET}")
    actions = ROOT / "actions"
    files = sorted(actions.glob("*.py"))
    _emit("PASS", f"{len(files)} action files")
    if not deep:
        _emit("WARN", "discovery not attempted", "re-run with --tools to load every action")
        return
    sys.path.insert(0, str(ROOT))
    try:
        from core.action_loader import discover_actions
    except Exception as e:
        _emit("FAIL", "cannot import core.action_loader", str(e)[:100])
        return
    logs: list[str] = []
    reg = discover_actions(actions, logger=logs.append)
    n = len(reg.get_tool_declarations())
    _emit("PASS" if n else "FAIL", f"{n} tools discovered")
    for line in logs:
        if "rejected" in line.lower():
            _emit("WARN", line.replace("Action rejected: ", "")[:110])


def check_browsers() -> None:
    print(f"\n{BOLD}Browser automation{RESET}")
    root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", Path.home() / ".cache" / "ms-playwright"))
    if os.name == "nt":
        root = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "ms-playwright"
    found = sorted(p.name for p in root.glob("*chromium*")) if root.exists() else []
    if found:
        _emit("PASS", "playwright chromium", found[0])
    else:
        _emit("WARN", "playwright browsers not downloaded",
              "browser_control, web_autopilot won't work",
              "python -m playwright install chromium")


def main() -> int:
    ap = argparse.ArgumentParser(description="Ultron environment health check")
    ap.add_argument("--tools", action="store_true", help="also load every action file")
    args = ap.parse_args()

    print(f"{BOLD}Ultron doctor{RESET} {DIM}— {ROOT}{RESET}")
    check_python()
    check_deps()
    check_config()
    check_audio()
    check_tools(args.tools)
    check_browsers()

    total = sum(_counts.values())
    print(f"\n{BOLD}{total} checks{RESET}: "
          f"{GREEN}{_counts['PASS']} pass{RESET}, "
          f"{YELLOW}{_counts['WARN']} warn{RESET}, "
          f"{RED}{_counts['FAIL']} fail{RESET}")

    if _counts["FAIL"]:
        print(f"\n{RED}Fix the FAILs above before expecting the app to start.{RESET}")
        return 1
    print(f"\n{GREEN}No blocking problems found.{RESET}"
          f"{'' if args.tools else ' Run with --tools to validate every action.'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
