"""Legacy sentry disabled: no capture, lock, disclosure or autonomous effects.

Historical snapshots are left untouched, not automatically deleted or uploaded.
A future adapter requires independent consent, retention and lifecycle controls.
"""
from __future__ import annotations

from pathlib import Path

_sentry_active = False
_sentry_state = "DISABLED"
_detection_count = 0

def _get_telegram_creds() -> tuple[str, str]:
    return "", ""


def _send_telegram_photo(photo_path: Path, caption: str) -> bool:
    return False


def _lock_workstation() -> bool:
    return False


def _broadcast_dashboard_breach(reason: str, photo_name: str) -> None:
    return None


def _speak_alert(player=None) -> None:
    return None


# ── Surveillance Worker ─────────────────────────────────────────────────────

def _sentry_worker(player=None):
    return "Surveillance worker disabled; no capture or dispatch attempted."


# ── Action Interface ─────────────────────────────────────────────────────────

def activate_sentry(player=None) -> str:
    return "Sentry activation disabled pending scoped capture, retention, dispatch and lifecycle design; no surveillance started."


def deactivate_sentry() -> str:
    return "Sentry disabled; no owned worker running in this adapter. Historical files unchanged."


def sentry_status() -> str:
    return "Sentry disabled; no camera, input monitor, snapshot storage, alerts or workstation lock started by this adapter."


def sentry_gallery() -> str:
    return "Gallery disclosure disabled; historical files not read, deleted or transmitted."


def instant_lockdown(player=None) -> str:
    return "Bundled lockdown disabled; no camera, lock, voice or alert action attempted."


# ── Unified Dispatcher ───────────────────────────────────────────────────────

def sentry_protocol(
    parameters: dict = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    params = {} if parameters is None else parameters
    if not isinstance(params, dict) or not isinstance(params.get("action", "status"), str):
        return "Invalid sentry request; no action attempted."
    action = params.get("action", "status").lower().strip()

    try:
        if action in ("activate", "arm", "start", "enable"):
            return activate_sentry(player)
        elif action in ("deactivate", "disarm", "stop", "disable"):
            return deactivate_sentry()
        elif action in ("lockdown", "lock", "lock_pc", "intruder_lockdown"):
            return instant_lockdown(player)
        elif action in ("status", "check", "info"):
            return sentry_status()
        elif action in ("gallery", "snapshots", "logs", "breaches"):
            return sentry_gallery()
        else:
            return f"Unknown Sentry action: '{action}'. Available: activate, deactivate, lockdown, status, gallery."
    except Exception as e:
        return f"Sentry Protocol error ({action}): {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "sentry_protocol",
    "description": "Surveillance, lockdown, snapshots, Telegram/dashboard dispatch and voice effects disabled pending scoped consent, retention and lifecycle design. status/deactivate are local metadata only; gallery disclosure disabled.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "status | deactivate; activate/lockdown/gallery are disabled"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": sentry_protocol,
}
