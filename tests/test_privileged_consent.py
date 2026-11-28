"""Privileged entry points cannot run before host consent; fake effects only."""
import json

import pytest

from ultron.actions import system_command as sc
from ultron.actions import system_utility as utility
from ultron.core import confirm


@pytest.fixture(autouse=True)
def clean_gate(tmp_path, monkeypatch):
    monkeypatch.setattr(confirm, "_pending", None)
    for name in ("_show_cb", "_hide_cb", "_show_with_id_cb", "_hide_with_id_cb", "_log_cb"):
        monkeypatch.setattr(confirm, name, None)
    monkeypatch.setattr(sc, "_AUDIT_DIR", tmp_path)
    monkeypatch.setattr(sc, "_AUDIT_FILE", tmp_path / "audit.log")


@pytest.mark.parametrize("command", ["whoami", "git log", "git diff", "git status", "ls --help", "git -c core.pager=anything log"])
def test_shell_never_runs_headless(command, monkeypatch):
    monkeypatch.setattr(sc, "_run_command", lambda *a, **k: pytest.fail("executed"))
    assert "have not done it" in sc.system_command_handler({"command": command})


def test_shell_full_immutable_plan_and_one_shot(monkeypatch):
    shown, ran = [], []
    confirm.bind(lambda *a: shown.append(a), lambda: None)
    monkeypatch.setattr(sc, "_run_command", lambda *a, **k: ran.append((a, k)) or "result")
    command = "echo " + "a" * 600 + " final_suffix"
    params = {"command": command, "shell": "cmd", "timeout": 999}
    cwd = sc.os.getcwd()
    assert "PENDING" in sc.system_command_handler(params)
    assert not ran and command in shown[0][1]
    assert cwd in shown[0][1] and "60s" in shown[0][1]
    params.update(command="different", shell="powershell", timeout=2)
    confirm.resolve(True)
    confirm.resolve(True)
    assert ran == [((command, "cmd", 60), {"cwd": cwd})]


def test_denied_shell_never_runs(monkeypatch):
    confirm.bind(lambda *a: None, lambda: None)
    monkeypatch.setattr(sc, "_run_command", lambda *a, **k: pytest.fail("executed"))
    sc.system_command_handler({"command": "git log"})
    confirm.resolve(False)


def test_audit_contains_no_command_or_output(tmp_path):
    sc._audit_log("SECRET-COMMAND", "bash", "confirmed", "SECRET-OUTPUT")
    text = (tmp_path / "audit.log").read_text()
    row = json.loads(text)
    assert "SECRET" not in text
    assert len(row["command_sha256"]) == 64
    assert "command" not in row and "result" not in row


@pytest.mark.parametrize("operation,helper", [("empty_recycle_bin", "_empty_recycle_bin_now"), ("sleep", "_sleep_computer_now")])
def test_utility_dispatch_and_public_helpers_require_consent(monkeypatch, operation, helper):
    monkeypatch.setattr(utility, "_OS", "Windows")
    calls = []
    monkeypatch.setattr(utility, helper, lambda: calls.append(operation) or "submitted")
    public = utility.empty_recycle_bin if operation == "empty_recycle_bin" else utility.sleep_computer
    assert "have not done it" in public()
    assert not calls
    confirm.bind(lambda *a: None, lambda: None)
    assert "PENDING" in utility.system_utility_handler({"action": operation})
    assert not calls
    confirm.resolve(False)
    assert not calls
    public()
    confirm.resolve(True)
    assert calls == [operation]


def test_unsupported_utility_does_not_offer_fake_action(monkeypatch):
    monkeypatch.setattr(utility, "_OS", "Linux")
    monkeypatch.setattr(confirm, "request", lambda **k: pytest.fail("approval for unsupported action"))
    assert "not supported" in utility.sleep_computer()
    assert "not supported" in utility.empty_recycle_bin()
