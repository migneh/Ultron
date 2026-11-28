"""Read-only, local-only tool dispatch/dependency diagnostics."""

from __future__ import annotations

import importlib.util
import json
import shutil
from typing import Any

from ultron.core.tool_observability import OBSERVER, registry_status

# Fixed allowlists: do not import provider modules, run programs or inspect
# credentials just to report whether a dependency can be located.
_MODULES = ("ddgs", "requests", "urllib3", "send2trash", "bs4", "PyQt6", "tzdata")
_PROGRAMS = ("systemctl", "notify-send", "osascript", "powershell", "adb", "ffmpeg")


def dependencies() -> dict:
    modules, programs = {}, {}
    for name in _MODULES:
        try:
            modules[name] = "locatable" if importlib.util.find_spec(name) is not None else "missing"
        except Exception:
            modules[name] = "unknown"
    for name in _PROGRAMS:
        try:
            programs[name] = "on_path" if shutil.which(name) else "not_on_path"
        except Exception:
            programs[name] = "unknown"
    return {
        "python_modules": modules,
        "programs": programs,
        "meaning": "Presence only, not importability, version compatibility, permissions, native support or service health. Missing optional/platform-specific dependencies need not be errors.",
    }


def tool_status(parameters: dict, **kwargs) -> str:
    if not isinstance(parameters, dict) or parameters.keys() - {"section", "limit"}:
        return "Tool status [INVALID_ARGUMENTS]: use section and optional limit only."
    section = parameters.get("section", "summary")
    limit = parameters.get("limit", 20)
    if not isinstance(section, str) or section not in {
        "summary",
        "recent",
        "dependencies",
        "registry",
    }:
        return "Tool status [INVALID_ARGUMENTS]: section must be summary, recent, dependencies or registry."
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        return "Tool status [INVALID_ARGUMENTS]: limit must be an integer from 1 to 100."
    report: dict[str, Any] = {
        "scope": "Local registry dispatch only; inline core tools, direct helper calls and later background/approval work are not measured. HANDLER_RETURNED is not proof of effect success. Registry lists capped at 200 entries each.",
        "privacy": "Metadata only, process-memory retention. No arguments, results, raw exception messages, credentials or file paths in this telemetry. Tool names and timings are visible to callers. This is not a global log scrubber.",
    }
    if section in {"summary", "recent"}:
        report["dispatch"] = OBSERVER.snapshot(limit)
    if section in {"summary", "registry"}:
        try:
            report["registry"] = registry_status()
        except Exception:
            report["registry"] = {"state": "snapshot_unavailable"}
    if section in {"summary", "dependencies"}:
        report["dependencies"] = dependencies()
    return json.dumps(report, ensure_ascii=True, indent=2)


TOOL = {
    "name": "tool_status",
    "description": "Read-only local diagnostics: bounded recent action/plugin dispatch timings and outcome codes, registered/enabled discovery state, and fixed optional dependency presence checks. No network, shell execution, credentials or raw tool arguments/results. HANDLER_RETURNED does not prove an effect succeeded. Does not monitor inline core tools or background work.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "section": {
                "type": "STRING",
                "enum": ["summary", "recent", "dependencies", "registry"],
            },
            "limit": {
                "type": "INTEGER",
                "description": "Recent dispatch entries, 1–100, default 20",
            },
        },
        "required": [],
    },
    "handler": tool_status,
}
