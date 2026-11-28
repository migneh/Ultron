"""No real messages: fake transport, temporary outbox and simulated HUD clicks."""

import ast
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from ultron.actions import send_message as action
from ultron.core import confirm as cf
from ultron.core import messaging as msg
from ultron.core.action_loader import ActionRegistry, _validate


class FakeTransport:
    def __init__(self):
        self.lookups = []
        self.sends = []
        self.outcome = msg.Outcome("sent", receipt="telegram:123:55")

    def verify(self, receiver):
        self.lookups.append(receiver)
        return {
            "sender_id": "777",
            "sender_name": "Ultron bot",
            "recipient_id": receiver,
            "recipient_name": "Test recipient",
            "recipient_type": "private",
        }

    def send(self, record):
        self.sends.append(dict(record))
        return self.outcome


@pytest.fixture
def flow(tmp_path, monkeypatch):
    monkeypatch.setattr(msg.requests, "post", lambda *a, **k: pytest.fail("Real HTTP forbidden"))
    for attr in (
        "_pending",
        "_show_cb",
        "_hide_cb",
        "_log_cb",
        "_show_with_id_cb",
        "_hide_with_id_cb",
    ):
        monkeypatch.setattr(cf, attr, None)
    shown, logs = [], []
    finished = threading.Event()

    def log(text):
        logs.append(text)
        if text.startswith("SYS: Confirmed"):
            finished.set()

    cf.bind(
        None, None, log, show_with_id=lambda *args: shown.append(args), hide_with_id=lambda _: None
    )
    path = tmp_path / "outbox.sqlite3"
    transport = FakeTransport()
    monkeypatch.setattr(action, "database_path", lambda: path)
    monkeypatch.setattr(action, "_transport", lambda: transport)
    return SimpleNamespace(
        store=msg.Outbox(path), transport=transport, shown=shown, logs=logs, finished=finished
    )


def args(**kwargs):
    return {"platform": "telegram", "receiver": "123", "message_text": "Hello", **kwargs}


def approve(flow):
    flow.finished.clear()
    cf.resolve(True, flow.shown[-1][2])
    assert flow.finished.wait(3), "Mock send callback did not complete"


def test_preview_is_persistent_but_never_sends(flow):
    output = action.send_message(
        args(action="preview", message_text="مرحبا <b>plain text</b>\nline 2")
    )
    assert "Exact text" in output and "مرحبا <b>plain text</b>\nline 2" in output
    assert "777" in output and "123" in output
    record = flow.store.list()[0]
    assert msg.Outbox(flow.store.path).get(record["id"])["state"] == "draft"
    assert not flow.shown and not flow.transport.sends


def test_default_send_requests_approval_and_preserves_immutable_payload(flow):
    parameters = args()
    output = action.send_message(parameters)
    record = flow.store.list()[0]
    assert "CONFIRMATION_PENDING" in output
    assert record["state"] == "awaiting_confirmation"
    assert not flow.transport.sends
    parameters["receiver"] = "999"
    parameters["message_text"] = "mutated"
    approve(flow)
    assert flow.transport.sends[0]["body"] == "Hello"
    assert flow.transport.sends[0]["recipient_id"] == "123"
    final = flow.store.get(record["id"])
    assert final["state"] == "sent"
    assert final["receipt"] == "telegram:123:55"
    assert "Hello" not in "\n".join(flow.logs)


def test_full_preview_is_not_truncated_to_old_300_character_limit(flow):
    text = "start " + "x" * 3500 + " END-OF-MESSAGE"
    action.send_message(args(message_text=text))
    assert text in flow.shown[-1][1]
    assert "END-OF-MESSAGE" in flow.shown[-1][1]


def test_cancel_button_blocks_send(flow):
    action.send_message(args())
    cf.resolve(False, flow.shown[-1][2])
    assert flow.store.list()[0]["state"] == "cancelled"
    assert not flow.transport.sends


def test_cancel_action_invalidates_queued_callback(flow):
    action.send_message(args())
    record = flow.store.list()[0]
    token = flow.shown[-1][2]
    assert "cancelled" in action.send_message({"action": "cancel", "message_id": record["id"]})
    cf.resolve(True, token)
    assert not flow.transport.sends


def test_duplicate_calls_reuse_attempt_and_only_one_send_occurs(flow):
    action.send_message(args())
    first = flow.store.list()[0]["id"]
    assert "No new send" in action.send_message(args())
    assert len(flow.shown) == 1
    approve(flow)
    assert "sent" in action.send_message(args())
    assert len(flow.transport.sends) == 1
    assert len(flow.store.list()) == 1
    assert flow.store.list()[0]["id"] == first


def test_unknown_outcome_blocks_automatic_retry(flow):
    flow.transport.outcome = msg.Outcome("outcome_unknown", "Check manually")
    action.send_message(args())
    approve(flow)
    assert "outcome_unknown" in action.send_message(args())
    assert len(flow.transport.sends) == 1
    assert len(flow.shown) == 1


def test_definitive_failure_requires_a_new_human_approval(flow):
    flow.transport.outcome = msg.Outcome("failed", "Telegram refused")
    action.send_message(args())
    approve(flow)
    flow.transport.outcome = msg.Outcome("sent", receipt="telegram:123:56")
    assert "CONFIRMATION_PENDING" in action.send_message(args())
    assert len(flow.store.list()) == 2
    assert len(flow.transport.sends) == 1
    approve(flow)
    assert len(flow.transport.sends) == 2


def test_headless_send_returns_to_draft_without_sending(flow):
    cf.bind(None, None)
    assert "cannot confirm" in action.send_message(args())
    assert flow.store.list()[0]["state"] == "draft"
    assert not flow.transport.sends


def test_another_confirmation_cannot_be_replaced(flow):
    cf.request("other", "Other action", "detail", lambda: "must not run")
    other_token = flow.shown[-1][2]
    assert "CONFIRMATION_BUSY" in action.send_message(args())
    assert cf.is_current(other_token)
    assert len(flow.shown) == 1
    assert flow.store.list()[0]["state"] == "draft"


def test_outbox_expiry_blocks_late_delivery(flow, monkeypatch):
    action.send_message(args())
    record = flow.store.list()[0]
    monkeypatch.setattr(msg.time, "time", lambda: record["expires"] + 1)
    assert flow.store.get(record["id"])["state"] == "expired"
    approve(flow)
    assert not flow.transport.sends


def test_immutable_id_cannot_override_body_or_recipient(flow):
    action.send_message(args(action="preview"))
    record = flow.store.list()[0]
    output = action.send_message({"message_id": record["id"], "message_text": "changed"})
    assert "immutable" in output
    assert not flow.shown and not flow.transport.sends


def test_in_flight_cannot_be_cancelled_or_silently_retried(flow, monkeypatch):
    started, release = threading.Event(), threading.Event()
    original = flow.transport.send

    def blocked(record):
        started.set()
        assert release.wait(3)
        return original(record)

    monkeypatch.setattr(flow.transport, "send", blocked)
    action.send_message(args())
    record = flow.store.list()[0]
    cf.resolve(True, flow.shown[-1][2])
    assert started.wait(3)
    try:
        assert "Cannot recall" in action.send_message(
            {"action": "cancel", "message_id": record["id"]}
        )
        assert "sending" in action.send_message(args())
    finally:
        release.set()
    assert flow.finished.wait(3)
    assert len(flow.transport.sends) == 1


def test_concurrent_prepares_and_claims_are_atomic(flow):
    identity = flow.transport.verify("123")
    with ThreadPoolExecutor(max_workers=4) as pool:
        records = list(pool.map(lambda _: flow.store.prepare(identity, "same"), range(8)))
    assert len({r["id"] for r in records}) == 1
    message_id = records[0]["id"]
    assert flow.store.wait_for_confirmation(message_id, 90)
    with ThreadPoolExecutor(max_workers=4) as pool:
        claimed = list(pool.map(lambda _: flow.store.claim(message_id), range(8)))
    assert sum(record is not None for record in claimed) == 1
    assert msg.Outbox(flow.store.path).prepare(identity, "same")["state"] == "sending"


def test_sent_dedup_window_and_uncertain_state_survive_restart(flow, monkeypatch):
    identity = flow.transport.verify("123")
    record = flow.store.prepare(identity, "same")
    flow.store.wait_for_confirmation(record["id"], 90)
    flow.store.claim(record["id"])
    flow.store.finish(record["id"], msg.Outcome("sent", receipt="test"))
    now = msg.time.time()
    monkeypatch.setattr(msg.time, "time", lambda: now + msg.DEDUPE_SECONDS + 10)
    new = msg.Outbox(flow.store.path).prepare(identity, "same")
    assert new["id"] != record["id"]
    flow.store.wait_for_confirmation(new["id"], 90)
    flow.store.claim(new["id"])
    flow.store.finish(new["id"], msg.Outcome("outcome_unknown"))
    monkeypatch.setattr(msg.time, "time", lambda: now + 30 * msg.DEDUPE_SECONDS)
    assert flow.store.prepare(identity, "same")["id"] == new["id"]


@pytest.mark.parametrize(
    "parameters",
    [
        args(platform="whatsapp"),
        args(platform="unknown telegram thing"),
        args(receiver="Alice"),
        args(receiver="@username"),
        args(receiver=True),
        args(message_text=""),
        args(message_text=False),
        args(message_text="x" * 4001),
        args(message_text="\x00"),
        args(message_text="😀" * 2001),
        args(confirmed=True),
        args(approved=True),
        {"action": "status", "message_id": "../bad"},
        {"action": "list", "limit": 0},
        {"action": []},
        {"action": "unknown"},
    ],
)
def test_bad_requests_cannot_send_or_display_approval(flow, parameters):
    assert "rejected" in action.send_message(parameters)
    assert not flow.shown and not flow.transport.sends


def test_group_preview_and_identity_control_character_escaping(flow):
    identity = flow.transport.verify("-100123")
    identity.update(recipient_type="supergroup", recipient_name="Group\nFAKE FIELD\u202e")
    record = flow.store.prepare(identity, "Hello")
    preview = action.send_message({"action": "preview", "message_id": record["id"]})
    assert "WARNING" in preview and "-100123" in preview
    assert "Group\\nFAKE FIELD\\u202e" in preview


def test_list_omits_bodies_and_registry_dispatch_works(flow):
    declaration = _validate(action, "send_message.py")
    assert declaration.valid
    registry = ActionRegistry({declaration.name: declaration}, logger=lambda _: None)
    registry.run("send_message", args(action="preview", message_text="BODY-PRIVATE"))
    output = registry.run("send_message", {"action": "list"})
    assert "BODY-PRIVATE" not in output
    assert "draft" in output


def test_confirmation_ui_uses_plain_complete_text_and_request_ids():
    # Source contract only: PyQt6 is unavailable in this headless environment.
    tree = ast.parse(Path("ultron/ui.py").read_text(encoding="utf-8"))
    classes = {node.name: node for node in tree.body if isinstance(node, ast.ClassDef)}
    banner = ast.unparse(classes["ConfirmBanner"])
    assert "setPlainText(detail)" in banner
    assert "PlainText" in banner
    wrapper = classes["UltronUI"]
    show = next(
        node
        for node in wrapper.body
        if isinstance(node, ast.FunctionDef) and node.name == "show_confirm"
    )
    code = ast.unparse(show)
    assert "request_id" in code
    assert "[:300]" not in code


def test_active_outbox_limit_rejects_without_sending(flow, monkeypatch):
    monkeypatch.setattr(msg, "MAX_PENDING", 1)
    action.send_message(args(action="preview", message_text="one"))
    assert "At most" in action.send_message(args(action="preview", message_text="two"))
    assert len(flow.store.list()) == 1
    assert not flow.transport.sends


def test_unexpected_transport_error_is_uncertain_not_retried(flow, monkeypatch):
    def broken(_):
        raise RuntimeError("secret-bearing URL must not escape")

    monkeypatch.setattr(flow.transport, "send", broken)
    action.send_message(args())
    approve(flow)
    output = action.send_message(args())
    assert "outcome_unknown" in output
    assert "secret-bearing URL" not in output
    assert "secret-bearing URL" not in "\n".join(flow.logs)
    assert len(flow.shown) == 1
