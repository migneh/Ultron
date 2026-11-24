"""Telegram API contracts with synthetic responses only. No HTTP is permitted."""

import pytest

from core import messaging as msg
from memory import config_manager

TOKEN = "123456:" + "A" * 30  # synthetic test value, not a credential


class Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def json(self):
        return self.data


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    monkeypatch.setattr(msg.requests, "post", lambda *a, **k: pytest.fail("Real HTTP forbidden"))


@pytest.fixture
def api(monkeypatch):
    calls = []
    results = {
        "getMe": Response(
            {"ok": True, "result": {"id": 777, "is_bot": True, "first_name": "Ultron bot"}}
        ),
        "getChat": Response(
            {"ok": True, "result": {"id": 123, "type": "private", "first_name": "Alice"}}
        ),
        "sendMessage": Response(
            {"ok": True, "result": {"message_id": 55, "chat": {"id": 123}, "text": "Hello"}}
        ),
    }

    def fake(token, method, payload):
        calls.append((token, method, payload))
        value = results[method]
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(msg, "_token", lambda: TOKEN)
    monkeypatch.setattr(msg, "_api", fake)
    return calls, results, msg.TelegramTransport()


def record(transport):
    return {**transport.verify("123"), "body": "Hello"}


def test_success_requires_matching_receipt_and_sends_plain_text_once(api):
    calls, _, transport = api
    result = transport.send(record(transport))
    assert result.state == "sent"
    assert result.receipt == "telegram:123:55"
    sends = [payload for _, method, payload in calls if method == "sendMessage"]
    assert sends == [{"chat_id": "123", "text": "Hello"}]
    assert [method for _, method, _ in calls].count("getMe") == 2


@pytest.mark.parametrize(
    "response",
    [
        Response({"ok": True, "result": {"message_id": 55, "chat": {"id": 999}, "text": "Hello"}}),
        Response(
            {"ok": True, "result": {"message_id": 55, "chat": {"id": 123}, "text": "Changed"}}
        ),
        Response(
            {"ok": True, "result": {"message_id": True, "chat": {"id": 123}, "text": "Hello"}}
        ),
        Response({"ok": True, "result": {"chat": {"id": 123}, "text": "Hello"}}),
        Response({"ok": False}, status=500),
        Response({"ok": False}, status=302),
        Response([]),
        Response({"ok": True, "result": None}),
    ],
)
def test_unmatched_or_uncertain_response_never_reports_sent_or_retries(api, response):
    calls, results, transport = api
    planned = record(transport)
    results["sendMessage"] = response
    assert transport.send(planned).state == "outcome_unknown"
    assert len([1 for _, method, _ in calls if method == "sendMessage"]) == 1


@pytest.mark.parametrize("code", [400, 401, 403, 404, 429])
def test_explicit_rejection_is_failed_without_fallback_send(api, code):
    calls, results, transport = api
    planned = record(transport)
    results["sendMessage"] = Response(
        {"ok": False, "description": "PRIVATE SERVER DATA"}, status=code
    )
    outcome = transport.send(planned)
    assert outcome.state == "failed"
    assert "PRIVATE SERVER DATA" not in outcome.detail
    assert len([1 for _, method, _ in calls if method == "sendMessage"]) == 1


def test_send_timeout_is_unknown_and_credential_url_is_never_echoed(api):
    calls, results, transport = api
    planned = record(transport)
    results["sendMessage"] = msg.requests.Timeout(
        f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    )
    outcome = transport.send(planned)
    assert outcome.state == "outcome_unknown"
    assert TOKEN not in outcome.detail
    assert len([1 for _, method, _ in calls if method == "sendMessage"]) == 1


def test_changed_sending_account_requires_new_preview(api):
    calls, results, transport = api
    planned = record(transport)
    results["getMe"] = Response(
        {"ok": True, "result": {"id": 888, "is_bot": True, "first_name": "Other bot"}}
    )
    assert transport.send(planned).state == "failed"
    assert not any(method == "sendMessage" for _, method, _ in calls)


def test_metadata_timeout_is_pre_send_failure_without_credentials_in_error(api):
    _, results, transport = api
    results["getChat"] = msg.requests.Timeout(f"bot{TOKEN}/getChat")
    with pytest.raises(msg.VerificationError) as error:
        transport.verify("123")
    assert TOKEN not in str(error.value)


@pytest.mark.parametrize(
    "chat",
    [
        {"id": 999, "type": "private"},
        {"id": True, "type": "private"},
        {"id": 123, "type": "unknown"},
    ],
)
def test_recipient_verification_must_match_exact_chat(api, chat):
    calls, results, transport = api
    results["getChat"] = Response({"ok": True, "result": chat})
    with pytest.raises(msg.VerificationError):
        transport.verify("123")
    assert not any(method == "sendMessage" for _, method, _ in calls)


def test_http_wrapper_has_bounded_timeouts_and_disables_redirects(monkeypatch):
    captured = []
    monkeypatch.setattr(
        msg.requests, "post", lambda *a, **k: captured.append((a, k)) or Response({})
    )
    msg._api(TOKEN, "getMe", {})
    assert len(captured) == 1
    assert captured[0][1]["timeout"] == (5, 15)
    assert captured[0][1]["allow_redirects"] is False


def test_credentials_are_configured_not_model_supplied(monkeypatch):
    monkeypatch.delenv("TELEGRAM_BOT_TOKEN", raising=False)
    monkeypatch.setattr(
        config_manager, "get_telegram_config", lambda: {"token": TOKEN, "enabled": False}
    )
    with pytest.raises(msg.VerificationError, match="Enable"):
        msg._token()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    assert msg._token() == TOKEN
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "not/a/valid/token")
    with pytest.raises(msg.VerificationError, match="valid Telegram"):
        msg._token()
