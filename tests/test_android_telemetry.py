"""Selected-device telemetry without real ADB, native effects or model calls."""
import json
from types import SimpleNamespace

import pytest

from ultron.actions import android_bridge as android
from ultron.core import android_files, confirm
from ultron.core import android_telemetry as telemetry
from ultron.core import operation_policy as policy


@pytest.fixture
def device(monkeypatch):
    state = SimpleNamespace(snapshot={"serial": "SERIAL", "transport_id": "7", "binary": "/fake/adb", "binary_identity": ["id"]},
                            calls=[], probes=0, change_at=None, seen={}, fail=False,
                            outputs={"getprop": b"device property", "battery": b"level: 100\nscale: 200\nstatus: 2\n",
                                     "df": b"Filesystem 1K-blocks Used Available Use% Mounted on\n/dev/fuse 1000 400 600 40% /storage/emulated\n",
                                     "ip": b"inet 192.168.1.12/24 scope global wlan0"})
    def snapshot(serial):
        state.probes += 1
        if serial != "SERIAL":
            raise ValueError("not selected")
        if state.change_at is not None and state.probes >= state.change_at:
            state.snapshot["transport_id"] = "8"
        return dict(state.snapshot)
    monkeypatch.setattr(android, "_adb_snapshot", snapshot)
    def receive(cmd, output, expected, timeout, *, max_bytes):
        assert expected is None and 0 < timeout <= 5 and max_bytes == 65536
        state.calls.append(cmd)
        query = cmd[8]
        key = "battery" if query == "dumpsys" else query
        output.write(state.outputs[key])
        if state.fail:
            raise ValueError("private error")
        return "unused-checksum"
    monkeypatch.setattr(android_files, "_receive", receive)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    return state


def preview(device, monkeypatch, fields=None):
    monkeypatch.setattr(confirm, "request", lambda **kw: device.seen.update(kw) or "pending")
    assert android.get_device_info("SERIAL", fields) == "pending"
    return device.seen


def test_headless_telemetry_does_not_query(device):
    assert "have not done it" in android.get_device_info("SERIAL")
    assert not device.calls


def test_defaults_disclose_context_and_exclude_ip_storage(device, monkeypatch):
    seen = preview(device, monkeypatch)
    assert "configured model/UI/log" in seen["detail"]
    assert not device.calls
    result = json.loads(seen["run"]())
    assert result["state"] == "reported"
    assert set(result["fields"]) == set(telemetry.DEFAULT_FIELDS)
    assert "wifi_ip" not in result["fields"] and "storage" not in result["fields"]
    assert result["fields"]["battery"]["value"] == {"percent": 50.0, "charge_state": "charging"}
    assert all(cmd[:8] == ["/fake/adb", "-H", "127.0.0.1", "-P", "5037", "-t", "7", "shell"] for cmd in device.calls)
    assert "REJECTED" in seen["run"]()
    assert len(device.calls) == len(telemetry.DEFAULT_FIELDS)


def test_sensitive_fields_are_explicit_fixed_queries(device, monkeypatch):
    seen = preview(device, monkeypatch, ["wifi_ip", "storage"])
    result = json.loads(seen["run"]())
    assert result["fields"]["wifi_ip"]["value"] == "192.168.1.12"
    assert result["fields"]["storage"]["value"]["available_kib"] == 600
    assert len(device.calls) == 2


def test_field_list_mutation_cannot_escalate_approved_request(device, monkeypatch):
    fields = ["model"]
    seen = preview(device, monkeypatch, fields)
    fields.append("wifi_ip")
    result = json.loads(seen["run"]())
    assert set(result["fields"]) == {"model"}
    assert len(device.calls) == 1


def test_cancellation_no_queries(device, monkeypatch):
    seen = preview(device, monkeypatch)
    seen["on_cancel"]("cancelled")
    assert "REJECTED" in seen["run"]() and not device.calls


def test_device_changes_mid_request_discard_all_data(device, monkeypatch):
    seen = preview(device, monkeypatch, ["model", "brand"])
    device.change_at = 3  # preview, first query, then changed second query probe
    result = json.loads(seen["run"]())
    assert result["state"] == "device_changed_results_discarded" and result["fields"] == {}
    assert len(device.calls) == 1


def test_change_after_last_query_discards_output(device, monkeypatch):
    seen = preview(device, monkeypatch, ["model"])
    device.change_at = 3
    result = json.loads(seen["run"]())
    assert result["fields"] == {} and "discarded" in result["state"]


def test_nonzero_or_timeout_does_not_parse_partial_stdout(device, monkeypatch):
    seen = preview(device, monkeypatch, ["model"])
    device.fail = True
    result = json.loads(seen["run"]())
    assert result["state"] == "unavailable"
    assert result["fields"]["model"] == {"state": "unavailable_or_failed"}
    assert "private" not in str(result)


@pytest.mark.parametrize("fields", [[], ["shell"], ["model", "model"], ["getprop;id"], "model", [True], [{}]])
def test_invalid_fields_no_probe(device, monkeypatch, fields):
    monkeypatch.setattr(android, "_adb_snapshot", lambda *a: pytest.fail("device probed"))
    assert "preview unavailable" in android.get_device_info("SERIAL", fields)
    assert not device.calls


@pytest.mark.parametrize("value", [b"", b"line one\nline two", b"a" * 201, b"secret\x00stuff", b"\xff"])
def test_malformed_properties_are_unavailable_not_raw_dump(device, monkeypatch, value):
    seen = preview(device, monkeypatch, ["model"])
    device.outputs["getprop"] = value
    assert json.loads(seen["run"]())["state"] == "unavailable"


@pytest.mark.parametrize("text", ["level: 1\nscale: 0", "level: 101\nscale: 100", "scale: 100", "level: 1"])
def test_invalid_battery_not_fabricated_zero(text):
    with pytest.raises(ValueError):
        telemetry._parse("battery", text)


def test_valid_zero_battery_is_preserved():
    assert telemetry._parse("battery", "level: 0\nscale: 100\nstatus: 3")["percent"] == 0


def test_query_budget_skips_remaining_fields(device, monkeypatch):
    seen = preview(device, monkeypatch, ["model", "brand"])
    clock = iter([0, 0, 21, 21])
    monkeypatch.setattr(telemetry, "_clock", lambda: next(clock))
    result = json.loads(seen["run"]())
    assert result["state"] == "unavailable"
    assert all(field["state"] == "deadline_not_queried" for field in result["fields"].values())
    assert not device.calls


def test_battery_alias_selects_only_battery(device, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: device.seen.update(kw) or "pending")
    assert android.android_bridge({"action": "battery", "serial": "SERIAL"}) == "pending"
    result = json.loads(device.seen["run"]())
    assert set(result["fields"]) == {"battery"}


def test_telemetry_direct_sink_cannot_bypass_approval(device):
    plan = policy.prepare("android.telemetry.selected", ("android:SERIAL",), {})
    with pytest.raises(PermissionError):
        telemetry._execute(plan)
    assert not device.calls


def test_missing_serial_never_defaults_to_connected_phone(device):
    assert "preview unavailable" in android.get_device_info()
    assert not device.calls


def test_partial_result_does_not_claim_complete(device, monkeypatch):
    seen = preview(device, monkeypatch, ["model", "battery"])
    device.outputs["battery"] = b"not battery data"
    assert json.loads(seen["run"]())["state"] == "partial"
