"""Token expiry must apply to HTTP, downloads, TTS and WebSocket entrypoints."""
import time
import pytest
pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect
from dashboard import server


@pytest.fixture
def dashboard(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(server, "_local_ip", lambda: "127.0.0.1")
    instance = server.DashboardServer()
    instance._tokens["expired"] = time.time() - 1
    instance._tokens["valid"] = time.time() + 60
    return instance


@pytest.mark.parametrize("path", ["/api/tts", "/uploads/test.txt"])
def test_expired_http_token_rejected(dashboard, path):
    with TestClient(dashboard.app) as client:
        assert client.get(path, params={"token": "expired"}).status_code == 401


@pytest.mark.parametrize("path", ["/ws", "/ws/phone-audio"])
def test_expired_websocket_token_rejected(dashboard, path):
    with TestClient(dashboard.app) as client:
        with pytest.raises(WebSocketDisconnect) as error:
            with client.websocket_connect(path + "?token=expired"):
                pass
        assert error.value.code == 4001


def test_valid_download_token_still_works(dashboard):
    (dashboard._uploads_dir / "test.txt").write_text("hello")
    with TestClient(dashboard.app) as client:
        response = client.get("/uploads/test.txt?token=valid")
        assert response.status_code == 200
        assert response.text == "hello"


def test_connected_websocket_cannot_submit_after_expiry(dashboard):
    with TestClient(dashboard.app) as client:
        with client.websocket_connect("/ws?token=valid") as ws:
            dashboard._tokens["valid"] = time.time() - 1
            ws.send_json({"type": "command", "text": "must not run"})
            with pytest.raises(WebSocketDisconnect):
                ws.receive_json()
        assert dashboard._command_queue.empty()
