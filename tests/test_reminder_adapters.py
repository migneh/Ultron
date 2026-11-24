"""Native adapter contracts only: no real OS jobs or notifications are invoked."""

import plistlib
import subprocess
from datetime import datetime
from pathlib import Path
from xml.etree import ElementTree as ET

import pytest

from core import reminders as rm


@pytest.fixture(autouse=True)
def no_real_processes(monkeypatch):
    monkeypatch.setattr(rm.subprocess, "run", lambda *a, **k: pytest.fail("Unexpected native call"))


@pytest.fixture
def native(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(rm, "_unit_dir", lambda: tmp_path / "units")
    monkeypatch.setattr(rm, "_launch_dir", lambda: tmp_path / "agents")
    monkeypatch.setattr(rm, "_run", lambda args, **kwargs: calls.append(args))
    return tmp_path, calls


def record(system):
    return {
        "id": "a" * 32,
        "platform": system,
        "target_utc": "2035-06-01T12:30:00+00:00",
        "message": "private message",
    }


def test_windows_xml_is_escaped_and_uses_utc_boundary(native, monkeypatch):
    root, calls = native
    database = root / "user & company" / "registry.sqlite3"
    database.parent.mkdir()
    monkeypatch.setattr(rm, "RUNNER", root / "app & suite" / "reminders.py")
    captured = []

    def capture(args, **kwargs):
        calls.append(args)
        if "/XML" in args:
            path = Path(args[args.index("/XML") + 1])
            captured.append(ET.fromstring(path.read_bytes()))

    monkeypatch.setattr(rm, "_run", capture)
    rm.install_job(record("Windows"), database)
    ns = {"s": "http://schemas.microsoft.com/windows/2004/02/mit/task"}
    assert (
        captured[0].find("s:Triggers/s:TimeTrigger/s:StartBoundary", ns).text
        == record("Windows")["target_utc"]
    )
    args = captured[0].find("s:Actions/s:Exec/s:Arguments", ns).text
    assert "app & suite" in args
    assert "private message" not in args
    assert "--database" in args
    assert not list(database.parent.glob("*.xml"))
    rm.remove_job(record("Windows"))
    assert calls[-1] == ["schtasks", "/Delete", "/TN", "UltronReminder_" + "a" * 32, "/F"]


def test_linux_uses_persistent_on_disk_units_and_utc(native):
    root, calls = native
    database = root / "registry.sqlite3"
    rm.install_job(record("Linux"), database)
    name = "UltronReminder_" + "a" * 32
    service = (root / "units" / f"{name}.service").read_text()
    timer = (root / "units" / f"{name}.timer").read_text()
    assert "ExecStart=:" in service
    assert "--database" in service and "--id" in service
    assert "private message" not in service
    assert "OnCalendar=2035-06-01 12:30:00 UTC" in timer
    assert "Persistent=true" in timer
    assert calls[-1] == ["systemctl", "--user", "enable", "--now", f"{name}.timer"]
    rm.remove_job(record("Linux"))
    assert not list((root / "units").iterdir())
    assert ["systemctl", "--user", "disable", "--now", f"{name}.timer"] in calls


def test_systemd_arguments_escape_specifiers_and_disable_env_expansion(native, monkeypatch):
    root, _ = native
    monkeypatch.setattr(rm, "RUNNER", root / 'suite %u $HOME "quoted"' / "reminders.py")
    rm.install_job(record("Linux"), root / "registry.sqlite3")
    service = next((root / "units").glob("*.service")).read_text()
    assert "%%u" in service
    assert '\\"quoted\\"' in service
    assert "ExecStart=:" in service
    with pytest.raises(ValueError, match="control"):
        rm._systemd_arg("bad\npath")


def test_mac_uses_due_polling_not_invalid_year_calendar(native):
    root, calls = native
    rm.install_job(record("Darwin"), root / "registry.sqlite3")
    path = next((root / "agents").glob("*.plist"))
    data = plistlib.loads(path.read_bytes())
    assert data["StartInterval"] == 60
    assert data["RunAtLoad"] is True
    assert "StartCalendarInterval" not in data
    assert "private message" not in data["ProgramArguments"]
    assert calls[-1][0:2] == ["launchctl", "bootstrap"]
    rm.remove_job(record("Darwin"))
    assert not path.exists()
    assert calls[-1][0:2] == ["launchctl", "bootout"]


def test_partial_linux_registration_rolls_back_after_failed_enable(native, monkeypatch):
    root, calls = native
    monkeypatch.setattr(rm.platform, "system", lambda: "Linux")
    monkeypatch.setattr(rm, "_now", lambda: datetime(2035, 1, 1, tzinfo=rm.UTC))

    def capture(args, **kwargs):
        calls.append(args)
        if "enable" in args:
            raise RuntimeError("enable failed")

    monkeypatch.setattr(rm, "_run", capture)
    store = rm.ReminderStore(root / "registry.sqlite3")
    created = rm.create_reminder(store, "2035-06-01", "12:30", "tea", "UTC")
    assert created["state"] == "scheduling_failed"
    assert "enable failed" in created["error"]
    assert not list((root / "units").iterdir())
    assert not store.claim(created["id"])


def test_scheduler_calls_have_timeout_and_no_shell(monkeypatch):
    calls = []

    def capture(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "", "")

    monkeypatch.setattr(rm.subprocess, "run", capture)
    rm._run(["example", "one argument; not shell"])
    assert calls[0][1]["timeout"] == 20
    assert not calls[0][1].get("shell", False)


def test_nonzero_scheduler_exit_is_not_reported_success(monkeypatch):
    monkeypatch.setattr(
        rm.subprocess,
        "run",
        lambda args, **kw: subprocess.CompletedProcess(args, 1, "", "permission denied"),
    )
    with pytest.raises(RuntimeError, match="permission denied"):
        rm._run(["example"])
