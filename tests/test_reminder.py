"""Reminder state/timezone regressions. Never register jobs or show notifications."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

import pytest

from ultron.actions import reminder as action
from ultron.core import reminders as rm
from ultron.core.action_loader import ActionRegistry, _validate


@pytest.fixture(autouse=True)
def no_real_processes(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Tests must never invoke native schedulers/notifications")

    monkeypatch.setattr(rm.subprocess, "run", blocked)


@pytest.fixture
def service(tmp_path, monkeypatch):
    path = tmp_path / "registry.sqlite3"
    clock = [datetime(2035, 1, 1, tzinfo=rm.UTC)]
    installed, removed, notifications = [], [], []
    monkeypatch.setattr(action, "database_path", lambda: path)
    monkeypatch.setattr(rm, "_now", lambda: clock[0])
    monkeypatch.setattr(rm.platform, "system", lambda: "Linux")
    monkeypatch.setattr(rm, "install_job", lambda record, db: installed.append(record["id"]))
    monkeypatch.setattr(rm, "remove_job", lambda record: removed.append(record["id"]))
    monkeypatch.setattr(rm, "notify", notifications.append)
    return rm.ReminderStore(path), clock, installed, removed, notifications


def create(store, message="tea", **kwargs):
    return rm.create_reminder(store, "2035-06-01", "12:30", message, "UTC", **kwargs)


def due(store, clock, record):
    clock[0] = datetime.fromisoformat(record["target_utc"]) + timedelta(seconds=1)


def test_create_reopen_status_and_legacy_tool_call(service):
    store, _, installed, _, _ = service
    output = action.reminder(
        {"date": "2035-06-01", "time": "12:30", "message": 'tea "break"', "timezone": "UTC"}
    )
    assert "Reminder registered" in output
    records = rm.ReminderStore(store.path).list()
    assert len(records) == 1
    assert records[0]["id"] in output
    assert records[0]["message"] == 'tea "break"'
    assert installed == [records[0]["id"]]
    assert "scheduled" in action.reminder({"action": "status", "reminder_id": records[0]["id"]})


def test_cancel_is_durable_and_suppresses_late_worker(service):
    store, clock, _, removed, notifications = service
    record = create(store)
    output = action.reminder({"action": "cancel", "reminder_id": record["id"]})
    assert "cancelled" in output
    due(store, clock, record)
    assert not rm.deliver(store.path, record["id"])
    assert notifications == []
    assert removed == [record["id"]]
    assert store.list() == []
    assert store.list(include_finished=True)[0]["state"] == "cancelled"


def test_cancel_failure_reports_cleanup_pending_but_still_suppresses_delivery(service, monkeypatch):
    store, clock, _, _, notifications = service
    record = create(store)

    def unavailable(_):
        raise RuntimeError("scheduler unavailable")

    monkeypatch.setattr(rm, "remove_job", unavailable)
    assert "cleanup pending" in action.reminder({"action": "cancel", "reminder_id": record["id"]})
    due(store, clock, record)
    assert not rm.deliver(store.path, record["id"])
    assert not notifications
    monkeypatch.setattr(rm, "remove_job", lambda _: None)
    action.reminder({"action": "cancel", "reminder_id": record["id"]})
    assert store.get(record["id"])["cleanup_error"] == ""


def test_delivery_is_due_only_and_at_most_once(service):
    store, clock, _, removed, notifications = service
    record = create(store)
    assert not rm.deliver(store.path, record["id"])
    due(store, clock, record)
    assert rm.deliver(store.path, record["id"])
    assert not rm.deliver(store.path, record["id"])
    assert notifications == ["tea"]
    assert removed == [record["id"]]
    assert store.get(record["id"])["state"] == "notified"
    assert "does not confirm it was seen" in action.reminder(
        {"action": "status", "reminder_id": record["id"]}
    )


def test_concurrent_workers_cannot_double_deliver(service):
    store, clock, _, _, notifications = service
    record = create(store)
    due(store, clock, record)
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: rm.deliver(store.path, record["id"]), range(8)))
    assert results.count(True) == 1
    assert notifications == ["tea"]


def test_notification_failure_is_recorded_not_retried(service, monkeypatch):
    store, clock, _, _, _ = service
    record = create(store)
    due(store, clock, record)

    def unavailable(_):
        raise RuntimeError("no desktop session")

    monkeypatch.setattr(rm, "notify", unavailable)
    assert rm.deliver(store.path, record["id"])
    final = store.get(record["id"])
    assert final["state"] == "notification_failed"
    assert "no desktop session" in final["error"]
    assert not rm.deliver(store.path, record["id"])


def test_delivery_claim_wins_cancel_race(service):
    store, clock, _, _, _ = service
    record = create(store)
    due(store, clock, record)
    assert store.claim(record["id"])
    assert "already started" in action.reminder({"action": "cancel", "reminder_id": record["id"]})
    assert store.get(record["id"])["state"] == "firing"


def test_cancel_during_registration_cannot_be_resurrected(service, monkeypatch):
    store, _, _, removed, _ = service
    monkeypatch.setattr(rm, "install_job", lambda record, _: store.cancel(record["id"]))
    record = create(store)
    assert record["state"] == "cancelled"
    assert removed == [record["id"]]


def test_registration_failure_has_traceable_id_and_cleanup(service, monkeypatch):
    store, _, _, removed, _ = service

    def unavailable(*_):
        raise RuntimeError("no systemd user manager")

    monkeypatch.setattr(rm, "install_job", unavailable)
    output = action.reminder(
        {"date": "2035-06-01", "time": "12:30", "message": "tea", "timezone": "UTC"}
    )
    assert "not registered successfully" in output
    record = store.list(include_finished=True)[0]
    assert record["id"] in output
    assert record["state"] == "scheduling_failed"
    assert removed == [record["id"]]
    assert not store.claim(record["id"])


def test_two_reminders_at_same_time_have_distinct_ids(service):
    store, _, _, _, _ = service
    assert create(store)["id"] != create(store)["id"]


def test_active_limit_is_enforced_in_transaction(service, monkeypatch):
    store, _, _, _, _ = service
    monkeypatch.setattr(rm, "MAX_ACTIVE", 2)
    create(store)
    create(store)
    with pytest.raises(ValueError, match="At most"):
        create(store)
    assert len(store.list()) == 2


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"date": "2035-02-30", "time": "12:00"},
        {"date": "2035-06-01", "time": "25:30"},
        {"date": "2035-06-01", "time": "12:00", "timezone": "Not/AZone"},
        {"date": "2035-06-01", "time": "12:00", "message": ""},
        {"date": "2035-06-01", "time": "12:00", "message": False},
        {"date": "2035-06-01", "time": "12:00", "message": "x" * 501},
        {"date": "2035-06-01", "time": "12:00", "fold": True},
        {"date": "2035-06-01", "time": "12:00", "fold": 0.0},
        {"action": "status", "reminder_id": "../../user-job"},
        {"action": "cancel", "reminder_id": "a" * 32},
        {"action": "list", "include_finished": "yes"},
        {"action": "list", "limit": -1},
        {"action": "unknown"},
        {"action": []},
    ],
)
def test_invalid_requests_do_not_install_jobs(service, parameters):
    _, _, installed, removed, notifications = service
    assert "rejected" in action.reminder(parameters)
    assert not installed and not removed and not notifications


def test_minimum_lead_time_and_past_date(service):
    store, _, _, _, _ = service
    for date, clock in (("2034-01-01", "12:00"), ("2035-01-01", "00:00")):
        with pytest.raises(ValueError, match="60 seconds"):
            rm.create_reminder(store, date, clock, "tea", "UTC")


def test_explicit_timezone_and_dst_boundaries():
    assert rm.parse_target("2026-11-23", "10:00", "Africa/Tunis").hour == 9
    with pytest.raises(ValueError, match="does not exist"):
        rm.parse_target("2026-03-08", "02:30", "America/New_York")
    with pytest.raises(ValueError, match="occurs twice"):
        rm.parse_target("2026-11-01", "01:30", "America/New_York")
    early = rm.parse_target("2026-11-01", "01:30", "America/New_York", fold=0)
    late = rm.parse_target("2026-11-01", "01:30", "America/New_York", fold=1)
    assert late - early == timedelta(hours=1)


def test_local_timezone_dst_validation(monkeypatch):
    import time

    if not hasattr(time, "tzset"):
        pytest.skip("tzset unavailable")
    try:
        with monkeypatch.context() as context:
            context.setenv("TZ", "America/New_York")
            time.tzset()
            with pytest.raises(ValueError, match="does not exist"):
                rm.parse_target("2026-03-08", "02:30")
            with pytest.raises(ValueError, match="occurs twice"):
                rm.parse_target("2026-11-01", "01:30")
    finally:
        time.tzset()


def test_reminder_registry_contract_and_no_create_fields_for_list(service):
    record = _validate(action, "reminder.py")
    assert record.valid
    registry = ActionRegistry({record.name: record}, logger=lambda _: None)
    assert "No reminders" in registry.run("reminder", {"action": "list"})
    assert action.TOOL["parameters"]["required"] == []


def test_missing_database_runner_does_not_create_files(tmp_path):
    path = tmp_path / "missing.sqlite3"
    assert not rm.deliver(path, "a" * 32)
    assert not path.exists()


def test_frozen_create_is_explicitly_unsupported(service, monkeypatch):
    store, _, _, _, _ = service
    monkeypatch.setattr(rm.sys, "frozen", True, raising=False)
    with pytest.raises(ValueError, match="frozen-app"):
        create(store)


def test_notification_text_is_data_not_code(monkeypatch):
    calls = []

    def capture(args, **kwargs):
        calls.append((args, kwargs))

    monkeypatch.setattr(rm, "_run", capture)
    message = "quotes '\"; $(touch /tmp/no) & data\nnext"
    monkeypatch.setattr(rm.platform, "system", lambda: "Windows")
    rm.notify(message)
    args, kwargs = calls[-1]
    assert message not in args[-1]
    assert kwargs["env"]["ULTRON_REMINDER_MESSAGE"] == message
    monkeypatch.setattr(rm.platform, "system", lambda: "Darwin")
    rm.notify(message)
    assert calls[-1][0][-1] == message
    assert message not in calls[-1][0][2]
    monkeypatch.setattr(rm.platform, "system", lambda: "Linux")
    rm.notify(message)
    assert calls[-1][0] == ["notify-send", "--", "ULTRON Reminder", message]
