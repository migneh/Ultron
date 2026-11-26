"""Session undo registry with exact-entry host approval.

Registered callbacks remain trusted, action-specific code; approval cannot prove
that a callback is a safe inverse. File callbacks perform their own conflict
checks. Other legacy callbacks may have weaker guarantees. No durable history.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from ultron.core import operation_policy as policy

# How many reversible operations we keep. Ten is roughly "this conversation":
# far enough back to catch a mistake you noticed a few commands later, short
# enough that a closure holding a file's old contents cannot pile up in RAM.
MAX_DEPTH = 10


@dataclass(frozen=True)
class _Entry:
    label:   str                    # human sentence, spoken back to the user
    undo:    Callable[[], str]      # returns a short result string
    at:      float = field(default_factory=time.monotonic)
    entry_id: str = field(default_factory=lambda: uuid4().hex)
    detail: str = "Legacy callback: exact native/file effects are action-defined, not independently verified by the undo registry."


_stack: list[_Entry] = []
_lock = threading.Lock()


def push_undo(label: str, undo_fn: Callable[[], str], *, detail: str = "") -> None:
    """Record that `label` just happened and `undo_fn()` reverses it.

    Called from action handlers, which run in executor threads — hence the
    lock. Never raises: a broken undo registration must not take down the
    action that actually succeeded."""
    if not callable(undo_fn):
        return
    try:
        with _lock:
            _stack.append(_Entry(label=str(label)[:120], undo=undo_fn,
                                 **({"detail": str(detail)[:16384]} if detail else {})))
            # Drop the oldest rather than refusing the newest: the recent past
            # is what people ask to undo.
            while len(_stack) > MAX_DEPTH:
                _stack.pop(0)
    except Exception as e:                                  # pragma: no cover
        print(f"[Undo] push failed: {e}")


def can_undo() -> bool:
    with _lock:
        return bool(_stack)


def peek() -> str:
    """Label of the operation that `undo_last()` would reverse, or ''."""
    with _lock:
        return _stack[-1].label if _stack else ""


def history() -> list[str]:
    """Most recent first — used by the UI panel and the `undo` tool's list mode."""
    with _lock:
        return [e.label for e in reversed(_stack)]


def _execute_undo(plan, entry):
    policy.consume(plan)
    with _lock:
        if not _stack or _stack[-1] is not entry or plan.payload()["entry_id"] != entry.entry_id:
            return "Undo rejected: stack changed; no callback executed. Request a fresh preview."
        _stack.pop()
    # Pop before effects: partial failures must not silently retry.
    try:
        detail = entry.undo() or "No callback result provided; outcome unverified."
    except Exception:
        return "Could not undo: conflict or execution failure; outcome may be partial. Entry consumed; no automatic retry."
    return f"Undo callback returned for '{entry.label}': {detail}"


def undo_last() -> str:
    """Approve one exact top entry; denial/expiry never pop the stack."""
    with _lock:
        entry = _stack[-1] if _stack else None
    if entry is None:
        return "There is nothing to undo in this session."
    plan = policy.prepare("session.undo", (entry.entry_id,),
                          {"entry_id": entry.entry_id, "label": entry.label, "detail": entry.detail})
    return policy.request(plan, title="Run one registered undo callback",
                          detail=f"Exact session entry: {entry.entry_id}\nAction: {entry.label}\n{entry.detail}\n"
                          "Run this action's registered inverse only if it is still the most recent entry. "
                          "Callbacks are trusted application code, not guaranteed safe or complete inverses; "
                          "they may affect files or native settings. Conflict/partial failure consumes the entry; "
                          "no automatic retry. History is session-only.",
                          execute=lambda approved: _execute_undo(approved, entry))


def clear() -> None:
    """Forget the stack. Called when the app shuts down so closures holding old
    file contents do not outlive the session."""
    with _lock:
        _stack.clear()
