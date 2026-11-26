"""Side-effect-free prerequisite checks, not native/provider certification.

No optional-feature module imports, subprocesses, writes, model loading or network.
Reports metadata/status only, never config values, environment secrets or paths.
"""
from __future__ import annotations

import json
import os
import stat
import sys
from importlib import metadata

from ultron import __version__
from ultron.paths import CONFIG_DIR, PACKAGE_ROOT

PROFILES = {
    "desktop": ("PyQt6", "numpy", "sounddevice", "google-genai", "requests", "edge-tts", "miniaudio"),
    "test": ("pytest", "ruff", "requests", "beautifulsoup4", "fastapi", "httpx", "cryptography", "psutil", "numpy"),
    "workspace": ("google-auth", "google-auth-oauthlib", "keyring"),
}
RESOURCES = ("core/prompt.txt", "core/face_model.obj", "dashboard/static/app.html", "assets/ultron_avatar.png")


def _configuration():
    target = CONFIG_DIR / "api_keys.json"
    try:
        info = target.lstat()
        if not stat.S_ISREG(info.st_mode):
            return "unsupported_file_type"
        if info.st_size > 65536:
            return "oversized"
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
        with os.fdopen(os.open(target, flags), "rb") as stream:
            actual = os.fstat(stream.fileno())
            if not stat.S_ISREG(actual.st_mode):
                return "unsupported_file_type"
            raw = stream.read(65537)
        if len(raw) > 65536:
            return "oversized"
        return "object_present" if isinstance(json.loads(raw), dict) else "invalid_root"
    except FileNotFoundError:
        return "missing_first_run_setup_required"
    except (ValueError, UnicodeError):
        return "invalid_json"
    except OSError:
        return "unreadable"


def _resource(name):
    try:
        return (PACKAGE_ROOT / name).is_file()
    except OSError:
        return False


def inspect(profile="desktop"):
    if profile not in PROFILES:
        raise ValueError("Unknown diagnostics profile")
    dependencies = []
    for name in PROFILES[profile]:
        try:
            value = metadata.version(name)
        except metadata.PackageNotFoundError:
            dependencies.append({"distribution": name, "status": "missing"})
        except Exception:
            dependencies.append({"distribution": name, "status": "metadata_unreadable"})
        else:
            dependencies.append({"distribution": name, "status": "installed_metadata", "version": value})
    resources = [{"resource": name, "present": _resource(name)} for name in RESOURCES]
    configuration = _configuration()
    okay = (sys.version_info >= (3, 11) and all(d["status"] == "installed_metadata" for d in dependencies)
            and all(r["present"] for r in resources)
            and configuration in {"object_present", "missing_first_run_setup_required"})
    return {"application_version": __version__, "profile": profile, "python": sys.version.split()[0],
            "prerequisites_present": okay, "dependencies": dependencies, "resources": resources,
            "configuration_status": configuration,
            "limits": "Metadata/resource checks only: no imports, credential validation, GUI/audio/native models, provider connectivity or privileged-effect certification."}
