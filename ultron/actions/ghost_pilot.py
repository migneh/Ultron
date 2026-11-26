"""Pointer-only reviewed motion; legacy blind typing/click workflows fail closed.

A HUD approval cannot establish which application/control owns keyboard focus.
Search, note, typing and automatic result clicks require a future target-addressed
adapter; this module never falls back to Run dialogs, hotkeys or guessed pixels.
"""
from __future__ import annotations

import json

from ultron.core import desktop_motion

UNSUPPORTED = (
    "Blind GUI typing/click/search/app-launch workflows are disabled in ghost_pilot: "
    "no verified target-control adapter is configured. Host approval alone cannot "
    "establish safe focus. Use a dedicated search/document tool or pointer-only move/demo."
)


def human_glide_to(target_x: int, target_y: int, duration: float = 1.0, steps: int = 40):
    """Compatibility entry: always approved and bounded, never raw movement."""
    return desktop_motion.request("move", x=target_x, y=target_y, seconds=duration)


def human_type(text: str, base_delay: float = .05):
    return UNSUPPORTED


def ghost_search(query: str, browser: str = "chrome") -> str:
    return UNSUPPORTED


def ghost_write_note(app_name: str, message: str) -> str:
    return UNSUPPORTED


def ghost_demonstration() -> str:
    return desktop_motion.request("demo", seconds=2)


def ghost_pilot_handler(parameters: dict, player=None, **kwargs) -> str:
    if not isinstance(parameters, dict):
        return "Invalid pointer parameters."
    action = parameters.get("action", "")
    if not isinstance(action, str):
        return "Invalid pointer action."
    action = action.lower().strip()
    if action in {"search", "browse", "google", "web", "write", "note", "type_note", "notepad", "type", "human_type"}:
        return UNSUPPORTED
    if action in {"glide", "move"}:
        return human_glide_to(parameters.get("x"), parameters.get("y"), parameters.get("duration", 1))
    if action in {"demo", "showcase", "infinity", "reticle"}:
        return ghost_demonstration()
    if action == "status":
        return json.dumps(desktop_motion.status())
    if action == "cancel":
        return json.dumps(desktop_motion.cancel(parameters.get("operation_id", "")))
    return "Unknown action. Use move, demo, status or cancel; blind keyboard/click workflows disabled."


TOOL = {
    "name": "ghost_pilot",
    "description": "Host-approved pointer-only move/demo on Windows interactive primary display, with held-input checks, fail-safe and bounded steps. No clicks, typing, keyboard shortcuts, app launch or search workflows. Cannot verify application/hover effects. Other platforms fail closed. status/cancel affect only owned pointer operation.",
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "move | demo | status | cancel; old type/search/note workflows disabled"},
        "x": {"type": "INTEGER", "description": "Explicit primary-display target X, excluding fail-safe edges"},
        "y": {"type": "INTEGER", "description": "Explicit primary-display target Y, excluding fail-safe edges"},
        "duration": {"type": "NUMBER", "description": "Move request duration 0.2–3 seconds; default 1; not a hard native-call deadline"},
        "operation_id": {"type": "STRING", "description": "Exact currently owned operation ID from status, for cancellation"}
    }, "required": ["action"]},
    "handler": ghost_pilot_handler,
}
