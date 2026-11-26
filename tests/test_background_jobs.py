"""Durable jobs and research collection with deterministic fake workers/sources."""
import json
import subprocess
import sys
import threading
import time

import pytest

from ultron.actions import background_jobs as action
from ultron.actions import drone_swarm as swarm
from ultron.core.background_jobs import JobService
from ultron.core.web_research import ResearchReport


def wait_job(service, job_id):
    with service._lock:
        worker = service._workers.get(job_id)
    if worker:
        worker[0].join(3)
        assert not worker[0].is_alive()
    return service.get(job_id)


@pytest.fixture
def service(tmp_path):
    instance = JobService(tmp_path / "jobs.sqlite3", capacity=2)
    yield instance
    assert instance.shutdown()["workers_still_running"] == 0


def test_job_is_persisted_before_worker_starts_and_completed_later(service):
    entered, release = threading.Event(), threading.Event()

    def worker(ctx):
        assert service.get(ctx.job_id)["state"] == "running"
        entered.set()
        assert release.wait(2)
        ctx.call()
        return {"state": "completed", "count": 1}

    job = service.submit("swarm_research", worker)
    try:
        assert entered.wait(2)
        assert job["id"] and service.get(job["id"])["state"] == "running"
    finally:
        release.set()
    result = wait_job(service, job["id"])
    assert result["state"] == "completed" and result["calls"] == 1
    assert result["result"] == {"count": 1}


def test_cancel_is_cooperative_and_cannot_free_capacity_while_blocked(service):
    entered, release = threading.Event(), threading.Event()

    def blocked(ctx):
        entered.set()
        assert release.wait(2)
        ctx.checkpoint()
        return {"state": "completed"}

    first = service.submit("swarm_research", blocked)
    second = service.submit("swarm_research", blocked)
    try:
        assert entered.wait(2)
        assert service.cancel(first["id"])["state"] == "cancel_requested"
        with pytest.raises(ValueError):
            service.submit("swarm_research", lambda ctx: {"state": "completed"})
        assert len(service._workers) == 2
    finally:
        release.set()
    assert wait_job(service, first["id"])["state"] == "cancelled"
    wait_job(service, second["id"])


def test_other_runtime_cannot_exceed_admission_but_can_request_cancel(service):
    entered, release = threading.Event(), threading.Event()

    def blocked(ctx):
        entered.set()
        assert release.wait(2)
        ctx.checkpoint()
        return {"state": "completed"}

    job = service.submit("swarm_research", blocked)
    other = JobService(service.path)
    try:
        assert entered.wait(2)
        assert not other.recover()
        with pytest.raises(ValueError):
            other.submit("swarm_research", lambda ctx: {"state": "completed"})
        other.cancel(job["id"])
        assert service.get(job["id"])["cancel_requested"]
    finally:
        release.set()
        other.shutdown()
    assert wait_job(service, job["id"])["state"] == "cancelled"


def test_deadline_is_not_claimed_as_hard_thread_termination(service):
    entered, release = threading.Event(), threading.Event()

    def late(ctx):
        ctx.end = time.monotonic() - 1
        entered.set()
        assert release.wait(2)
        ctx.checkpoint()
        return {"state": "completed"}

    job = service.submit("swarm_research", late)
    try:
        assert entered.wait(2)
        with service._db() as db:
            db.execute("UPDATE jobs SET deadline=0 WHERE id=?", (job["id"],))
        status = service.get(job["id"])
        assert status["overdue"] and status["state"] == "running"
        assert job["id"] in service._workers
    finally:
        release.set()
    assert wait_job(service, job["id"])["state"] == "deadline_exceeded"


def test_possible_effect_then_cancellation_is_unknown_not_rolled_back(service):
    entered, release = threading.Event(), threading.Event()

    def effect(ctx):
        ctx.begin_effect()
        entered.set()
        assert release.wait(2)
        return {"state": "completed"}

    job = service.submit("swarm_research", effect)
    try:
        assert entered.wait(2)
        service.cancel(job["id"])
    finally:
        release.set()
    assert wait_job(service, job["id"])["state"] == "outcome_unknown"


def test_call_budget_is_persisted_and_enforced(service):
    def worker(ctx):
        ctx.call()
        ctx.call()
        return {"state": "completed"}

    job = service.submit("swarm_research", worker, call_limit=1)
    result = wait_job(service, job["id"])
    assert result["state"] == "failed" and result["calls"] == 1


@pytest.mark.parametrize("outcome", [{"state": "invented"}, {"state": "completed", "data": "x" * 9000},
                                     {"state": "completed", "data": {1, 2}}, {"state": "completed", "value": float("nan")}])
def test_invalid_or_oversized_results_never_leave_false_success(service, outcome):
    job = service.submit("swarm_research", lambda ctx: outcome)
    result = wait_job(service, job["id"])
    assert result["state"] == "failed"
    assert "data" not in result["result"]


def test_exception_details_not_persisted_and_terminal_cancel_is_noop(service):
    def worker(ctx):
        raise RuntimeError("SECRET token URL")

    job = service.submit("swarm_research", worker)
    assert wait_job(service, job["id"])["state"] == "failed"
    assert "SECRET" not in json.dumps(service.list())
    assert service.cancel(job["id"])["state"] == "failed"


def test_shutdown_preserves_owner_lock_until_last_worker_exits(service):
    entered, release = threading.Event(), threading.Event()

    def blocked(ctx):
        entered.set()
        assert release.wait(2)
        ctx.checkpoint()
        return {"state": "completed"}

    job = service.submit("swarm_research", blocked)
    assert entered.wait(2)
    assert service.shutdown(timeout=0)["workers_still_running"] == 1
    other = JobService(service.path)
    try:
        assert not other.recover()
    finally:
        release.set()
    assert wait_job(service, job["id"])["state"] == "cancelled"
    assert other.recover()
    other.shutdown()


@pytest.mark.parametrize("stage", ["constructor", "start"])
def test_worker_start_failure_is_terminal_and_releases_slot(service, monkeypatch, stage):
    class BrokenThread:
        def __init__(self, **kwargs):
            if stage == "constructor":
                raise RuntimeError("SECRET")

        def start(self):
            raise RuntimeError("SECRET")

    monkeypatch.setattr(threading, "Thread", BrokenThread)
    job = service.submit("swarm_research", lambda ctx: pytest.fail("No run"))
    assert job["state"] == "failed" and not service._workers


def test_crash_recovery_is_unknown_and_never_replays(tmp_path):
    path = tmp_path / "crash.sqlite3"
    script = '''
import os,sys,threading
from ultron.core.background_jobs import JobService
s=JobService(sys.argv[1])
entered=threading.Event()
def blocked(ctx):
    entered.set()
    threading.Event().wait(60)
job=s.submit('swarm_research',blocked)
assert entered.wait(2)
print(job['id'],flush=True)
os._exit(0)
'''
    result = subprocess.run([sys.executable, "-c", script, str(path)], capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    service = JobService(path)
    try:
        job = service.get(result.stdout.strip())
        assert job["state"] == "outcome_unknown" and not service._workers
        assert "No automatic retry" in job["result"]["note"]
    finally:
        service.shutdown()


def test_history_capacity_and_explicit_metadata_cleanup(tmp_path):
    service = JobService(tmp_path / "tiny.sqlite3", history_limit=1)
    try:
        job = service.submit("swarm_research", lambda ctx: {"state": "completed"})
        wait_job(service, job["id"])
        with pytest.raises(ValueError):
            service.submit("swarm_research", lambda ctx: {"state": "completed"})
        assert service.clear_terminal() == 1
        assert service.list() == []
    finally:
        service.shutdown()


def report(*, issues=None, results=True):
    return ResearchReport(query="Test", issues=issues or [], results=[{
        "title": "Official source", "snippet": "Snippet", "url": "https://example.org/source",
        "retrieved_at": "2026-11-23", "published_at": ""}] if results else [])


@pytest.fixture
def collection(service, tmp_path, monkeypatch):
    monkeypatch.setattr(swarm, "get_service", lambda: service)
    monkeypatch.setattr(action, "get_service", lambda: service)
    root = tmp_path / "reports"
    monkeypatch.setattr(swarm, "_REPORTS_DIR", root)
    return root


@pytest.mark.parametrize("kind,expected", [("sources", "completed"), ("fallback", "partial"), ("empty", "failed"), ("exception", "failed")])
def test_swarm_evidence_outcomes_are_not_fake_convergence(service, collection, monkeypatch, kind, expected):
    def source(*args):
        if kind == "exception":
            raise RuntimeError("SECRET")
        return report(issues=["fallback"] if kind == "fallback" else [], results=kind != "empty")

    monkeypatch.setattr(swarm, "collect_research", source)
    output = json.loads(swarm.swarm_parallel_execute("test", subtasks=["one", "two"]))
    job = wait_job(service, output["job"]["id"])
    assert job["state"] == expected
    if expected in {"completed", "partial"}:
        text = (collection / job["result"]["report_name"]).read_text()
        assert "https://example.org/source" in text
        assert "100% Convergence" not in text and "SECRET" not in text
        assert not job["result"]["verified"]
    else:
        assert not list(collection.glob("*.md"))


def test_cancelled_research_never_publishes_late_result(service, collection, monkeypatch):
    entered, release = threading.Event(), threading.Event()

    def source(*args):
        entered.set()
        assert release.wait(2)
        return report()

    monkeypatch.setattr(swarm, "collect_research", source)
    output = json.loads(swarm.swarm_parallel_execute("test", subtasks=["one"]))
    job_id = output["job"]["id"]
    try:
        assert entered.wait(2)
        service.cancel(job_id)
    finally:
        release.set()
    assert wait_job(service, job_id)["state"] == "cancelled"
    assert not list(collection.glob("*.md"))


@pytest.mark.parametrize("args", [{"action": "launch", "drone_type": "market", "target": "../../secret"},
                                  {"action": "launch", "drone_type": "system", "iterations": 0},
                                  {"action": "launch", "drone_type": "system", "iterations": 10000},
                                  {"action": "launch", "drone_type": "system", "interval": True},
                                  {"action": "parallel_swarm", "directive": "test", "subtasks": ["x"] * 4},
                                  {"action": "nonsense", "directive": "do not implicitly launch"},
                                  {"action": "kill", "drone_id": "all"}])
def test_invalid_swarm_requests_cannot_launch_or_fuzzy_cancel(service, collection, args):
    assert "rejected" in swarm.drone_swarm(**args)
    assert service.list() == []


def test_inspection_tool_cannot_submit_code_or_forge_state(service, collection):
    result = json.loads(action.background_jobs({"action": "submit", "code": "arbitrary"}))
    assert result["status"] == "rejected" and not service.list()
    result = json.loads(action.background_jobs({"action": "list"}))
    assert result["status"] == "completed" and result["data"] == []


def test_unavailable_market_data_is_not_zero_or_completed(service, collection, monkeypatch):
    def unavailable(_):
        raise ValueError("No quote")

    monkeypatch.setattr(swarm, "_market_price", unavailable)
    output = json.loads(swarm.launch_drone("market", "BTC", iterations=1))
    record = wait_job(service, output["job"]["id"])
    assert record["state"] == "failed" and not list(collection.glob("*.md"))


def test_mixed_market_data_is_partial_and_marks_missing_samples(service, collection, monkeypatch):
    values = iter([100, None])

    def quote(_):
        value = next(values)
        if value is None:
            raise ValueError("Unavailable")
        return value

    monkeypatch.setattr(swarm, "_market_price", quote)
    from ultron.core.background_jobs import JobContext
    monkeypatch.setattr(JobContext, "wait", lambda ctx, seconds: ctx.checkpoint())
    output = json.loads(swarm.launch_drone("market", "BTC", interval=5, iterations=2))
    record = wait_job(service, output["job"]["id"])
    assert record["state"] == "partial"
    text = (collection / record["result"]["report_name"]).read_text()
    assert "Sample unavailable" in text and '"usd": 0' not in text


def test_exact_report_read_blocks_traversal_and_fuzzy_matches(collection, service):
    collection.mkdir()
    (collection / "actual.md").write_text("test")
    for name in ("../secret.md", "act", "*.md"):
        assert "rejected" in swarm.drone_swarm(action="reports", report_name=name)
    assert swarm.drone_swarm(action="reports", report_name="actual.md") == "test"


def test_job_tool_uses_real_registry_contract(service, collection):
    from ultron.core.action_loader import ActionRegistry, _validate
    record = _validate(action, "background_jobs.py")
    assert record.valid
    registry = ActionRegistry({record.name: record}, lambda _: None)
    output = json.loads(registry.run("background_jobs", {"action": "list"}))
    assert output["status"] == "completed"


@pytest.mark.parametrize("mirror_error", [False, True])
def test_main_lifecycle_reconciles_then_shuts_down_jobs_without_native_ui(monkeypatch, mirror_error):
    import ast
    from pathlib import Path
    from types import SimpleNamespace

    import ultron.core.android_mirror as mirrors
    import ultron.core.background_jobs as jobs
    import ultron.core.desktop_motion as pointer
    calls = []
    monkeypatch.setattr(pointer, "shutdown_motion", lambda: calls.append("pointer_shutdown") or {"state": "closed"})
    def mirror_shutdown():
        calls.append("mirror_shutdown")
        if mirror_error:
            raise RuntimeError("native shutdown failed")
        return {"state": "no_owned_session"}
    monkeypatch.setattr(mirrors, "shutdown_mirrors", mirror_shutdown)
    monkeypatch.setattr(jobs, "get_service", lambda: calls.append("recover"))
    monkeypatch.setattr(jobs, "shutdown_jobs", lambda: calls.append("shutdown") or {"workers_still_running": 0})
    function = next(node for node in ast.parse(Path("ultron/app.py").read_text()).body
                    if isinstance(node, ast.FunctionDef) and node.name == "main")
    namespace = {
        "ASSETS_DIR": Path("ultron/assets"),
        "UltronUI": lambda _: SimpleNamespace(root=SimpleNamespace(mainloop=lambda: calls.append("mainloop"))),
        "threading": SimpleNamespace(Thread=lambda **_: SimpleNamespace(start=lambda: None)),
    }
    exec(compile(ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[])), "main-hook", "exec"), namespace)
    namespace["main"]()
    assert calls == ["recover", "mainloop", "pointer_shutdown", "mirror_shutdown", "shutdown"]
