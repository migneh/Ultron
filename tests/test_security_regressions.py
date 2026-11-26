"""Consent and shell boundary regressions. No generated code is executed."""
import pytest

from ultron.actions import self_evolution as se
from ultron.actions import system_command as sc


@pytest.mark.parametrize("command", [
    "whoami; touch /tmp/pwned", "ls && touch /tmp/pwned", "ls >secret",
    "ls\ntouch /tmp/pwned", "ls $(touch /tmp/pwned)", "ls `id`",
    "whoami & calc", "./ls", "git branch new-branch", "git branch -D main",
    "git remote add bad https://example.com", "git log --output=secret",
    "git diff --ext-diff", "date 010112002030", "hostname changed",
    "ip link set eth0 down", "ifconfig eth0 down", "ls %EVIL%",
])
def test_unsafe_inspection_commands_need_consent(command):
    assert sc._classify(command) != "direct"


def test_synthesis_does_not_write_before_approval(tmp_path, monkeypatch):
    monkeypatch.setattr(se, "_ACTIONS_DIR", tmp_path)
    monkeypatch.setattr(se, "_prometheus_audit_log", lambda *args: None)
    captured = {}
    def request(**kwargs):
        captured.update(kwargs)
        return "awaiting approval"
    monkeypatch.setattr(se.confirm_gate, "request", request)
    code = '"""Safe regression fixture."""\nVALUE = 42\n'
    assert se.synthesize_action("regression_tool", "Test fixture", code) == "awaiting approval"
    assert not list(tmp_path.glob("*.py"))
    assert callable(captured["run"])


def test_synthesis_refuses_existing_tool(tmp_path, monkeypatch):
    monkeypatch.setattr(se, "_ACTIONS_DIR", tmp_path)
    path = tmp_path / "regression_tool.py"
    path.write_text("# existing implementation")
    result = se.synthesize_action("regression_tool", "Test", '"""Test code."""\nVALUE = 42\n')
    assert "already exists" in result
    assert path.read_text() == "# existing implementation"


@pytest.mark.parametrize("command", ["ipconfig /release", "ipconfig /renew", "ipconfig /flushdns"])
def test_ipconfig_mutations_require_confirmation(command):
    assert sc._classify(command) == "confirm"


def test_generated_desktop_code_is_not_executed_before_approval(monkeypatch):
    from ultron.actions import desktop
    monkeypatch.setattr(desktop, "_build_sandbox", lambda: pytest.fail("ran before approval"))
    assert "disabled" in desktop._execute_generated_code('print("test")')
