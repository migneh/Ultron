# Legacy platform helpers; configuration remains in deployment config/api_keys.json.
import json
import platform

from ultron.paths import PROJECT_ROOT

_CONFIG_PATH = PROJECT_ROOT / "config" / "api_keys.json"

def _platform_os() -> str:
    """Auto-detect OS when config file is absent."""
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )

def get_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        return {}

def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    value = get_config().get("os_system")
    if isinstance(value, str) and value.strip().lower() in {"windows", "mac", "linux"}:
        return value.strip().lower()
    return _platform_os()

def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
