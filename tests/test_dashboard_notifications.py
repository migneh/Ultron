"""Private notifications use fake sockets only; no real devices or network."""
import asyncio
import time

import pytest
from fastapi.testclient import TestClient

from ultron.core import confirm
from ultron.core import operation_policy as policy
from ultron.dashboard import server


class Socket:
    def __init__(self, error=False):
        self.sent = []
        self.error = error

    async def send_json(self, message):
        self.sent.append(message)
        if self.error:
            raise OSError("secret-bearing failure")


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(server, "_local_ip", lambda: "127.0.0.1")
    d = server.DashboardServer()
    monkeypatch.setattr(server, "_GLOBAL_DASHBOARD", d)
    d._tokens["valid"] = time.time() + 100
    socket = Socket()
    d._clients.add(socket)
    d._notification_clients["connection-a"] = (socket, "valid")
    # asyncio.run retains the approval ContextVar in this fake owner loop.
    monkeypatch.setattr(d, "_notification_call", asyncio.run)
    return d, socket


def approve(operation_hud):
    confirm.resolve(True, operation_hud.shown[-1][2])
    assert operation_hud.finished.wait(2)


def test_direct_action_requests_exact_preview_before_effect(dashboard, operation_hud):
    from ultron.actions.omni_telepathy import telepathy_broadcast
    d, socket = dashboard
    text = 'مرحبا\nDestinations: spoofed'
    result = telepathy_broadcast(text)
    assert "PENDING" in result
    assert socket.sent == []
    assert "connection-a" in operation_hud.shown[-1][1]
    assert "\\nDestinations" in operation_hud.shown[-1][1]
    approve(operation_hud)
    assert socket.sent == [{"type": "sys", "text": "[TELEPATHY] " + text}]
    assert d._history == []
    assert "Display/read status unknown" in " ".join(operation_hud.logs)
    assert "مرحبا" not in " ".join(operation_hud.logs)


@pytest.mark.parametrize("change", ["disconnect", "new_connection", "expired_token", "revoked_token"])
def test_destinations_must_still_match(dashboard, operation_hud, change):
    d, socket = dashboard
    assert "PENDING" in d.request_notification("private")
    if change == "disconnect":
        d._clients.clear()
    elif change == "new_connection":
        extra = Socket()
        d._clients.add(extra)
        d._notification_clients["new"] = (extra, "valid")
    elif change == "expired_token":
        d._tokens["valid"] = time.time() - 1
    else:
        d._tokens.clear()
    approve(operation_hud)
    assert socket.sent == []
    assert "REJECTED" in " ".join(operation_hud.logs)


def test_direct_sink_and_legacy_broadcast_cannot_bypass(dashboard):
    d, socket = dashboard
    current = policy.prepare('ultron.dashboard.notification', ("connection-a",), {"text": "private"})
    assert "REJECTED" in asyncio.run(d._deliver_notification(current))
    with pytest.raises(ValueError, match="request_notification"):
        asyncio.run(d.broadcast({"type": "sys", "text": "[TELEPATHY] private"}))
    assert socket.sent == [] and d._history == []


def test_failed_write_is_unknown_not_automatically_retried(dashboard, operation_hud):
    d, socket = dashboard
    socket.error = True
    d.request_notification("private")
    callback = confirm._pending.run
    approve(operation_hud)
    assert len(socket.sent) == 1
    assert "OUTCOME_UNKNOWN" in " ".join(operation_hud.logs)
    assert "secret-bearing" not in " ".join(operation_hud.logs)
    assert "REJECTED" in callback()
    assert len(socket.sent) == 1


@pytest.mark.parametrize("text", ["", "   ", None, {}, "x" * 4001])
def test_invalid_payload_never_opens_confirmation(dashboard, operation_hud, text):
    d, socket = dashboard
    assert "rejected" in d.request_notification(text)
    assert not operation_hud.shown and not socket.sent


def test_no_active_destinations_never_opens_confirmation(dashboard, operation_hud):
    d, _ = dashboard
    d._clients.clear()
    assert "Nothing sent" in d.request_notification("private")
    assert not operation_hud.shown


def test_real_dashboard_loop_and_connection_registration(tmp_path, monkeypatch, operation_hud):
    monkeypatch.setattr(server, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(server, "_local_ip", lambda: "127.0.0.1")
    d = server.DashboardServer()
    monkeypatch.setattr(server, "_GLOBAL_DASHBOARD", d)
    d._tokens["valid"] = time.time() + 100
    with TestClient(d.app) as client:
        with client.websocket_connect("/ws?token=valid") as ws:
            # The real thread-to-event-loop bridge propagates the approval grant.
            assert "PENDING" in d.request_notification("private")
            approve(operation_hud)
            assert ws.receive_json() == {"type": "sys", "text": "[TELEPATHY] private"}
            assert not d._history
        assert not d._notification_clients


def test_missing_dashboard_loop_fails_closed(tmp_path, monkeypatch, operation_hud):
    monkeypatch.setattr(server, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(server, "_local_ip", lambda: "127.0.0.1")
    d = server.DashboardServer()
    assert "unavailable" in d.request_notification("private")
    assert not operation_hud.shown


def test_change_during_write_is_reported_partial(dashboard, operation_hud):
    d, first = dashboard
    second = Socket()
    d._clients.add(second)
    d._notification_clients["connection-b"] = (second, "valid")

    async def revoke_after_write(message):
        first.sent.append(message)
        d._tokens.clear()

    first.send_json = revoke_after_write
    d.request_notification("private")
    approve(operation_hud)
    assert len(first.sent) == 1 and not second.sent
    assert "PARTIAL" in " ".join(operation_hud.logs)


def test_timeout_has_unknown_outcome_and_cancels_future(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(server, "_local_ip", lambda: "127.0.0.1")
    d = server.DashboardServer()
    from concurrent.futures import Future

    class FutureTimeout(Future):
        def result(self, timeout):
            assert timeout == 5
            raise TimeoutError()

    future = FutureTimeout()
    d._notification_loop = type("Loop", (), {"is_running": lambda _: True})()

    def submit(coro, loop):
        coro.close()
        return future

    monkeypatch.setattr(asyncio, "run_coroutine_threadsafe", submit)
    current = policy.prepare('ultron.dashboard.notification', ("a",), {"text": "private"})
    assert "OUTCOME_UNKNOWN" in d._send_notification_plan(current)
    assert future.cancelled()
