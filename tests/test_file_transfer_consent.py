"""Temporary-file effects only; no native Trash or user files."""
from pathlib import Path

import pytest

from ultron.actions import file_controller as files
from ultron.core import confirm, undo
from ultron.core import file_safety as safety
from ultron.core import operation_policy as policy


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "_SAFE_ROOTS", [tmp_path])
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    undo.clear()
    yield tmp_path
    undo.clear()


def capture(monkeypatch):
    requests = []
    monkeypatch.setattr(confirm, "request", lambda **kw: requests.append(kw) or "pending")
    return requests


def setup(rig):
    src, dst = rig / "source", rig / "destination"
    src.write_text("approved bytes")
    return src, dst


@pytest.mark.parametrize("action", ["move", "copy", "rename"])
def test_headless_direct_helpers_no_effect(rig, action):
    src, dst = setup(rig)
    result = getattr(files, action + "_file")(str(src), **({"new_name": dst.name} if action == "rename" else {"destination": str(dst)}))
    assert "have not done it" in result
    assert src.exists() and not dst.exists() and not undo.can_undo()


@pytest.mark.parametrize("copy", [True, False])
def test_exact_approval_and_separate_undo(rig, monkeypatch, copy):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    message, callback = safety.transfer(src, dst, copy=copy, allowed=files._is_safe_path)
    assert message == "pending" and callback is None and not undo.can_undo()
    assert str(src) in requests[0]["detail"] and str(dst) in requests[0]["detail"]
    assert "Copied:" in requests[0]["run"]() if copy else "Moved:" in requests[0]["run"]()
    assert dst.read_text() == "approved bytes"
    assert "REJECTED" in requests[0]["run"]()
    assert undo.undo_last() == "pending" and dst.exists()
    assert "Undo callback returned" in requests[1]["run"]()
    assert src.read_text() == "approved bytes" and not dst.exists()
    assert "REJECTED" in requests[1]["run"]()


def test_denial_no_effect(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.move_file(str(src), destination=str(dst))
    requests[0]["on_cancel"]("cancelled")
    assert "REJECTED" in requests[0]["run"]()
    assert src.exists() and not dst.exists()


def test_expired_no_effect(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(dst))
    monkeypatch.setattr(policy.time, "monotonic", lambda: float("inf"))
    assert "EXPIRED" in requests[0]["run"]() and not dst.exists()


@pytest.mark.parametrize("change", ["edit", "replace", "delete", "symlink"])
def test_stale_source_no_transfer(rig, monkeypatch, change):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.move_file(str(src), destination=str(dst))
    if change == "edit":
        src.write_text("later")
    elif change == "replace":
        other = rig / "other"
        other.write_text("approved bytes")
        other.replace(src)
    elif change == "delete":
        src.unlink()
    else:
        src.unlink()
        src.symlink_to(rig / "other")
    result = requests[0]["run"]()
    assert "Moved:" not in result and not dst.exists() and not undo.can_undo()


def test_revoked_root_no_transfer(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.move_file(str(src), destination=str(dst))
    monkeypatch.setattr(files, "_SAFE_ROOTS", [])
    assert "OUTCOME_UNKNOWN" in requests[0]["run"]()
    assert src.exists() and not dst.exists()


def test_destination_occupied_after_approval_no_retarget(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(dst))
    dst.mkdir()
    assert "OUTCOME_UNKNOWN" in requests[0]["run"]()
    assert not list(dst.iterdir()) and src.exists()


def test_directory_destination_expanded_once_before_approval(rig, monkeypatch):
    src, folder = setup(rig)
    folder.mkdir()
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(folder))
    assert str(folder / src.name) in requests[0]["detail"]
    assert "Copied:" in requests[0]["run"]()
    assert (folder / src.name).exists()


def test_parent_replaced_after_approval_no_transfer(rig, monkeypatch):
    src, _ = setup(rig)
    folder = rig / "folder"
    folder.mkdir()
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(folder / "copy"))
    folder.rename(rig / "old")
    folder.mkdir()
    assert "parent identity changed" in requests[0]["run"]()
    assert not list(folder.iterdir())


def test_copy_staging_failed_publication_preserves_competitor(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(dst))
    real = safety.os.link
    def race(source, destination, **kw):
        dst.write_text("competitor")
        return real(source, destination, **kw)
    monkeypatch.setattr(safety.os, "link", race)
    assert "OUTCOME_UNKNOWN" in requests[0]["run"]()
    assert dst.read_text() == "competitor" and src.read_text() == "approved bytes"
    assert not list(rig.glob(".ultron-copy-*.part"))


def test_move_unlink_failure_retains_both_no_retry(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.move_file(str(src), destination=str(dst))
    real = Path.unlink
    def fail(path, *args, **kw):
        if path == src:
            raise OSError("private native details")
        return real(path, *args, **kw)
    monkeypatch.setattr(Path, "unlink", fail)
    result = requests[0]["run"]()
    assert "OUTCOME_UNKNOWN" in result and "private" not in result
    assert src.read_text() == dst.read_text() == "approved bytes"
    assert not undo.can_undo()


def test_direct_effect_sink_no_grant(rig):
    plan = policy.prepare("files.copy", ("file",), {})
    with pytest.raises(PermissionError):
        safety._apply_transfer(plan, lambda p: True)


def test_undo_headless_and_denial_preserve_entry(rig, monkeypatch):
    calls = []
    undo.push_undo("fake effect", lambda: calls.append(1) or "ok")
    assert "have not done it" in undo.undo_last()
    assert undo.can_undo() and not calls
    requests = capture(monkeypatch)
    assert undo.undo_last() == "pending"
    requests[0]["on_cancel"]("cancelled")
    assert "REJECTED" in requests[0]["run"]()
    assert undo.can_undo() and not calls


def test_undo_changed_stack_never_runs_wrong_entry(rig, monkeypatch):
    calls = []
    undo.push_undo("first", lambda: calls.append("first"))
    requests = capture(monkeypatch)
    undo.undo_last()
    undo.push_undo("second", lambda: calls.append("second"))
    assert "stack changed" in requests[0]["run"]()
    assert undo.history() == ["second", "first"] and not calls


def test_clear_invalidates_pending_undo(rig, monkeypatch):
    calls = []
    undo.push_undo("first", lambda: calls.append(1))
    requests = capture(monkeypatch)
    undo.undo_last()
    undo.clear()
    assert "stack changed" in requests[0]["run"]() and not calls


def test_concurrent_previews_only_one_undo_callback(rig, monkeypatch):
    calls = []
    undo.push_undo("first", lambda: calls.append(1) or "submitted, not verified")
    requests = capture(monkeypatch)
    undo.undo_last()
    undo.undo_last()
    assert "callback returned" in requests[0]["run"]()
    assert "stack changed" in requests[1]["run"]() and calls == [1]


def test_undo_failure_consumed_sanitized_and_not_claimed_done(rig, monkeypatch):
    def fail():
        raise RuntimeError("private payload")
    undo.push_undo("fake", fail)
    requests = capture(monkeypatch)
    undo.undo_last()
    result = requests[0]["run"]()
    assert "Could not undo" in result and "private" not in result and "Undone" not in result
    assert not undo.can_undo()


def test_changed_transfer_target_after_undo_preview_retained(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(dst))
    requests[0]["run"]()
    undo.undo_last()
    dst.write_text("later edit")
    assert "Could not undo" in requests[1]["run"]()
    assert dst.read_text() == "later edit" and not undo.can_undo()


def test_raw_undo_executor_no_grant(rig):
    plan = policy.prepare("session.undo", ("entry",), {})
    with pytest.raises(PermissionError):
        undo._execute_undo(plan, None)


def test_alternate_desktop_bulk_paths_fail_closed(rig, monkeypatch):
    from ultron.actions import desktop
    monkeypatch.setattr(desktop, "_get_desktop", lambda: pytest.fail("desktop enumerated"))
    assert "disabled" in desktop.organize_desktop()
    assert "disabled" in desktop.clean_desktop()
    assert not list(rig.iterdir())


def test_parallel_undo_approvals_invoke_callback_once(rig, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    calls = []
    undo.push_undo("fake", lambda: calls.append(1) or "fake result")
    requests = capture(monkeypatch)
    undo.undo_last()
    undo.undo_last()
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda request: request["run"](), requests))
    assert calls == [1]
    assert sum("callback returned" in result for result in results) == 1
    assert sum("stack changed" in result for result in results) == 1


def test_undo_preview_discloses_full_transfer_paths_and_hash(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(dst))
    requests[0]["run"]()
    undo.undo_last()
    assert str(src) in requests[1]["detail"] and str(dst) in requests[1]["detail"]
    assert safety.fingerprint(dst)[-1] in requests[1]["detail"]


def test_copy_staging_cleanup_error_preserves_published_file_reports_unknown(rig, monkeypatch):
    src, dst = setup(rig)
    requests = capture(monkeypatch)
    files.copy_file(str(src), destination=str(dst))
    real = Path.unlink
    def fail(path, *args, **kw):
        if path.name.startswith(".ultron-copy-"):
            raise OSError("cleanup failure")
        return real(path, *args, **kw)
    monkeypatch.setattr(Path, "unlink", fail)
    assert "OUTCOME_UNKNOWN" in requests[0]["run"]()
    assert src.read_text() == dst.read_text() == "approved bytes"
    assert len(list(rig.glob(".ultron-copy-*.part"))) == 1
    assert not undo.can_undo()


def test_undo_expiry_preserves_entry_without_callback(rig, monkeypatch):
    calls = []
    undo.push_undo("fake", lambda: calls.append(1))
    requests = capture(monkeypatch)
    undo.undo_last()
    monkeypatch.setattr(policy.time, "monotonic", lambda: float("inf"))
    assert "EXPIRED" in requests[0]["run"]()
    assert undo.can_undo() and not calls
