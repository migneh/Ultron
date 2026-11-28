"""Human gate identities, expiry, busy behavior and lifecycle callbacks."""

import threading

import pytest

from ultron.core import confirm as cf


@pytest.fixture
def gate(monkeypatch):
    for attr in (
        "_pending",
        "_show_cb",
        "_hide_cb",
        "_log_cb",
        "_show_with_id_cb",
        "_hide_with_id_cb",
    ):
        monkeypatch.setattr(cf, attr, None)
    shown, hidden, logs = [], [], []
    finished = threading.Event()

    def log(text):
        logs.append(text)
        if text.startswith(("SYS: Confirmed", "ERR: Confirmed action")):
            finished.set()

    cf.bind(
        show=None,
        hide=None,
        log=log,
        show_with_id=lambda *args: shown.append(args),
        hide_with_id=lambda token: hidden.append(token),
    )
    return shown, hidden, logs, finished


def test_pending_request_never_replaced_by_another(gate):
    shown, _, _, _ = gate
    ran, cancelled = [], []
    assert "PENDING" in cf.request("a", "first", "first body", lambda: ran.append("a") or "done")
    assert "BUSY" in cf.request(
        "b", "second", "second body", lambda: "must not run", on_cancel=cancelled.append
    )
    assert cancelled == ["busy"]
    assert len(shown) == 1
    assert cf.pending_title() == "first"
    assert not ran


def test_stale_click_cannot_approve_a_new_request(gate):
    shown, hidden, _, finished = gate
    ran = []
    cf.request("a", "first", "body", lambda: ran.append("a") or "done")
    first = shown[-1][2]
    cf.resolve(False, first)
    cf.request("b", "second", "body", lambda: ran.append("b") or "done")
    second = shown[-1][2]
    cf.resolve(True, first)
    assert cf.is_current(second)
    assert hidden == [first]
    assert not ran
    cf.resolve(True, second)
    assert finished.wait(2)
    assert ran == ["b"]
    cf.resolve(True, second)
    assert ran == ["b"]


def test_expired_request_not_executed_and_callback_runs(gate, monkeypatch):
    shown, _, _, _ = gate
    clock = [0.0]
    monkeypatch.setattr(cf.time, "monotonic", lambda: clock[0])
    ran, cancelled = [], []
    cf.request("a", "first", "body", lambda: ran.append(True) or "done", on_cancel=cancelled.append)
    clock[0] += cf.TIMEOUT_SECONDS + 1
    assert not cf.is_current(shown[-1][2])
    cf.resolve(True, shown[-1][2])
    assert not ran
    assert cancelled == ["expired"]
    assert cf.pending_title() == ""


def test_cancel_pending_is_scoped_to_its_key(gate):
    cancelled = []
    cf.request("a", "first", "body", lambda: "must not run", on_cancel=cancelled.append)
    assert not cf.cancel_pending("b")
    assert cf.pending_title() == "first"
    assert cf.cancel_pending("a")
    assert cancelled == ["cancelled"]
    assert cf.pending_title() == ""


def test_headless_refusal_notifies_lifecycle(gate):
    cf.bind(None, None)
    cancelled = []
    assert "cannot confirm" in cf.request(
        "a", "title", "body", lambda: "must not run", on_cancel=cancelled.append
    )
    assert cancelled == ["unavailable"]


def test_show_failure_does_not_leave_live_approval(gate):
    def broken(*args):
        raise RuntimeError("private payload should not appear")

    cf.bind(broken, None)
    cancelled = []
    result = cf.request("a", "title", "body", lambda: "must not run", on_cancel=cancelled.append)
    assert "private payload" not in result
    assert cancelled == ["unavailable"]
    assert cf.pending_title() == ""


def test_callback_failure_does_not_poison_gate(gate):
    shown, _, _, _ = gate

    def broken(_):
        raise RuntimeError("private")

    cf.request("a", "first", "body", lambda: "done", on_cancel=broken)
    cf.resolve(False, shown[-1][2])
    assert "PENDING" in cf.request("b", "second", "body", lambda: "done")


def test_legacy_binding_and_resolution_still_work(gate):
    ran = threading.Event()
    titles = []
    cf.bind(lambda title, detail: titles.append(title), lambda: None)
    cf.request("a", "legacy", "body", lambda: ran.set() or "done")
    assert titles == ["legacy"]
    cf.resolve(True)
    assert ran.wait(2)


def test_action_exception_does_not_leak_credential_url(gate):
    shown, _, logs, finished = gate

    def broken():
        raise RuntimeError("https://host/botTOP-SECRET/sendMessage")

    cf.request("a", "Send Telegram message", "body", broken)
    cf.resolve(True, shown[-1][2])
    assert finished.wait(2)
    assert not any("TOP-SECRET" in text for text in logs)


def test_expiry_allows_new_banner_but_old_click_stays_invalid(gate, monkeypatch):
    shown, _, _, _ = gate
    clock = [0.0]
    monkeypatch.setattr(cf.time, "monotonic", lambda: clock[0])
    ran = []
    cf.request("a", "old", "body", lambda: ran.append("old") or "done")
    old = shown[-1][2]
    clock[0] += cf.TIMEOUT_SECONDS + 1
    cf.request("b", "new", "body", lambda: ran.append("new") or "done")
    current = shown[-1][2]
    assert current != old
    cf.resolve(True, old)
    assert cf.is_current(current)
    assert not ran


def test_only_boolean_true_accepts_a_request(gate):
    shown, _, _, _ = gate
    ran = []
    cf.request("a", "action", "body", lambda: ran.append(True) or "done")
    cf.resolve("yes", shown[-1][2])
    assert not ran
    assert cf.pending_title() == ""


def test_worker_start_failure_clears_approval_without_running(gate, monkeypatch):
    shown, _, _, _ = gate
    ran, cancelled = [], []
    cf.request(
        "a", "action", "body", lambda: ran.append(True) or "done", on_cancel=cancelled.append
    )

    class BrokenThread:
        def __init__(self, **kwargs):
            pass

        def start(self):
            raise RuntimeError("no worker available")

    monkeypatch.setattr(cf.threading, "Thread", BrokenThread)
    cf.resolve(True, shown[-1][2])
    assert not ran
    assert cancelled == ["unavailable"]
    assert not cf.pending_title()
