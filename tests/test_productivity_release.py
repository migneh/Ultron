"""Local-first release integration. No live network, accounts or desktop effects."""
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone

import pytest

from ultron.core import confirm
from ultron.core import local_documents as docs
from ultron.core import local_productivity as local
from ultron.core import productivity_store as store
from ultron.core.action_loader import ActionRegistry, _validate
from ultron.core.local_calculator import calculate, convert
from ultron.core.productivity_api import dispatch
from ultron.core.productivity_setup import configure_root


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    monkeypatch.setattr(store, "database_path", lambda: tmp_path / "private" / "productivity.sqlite3")
    root = tmp_path / "docs"
    root.mkdir()
    return root


def call(name, **args):
    return json.loads(dispatch(name, args))


@pytest.mark.parametrize("expression,value", [("0.1+0.2", "0.3"), ("(10-2)*3/4", "6"),
                                               ("2**-3", "0.125"), ("10%3", "1"),
                                               ("-(-2)", "2"), ("1e2/4", "25"), ("0", "0")])
def test_decimal_arithmetic(expression, value):
    assert calculate(expression) == value


@pytest.mark.parametrize("expression", ["__import__('os')", "open('/etc/passwd')", "x+1", "True", "[1]", "2**100000", "1/0", "0x10", "1_000", "1,2", "1e999", "'hello'", "2<<3", "1+" * 300, "(10**12)**12"])
def test_rejected_expressions(expression):
    with pytest.raises(ValueError):
        calculate(expression)


@pytest.mark.parametrize("value,source,destination,expected", [("1", "in", "cm", "2.54"), ("32", "F", "C", "0"),
                                                            ("0", "C", "K", "273.15"), ("1", "h", "s", "3.6E+3"),
                                                            ("1000", "mL", "L", "1")])
def test_unit_conversion(value, source, destination, expected):
    assert convert(value, source, destination) == expected


@pytest.mark.parametrize("value,source,destination", [("1", "m", "kg"), ("1", "USD", "TND"), ("-1", "K", "C"), ("nan", "m", "cm"), ("1,2", "m", "cm")])
def test_invalid_units(value, source, destination):
    with pytest.raises(ValueError):
        convert(value, source, destination)


def test_task_persistence_versions_dates_and_local_notices(workspace):
    task = local.tasks("create", title="Test", notes="Private", due_date="2026-12-01")
    assert local.tasks("get", task_id=task["id"])["notes"] == "Private"
    assert local.tasks("list")[0]["version"] == 1
    changed = local.tasks("update", task_id=task["id"], state="done", expected_version=1)
    assert changed["version"] == 2 and changed["state"] == "done"
    with pytest.raises(ValueError):
        local.tasks("update", task_id=task["id"], state="todo", expected_version=1)
    digest = local.notifications("digest")
    assert len(digest["notices"]) == 2
    local.notifications("acknowledge", notice_id=digest["notices"][0]["id"])
    assert local.notifications("clear_acknowledged")["removed"] == 1
    assert len(local.notifications("digest")["notices"]) == 1


def test_concurrent_task_version_only_one_winner(workspace):
    task = local.tasks("create", title="Concurrent")

    def update(_):
        try:
            return local.tasks("update", task_id=task["id"], state="doing", expected_version=1)["version"]
        except ValueError:
            return "conflict"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(update, range(2)))
    assert results.count(2) == 1 and results.count("conflict") == 1


def test_evidence_is_never_auto_verified_or_fetched(workspace):
    item = local.evidence("add", claim="A claim", url="https://example.org/paper", quote="A supplied quote", locator="page 2")
    assert item["verification"] == "unverified_user_supplied" and not item["fetched_by_tool"]
    assert local.evidence("get", evidence_id=item["id"])["locator"] == "page 2"
    assert len(local.evidence("list")) == 1
    with pytest.raises(ValueError):
        local.evidence("add", claim="Claim", url="https://token@example.org/")


def test_quiet_hours_cross_midnight_and_no_external_delivery(workspace, monkeypatch):
    local.notifications("quiet_hours", timezone="UTC", start_hour=22, end_hour=7)
    monkeypatch.setattr(local, "now", lambda: datetime(2026, 11, 23, 23, tzinfo=timezone.utc))
    assert local.notifications("digest")["quiet_now"]
    monkeypatch.setattr(local, "now", lambda: datetime(2026, 11, 23, 12, tzinfo=timezone.utc))
    assert not local.notifications("digest")["quiet_now"]
    assert "local inbox only" in local.notifications("digest")["delivery"]


def test_no_implicit_document_grant_or_model_supplied_grant(workspace):
    source = workspace / "private.txt"
    source.write_text("private")
    with pytest.raises(ValueError):
        docs.read_text(str(source))
    assert call("safe_sharing", action="preview", path=str(source), approved=True)["status"] == "rejected"
    configure_root(str(workspace))
    assert docs.read_text(str(source))[1] == "private"
    configure_root(str(workspace), remove=True)
    with pytest.raises(ValueError):
        docs.read_text(str(source))


def test_text_and_csv_comparison_provenance(workspace):
    configure_root(str(workspace))
    a, b = workspace / "a.csv", workspace / "b.csv"
    a.write_text('item,amount\ncoffee,1\n')
    b.write_text('item,amount\ncoffee,2\n')
    result = docs.compare(str(a), str(b))
    assert "@@" in result["diff"] and "-coffee,1" in result["diff"]
    assert result["left_sha256"] != result["right_sha256"]
    assert not result["csv"]["cells_identical"] and not result["truncated"]


def test_comparison_explicitly_marks_output_truncation(workspace):
    configure_root(str(workspace))
    a, b = workspace / "a.txt", workspace / "b.txt"
    a.write_text("\n".join(f"old-{i}" for i in range(500)))
    b.write_text("\n".join(f"new-{i}" for i in range(500)))
    assert docs.compare(str(a), str(b))["truncated"]


@pytest.mark.parametrize("suffix,content", [(".pdf", b"PDF"), (".txt", b"\xff"), (".txt", b"x" * 24001), (".txt", b"a\x00b")])
def test_unsupported_inputs_fail_closed(workspace, suffix, content):
    configure_root(str(workspace))
    path = workspace / ("bad" + suffix)
    path.write_bytes(content)
    assert call("safe_sharing", action="preview", path=str(path))["status"] == "rejected"


def test_symlink_inputs_cannot_bypass_roots(workspace, tmp_path):
    configure_root(str(workspace))
    outside = tmp_path / "outside.txt"
    outside.write_text("secret")
    link = workspace / "link.txt"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("Symlinks unavailable")
    with pytest.raises(ValueError):
        docs.read_text(str(link))


def test_redaction_preview_review_then_exact_verified_publish(workspace, operation_hud):
    configure_root(str(workspace))
    source = workspace / "source.md"
    source.write_text("Email alice@example.org; PIN SECRET; phone +216 12 345 678", encoding="utf-8")
    result = docs.preview(str(source), ["SECRET"])
    assert not list(workspace.glob("*.txt"))
    assert "alice@example.org" not in result["output_text"] and "SECRET" not in result["output_text"]
    output = workspace / "reviewed.txt"
    pending = call("safe_sharing", action="publish", preview_id=result["preview_id"], destination=str(output))
    assert pending["status"] == "needs_approval" and not output.exists()
    confirm.resolve(True, operation_hud.shown[-1][2])
    assert operation_hud.finished.wait(2)
    assert output.read_text() == result["output_text"]
    assert "alice@example.org" in source.read_text()


@pytest.mark.parametrize("change", ["source", "grant", "discard", "destination"])
def test_publication_rechecks_source_grants_preview_and_conflicts(workspace, operation_hud, change):
    configure_root(str(workspace))
    source = workspace / "source.txt"
    source.write_text("Private alice@example.org")
    result = docs.preview(str(source))
    output = workspace / "out.txt"
    docs.publish(result["preview_id"], str(output))
    if change == "source":
        source.write_text("Changed")
    elif change == "grant":
        configure_root(str(workspace), remove=True)
    elif change == "discard":
        docs.discard(result["preview_id"])
    else:
        output.write_text("existing")
    confirm.resolve(True, operation_hud.shown[-1][2])
    assert operation_hud.finished.wait(2)
    assert not output.exists() if change != "destination" else output.read_text() == "existing"


def test_new_actions_discover_and_dispatch_with_real_contracts(workspace):
    import importlib
    for name, args in [("calculator", {"action": "calculate", "expression": ".1+.2"}),
                       ("task_board", {"action": "create", "title": "Test"}),
                       ("notification_center", {"action": "digest"}),
                       ("evidence_ledger", {"action": "list"}),
                       ("google_workspace", {"action": "status"})]:
        module = importlib.import_module('ultron.actions.' + name)
        record = _validate(module, name + ".py")
        assert record.valid
        registry = ActionRegistry({name: record}, lambda _: None)
        assert json.loads(registry.run(name, args))["status"] == "completed"


@pytest.mark.parametrize("tool", ["calculator", "task_board", "safe_sharing", "evidence_ledger", "notification_center", "google_workspace"])
def test_no_tool_arguments_can_forge_access(tool, workspace):
    assert call(tool, action="status", approved=True, scopes=["all"])["status"] == "rejected"


def test_task_edits_and_due_date_clear_require_version(workspace):
    task = local.tasks("create", title="Original", due_date="2026-12-01")
    edited = local.tasks("update", task_id=task["id"], expected_version=1, title="Renamed", notes="Reviewed", due_date="")
    assert edited["title"] == "Renamed" and edited["notes"] == "Reviewed"
    assert edited["due_date"] is None and edited["state"] == "todo"


@pytest.mark.parametrize("value", [False, 20261201, "20261201", "tomorrow", "2026-02-30", "2026-12-01T12:00:00Z"])
def test_due_dates_never_pretend_to_schedule_times(workspace, value):
    assert call("task_board", action="create", title="Test", due_date=value)["status"] == "rejected"


def test_expired_preview_and_cancellation_do_not_write(workspace, operation_hud):
    configure_root(str(workspace))
    source = workspace / "source.txt"
    source.write_text("alice@example.org")
    result = docs.preview(str(source))
    output = workspace / "out.txt"
    docs.publish(result["preview_id"], str(output))
    confirm.resolve(False, operation_hud.shown[-1][2])
    assert not output.exists()
    with store.connection() as db:
        db.execute("UPDATE previews SET created=0 WHERE id=?", (result["preview_id"],))
    with pytest.raises(ValueError):
        docs.publish(result["preview_id"], str(output))


def test_literals_are_exact_not_arbitrary_regex(workspace):
    configure_root(str(workspace))
    source = workspace / "source.txt"
    source.write_text("الرمز SECRET and SECRET and (a+)+$")
    result = docs.preview(str(source), ["SECRET", "(a+)+$", "SECRET and"])
    assert "SECRET" not in result["output_text"]
    assert "(a+)+$" not in result["output_text"]
    assert "الرمز" in result["output_text"]


def test_notification_expiry_and_deduplication(workspace):
    with store.connection() as db:
        local.notify(db, "Test", "Private", "same")
        local.notify(db, "Test", "Private", "same")
    assert len(local.notifications("digest")["notices"]) == 1
    with store.connection() as db:
        db.execute("UPDATE notices SET expires='2000-01-01T00:00:00+00:00'")
    assert not local.notifications("digest")["notices"]


def test_productivity_concurrency_is_bounded_without_queuing(workspace):
    from ultron.core import productivity_api
    for _ in range(4):
        assert productivity_api._SLOTS.acquire(blocking=False)
    try:
        assert call("calculator", action="calculate", expression="1+1")["status"] == "blocked"
    finally:
        for _ in range(4):
            productivity_api._SLOTS.release()
    assert call("calculator", action="calculate", expression="1+1")["data"]["value"] == "2"


def test_new_document_actions_also_work_via_registry(workspace):
    import importlib
    configure_root(str(workspace))
    path = workspace / "example.txt"
    path.write_text("alice@example.org")
    for name, args in [("document_compare", {"action": "compare", "left_path": str(path), "right_path": str(path)}),
                       ("safe_sharing", {"action": "preview", "path": str(path)})]:
        record = _validate(importlib.import_module('ultron.actions.' + name), name + ".py")
        assert record.valid
        registry = ActionRegistry({name: record}, lambda _: None)
        assert json.loads(registry.run(name, args))["status"] == "completed"
