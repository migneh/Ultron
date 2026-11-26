"""No real recording, research, Telegram calls, or external delivery."""
import ast
import json
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from ultron.actions import drone_swarm as swarm
from ultron.actions import meeting_scribe as meeting
from ultron.actions import send_message as message_action
from ultron.core import confirm
from ultron.core import messaging as messaging
from ultron.core import report_sharing as sharing
from ultron.core.action_loader import ActionRegistry, _validate
from ultron.core.background_jobs import JobService
from ultron.core.web_research import ResearchReport


@pytest.fixture
def flow(tmp_path, monkeypatch, operation_hud):
    monkeypatch.setattr(messaging.requests, "post", lambda *a, **kw: pytest.fail("Real HTTP forbidden"))
    root = tmp_path / "reports"
    root.mkdir()
    monkeypatch.setattr(swarm, "_REPORTS_DIR", root)
    monkeypatch.setattr(meeting, "_MEETINGS_DIR", root)
    monkeypatch.setattr(meeting, "_MEETINGS_LOG", root / "meetings_index.json")
    path = tmp_path / "outbox.sqlite3"
    sends, lookups = [], []

    class Transport:
        def verify(self, receiver):
            lookups.append(receiver)
            return {"sender_id": "777", "sender_name": "Test bot", "recipient_id": receiver,
                    "recipient_name": "Test recipient", "recipient_type": "private"}

        def send(self, record):
            sends.append(dict(record))
            return messaging.Outcome("sent", receipt="telegram:123:55")

    monkeypatch.setattr(message_action, "database_path", lambda: path)
    transport = Transport()
    monkeypatch.setattr(message_action, "_transport", lambda: transport)
    jobs = JobService(tmp_path / "jobs.sqlite3")
    monkeypatch.setattr(swarm, "get_service", lambda: jobs)
    yield SimpleNamespace(root=root, sends=sends, lookups=lookups, transport=transport,
                          store=messaging.Outbox(path), hud=operation_hud, jobs=jobs)
    assert jobs.shutdown()["workers_still_running"] == 0


def approve(flow):
    confirm.resolve(True, flow.hud.shown[-1][2])
    assert flow.hud.finished.wait(2)


def dispatch(module, parameters):
    rec = _validate(module, "test.py")
    assert rec.valid, rec.error
    return ActionRegistry({rec.name: rec}, lambda _: None).run(rec.name, parameters)


def test_swarm_explicit_share_uses_exact_snapshot_and_recipient(flow):
    report = flow.root / "report.md"
    report.write_text("# Test\nمرحبا — exact report", encoding="utf-8")
    result = dispatch(swarm, {"action": "share_report", "report_name": report.name, "receiver": "123"})
    assert "PENDING" in result and not flow.sends
    assert "123" in flow.hud.shown[-1][1]
    report.write_text("Changed after preview", encoding="utf-8")
    approve(flow)
    assert len(flow.sends) == 1
    assert flow.sends[0]["body"] == "# Test\nمرحبا — exact report"
    assert flow.sends[0]["recipient_id"] == "123"
    assert flow.store.list()[0]["state"] == "sent"


def test_cancel_share_and_repeated_request_never_send(flow):
    (flow.root / "report.md").write_text("private", encoding="utf-8")
    args = {"action": "share_report", "report_name": "report.md", "receiver": "123"}
    dispatch(swarm, args)
    dispatch(swarm, args)
    assert len(flow.hud.shown) == 1
    confirm.resolve(False, flow.hud.shown[-1][2])
    assert not flow.sends
    assert flow.store.list()[0]["state"] == "cancelled"


@pytest.mark.parametrize("name", ["../secret.md", "/tmp/secret.md", "sub/report.md", "sub\\report.md", "report", "*.md"])
def test_invalid_report_selection_never_looks_up_recipient(flow, name):
    result = dispatch(swarm, {"action": "share_report", "report_name": name, "receiver": "123"})
    assert "rejected" in result
    assert not flow.lookups and not flow.hud.shown


def test_symlink_report_not_shared(flow, tmp_path):
    outside = tmp_path / "private.md"
    outside.write_text("private", encoding="utf-8")
    try:
        (flow.root / "link.md").symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        sharing.read_report(flow.root, "link.md")
    assert not flow.lookups


@pytest.mark.parametrize("text", ["x" * 16001, "x" * 4001, "😀" * 2001, "\x00private"])
def test_large_or_invalid_reports_never_truncated_or_sent(flow, text):
    (flow.root / "report.md").write_text(text, encoding="utf-8")
    result = dispatch(swarm, {"action": "share_report", "report_name": "report.md", "receiver": "123"})
    assert "rejected" in result
    assert not flow.lookups and not flow.hud.shown and not flow.sends


def test_no_default_or_fuzzy_recipient(flow):
    (flow.root / "report.md").write_text("private", encoding="utf-8")
    for receiver in ("", "Alice", "@username"):
        assert "rejected" in dispatch(swarm, {"action": "share_report", "report_name": "report.md", "receiver": receiver})
    assert not flow.lookups and not flow.hud.shown


def test_meeting_stop_saves_factual_metadata_locally_without_approval_or_send(flow, monkeypatch):
    from ultron.core.meeting_recording import Recorder, Recording
    recorder = Recorder()
    session = Recording("Private meeting")
    session.started_mono -= 60
    session.ended_mono = time.monotonic()
    session.chunks = [np.zeros((1024, 1), dtype=np.int16)]
    session.samples = 1024
    session.bytes_used = 2048
    session.state = "READY"
    recorder._session = session
    monkeypatch.setattr(meeting, "_RECORDER", recorder)
    result = meeting.stop_recording()
    assert "No transcription or content analysis was performed" in result
    assert "Session objectives confirmed" not in result
    assert "Verify project delivery milestones" not in result
    records = json.loads(meeting._MEETINGS_LOG.read_text())
    assert records[0]["summary"] == result
    assert (flow.root / records[0]["filename"]).is_file()
    assert not flow.sends and not flow.lookups and not flow.hud.shown
    # Sharing the selected metadata is a separate approved operation, not audio.
    output = dispatch(meeting, {"action": "share", "filename": records[0]["filename"], "receiver": "123"})
    assert "PENDING" in output and not flow.sends
    approve(flow)
    assert flow.sends[0]["body"] == result


@pytest.mark.parametrize("records", [[], [{"filename": "old.wav"}],
                                     [{"filename": "old.wav", "summary": "one"}, {"filename": "old.wav", "summary": "two"}]])
def test_missing_legacy_or_ambiguous_meeting_summary_not_invented(flow, records):
    meeting._MEETINGS_LOG.write_text(json.dumps(records), encoding="utf-8")
    assert "rejected" in dispatch(meeting, {"action": "share", "filename": "old.wav", "receiver": "123"})
    assert not flow.lookups and not flow.hud.shown


def test_swarm_research_completion_is_local_only(flow, monkeypatch):
    monkeypatch.setattr(swarm, "collect_research", lambda *args: fake_report())
    result = json.loads(swarm.swarm_parallel_execute("test topic", subtasks=["test topic"]))
    record = wait_job(flow.jobs, result["job"]["id"])
    assert (flow.root / record["result"]["report_name"]).is_file()
    assert not flow.sends and not flow.lookups and not flow.hud.shown


@pytest.mark.parametrize("module", [swarm, meeting])
def test_modules_have_no_legacy_telegram_transport_or_automatic_sharing_calls(module):
    tree = ast.parse(Path(module.__file__).read_text(encoding="utf-8"))
    forbidden = {"send_telegram_alert", "get_telegram_bot", "_send_telegram_brief", "_notify_boss_telegram"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name):
                assert node.func.id not in forbidden
            if isinstance(node.func, ast.Attribute):
                assert node.func.attr not in {"post", "send_message", "send_photo"}
    # Shared outbox is invoked only in the explicitly selected share branch/helper.
    if module is swarm:
        handler = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "drone_swarm")
        assert any(isinstance(n, ast.If) and ast.unparse(n.test) == "act == 'share_report'" for n in ast.walk(handler))


def test_unknown_share_outcome_blocks_duplicate_submission(flow, monkeypatch):
    (flow.root / "report.md").write_text("private", encoding="utf-8")

    def uncertain(record):
        flow.sends.append(dict(record))
        return messaging.Outcome("outcome_unknown", "Check destination manually")

    monkeypatch.setattr(flow.transport, "send", uncertain)
    args = {"action": "share_report", "report_name": "report.md", "receiver": "123"}
    dispatch(swarm, args)
    approve(flow)
    assert flow.store.list()[0]["state"] == "outcome_unknown"
    assert "PENDING" not in dispatch(swarm, args)
    assert len(flow.sends) == 1 and len(flow.hud.shown) == 1


def test_expired_share_never_sends(flow):
    (flow.root / "report.md").write_text("private", encoding="utf-8")
    dispatch(swarm, {"action": "share_report", "report_name": "report.md", "receiver": "123"})
    confirm._pending.at -= confirm.TIMEOUT_SECONDS + 1
    confirm.resolve(True, flow.hud.shown[-1][2])
    assert not flow.sends
    assert flow.store.list()[0]["state"] == "expired"


def test_parallel_and_market_completion_do_not_request_sharing(flow, monkeypatch):
    monkeypatch.setattr(swarm, "collect_research", lambda *args: fake_report())
    result = json.loads(swarm.swarm_parallel_execute("mock objective"))
    assert "No Telegram notification sent" in result["note"]
    wait_job(flow.jobs, result["job"]["id"])
    monkeypatch.setattr(swarm, "_market_price", lambda _: 100)
    result = json.loads(swarm.launch_drone("market", "BTC", iterations=1))
    record = wait_job(flow.jobs, result["job"]["id"])
    assert (flow.root / record["result"]["report_name"]).is_file()
    assert not flow.lookups and not flow.sends and not flow.hud.shown


def wait_job(service, job_id):
    with service._lock:
        worker = service._workers.get(job_id)
    if worker:
        worker[0].join(3)
        assert not worker[0].is_alive()
    return service.get(job_id)


def fake_report():
    return ResearchReport(query="Mock", results=[{"title": "Source", "snippet": "Unverified", "url": "https://example.org/", "retrieved_at": "test", "published_at": ""}])
