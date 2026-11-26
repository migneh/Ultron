"""Inspect/cancel durable host jobs; cannot submit arbitrary code or job kinds."""
import json

from ultron.core.background_jobs import get_service


def background_jobs(parameters: dict, **kwargs) -> str:
    try:
        if not isinstance(parameters, dict):
            raise ValueError("Arguments must be an object")
        action = parameters.get("action")
        fields = {"list": {"limit"}, "status": {"job_id"}, "cancel": {"job_id"}, "clear_terminal": set()}
        if not isinstance(action, str) or action not in fields or parameters.keys() - (fields[action] | {"action"}):
            raise ValueError("Unknown action/arguments")
        service = get_service()
        if action == "list":
            data = service.list(parameters.get("limit", 20))
        elif action == "status":
            data = service.get(parameters.get("job_id"))
        elif action == "cancel":
            data = service.cancel(parameters.get("job_id"))
        else:
            data = {"removed_metadata": service.clear_terminal(), "reports_removed": False}
        return json.dumps({"status": "completed", "data": data,
                           "note": "Inspection/cancellation request is not proof of worker termination. No job replay or automatic retry."})
    except ValueError:
        return json.dumps({"status": "rejected", "error": "Check exact job ID, action, fields or limit (1–100)."})
    except Exception:
        return json.dumps({"status": "unavailable", "error": "Job journal unavailable; no automatic retry."})


TOOL = {
    "name": "background_jobs",
    "description": "Inspect durable host background jobs: list, status(job_id), cancel(job_id), clear_terminal (metadata only, never reports). Exact full IDs only. No arbitrary submission/code, replay or automatic retries. cancel_requested/overdue do not mean termination; blocked workers retain admission slots. After process ownership transfers, unfinished jobs are interrupted/outcome_unknown, never silently restarted.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {"type": "STRING", "description": "list | status | cancel | clear_terminal"},
            "job_id": {"type": "STRING", "description": "Exact full host-issued job ID"},
            "limit": {"type": "INTEGER", "description": "1–100, default 20"},
        },
        "required": ["action"],
    },
    "handler": background_jobs,
}
