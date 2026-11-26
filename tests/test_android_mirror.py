"""Owned mirror lifecycle without scrcpy, ADB, native windows or real processes."""
import json
import subprocess
import threading
from types import SimpleNamespace

import pytest

from ultron.actions import android_bridge as android
from ultron.core import android_mirror as mirror
from ultron.core import confirm
from ultron.core import operation_policy as policy

REAL_THREAD = threading.Thread


class FakeProcess:
    def __init__(self):
        self.alive = True
        self.stubborn = False
        self.terminations = 0
        self.kills = 0

    def poll(self):
        return None if self.alive else 0

    def wait(self, timeout):
        assert timeout <= 300
        if self.alive:
            raise subprocess.TimeoutExpired("fake", timeout)
        return 0

    def terminate(self):
        self.terminations += 1
        if not self.stubborn:
            self.alive = False

    def kill(self):
        self.kills += 1
        if not self.stubborn:
            self.alive = False


@pytest.fixture
def session(tmp_path, monkeypatch):
    scrcpy = tmp_path / "scrcpy"
    scrcpy.write_bytes(b"fake scrcpy executable; not run")
    monkeypatch.setattr(mirror.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(android, "_find_binary", lambda name: str(scrcpy))
    device = {"serial": "SERIAL", "transport_id": "7", "binary": "/fake/adb", "binary_identity": ["identity"]}
    monkeypatch.setattr(android, "_adb_snapshot", lambda serial: dict(device) if serial == "SERIAL" else (_ for _ in ()).throw(ValueError("serial")))
    state = SimpleNamespace(service=mirror.MirrorService(), owner_ok=True, releases=0, spawns=[], watchers=[],
                            seen={}, process=FakeProcess(), device=device, scrcpy=scrcpy, thread_failure=False)
    monkeypatch.setattr(mirror, "_SERVICE", state.service)
    monkeypatch.setattr(mirror, "_SHUTDOWN", False)
    class Owner:
        def __init__(self, path):
            pass
        def acquire(self):
            return state.owner_ok
        def release(self):
            state.releases += 1
    monkeypatch.setattr(mirror, "OwnerLock", Owner)
    def popen(*a, **kw):
        state.spawns.append((a, kw))
        return state.process
    monkeypatch.setattr(mirror.subprocess, "Popen", popen)
    class Thread:
        def __init__(self, target, args, **kwargs):
            self.target, self.args = target, args
        def start(self):
            if state.thread_failure:
                raise RuntimeError("thread failed")
            state.watchers.append(lambda: self.target(*self.args))
    monkeypatch.setattr(mirror.threading, "Thread", Thread)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    return state


def preview(state, monkeypatch, seconds=60):
    monkeypatch.setattr(confirm, "request", lambda **kw: state.seen.update(kw) or "pending")
    assert android.mirror_screen("SERIAL", seconds) == "pending"
    return state.seen


def launch(state, monkeypatch):
    preview(state, monkeypatch)
    return json.loads(state.seen["run"]())


def test_headless_mirror_cannot_spawn(session):
    assert "have not done it" in android.mirror_screen("SERIAL")
    assert not session.spawns


def test_exact_consent_and_view_only_flags(session, monkeypatch):
    result = launch(session, monkeypatch)
    assert "display_not_verified" in result["state"]
    assert "REJECTED" in session.seen["run"]()
    assert len(session.spawns) == 1
    command = session.spawns[0][0][0]
    for flag in ("--serial=SERIAL", "--no-control", "--no-audio", "--no-clipboard-autosync", "--no-power-on", "--time-limit=60"):
        assert flag in command
    assert not any(arg.startswith("--record") for arg in command)
    environment = session.spawns[0][1]["env"]
    assert environment["ADB"] == "/fake/adb" and environment["ADB_SERVER_SOCKET"] == "tcp:127.0.0.1:5037"
    assert session.spawns[0][1]["stdout"] == subprocess.DEVNULL
    assert result["mirror_id"] == json.loads(mirror.status())["mirror_id"]


def test_cancel_before_launch(session, monkeypatch):
    preview(session, monkeypatch)
    session.seen["on_cancel"]("cancelled")
    assert "REJECTED" in session.seen["run"]() and not session.spawns


@pytest.mark.parametrize("changed", ["transport", "binary"])
def test_preview_identity_changes_block_launch(session, monkeypatch, changed):
    preview(session, monkeypatch)
    if changed == "transport":
        session.device["transport_id"] = "8"
    else:
        session.scrcpy.write_bytes(b"changed executable")
    assert "changed" in session.seen["run"]()
    assert not session.spawns


def test_busy_does_not_launch_another_process(session, monkeypatch):
    launch(session, monkeypatch)
    result = launch(session, monkeypatch)
    assert result["started"] is False and len(session.spawns) == 1


def test_other_runtime_lock_refuses_launch(session, monkeypatch):
    session.owner_ok = False
    assert launch(session, monkeypatch)["state"] == "another_runtime_owns_mirror"
    assert not session.spawns


def test_stop_requires_exact_owned_session_id(session, monkeypatch):
    result = launch(session, monkeypatch)
    assert json.loads(mirror.stop("a" * 32))["state"] == "no_matching_owned_session"
    assert json.loads(mirror.stop("123"))["state"] == "invalid_mirror_id"
    assert session.process.terminations == 0
    assert json.loads(mirror.stop(result["mirror_id"]))["state"] == "process_exit_observed"
    assert session.process.terminations == 1 and session.releases == 1


def test_watchdog_stops_owned_process_on_deadline(session, monkeypatch):
    launch(session, monkeypatch)
    session.watchers[0]()
    assert session.process.terminations == 1
    assert session.service.current is None and session.releases == 1


def test_unstoppable_process_retains_owner_and_slot(session, monkeypatch):
    result = launch(session, monkeypatch)
    session.process.stubborn = True
    assert json.loads(mirror.stop(result["mirror_id"]))["state"] == "stop_uncertain_slot_retained"
    assert session.process.kills == 1 and session.releases == 0
    assert launch(session, monkeypatch)["started"] is False
    assert len(session.spawns) == 1
    session.process.alive = False
    assert json.loads(mirror.status())["state"] == "process_exited"
    assert session.releases == 1


def test_native_exit_releases_slot_without_killing(session, monkeypatch):
    launch(session, monkeypatch)
    session.process.alive = False
    session.watchers[0]()
    assert session.process.terminations == 0 and session.releases == 1


def test_launch_failure_releases_owner(session, monkeypatch):
    def fail(*a, **kw):
        raise OSError("native spawn failed")
    monkeypatch.setattr(mirror.subprocess, "Popen", fail)
    assert launch(session, monkeypatch)["state"] == "launch_failed"
    assert session.releases == 1 and session.service.current is None


def test_watchdog_start_failure_stops_process(session, monkeypatch):
    session.thread_failure = True
    assert launch(session, monkeypatch)["state"] == "watchdog_failed_stop_attempted"
    assert not session.process.alive and session.releases == 1


def test_shutdown_stops_and_closes_admission(session, monkeypatch):
    launch(session, monkeypatch)
    assert mirror.shutdown_mirrors()["state"] == "process_exit_observed"
    assert "REJECTED" in session.seen["run"]()
    with pytest.raises(RuntimeError):
        mirror._service()


@pytest.mark.parametrize("seconds", [0, 4, 301, True, "60", None])
def test_duration_is_bounded_before_device_probe(session, monkeypatch, seconds):
    monkeypatch.setattr(android, "_adb_snapshot", lambda *a: pytest.fail("device probed"))
    assert "integer from 5 to 300" in android.mirror_screen("SERIAL", seconds)
    assert not session.spawns


def test_sink_has_no_direct_launch_bypass(session):
    plan = policy.prepare("android.mirror.view_only", ("android:SERIAL",), {})
    with pytest.raises(PermissionError):
        mirror._execute(plan)
    assert not session.spawns


def test_dispatch_status_stop_and_start(session, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: session.seen.update(kw) or "pending")
    assert android.android_bridge({"action": "mirror", "serial": "SERIAL", "seconds": 5}) == "pending"
    result = json.loads(session.seen["run"]())
    assert json.loads(android.android_bridge({"action": "mirror_status"}))["mirror_id"] == result["mirror_id"]
    assert json.loads(android.android_bridge({"action": "mirror_stop", "mirror_id": result["mirror_id"]}))["state"] == "process_exit_observed"


def test_concurrent_launch_admits_one_owned_process(session):
    payload = {"device": session.device, "scrcpy": mirror._scrcpy_snapshot(), "seconds": 60}
    barrier = threading.Barrier(3)
    results = []
    def run():
        barrier.wait()
        results.append(session.service.launch(payload))
    workers = [REAL_THREAD(target=run) for _ in range(2)]
    for worker in workers:
        worker.start()
    barrier.wait()
    for worker in workers:
        worker.join(timeout=2)
        assert not worker.is_alive()
    assert sum(result["started"] for result in results) == 1
    assert len(session.spawns) == 1


def test_idle_shutdown_blocks_late_approved_launch(session, monkeypatch):
    preview(session, monkeypatch)
    monkeypatch.setattr(mirror, "_SERVICE", None)
    assert mirror.shutdown_mirrors()["state"] == "no_owned_session"
    assert "OUTCOME_UNKNOWN" in session.seen["run"]()
    assert not session.spawns


def test_old_session_stop_and_watcher_cannot_stop_new_session(session, monkeypatch):
    first = launch(session, monkeypatch)
    old_watcher = session.watchers[0]
    session.process.alive = False
    mirror.status()  # reap first session
    session.process = FakeProcess()
    second = launch(session, monkeypatch)
    assert first["mirror_id"] != second["mirror_id"]
    old_watcher()
    assert json.loads(mirror.stop(first["mirror_id"]))["state"] == "no_matching_owned_session"
    assert session.process.terminations == 0 and session.process.alive


def test_status_without_session_does_not_create_runtime(session, monkeypatch):
    monkeypatch.setattr(mirror, "_SERVICE", None)
    assert json.loads(mirror.status())["state"] == "no_owned_session"
    assert json.loads(mirror.stop("a" * 32))["state"] == "no_owned_session"
    assert mirror._SERVICE is None and not session.spawns
