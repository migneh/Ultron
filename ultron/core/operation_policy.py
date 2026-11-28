"""Host-only immutable operation previews and single-use HUD execution.

This is an in-process approval primitive, not a Python sandbox or a global
permission broker. Callers must put it at effect boundaries and independently
revalidate resources. No model-facing API accepts approval flags or tokens.
Plans and payloads are intentionally not persisted or logged here.
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

from ultron.core import confirm


class _Admission:
    def __init__(self):
        self.lock = threading.Lock()
        self.requested = False


@dataclass(frozen=True)
class OperationPlan:
    operation_id: str
    kind: str
    resources: tuple[str, ...]
    payload_json: str
    fingerprint: str
    expires_at: float  # process-local monotonic time, never persisted
    _admission: _Admission = field(default_factory=_Admission, repr=False, compare=False)

    def payload(self) -> dict:
        """Return a detached copy; callers cannot mutate the approved snapshot."""
        return json.loads(self.payload_json)


def prepare(kind: str, resources: tuple[str, ...], payload: dict) -> OperationPlan:
    if not isinstance(kind, str) or not kind or len(kind) > 100:
        raise ValueError("Invalid operation kind")
    if (not isinstance(resources, tuple) or not 1 <= len(resources) <= 100
            or any(not isinstance(r, str) or not r or len(r) > 200 for r in resources)
            or len(set(resources)) != len(resources)):
        raise ValueError("Invalid operation resources")
    if not isinstance(payload, dict):
        raise ValueError("Invalid operation payload")
    encoded = json.dumps(payload, ensure_ascii=True, sort_keys=True,
                         separators=(",", ":"), allow_nan=False)
    if len(encoded) > 65536:
        raise ValueError("Operation payload too large")
    resources = tuple(sorted(resources))
    digest = hashlib.sha256(json.dumps([kind, resources, encoded],
                                      separators=(",", ":")).encode()).hexdigest()
    return OperationPlan(uuid4().hex, kind, resources, encoded, digest,
                         time.monotonic() + confirm.TIMEOUT_SECONDS)


class _Grant:
    def __init__(self, plan):
        self.plan = plan
        self.used = False
        self.lock = threading.Lock()


_active_grant: ContextVar[_Grant | None] = ContextVar("operation_grant", default=None)


def consume(plan: OperationPlan) -> None:
    """Effect sinks must call this before writing, including alternate callers.

    Context propagates into asyncio tasks submitted by the approved callback.
    The shared locked grant can only be consumed once, even across copied
    contexts. Ordinary direct calls and newly constructed plans have no grant.
    This protects application call paths, not arbitrary malicious Python code.
    """
    grant = _active_grant.get()
    if grant is None:
        raise PermissionError("No host approval")
    with grant.lock:
        if grant.plan is not plan or grant.used or time.monotonic() >= plan.expires_at:
            raise PermissionError("Approval mismatch, replay or expiry")
        grant.used = True


def request(plan: OperationPlan, *, title: str, detail: str,
            execute: Callable[[OperationPlan], str]) -> str:
    """Only the human-confirmation callback may consume this request once.

    Expiry is checked again on the worker thread, not just when the HUD click
    arrives. Failure/partial/unknown effects are never retried by this layer.
    Preview text must be constructed from the plan, not mutable input objects.
    """
    if time.monotonic() >= plan.expires_at:
        return "[EXPIRED] Operation expired; create a fresh preview. Nothing sent."
    with plan._admission.lock:
        if plan._admission.requested:
            return "[REJECTED] Plan already submitted; create a fresh preview. Nothing new approved."
        plan._admission.requested = True
    lock = threading.Lock()
    consumed = False

    def stop(_reason):
        nonlocal consumed
        with lock:
            consumed = True

    def approved():
        nonlocal consumed
        with lock:
            if consumed:
                return "[REJECTED] Operation already consumed or cancelled; no new effect."
            consumed = True
        if time.monotonic() >= plan.expires_at:
            return "[EXPIRED] Operation expired before execution; no effect."
        token = _active_grant.set(_Grant(plan))
        try:
            return execute(plan)
        except Exception:
            # An executor may have performed a partial effect before raising.
            # Never expose payload-bearing exceptions or advertise safe retry.
            return "[OUTCOME_UNKNOWN] Execution interrupted. Check the destination; do not retry automatically."
        finally:
            _active_grant.reset(token)

    return confirm.request(key=f"operation:{plan.operation_id}", title=title,
                           detail=detail, run=approved, on_cancel=stop)


def require_consumed(kinds: tuple[str, ...]) -> None:
    """Delegated effect/inverse helpers require a consumed host callback context.

    This is not a new grant and does not authorize an independent operation.
    Trusted executors must still bind and validate their exact snapshot. Useful
    for private low-level helpers also reached by registered session inverses.
    """
    grant = _active_grant.get()
    if grant is None:
        raise PermissionError("No consumed host operation")
    with grant.lock:
        if not grant.used or grant.plan.kind not in kinds:
            raise PermissionError("Wrong/unconsumed host operation")
