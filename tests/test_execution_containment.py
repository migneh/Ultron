"""Fail-closed generated-code paths; no hostile code is actually executed."""
import sys

import pytest

from ultron.actions import desktop
from ultron.actions import self_evolution as se


@pytest.fixture
def draft_env(tmp_path, monkeypatch):
    actions = tmp_path / "actions"
    plugins = tmp_path / "plugins"
    actions.mkdir()
    plugins.mkdir()
    drafts = tmp_path / "drafts"
    monkeypatch.setattr(se, "_ACTIONS_DIR", actions)
    monkeypatch.setattr(se, "_PLUGINS_DIR", plugins)
    monkeypatch.setattr(se, "_draft_directory", lambda: drafts)
    monkeypatch.setattr(se, "_prometheus_audit_log", lambda *a: None)
    captured = {}
    monkeypatch.setattr(se.confirm_gate, "request", lambda **kw: captured.update(kw) or "pending")
    return actions, plugins, drafts, captured


@pytest.mark.parametrize("category", ["action", "plugin"])
def test_approved_source_stays_inert(draft_env, category):
    actions, plugins, drafts, captured = draft_env
    code = 'raise RuntimeError("must not execute at import")\n'
    before = set(sys.modules)
    assert se.synthesize_action("review_fixture", "draft", code, category=category) == "pending"
    assert not drafts.exists()
    assert "Review-only draft saved" in captured["run"]()
    assert not list(actions.iterdir()) and not list(plugins.iterdir())
    files = list(drafts.iterdir())
    assert len(files) == 1 and files[0].name.endswith(".py.txt")
    assert files[0].read_text() == code
    assert not (set(sys.modules) - before) & {'ultron.actions.review_fixture', 'ultron.plugins.review_fixture'}
    assert "already exists" in captured["run"]()


def test_failed_draft_write_never_promotes(draft_env, monkeypatch):
    actions, plugins, _, captured = draft_env
    se.synthesize_action("broken", "draft", 'VALUE = "long enough fixture"\n')
    monkeypatch.setattr(se.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("disk")))
    with pytest.raises(OSError):
        captured["run"]()
    assert not list(actions.iterdir()) and not list(plugins.iterdir())


def test_no_registry_test_backdoor(monkeypatch):
    class Trap:
        def has(self, *args):
            pytest.fail("registry queried")
    monkeypatch.setattr(se, "_LIVE_ACTION_REGISTRY", Trap())
    monkeypatch.setattr(se, "_LIVE_PLUGIN_REGISTRY", Trap())
    for alias in ("test", "run", "execute"):
        assert "disabled" in se.self_evolution({"action": alias, "tool_name": "anything"})


def test_desktop_task_never_generates_or_executes(monkeypatch):
    monkeypatch.setattr(desktop, "_ask_gemini_for_desktop_action", lambda *a: pytest.fail("provider called"))
    monkeypatch.setattr(desktop, "_build_sandbox", lambda: pytest.fail("sandbox called"))
    for args in ({"action": "task", "task": "do something"}, {"action": "unknown action"}, {"task": "anything"}):
        assert "disabled" in desktop.desktop_control(args)
    assert "disabled" in desktop._execute_generated_code('raise RuntimeError("never")')


def test_sandbox_stub_fail_closed():
    with pytest.raises(RuntimeError, match="disabled"):
        desktop._build_sandbox()


def test_source_size_bounded(draft_env):
    assert "refused" in se.synthesize_action("large", "large", "x" * 100001)
    assert "refused" in se.synthesize_action("wrong", "wrong", {})
