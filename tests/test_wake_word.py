"""Fake wake providers only: no downloads, microphone, native model or GUI."""
import json
import sys
from types import ModuleType, SimpleNamespace

import pytest

from ultron.core import wake_word as wake
from ultron.memory import config_manager as config


def test_legacy_default_is_preserved():
    selected = wake.settings({})
    assert wake.WAKE_MODEL == selected.model == "hey_jarvis"
    assert selected.label == "hey jarvis" and selected.threshold == .5


@pytest.mark.parametrize("model", wake.BUILTIN_MODELS)
def test_builtin_selection(model):
    selected = wake.settings({"wake_word_model": model})
    assert selected.model == model and selected.label == model.replace("_", " ")


@pytest.mark.parametrize("value", [0, -1, 1.1, float("nan"), float("inf"), True, "0.5", None, 10 ** 500])
def test_invalid_threshold_refused(value):
    with pytest.raises(ValueError):
        wake.settings({"wake_word_threshold": value})


@pytest.mark.parametrize("value", ["hey_ultron", "relative.onnx", "", None, "https://example.com/m.onnx"])
def test_unavailable_or_arbitrary_phrase_not_a_model(value):
    with pytest.raises(ValueError):
        wake.settings({"wake_word_model": value})


def test_custom_model_needs_real_absolute_onnx_and_label_is_only_display(tmp_path):
    path = tmp_path / "my_phrase.onnx"
    path.write_bytes(b"fake test model")
    selected = wake.settings({"wake_word_model": str(path), "wake_word_label": "hello assistant"})
    assert selected.model == str(path) and selected.score_key == "my_phrase"
    assert selected.label == "hello assistant"


@pytest.mark.parametrize("label", ["", "bad\nlabel", "a" * 81, None])
def test_invalid_label_refused(label):
    with pytest.raises(ValueError):
        wake.settings({"wake_word_label": label})


@pytest.fixture
def stored(tmp_path, monkeypatch):
    directory = tmp_path / "config"
    directory.mkdir()
    path = directory / "api_keys.json"
    monkeypatch.setattr(config, "CONFIG_DIR", directory)
    monkeypatch.setattr(config, "CONFIG_FILE", path)
    return path


def test_save_preserves_unrelated_config_and_does_not_enable(stored):
    stored.write_text(json.dumps({"gemini_api_key": "fake-private", "wake_word_enabled": False}))
    config.save_wake_settings(wake_word_model="alexa", wake_word_threshold=.7)
    data = json.loads(stored.read_text())
    assert data["gemini_api_key"] == "fake-private" and data["wake_word_enabled"] is False
    assert data["wake_word_label"] == "alexa" and data["wake_word_threshold"] == .7
    assert not list(stored.parent.glob(".wake-settings-*"))


def test_invalid_update_does_not_write(stored):
    stored.write_text('{"keep": "original"}')
    with pytest.raises(ValueError):
        config.save_wake_settings(wake_word_threshold=0)
    assert stored.read_text() == '{"keep": "original"}'


def test_corrupt_config_is_not_overwritten(stored):
    stored.write_text("{broken")
    with pytest.raises(ValueError):
        config.save_wake_settings(wake_word_model="alexa")
    assert stored.read_text() == "{broken"


def test_model_change_resets_stale_label(stored):
    stored.write_text('{"wake_word_label": "hey jarvis"}')
    config.save_wake_settings(wake_word_model="alexa")
    assert wake.settings().label == "alexa"


def test_invalid_setup_does_not_install_or_download(stored, monkeypatch):
    stored.write_text('{"wake_word_model": "invalid phrase"}')
    monkeypatch.setattr(wake.subprocess, "run", lambda *a, **kw: pytest.fail("installation"))
    assert wake.install_and_download(logger=lambda _: None)[0] is False


def fake_provider(tmp_path, monkeypatch):
    package = ModuleType("openwakeword")
    package.__path__ = [str(tmp_path)]
    package.__file__ = str(tmp_path / "__init__.py")
    models = tmp_path / "resources" / "models"
    models.mkdir(parents=True)
    monkeypatch.setitem(sys.modules, "openwakeword", package)
    monkeypatch.setattr(wake, "is_installed", lambda: True)
    return package, models


def test_readiness_uses_selected_onnx_not_other_or_tflite(tmp_path, monkeypatch):
    _, directory = fake_provider(tmp_path, monkeypatch)
    for name in ("hey_jarvis_v0.1.onnx", "alexa.tflite", "melspectrogram.onnx", "embedding_model.onnx"):
        (directory / name).touch()
    assert wake.is_ready(wake.settings({}))
    assert not wake.is_ready(wake.settings({"wake_word_model": "alexa"}))
    (directory / "alexa_v0.1.onnx").touch()
    assert wake.is_ready(wake.settings({"wake_word_model": "alexa"}))


def test_installer_downloads_only_selected_builtin(stored, tmp_path, monkeypatch):
    config.save_wake_settings(wake_word_model="alexa")
    package, _ = fake_provider(tmp_path, monkeypatch)
    calls = []
    utility = ModuleType("openwakeword.utils")
    utility.download_models = lambda names: calls.append(names)
    package.utils = utility
    monkeypatch.setitem(sys.modules, "openwakeword.utils", utility)
    monkeypatch.setattr(wake, "is_ready", lambda selected: selected.model == "alexa")
    assert wake.install_and_download(logger=lambda _: None)[0]
    assert calls == [["alexa"]]


def test_custom_setup_never_downloads_all_as_fallback(stored, tmp_path, monkeypatch):
    path = tmp_path / "model.onnx"
    path.touch()
    config.save_wake_settings(wake_word_model=str(path))
    monkeypatch.setattr(wake, "is_ready", lambda _: False)
    monkeypatch.setattr(wake.subprocess, "run", lambda *a, **kw: pytest.fail("installation"))
    ok, message = wake.install_and_download(logger=lambda _: None)
    assert not ok and "no automatic download" in message


def test_detector_loads_exact_model_and_logs_actual_label(tmp_path, monkeypatch):
    fake_provider(tmp_path, monkeypatch)
    calls, logs = [], []
    module = ModuleType("openwakeword.model")
    module.Model = lambda **kw: calls.append(kw) or SimpleNamespace()
    monkeypatch.setitem(sys.modules, "openwakeword.model", module)
    monkeypatch.setattr(wake.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None, is_alive=lambda: False, join=lambda timeout: None))
    detector = wake.WakeWordDetector(lambda: None, selection=wake.settings({"wake_word_model": "alexa"}), logger=logs.append)
    assert detector.start()
    assert calls == [{"wakeword_models": ["alexa"], "inference_framework": "onnx"}]
    assert "'alexa'" in logs[-1]
    detector.stop()


@pytest.mark.parametrize("scores,detected", [({"unrelated": .99}, False), ({"alexa": .9}, True),
    ({"alexa_v0.1": .8}, True), ({"alexa_other": 1}, False), ({"alexa": float("nan")}, False)])
def test_predictions_match_only_selected_model(scores, detected, monkeypatch):
    detector = wake.WakeWordDetector(lambda: None, selection=wake.settings({"wake_word_model": "alexa"}), logger=lambda _: None)
    # One synchronous fake inference iteration, then terminate regardless of score.
    hits = []
    detector._on_detect = lambda: hits.append(1)
    detector._running = True
    def predict(frame):
        detector._running = False
        return scores
    detector._model = SimpleNamespace(predict=predict)
    detector._queue.put([0] * 1280)
    detector._loop()
    assert bool(hits) == detected


def test_cli_updates_without_importing_ui(stored, capsys):
    from ultron.__main__ import main
    main(["wake-config", "--model", "alexa", "--threshold", "0.6"])
    result = json.loads(capsys.readouterr().out)
    assert result["wake_word_model"] == "alexa" and result["wake_word_threshold"] == .6
    assert "ultron.ui" not in sys.modules
