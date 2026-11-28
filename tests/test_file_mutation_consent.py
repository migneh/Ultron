"""Temporary files and fake host approval only; no native Trash/user data."""

import pytest

from ultron.actions import file_controller as files
from ultron.core import confirm, undo
from ultron.core import file_mutations as mutations
from ultron.core import operation_policy as policy


@pytest.fixture
def rig(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "_SAFE_ROOTS", [tmp_path])
    for attr in ("_pending", "_show_cb", "_hide_cb", "_log_cb", "_show_with_id_cb", "_hide_with_id_cb"):
        monkeypatch.setattr(confirm, attr, None)
    undo.clear()
    yield tmp_path
    undo.clear()


def previews(monkeypatch):
    seen = []
    monkeypatch.setattr(confirm, "request", lambda **kw: seen.append(kw) or "pending")
    return seen


@pytest.mark.parametrize("action", ["create_file", "create_folder", "write_file"])
def test_headless_helpers_no_effect(rig, action):
    target = rig / "new"
    assert "have not done it" in getattr(files, action)(str(target))
    assert not target.exists() and not undo.can_undo()


@pytest.mark.parametrize("action", ["create_file", "create_folder", "write_file"])
def test_denial_and_replay_no_effect(rig, monkeypatch, action):
    seen = previews(monkeypatch)
    target = rig / "new"
    assert getattr(files, action)(str(target)) == "pending"
    seen[0]["on_cancel"]("denied")
    assert "REJECTED" in seen[0]["run"]()
    assert not target.exists() and not undo.can_undo()


@pytest.mark.parametrize("append", [False, True])
def test_exact_write_and_binary_inverse_separately_approved(rig, monkeypatch, append):
    target = rig / "file"
    target.write_bytes(b"\xff\x00\r\n")
    seen = previews(monkeypatch)
    assert files.write_file(str(target), content="new\r\n", append=append) == "pending"
    assert target.read_bytes() == b"\xff\x00\r\n" and not undo.can_undo()
    assert str(target) in seen[0]["detail"] and "new\\r\\n" in seen[0]["detail"]
    assert "Written to" in seen[0]["run"]()
    assert target.read_bytes() == (b"\xff\x00\r\n" if append else b"") + b"new\r\n"
    assert "REJECTED" in seen[0]["run"]()
    assert undo.undo_last() == "pending"
    assert "callback returned" in seen[1]["run"]()
    assert target.read_bytes() == b"\xff\x00\r\n"


@pytest.mark.parametrize("action", ["create_file", "write_file", "create_folder"])
def test_create_and_inverse_remove_only_owned_new_target(rig, monkeypatch, action):
    target = rig / "new"
    seen = previews(monkeypatch)
    getattr(files, action)(str(target))
    assert "created" in seen[0]["run"]().lower() if action != "write_file" else "Written to" in seen[0]["run"]()
    assert target.exists()
    undo.undo_last()
    assert "callback returned" in seen[1]["run"]()
    assert not target.exists()


@pytest.mark.parametrize("change", ["edit", "replace", "delete", "symlink"])
def test_changed_target_after_preview_not_overwritten(rig, monkeypatch, change):
    target = rig / "file"
    target.write_text("old")
    seen = previews(monkeypatch)
    files.write_file(str(target), content="proposed")
    if change == "edit":
        target.write_text("later")
    elif change == "replace":
        other = rig / "other"
        other.write_text("old")
        other.replace(target)
    elif change == "delete":
        target.unlink()
    else:
        target.unlink()
        other = rig / "other"
        other.write_text("keep")
        target.symlink_to(other)
    assert "OUTCOME_UNKNOWN" in seen[0]["run"]()
    assert not undo.can_undo()
    if target.is_file():
        assert target.read_text() != "proposed"


def test_new_target_collision_never_overwrites(rig, monkeypatch):
    target = rig / "file"
    seen = previews(monkeypatch)
    files.create_file(str(target), content="proposed")
    target.write_text("competitor")
    assert "OUTCOME_UNKNOWN" in seen[0]["run"]()
    assert target.read_text() == "competitor"


def test_parent_replaced_no_write(rig, monkeypatch):
    parent = rig / "parent"
    parent.mkdir()
    seen = previews(monkeypatch)
    files.create_file(str(parent / "file"), content="text")
    parent.rename(rig / "old")
    parent.mkdir()
    assert "OUTCOME_UNKNOWN" in seen[0]["run"]()
    assert not list(parent.iterdir())


def test_root_revoked_no_write(rig, monkeypatch):
    seen = previews(monkeypatch)
    files.create_file(str(rig / "file"), content="text")
    monkeypatch.setattr(files, "_SAFE_ROOTS", [])
    assert "OUTCOME_UNKNOWN" in seen[0]["run"]()
    assert not list(rig.iterdir())


@pytest.mark.parametrize("action", ["create_file", "create_folder", "write_file"])
def test_no_recursive_parents(rig, monkeypatch, action):
    seen = previews(monkeypatch)
    assert "rejected" in getattr(files, action)(str(rig / "missing" / "new"))
    assert not seen and not list(rig.iterdir())


@pytest.mark.parametrize("kind", ["input", "old", "result"])
def test_byte_limits_before_approval(rig, monkeypatch, kind):
    seen = previews(monkeypatch)
    target = rig / "file"
    if kind == "old":
        target.write_bytes(b"a" * (mutations.MAX_BYTES + 1))
    elif kind == "result":
        target.write_bytes(b"a" * mutations.MAX_BYTES)
    content = "é" * 8001 if kind == "input" else "x"
    assert "rejected" in files.write_file(str(target), content=content, append=kind == "result")
    assert not seen


def test_expiry_no_write(rig, monkeypatch):
    seen = previews(monkeypatch)
    files.write_file(str(rig / "file"), content="text")
    monkeypatch.setattr(policy.time, "monotonic", lambda: float("inf"))
    assert "EXPIRED" in seen[0]["run"]()
    assert not list(rig.iterdir())


def test_direct_sink_and_publish_helper_require_consumed_grant(rig):
    plan = policy.prepare("files.write", ("file",), {})
    with pytest.raises(PermissionError):
        mutations._execute(plan, lambda p: True)
    with pytest.raises(PermissionError):
        mutations._publish(rig / "file", b"bytes", lambda p: True, [], None)
    with pytest.raises(PermissionError):
        files._undo_write(rig / "file", b"bytes")()
    assert not list(rig.iterdir())


def test_staging_write_failure_preserves_old_bytes(rig, monkeypatch):
    target = rig / "file"
    target.write_text("old")
    seen = previews(monkeypatch)
    files.write_file(str(target), content="new")
    monkeypatch.setattr(mutations.os, "fsync", lambda _: (_ for _ in ()).throw(OSError("private failure")))
    result = seen[0]["run"]()
    assert "OUTCOME_UNKNOWN" in result and "private" not in result
    assert target.read_text() == "old" and not undo.can_undo()
    assert not list(rig.glob(".ultron-write-*.part"))


def test_changed_after_staging_before_replace_is_refused(rig, monkeypatch):
    target = rig / "file"
    target.write_text("old")
    seen = previews(monkeypatch)
    files.write_file(str(target), content="new")
    monkeypatch.setattr(mutations.os, "fsync", lambda _: target.write_text("competitor"))
    assert "OUTCOME_UNKNOWN" in seen[0]["run"]()
    assert target.read_text() == "competitor"


def test_folder_inverse_refuses_nonempty(rig, monkeypatch):
    target = rig / "folder"
    seen = previews(monkeypatch)
    files.create_folder(str(target))
    seen[0]["run"]()
    undo.undo_last()
    (target / "keep").write_text("later")
    assert "Could not undo" in seen[1]["run"]()
    assert (target / "keep").read_text() == "later"


def test_write_inverse_refuses_edited_target(rig, monkeypatch):
    target = rig / "file"
    target.write_text("old")
    seen = previews(monkeypatch)
    files.write_file(str(target), content="new")
    seen[0]["run"]()
    undo.undo_last()
    target.write_text("later")
    assert "Could not undo" in seen[1]["run"]()
    assert target.read_text() == "later"


def test_raw_registered_inverse_without_undo_grant_is_refused(rig, monkeypatch):
    seen = previews(monkeypatch)
    files.write_file(str(rig / "file"), content="new")
    seen[0]["run"]()
    with pytest.raises(PermissionError):
        undo._stack[-1].undo()
    assert (rig / "file").read_text() == "new"


def test_replace_failure_no_undo_and_original_retained(rig, monkeypatch):
    target = rig / "file"
    target.write_text("old")
    seen = previews(monkeypatch)
    files.write_file(str(target), content="new")
    monkeypatch.setattr(mutations.os, "replace", lambda *a: (_ for _ in ()).throw(OSError("failed")))
    assert "OUTCOME_UNKNOWN" in seen[0]["run"]()
    assert target.read_text() == "old" and not undo.can_undo()


def test_existing_hardlink_is_not_modified_in_place(rig, monkeypatch):
    target, alias = rig / "file", rig / "alias"
    target.write_text("old")
    mutations.os.link(target, alias)
    seen = previews(monkeypatch)
    files.write_file(str(target), content="new")
    seen[0]["run"]()
    assert target.read_text() == "new" and alias.read_text() == "old"


def test_require_consumed_rejects_wrong_and_unconsumed_grants(rig):
    plan = policy.prepare("files.write", ("file",), {})
    grant = policy._Grant(plan)
    token = policy._active_grant.set(grant)
    try:
        with pytest.raises(PermissionError):
            policy.require_consumed(("files.write",))
        policy.consume(plan)
        with pytest.raises(PermissionError):
            policy.require_consumed(("session.undo",))
        policy.require_consumed(("files.write",))
    finally:
        policy._active_grant.reset(token)


@pytest.mark.parametrize("content,append", [(None, False), ("x", "false"), ("\ud800", False)])
def test_invalid_text_or_append_direct_helper_fails_closed(rig, monkeypatch, content, append):
    seen = previews(monkeypatch)
    assert "rejected" in files.write_file(str(rig / "file"), content=content, append=append)
    assert not seen and not list(rig.iterdir())


def test_exact_maximum_before_after_fits_immutable_plan(rig, monkeypatch):
    target = rig / "file"
    target.write_bytes(b"a" * mutations.MAX_BYTES)
    seen = previews(monkeypatch)
    assert files.write_file(str(target), content="b" * mutations.MAX_BYTES) == "pending"
    assert "Written to" in seen[0]["run"]()
    assert target.read_bytes() == b"b" * mutations.MAX_BYTES
    undo.undo_last()
    assert "callback returned" in seen[1]["run"]()
    assert target.read_bytes() == b"a" * mutations.MAX_BYTES


def test_folder_preview_collision_refuses_without_removing_competitor(rig, monkeypatch):
    target = rig / "folder"
    seen = previews(monkeypatch)
    files.create_folder(str(target))
    target.mkdir()
    (target / "keep").write_text("competitor")
    assert "rejected" in seen[0]["run"]()
    assert (target / "keep").read_text() == "competitor"
    assert not undo.can_undo()


def test_undo_parent_replacement_does_not_restore_into_new_directory(rig, monkeypatch):
    parent = rig / "parent"
    parent.mkdir()
    target = parent / "file"
    target.write_text("old")
    seen = previews(monkeypatch)
    files.write_file(str(target), content="new")
    seen[0]["run"]()
    undo.undo_last()
    parent.rename(rig / "moved")
    parent.mkdir()
    assert "Could not undo" in seen[1]["run"]()
    assert not list(parent.iterdir())
    assert (rig / "moved" / "file").read_text() == "new"
