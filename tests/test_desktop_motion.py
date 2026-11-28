"""Fake pointer backend only: no mouse, keyboard, app, screenshots or GUI session."""
import json
from types import SimpleNamespace

import pytest

from ultron.actions import ghost_pilot as ghost
from ultron.core import confirm
from ultron.core import desktop_motion as motion
from ultron.core import operation_policy as policy


@pytest.fixture
def pointer(tmp_path, monkeypatch):
    state = SimpleNamespace(held=False, owner_ok=True, released=0, seen={}, after_move=None)
    class Backend:
        FAILSAFE = True
        size_value = (800, 600)
        current = (100, 100)
        calls = None
        def size(self):
            return self.size_value
        def position(self):
            return self.current
        def moveTo(self, x, y, **kw):
            assert kw == {"duration": 0, "_pause": False}
            self.current = (x, y)
            self.calls.append((x, y))
            if state.after_move:
                state.after_move()
    state.backend = Backend()
    state.backend.calls = []
    monkeypatch.setattr(motion, "_backend", lambda: state.backend)
    monkeypatch.setattr(motion, "_held_input", lambda: state.held)
    monkeypatch.setattr(motion.Path, "home", lambda: tmp_path)
    class Owner:
        def __init__(self, path):
            pass
        def acquire(self):
            return state.owner_ok
        def release(self):
            state.released += 1
    monkeypatch.setattr(motion, "OwnerLock", Owner)
    class Event:
        stopped = False
        def is_set(self):
            return self.stopped
        def set(self):
            self.stopped = True
        def wait(self, timeout):
            assert 0 < timeout <= .15
            return self.stopped
    monkeypatch.setattr(motion.threading, "Event", Event)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    monkeypatch.setattr(motion, "_CLOSED", False)
    assert motion.status()["state"] == "idle"
    return state


def preview(pointer, monkeypatch, **options):
    monkeypatch.setattr(confirm, "request", lambda **kw: pointer.seen.update(kw) or "pending")
    return motion.request("move", x=400, y=300, **options)


def test_headless_no_motion(pointer):
    assert "have not done it" in ghost.human_glide_to(400, 300)
    assert not pointer.backend.calls


def test_approved_motion_exact_target_bounded_steps_and_no_replay(pointer, monkeypatch):
    assert preview(pointer, monkeypatch) == "pending"
    assert not pointer.backend.calls
    assert '"target": [400, 300]' in pointer.seen["detail"]
    assert "target observed" in pointer.seen["run"]()
    assert len(pointer.backend.calls) == 20 and pointer.backend.current == (400, 300)
    assert "REJECTED" in pointer.seen["run"]()
    assert motion.status()["state"] == "idle" and pointer.released == 1


def test_deny_no_motion(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    pointer.seen["on_cancel"]("cancelled")
    assert "REJECTED" in pointer.seen["run"]() and not pointer.backend.calls


def test_display_change_before_execute_no_motion(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    pointer.backend.size_value = (1024, 768)
    assert "geometry changed" in pointer.seen["run"]()
    assert not pointer.backend.calls


def test_held_button_at_preview_is_refused(pointer, monkeypatch):
    pointer.held = True
    assert "preview unavailable" in preview(pointer, monkeypatch)
    assert not pointer.backend.calls and not pointer.seen


def test_button_held_after_approval_no_motion(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    pointer.held = True
    assert "OUTCOME_UNKNOWN" in pointer.seen["run"]()
    assert not pointer.backend.calls


def test_user_cursor_intervention_stops_no_retry(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    pointer.after_move = lambda: setattr(pointer.backend, "current", (50, 50))
    assert "changed externally" in pointer.seen["run"]()
    assert len(pointer.backend.calls) == 1


def test_button_pressed_mid_operation_interrupts(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    pointer.after_move = lambda: setattr(pointer, "held", True)
    assert "interrupted after 1" in pointer.seen["run"]()
    assert len(pointer.backend.calls) == 1


def test_failsafe_disabled_mid_operation_stops(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    pointer.after_move = lambda: setattr(pointer.backend, "FAILSAFE", False)
    assert "interrupted after 1" in pointer.seen["run"]()


def test_exact_owned_cancel_stops(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    ids = []
    def cancel():
        operation_id = motion.status()["operation_id"]
        ids.append(operation_id)
        assert motion.cancel("wrong")["state"] == "no_matching_owned_operation"
        assert motion.cancel(operation_id)["state"] == "cancel_requested"
    pointer.after_move = cancel
    assert "cancelled after 1" in pointer.seen["run"]()
    assert motion.cancel(ids[0])["state"] == "no_matching_owned_operation"


def test_native_error_does_not_leak_or_retry(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    def fail(*a, **kw):
        raise RuntimeError("private native error")
    monkeypatch.setattr(pointer.backend, "moveTo", fail)
    result = pointer.seen["run"]()
    assert "interrupted" in result and "private" not in result and pointer.released == 1


def test_other_runtime_owner_refuses_effect(pointer, monkeypatch):
    pointer.owner_ok = False
    preview(pointer, monkeypatch)
    assert "Another runtime" in pointer.seen["run"]() and not pointer.backend.calls


def test_busy_inprocess_lock_refuses(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    motion._ADMISSION.acquire()
    try:
        assert "Another owned" in pointer.seen["run"]()
    finally:
        motion._ADMISSION.release()
    assert not pointer.backend.calls


@pytest.mark.parametrize("seconds", [0, -1, 4, float("nan"), float("inf"), True, "1", 10 ** 500])
def test_invalid_duration_no_metadata_or_input(pointer, monkeypatch, seconds):
    monkeypatch.setattr(motion, "_backend", lambda: pytest.fail("backend queried"))
    assert "finite duration" in motion.request("move", x=1, y=2, seconds=seconds)


@pytest.mark.parametrize("x,y", [(0, 20), (799, 20), (-1, 20), (30, 599), (True, 20), (1.5, 20), (None, None)])
def test_invalid_target_no_approval_or_motion(pointer, monkeypatch, x, y):
    monkeypatch.setattr(confirm, "request", lambda **kw: pytest.fail("approval offered"))
    assert "explicit integer" in motion.request("move", x=x, y=y)
    assert not pointer.backend.calls


def test_direct_sink_no_grant_no_input(pointer):
    plan = policy.prepare("desktop.pointer_only", ("interactive_primary_display",), {})
    with pytest.raises(PermissionError):
        motion._execute(plan)
    assert not pointer.backend.calls


@pytest.mark.parametrize("action", ["search", "browse", "write", "note", "type", "human_type"])
def test_blind_workflows_fail_closed_before_backend(pointer, monkeypatch, action):
    monkeypatch.setattr(motion, "_backend", lambda: pytest.fail("backend queried"))
    assert "disabled" in ghost.ghost_pilot_handler({"action": action, "query": "dangerous command\n"})
    assert not pointer.backend.calls


def test_direct_legacy_typing_and_workflow_helpers_fail_closed(pointer):
    assert "disabled" in ghost.human_type("anything\n")
    assert "disabled" in ghost.ghost_search("anything")
    assert "disabled" in ghost.ghost_write_note("terminal", "anything")
    assert not pointer.backend.calls


def test_demo_uses_bounded_approved_primary_display_points(pointer, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: pointer.seen.update(kw) or "pending")
    assert ghost.ghost_demonstration() == "pending"
    assert "target observed" in pointer.seen["run"]()
    assert len(pointer.backend.calls) == 25
    assert all(0 < x < 799 and 0 < y < 599 for x, y in pointer.backend.calls)


def test_deadline_checkpoint_prevents_first_move(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    clock = iter([0, 10])
    monkeypatch.setattr(motion, "_clock", lambda: next(clock))
    assert "stopped after 0" in pointer.seen["run"]()
    assert not pointer.backend.calls


def test_unsupported_platform_no_pyautogui_import(monkeypatch):
    monkeypatch.setattr(motion.platform, "system", lambda: "Linux")
    assert "preview unavailable" in motion.request("move", x=10, y=10)


def test_status_cancel_dispatch_never_moves(pointer):
    assert json.loads(ghost.ghost_pilot_handler({"action": "status"}))["state"] == "idle"
    assert json.loads(ghost.ghost_pilot_handler({"action": "cancel", "operation_id": "missing"}))["state"] == "no_matching_owned_operation"
    assert not pointer.backend.calls


def test_shutdown_blocks_late_approved_motion(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    assert motion.shutdown_motion()["state"] == "closed"
    assert "shut down" in pointer.seen["run"]()
    assert not pointer.backend.calls


def test_shutdown_cancels_active_motion_at_checkpoint(pointer, monkeypatch):
    preview(pointer, monkeypatch)
    pointer.after_move = motion.shutdown_motion
    assert "cancelled after 1" in pointer.seen["run"]()
    assert motion.status()["state"] == "closed"
    assert len(pointer.backend.calls) == 1


def fake_windows_api(monkeypatch, *, held=False, mismatch=False, available=True):
    closed = []
    class Function:
        def __init__(self, callback):
            self.callback = callback
        def __call__(self, *args):
            return self.callback(*args)
    def desktop_name(handle, index, buffer, size, needed):
        buffer.value = "Other" if mismatch and handle == 2 else "Default"
        return 1
    user = SimpleNamespace(
        OpenInputDesktop=Function(lambda *a: 1 if available else 0),
        CloseDesktop=Function(lambda handle: closed.append(handle)),
        GetThreadDesktop=Function(lambda *a: 2),
        GetUserObjectInformationW=Function(desktop_name),
        GetAsyncKeyState=Function(lambda key: -32768 if held and key == 1 else 0),
    )
    kernel = SimpleNamespace(GetCurrentThreadId=Function(lambda: 10))
    monkeypatch.setattr(motion.ctypes, "WinDLL", lambda name, **kw: user if name == "user32" else kernel, raising=False)
    return closed


def test_native_guard_held_input_and_handle_cleanup(monkeypatch):
    closed = fake_windows_api(monkeypatch, held=True)
    assert motion._held_input() is True
    assert closed == [1]


def test_native_guard_idle_and_handle_cleanup(monkeypatch):
    closed = fake_windows_api(monkeypatch)
    assert motion._held_input() is False
    assert closed == [1]


def test_native_guard_wrong_desktop_fails_closed(monkeypatch):
    closed = fake_windows_api(monkeypatch, mismatch=True)
    with pytest.raises(ValueError, match="desktop changed"):
        motion._held_input()
    assert closed == [1]


def test_native_guard_unreadable_desktop_fails_closed(monkeypatch):
    closed = fake_windows_api(monkeypatch, available=False)
    with pytest.raises(ValueError, match="unavailable"):
        motion._held_input()
    assert not closed
