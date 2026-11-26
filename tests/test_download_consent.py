"""Fake transport/host approvals, temporary files, no real network or user data."""
import contextlib
import hashlib
from types import SimpleNamespace

import pytest

from ultron.actions import file_controller as files
from ultron.core import confirm, downloads, undo
from ultron.core import operation_policy as policy
from ultron.core import web_research as web


@pytest.fixture
def rig(tmp_path, monkeypatch):
    state = SimpleNamespace(root=tmp_path, seen=[], opened=[], dns=[], closed=0, data=b"untrusted\x00bytes")
    monkeypatch.setattr(files, "_SAFE_ROOTS", [tmp_path])
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    monkeypatch.setattr(web, "addresses", lambda url: state.dns.append(url) or ["8.8.8.8"])
    @contextlib.contextmanager
    def opened(url, address, connect, read, **kwargs):
        state.opened.append(url)
        try:
            yield SimpleNamespace(status=200, headers={}, stream=lambda *a, **k: iter([state.data]))
        finally:
            state.closed += 1
    monkeypatch.setattr(web, "_open", opened)
    undo.clear()
    yield state
    undo.clear()


def preview(rig, monkeypatch):
    monkeypatch.setattr(confirm, "request", lambda **kw: rig.seen.append(kw) or "pending")
    assert files.download_file("https://example.com/file", str(rig.root)) == "pending"


def received(rig, monkeypatch):
    preview(rig, monkeypatch)
    assert rig.seen[0]["run"]() == "pending"
    assert len(rig.seen) == 2


def test_headless_no_dns_network_or_file(rig):
    result = files.download_file("https://example.com/file", str(rig.root))
    assert "have not done it" in result
    assert not rig.dns and not rig.opened and not list(rig.root.iterdir())


def test_two_distinct_approvals_and_separate_inverse(rig, monkeypatch):
    preview(rig, monkeypatch)
    assert not rig.dns
    assert rig.seen[0]["run"]() == "pending"
    assert rig.opened == ["https://example.com/file"] and rig.closed == 1
    assert not list(rig.root.iterdir()) and not undo.can_undo()
    assert hashlib.sha256(rig.data).hexdigest() in rig.seen[1]["detail"]
    assert str(rig.root / "file") in rig.seen[1]["detail"]
    assert "Downloaded:" in rig.seen[1]["run"]()
    assert (rig.root / "file").read_bytes() == rig.data
    assert undo.undo_last() == "pending"
    assert (rig.root / "file").exists()
    assert "callback returned" in rig.seen[2]["run"]()
    assert not (rig.root / "file").exists()
    assert "REJECTED" in rig.seen[0]["run"]()
    assert "REJECTED" in rig.seen[1]["run"]()
    assert len(rig.opened) == 1


@pytest.mark.parametrize("stage", [0, 1])
def test_denial_never_publishes(rig, monkeypatch, stage):
    if stage:
        received(rig, monkeypatch)
    else:
        preview(rig, monkeypatch)
    rig.seen[stage]["on_cancel"]("denied")
    assert "REJECTED" in rig.seen[stage]["run"]()
    assert not list(rig.root.iterdir()) and not undo.can_undo()
    assert len(rig.opened) == stage


@pytest.mark.parametrize("stage", [0, 1])
def test_expiry_never_publishes(rig, monkeypatch, stage):
    if stage:
        received(rig, monkeypatch)
    else:
        preview(rig, monkeypatch)
    monkeypatch.setattr(policy.time, "monotonic", lambda: float("inf"))
    assert "EXPIRED" in rig.seen[stage]["run"]()
    assert not list(rig.root.iterdir()) and not undo.can_undo()


@pytest.mark.parametrize("stage", [0, 1])
def test_target_collision_after_preview_refused(rig, monkeypatch, stage):
    if stage:
        received(rig, monkeypatch)
    else:
        preview(rig, monkeypatch)
    target = rig.root / "file"
    target.write_text("competitor")
    result = rig.seen[stage]["run"]()
    assert "Downloaded:" not in result
    assert target.read_text() == "competitor" and not undo.can_undo()
    assert len(rig.opened) == stage


@pytest.mark.parametrize("stage", [0, 1])
def test_revoked_roots_stop_fetch_or_save(rig, monkeypatch, stage):
    if stage:
        received(rig, monkeypatch)
    else:
        preview(rig, monkeypatch)
    monkeypatch.setattr(files, "_SAFE_ROOTS", [])
    assert "Downloaded:" not in rig.seen[stage]["run"]()
    assert not list(rig.root.iterdir()) and len(rig.opened) == stage


@pytest.mark.parametrize("stage", [0, 1])
def test_replaced_parent_refuses(rig, monkeypatch, stage):
    parent = rig.root / "folder"
    parent.mkdir()
    rig.root = parent
    if stage:
        received(rig, monkeypatch)
    else:
        preview(rig, monkeypatch)
    parent.rename(parent.with_name("old"))
    parent.mkdir()
    assert "Downloaded:" not in rig.seen[stage]["run"]()
    assert not list(parent.iterdir()) and len(rig.opened) == stage


def test_parent_change_during_network_discards_receipt(rig, monkeypatch):
    parent = rig.root / "folder"
    parent.mkdir()
    rig.root = parent
    def receive(url):
        parent.rename(parent.with_name("old"))
        parent.mkdir()
        return downloads.Payload(b"bytes", url, "now")
    monkeypatch.setattr(downloads, "receive", receive)
    preview(rig, monkeypatch)
    assert "parent changed" in rig.seen[0]["run"]()
    assert len(rig.seen) == 1 and not list(parent.iterdir())


def test_raw_receive_worker_publish_and_legacy_inverse_no_grant(rig):
    with pytest.raises(PermissionError):
        downloads.receive("https://example.com/file")
    with pytest.raises(PermissionError):
        downloads._receive("https://example.com/file", web.Budget(1))
    with pytest.raises(PermissionError):
        downloads.publish(rig.root / "file", b"data", lambda _: True)
    with pytest.raises(PermissionError):
        files._undo_create(rig.root / "file")()
    assert not rig.opened and not list(rig.root.iterdir())


def test_wrong_bytes_cannot_use_publish_approval(rig, monkeypatch):
    received(rig, monkeypatch)
    real = downloads.publish
    def altered(target, data, allowed, **kwargs):
        return real(target, b"different", allowed, **kwargs)
    monkeypatch.setattr(downloads, "publish", altered)
    assert "failed" in rig.seen[1]["run"]()
    assert not list(rig.root.iterdir()) and not undo.can_undo()


def test_wrong_target_cannot_use_publish_approval(rig, monkeypatch):
    received(rig, monkeypatch)
    real = downloads.publish
    monkeypatch.setattr(downloads, "publish", lambda target, data, allowed, **kw: real(target.with_name("other"), data, allowed, **kw))
    assert "failed" in rig.seen[1]["run"]()
    assert not list(rig.root.iterdir())


def test_raw_download_inverse_no_grant(rig, monkeypatch):
    received(rig, monkeypatch)
    rig.seen[1]["run"]()
    with pytest.raises(PermissionError):
        undo._stack[-1].undo()
    assert (rig.root / "file").exists()


def test_inverse_replaced_same_bytes_refused(rig, monkeypatch):
    received(rig, monkeypatch)
    rig.seen[1]["run"]()
    target = rig.root / "file"
    replacement = rig.root / "replacement"
    replacement.write_bytes(rig.data)
    replacement.replace(target)
    undo.undo_last()
    assert "Could not undo" in rig.seen[2]["run"]()
    assert target.read_bytes() == rig.data


def test_changed_redirect_receipt_refused(rig, monkeypatch):
    preview(rig, monkeypatch)
    monkeypatch.setattr(downloads, "receive", lambda _: downloads.Payload(b"data", "https://other.example/file", "now"))
    assert "Invalid or redirected receipt" in rig.seen[0]["run"]()
    assert len(rig.seen) == 1 and not list(rig.root.iterdir())


def test_id_aware_confirmation_handoff_and_stale_fetch_click(rig):
    import threading
    shown, hidden = [], []
    ready = threading.Event()
    def show(title, detail, request_id):
        shown.append((title, request_id))
        if len(shown) == 2:
            ready.set()
    confirm.bind(lambda *a: None, lambda: None, show_with_id=show, hide_with_id=hidden.append)
    assert "CONFIRMATION_PENDING" in files.download_file("https://example.com/file", str(rig.root))
    fetch_id = shown[0][1]
    confirm.resolve(True, fetch_id)
    assert ready.wait(3)
    save_id = shown[1][1]
    assert save_id != fetch_id and not list(rig.root.iterdir())
    confirm.resolve(True, fetch_id)  # stale click cannot approve the new save
    assert confirm.pending_title() == "Save these exact received download bytes"
    confirm.resolve(False, save_id)
    assert not confirm.pending_title() and not list(rig.root.iterdir())
    assert hidden == [fetch_id, save_id] and len(rig.opened) == 1


def test_fetch_grant_cannot_publish(rig):
    plan = policy.prepare("download.fetch", ("public_network",), {})
    token = policy._active_grant.set(policy._Grant(plan))
    try:
        policy.consume(plan)
        with pytest.raises(PermissionError):
            downloads.publish(rig.root / "file", b"data", lambda _: True, plan=plan)
    finally:
        policy._active_grant.reset(token)
    assert not list(rig.root.iterdir())


def test_inverse_parent_replaced_refused(rig, monkeypatch):
    parent = rig.root / "folder"
    parent.mkdir()
    rig.root = parent
    received(rig, monkeypatch)
    rig.seen[1]["run"]()
    undo.undo_last()
    parent.rename(parent.with_name("old"))
    parent.mkdir()
    (parent.with_name("old") / "file").rename(parent / "file")
    assert "Could not undo" in rig.seen[2]["run"]()
    assert (parent / "file").read_bytes() == rig.data
