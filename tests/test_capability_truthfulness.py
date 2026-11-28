"""Fake native/provider adapters: no desktop, network, audio or ADB effects."""
import subprocess
import sys
from types import SimpleNamespace

import pytest

from ultron.actions import iot_overlord as iot
from ultron.actions import media_controller as media
from ultron.actions import workspace_matrix as workspace


@pytest.mark.parametrize("value", [None, True, "0", -1, 101, 12.5, {}, []])
def test_invalid_volume_never_calls_backend(value, monkeypatch):
    monkeypatch.setattr(media, "_windows_endpoint", lambda: pytest.fail("backend reached"))
    monkeypatch.setattr(media, "_OS", "Windows")
    assert "Invalid" in media.media_volume_set(value)


def test_zero_volume_survives_dispatch_and_scalar_readback(monkeypatch):
    levels = []
    endpoint = SimpleNamespace(SetMasterVolumeLevelScalar=lambda value, _: levels.append(value),
                               GetMasterVolumeLevelScalar=lambda: 0.0)
    monkeypatch.setattr(media, "_OS", "Windows")
    monkeypatch.setattr(media, "_windows_endpoint", lambda: endpoint)
    assert "Volume readback: 0%" in media.media_controller_handler({"action": "volume_set", "volume": 0})
    assert levels == [0.0]


def test_windows_failure_is_not_success(monkeypatch):
    monkeypatch.setattr(media, "_OS", "Windows")
    def fail():
        raise RuntimeError("private backend details")
    monkeypatch.setattr(media, "_windows_endpoint", fail)
    result = media.media_volume_set(60)
    assert "failed or is uncertain" in result and "private" not in result


def test_readback_mismatch_is_not_success(monkeypatch):
    monkeypatch.setattr(media, "_OS", "Windows")
    monkeypatch.setattr(media, "_windows_endpoint", lambda: SimpleNamespace(
        SetMasterVolumeLevelScalar=lambda *a: None, GetMasterVolumeLevelScalar=lambda: .2))
    assert "not verified" in media.media_volume_set(60)


def test_mac_command_checked_and_bounded(monkeypatch):
    monkeypatch.setattr(media, "_OS", "Darwin")
    calls = []
    monkeypatch.setattr(media.subprocess, "run", lambda *a, **k: calls.append((a, k)))
    assert "not verified" in media.media_volume_set(0)
    assert calls[0][1]["check"] is True and calls[0][1]["timeout"] == 5
    def fail(*a, **kw):
        raise subprocess.CalledProcessError(1, a)
    monkeypatch.setattr(media.subprocess, "run", fail)
    assert "failed or is uncertain" in media.media_volume_set(50)


def test_linux_absolute_volume_explicitly_unsupported(monkeypatch):
    monkeypatch.setattr(media, "_OS", "Linux")
    monkeypatch.setattr(media.subprocess, "run", lambda *a, **kw: pytest.fail("executed"))
    assert "unsupported" in media.media_volume_set(50)


def test_mute_is_not_secret_toggle(monkeypatch):
    keys = []
    monkeypatch.setattr(media, "_PYAUTOGUI", True)
    monkeypatch.setattr(media, "pyautogui", SimpleNamespace(press=keys.append), raising=False)
    assert "unavailable" in media.media_mute()
    assert "unavailable" in media.media_unmute()
    assert not keys
    assert "not verified" in media.media_controller_handler({"action": "toggle_mute"})
    assert keys == ["volumemute"]


def test_media_key_headless_and_exception(monkeypatch):
    monkeypatch.setattr(media, "_PYAUTOGUI", False)
    assert "unavailable" in media.media_controller_handler({"action": "volume_up"})
    monkeypatch.setattr(media, "_PYAUTOGUI", True)
    def fail(*a):
        raise RuntimeError("keyboard disconnected")
    monkeypatch.setattr(media, "pyautogui", SimpleNamespace(press=fail), raising=False)
    assert "uncertain" in media.media_next()


@pytest.fixture
def minimal_workspace(monkeypatch):
    preset = {"name": "isolated", "title": "ISOLATED", "run_audit": True, "dnd": True}
    monkeypatch.setattr(workspace, "_load_presets", lambda: {"isolated": preset})
    monkeypatch.setattr(workspace, "_match_preset", lambda *a: preset)
    # Trap a regression to the unsupported DND call.
    monkeypatch.setitem(sys.modules, 'ultron.actions.android_bridge', SimpleNamespace(
        android_bridge=lambda *a: pytest.fail("unsupported ADB operation")))
    return preset


def test_workspace_calls_actual_audit_signature(minimal_workspace, monkeypatch):
    calls = []
    monkeypatch.setitem(sys.modules, 'ultron.actions.network_auditor', SimpleNamespace(
        audit_security_posture=lambda: calls.append(1) or "FAKE AUDIT"))
    text = workspace.orchestrate_workspace("isolated")
    assert calls == [1] and "FAKE AUDIT" in text
    assert "Android DND: unsupported" in text
    assert "fully materialized" not in text


def test_workspace_audit_failure_is_not_healthy(minimal_workspace, monkeypatch):
    def fail():
        raise RuntimeError("offline")
    monkeypatch.setitem(sys.modules, 'ultron.actions.network_auditor', SimpleNamespace(audit_security_posture=fail))
    assert "security posture not established" in workspace.orchestrate_workspace("isolated")


def test_workspace_preserves_media_failure(minimal_workspace, monkeypatch):
    monkeypatch.setattr(media, "media_volume_set", lambda level: "volume backend unavailable")
    minimal_workspace["run_audit"] = False
    assert "volume backend unavailable" in workspace.orchestrate_workspace("isolated", custom_volume=0)


def test_focus_reports_offline_and_no_dnd(monkeypatch):
    monkeypatch.setattr(iot, "_call_ha_service", lambda *a: False)
    monkeypatch.setitem(sys.modules, 'ultron.actions.android_bridge', SimpleNamespace(
        android_bridge=lambda *a: pytest.fail("unsupported DND call")))
    text = iot.execute_focus_mode()
    assert "no successful change confirmed" in text and "DND: unsupported" in text
    assert "Distractions eliminated" not in text


@pytest.mark.parametrize("scene", ["focus", "gaming", "study", "cinema", "lockdown", "studio"])
def test_workspace_lighting_offline_not_engaged(scene, monkeypatch):
    monkeypatch.setattr(iot, "_call_ha_service", lambda *a: False)
    assert "no successful change confirmed" in workspace._trigger_iot_lighting(scene)


@pytest.mark.parametrize("theme", ["cyan", "blackout"])
def test_theme_offline_has_no_simulated_success(theme, monkeypatch):
    monkeypatch.setattr(iot, "_call_ha_service", lambda *a: False)
    text = iot.set_room_theme(theme)
    assert "no successful change confirmed" in text
    assert "Simulation" not in text and "dominion active" not in text


def test_failed_iot_toggle_is_not_queued(monkeypatch):
    monkeypatch.setattr(iot, "_call_ha_service", lambda *a: False)
    assert "nothing queued" in iot.toggle_smart_device("light.fixture")


def test_legacy_iot_raw_helper_cannot_enable_implicit_workspace_effect(monkeypatch):
    monkeypatch.setattr(iot, "_call_ha_service", lambda *a: pytest.fail("legacy raw helper called"))
    assert "disabled" in workspace._trigger_iot_lighting("focus")
    assert "toggle disabled" in iot.toggle_smart_device("light.fixture")
