"""Screenshot privacy/integrity tests; never connect ADB or capture a real screen."""
import hashlib
import io
import struct
import sys
import zlib
from types import SimpleNamespace

import pytest

from ultron.actions import android_bridge as android
from ultron.core import android_capture as capture
from ultron.core import android_files, confirm
from ultron.core import operation_policy as policy
from ultron.core import productivity_store as store


def chunk(kind, data):
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)


def png(width=1, height=1):
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"\x00\x00\x00\x00")) + chunk(b"IEND", b""))


@pytest.fixture
def screen(tmp_path, monkeypatch):
    root = tmp_path / "approved"
    root.mkdir()
    monkeypatch.setattr(store, "database_path", lambda: tmp_path / "settings.sqlite3")
    store.set_setting("document_roots", [str(root)])
    device = {"serial": "SERIAL", "transport_id": "7", "binary": "/fake/adb", "binary_identity": ["fake"]}
    state = SimpleNamespace(device=device, calls=[], data=png(), target=root / "screen.png", seen={})
    monkeypatch.setattr(android, "_adb_snapshot", lambda serial: dict(device) if serial == "SERIAL" else (_ for _ in ()).throw(ValueError("serial")))
    def receive(cmd, output, expected, timeout, *, max_bytes):
        assert expected is None and timeout == 15 and max_bytes == 16 * 1024 * 1024
        state.calls.append(cmd)
        output.write(state.data)
        return hashlib.sha256(state.data).hexdigest()
    monkeypatch.setattr(android_files, "_receive", receive)
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    return state


def preview(screen, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: screen.seen.update(kw) or "pending")
    return android.take_screenshot(str(screen.target), "SERIAL")


def test_headless_does_not_capture(screen):
    assert "have not done it" in android.take_screenshot(str(screen.target), "SERIAL")
    assert not screen.calls and not screen.target.exists()


def test_single_frame_approved_device_and_new_file(screen, monkeypatch):
    assert preview(screen, monkeypatch) == "pending"
    assert not screen.calls and not screen.target.exists()
    assert "WHEN EXECUTION STARTS" in screen.seen["detail"]
    result = screen.seen["run"]()
    assert "saved locally" in result and "not decoded" in result
    assert screen.target.read_bytes() == screen.data
    assert len(screen.calls) == 1
    assert screen.calls[0] == ["/fake/adb", "-H", "127.0.0.1", "-P", "5037", "-t", "7", "exec-out", "screencap", "-p"]
    assert "REJECTED" in screen.seen["run"]()
    assert len(screen.calls) == 1 and not list(screen.target.parent.glob("*.part"))


def test_deny_prevents_capture(screen, monkeypatch):
    preview(screen, monkeypatch)
    screen.seen["on_cancel"]("cancelled")
    assert "REJECTED" in screen.seen["run"]()
    assert not screen.calls


def test_destination_conflict_no_capture(screen, monkeypatch):
    preview(screen, monkeypatch)
    screen.target.write_bytes(b"existing")
    assert "conflict" in screen.seen["run"]()
    assert not screen.calls and screen.target.read_bytes() == b"existing"


def test_transport_change_prevents_capture(screen, monkeypatch):
    preview(screen, monkeypatch)
    screen.device["transport_id"] = "8"
    assert "changed" in screen.seen["run"]()
    assert not screen.calls


def test_revoked_root_prevents_capture(screen, monkeypatch):
    preview(screen, monkeypatch)
    store.set_setting("document_roots", [])
    assert "OUTCOME_UNKNOWN" in screen.seen["run"]()
    assert not screen.calls


@pytest.mark.parametrize("data", [b"not a PNG", png()[:-1], png() + b"trailing", png(20000, 20000)])
def test_invalid_png_not_published(screen, monkeypatch, data):
    preview(screen, monkeypatch)
    screen.data = data
    assert "OUTCOME_UNKNOWN" in screen.seen["run"]()
    assert not screen.target.exists() and not list(screen.target.parent.glob("*.part"))


def test_bad_crc_not_published(screen, monkeypatch):
    preview(screen, monkeypatch)
    screen.data = png()[:-5] + b"x" + png()[-4:]
    assert "OUTCOME_UNKNOWN" in screen.seen["run"]()
    assert not screen.target.exists()


def test_partial_receive_failure_cleans_output(screen, monkeypatch):
    preview(screen, monkeypatch)
    def fail(cmd, output, *a, **kw):
        output.write(b"partial")
        raise ValueError("timeout")
    monkeypatch.setattr(android_files, "_receive", fail)
    assert "OUTCOME_UNKNOWN" in screen.seen["run"]()
    assert not screen.target.exists() and not list(screen.target.parent.glob("*.part"))


def test_publication_race_never_replaces_other_file(screen, monkeypatch):
    preview(screen, monkeypatch)
    real_link = capture.os.link
    def race(src, dst):
        screen.target.write_bytes(b"other writer")
        return real_link(src, dst)
    monkeypatch.setattr(capture.os, "link", race)
    assert "OUTCOME_UNKNOWN" in screen.seen["run"]()
    assert screen.target.read_bytes() == b"other writer"


@pytest.mark.parametrize("destination", ["", "downloads", "/outside/screen.png", "relative.png"])
def test_invalid_destination_cannot_capture(screen, destination):
    assert "preview unavailable" in android.take_screenshot(destination, "SERIAL")
    assert not screen.calls


def test_invalid_or_missing_serial_no_capture(screen):
    assert "preview unavailable" in android.take_screenshot(str(screen.target))
    assert not screen.calls


def test_dispatch_passes_explicit_serial_and_destination(screen, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: screen.seen.update(kw) or "pending")
    assert android.android_bridge({"action": "screenshot", "serial": "SERIAL", "file_path": str(screen.target)}) == "pending"
    assert not screen.calls


def test_capture_sink_rejects_unapproved_plan(screen):
    plan = policy.prepare("android.capture.single_png", ("android:SERIAL",), {})
    with pytest.raises(PermissionError):
        capture._execute(plan)


def test_bounded_unknown_length_stream_success():
    output = io.BytesIO()
    digest = android_files._receive([sys.executable, "-c", "print('abc',end='')"], output, None, timeout=2, max_bytes=3)
    assert digest == hashlib.sha256(b"abc").hexdigest()


def test_bounded_unknown_length_stream_overflow():
    output = io.BytesIO()
    with pytest.raises(ValueError):
        android_files._receive([sys.executable, "-c", "print('abcdef',end='')"], output, None, timeout=2, max_bytes=3)
    assert len(output.getvalue()) <= 3


def test_animated_png_refused(screen, monkeypatch):
    preview(screen, monkeypatch)
    image = png()
    screen.data = image[:33] + chunk(b"acTL", struct.pack(">II", 2, 0)) + image[33:]
    assert "OUTCOME_UNKNOWN" in screen.seen["run"]()
    assert not screen.target.exists()
