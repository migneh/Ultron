"""
Tests for core/config.py — centralized configuration.

These tests never touch the real config/api_keys.json: they monkeypatch the
module-level paths and environment so each case is hermetic.
"""
from ultron.core import config as cfg


def _write_tmp_config(tmp_path, data: dict):
    p = tmp_path / "api_keys.json"
    p.write_text(__import__("json").dumps(data), encoding="utf-8")
    return p


def test_get_gemini_key_env_wins(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "env-secret-123")
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"gemini_api_key": "file-secret"}))
    assert cfg.get_gemini_key() == "env-secret-123"


def test_get_gemini_key_from_file(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"gemini_api_key": "file-secret"}))
    assert cfg.get_gemini_key() == "file-secret"


def test_get_gemini_key_falls_back_to_api_key(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"api_key": "legacy-key"}))
    assert cfg.get_gemini_key() == "legacy-key"


def test_get_gemini_key_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "does-not-exist.json")
    assert cfg.get_gemini_key() is None


def test_load_api_keys_ignores_bad_json(monkeypatch, tmp_path, caplog):
    bad = tmp_path / "api_keys.json"
    bad.write_text("{not valid json", encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_FILE", bad)
    with caplog.at_level("WARNING", logger="ultron.config"):
        assert cfg.load_api_keys() == {}


def test_get_bool_and_get_str(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"ui_color": "#ff0008", "proactive": "true"}))
    assert cfg.get_str("ui_color") == "#ff0008"
    assert cfg.get_str("missing", "default") == "default"
    # env override
    monkeypatch.setenv("ui_color", "#00ff00")
    assert cfg.get_str("ui_color") == "#00ff00"
    assert cfg.get_bool("proactive") is True
    assert cfg.get_bool("missing_flag", False) is False


def test_require_gemini_key_raises_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "missing.json")
    try:
        cfg.require_gemini_key()
        raise AssertionError("require_gemini_key should have raised")
    except RuntimeError as e:
        assert "Gemini API key" in str(e)


def test_setup_logging_is_idempotent(tmp_path):
    import logging
    import logging.handlers as lh

    cfg.setup_logging(log_file=tmp_path / "ultron.log")
    cfg.setup_logging(log_file=tmp_path / "ultron.log")  # should not duplicate handlers
    root = logging.getLogger("ultron")  # the logger setup_logging configures
    file_handlers = [h for h in root.handlers if isinstance(h, lh.RotatingFileHandler)]
    stream_handlers = [h for h in root.handlers if type(h) is logging.StreamHandler]
    assert len(file_handlers) == 1, f"expected 1 file handler, got {len(file_handlers)}"
    assert len(stream_handlers) == 1, f"expected 1 stream handler, got {len(stream_handlers)}"
    assert len(root.handlers) == 2  # exactly stream + file, never duplicated


def test_get_ai_provider_defaults_to_gemini(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {}))
    assert cfg.get_ai_provider() == "gemini"


def test_get_ai_provider_from_ai_provider_key(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"ai_provider": "ollama"}))
    assert cfg.get_ai_provider() == "ollama"


def test_get_ai_provider_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_PROVIDER", "openai")
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"ai_provider": "ollama"}))
    assert cfg.get_ai_provider() == "openai"


def test_get_ai_provider_legacy_provider_key(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_PROVIDER", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"provider": "gemini"}))
    assert cfg.get_ai_provider() == "gemini"


def test_get_ai_model_from_ai_model_key(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"ai_model": "models/gemini-2.5-flash"}))
    assert cfg.get_ai_model() == "models/gemini-2.5-flash"


def test_get_ai_model_env_override(monkeypatch, tmp_path):
    monkeypatch.setenv("AI_MODEL", "custom-model")
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"ai_model": "models/gemini-2.5-flash"}))
    assert cfg.get_ai_model() == "custom-model"


def test_get_ai_model_legacy_model_key(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", _write_tmp_config(tmp_path, {"model": "legacy-model"}))
    assert cfg.get_ai_model() == "legacy-model"


def test_get_ai_model_none_when_missing(monkeypatch, tmp_path):
    monkeypatch.delenv("AI_MODEL", raising=False)
    monkeypatch.setattr(cfg, "CONFIG_FILE", tmp_path / "does-not-exist.json")
    assert cfg.get_ai_model() is None


def test_workspace_recall_imports_available():
    """workspace_recall must import re and subprocess (P1 bug fix)."""
    import ultron.actions.workspace_recall as wr
    assert hasattr(wr, "re"), "workspace_recall must import re"
    assert hasattr(wr, "subprocess"), "workspace_recall must import subprocess"
