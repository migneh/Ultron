"""Strict action contracts and structured outcomes for the local-first release."""
from __future__ import annotations

import json
import threading
from zoneinfo import ZoneInfoNotFoundError

FIELDS = {
    "calculator": {"calculate": {"expression"}, "convert": {"value", "from_unit", "to_unit"}},
    "task_board": {"create": {"title", "notes", "due_date"}, "list": {"state", "limit"},
                   "get": {"task_id"}, "update": {"task_id", "state", "title", "notes", "due_date", "expected_version"}},
    "evidence_ledger": {"add": {"claim", "url", "quote", "locator"}, "get": {"evidence_id"}, "list": {"limit"}},
    "document_compare": {"compare": {"left_path", "right_path"}},
    "safe_sharing": {"preview": {"path", "literals"}, "publish": {"preview_id", "destination"}, "discard": {"preview_id"}},
    "notification_center": {"digest": {"limit"}, "acknowledge": {"notice_id"},
                            "clear_acknowledged": set(), "quiet_hours": {"timezone", "start_hour", "end_hour"}},
    "google_workspace": {"status": set(), "drive_metadata": {"file_id"},
                         "drive_text": {"file_id"}, "agenda": {"time_min", "time_max"},
                         "availability": {"time_min", "time_max"}},
}


_SLOTS = threading.BoundedSemaphore(4)


def dispatch(name, parameters):
    if not _SLOTS.acquire(blocking=False):
        return json.dumps({"status": "blocked", "error": "Four productivity operations already active. No work queued; retry deliberately later."})
    try:
        return _dispatch(name, parameters)
    finally:
        _SLOTS.release()


def _dispatch(name, parameters):
    try:
        if not isinstance(parameters, dict) or not isinstance(parameters.get("action"), str):
            raise ValueError("Provide an explicit action and documented fields.")
        action = parameters["action"]
        if action not in FIELDS[name] or parameters.keys() - (FIELDS[name][action] | {"action"}):
            raise ValueError("Unknown action or fields. Tool arguments cannot grant access or approval.")
        args = {key: value for key, value in parameters.items() if key != "action"}
        if name == "calculator":
            from ultron.core.local_calculator import calculate, convert
            if action == "calculate":
                data = {"value": calculate(args.get("expression")), "precision": "28 significant decimal digits; rounded as necessary"}
            else:
                data = {"value": convert(args.get("value"), args.get("from_unit"), args.get("to_unit")), "unit": args.get("to_unit")}
        elif name == "task_board":
            from ultron.core.local_productivity import tasks
            data = tasks(action, **args)
        elif name == "evidence_ledger":
            from ultron.core.local_productivity import evidence
            data = evidence(action, **args)
        elif name == "notification_center":
            from ultron.core.local_productivity import notifications
            data = notifications(action, **args)
        elif name == "document_compare":
            from ultron.core.local_documents import compare
            data = compare(args.get("left_path"), args.get("right_path"))
        elif name == "safe_sharing":
            from ultron.core.local_documents import discard, preview, publish
            if action == "preview":
                data = preview(args.get("path"), args.get("literals"))
            elif action == "publish":
                data = publish(args.get("preview_id"), args.get("destination"))
            else:
                data = discard(args.get("preview_id"))
        elif name == "google_workspace":
            from ultron.core.google_workspace import workspace
            data = workspace(action, **args)
        else:
            raise ValueError("Unknown productivity capability.")
        status = "needs_approval" if isinstance(data, str) and "[CONFIRMATION_PENDING]" in data else "completed"
        if isinstance(data, str) and "[CONFIRMATION_BUSY]" in data:
            status = "blocked"
        if isinstance(data, str) and data.startswith(("I cannot confirm", "Could not display")):
            status = "blocked"
        return json.dumps({"status": status, "data": data}, ensure_ascii=False)
    except (ValueError, TypeError, KeyError, ZoneInfoNotFoundError):
        # Validation messages below are safe to show; unexpected provider/native
        # exceptions are handled separately to avoid credential-bearing URLs.
        return _rejected(name, parameters)
    except Exception:
        return json.dumps({"status": "unavailable", "error": "Operation unavailable. No automatic retry. Check setup/state; no completion is certified."})


def _rejected(name, parameters):
    # Do not echo arbitrary private data from parser/codec exceptions.
    return json.dumps({"status": "rejected", "error": f"Invalid input or access/setup constraint for {name}. Check documented formats, host grants, IDs and versions. No operation completion is certified."})
