"""Persistent, consent-gated message outbox and verified Telegram bot transport.

No desktop keystrokes, automatic send retries, parse-mode fallback or credentials
in receipts. Unknown network outcomes remain blocked from automatic resending.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import re
import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

import requests

DEDUPE_SECONDS = 24 * 60 * 60
MAX_PENDING = 100


def database_path() -> Path:
    return Path.home() / ".ultron" / "message_outbox.sqlite3"


def identifier(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{32}", value) is None:
        raise ValueError("Use the full message_id returned by preview/list.")
    return value


def recipient_id(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"-?[1-9][0-9]{0,18}", value.strip()) is None:
        raise ValueError(
            "Telegram requires an explicit numeric chat ID, not a contact name or username."
        )
    return str(int(value.strip()))


@contextlib.contextmanager
def connection(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        if os.name != "nt":
            path.chmod(0o600)
        db.execute("""CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY, fingerprint TEXT NOT NULL, platform TEXT NOT NULL,
            sender_id TEXT NOT NULL, sender_name TEXT NOT NULL,
            recipient_id TEXT NOT NULL, recipient_name TEXT NOT NULL, recipient_type TEXT NOT NULL,
            body TEXT NOT NULL, state TEXT NOT NULL, receipt TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '', created REAL NOT NULL, updated REAL NOT NULL,
            expires REAL NOT NULL DEFAULT 0
        )""")
        db.execute("CREATE INDEX IF NOT EXISTS idx_messages_fingerprint ON messages(fingerprint)")
        db.execute(
            "UPDATE messages SET state='expired',error='Confirmation expired',updated=? WHERE state='awaiting_confirmation' AND expires<?",
            (time.time(), time.time()),
        )
        db.commit()
        yield db
    finally:
        db.close()


class Outbox:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    def get(self, message_id: str) -> dict:
        identifier(message_id)
        with connection(self.path) as db:
            row = db.execute("SELECT * FROM messages WHERE id=?", (message_id,)).fetchone()
        if row is None:
            raise ValueError("Message not found. List the outbox to get its ID.")
        return dict(row)

    def prepare(self, identity: dict, body: str) -> dict:
        fingerprint = hashlib.sha256(
            json.dumps(
                ["telegram", identity["sender_id"], identity["recipient_id"], body],
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        now = time.time()
        with connection(self.path) as db, db:
            db.execute("BEGIN IMMEDIATE")
            duplicate = db.execute(
                """SELECT * FROM messages WHERE fingerprint=? AND (
                state IN ('draft','awaiting_confirmation','sending','outcome_unknown') OR
                (state='sent' AND updated>=?)) ORDER BY created DESC LIMIT 1""",
                (fingerprint, now - DEDUPE_SECONDS),
            ).fetchone()
            if duplicate:
                return dict(duplicate)
            active = db.execute(
                "SELECT count(*) FROM messages WHERE state IN ('draft','awaiting_confirmation','sending')"
            ).fetchone()[0]
            if active >= MAX_PENDING:
                raise ValueError(
                    f"At most {MAX_PENDING} active outbox entries; cancel unused drafts first."
                )
            message_id = uuid4().hex
            db.execute(
                """INSERT INTO messages
                (id,fingerprint,platform,sender_id,sender_name,recipient_id,recipient_name,recipient_type,body,state,created,updated)
                VALUES (?,?,'telegram',?,?,?,?,?,?,'draft',?,?)""",
                (
                    message_id,
                    fingerprint,
                    identity["sender_id"],
                    identity["sender_name"],
                    identity["recipient_id"],
                    identity["recipient_name"],
                    identity["recipient_type"],
                    body,
                    now,
                    now,
                ),
            )
        return self.get(message_id)

    def list(self, limit: int = 20) -> list[dict]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 50:
            raise ValueError("limit must be an integer from 1 to 50.")
        with connection(self.path) as db:
            rows = db.execute(
                "SELECT * FROM messages ORDER BY created DESC, id LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def wait_for_confirmation(self, message_id: str, timeout: float) -> bool:
        identifier(message_id)
        with connection(self.path) as db, db:
            result = db.execute(
                "UPDATE messages SET state='awaiting_confirmation',expires=?,updated=?,error='' WHERE id=? AND state='draft'",
                (time.time() + timeout, time.time(), message_id),
            )
            return bool(result.rowcount == 1)

    def stop_waiting(self, message_id: str, reason: str):
        state = {"expired": "expired", "cancelled": "cancelled"}.get(reason, "draft")
        with connection(self.path) as db, db:
            db.execute(
                "UPDATE messages SET state=?,error=?,updated=? WHERE id=? AND state='awaiting_confirmation'",
                (state, "Confirmation " + reason, time.time(), identifier(message_id)),
            )

    def cancel(self, message_id: str) -> dict:
        identifier(message_id)
        with connection(self.path) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM messages WHERE id=?", (message_id,)).fetchone()
            if row is None:
                raise ValueError("Message not found.")
            if row[0] in {"sending", "outcome_unknown", "sent"}:
                raise ValueError(
                    "Cannot recall an in-flight, uncertain or already sent message. Check status; do not automatically retry."
                )
            db.execute(
                "UPDATE messages SET state='cancelled',updated=? WHERE id=? AND state IN ('draft','awaiting_confirmation')",
                (time.time(), message_id),
            )
        return self.get(message_id)

    def claim(self, message_id: str) -> dict | None:
        with connection(self.path) as db, db:
            result = db.execute(
                "UPDATE messages SET state='sending',updated=? WHERE id=? AND state='awaiting_confirmation' AND expires>=?",
                (time.time(), identifier(message_id), time.time()),
            )
            if result.rowcount != 1:
                return None
        return self.get(message_id)

    def finish(self, message_id: str, outcome: Outcome):
        if outcome.state not in {"sent", "failed", "outcome_unknown"}:
            raise ValueError("Invalid message outcome.")
        with connection(self.path) as db, db:
            db.execute(
                "UPDATE messages SET state=?,receipt=?,error=?,updated=? WHERE id=? AND state='sending'",
                (
                    outcome.state,
                    outcome.receipt,
                    outcome.detail,
                    time.time(),
                    identifier(message_id),
                ),
            )


@dataclass(frozen=True)
class Outcome:
    state: str
    detail: str = ""
    receipt: str = ""


class VerificationError(ValueError):
    """Definitive failure before any outbound send was attempted."""


def _token() -> str:
    from ultron.memory.config_manager import get_telegram_config

    configured = get_telegram_config()
    override = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not override and not configured["enabled"]:
        raise VerificationError(
            "Enable Telegram in Ultron settings or configure TELEGRAM_BOT_TOKEN."
        )
    token = override or configured["token"]
    if re.fullmatch(r"[0-9]{5,20}:[A-Za-z0-9_-]{20,200}", token) is None:
        raise VerificationError(
            "A valid Telegram bot token is required; do not put it in tool arguments."
        )
    return token


def _api(token: str, method: str, payload: dict):
    # No redirects or retry adapter: sending is a single attempt, never fallback
    # Markdown/HTML followed by another send with the same text.
    return requests.post(
        f"https://api.telegram.org/bot{token}/{method}",
        json=payload,
        timeout=(5, 15),
        allow_redirects=False,
    )


def _metadata(token: str, method: str, payload: dict) -> dict:
    try:
        response = _api(token, method, payload)
        data = response.json()
        if (
            response.status_code != 200
            or data.get("ok") is not True
            or not isinstance(data.get("result"), dict)
        ):
            raise VerificationError(
                "Telegram identity lookup was refused. Check bot permissions and the numeric chat ID."
            )
        return dict(data["result"])
    except VerificationError:
        raise
    except Exception:
        # requests exceptions may contain the token-bearing URL; never echo them.
        raise VerificationError(
            "Telegram identity lookup failed. No message send was attempted."
        ) from None


def _numeric(value) -> str:
    if isinstance(value, bool) or not isinstance(value, int) or value == 0:
        raise VerificationError("Telegram returned an invalid identity.")
    return str(value)


def _display(entity: dict) -> str:
    return str(
        entity.get("title")
        or " ".join(str(entity.get(key) or "") for key in ("first_name", "last_name")).strip()
        or entity.get("username")
        or entity["id"]
    )[:200]


class TelegramTransport:
    def _verify(self, token: str, receiver: str) -> dict:
        bot = _metadata(token, "getMe", {})
        chat = _metadata(token, "getChat", {"chat_id": receiver})
        if bot.get("is_bot") is not True or _numeric(chat.get("id")) != receiver:
            raise VerificationError(
                "Telegram recipient verification did not match the requested chat."
            )
        kind = chat.get("type")
        if kind not in {"private", "group", "supergroup", "channel"}:
            raise VerificationError("Unsupported Telegram chat type.")
        return {
            "sender_id": _numeric(bot.get("id")),
            "sender_name": _display(bot),
            "recipient_id": receiver,
            "recipient_name": _display(chat),
            "recipient_type": kind,
        }

    def verify(self, receiver: str) -> dict:
        return self._verify(_token(), recipient_id(receiver))

    def send(self, record: dict) -> Outcome:
        try:
            token = _token()
            current = self._verify(token, record["recipient_id"])
            if (
                current["sender_id"] != record["sender_id"]
                or current["recipient_type"] != record["recipient_type"]
            ):
                return Outcome(
                    "failed", "Sender account or recipient type changed. Create a fresh preview."
                )
        except Exception:
            return Outcome(
                "failed",
                "Identity/credential recheck failed before sending. Create a fresh preview.",
            )
        try:
            response = _api(
                token, "sendMessage", {"chat_id": record["recipient_id"], "text": record["body"]}
            )
            data = response.json()
            if response.status_code in {400, 401, 403, 404, 429} and data.get("ok") is False:
                return Outcome(
                    "failed",
                    f"Telegram rejected the send (HTTP {response.status_code}). No automatic retry.",
                )
            result = data.get("result")
            if (
                response.status_code == 200
                and data.get("ok") is True
                and isinstance(result, dict)
                and isinstance(result.get("message_id"), int)
                and not isinstance(result["message_id"], bool)
                and result["message_id"] > 0
                and str(result.get("chat", {}).get("id")) == record["recipient_id"]
                and result.get("text") == record["body"]
            ):
                return Outcome(
                    "sent", receipt=f"telegram:{record['recipient_id']}:{result['message_id']}"
                )
        except Exception:
            pass
        return Outcome(
            "outcome_unknown",
            "The send may have reached Telegram, but no matching receipt was obtained. Check Telegram manually; automatic retry is blocked.",
        )


def send_approved(store: Outbox, message_id: str, transport: TelegramTransport) -> str:
    record = store.claim(message_id)
    if record is None:
        return f"Message {message_id}: not sent by this callback; no active unexpired approval."
    try:
        outcome = transport.send(record)
    except Exception:
        outcome = Outcome(
            "outcome_unknown",
            "Send interrupted; check the platform manually. Automatic retry is blocked.",
        )
    store.finish(message_id, outcome)
    return f"Message {message_id}: {outcome.state}." + (
        f" {outcome.detail}"
        if outcome.detail
        else " Telegram accepted the message; delivery/read status is not known."
    )
