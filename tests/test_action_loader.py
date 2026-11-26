"""Dispatch contracts: effects are stubbed; no desktop, network or jobs run."""
from types import SimpleNamespace

import pytest

from ultron.core.action_loader import ActionRegistry, _call_handler, _validate
from ultron.core.tool_observability import DispatchIssue


def registry(tool):
    rec = _validate(SimpleNamespace(TOOL=tool), "test.py")
    assert rec.valid, rec.error
    return ActionRegistry({rec.name: rec}, lambda _: None)


def declaration(handler, mode="parameters", properties=None):
    return {"name": "example", "description": "Example", "handler": handler,
            "argument_mode": mode,
            "parameters": {"type": "OBJECT", "properties": properties or {}}}


def test_original_dict_convention_and_host_context():
    seen = {}

    def handler(parameters, **kwargs):
        seen.update(parameters=parameters, context=kwargs)
        return "ok"

    assert registry(declaration(handler)).run("example", {"player": "untrusted"}, {"player": "host"}) == "ok"
    assert seen["parameters"] == {"player": "untrusted"}
    assert seen["context"]["player"] == "host"


def test_named_options_do_not_receive_undeclared_context():
    def handler(action="status", player=None, **options):
        assert action == "research"
        assert player == "host"
        assert options == {}
        return "ok"

    reg = registry(declaration(handler, "keywords", {"action": {"type": "STRING"}}))
    assert reg.run("example", {"action": "research"}, {"player": "host", "speak": "host"}) == "ok"
    assert "argument_mode" not in reg.get_tool_declarations()[0]


@pytest.mark.parametrize("field", ["player", "speak", "response", "session_memory", "parameters", "unknown"])
def test_named_dispatch_rejects_injected_or_unknown_fields(field):
    called = []

    def handler(**kwargs):
        called.append(kwargs)

    reg = registry(declaration(handler, "keywords"))
    reg.run("example", {field: "injected"})
    assert called == []


def test_required_named_field_rejected_before_execution():
    called = []
    tool = declaration(lambda **kw: called.append(kw), "keywords", {"action": {"type": "STRING"}})
    tool["parameters"]["required"] = ["action"]
    registry(tool).run("example", {})
    assert called == []


def test_direct_named_helper_rejects_context_override():
    with pytest.raises(DispatchIssue, match="INVALID_ARGUMENTS"):
        _call_handler(lambda **kw: None, {"player": "untrusted"}, {}, "keywords")


@pytest.mark.parametrize("tool", [
    declaration(lambda action="": None),
    declaration(lambda parameters: None, "invalid"),
    declaration(lambda parameters: None, "keywords", {"player": {"type": "STRING"}}),
    declaration(lambda action: None, "keywords", {"unknown": {"type": "STRING"}}),
])
def test_incompatible_contract_rejected_during_discovery(tool):
    assert not _validate(SimpleNamespace(TOOL=tool), "bad.py").valid


def test_real_web_autopilot_research_receives_query(monkeypatch):
    from ultron.actions import web_autopilot as module
    seen = []
    monkeypatch.setattr(module, "deep_web_research", lambda query: seen.append(query) or "research result")
    result = registry(module.TOOL).run("web_autopilot", {"action": "research", "query": "dispatch test"}, {"speak": object()})
    assert result == "research result"
    assert seen == ["dispatch test"]


def test_real_swarm_status_does_not_default_to_list(monkeypatch):
    from ultron.actions import drone_swarm as module
    monkeypatch.setattr(module, "get_drone_status", lambda drone_id: f"status:{drone_id}")
    monkeypatch.setattr(module, "list_drones", lambda: pytest.fail("wrong default branch"))
    assert registry(module.TOOL).run("drone_swarm", {"action": "status", "drone_id": "test"}) == "status:test"


def test_real_telepathy_broadcast_receives_message(monkeypatch):
    from ultron.actions import omni_telepathy as module
    monkeypatch.setattr(module, "telepathy_broadcast", lambda message: f"stub:{message}")
    assert registry(module.TOOL).run("omni_telepathy", {"action": "broadcast", "text": "test"}) == "stub:test"


def test_real_screen_handler_receives_prompt_without_capture(monkeypatch):
    from ultron.actions import screen_processor as module
    seen = []

    class Player:
        def set_active_task(self, *args, **kwargs):
            seen.append(kwargs["details"])

    def no_capture():
        raise RuntimeError("capture disabled by test")

    # Audio is an optional effect imported inside the handler.
    import sys
    monkeypatch.setitem(sys.modules, 'ultron.actions.audio_matrix', SimpleNamespace(play_sound_async=lambda _: None))
    monkeypatch.setattr(module, "_capture_screen", no_capture)
    result = registry(module.TOOL).run("screen_mind_read", {"prompt": "Inspect this specific dialog"}, {"player": Player()})
    assert seen == ["Inspect this specific dialog"]
    assert "capture disabled by test" in result
