"""Developer tools preserve review assistance without executing generated effects."""

import pytest

from ultron.actions import code_helper as helper
from ultron.actions import dev_agent as developer
from ultron.core import confirm
from ultron.core import operation_policy as policy
from ultron.core import productivity_store as store
from ultron.core import source_drafts as drafts


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(drafts, "directory", lambda: tmp_path / "drafts")
    monkeypatch.setattr(store, "database_path", lambda: tmp_path / "private.sqlite3")
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    monkeypatch.setattr(helper, "_generate", lambda prompt: 'raise RuntimeError("inert source")')
    return tmp_path


def capture(monkeypatch):
    seen = {}
    monkeypatch.setattr(confirm, "request", lambda **kw: seen.update(kw) or "pending")
    return seen


def test_no_write_before_approval_and_no_execution(isolated, monkeypatch):
    seen = capture(monkeypatch)
    assert helper.code_helper({"action": "write", "description": "Example"}) == "pending"
    assert not (isolated / "drafts").exists()
    assert 'raise RuntimeError("inert source")' in seen["detail"]
    assert "Not installed" in seen["run"]()
    paths = list((isolated / "drafts").iterdir())
    assert len(paths) == 1 and paths[0].suffix == ".txt"
    assert paths[0].read_text() == 'raise RuntimeError("inert source")'
    assert "REJECTED" in seen["run"]()


def test_draft_headless_and_denied(isolated, monkeypatch):
    assert "have not done it" in drafts.request("Source")
    assert not (isolated / "drafts").exists()
    seen = capture(monkeypatch)
    drafts.request("Source")
    seen["on_cancel"]("cancelled")
    assert "REJECTED" in seen["run"]()
    assert not (isolated / "drafts").exists()


@pytest.mark.parametrize("action", ["run", "execute", "build", "screen_debug"])
def test_privileged_actions_never_reach_provider(isolated, monkeypatch, action):
    monkeypatch.setattr(helper, "_generate", lambda *a: pytest.fail("provider called"))
    assert "disabled" in helper.code_helper({"action": action, "description": "anything"})


def test_legacy_effect_helpers_are_fail_closed(isolated):
    with pytest.raises(PermissionError):
        helper._save_file(isolated / "bad.py", "code")
    with pytest.raises(PermissionError):
        helper._take_screenshot()
    assert "disabled" in helper._run_file(isolated / "bad.py", [], 5)
    assert "disabled" in developer._run_project("python bad.py", isolated)
    assert "disabled" in developer._install_dependencies(["bad"], isolated)
    assert developer._try_auto_install("No module named bad", isolated) is False
    assert developer._open_vscode(isolated) is False
    with pytest.raises(PermissionError):
        developer._write_file()
    with pytest.raises(PermissionError):
        developer._fix_files()
    assert not list(isolated.iterdir())


def test_edit_proposal_does_not_overwrite_source(isolated, monkeypatch):
    seen = capture(monkeypatch)
    original = isolated / "original.py"
    original.write_text("ORIGINAL = 42")
    store.set_setting("document_roots", [str(isolated)])
    assert helper.code_helper({"action": "edit", "file_path": str(original), "description": "improve"}) == "pending"
    assert "original-file overwrite" in seen["detail"]
    seen["run"]()
    assert original.read_text() == "ORIGINAL = 42"


def test_outside_root_read_refused_before_provider(isolated, monkeypatch):
    path = isolated / "source.py"
    path.write_text("secret")
    monkeypatch.setattr(helper, "_generate", lambda *a: pytest.fail("source exfiltration"))
    result = helper.code_helper({"action": "explain", "file_path": str(path)})
    assert "could not be completed" in result


def test_explanation_is_unverified_and_in_memory(isolated):
    result = helper.code_helper({"action": "explain", "code": "print(1)"})
    assert "unverified; no execution" in result
    assert not list(isolated.iterdir())


def test_project_planner_is_inert_and_approval_gated(isolated, monkeypatch):
    seen = capture(monkeypatch)
    assert developer.dev_agent({"description": "a project"}) == "pending"
    assert not (isolated / "drafts").exists()
    assert "Not installed" in seen["run"]()
    assert not list(isolated.rglob("*.py"))


def test_arbitrary_output_path_not_accepted(isolated, monkeypatch):
    monkeypatch.setattr(helper, "_generate", lambda *a: pytest.fail("provider called"))
    result = helper.code_helper({"action": "write", "description": "test", "output_path": str(isolated / "bad.py")})
    assert "disabled" in result and not list(isolated.iterdir())


def test_draft_effect_requires_grant(isolated):
    plan = policy.prepare("source_draft.save", ("local_review_drafts",), {"source": "text"})
    with pytest.raises(PermissionError):
        drafts._save(plan)


@pytest.mark.parametrize("source", ["", "\x00", "x" * 64001, None])
def test_invalid_drafts_refused_without_side_effect(isolated, source):
    with pytest.raises(ValueError):
        drafts.request(source)
    assert not list(isolated.iterdir())


def test_symlink_draft_directory_refused(isolated, monkeypatch):
    other = isolated / "other"
    other.mkdir()
    link = isolated / "linked"
    link.symlink_to(other, target_is_directory=True)
    monkeypatch.setattr(drafts, "directory", lambda: link)
    with pytest.raises(ValueError):
        drafts.request("code")
    assert not list(other.iterdir())


def test_existing_draft_never_overwritten(isolated, monkeypatch):
    seen = capture(monkeypatch)
    original = policy.prepare
    plans = []
    def prepare(*a, **kw):
        plan = original(*a, **kw)
        plans.append(plan)
        return plan
    monkeypatch.setattr(policy, "prepare", prepare)
    drafts.request("new")
    root = drafts.directory()
    root.mkdir()
    path = root / f"{plans[0].operation_id}.txt"
    path.write_text("existing")
    assert "OUTCOME_UNKNOWN" in seen["run"]()
    assert path.read_text() == "existing"


def test_static_inventory_never_imports_application_modules():
    from scripts.audit_privileged_sinks import inventory
    rows = list(inventory())
    assert rows and all(row[-1] == "unclassified_manual_trace_required" for row in rows)
    assert any(row[0] == "ultron/actions/android_bridge.py" for row in rows)
