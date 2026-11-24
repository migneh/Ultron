"""
core/config.py — centralized, fail-safe configuration for Ultron.

Why this exists
    Before this module, config/api_keys.json was read by ~20 hand-rolled
    `_get_api_key()` copies. Most returned "" on failure, but
    actions/web_search.py did `json.load(f)["gemini_api_key"]` — a missing
    file or missing key crashed that action at runtime. This module is the
    single place that loads, validates, and serves configuration.

Design
    * Never raises. Missing file, bad JSON, or missing key -> empty dict /
      empty string, logged at the appropriate level.
    * The environment variable GEMINI_API_KEY overrides the config file, so
      operators can inject secrets without touching disk.
    * All access goes through the logging module (not print), so operators
      can capture diagnostics to logs/ultron.log.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

LOG = logging.getLogger("ultron.config")

# Directory for runtime artifacts (logs, audit trails). *.log is gitignored.
LOGS_DIR = Path(__file__).resolve().parent.parent / "logs"


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


BASE_DIR = get_base_dir()
CONFIG_DIR = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"


# ── Logging ──────────────────────────────────────────────────────────────

def setup_logging(level: int = logging.INFO,
                  log_to_file: bool = True,
                  log_file: Path | None = None) -> logging.Logger:
    """Configure the Ultron root logger once at startup.

    Writes INFO+ to console and (optionally) DEBUG+ to a rotating file so
    diagnostics survive a session without printing noise to the user.
    Returns the root logger so callers can re-level it.
    """
    root = logging.getLogger("ultron")
    root.setLevel(level)

    # Clear any handlers a previous setup left behind (idempotent).
    for h in list(root.handlers):
        root.removeHandler(h)

    fmt = logging.Formatter(
        "%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    sh = logging.StreamHandler(sys.stdout)
    sh.setLevel(level)
    sh.setFormatter(fmt)
    root.addHandler(sh)

    if log_to_file:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        target = log_file or (LOGS_DIR / "ultron.log")
        fh = RotatingFileHandler(target, maxBytes=2_000_000, backupCount=3,
                                 encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        root.addHandler(fh)

    root.debug("Ultron logging initialized (level=%s)", logging.getLevelName(level))
    return root


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"ultron.{name}")


# ── Config loading ───────────────────────────────────────────────────────

def load_api_keys() -> dict:
    """Load config/api_keys.json. Never raises; returns {} on any problem."""
    try:
        if not CONFIG_FILE.exists():
            LOG.debug("config file not present: %s", CONFIG_FILE)
            return {}
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            LOG.warning("config file %s did not decode to an object; ignoring",
                        CONFIG_FILE)
            return {}
        LOG.debug("loaded %d keys from %s", len(data), CONFIG_FILE)
        return data
    except json.JSONDecodeError as e:
        LOG.warning("config file %s is not valid JSON (%s); ignoring", CONFIG_FILE, e)
        return {}
    except Exception as e:  # pragma: no cover - defensive catch-all; config must never raise  # noqa: BLE001
        LOG.warning("could not read config file %s (%s); ignoring", CONFIG_FILE, e)
        return {}


def save_api_keys(data: dict) -> None:
    """Persist the whole config dict to api_keys.json (creates the dir)."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    LOG.debug("wrote %d keys to %s", len(data), CONFIG_FILE)


def get_gemini_key() -> str | None:
    """Return the Gemini API key, or None if not configured.

    Resolution order:
      1. GEMINI_API_KEY environment variable
      2. config/api_keys.json  ("gemini_api_key", then "api_key")
    """
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key:
        LOG.debug("using GEMINI_API_KEY from environment")
        return env_key

    data = load_api_keys()
    key = (data.get("gemini_api_key") or data.get("api_key") or "").strip()
    if key:
        return key
    LOG.debug("no Gemini API key found in environment or config file")
    return None


def require_gemini_key() -> str:
    """Return the Gemini key, or raise RuntimeError if missing.

    Use at startup so the app fails fast with a clear message instead of
    dying inside a random action later.
    """
    key = get_gemini_key()
    if not key:
        raise RuntimeError(
            "No Gemini API key configured. Set GEMINI_API_KEY or write "
            "config/api_keys.json (see config/api_keys.json.example)."
        )
    return key


def get_str(key: str, default: str = "") -> str:
    """Read a single string value from config (env override, then file)."""
    env_val = os.environ.get(key, "").strip()
    if env_val:
        return env_val
    return str(load_api_keys().get(key, default))


def get_bool(key: str, default: bool = False) -> bool:
    """Read a boolean config value (env override, then file)."""
    raw = get_str(key, "").strip().lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default


def get_ai_provider() -> str:
    """Return the configured AI provider (env override, then file).

    Reads AI_PROVIDER env var, then config keys `ai_provider`, then falls back
    to the legacy `provider` key for backwards compatibility.
    """
    env_val = os.environ.get("AI_PROVIDER", "").strip()
    if env_val:
        return env_val
    data = load_api_keys()
    return str(data.get("ai_provider") or data.get("provider") or "gemini")


def get_ai_model() -> str | None:
    """Return the configured AI model (env override, then file).

    Reads AI_MODEL env var, then config keys `ai_model`, then falls back to
    the legacy `model` key for backwards compatibility.
    """
    env_val = os.environ.get("AI_MODEL", "").strip()
    if env_val:
        return env_val
    data = load_api_keys()
    return str(data.get("ai_model") or data.get("model") or "") or None
