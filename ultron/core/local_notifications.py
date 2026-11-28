"""Opt-in, at-most-once generic local HUD announcements, never external delivery.

Persist uncertainty before calling the UI. A crash/exception may lose an alert,
but cannot cause automatic retry. Notices remain available through explicit
inbox reads. Callback success means queued to UI, not displayed/read by a human.
"""
from __future__ import annotations

from ultron.core import local_productivity as local
from ultron.core import productivity_store as store


def configure(enabled: bool):
    """Host-only consent; not exposed through a model-facing tool."""
    if type(enabled) is not bool:
        raise ValueError("Use explicit boolean host consent")
    previous = store.setting("local_notification_delivery", {})
    config = {"enabled": enabled, "enabled_at": previous["enabled_at"]
              if enabled and previous.get("enabled") is True else local.stamp()}
    store.set_setting("local_notification_delivery", config)
    return config


def _enabled():
    config = store.setting("local_notification_delivery", {})
    return config if config.get("enabled") is True and isinstance(config.get("enabled_at"), str) else None


def deliver_tick(show_toast):
    """At most 20 new notices in one generic announcement per bounded tick.

    Claim-before-call prevents duplicates across reconnects/processes. Consent,
    quiet hours, expiry and acknowledgement are rechecked immediately before
    submission. Already queued UI events cannot be recalled atomically.
    """
    config = _enabled()
    if not config:
        return {"state": "disabled", "count": 0}
    if local.quiet_state()[1]:
        return {"state": "quiet", "count": 0}
    claimed = []
    with store.connection() as db:
        rows = db.execute("""SELECT id FROM notices WHERE acknowledged=0 AND expires>?
            AND created>=? AND NOT EXISTS(SELECT 1 FROM notice_deliveries WHERE notice_id=notices.id)
            ORDER BY created,id LIMIT 20""", (local.stamp(), config["enabled_at"])).fetchall()
        for row in rows:
            db.execute("INSERT INTO notice_deliveries VALUES(?,'outcome_unknown',?)", (row["id"], local.stamp()))
            claimed.append(row["id"])
    if not claimed:
        return {"state": "empty", "count": 0}
    current = _enabled()
    if current != config or local.quiet_state()[1]:
        with store.connection() as db:
            db.executemany("DELETE FROM notice_deliveries WHERE notice_id=? AND state='outcome_unknown'", [(item,) for item in claimed])
        return {"state": "deferred", "count": 0}
    with store.connection() as db:
        live = [item for item in claimed if db.execute("SELECT 1 FROM notices WHERE id=? AND acknowledged=0 AND expires>?", (item, local.stamp())).fetchone()]
        db.executemany("UPDATE notice_deliveries SET state='suppressed' WHERE notice_id=?", [(item,) for item in claimed if item not in live])
    if not live:
        return {"state": "suppressed", "count": 0}
    # No task titles, source quotes, job results or IDs are sent to the UI/log,
    # model, speech service, phone bridge or another external transport here.
    try:
        show_toast(f"{len(live)} new local notification(s). Ask for your notification inbox to review.", level="info", duration_ms=5000)
    except Exception:
        return {"state": "outcome_unknown", "count": len(live)}
    with store.connection() as db:
        db.executemany("UPDATE notice_deliveries SET state='queued_to_ui' WHERE notice_id=? AND state='outcome_unknown'", [(item,) for item in live])
    return {"state": "queued_to_ui", "count": len(live)}


def enqueue_job_outcome(job_id, state):
    """Best-effort bridge from terminal job metadata; no report bodies/queries."""
    store.identifier(job_id)
    from ultron.core.background_jobs import TERMINAL
    if state not in TERMINAL:
        raise ValueError("Only terminal job outcomes are notices")
    with store.connection() as db:
        local.notify(db, "Background job finished", f"Job {job_id}: {state}. Inspect background_jobs for the actual outcome.",
                     f"job:{job_id}:{state}")
