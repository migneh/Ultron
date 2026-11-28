"""Optional adapter contracts with fake OAuth, credential store and HTTP only."""
import json
import sys
from types import SimpleNamespace

import pytest

from ultron.core import google_workspace as google
from ultron.core import productivity_setup as setup
from ultron.core import productivity_store as store


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "database_path", lambda: tmp_path / "productivity.sqlite3")
    import requests
    monkeypatch.setattr(requests, "request", lambda *a, **k: pytest.fail("Live HTTP forbidden"))
    monkeypatch.setattr(requests, "post", lambda *a, **k: pytest.fail("Live HTTP forbidden"))
    monkeypatch.setattr(requests.sessions.Session, "request", lambda *a, **k: pytest.fail("Live session HTTP forbidden"))
    return tmp_path


def config(**overrides):
    value = {"drive": True, "calendar": True, "file_ids": ["selected-id"],
             "calendar_id": "primary", "model_context_allowed": True}
    value.update(overrides)
    store.set_setting("workspace", value)
    return value


def test_status_is_local_and_does_not_open_keyring(workspace, monkeypatch):
    monkeypatch.setattr(google, "backend", lambda: pytest.fail("No secret lookup for status"))
    result = google.workspace("status")
    assert not result["configured"] and not result["network_used"]


@pytest.mark.parametrize("kind", ["unconfigured", "no_model_consent", "not_allowed", "traversal", "disabled"])
def test_no_implicit_account_or_resource_access(workspace, monkeypatch, kind):
    monkeypatch.setattr(google, "_request", lambda *a, **k: pytest.fail("No HTTP admitted"))
    file_id = "selected-id"
    if kind != "unconfigured":
        config(model_context_allowed=kind != "no_model_consent", drive=kind != "disabled")
    if kind == "not_allowed":
        file_id = "other-id"
    elif kind == "traversal":
        file_id = "../selected-id"
    with pytest.raises(ValueError):
        google.workspace("drive_text", file_id=file_id)


def test_read_only_drive_text_and_provenance(workspace, monkeypatch):
    config()
    calls = []

    def request(_config, method, url, **kwargs):
        calls.append((method, url, kwargs))
        if url.endswith("/export"):
            return "Hello مرحبا".encode()
        return json.dumps({"id": "selected-id", "mimeType": "application/vnd.google-apps.document", "version": "2"}).encode()

    monkeypatch.setattr(google, "_request", request)
    result = google.workspace("drive_text", file_id="selected-id")
    assert result["text"] == "Hello مرحبا" and not result["cached"]
    assert result["metadata"]["version"] == "2"
    assert all(method == "GET" for method, _, _ in calls)


@pytest.mark.parametrize("window", [("2026-11-23T10:00:00", "2026-11-23T11:00:00"),
                                   ("2026-11-23T11:00:00Z", "2026-11-23T10:00:00Z"),
                                   ("2026-01-01T00:00:00Z", "2026-12-01T00:00:00Z")])
def test_invalid_calendar_windows_do_not_fetch(workspace, monkeypatch, window):
    config()
    monkeypatch.setattr(google, "_request", lambda *a, **k: pytest.fail("No request"))
    with pytest.raises(ValueError):
        google.workspace("agenda", time_min=window[0], time_max=window[1])


def test_agenda_truncation_and_freebusy_error_are_truthful(workspace, monkeypatch):
    config()
    window = {"time_min": "2026-11-23T10:00:00+01:00", "time_max": "2026-11-23T11:00:00+01:00"}
    monkeypatch.setattr(google, "_request", lambda *a, **k: json.dumps({"items": [{"id": "event"}], "nextPageToken": "more"}).encode())
    assert google.workspace("agenda", **window)["truncated"]
    monkeypatch.setattr(google, "_request", lambda *a, **k: json.dumps({"calendars": {"primary": {"errors": [{"reason": "notFound"}]}}}).encode())
    assert not google.workspace("availability", **window)["availability_known"]
    monkeypatch.setattr(google, "_request", lambda *a, **k: b'{}')
    assert not google.workspace("availability", **window)["availability_known"]


@pytest.mark.parametrize("method,url", [("POST", "https://www.googleapis.com/drive/v3/files/selected-id"),
                                        ("DELETE", "https://www.googleapis.com/calendar/v3/calendars/primary/events"),
                                        ("GET", "https://attacker.example/"),
                                        ("POST", "https://www.googleapis.com/gmail/v1/users/me/messages/send")])
def test_transport_refuses_writes_and_arbitrary_urls(workspace, monkeypatch, method, url):
    monkeypatch.setattr(google, "_credentials", lambda _: pytest.fail("No secret access"))
    with pytest.raises(ValueError):
        google._request({}, method, url)


def test_fixed_host_http_no_redirects_no_retry_and_size_bound(workspace, monkeypatch):
    import requests
    monkeypatch.setattr(google, "_credentials", lambda _: SimpleNamespace(token="fake-token"))
    calls = []

    class Response:
        status_code = 200

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def iter_content(self, size):
            assert size == 8192
            yield b"ab"
            yield b"cd"

    def request(method, url, **kwargs):
        calls.append((method, url, kwargs))
        return Response()

    monkeypatch.setattr(requests, "request", request)
    with pytest.raises(ValueError):
        google._request({}, "GET", "https://www.googleapis.com/drive/v3/files/selected-id", maximum=3)
    assert len(calls) == 1
    assert calls[0][2]["allow_redirects"] is False
    assert calls[0][2]["timeout"] == (5, 10)


def test_plaintext_keyring_is_rejected(workspace, monkeypatch):
    class Plaintext:
        priority = 10
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_keyring=lambda: Plaintext()))
    with pytest.raises(ValueError):
        google.backend()


def test_only_supported_os_keyring_is_selected(workspace, monkeypatch):
    secure = type("Secure", (), {"__module__": "keyring.backends.SecretService", "priority": 1})()
    monkeypatch.setitem(sys.modules, "keyring", SimpleNamespace(get_keyring=lambda: secure))
    assert google.backend() is secure


@pytest.mark.parametrize("partial", [False, True])
def test_host_oauth_uses_pkce_loopback_and_no_tool_supplied_tokens(workspace, monkeypatch, partial):
    pytest.importorskip("google_auth_oauthlib.flow")
    from google_auth_oauthlib.flow import InstalledAppFlow
    secret = workspace / "client.json"
    secret.write_text(json.dumps({"installed": {"token_uri": google.TOKEN_URI, "auth_uri": "https://accounts.google.com/o/oauth2/auth"}}))
    stored, calls = [], []
    monkeypatch.setattr(google, "backend", lambda: SimpleNamespace(set_password=lambda *args: stored.append(args)))
    credentials = SimpleNamespace(granted_scopes=[google.EVENT_SCOPE] if partial else [google.EVENT_SCOPE, google.BUSY_SCOPE],
                                  to_json=lambda: '{"fake":"test-only"}')

    class Flow:
        def run_local_server(self, **kwargs):
            calls.append(kwargs)
            return credentials

    def factory(client, scopes, **kwargs):
        assert kwargs["autogenerate_code_verifier"] is True
        assert set(scopes) == {google.EVENT_SCOPE, google.BUSY_SCOPE}
        return Flow()

    monkeypatch.setattr(InstalledAppFlow, "from_client_config", factory)
    if partial:
        with pytest.raises(ValueError):
            setup.connect(str(secret), calendar=True, allow_model_context=True)
        assert not stored and not store.setting("workspace", {})
        return
    result = setup.connect(str(secret), calendar=True, allow_model_context=True)
    assert result["configured"] and len(stored) == 1
    assert calls[0]["host"] == "127.0.0.1" and calls[0]["port"] == 0
    assert store.setting("workspace")["model_context_allowed"]


def test_disconnect_local_only_removes_secret_without_network(workspace, monkeypatch):
    config()
    deleted = []
    monkeypatch.setattr(google, "backend", lambda: SimpleNamespace(
        get_password=lambda *a: '{"refresh_token":"fake"}', delete_password=lambda *a: deleted.append(a)))
    result = setup.disconnect(local_only=True)
    assert result["local_credentials_removed"] and not result["remote_revocation_confirmed"]
    assert deleted and not store.setting("workspace")


@pytest.mark.parametrize("change", ["endpoint", "broad_scope"])
def test_credential_endpoint_and_scope_mismatch_fails_before_refresh(workspace, monkeypatch, change):
    pytest.importorskip("google.oauth2.credentials")
    configuration = config()
    data = {"token_uri": google.TOKEN_URI, "scopes": google.scopes(configuration)}
    if change == "endpoint":
        data["token_uri"] = "https://attacker.example/token"
    else:
        data["scopes"] = ["https://www.googleapis.com/auth/drive"]
    monkeypatch.setattr(google, "backend", lambda: SimpleNamespace(get_password=lambda *a: json.dumps(data)))
    with pytest.raises(ValueError):
        google._credentials(configuration)
