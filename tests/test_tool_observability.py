import concurrent.futures
import json
import threading

import pytest

from actions import tool_status as status
from core import action_loader as actions
from core import plugin_loader as plugins
from core import tool_observability as telemetry


@pytest.fixture
def observer(monkeypatch):
    obj = telemetry.Observer(10)
    monkeypatch.setattr(telemetry, "OBSERVER", obj)
    monkeypatch.setattr(status, "OBSERVER", obj)
    monkeypatch.setattr(telemetry, "_registries", ())
    return obj


def registry(handler, logger=lambda _: None):
    record = actions.ActionRecord(name="example", handler=handler, valid=True)
    return actions.ActionRegistry({"example": record}, logger)


def test_handler_returned_not_success(observer):
    logs = []
    reg = registry(lambda parameters: "Failure inside old handler: SECRET", logs.append)
    assert "SECRET" in reg.run("example", {"password": "SECRET"})
    event = observer.snapshot()["recent"][0]
    assert event["code"] == "HANDLER_RETURNED" and event["duration_ms"] >= 0
    assert "SECRET" not in str(observer.snapshot()) + str(logs)
    assert "parameters" not in event and "result" not in event


@pytest.mark.parametrize(
    "exception,code",
    [(RuntimeError("SECRET"), "TOOL_EXCEPTION"), (ImportError("SECRET"), "DEPENDENCY_MISSING")],
)
def test_exception_redaction(observer, capsys, exception, code):
    def fail(parameters):
        raise exception

    logs = []
    result = registry(fail, logs.append).run("example", {"body": "SECRET"})
    assert code in result
    assert "SECRET" not in result + str(logs) + str(observer.snapshot()) + str(capsys.readouterr())
    assert observer.snapshot()["active"] == 0


@pytest.mark.parametrize("parameters", [None, [], "secret", 1])
def test_invalid_parameters_no_execution(observer, parameters):
    def fail(**kwargs):
        pytest.fail("handler invoked")

    assert "INVALID_ARGUMENTS" in registry(fail).run("example", parameters)


def test_unavailable_invalid_name_sanitized(observer):
    reg = registry(lambda parameters: "ok")
    assert "UNAVAILABLE" in reg.run("SECRET\npath", {})
    assert "SECRET" not in str(observer.snapshot())
    assert "unknown" in reg.run([], {})


def test_logger_failure_no_repeat(observer):
    calls = []

    def logger(_):
        raise RuntimeError("logger failed")

    reg = registry(lambda parameters: calls.append(1) or "ok", logger)
    assert reg.run("example", {}) == "ok" and calls == [1]


def test_context_and_empty_result_compatibility(observer):
    seen = {}

    def handler(parameters, player=None, response=None):
        seen.update(parameters=parameters, player=player, response=response)

    assert registry(handler).run("example", {"x": 1}, {"player": "ui"}) == "Done."
    assert seen == {"parameters": {"x": 1}, "player": "ui", "response": None}


def test_bounded_history_and_snapshot_copies(observer):
    reg = registry(lambda parameters: "ok")
    for _ in range(30):
        reg.run("example", {})
    snapshot = observer.snapshot(10)
    assert len(snapshot["recent"]) == 10 and snapshot["total_finished"] == 30
    snapshot["counts"]["HANDLER_RETURNED"] = -1
    snapshot["recent"][0]["name"] = "mutated"
    assert observer.snapshot()["counts"]["HANDLER_RETURNED"] == 30
    assert observer.snapshot()["recent"][0]["name"] == "example"


def test_concurrent_active_and_counters(observer):
    started, release = threading.Event(), threading.Event()

    def handler(parameters):
        started.set()
        release.wait(2)
        return "ok"

    reg = registry(handler)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(reg.run, "example", {}) for _ in range(4)]
        assert started.wait(2)
        assert observer.snapshot()["active"] >= 1
        release.set()
        assert all(future.result() == "ok" for future in futures)
    assert observer.snapshot()["active"] == 0 and observer.snapshot()["total_finished"] == 4


@pytest.mark.parametrize("enabled,code", [(True, "HANDLER_RETURNED"), (False, "DISABLED")])
def test_plugin_dispatch(observer, monkeypatch, enabled, code):
    monkeypatch.setattr(plugins, "get_plugin_enabled", lambda _: enabled)
    record = plugins.PluginRecord(name="example", run=lambda parameters, **kwargs: "ok", valid=True)
    reg = plugins.PluginRegistry({"example": record}, lambda _: None)
    result = reg.run("example", {})
    assert result == "ok" if enabled else "DISABLED" in result
    assert observer.snapshot()["recent"][0]["code"] == code
    assert reg.status_snapshot()[0]["state"] == ("enabled" if enabled else "disabled")


def test_status_bound_registry_and_no_paths(observer, monkeypatch):
    monkeypatch.setattr(plugins, "get_plugin_enabled", lambda _: False)
    ar = registry(lambda parameters: "ok")
    ar._all_records.append(actions.ActionRecord("bad", file="/SECRET/path", error="SECRET"))
    pr = plugins.PluginRegistry({}, lambda _: None)
    telemetry.bind_registries(ar, pr)
    report = json.loads(status.tool_status({"section": "registry"}))
    assert report["registry"]["state"] == "bound"
    assert {"name": "bad", "state": "rejected"} in report["registry"]["actions"]
    assert "SECRET" not in str(report)


def test_dependency_checks_no_import_execution(observer, monkeypatch):
    seen = []
    monkeypatch.setattr(status.importlib.util, "find_spec", lambda name: seen.append(name) or None)
    monkeypatch.setattr(status.shutil, "which", lambda _: "/SECRET/path")
    report = json.loads(status.tool_status({"section": "dependencies"}))
    assert seen == list(status._MODULES)
    assert set(report["dependencies"]["python_modules"].values()) == {"missing"}
    assert set(report["dependencies"]["programs"].values()) == {"on_path"}
    assert "SECRET" not in str(report)


@pytest.mark.parametrize(
    "params",
    [
        None,
        {"section": []},
        {"limit": True},
        {"limit": 101},
        {"section": "run"},
        {"password": "SECRET"},
    ],
)
def test_status_invalid(observer, params):
    assert "INVALID_ARGUMENTS" in status.tool_status(params)


def test_status_registered_dispatch(observer):
    from types import SimpleNamespace

    record = actions._validate(SimpleNamespace(TOOL=status.TOOL), "tool_status.py")
    reg = actions.ActionRegistry({record.name: record}, lambda _: None)
    report = json.loads(reg.run("tool_status", {}))
    assert report["dispatch"]["active"] == 1  # this status call itself is in flight
    assert observer.snapshot()["recent"][0]["name"] == "tool_status"


def test_discovery_import_exception_redacted(observer, tmp_path, capsys):
    (tmp_path / "observability_fail.py").write_text('raise RuntimeError("SECRET")')
    logs = []
    reg = actions.discover_actions(tmp_path, logger=logs.append)
    assert not reg.names()
    assert "SECRET" not in str(logs) + str(capsys.readouterr())


def test_plugin_import_exception_redacted(tmp_path):
    assert "SECRET" not in plugins._load_error(
        tmp_path / "test.py", tmp_path, RuntimeError("SECRET")
    )
    assert "SECRET!" not in plugins._load_error(
        tmp_path / "test.py", tmp_path, ModuleNotFoundError(name="SECRET!")
    )


def test_monotonic_duration(observer, monkeypatch):
    ticks = iter([10.0, 10.125])
    monkeypatch.setattr(telemetry.time, "monotonic", lambda: next(ticks))
    assert registry(lambda parameters: "ok").run("example", {}) == "ok"
    assert observer.snapshot()["recent"][0]["duration_ms"] == 125.0


def test_plugin_exception_safe(observer, monkeypatch):
    monkeypatch.setattr(plugins, "get_plugin_enabled", lambda _: True)

    def fail(**kwargs):
        raise RuntimeError("SECRET")

    logs = []
    record = plugins.PluginRecord(name="example", run=fail, valid=True)
    reg = plugins.PluginRegistry({"example": record}, logs.append)
    result = reg.run("example", {"token": "SECRET"})
    assert "TOOL_EXCEPTION" in result and "SECRET" not in result + str(logs)
    assert observer.snapshot()["recent"][0]["kind"] == "plugin"


def test_dependency_probe_errors_are_unknown(observer, monkeypatch):
    def fail(*args):
        raise RuntimeError("SECRET")

    monkeypatch.setattr(status.importlib.util, "find_spec", fail)
    monkeypatch.setattr(status.shutil, "which", fail)
    report = status.dependencies()
    assert set(report["python_modules"].values()) == {"unknown"}
    assert set(report["programs"].values()) == {"unknown"}
    assert "SECRET" not in str(report)


def test_invalid_context_not_passed_to_handler(observer):
    assert "INVALID_ARGUMENTS" in registry(lambda parameters: "ok").run("example", {}, ctx=[])


def test_dispatch_source_does_not_log_payloads():
    from pathlib import Path

    source = Path("main.py").read_text()
    assert "with args: {fn_args}" not in source
    assert "output: {str(tool_res)" not in source
    assert "details=str(fn_args)" not in source
    assert "details=str(args)" not in source
    assert "Tool response ready (result omitted" in source
