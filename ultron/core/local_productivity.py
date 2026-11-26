"""Bounded local task, evidence and notification services. No network or scheduler."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo

from ultron.core import productivity_store as store


def now():
    return datetime.now(timezone.utc)


def stamp():
    return now().isoformat()


def limit(value=20):
    if type(value) is not int or not 1 <= value <= 100:
        raise ValueError("limit must be an integer from 1 to 100.")
    return value


def notify(db, title, body, dedupe):
    # Keep bounded persistent local notices. Never forward to external channels.
    db.execute("DELETE FROM notices WHERE expires<=?", (stamp(),))
    if db.execute("SELECT count(*) FROM notices").fetchone()[0] >= 1000:
        raise ValueError("Local notification inbox full; acknowledge and clear older notices.")
    db.execute("INSERT OR IGNORE INTO notices VALUES(?,?,?,?,?,?,0)",
               (store.new_id(), dedupe, title, body, stamp(), (now() + timedelta(days=30)).isoformat()))


def due_date(value):
    if value is None or value == "":
        return None
    if not isinstance(value, str) or date.fromisoformat(value).isoformat() != value:
        raise ValueError("Use a YYYY-MM-DD date, not a timestamp or reminder time.")
    return value


def tasks(action, **args):
    with store.connection() as db:
        if action == "create":
            title = store.text(args.get("title"), "title", 200)
            notes = store.text(args.get("notes", ""), "notes", 2000, empty=True)
            due = due_date(args.get("due_date"))
            if db.execute("SELECT count(*) FROM tasks").fetchone()[0] >= 5000:
                raise ValueError("Task board full (5000 tasks).")
            task_id = store.new_id()
            db.execute("INSERT INTO tasks VALUES(?,?,?,'todo',?,1,?)", (task_id, title, notes, due, stamp()))
            notify(db, "Task created", title, f"task:{task_id}:1")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
        if action == "list":
            state = args.get("state")
            if state is not None and state not in {"todo", "doing", "done", "archived"}:
                raise ValueError("Unknown task state.")
            return [dict(row) for row in db.execute("SELECT * FROM tasks WHERE (? IS NULL OR state=?) ORDER BY created DESC,id LIMIT ?",
                                                   (state, state, limit(args.get("limit", 20))))]
        task_id = store.identifier(args.get("task_id"))
        row = db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone()
        if row is None:
            raise ValueError("Task not found.")
        if action == "get":
            return dict(row)
        if action == "update":
            version = args.get("expected_version")
            state = args.get("state", row["state"])
            if not {"state", "title", "notes", "due_date"} & args.keys():
                raise ValueError("Specify at least one task field to update.")
            title = store.text(args.get("title", row["title"]), "title", 200)
            notes = store.text(args.get("notes", row["notes"]), "notes", 2000, empty=True)
            due = due_date(args.get("due_date", row["due_date"]))
            if type(version) is not int or version != row["version"]:
                raise ValueError("Task version conflict. Get the task and review it before updating.")
            if state not in {"todo", "doing", "done", "archived"}:
                raise ValueError("Choose todo, doing, done or archived. Completion is an explicit user-directed change, not inferred.")
            result = db.execute("UPDATE tasks SET state=?,title=?,notes=?,due_date=?,version=version+1 WHERE id=? AND version=?", (state, title, notes, due, task_id, version))
            if result.rowcount != 1:
                raise ValueError("Concurrent task update; reload before retrying.")
            notify(db, "Task updated", f"{title}: {state}", f"task:{task_id}:{version + 1}")
            return dict(db.execute("SELECT * FROM tasks WHERE id=?", (task_id,)).fetchone())
        raise ValueError("Unknown task action.")


def evidence(action, **args):
    with store.connection() as db:
        if action == "add":
            claim = store.text(args.get("claim"), "claim", 2000)
            url = store.text(args.get("url"), "url", 2000)
            parts = urlsplit(url)
            if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
                raise ValueError("Use an HTTPS source URL without credentials. This tool does not fetch it.")
            quote = store.text(args.get("quote", ""), "quote", 4000, empty=True)
            locator = store.text(args.get("locator", ""), "locator", 200, empty=True)
            if db.execute("SELECT count(*) FROM evidence").fetchone()[0] >= 5000:
                raise ValueError("Evidence ledger full (5000 entries).")
            evidence_id = store.new_id()
            db.execute("INSERT INTO evidence VALUES(?,?,?,?,?,?)", (evidence_id, claim, url, quote, locator, stamp()))
            result = dict(db.execute("SELECT * FROM evidence WHERE id=?", (evidence_id,)).fetchone())
        elif action == "get":
            row = db.execute("SELECT * FROM evidence WHERE id=?", (store.identifier(args.get("evidence_id")),)).fetchone()
            if row is None:
                raise ValueError("Evidence entry not found.")
            result = dict(row)
        elif action == "list":
            return [{**dict(row), "verification": "unverified_user_supplied", "fetched_by_tool": False}
                    for row in db.execute("SELECT * FROM evidence ORDER BY created DESC,id LIMIT ?", (limit(args.get("limit", 20)),))]
        else:
            raise ValueError("Unknown evidence action.")
        return {**result, "verification": "unverified_user_supplied", "fetched_by_tool": False}


def quiet_state():
    config = store.setting("quiet_hours", {"timezone": "UTC", "start_hour": 0, "end_hour": 0})
    hour = now().astimezone(ZoneInfo(config["timezone"])).hour
    start, end = config["start_hour"], config["end_hour"]
    quiet = start != end and (start <= hour < end if start < end else hour >= start or hour < end)
    return config, quiet


def notifications(action, **args):
    if action == "quiet_hours":
        zone = store.text(args.get("timezone"), "timezone", 100)
        ZoneInfo(zone)
        start, end = args.get("start_hour"), args.get("end_hour")
        if type(start) is not int or type(end) is not int or not 0 <= start < 24 or not 0 <= end < 24:
            raise ValueError("Hours must be integers from 0 to 23. Equal hours disable quiet hours.")
        config = {"timezone": zone, "start_hour": start, "end_hour": end}
        store.set_setting("quiet_hours", config)
        return config
    with store.connection() as db:
        if action == "acknowledge":
            if db.execute("UPDATE notices SET acknowledged=1 WHERE id=?", (store.identifier(args.get("notice_id")),)).rowcount != 1:
                raise ValueError("Notice not found.")
            return {"acknowledged": True}
        if action == "clear_acknowledged":
            result = db.execute("DELETE FROM notices WHERE acknowledged=1 OR expires<=?", (stamp(),))
            return {"removed": result.rowcount}
        if action != "digest":
            raise ValueError("Unknown notification action.")
        rows = [dict(row) for row in db.execute("""SELECT notices.*,COALESCE(notice_deliveries.state,'not_attempted') AS local_delivery_state
            FROM notices LEFT JOIN notice_deliveries ON notices.id=notice_deliveries.notice_id
            WHERE acknowledged=0 AND expires>? ORDER BY created,id LIMIT ?""",
                                                (stamp(), limit(args.get("limit", 20))))]
    config, quiet = quiet_state()
    return {"quiet_now": quiet, "policy": config, "notices": rows,
            "local_delivery_enabled": store.setting("local_notification_delivery", {}).get("enabled", False) is True,
            "delivery": "local inbox only; optional host-enabled generic HUD counts; no external sends; digest remains readable during quiet hours"}
