"""Host approval lifecycle without network or native effects."""
from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError, replace

import pytest

from ultron.core import confirm
from ultron.core import operation_policy as policy


def plan():
    return policy.prepare("test.write", ("destination",), {"text": "private"})


def test_payload_is_detached_immutable_and_fingerprinted():
    payload = {"nested": ["original"]}
    first = policy.prepare("test", ("b", "a"), payload)
    payload["nested"].append("changed")
    detached = first.payload()
    detached["nested"].append("also changed")
    assert first.payload() == {"nested": ["original"]}
    assert first.resources == ("a", "b")
    assert first.fingerprint == policy.prepare("test", ("a", "b"), {"nested": ["original"]}).fingerprint
    assert first.fingerprint != policy.prepare("test", ("a", "b"), payload).fingerprint
    with pytest.raises(FrozenInstanceError):
        first.kind = "changed"


def test_direct_effect_has_no_approval():
    with pytest.raises(PermissionError):
        policy.consume(plan())


def test_operation_hud_is_required_and_grant_is_one_use(operation_hud):
    original = plan()
    effects = []

    def execute(current):
        with pytest.raises(PermissionError):
            policy.consume(replace(current, payload_json='{"text":"changed"}'))
        policy.consume(current)
        effects.append(current.payload())
        with pytest.raises(PermissionError):
            policy.consume(current)
        return "[COMPLETED]"

    assert "PENDING" in policy.request(original, title="Test", detail="review", execute=execute)
    assert effects == []
    callback = confirm._pending.run
    confirm.resolve(True, operation_hud.shown[-1][2])
    assert operation_hud.finished.wait(2)
    assert effects == [{"text": "private"}]
    with ThreadPoolExecutor(max_workers=4) as pool:
        assert all("REJECTED" in result for result in pool.map(lambda _: callback(), range(8)))
    assert "private" not in " ".join(operation_hud.logs)
    with pytest.raises(PermissionError):
        policy.consume(original)


@pytest.mark.parametrize("reason", ["cancelled", "expired", "unavailable", "busy"])
def test_cancel_expiry_missing_ui_busy_never_execute(reason, operation_hud, monkeypatch):
    effects = []
    current = plan()
    if reason == "unavailable":
        confirm.bind(None, None)
    if reason == "busy":
        confirm.request("other", "Other", "Other", lambda: "done")
    result = policy.request(current, title="Test", detail="review", execute=lambda _: effects.append(True))
    if reason == "cancelled":
        callback = confirm._pending.run
        confirm.resolve(False, operation_hud.shown[-1][2])
        assert "REJECTED" in callback()
    elif reason == "expired":
        callback = confirm._pending.run
        monkeypatch.setattr(policy.time, "monotonic", lambda: current.expires_at + 1)
        assert "EXPIRED" in callback()
    elif reason == "busy":
        assert "BUSY" in result
    else:
        assert "not available" in result
    assert effects == []


def test_exception_is_unknown_never_payload_or_retry(operation_hud):
    def execute(current):
        policy.consume(current)
        raise RuntimeError("private payload and credentials")

    policy.request(plan(), title="Test", detail="review", execute=execute)
    callback = confirm._pending.run
    confirm.resolve(True, operation_hud.shown[-1][2])
    assert operation_hud.finished.wait(2)
    assert "OUTCOME_UNKNOWN" in " ".join(operation_hud.logs)
    assert "credentials" not in " ".join(operation_hud.logs)
    assert "REJECTED" in callback()


def test_same_plan_cannot_be_submitted_twice(operation_hud):
    current = plan()
    effects = []
    policy.request(current, title="Test", detail="review", execute=lambda _: effects.append(True))
    confirm.resolve(False, operation_hud.shown[-1][2])
    assert "REJECTED" in policy.request(current, title="Test", detail="review", execute=lambda _: effects.append(True))
    assert len(operation_hud.shown) == 1 and not effects


def test_shared_grant_survives_context_copy_but_only_one_sink_can_consume(operation_hud):
    from contextvars import copy_context
    winners = []

    def execute(current):
        def attempt(_):
            try:
                policy.consume(current)
                winners.append(True)
            except PermissionError:
                pass
        contexts = [copy_context() for _ in range(8)]
        with ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda ctx: ctx.run(attempt, None), contexts))
        return "done"

    policy.request(plan(), title="Test", detail="review", execute=execute)
    confirm.resolve(True, operation_hud.shown[-1][2])
    assert operation_hud.finished.wait(2)
    assert len(winners) == 1
