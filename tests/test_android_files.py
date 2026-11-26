"""Android file effects: isolated files, fake ADB, plus bounded local pipe tests."""
import hashlib
import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from ultron.actions import android_bridge as android
from ultron.core import android_files as files
from ultron.core import confirm
from ultron.core import operation_policy as policy
from ultron.core import productivity_store as store


@pytest.fixture
def transfer(tmp_path, monkeypatch):
    root = tmp_path / "approved"
    root.mkdir()
    monkeypatch.setattr(store, "database_path", lambda: tmp_path / "data.sqlite3")
    store.set_setting("document_roots", [str(root)])
    source = root / "fixture.apk"
    source.write_bytes(b"approved source bytes")
    device = {"serial": "SERIAL", "transport_id": "7", "binary": "/fake/adb", "binary_identity": ["fixture"]}
    monkeypatch.setattr(android, "_adb_snapshot", lambda serial: dict(device) if serial == "SERIAL" else (_ for _ in ()).throw(ValueError("device")))
    state = SimpleNamespace(root=root, source=source, device=device, effects=[], captured={}, remote=b"remote bytes", code=0, mkdir_code=0, install_output="Success", staged=None)
    def run(cmd, timeout=30):
        if "shell" in cmd:
            shell = cmd[-1]
            if shell.startswith("stat "):
                return 0, f"regular file:{len(state.remote)}", ""
            if shell.startswith("sha256sum "):
                content = state.remote if "ultron-" not in shell else source.read_bytes()
                return 0, hashlib.sha256(content).hexdigest() + "  path", ""
            state.effects.append(cmd)
            return state.mkdir_code, "", ""
        state.effects.append(cmd)
        staged = cmd[-1] if "install" in cmd else cmd[-2]
        state.staged = Path(staged)
        assert state.staged.read_bytes() == b"approved source bytes"
        assert state.staged != source
        return state.code, state.install_output if "install" in cmd else "", ""
    monkeypatch.setattr(android, "_run_cmd", run)
    def receive(cmd, output, expected_size):
        state.effects.append(cmd)
        assert expected_size == len(state.remote)
        output.write(state.remote)
        return hashlib.sha256(state.remote).hexdigest()
    monkeypatch.setattr(files, "_receive", receive)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    return state


def capture(state, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: state.captured.update(kw) or "pending")
    return state.captured


@pytest.mark.parametrize("action", ["push", "pull", "install"])
def test_headless_no_transfer_or_local_creation(transfer, action):
    target = transfer.root / "new.bin"
    result = files.request(action, "SERIAL", local_path=str(target if action == "pull" else transfer.source), phone_path="/sdcard/Download/input.bin" if action == "pull" else "/sdcard/Download/")
    assert "have not done it" in result
    assert not transfer.effects and not target.exists()
    assert sorted(p.name for p in transfer.root.iterdir()) == ["fixture.apk"]


def test_push_uses_private_snapshot_new_remote_dir_and_one_shot(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    assert android.push_file(str(transfer.source), serial="SERIAL") == "pending"
    assert not transfer.effects and "remote_directory" in seen["detail"]
    assert hashlib.sha256(transfer.source.read_bytes()).hexdigest() in seen["detail"]
    assert "readback matched" in seen["run"]()
    assert "REJECTED" in seen["run"]()
    assert len(transfer.effects) == 2
    assert "mkdir -- /sdcard/Download/ultron-" in transfer.effects[0][-1]
    assert transfer.effects[1][-1].endswith("/fixture.apk")
    assert transfer.effects[1][1:7] == ["-H", "127.0.0.1", "-P", "5037", "-t", "7"]
    assert not transfer.staged.exists()


@pytest.mark.parametrize("replace", [False, True])
def test_install_replacement_is_explicit(transfer, monkeypatch, replace):
    seen = capture(transfer, monkeypatch)
    assert android.install_apk(str(transfer.source), "SERIAL", replace) == "pending"
    assert f'"replace_existing": {str(replace).lower()}' in seen["detail"]
    assert "ADB reported" in seen["run"]()
    cmd = transfer.effects[0]
    assert ("-r" in cmd) is replace
    assert not transfer.staged.exists()


@pytest.mark.parametrize("action", ["push", "install"])
def test_source_change_stops_before_any_device_effect(transfer, monkeypatch, action):
    seen = capture(transfer, monkeypatch)
    files.request(action, "SERIAL", local_path=str(transfer.source))
    transfer.source.write_bytes(b"changed")
    assert "OUTCOME_UNKNOWN" in seen["run"]()
    assert not transfer.effects


def test_revoked_root_stops_transfer(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    android.push_file(str(transfer.source), serial="SERIAL")
    store.set_setting("document_roots", [])
    seen["run"]()
    assert not transfer.effects


def test_changed_transport_stops_transfer(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    android.install_apk(str(transfer.source), "SERIAL")
    transfer.device["transport_id"] = "8"
    assert "changed" in seen["run"]()
    assert not transfer.effects


def test_remote_mkdir_conflict_never_pushes(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    transfer.mkdir_code = 1
    android.push_file(str(transfer.source), serial="SERIAL")
    assert "no file pushed" in seen["run"]()
    assert len(transfer.effects) == 1


def test_install_failure_never_retried(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    transfer.install_output = "Failure [INSTALL_FAILED_ALREADY_EXISTS]"
    android.install_apk(str(transfer.source), "SERIAL")
    assert "uncertain" in seen["run"]()
    seen["run"]()
    assert len(transfer.effects) == 1


def test_pull_publishes_checked_new_file_and_cleans_temp(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    target = transfer.root / "received.bin"
    assert android.pull_file("/sdcard/Download/input.bin", str(target), "SERIAL") == "pending"
    assert not target.exists()
    assert "published without overwrite" in seen["run"]()
    assert target.read_bytes() == transfer.remote
    assert not list(transfer.root.glob("*.part"))
    assert len(transfer.effects) == 1


def test_pull_existing_target_is_never_replaced(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    target = transfer.root / "received.bin"
    android.pull_file("/sdcard/Download/input.bin", str(target), "SERIAL")
    target.write_bytes(b"do not overwrite")
    assert "conflict" in seen["run"]()
    assert target.read_bytes() == b"do not overwrite" and not transfer.effects


def test_remote_change_invalidates_pull(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    target = transfer.root / "received.bin"
    android.pull_file("/sdcard/Download/input.bin", str(target), "SERIAL")
    transfer.remote = b"changed"
    assert "changed" in seen["run"]()
    assert not target.exists() and not transfer.effects


def test_bad_received_checksum_not_published(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    target = transfer.root / "received.bin"
    android.pull_file("/sdcard/Download/input.bin", str(target), "SERIAL")
    monkeypatch.setattr(files, "_receive", lambda *a: "0" * 64)
    assert "not published" in seen["run"]()
    assert not target.exists() and not list(transfer.root.glob("*.part"))


def test_receive_exception_cleans_partial_file(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    target = transfer.root / "received.bin"
    android.pull_file("/sdcard/Download/input.bin", str(target), "SERIAL")
    def fail(cmd, output, expected):
        output.write(b"partial")
        raise ValueError("timeout")
    monkeypatch.setattr(files, "_receive", fail)
    assert "OUTCOME_UNKNOWN" in seen["run"]()
    assert not target.exists() and not list(transfer.root.glob("*.part"))


@pytest.mark.parametrize("path", ["/data/private", "/sdcard/Download/../x", "/sdcard/Download/a;id", "/sdcard/Download/a b", "/sdcard/Download/", "/sdcard/Download/-option", "/sdcard/Download/a//b"])
def test_remote_paths_reject_shell_syntax_and_traversal(path):
    with pytest.raises(ValueError):
        files._remote_path(path)


def test_effect_sink_requires_grant(transfer):
    plan = policy.prepare("android.file.install", ("android:SERIAL",), {})
    with pytest.raises(PermissionError):
        files._execute(plan)


def test_symlink_local_source_refused(transfer, monkeypatch):
    capture(transfer, monkeypatch)
    link = transfer.root / "link.apk"
    link.symlink_to(transfer.source)
    assert "preview unavailable" in android.install_apk(str(link), "SERIAL")
    assert not transfer.effects and not transfer.captured


@pytest.mark.parametrize("replace", ["true", 1, None])
def test_replacement_flag_must_be_boolean(transfer, replace):
    assert "preview unavailable" in android.install_apk(str(transfer.source), "SERIAL", replace)
    assert not transfer.effects


def test_bounded_receiver_success():
    # Trusted test fixture subprocess, never ADB or generated application code.
    output = io.BytesIO()
    checksum = files._receive([sys.executable, "-c", "import sys;sys.stdout.buffer.write(b'abc')"], output, 3, timeout=2)
    assert output.getvalue() == b"abc" and checksum == hashlib.sha256(b"abc").hexdigest()


@pytest.mark.parametrize("script,size", [("import sys;sys.stdout.buffer.write(b'x'*1000)", 10), ("print('short')", 50), ("raise SystemExit(1)", 0)])
def test_bounded_receiver_refuses_overflow_truncation_and_nonzero(script, size):
    output = io.BytesIO()
    with pytest.raises(ValueError):
        files._receive([sys.executable, "-c", script], output, size, timeout=2)
    assert len(output.getvalue()) <= size


def test_bounded_receiver_deadline():
    start = time.monotonic()
    with pytest.raises(ValueError, match="deadline"):
        files._receive([sys.executable, "-c", "import time;time.sleep(20)"], io.BytesIO(), 1, timeout=.1)
    assert time.monotonic() - start < 4


def test_pull_publication_race_does_not_overwrite(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    target = transfer.root / "race.bin"
    android.pull_file("/sdcard/Download/input.bin", str(target), "SERIAL")
    real_link = files.os.link
    def race(source, dest):
        target.write_bytes(b"created by another writer")
        return real_link(source, dest)
    monkeypatch.setattr(files.os, "link", race)
    assert "OUTCOME_UNKNOWN" in seen["run"]()
    assert target.read_bytes() == b"created by another writer"
    assert not list(transfer.root.glob("*.part"))


def test_cancelled_file_plan_has_no_effect(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    android.install_apk(str(transfer.source), "SERIAL")
    seen["on_cancel"]("cancelled")
    assert "REJECTED" in seen["run"]()
    assert not transfer.effects


def test_source_stage_failure_never_sends_device_mutation(transfer, monkeypatch):
    seen = capture(transfer, monkeypatch)
    android.install_apk(str(transfer.source), "SERIAL")
    def fail(*a):
        raise ValueError("source changed during copy")
    monkeypatch.setattr(files, "_stage_source", fail)
    assert "OUTCOME_UNKNOWN" in seen["run"]()
    assert not transfer.effects


def test_push_arbitrary_remote_destination_refused(transfer, monkeypatch):
    capture(transfer, monkeypatch)
    assert "preview unavailable" in android.push_file(str(transfer.source), "/data/local/tmp/", "SERIAL")
    assert not transfer.effects and not transfer.captured


def test_remote_directory_and_oversize_sources_refused(transfer, monkeypatch):
    monkeypatch.setattr(android, "_run_cmd", lambda *a, **kw: (0, f"regular file:{files.MAX_BYTES + 1}", ""))
    assert "preview unavailable" in android.pull_file("/sdcard/Download/a.bin", str(transfer.root / "new.bin"), "SERIAL")
    monkeypatch.setattr(android, "_run_cmd", lambda *a, **kw: (0, "directory:4096", ""))
    assert "preview unavailable" in android.pull_file("/sdcard/Download/a.bin", str(transfer.root / "new.bin"), "SERIAL")


def test_empty_receive_supported():
    output = io.BytesIO()
    result = files._receive([sys.executable, "-c", "pass"], output, 0, timeout=2)
    assert result == hashlib.sha256(b"").hexdigest()
