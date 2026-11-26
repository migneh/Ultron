"""Temporary files/fake native Trash callable only; never use real Trash."""
from types import SimpleNamespace

import pytest

from ultron.actions import file_controller as files
from ultron.core import confirm, undo
from ultron.core import file_safety as safety
from ultron.core import file_trash as trash
from ultron.core import operation_policy as policy


@pytest.fixture
def rig(tmp_path, monkeypatch):
    state = SimpleNamespace(root=tmp_path, calls=[], mode="remove")
    monkeypatch.setattr(files, "_SAFE_ROOTS", [tmp_path])
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    def backend(raw):
        from pathlib import Path
        state.calls.append(raw)
        path = Path(raw)
        if state.mode == "error":
            raise OSError("private provider details")
        if state.mode in ("remove", "remove_error", "recreate"):
            path.unlink()  # fake disposal in isolated tmp only, NOT actual Trash
        if state.mode == "remove_error":
            raise OSError("unknown after effect")
        if state.mode == "recreate":
            path.write_text("competitor")
    state.backend = backend
    monkeypatch.setattr(trash, "_backend", lambda: backend)
    undo.clear()
    yield state
    undo.clear()


def preview(rig, monkeypatch, path=None):
    seen = {}
    monkeypatch.setattr(confirm, "request", lambda **kw: seen.update(kw) or "pending")
    target = path or rig.root / "file"
    if path is None:
        target.write_text("approved bytes")
    result = files.delete_file(str(target))
    return target, seen, result


@pytest.mark.parametrize("entry", ["delete", "helper", "core"])
def test_headless_all_entrypoints_no_native_call(rig, entry):
    target = rig.root / "file"
    target.write_text("keep")
    if entry == "delete":
        result = files.delete_file(str(target))
    elif entry == "helper":
        result = files._safe_trash(target)
    else:
        result = trash.request(target, allowed=files._is_safe_path)
    assert "have not done it" in result
    assert target.read_text() == "keep" and not rig.calls and not undo.can_undo()


def test_exact_approval_once_source_absence_not_receipt(rig, monkeypatch):
    target, seen, result = preview(rig, monkeypatch)
    assert result == "pending" and target.exists() and not rig.calls
    assert str(target) in seen["detail"] and safety.fingerprint(target)[-1] in seen["detail"]
    outcome = seen["run"]()
    assert "original path is now absent" in outcome and "NOT verified" in outcome
    assert rig.calls == [str(target)] and not target.exists() and not undo.can_undo()
    assert "REJECTED" in seen["run"]() and len(rig.calls) == 1


def test_denial_does_not_remove_or_register_undo(rig, monkeypatch):
    target, seen, _ = preview(rig, monkeypatch)
    seen["on_cancel"]("cancelled")
    assert "REJECTED" in seen["run"]()
    assert target.exists() and not rig.calls and not undo.can_undo()


def test_expired_preview_no_call(rig, monkeypatch):
    target, seen, _ = preview(rig, monkeypatch)
    monkeypatch.setattr(policy.time, "monotonic", lambda: float("inf"))
    assert "EXPIRED" in seen["run"]()
    assert target.exists() and not rig.calls


@pytest.mark.parametrize("change", ["edit", "replace", "remove", "symlink", "directory", "link_count"])
def test_changed_target_never_submitted(rig, monkeypatch, change):
    target, seen, _ = preview(rig, monkeypatch)
    if change == "edit":
        target.write_text("later")
    elif change == "replace":
        replacement = rig.root / "other"
        replacement.write_text("approved bytes")
        replacement.replace(target)
    elif change == "remove":
        target.unlink()
    elif change == "symlink":
        target.unlink()
        target.symlink_to(rig.root / "missing")
    elif change == "directory":
        target.unlink()
        target.mkdir()
    else:
        import os
        os.link(target, rig.root / "alias")
    assert "no native request" in seen["run"]()
    assert not rig.calls and not undo.can_undo()


def test_revoked_roots_refuse(rig, monkeypatch):
    target, seen, _ = preview(rig, monkeypatch)
    monkeypatch.setattr(files, "_SAFE_ROOTS", [])
    assert "no native request" in seen["run"]()
    assert target.exists() and not rig.calls


def test_replaced_parent_refuse(rig, monkeypatch):
    parent = rig.root / "folder"
    parent.mkdir()
    target = parent / "file"
    target.write_text("approved bytes")
    _, seen, _ = preview(rig, monkeypatch, target)
    parent.rename(rig.root / "old")
    parent.mkdir()
    (rig.root / "old" / "file").rename(target)
    assert "no native request" in seen["run"]()
    assert target.exists() and not rig.calls


def test_backend_changed_after_preview_refuse(rig, monkeypatch):
    target, seen, _ = preview(rig, monkeypatch)
    monkeypatch.setattr(trash, "_backend", lambda: lambda _: pytest.fail("replacement invoked"))
    assert "backend changed" in seen["run"]()
    assert target.exists() and not rig.calls


def test_backend_unavailable_before_preview(rig, monkeypatch):
    def missing():
        raise ImportError("missing dependency private path")
    monkeypatch.setattr(trash, "_backend", missing)
    target, seen, result = preview(rig, monkeypatch)
    assert "unavailable/refused" in result and "private" not in result
    assert not seen and target.exists() and not rig.calls


@pytest.mark.parametrize("mode", ["error", "remove_error"])
def test_native_failure_no_retry_fallback_or_false_recoverability(rig, monkeypatch, mode):
    rig.mode = mode
    target, seen, _ = preview(rig, monkeypatch)
    result = seen["run"]()
    assert "outcome unknown" in result and "private" not in result
    assert rig.calls == [str(target)] and not undo.can_undo()
    assert target.exists() == (mode == "error")
    assert "REJECTED" in seen["run"]()


@pytest.mark.parametrize("mode", ["keep", "recreate"])
def test_source_present_after_call_reports_unverified_no_retry(rig, monkeypatch, mode):
    rig.mode = mode
    target, seen, _ = preview(rig, monkeypatch)
    assert "still exists or was recreated" in seen["run"]()
    assert target.exists() and len(rig.calls) == 1 and not undo.can_undo()


@pytest.mark.parametrize("kind", ["empty_directory", "populated_directory", "fifo", "symlink", "missing"])
def test_unsupported_types_refused_without_approval(rig, monkeypatch, kind):
    import os
    target = rig.root / "target"
    if kind.endswith("directory"):
        target.mkdir()
        if kind == "populated_directory":
            (target / "keep").write_text("keep")
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "symlink":
        target.symlink_to(rig.root / "missing")
    _, seen, result = preview(rig, monkeypatch, target)
    assert "unavailable/refused" in result and not seen and not rig.calls


def test_symlink_parent_refused(rig, monkeypatch):
    parent = rig.root / "real"
    parent.mkdir()
    (parent / "file").write_text("keep")
    link = rig.root / "alias"
    link.symlink_to(parent, target_is_directory=True)
    _, seen, result = preview(rig, monkeypatch, link / "file")
    assert "unavailable/refused" in result and not seen and not rig.calls


def test_cap_before_approval(rig, monkeypatch):
    monkeypatch.setattr(safety, "MAX_BYTES", 2)
    target, seen, result = preview(rig, monkeypatch)
    assert "unavailable/refused" in result and not seen
    assert target.exists() and not rig.calls


def test_direct_effect_sink_no_grant(rig):
    plan = policy.prepare("files.trash", ("path",), {})
    with pytest.raises(PermissionError):
        trash._execute(plan, lambda _: True, rig.backend)
    assert not rig.calls


def test_automatic_restore_disabled_no_files_or_undo(rig):
    missing = rig.root / "not_created"
    assert "disabled" in files._restore_from_trash(missing)
    assert "no stable native receipt" in trash.restore_disabled()
    assert not missing.exists() and not rig.calls and not undo.can_undo()


def test_hardlink_disclosure_and_alias_survives(rig, monkeypatch):
    import os
    target = rig.root / "file"
    alias = rig.root / "alias"
    target.write_text("keep alias")
    os.link(target, alias)
    _, seen, _ = preview(rig, monkeypatch, target)
    assert "not every hardlink" in seen["detail"]
    seen["run"]()
    assert not target.exists() and alias.read_text() == "keep alias"
