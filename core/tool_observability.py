"""Bounded, metadata-only dispatch telemetry. No arguments/results/exceptions stored.

A returned handler is not proof of delivery, successful side effects, completed
background work or approval. This layer never retries or cancels tools.
"""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Callable

_NAME = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]{0,63}\Z")
CODES = frozenset(
    {
        "HANDLER_RETURNED",
        "TOOL_EXCEPTION",
        "DEPENDENCY_MISSING",
        "INVALID_ARGUMENTS",
        "UNAVAILABLE",
        "DISABLED",
    }
)


def safe_name(value) -> str:
    return value if isinstance(value, str) and _NAME.fullmatch(value) else "unknown"


class DispatchIssue(Exception):
    def __init__(self, code: str):
        self.code = code if code in CODES else "TOOL_EXCEPTION"
        super().__init__(self.code)


class Observer:
    def __init__(self, capacity: int = 100):
        if not isinstance(capacity, int) or not 1 <= capacity <= 1000:
            raise ValueError("Invalid event capacity")
        self._lock = threading.Lock()
        self._events: deque[dict] = deque(maxlen=capacity)
        self._active = 0
        self._total = 0
        self._counts = dict.fromkeys(sorted(CODES), 0)

    def invoke(
        self, kind: str, name: str, fn: Callable[[], str], logger: Callable[[str], None]
    ) -> str:
        kind = kind if kind in {"action", "plugin"} else "tool"
        name = safe_name(name)
        started = time.monotonic()
        with self._lock:
            self._active += 1
        code = "TOOL_EXCEPTION"
        try:
            result = fn()
            code = "HANDLER_RETURNED"
            return result
        except DispatchIssue as error:
            code = error.code
        except ImportError:
            code = "DEPENDENCY_MISSING"
        except Exception:
            code = "TOOL_EXCEPTION"
        finally:
            elapsed = max(0.0, time.monotonic() - started)
            event = {
                "kind": kind,
                "name": name,
                "code": code,
                "duration_ms": round(elapsed * 1000, 3),
                "finished_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            }
            with self._lock:
                self._active -= 1
                self._total += 1
                self._counts[code] += 1
                self._events.append(event)
            try:
                logger(f"[tool] {kind}:{name} code={code} duration_ms={event['duration_ms']}")
            except Exception:
                pass  # a failing log sink must never repeat or mask an action
        messages = {
            "INVALID_ARGUMENTS": "parameters must be an object",
            "UNAVAILABLE": "tool is not registered/available",
            "DISABLED": "plugin is disabled",
            "DEPENDENCY_MISSING": "a required Python dependency could not be imported",
            "TOOL_EXCEPTION": "handler raised an exception; outcome may be partial or unknown; do not retry automatically",
        }
        return f"Tool '{name}' [{code}]: {messages.get(code, 'dispatch failed')}."

    def snapshot(self, limit: int = 20) -> dict:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100")
        with self._lock:
            return {
                "active": self._active,
                "total_finished": self._total,
                "counts": dict(self._counts),
                "recent": [dict(event) for event in list(self._events)[-limit:][::-1]],
                "retention": self._events.maxlen,
            }


OBSERVER = Observer()
_registry_lock = threading.Lock()
_registries: tuple = ()


def bind_registries(actions, plugins) -> None:
    global _registries
    with _registry_lock:
        _registries = (actions, plugins)


def registry_status() -> dict:
    with _registry_lock:
        registries = _registries
    if not registries:
        return {"state": "not_bound", "actions": [], "plugins": []}
    return {
        "state": "bound",
        "actions": registries[0].status_snapshot(),
        "plugins": registries[1].status_snapshot(),
    }
