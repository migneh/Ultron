"""Persistent reminder management through a SQLite registry and native OS jobs."""

from __future__ import annotations

from ultron.core.reminders import ReminderStore, cleanup, create_reminder, database_path


def _describe(record: dict) -> str:
    text = (
        f"{record['id']} — {record['message']}\n"
        f"State: {record['state']}; requested: {record['wall_time']} ({record['zone']}); "
        f"UTC: {record['target_utc']}"
    )
    if record["state"] == "notified":
        text += "\nThe OS notification command succeeded; this does not confirm it was seen."
    if record["state"] == "firing":
        text += "\nDelivery was claimed. If the worker crashed, create a new reminder; no automatic retry."
    if record["state"] == "registering":
        text += "\nRegistration is pending/uncertain; do not assume the OS job is active."
    if record["error"]:
        text += f"\nError: {record['error']}"
    if record["cleanup_error"]:
        text += (
            f"\nNative job cleanup pending: {record['cleanup_error']}. "
            "Use cancel with this ID to retry cleanup. Cancelled/failed entries cannot deliver."
        )
    return text


def reminder(parameters: dict, response=None, player=None, session_memory=None) -> str:
    """Existing date/time calls create reminders; action adds management operations."""
    try:
        if not isinstance(parameters, dict):
            raise ValueError("Reminder parameters must be an object.")
        action = parameters.get("action", "create")
        if not isinstance(action, str):
            raise ValueError("action must be text.")
        action = action.strip().lower()
        store = ReminderStore(database_path())
        if action == "create":
            record = create_reminder(
                store,
                parameters.get("date", ""),
                parameters.get("time", ""),
                parameters.get("message", "Reminder"),
                parameters.get("timezone", ""),
                parameters.get("fold"),
            )
            result = _describe(record)
            prefix = (
                "Reminder registered.\n"
                if record["state"] == "scheduled"
                else "Reminder was not registered successfully.\n"
            )
            if player is not None and hasattr(player, "write_log"):
                try:
                    player.write_log(f"[Reminder] {record['id']}: {record['state']}")
                except Exception:
                    pass  # logging must not hide successful registration
            return prefix + result
        if action == "list":
            include_finished = parameters.get("include_finished", False)
            if not isinstance(include_finished, bool):
                raise ValueError("include_finished must be true or false.")
            limit = parameters.get("limit", 50)
            records = store.list(include_finished=include_finished, limit=limit)
            if not records:
                return "No reminders in the requested registry scope. Legacy jobs created before this upgrade are not indexed."
            return (
                f"Registered reminders (up to {limit}; only jobs created by this version):\n"
                + "\n\n".join(map(_describe, records))
            )
        reminder_id = parameters.get("reminder_id", "")
        if action == "status":
            return _describe(store.get(reminder_id))
        if action == "cancel":
            before = store.get(reminder_id)
            record = store.cancel(reminder_id)
            if before["state"] in {"scheduled", "registering"} or before["cleanup_error"]:
                cleanup(store, record)
            return _describe(store.get(reminder_id))
        raise ValueError("Unknown action. Use create, list, status or cancel.")
    except (ValueError, TypeError) as error:
        return f"Reminder request rejected: {error}"
    except Exception as error:
        return f"Reminder operation failed: {error}"


TOOL = {
    "name": "reminder",
    "description": (
        "Create, list, inspect or cancel persistent OS-scheduled reminders by stable reminder_id. "
        "Default action create preserves existing date/time calls. Requires date YYYY-MM-DD, time HH:MM "
        "and a message when creating; choose at least 60 seconds ahead. Optional IANA timezone, e.g. Africa/Tunis; "
        "otherwise use the computer's local timezone. Ambiguous DST time requires fold=0/1. "
        "Jobs survive assistant exit; native scheduling requires a logged-in user/session and working OS scheduler. "
        "Windows Task Scheduler, macOS launchd (up to about one minute polling delay), Linux systemd user timers. "
        "Notifications are best-effort, not guaranteed delivery. Lists only this version's registered jobs."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "enum": ["create", "list", "status", "cancel"],
                "description": "Operation, default create",
            },
            "date": {"type": "STRING", "description": "Reminder date YYYY-MM-DD"},
            "time": {"type": "STRING", "description": "Reminder wall time HH:MM (24-hour)"},
            "message": {"type": "STRING", "description": "Reminder text, 1–500 characters"},
            "timezone": {
                "type": "STRING",
                "description": "Optional IANA timezone, otherwise system local",
            },
            "fold": {
                "type": "INTEGER",
                "description": "DST ambiguity only: 0 earlier occurrence, 1 later",
            },
            "reminder_id": {
                "type": "STRING",
                "description": "Full ID from create/list; needed for status/cancel",
            },
            "include_finished": {
                "type": "BOOLEAN",
                "description": "List terminal records too; default false",
            },
            "limit": {"type": "INTEGER", "description": "List at most 1–100 reminders, default 50"},
        },
        "required": [],
    },
    "handler": reminder,
}
