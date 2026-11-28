"""Process lifecycle/approval tests use only fake processes, never host signals."""
from types import SimpleNamespace

import psutil
import pytest

from ultron.actions import process_manager as manager
from ultron.core import confirm
from ultron.core import operation_policy as policy


class FakeProcess:
    def __init__(self, pid, name="editor", created=10.0):
        self.pid = pid
        self.label = name
        self.created = created
        self.info = {"pid": pid, "name": name}
        self.signals = 0
        self.wait_error = None

    def name(self):
        return self.label

    def create_time(self):
        return self.created

    def terminate(self):
        self.signals += 1

    def kill(self):
        pytest.fail("force kill must never be called")

    def wait(self, timeout):
        assert 0 <= timeout <= 3
        if self.wait_error:
            raise self.wait_error
        return 0


@pytest.fixture
def processes(monkeypatch):
    table = {42: FakeProcess(42)}
    monkeypatch.setattr(manager, "_protected_pids", lambda: {0, 1, 999})
    monkeypatch.setattr(manager.psutil, "Process", lambda pid: table[pid])
    monkeypatch.setattr(manager.psutil, "process_iter", lambda *a: iter(table.values()))
    monkeypatch.setattr(manager, "_OS", "Linux")
    for field in ("_pending", "_show_cb", "_hide_cb", "_show_with_id_cb", "_hide_with_id_cb", "_log_cb"):
        monkeypatch.setattr(confirm, field, None)
    return table


def capture_request(monkeypatch):
    captured = {}
    monkeypatch.setattr(confirm, "request", lambda **kw: captured.update(kw) or "pending")
    return captured


def test_headless_process_termination_refuses(processes):
    assert "have not done it" in manager.kill_process(42)
    assert processes[42].signals == 0


def test_exact_process_snapshot_is_single_use(processes, monkeypatch):
    captured = capture_request(monkeypatch)
    assert manager.kill_process("editor") == "pending"
    assert processes[42].signals == 0
    assert '"pid": 42' in captured["detail"]
    assert "exit observed" in captured["run"]()
    assert "REJECTED" in captured["run"]()
    assert processes[42].signals == 1


def test_pid_reuse_aborts_before_signal(processes, monkeypatch):
    captured = capture_request(monkeypatch)
    manager.kill_process(42)
    processes[42] = FakeProcess(42, created=20.0)
    assert "snapshot changed" in captured["run"]()
    assert processes[42].signals == 0


def test_no_substring_kill(processes, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: pytest.fail("unexpected approval"))
    assert "No exact" in manager.kill_process("edit")


def test_no_automatic_force_kill(processes, monkeypatch):
    captured = capture_request(monkeypatch)
    processes[42].wait_error = psutil.TimeoutExpired(3, pid=42)
    manager.kill_process(42)
    assert "No force-kill" in captured["run"]()
    assert processes[42].signals == 1


def test_cancellation_prevents_effect(processes, monkeypatch):
    captured = capture_request(monkeypatch)
    manager.kill_process(42)
    captured["on_cancel"]("cancelled")
    assert "REJECTED" in captured["run"]()
    assert not processes[42].signals


def test_batch_revalidates_before_any_signal(processes, monkeypatch):
    captured = capture_request(monkeypatch)
    processes[43] = FakeProcess(43)
    manager.kill_process("editor")
    processes[43].created += 1
    assert "nothing terminated" in captured["run"]()
    assert not any(p.signals for p in processes.values())


def test_new_name_match_not_added_after_approval(processes, monkeypatch):
    captured = capture_request(monkeypatch)
    manager.kill_process("editor")
    processes[43] = FakeProcess(43)
    captured["run"]()
    assert processes[42].signals == 1 and processes[43].signals == 0


def test_effect_sink_requires_matching_grant(processes):
    plan = policy.prepare("process.terminate", ("pid:42",), {"targets": [manager._process_identity(42)]})
    with pytest.raises(PermissionError):
        manager._terminate_plan(plan)
    assert not processes[42].signals


@pytest.mark.parametrize("target", [0, 1, 999, True, {}, "", "x\ncmd", "a" * 201])
def test_protected_or_invalid_targets_refused(processes, monkeypatch, target):
    monkeypatch.setattr(confirm, "request", lambda **kw: pytest.fail("unexpected approval"))
    result = manager.kill_process(target)
    assert "Refused" in result or "Invalid" in result


def test_batch_bound(processes):
    for pid in range(50, 71):
        processes[pid] = FakeProcess(pid)
    assert "Too many" in manager.kill_process("editor")


def test_access_denied_not_reported_as_exit(processes, monkeypatch):
    captured = capture_request(monkeypatch)
    def denied():
        raise psutil.AccessDenied(42)
    processes[42].terminate = denied
    manager.kill_process(42)
    assert "access denied" in captured["run"]()


def test_focus_query_is_data_not_powershell(monkeypatch):
    monkeypatch.setattr(manager, "_OS", "Windows")
    calls = []
    def run(*a, **kw):
        calls.append((a, kw))
        return SimpleNamespace(returncode=0, stdout="FOCUSED\n")
    monkeypatch.setattr(manager.subprocess, "run", run)
    malicious = "'; Write-Output BAD; #"
    assert "accepted" in manager.focus_window_by_name(malicious)
    script = calls[0][0][0][-1]
    assert malicious not in script
    assert "$env:ULTRON_FOCUS_QUERY" in script
    assert calls[0][1]["env"]["ULTRON_FOCUS_QUERY"] == malicious
    assert calls[0][1]["timeout"] == 5


def test_focus_nonzero_exit_not_success(monkeypatch):
    monkeypatch.setattr(manager, "_OS", "Windows")
    monkeypatch.setattr(manager.subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=1, stdout="FOCUSED"))
    assert "accepted" not in manager.focus_window_by_name("editor")
