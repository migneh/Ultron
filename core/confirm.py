"""Human-only confirmation with immutable request identities.

Existing actions retain request()/resolve(). The HUD additionally binds request
IDs so delayed clicks/hide signals cannot approve or dismiss a newer request.
Only one request may wait at a time; requests never silently replace one another.
Callbacks run outside the gate lock and cannot forge acceptance via tool params.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

TIMEOUT_SECONDS = 90.0


@dataclass
class _Pending:
    key: str
    title: str
    detail: str
    run: Callable[[], str]
    at: float
    request_id: str = field(default_factory=lambda: uuid4().hex)
    on_cancel: Callable[[str], None] | None = None


_pending: _Pending | None = None
_lock = threading.Lock()
_show_cb: Callable | None = None
_hide_cb: Callable | None = None
_log_cb: Callable | None = None
_show_with_id_cb: Callable | None = None
_hide_with_id_cb: Callable | None = None


def bind(show, hide, log=None, *, show_with_id=None, hide_with_id=None) -> None:
    """ID-aware callbacks are used by the HUD; two-argument clients remain supported."""
    global _show_cb, _hide_cb, _log_cb, _show_with_id_cb, _hide_with_id_cb
    _show_cb, _hide_cb, _log_cb = show, hide, log
    _show_with_id_cb, _hide_with_id_cb = show_with_id, hide_with_id


def _log(message: str):
    if _log_cb:
        try:
            _log_cb(message)
        except Exception:
            pass


def _hide(pending: _Pending):
    try:
        if _hide_with_id_cb:
            _hide_with_id_cb(pending.request_id)
        elif _hide_cb:
            _hide_cb()
    except Exception:
        pass


def _cancelled(callback: Callable | None, reason: str):
    if callback:
        try:
            callback(reason)
        except Exception:
            _log("ERR: Could not update cancelled confirmation state.")


def _expire():
    global _pending
    expired = None
    with _lock:
        if _pending is not None and time.monotonic() - _pending.at > TIMEOUT_SECONDS:
            expired, _pending = _pending, None
    if expired is not None:
        _hide(expired)
        _cancelled(expired.on_cancel, "expired")
        _log(f"SYS: Confirmation expired — {expired.title}")


def is_current(request_id: str) -> bool:
    """Let the GUI discard a queued show signal for an obsolete request."""
    with _lock:
        return (
            _pending is not None
            and _pending.request_id == request_id
            and time.monotonic() - _pending.at <= TIMEOUT_SECONDS
        )


def request(
    key: str,
    title: str,
    detail: str,
    run: Callable[[], str],
    *,
    on_cancel: Callable[[str], None] | None = None,
) -> str:
    global _pending
    _expire()
    if _show_cb is None and _show_with_id_cb is None:
        _cancelled(on_cancel, "unavailable")
        return (
            f"I cannot confirm '{title}' right now because the interface is "
            "not available, so I have not done it."
        )
    with _lock:
        busy = _pending is not None
        if not busy:
            pending = _Pending(key, title, detail, run, time.monotonic(), on_cancel=on_cancel)
            _pending = pending
    if busy:
        _cancelled(on_cancel, "busy")
        return "[CONFIRMATION_BUSY] Another confirmation is waiting. Resolve it on the HUD first. Nothing new was approved."
    try:
        if _show_with_id_cb:
            _show_with_id_cb(title, detail, pending.request_id)
        elif _show_cb:
            _show_cb(title, detail)
    except Exception:
        with _lock:
            if _pending is pending:
                _pending = None
        _hide(pending)
        _cancelled(on_cancel, "unavailable")
        return "Could not display the confirmation. Nothing was approved."
    _log(f"SYS: Awaiting confirmation — {title}")
    return (
        f"[CONFIRMATION_PENDING] I have put a confirmation on screen for: {title}. "
        "Say ONE short sentence in the user's own language telling them to review "
        "and confirm it on the HUD. Do not claim it is done."
    )


def resolve(accepted: bool, request_id: str | None = None) -> None:
    """Called by the interface, never exposed as a model tool.

    ID-less resolution remains for legacy in-process clients. The main HUD
    always supplies an ID; stale ID-aware events cannot consume the next request.
    """
    global _pending
    _expire()
    with _lock:
        if _pending is None or (request_id is not None and _pending.request_id != request_id):
            return
        pending, _pending = _pending, None
    _hide(pending)
    if accepted is not True:
        _cancelled(pending.on_cancel, "cancelled")
        _log(f"SYS: Cancelled — {pending.title}")
        return

    def worker():
        try:
            result = pending.run() or "Done."
            _log(f"SYS: Confirmed — {pending.title}. {result}")
        except Exception:
            # Do not leak request payloads, credential-bearing URLs or traceback data.
            _log(f"ERR: Confirmed action failed — {pending.title}")

    try:
        threading.Thread(target=worker, daemon=True, name=f"confirm-{pending.key}").start()
    except Exception:
        _cancelled(pending.on_cancel, "unavailable")
        _log(f"ERR: Could not start confirmed action — {pending.title}")


def cancel_pending(key: str) -> bool:
    """Cancel only the matching action; never consumes another pending banner."""
    global _pending
    _expire()
    with _lock:
        if _pending is None or _pending.key != key:
            return False
        pending, _pending = _pending, None
    _hide(pending)
    _cancelled(pending.on_cancel, "cancelled")
    return True


def pending_title() -> str:
    _expire()
    with _lock:
        return _pending.title if _pending else ""
