"""No actual network, physical device, capture, lock, voice or dispatch calls."""
import json
from types import SimpleNamespace

import pytest

from ultron.actions import iot_overlord as iot
from ultron.actions import sentry_protocol as sentry
from ultron.actions import workspace_matrix as workspace
from ultron.core import confirm
from ultron.core import iot_lighting as lights
from ultron.core import operation_policy as policy


@pytest.fixture
def rig(tmp_path, monkeypatch):
    import requests
    state = SimpleNamespace(config={"home_assistant_url": "https://192.168.1.2:8123",
                                   "home_assistant_token": "private-test-token-123",
                                   "home_assistant_light_entities": ["light.desk"]},
                            seen={}, calls=[], code=200, error=False, closed=0)
    path = tmp_path / "config.json"
    monkeypatch.setattr(lights, "CONFIG", path)
    def save():
        path.write_text(json.dumps(state.config), encoding="utf-8")
    state.save = save
    save()
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            state.closed += 1
        @property
        def status_code(self):
            return state.code
        @property
        def content(self):
            pytest.fail("response body read")
    class Session:
        trust_env = True
        def __enter__(self):
            return self
        def __exit__(self, *args):
            state.closed += 1
        def post(self, url, **kw):
            assert self.trust_env is False
            state.calls.append((url, kw))
            if state.error:
                raise RuntimeError("private-provider-error")
            return Response()
    monkeypatch.setattr(requests, "Session", Session)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    return state


def preview(rig, monkeypatch, settings=None):
    monkeypatch.setattr(confirm, "request", lambda **kw: rig.seen.update(kw) or "pending")
    return lights.request("light.desk", "turn_on", settings)


def test_headless_no_network(rig):
    assert "have not done it" in lights.request("light.desk", "turn_on")
    assert not rig.calls


def test_exact_single_approved_request_no_body_no_redirect_no_replay(rig, monkeypatch):
    settings = {"rgb_color": [0, 220, 255], "brightness": 210}
    assert preview(rig, monkeypatch, settings) == "pending"
    assert not rig.calls
    assert "private-test-token" not in rig.seen["detail"]
    settings["rgb_color"][0] = 255
    assert "device state not verified" in rig.seen["run"]()
    url, options = rig.calls[0]
    assert url == "https://192.168.1.2:8123/api/services/light/turn_on"
    assert options["json"] == {"entity_id": "light.desk", "rgb_color": [0, 220, 255], "brightness": 210}
    assert options["timeout"] == (3, 4) and options["stream"] and options["verify"]
    assert options["allow_redirects"] is False and rig.closed == 2
    assert "REJECTED" in rig.seen["run"]() and len(rig.calls) == 1


def test_denial_no_network(rig, monkeypatch):
    preview(rig, monkeypatch)
    rig.seen["on_cancel"]("cancelled")
    assert "REJECTED" in rig.seen["run"]() and not rig.calls


def test_expired_approval_no_network(rig, monkeypatch):
    preview(rig, monkeypatch)
    monkeypatch.setattr(policy.time, "monotonic", lambda: float("inf"))
    assert "EXPIRED" in rig.seen["run"]() and not rig.calls


@pytest.mark.parametrize("key,value", [("home_assistant_token", "changed-private-token-123"),
    ("home_assistant_url", "https://192.168.1.3"), ("home_assistant_light_entities", ["light.other"])])
def test_configuration_changed_discards_approval(rig, monkeypatch, key, value):
    preview(rig, monkeypatch)
    rig.config[key] = value
    rig.save()
    assert "nothing sent" in rig.seen["run"]() and not rig.calls


@pytest.mark.parametrize("url", ["http://192.168.1.2:8123", "https://homeassistant.local", "https://127.0.0.1",
    "https://169.254.169.254", "https://8.8.8.8", "https://[::1]", "https://u:p@192.168.1.2",
    "https://192.168.1.2/path", "https://192.168.1.2?x=1", "https://192.168.1.2#x", "https://192.168.1.2:0"])
def test_unsafe_endpoint_no_approval(rig, monkeypatch, url):
    rig.config["home_assistant_url"] = url
    rig.save()
    assert "unavailable or invalid" in preview(rig, monkeypatch)
    assert not rig.seen and not rig.calls


@pytest.mark.parametrize("entity,service,settings", [
    (None, "turn_on", {}), ("light.all", "turn_on", {}), ("switch.heater", "turn_on", {}),
    ("light.other", "turn_on", {}), ("light.desk", "toggle", {}),
    ("light.desk", "turn_off", {"brightness": 2}), ("light.desk", "turn_on", {"brightness": True}),
    ("light.desk", "turn_on", {"rgb_color": [0, 0, 256]}),
    ("light.desk", "turn_on", {"transition": 60}), ("light.desk", "turn_on", {"brightness": 0})])
def test_invalid_payload_no_approval(rig, monkeypatch, entity, service, settings):
    monkeypatch.setattr(confirm, "request", lambda **kw: pytest.fail("approval offered"))
    assert "unavailable or invalid" in lights.request(entity, service, settings)
    assert not rig.calls


@pytest.mark.parametrize("code", [302, 307, 401, 429, 500])
def test_unaccepted_response_no_retry(rig, monkeypatch, code):
    rig.code = code
    preview(rig, monkeypatch)
    assert "did not report acceptance" in rig.seen["run"]()
    assert len(rig.calls) == 1 and rig.closed == 2


def test_timeout_unknown_sanitized_no_retry(rig, monkeypatch):
    rig.error = True
    preview(rig, monkeypatch)
    result = rig.seen["run"]()
    assert "outcome unknown" in result and "private" not in result
    assert len(rig.calls) == 1


def test_direct_sink_without_grant(rig):
    plan = policy.prepare("iot.single_light", ("light.desk",), {})
    with pytest.raises(PermissionError):
        lights._execute(plan)
    assert not rig.calls


def test_raw_helper_and_implicit_workspace_never_submit(rig):
    assert iot._call_ha_service("light", "turn_on", {}) is False
    assert "disabled" in workspace._trigger_iot_lighting("focus")
    assert not rig.calls


def test_turn_off_alias_is_not_toggle_or_on(rig, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: rig.seen.update(kw) or "pending")
    assert iot.iot_overlord({"action": "turn_off", "entity_id": "light.desk", "state": "on"}) == "pending"
    assert "accepted" in rig.seen["run"]()
    assert rig.calls[0][0].endswith("/turn_off")
    assert rig.calls[0][1]["json"] == {"entity_id": "light.desk"}


def test_sentry_effect_helpers_fail_closed_and_no_gallery_read(rig, tmp_path):
    assert "disabled" in sentry.activate_sentry()
    assert "disabled" in sentry._sentry_worker()
    assert "disabled" in sentry.instant_lockdown()
    assert sentry._send_telegram_photo(tmp_path / "missing.jpg", "private") is False
    assert sentry._lock_workstation() is False
    assert sentry._speak_alert() is None
    assert sentry._broadcast_dashboard_breach("private", "x") is None
    assert "disabled" in sentry.sentry_gallery()
    assert not rig.calls


@pytest.mark.parametrize("action", ["lockdown", "lock", "red_alert", "discover", "scan", "status"])
def test_iot_disabled_or_status_no_network(rig, action):
    assert isinstance(iot.iot_overlord({"action": action}), str)
    assert not rig.calls


def test_macro_lockdown_chain_removed(rig, monkeypatch):
    from ultron.actions import macro_protocol as macro
    monkeypatch.setattr(macro, "_lock_screen", lambda: pytest.fail("lock called"))
    monkeypatch.setattr(macro, "_minimize_all_windows", lambda: pytest.fail("GUI effect"))
    assert "disabled" in macro._execute_lockdown()
    assert not rig.calls


@pytest.mark.parametrize("key,value", [
    ("home_assistant_light_entities", []), ("home_assistant_light_entities", ["light.all"]),
    ("home_assistant_light_entities", ["light.desk", "light.desk"]),
    ("home_assistant_light_entities", ["switch.boiler"]), ("home_assistant_token", ""),
    ("home_assistant_token", "private-token\r\ninjected"),
])
def test_invalid_operator_provisioning_no_request(rig, monkeypatch, key, value):
    rig.config[key] = value
    rig.save()
    assert "unavailable or invalid" in preview(rig, monkeypatch)
    assert not rig.calls and not rig.seen


def test_missing_configuration_no_request(rig, monkeypatch):
    lights.CONFIG.unlink()
    assert "unavailable or invalid" in preview(rig, monkeypatch)
    assert not rig.calls


def test_explicit_entity_required_even_for_theme(rig, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: pytest.fail("approval offered"))
    assert "nothing queued" in iot.set_room_theme("cyan")
    assert not rig.calls
