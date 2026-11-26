"""Regression cases from repository-wide debug pass; no native desktop/providers."""
import ast
import json
import logging
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from ultron import config as platform_config
from ultron.__main__ import main as cli
from ultron.core import config as central_config
from ultron.core import diagnostics
from ultron.core import wake_word as wake
from ultron.memory import config_manager as preferences


@pytest.fixture
def models(monkeypatch):
    state = SimpleNamespace(count=0, predict=lambda _: {"hey_jarvis": .9})
    package = ModuleType("openwakeword")
    package.__path__ = []
    module = ModuleType("openwakeword.model")
    class Model:
        def __init__(self, **kwargs):
            state.count += 1
        def predict(self, frame):
            return state.predict(frame)
    module.Model = Model
    monkeypatch.setitem(sys.modules, "openwakeword", package)
    monkeypatch.setitem(sys.modules, "openwakeword.model", module)
    return state


def detector(callback=lambda: None):
    return wake.WakeWordDetector(callback, selection=wake.settings({}), logger=lambda _: None)


def test_stop_during_inference_prevents_late_detection_and_overlap(models):
    entered, release, hits = threading.Event(), threading.Event(), []
    def blocked(frame):
        entered.set()
        assert release.wait(3)
        return {"hey_jarvis": 1}
    models.predict = blocked
    instance = detector(lambda: hits.append(1))
    assert instance.start()
    instance._queue.put([0] * 1280)
    assert entered.wait(2)
    try:
        assert instance.stop() is False
        assert not instance.ready
        assert instance.start() is False and models.count == 1
    finally:
        release.set()
        instance._thread.join(2)
    assert not hits and not instance._thread.is_alive()
    old_queue = instance._queue
    assert instance.start() and models.count == 2
    assert instance._queue is not old_queue
    assert instance.stop() and not instance.ready


def test_stop_from_detection_callback_no_self_join(models):
    done, outcomes = threading.Event(), []
    instance = detector()
    def detected():
        outcomes.append(instance.stop())
        done.set()
    instance._on_detect = detected
    assert instance.start()
    instance._queue.put([0] * 1280)
    assert done.wait(2)
    instance._thread.join(2)
    assert outcomes == [False] and not instance.ready and not instance._thread.is_alive()


def test_concurrent_start_loads_single_model(models):
    instance = detector()
    try:
        with ThreadPoolExecutor(max_workers=6) as workers:
            assert all(workers.map(lambda _: instance.start(), range(6)))
        assert models.count == 1
    finally:
        assert instance.stop()


def test_thread_start_failure_does_not_advertise_ready(models, monkeypatch):
    class FailedThread:
        def __init__(self, **kwargs):
            pass
        def start(self):
            raise RuntimeError("private native failure")
        def is_alive(self):
            return False
        def join(self, timeout):
            pass
    monkeypatch.setattr(wake.threading, "Thread", FailedThread)
    instance = detector()
    assert instance.start() is False
    assert not instance.ready and not instance._running and instance._model is None
    assert instance.stop()


def method(name):
    source = ast.parse(Path("ultron/app.py").read_text())
    cls = next(n for n in source.body if isinstance(n, ast.ClassDef) and n.name == "UltronLive")
    node = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
    namespace = {}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[node], type_ignores=[])), "app-method", "exec"), namespace)
    return namespace, namespace[name]


def test_ui_enable_model_failure_not_persisted_or_reported_enabled():
    namespace, toggle = method("_ui_wake_toggle")
    saved = []
    namespace.update(wake_is_ready=lambda: True, save_wake_word_enabled=saved.append)
    instance = SimpleNamespace(_wake_enabled=False, _ensure_wake_detector=lambda: False,
                               sleep=lambda **kw: pytest.fail("put to sleep with unusable model"))
    assert toggle(instance, True) == "unavailable"
    assert instance._wake_enabled is False and saved == []


def test_ui_disable_stops_detector():
    namespace, toggle = method("_ui_wake_toggle")
    calls = []
    namespace.update(save_wake_word_enabled=lambda value: calls.append(value))
    instance = SimpleNamespace(_wake_enabled=True, _wake_detector=SimpleNamespace(stop=lambda: calls.append("stop")),
                               wake=lambda **kw: calls.append("awake"))
    assert toggle(instance, False) == "disabled"
    assert calls == [False, "stop", "awake"]


@pytest.mark.parametrize("data", [[], None, 42, "bad", False])
def test_non_object_preferences_and_platform_config_safe(tmp_path, monkeypatch, data):
    path = tmp_path / "config.json"
    path.write_text(json.dumps(data))
    monkeypatch.setattr(preferences, "CONFIG_FILE", path)
    monkeypatch.setattr(platform_config, "_CONFIG_PATH", path)
    assert preferences.load_api_keys() == {} and platform_config.get_config() == {}
    assert preferences.get_ai_provider() == ""
    assert isinstance(platform_config.get_os(), str)


@pytest.mark.parametrize("value,expected", [("false", False), ("OFF", False), ("true", True), ("yes", True), ([], False), (None, False), (1, True), (0, False)])
def test_wake_and_ptt_flags_are_not_arbitrary_truthiness(monkeypatch, value, expected):
    monkeypatch.setattr(preferences, "load_api_keys", lambda: {"wake_word_enabled": value, "push_to_talk_enabled": value})
    assert preferences.get_wake_word_enabled() is expected
    assert preferences.get_push_to_talk_enabled() is expected


@pytest.mark.parametrize("value", [None, 42, [], {}])
def test_mistyped_provider_and_os_do_not_crash(monkeypatch, value):
    monkeypatch.setattr(preferences, "load_api_keys", lambda: {"ai_provider": value})
    monkeypatch.setattr(platform_config, "get_config", lambda: {"os_system": value})
    assert preferences.get_ai_provider() == ""
    assert platform_config.get_os() == platform_config._platform_os()


def test_nonstring_api_key_uses_valid_fallback(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(central_config, "load_api_keys", lambda: {"gemini_api_key": 42, "api_key": " valid-fallback "})
    assert central_config.get_gemini_key() == "valid-fallback"


def test_reinitializing_logging_closes_replaced_file_handler(tmp_path):
    central_config.setup_logging(log_file=tmp_path / "first.log")
    handler = next(h for h in logging.getLogger("ultron").handlers if isinstance(h, logging.FileHandler))
    central_config.setup_logging(log_file=tmp_path / "second.log")
    assert handler.stream is None


@pytest.fixture
def doctor(tmp_path, monkeypatch):
    monkeypatch.setattr(diagnostics, "CONFIG_DIR", tmp_path / "config")
    monkeypatch.setattr(diagnostics, "PACKAGE_ROOT", tmp_path)
    for name in diagnostics.RESOURCES:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("fake resource")
    monkeypatch.setattr(diagnostics.metadata, "version", lambda _: "test-installed")
    return tmp_path


def test_doctor_first_run_missing_config_is_not_crash(doctor):
    report = diagnostics.inspect("test")
    assert report["prerequisites_present"]
    assert report["configuration_status"] == "missing_first_run_setup_required"


def test_doctor_reports_missing_distribution_without_import(doctor, monkeypatch):
    def missing(name):
        raise diagnostics.metadata.PackageNotFoundError(name)
    monkeypatch.setattr(diagnostics.metadata, "version", missing)
    report = diagnostics.inspect("desktop")
    assert not report["prerequisites_present"]
    assert all(row["status"] == "missing" for row in report["dependencies"])


@pytest.mark.parametrize("content,status", [('[]', "invalid_root"), ('{bad', "invalid_json"), ('{"secret": "not-for-output"}', "object_present")])
def test_doctor_config_status_never_discloses_values(doctor, content, status):
    directory = doctor / "config"
    directory.mkdir()
    (directory / "api_keys.json").write_text(content)
    report = diagnostics.inspect()
    assert report["configuration_status"] == status
    assert "not-for-output" not in json.dumps(report) and "secret" not in json.dumps(report)


def test_doctor_cli_json_exit_status_and_no_ui_import(doctor, monkeypatch, capsys):
    assert cli(["doctor", "--profile", "test", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["prerequisites_present"]
    (doctor / diagnostics.RESOURCES[0]).unlink()
    assert cli(["doctor", "--json"]) == 1
    assert not json.loads(capsys.readouterr().out)["prerequisites_present"]
    assert "ultron.app" not in sys.modules and "ultron.ui" not in sys.modules


def test_tool_loop_lambdas_bind_deferred_iteration_values():
    tree = ast.parse(Path("ultron/app.py").read_text())
    tracked = {"fn_name", "tool_res", "ack", "player"}
    relevant = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Lambda):
            used = {n.id for n in ast.walk(node.body) if isinstance(n, ast.Name)} & tracked
            if used & {"fn_name", "tool_res", "ack"}:
                relevant.append(node)
                assert used <= {arg.arg for arg in node.args.args}
    assert len(relevant) >= 3


def test_doctor_special_file_and_large_config_are_not_parsed(doctor):
    import os
    directory = doctor / "config"
    directory.mkdir()
    target = directory / "api_keys.json"
    if hasattr(os, "mkfifo"):
        os.mkfifo(target)
        assert diagnostics.inspect()["configuration_status"] == "unsupported_file_type"
        target.unlink()
    target.write_bytes(b"x" * 65537)
    assert diagnostics.inspect()["configuration_status"] == "oversized"


def test_doctor_unreadable_resource_is_a_failure_status(doctor, monkeypatch):
    monkeypatch.setattr(diagnostics, "_resource", lambda _: False)
    assert not diagnostics.inspect()["prerequisites_present"]
