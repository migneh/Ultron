"""Approval-gated pointer-only motion, not autonomous GUI interaction.

Windows interactive-desktop/button guards are best effort, not atomic isolation.
No clicks, keypresses, app launch, typing, screenshots or foreground assumptions.
"""
from __future__ import annotations

import ctypes
import json
import math
import platform
import threading
import time
from pathlib import Path

from ultron.core import file_safety
from ultron.core import operation_policy as policy
from ultron.core.background_jobs import OwnerLock

_ACTIVE_LOCK = threading.Lock()
_ADMISSION = threading.Lock()
_ACTIVE = None
_CLOSED = False
_clock = time.monotonic


def _backend():
    if platform.system() != "Windows":
        raise ValueError("Native held-input/desktop guards currently support Windows only")
    import pyautogui
    pyautogui.FAILSAFE = True
    return pyautogui


def _held_input():
    """Require readable active input desktop matching this thread's desktop."""
    user = ctypes.WinDLL("user32", use_last_error=True)
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    user.OpenInputDesktop.argtypes = [ctypes.c_uint32, ctypes.c_bool, ctypes.c_uint32]
    user.OpenInputDesktop.restype = ctypes.c_void_p
    user.CloseDesktop.argtypes = [ctypes.c_void_p]
    user.GetThreadDesktop.argtypes = [ctypes.c_uint32]
    user.GetThreadDesktop.restype = ctypes.c_void_p
    user.GetUserObjectInformationW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_uint32, ctypes.POINTER(ctypes.c_uint32)]
    user.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user.GetAsyncKeyState.restype = ctypes.c_short
    kernel.GetCurrentThreadId.restype = ctypes.c_uint32
    desktop = user.OpenInputDesktop(0, False, 1)
    if not desktop:
        raise ValueError("Interactive input desktop unavailable")
    try:
        def name(handle):
            text, needed = ctypes.create_unicode_buffer(256), ctypes.c_uint32()
            if not handle or not user.GetUserObjectInformationW(handle, 2, text, ctypes.sizeof(text), ctypes.byref(needed)):
                raise ValueError("Desktop identity unavailable")
            return text.value
        if name(desktop) != name(user.GetThreadDesktop(kernel.GetCurrentThreadId())):
            raise ValueError("Input desktop changed/inaccessible")
        # Mouse buttons plus shift/control/alt and both Windows keys.
        return any(user.GetAsyncKeyState(key) & 0x8000 for key in (1, 2, 4, 5, 6, 16, 17, 18, 91, 92))
    finally:
        user.CloseDesktop(desktop)


def _snapshot(backend):
    if not backend.FAILSAFE or _held_input():
        raise ValueError("Fail-safe disabled or input is held")
    width, height = backend.size()
    x, y = backend.position()
    if not 4 <= width <= 32768 or not 4 <= height <= 32768 or not 0 < x < width - 1 or not 0 < y < height - 1:
        raise ValueError("Unsupported geometry or cursor at display/fail-safe edge")
    return (width, height), (x, y)


def _execute(plan):
    global _ACTIVE
    policy.consume(plan)
    with _ACTIVE_LOCK:
        if _CLOSED:
            return "Pointer service shut down; nothing moved."
    if not _ADMISSION.acquire(blocking=False):
        return "Another owned pointer operation is active; nothing new moved."
    owner = None
    try:
        path = Path.home() / ".ultron" / "pointer-motion.owner.lock"
        file_safety.checked(path, lambda _: True)
        path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        owner = OwnerLock(path)
        if not owner.acquire():
            return "Another runtime owns pointer motion; nothing moved."
        payload = plan.payload()
        backend = _backend()
        size, previous = _snapshot(backend)
        if list(size) != payload["display"]:
            return "Display geometry changed; nothing moved."
        if payload["action"] == "move":
            end = payload["target"]
            points = [(round(previous[0] + (end[0] - previous[0]) * index / 20),
                       round(previous[1] + (end[1] - previous[1]) * index / 20)) for index in range(1, 21)]
        else:
            points = [tuple(point) for point in payload["points"]]
        stop = threading.Event()
        with _ACTIVE_LOCK:
            if _CLOSED:
                return "Pointer service shut down; nothing moved."
            _ACTIVE = {"operation_id": plan.operation_id, "stop": stop}
        deadline = _clock() + payload["seconds"] + 1
        completed = 0
        try:
            for point in points:
                if stop.is_set() or _clock() >= deadline:
                    return f"Pointer motion stopped after {completed} steps; no rollback/retry."
                current_size, current = _snapshot(backend)
                if current_size != size or current != previous:
                    return f"Pointer/display changed externally after {completed} steps; stopped without retry."
                backend.moveTo(*point, duration=0, _pause=False)
                previous = point
                completed += 1
                if stop.wait(payload["seconds"] / len(points)):
                    return f"Pointer motion cancelled after {completed} steps; no rollback."
            final_size, observed = _snapshot(backend)
            if final_size != size or observed != previous:
                return "Motion submitted; final pointer target not observed. No retry."
            return "Pointer target observed after bounded motion. No clicks, typing or app actions were sent; application effects/hover behavior not verified."
        except Exception:
            return f"Pointer motion interrupted after {completed} steps; outcome may be partial. No retry."
        finally:
            with _ACTIVE_LOCK:
                _ACTIVE = None
    finally:
        if owner is not None:
            owner.release()
        _ADMISSION.release()


def request(action, *, x=None, y=None, seconds=1):
    if (not isinstance(action, str) or action not in {"move", "demo"} or type(seconds) not in (int, float)
            or not .2 <= seconds <= 3 or not math.isfinite(seconds)):
        return "Use move/demo and a finite duration from 0.2 to 3 seconds."
    try:
        backend = _backend()
        size, _ = _snapshot(backend)
        payload = {"action": action, "display": list(size), "seconds": seconds}
        if action == "move":
            if type(x) is not int or type(y) is not int or not 0 < x < size[0] - 1 or not 0 < y < size[1] - 1:
                return "Choose explicit integer coordinates inside the primary display, excluding fail-safe edges."
            payload["target"] = [x, y]
        else:
            cx, cy = size[0] // 2, size[1] // 2
            payload["points"] = [[max(1, min(size[0] - 2, round(cx + size[0] * .15 * math.sin(i * math.pi / 12)))),
                                  max(1, min(size[1] - 2, round(cy + size[1] * .1 * math.sin(i * math.pi / 6))))] for i in range(25)]
        plan = policy.prepare("desktop.pointer_only", ("interactive_primary_display",), payload)
        return policy.request(plan, title="Move pointer only (no clicks or typing)",
                              detail="Pointer starts from its position at execution, including after your HUD click. "
                              "Do not hold buttons/modifiers. Motion can trigger hover/accessibility behaviors; this is not a GUI sandbox. "
                              "Best-effort stop on user motion, held input, geometry change, cancellation or fail-safe. "
                              "No window/control targeting, clicking, typing, shell, screenshots or app launch.\n"
                              + json.dumps(payload), execute=_execute)
    except Exception:
        return "Pointer preview unavailable. Requires Windows interactive desktop, readable held-input state and usable PyAutoGUI; nothing moved."


def status():
    with _ACTIVE_LOCK:
        return {"state": "active", "operation_id": _ACTIVE["operation_id"]} if _ACTIVE else {"state": "closed" if _CLOSED else "idle"}


def cancel(operation_id):
    with _ACTIVE_LOCK:
        if _ACTIVE and _ACTIVE["operation_id"] == operation_id:
            _ACTIVE["stop"].set()
            return {"state": "cancel_requested", "operation_id": operation_id}
        return {"state": "no_matching_owned_operation"}


def shutdown_motion():
    """No new input; stop at the next owned-operation checkpoint."""
    global _CLOSED
    with _ACTIVE_LOCK:
        _CLOSED = True
        if _ACTIVE:
            _ACTIVE["stop"].set()
            return {"state": "cancel_requested", "operation_id": _ACTIVE["operation_id"]}
        return {"state": "closed"}
