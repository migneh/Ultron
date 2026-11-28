"""Android consent/transport tests use fake ADB only; no device commands run."""
import pytest

from ultron.actions import android_bridge as android
from ultron.core import confirm
from ultron.core import operation_policy as policy


@pytest.fixture
def adb(tmp_path, monkeypatch):
    binary = tmp_path / "adb"
    binary.write_bytes(b"fake executable; never executed")
    monkeypatch.setattr(android, "_find_binary", lambda name: str(binary))
    state = {"transport": "7", "status": "device", "effects": [], "exit": 0}
    def run(cmd, timeout=30):
        if cmd[-2:] == ["devices", "-l"]:
            return 0, f"List of devices attached\nSERIAL {state['status']} product:fixture transport_id:{state['transport']}\nOTHER device transport_id:9", ""
        state["effects"].append((cmd, timeout))
        return state["exit"], "untrusted device output", "private error"
    monkeypatch.setattr(android, "_run_cmd", run)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    state["binary"] = binary
    return state


def capture(monkeypatch):
    seen = {}
    monkeypatch.setattr(confirm, "request", lambda **kw: seen.update(kw) or "pending")
    return seen


def test_shell_headless_has_no_effect(adb):
    assert "have not done it" in android.run_shell("getprop", "SERIAL")
    assert not adb["effects"]


def test_exact_serial_transport_and_command_approved_once(adb, monkeypatch):
    seen = capture(monkeypatch)
    command = "echo " + "x" * 900 + "; input keyevent 26"
    assert android.run_shell(command, "SERIAL") == "pending"
    assert not adb["effects"]
    assert command in seen["detail"] and "SERIAL" in seen["detail"]
    assert "exit code 0" in seen["run"]()
    assert "REJECTED" in seen["run"]()
    assert len(adb["effects"]) == 1
    cmd, timeout = adb["effects"][0]
    assert cmd == [str(adb["binary"]), "-H", "127.0.0.1", "-P", "5037", "-t", "7", "shell", command]
    assert timeout == 30


def test_reconnected_transport_needs_new_consent(adb, monkeypatch):
    seen = capture(monkeypatch)
    android.run_shell("getprop", "SERIAL")
    adb["transport"] = "8"
    assert "changed" in seen["run"]()
    assert not adb["effects"]


def test_executable_change_invalidates_approval(adb, monkeypatch):
    seen = capture(monkeypatch)
    android.run_shell("getprop", "SERIAL")
    adb["binary"].write_bytes(b"different binary")
    assert "changed" in seen["run"]()
    assert not adb["effects"]


@pytest.mark.parametrize("status", ["offline", "unauthorized", "recovery"])
def test_non_authorized_transport_not_approved(adb, monkeypatch, status):
    monkeypatch.setattr(confirm, "request", lambda **kw: pytest.fail("approval offered"))
    adb["status"] = status
    assert "preview unavailable" in android.run_shell("getprop", "SERIAL")
    assert not adb["effects"]


@pytest.mark.parametrize("serial", ["", "MISSING", "-SERIAL", "SERIAL\nOTHER", {}, True])
def test_explicit_valid_serial_required(adb, serial):
    assert "preview unavailable" in android.run_shell("getprop", serial)
    assert not adb["effects"]


def test_cancelled_shell_cannot_execute(adb, monkeypatch):
    seen = capture(monkeypatch)
    android.run_shell("getprop", "SERIAL")
    seen["on_cancel"]("cancelled")
    assert "REJECTED" in seen["run"]()
    assert not adb["effects"]


def test_effect_sink_requires_grant(adb):
    plan = policy.prepare("android.shell", ("android:SERIAL",), {})
    with pytest.raises(PermissionError):
        android._execute_device_plan(plan)
    assert not adb["effects"]


@pytest.mark.parametrize("target", ["system", "recovery", "bootloader", "fastboot"])
def test_reboot_is_transport_pinned_and_not_verified(adb, monkeypatch, target):
    seen = capture(monkeypatch)
    assert android.android_bridge({"action": "reboot", "target": target, "serial": "SERIAL"}) == "pending"
    assert not adb["effects"]
    assert "actual boot state not verified" in seen["run"]()
    tail = ["reboot"] + ([] if target == "system" else [target])
    assert adb["effects"][0][0][-len(tail):] == tail


@pytest.mark.parametrize("target", ["edl", "sideload", "unknown"])
def test_unsupported_dangerous_reboot_targets_do_not_probe(adb, monkeypatch, target):
    monkeypatch.setattr(android, "_adb_snapshot", lambda *a: pytest.fail("device probed"))
    assert "Unsupported" in android.reboot_device(target, "SERIAL")
    assert not adb["effects"]


def test_flash_is_fail_closed_even_direct_helper(adb, monkeypatch):
    monkeypatch.setattr(android, "_find_binary", lambda *a: pytest.fail("binary lookup"))
    assert "disabled" in android.flash_partition("boot", "/private/image.img", "SERIAL")
    assert "disabled" in android.android_bridge({"action": "flash", "partition": "boot", "file_path": "/private/image.img"})
    assert not adb["effects"]


def test_command_failure_is_uncertain_and_not_retried(adb, monkeypatch):
    seen = capture(monkeypatch)
    android.run_shell("anything", "SERIAL")
    adb["exit"] = -1
    text = seen["run"]()
    assert "uncertain" in text and "private error" not in text
    assert len(adb["effects"]) == 1


@pytest.mark.parametrize("command", ["", "x" * 4001, "a\x00b", []])
def test_invalid_shell_command_no_probe(adb, monkeypatch, command):
    monkeypatch.setattr(android, "_adb_snapshot", lambda *a: pytest.fail("device probed"))
    assert "Invalid Android command" in android.run_shell(command, "SERIAL")
    assert not adb["effects"]
