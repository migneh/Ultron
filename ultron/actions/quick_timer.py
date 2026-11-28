"""Manage session-only countdowns with cancellable, monotonic scheduling.

No timers are restored after shutdown. Use the reminder tool for OS-scheduled
notifications. Completion callbacks run on a worker thread, like the old tool.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Protocol
from uuid import uuid4

MAX_DURATION = 7 * 24 * 60 * 60
MAX_ACTIVE = 32
MAX_HISTORY = 100


class _Handle(Protocol):
    daemon: bool

    def start(self) -> None: ...
    def cancel(self) -> None: ...


@dataclass
class _Countdown:
    timer_id: str
    label: str
    duration: int
    remaining: float
    deadline: float
    state: str = "running"
    generation: int = 0
    handle: _Handle | None = None
    speak: object = field(default=None, repr=False)
    player: object = field(default=None, repr=False)


class TimerService:
    """Thread-safe timer state; injected clock/scheduler make races testable."""

    def __init__(
        self, clock: Callable[[], float] = time.monotonic, timer_factory: Callable = threading.Timer
    ):
        self._clock = clock
        self._timer_factory = timer_factory
        self._lock = threading.RLock()
        self._timers: dict[str, _Countdown] = {}

    def _snapshot(self, entry: _Countdown) -> dict:
        remaining = (
            max(0.0, entry.deadline - self._clock())
            if entry.state == "running"
            else entry.remaining
        )
        return {
            "id": entry.timer_id,
            "label": entry.label,
            "state": entry.state,
            "duration_seconds": entry.duration,
            "remaining_seconds": math.ceil(remaining),
        }

    def _resolve(self, reference: str) -> _Countdown:
        reference = reference.strip()
        if reference in self._timers:
            return self._timers[reference]
        candidates = [
            entry
            for entry in self._timers.values()
            if entry.state in {"running", "paused"}
            and (not reference or entry.label.casefold() == reference.casefold())
        ]
        if len(candidates) == 1:
            return candidates[0]
        if len(candidates) > 1:
            raise ValueError("Multiple timers match. List timers and use an exact timer_id.")
        raise ValueError("Timer not found. List timers to get an exact timer_id.")

    def _arm(self, entry: _Countdown):
        generation = entry.generation
        handle = self._timer_factory(
            entry.remaining, lambda: self._finish(entry.timer_id, generation)
        )
        handle.daemon = True
        entry.handle = handle
        handle.start()

    def _trim(self):
        terminal = [
            key for key, entry in self._timers.items() if entry.state not in {"running", "paused"}
        ]
        for key in terminal[:-MAX_HISTORY]:
            del self._timers[key]

    def _finish(self, timer_id: str, generation: int):
        with self._lock:
            entry = self._timers.get(timer_id)
            if entry is None or entry.state != "running" or entry.generation != generation:
                return  # a cancelled/paused/replaced callback must never announce
            entry.state = "completed"
            entry.remaining = 0
            speak, player = entry.speak, entry.player
            entry.speak = entry.player = entry.handle = None
            message = f"Timer complete: {entry.label}"
            self._trim()
        # One failed notification channel must not prevent the other.
        try:
            if player is not None and hasattr(player, "write_log"):
                player.write_log(f"⏰ {message}")
        except Exception:
            pass
        try:
            if callable(speak):
                speak(message)
        except Exception:
            pass

    def start(self, seconds: int, label: str = "countdown", speak=None, player=None) -> dict:
        if (
            isinstance(seconds, bool)
            or not isinstance(seconds, int)
            or not 1 <= seconds <= MAX_DURATION
        ):
            raise ValueError(f"Duration must be a whole number from 1 to {MAX_DURATION} seconds.")
        if not isinstance(label, str):
            raise ValueError("Timer message must be text.")
        label = " ".join(label.split())[:200] or "countdown"
        with self._lock:
            if sum(e.state in {"running", "paused"} for e in self._timers.values()) >= MAX_ACTIVE:
                raise ValueError(
                    f"At most {MAX_ACTIVE} active timers are allowed. Cancel one first."
                )
            timer_id = uuid4().hex[:12]
            entry = _Countdown(
                timer_id,
                label,
                seconds,
                float(seconds),
                self._clock() + seconds,
                speak=speak,
                player=player,
            )
            self._timers[timer_id] = entry
            try:
                self._arm(entry)
            except Exception:
                del self._timers[timer_id]
                raise
            return self._snapshot(entry)

    def list(self, include_finished: bool = False) -> list[dict]:
        with self._lock:
            return [
                self._snapshot(entry)
                for entry in self._timers.values()
                if include_finished or entry.state in {"running", "paused"}
            ]

    def status(self, reference: str = "") -> dict:
        with self._lock:
            return self._snapshot(self._resolve(reference))

    def change(self, action: str, reference: str = "") -> dict:
        with self._lock:
            entry = self._resolve(reference)
            if action == "pause" and entry.state == "running":
                entry.remaining = max(0.0, entry.deadline - self._clock())
                entry.state = "paused"
                entry.generation += 1
                if entry.handle is not None:
                    entry.handle.cancel()
                entry.handle = None
            elif action == "resume" and entry.state == "paused":
                entry.deadline = self._clock() + entry.remaining
                entry.state = "running"
                entry.generation += 1
                try:
                    self._arm(entry)
                except Exception:
                    entry.state = "paused"
                    entry.handle = None
                    raise
            elif action == "cancel" and entry.state in {"running", "paused"}:
                entry.remaining = (
                    max(0.0, entry.deadline - self._clock())
                    if entry.state == "running"
                    else entry.remaining
                )
                entry.state = "cancelled"
                entry.generation += 1
                if entry.handle is not None:
                    entry.handle.cancel()
                entry.handle = entry.speak = entry.player = None
                self._trim()
            elif action not in {"pause", "resume", "cancel"}:
                raise ValueError(f"Unknown timer action: {action}")
            return self._snapshot(entry)


_SERVICE = TimerService()


def _describe(timer: dict) -> str:
    return (
        f"{timer['id']} — {timer['label']}: {timer['state']}, "
        f"{timer['remaining_seconds']}s remaining"
    )


def start_countdown_timer(seconds: int, message: str = "", speak_cb=None, player_cb=None) -> str:
    """Backwards-compatible public entrypoint, now returning a manageable timer ID."""
    timer = _SERVICE.start(seconds, message, speak_cb, player_cb)
    return f"Timer set: {_describe(timer)}. Session only; stops when Ultron exits."


def _duration_part(value, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, str)):
        raise ValueError(f"{name} must be a non-negative whole number.")
    try:
        result = int(value)
    except ValueError:
        raise ValueError(f"{name} must be a non-negative whole number.") from None
    if result < 0:
        raise ValueError(f"{name} must be non-negative.")
    return result


def quick_timer_handler(parameters: dict, speak=None, player=None, **kwargs) -> str:
    try:
        if not isinstance(parameters, dict):
            raise ValueError("Timer parameters must be an object.")
        action = parameters.get("action", "start")
        if not isinstance(action, str):
            raise ValueError("Timer action must be text.")
        action = action.strip().lower()
        if action == "start":
            seconds = _duration_part(parameters.get("seconds", 0), "seconds")
            minutes = _duration_part(parameters.get("minutes", 0), "minutes")
            total = seconds + minutes * 60
            if "seconds" not in parameters and "minutes" not in parameters:
                total = 60
            return start_countdown_timer(
                total, parameters.get("message", "countdown"), speak, player
            )
        if action == "list":
            timers = _SERVICE.list()
            return (
                "Active timers:\n" + "\n".join(map(_describe, timers))
                if timers
                else "No active timers."
            )
        reference = parameters.get("timer_id") or parameters.get("message") or ""
        if not isinstance(reference, str):
            raise ValueError("timer_id must be text.")
        if action == "status":
            return _describe(_SERVICE.status(reference))
        if action in {"pause", "resume", "cancel"}:
            return _describe(_SERVICE.change(action, reference))
        return "Unknown timer action. Use start, list, status, pause, resume, or cancel."
    except (ValueError, TypeError, OverflowError) as error:
        return f"Timer request rejected: {error}"
    except Exception as error:
        return f"Timer operation failed: {error}"


TOOL = {
    "name": "quick_timer",
    "description": (
        "Manage session-only countdowns: start, list, status, pause, resume, cancel. "
        "Start returns a timer_id; use it to manage that timer. An exact unique message label also works. "
        "Timers stop when Ultron exits. Use reminder for OS-scheduled notifications. "
        "Default duration is 60 seconds only when no duration fields are supplied; maximum 7 days."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["start", "list", "status", "pause", "resume", "cancel"],
                "description": "Operation; default start for existing calls",
            },
            "minutes": {
                "type": "INTEGER",
                "description": "Non-negative whole minutes, added to seconds",
            },
            "seconds": {
                "type": "INTEGER",
                "description": "Non-negative whole seconds, added to minutes",
            },
            "message": {
                "type": "STRING",
                "description": "Timer label; also usable as exact unique lookup label",
            },
            "timer_id": {
                "type": "STRING",
                "description": "ID returned by start/list, required when labels are ambiguous",
            },
        },
        "required": [],
    },
    "handler": quick_timer_handler,
}
