"""No sleeps or real timer threads: exercise scheduling and stale-callback races."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from ultron.actions import quick_timer as qt
from ultron.core.action_loader import ActionRegistry, _validate


class FakeHandle:
    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.daemon = False
        self.cancelled = False
        self.started = False

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        # Simulate a callback already enqueued before cancel/pause won the lock.
        self.callback()


@pytest.fixture
def timers(monkeypatch):
    clock = [100.0]
    handles = []

    def schedule(delay, callback):
        handle = FakeHandle(delay, callback)
        handles.append(handle)
        return handle

    service = qt.TimerService(clock=lambda: clock[0], timer_factory=schedule)
    monkeypatch.setattr(qt, "_SERVICE", service)
    return service, clock, handles


def test_legacy_start_default_and_duration_addition(timers):
    service, _, handles = timers
    assert "Timer set" in qt.quick_timer_handler({})
    assert handles[-1].delay == 60
    assert "Timer set" in qt.quick_timer_handler({"minutes": 2, "seconds": 5, "message": "tea"})
    assert service.list()[-1]["duration_seconds"] == 125
    assert handles[-1].started and handles[-1].daemon


def test_status_uses_monotonic_remaining_time(timers):
    service, clock, _ = timers
    timer = service.start(60, "tea")
    clock[0] += 4.2
    assert service.status(timer["id"])["remaining_seconds"] == 56
    assert service.status("TEA")["id"] == timer["id"]


def test_cancel_suppresses_queued_callback(timers):
    service, _, handles = timers
    announced = []
    timer = service.start(60, "tea", speak=announced.append)
    service.change("cancel", timer["id"])
    handles[0].fire()
    assert handles[0].cancelled
    assert announced == []
    assert service.list() == []
    assert service.status(timer["id"])["state"] == "cancelled"


def test_pause_resume_preserves_time_and_ignores_old_generation(timers):
    service, clock, handles = timers
    announced = []
    timer = service.start(60, "tea", speak=announced.append)
    clock[0] += 15
    assert service.change("pause", timer["id"])["remaining_seconds"] == 45
    clock[0] += 100
    assert service.status(timer["id"])["remaining_seconds"] == 45
    service.change("resume", timer["id"])
    assert handles[-1].delay == 45
    handles[0].fire()
    assert announced == []
    handles[-1].fire()
    handles[-1].fire()
    assert announced == ["Timer complete: tea"]
    assert service.status(timer["id"])["remaining_seconds"] == 0


def test_notification_channels_are_independent(timers):
    service, _, handles = timers
    announced = []

    class BrokenLog:
        def write_log(self, _):
            raise RuntimeError("UI unavailable")

    service.start(1, "tea", speak=announced.append, player=BrokenLog())
    handles[0].fire()
    assert announced == ["Timer complete: tea"]


def test_ambiguous_labels_do_not_cancel_anything(timers):
    service, _, _ = timers
    service.start(60, "tea")
    service.start(30, "tea")
    assert "Multiple timers" in qt.quick_timer_handler({"action": "cancel", "message": "tea"})
    assert len(service.list()) == 2
    assert "Multiple timers" in qt.quick_timer_handler({"action": "cancel"})


@pytest.mark.parametrize(
    "parameters",
    [
        {"seconds": 0},
        {"seconds": -1},
        {"seconds": True},
        {"seconds": 1.5},
        {"seconds": "tomorrow"},
        {"minutes": -1, "seconds": 120},
        {"seconds": qt.MAX_DURATION + 1},
        {"seconds": None},
        {"action": []},
        {"message": 123},
        {"message": False},
        {"action": "status", "timer_id": 3},
    ],
)
def test_invalid_input_is_rejected_without_starting(timers, parameters):
    service, _, _ = timers
    assert "rejected" in qt.quick_timer_handler(parameters)
    assert service.list() == []


def test_active_limit_and_bounded_terminal_history(timers, monkeypatch):
    service, _, handles = timers
    monkeypatch.setattr(qt, "MAX_ACTIVE", 2)
    monkeypatch.setattr(qt, "MAX_HISTORY", 2)
    service.start(60)
    service.start(60)
    with pytest.raises(ValueError, match="At most"):
        service.start(60)
    handles[0].fire()
    handles[1].fire()
    service.start(60)
    handles[-1].fire()
    assert len(service.list(include_finished=True)) == 2


def test_scheduler_failure_does_not_leave_a_running_timer(timers):
    service, _, _ = timers

    def broken(*args):
        raise RuntimeError("Cannot start worker")

    service._timer_factory = broken
    assert "failed" in qt.quick_timer_handler({"seconds": 60})
    assert not service.list()


def test_concurrent_starts_produce_unique_manageable_ids(timers):
    service, _, _ = timers
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda n: service.start(60, str(n)), range(12)))
    assert len({row["id"] for row in results}) == 12
    assert len(service.list()) == 12


def test_timer_is_compatible_with_registry_dispatch(timers):
    record = _validate(qt, "quick_timer.py")
    assert record.valid
    registry = ActionRegistry({record.name: record}, logger=lambda _: None)
    assert "Timer set" in registry.run("quick_timer", {"seconds": 5, "message": "registry"})
    assert "registry" in registry.run("quick_timer", {"action": "list"})
    assert "cancelled" in registry.run("quick_timer", {"action": "cancel", "message": "registry"})
