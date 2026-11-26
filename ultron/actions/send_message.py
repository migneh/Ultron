"""Preview and explicitly approve verified Telegram bot sends; never type blind."""

from __future__ import annotations

import unicodedata

from ultron.core import confirm
from ultron.core.messaging import (
    Outbox,
    TelegramTransport,
    database_path,
    recipient_id,
    send_approved,
)


def _transport() -> TelegramTransport:
    return TelegramTransport()


def _name(value: str) -> str:
    # Remote display names are not allowed to inject new preview fields or bidi controls.
    return "".join(
        char.encode("unicode_escape").decode("ascii")
        if unicodedata.category(char).startswith("C")
        else char
        for char in value
    )


def _summary(record: dict) -> str:
    result = (
        f"Message ID: {record['id']}\nState: {record['state']}\n"
        f"Platform: Telegram bot\nFrom bot: {_name(record['sender_name'])} (ID {record['sender_id']})\n"
        f"To: {_name(record['recipient_name'])} (chat ID {record['recipient_id']}, {record['recipient_type']})"
    )
    if record["receipt"]:
        result += f"\nReceipt: {record['receipt']} — Telegram accepted it; delivered/read status is unknown."
    if record["error"]:
        result += f"\nNote: {record['error']}"
    if record["state"] in {"sending", "outcome_unknown"}:
        result += "\nDo not retry automatically. Check Telegram manually; a send may already have occurred."
    return result


def _preview(record: dict) -> str:
    warning = (
        "\nWARNING: This targets a group/channel, not a private conversation."
        if record["recipient_type"] != "private"
        else ""
    )
    return (
        _summary(record)
        + warning
        + f"\n\nExact text ({len(record['body'])} characters):\n{record['body']}"
        + "\n\nReview the numeric chat ID, sending bot and full text. Only the HUD CONFIRM button authorizes a new send."
    )


def _prepare(parameters: dict, store: Outbox, transport: TelegramTransport) -> dict:
    if "message_id" in parameters:
        if set(parameters) - {"action", "message_id"}:
            raise ValueError(
                "An existing message_id is immutable. Do not supply recipient/body overrides."
            )
        return store.get(parameters["message_id"])
    platform = parameters.get("platform", "")
    if not isinstance(platform, str) or platform.strip().casefold() not in {"telegram", "tg"}:
        raise ValueError(
            "Verified sending supports Telegram bots only. Blind desktop messaging is disabled; no keystrokes or sends were performed."
        )
    receiver = recipient_id(parameters.get("receiver", ""))
    body = parameters.get("message_text", "")
    if not isinstance(body, str) or not body.strip() or "\x00" in body:
        raise ValueError("message_text must be non-empty text without NUL bytes.")
    try:
        size = len(body.encode("utf-16-le")) // 2
    except UnicodeEncodeError:
        raise ValueError("message_text contains invalid Unicode.") from None
    if size > 4000:
        raise ValueError(
            "message_text must fit within 4000 UTF-16 code units; automatic splitting is not allowed."
        )
    return store.prepare(transport.verify(receiver), body)


def send_message(parameters: dict, response=None, player=None, session_memory=None) -> str:
    try:
        if not isinstance(parameters, dict):
            raise ValueError("Message parameters must be an object.")
        action = parameters.get("action", "send")
        if not isinstance(action, str):
            raise ValueError("action must be text.")
        action = action.strip().lower()
        allowed = {
            "preview": {"action", "platform", "receiver", "message_text", "message_id"},
            "send": {"action", "platform", "receiver", "message_text", "message_id"},
            "status": {"action", "message_id"},
            "cancel": {"action", "message_id"},
            "list": {"action", "limit"},
        }
        if action not in allowed or set(parameters) - allowed[action]:
            raise ValueError(
                "Use preview/send/status/list/cancel and their documented fields. Tool parameters cannot grant approval."
            )
        store = Outbox(database_path())
        if action == "list":
            rows = store.list(parameters.get("limit", 20))
            return (
                "Outbox is empty."
                if not rows
                else "Recent outbox entries (bodies omitted):\n\n"
                + "\n\n".join(map(_summary, rows))
            )
        if action == "status":
            return _summary(store.get(parameters.get("message_id", "")))
        if action == "cancel":
            message_id = parameters.get("message_id", "")
            record = store.cancel(message_id)
            confirm.cancel_pending(f"message:{message_id}")
            return _summary(record) + "\nNo new send was performed."
        transport = _transport()
        record = _prepare(parameters, store, transport)
        if action == "preview":
            return _preview(record) + "\nPreview only; no new send was performed."
        if not store.wait_for_confirmation(record["id"], confirm.TIMEOUT_SECONDS):
            return (
                _summary(store.get(record["id"]))
                + "\nExisting/terminal attempt reused. No new send or confirmation was created."
            )
        record = store.get(record["id"])
        message_id = record["id"]
        result = confirm.request(
            key=f"message:{message_id}",
            title="Send Telegram message",
            detail=_preview(record),
            run=lambda: send_approved(store, message_id, transport),
            on_cancel=lambda reason: store.stop_waiting(message_id, reason),
        )
        return (
            result
            + f"\nMessage ID: {message_id}. No new send has been performed by this tool call. Use status after HUD approval."
        )
    except ValueError as error:
        return f"Message request rejected: {error}"
    except Exception:
        # Never echo HTTP exception strings containing bot-token URLs or content.
        return "Message operation failed safely. Check outbox status before retrying; no automatic resend will be attempted."


TOOL = {
    "name": "send_message",
    "description": (
        "Preview and request human approval for verified Telegram BOT messages to explicit numeric chat IDs. "
        "Actions: preview, send (default: requests a HUD confirmation, never approves), status, list, cancel. "
        "Use receiver/message_text/platform for a new entry or an immutable message_id for an existing entry. "
        "Preserve the user's exact requested text/language. Requires enabled Telegram bot settings or TELEGRAM_BOT_TOKEN. "
        "Sends as the displayed bot, not the user's personal account. No blind WhatsApp/Signal/Discord/Instagram/Messenger sending. "
        "Duplicate payloads are blocked for 24h after a sent receipt; in-flight/unknown attempts block retries indefinitely. "
        "Only sent with a receipt means Telegram accepted it; delivery/read status is unknown. Never retry unknown outcomes automatically."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["preview", "send", "status", "list", "cancel"],
                "description": "Default send requests HUD approval only",
            },
            "platform": {"type": "STRING", "description": "telegram or tg; new entries only"},
            "receiver": {
                "type": "STRING",
                "description": "Explicit numeric Telegram chat ID; no fuzzy contact names",
            },
            "message_text": {
                "type": "STRING",
                "description": "Exact text, max 4000 UTF-16 units; plain text only",
            },
            "message_id": {
                "type": "STRING",
                "description": "Full ID from preview/send/list; cannot be combined with body/recipient overrides",
            },
            "limit": {"type": "INTEGER", "description": "List at most 1–50 entries, default 20"},
        },
        "required": [],
    },
    "handler": send_message,
}
