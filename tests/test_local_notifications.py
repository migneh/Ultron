"""Notification tests use isolated SQLite and fake HUDs; no desktop/network."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest

from ultron.core import local_notifications as delivery
from ultron.core import local_productivity as local
from ultron.core import productivity_store as store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "database_path", lambda: tmp_path / "inbox.sqlite3")
    clock = [datetime(2026, 1, 1, 12, tzinfo=timezone.utc)]
    monkeypatch.setattr(local, "now", lambda: clock[0])
    return clock


def notice(key="one"):
    with store.connection() as db:
        local.notify(db, "SECRET TITLE", "SECRET BODY", key)


def test_default_disabled_and_host_boolean():
    notice()
    assert delivery.deliver_tick(None)["state"] == "disabled"
    with pytest.raises(ValueError):
        delivery.configure("on")


def test_no_historical_replay_or_private_content(isolated):
    notice("old")
    isolated[0] += timedelta(seconds=1)
    delivery.configure(True)
    notice("new")
    calls = []
    assert delivery.deliver_tick(lambda *a, **kw: calls.append((a, kw)))["count"] == 1
    assert "SECRET" not in str(calls)
    assert delivery.deliver_tick(None)["state"] == "empty"
    assert {n["local_delivery_state"] for n in local.notifications("digest")["notices"]} == {"not_attempted", "queued_to_ui"}


def test_quiet_hours_overnight_then_release(isolated):
    delivery.configure(True)
    notice()
    local.notifications("quiet_hours", timezone="UTC", start_hour=23, end_hour=13)
    assert delivery.deliver_tick(None)["state"] == "quiet"
    isolated[0] += timedelta(hours=2)
    assert delivery.deliver_tick(lambda *a, **k: None)["count"] == 1


def test_uncertain_callback_never_retried():
    delivery.configure(True)
    notice()
    def fail(*a, **kw):
        raise RuntimeError("UI failure")
    assert delivery.deliver_tick(fail)["state"] == "outcome_unknown"
    assert delivery.deliver_tick(fail)["state"] == "empty"
    assert local.notifications("digest")["notices"][0]["local_delivery_state"] == "outcome_unknown"


def test_ack_expiry_and_cascade(isolated):
    delivery.configure(True)
    notice()
    item = local.notifications("digest")["notices"][0]
    local.notifications("acknowledge", notice_id=item["id"])
    assert delivery.deliver_tick(None)["count"] == 0
    notice("other")
    delivery.deliver_tick(lambda *a, **k: None)
    isolated[0] += timedelta(days=31)
    local.notifications("clear_acknowledged")
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM notice_deliveries").fetchone()[0] == 0


def test_concurrent_ticks_at_most_once():
    delivery.configure(True)
    notice()
    calls = []
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda _: delivery.deliver_tick(lambda *a, **k: calls.append(a)), range(2)))
    assert len(calls) == 1


def test_disable_and_reenable_skips_disabled_period(isolated):
    delivery.configure(True)
    delivery.configure(False)
    notice()
    isolated[0] += timedelta(seconds=1)
    delivery.configure(True)
    assert delivery.deliver_tick(None)["count"] == 0


def test_batch_bounded():
    delivery.configure(True)
    for index in range(23):
        notice(str(index))
    assert delivery.deliver_tick(lambda *a, **k: None)["count"] == 20
    assert delivery.deliver_tick(lambda *a, **k: None)["count"] == 3


def test_job_outcomes_dedupe():
    delivery.enqueue_job_outcome("a" * 32, "failed")
    delivery.enqueue_job_outcome("a" * 32, "failed")
    assert len(local.notifications("digest")["notices"]) == 1
    with pytest.raises(ValueError):
        delivery.enqueue_job_outcome("a" * 32, "running")


def test_revocation_between_claim_and_submission(monkeypatch):
    delivery.configure(True)
    notice()
    real = delivery._enabled
    reads = []
    def revoke():
        reads.append(1)
        if len(reads) == 2:
            delivery.configure(False)
        return real()
    monkeypatch.setattr(delivery, "_enabled", revoke)
    assert delivery.deliver_tick(None)["state"] == "deferred"
    with store.connection() as db:
        assert db.execute("SELECT count(*) FROM notice_deliveries").fetchone()[0] == 0
