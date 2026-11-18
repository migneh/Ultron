"""
quick_timer.py — Countdown timer and desktop notification action for Ultron AI.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

import threading
import time
from typing import Optional


def _run_timer(seconds: int, message: str, speak_cb=None, player_cb=None):
    """Wait in a background thread and then announce completion."""
    time.sleep(seconds)
    msg = f"Timer complete: {message or 'Time is up!'}"
    if player_cb and hasattr(player_cb, "write_log"):
        player_cb.write_log(f"⏰ {msg}")
    if speak_cb and callable(speak_cb):
        try:
            speak_cb(msg)
        except Exception:
            pass


def start_countdown_timer(seconds: int, message: str = "", speak_cb=None, player_cb=None) -> str:
    secs = max(1, int(seconds))
    mins = secs // 60
    rem_secs = secs % 60
    time_desc = f"{mins} minute(s)" if mins and not rem_secs else f"{mins}m {rem_secs}s" if mins else f"{secs} seconds"

    t = threading.Thread(
        target=_run_timer,
        args=(secs, message, speak_cb, player_cb),
        daemon=True
    )
    t.start()
    return f"Timer set for {time_desc} ({message or 'countdown'}). I will alert you when it expires."


def _as_int(value, field: str) -> int:
    """Coerce a tool argument to int, or raise ValueError with a readable reason.

    The model is *asked* for INTEGER, but it does not always comply — "90" and
    1.5 both arrive in practice. A bare int() on those raised straight out of the
    handler, which the loader can only report as a failure; tool handlers are
    supposed to answer instead.
    """
    if value is None or value == "":
        return 0
    if isinstance(value, bool):            # bool is an int subclass; not a duration
        raise ValueError(f"{field} must be a number, not true/false")
    try:
        return int(float(value))           # accepts 90, "90", " 90 ", 1.5
    except (TypeError, ValueError):
        raise ValueError(f"{field} must be a number, got {value!r}")


def quick_timer_handler(parameters: dict, speak=None, player=None, **kwargs) -> str:
    seconds = parameters.get("seconds") or 0
    minutes = parameters.get("minutes") or 0
    message = parameters.get("message", "Timer finished")

    only_one_given = bool(parameters.get("seconds") or parameters.get("minutes"))
    try:
        total_secs = _as_int(seconds, "seconds") + _as_int(minutes, "minutes") * 60
    except ValueError as exc:
        return f"I could not set that timer — {exc}."

    if not only_one_given:
        # Previously this silently became a one-minute timer, so a mis-routed
        # call ("set a timer") produced a countdown nobody asked for.
        return "How long should the timer run? Tell me minutes or seconds."

    if total_secs <= 0:
        return "That duration has already passed — give me a positive number of minutes or seconds."

    return start_countdown_timer(total_secs, message=message, speak_cb=speak, player_cb=player)


TOOL = {
    "name": "quick_timer",
    "description": (
        "Sets a quick countdown timer or alarm that alerts the user when time is up. "
        "Use when user says: 'set a timer for 5 minutes', 'timer for 30 seconds', 'remind me in 2 minutes'."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "minutes": {
                "type": "INTEGER",
                "description": "Number of minutes"
            },
            "seconds": {
                "type": "INTEGER",
                "description": "Number of seconds"
            },
            "message": {
                "type": "STRING",
                "description": "Timer label or alert message (e.g. 'check oven', 'tea ready')"
            }
        },
        "required": []
    },
    "handler": quick_timer_handler
}
