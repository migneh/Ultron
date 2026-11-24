import pytest

from actions import file_controller as files
from core import file_safety as safety
from core import undo


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "_SAFE_ROOTS", [tmp_path])
    monkeypatch.setattr(files, "_get_desktop", lambda: tmp_path)
    undo.clear()
    yield
    undo.clear()


@pytest.mark.parametrize("action", ["move", "copy", "rename"])
def test_transfer_and_undo(tmp_path, action):
    src = tmp_path / "source.txt"
    src.write_text("original")
    dst = tmp_path / "dest.txt"
    result = files.file_controller(
        {"action": action, "path": str(src), "destination": str(dst), "new_name": dst.name}
    )
    assert ("Moved:" if action != "copy" else "Copied:") in result
    assert dst.read_text() == "original"
    assert src.exists() == (action == "copy")
    assert "Undone:" in undo.undo_last()
    assert src.read_text() == "original" and not dst.exists()


@pytest.mark.parametrize("action", ["move", "copy", "rename"])
def test_preview(tmp_path, action):
    src = tmp_path / "source.txt"
    src.write_text("text")
    result = files.file_controller(
        {
            "action": action,
            "path": str(src),
            "destination": str(tmp_path / "dest.txt"),
            "new_name": "dest.txt",
            "dry_run": True,
        }
    )
    assert "DRY RUN" in result
    assert list(tmp_path.iterdir()) == [src]
    assert not undo.can_undo()


@pytest.mark.parametrize("action", ["move", "copy", "rename"])
def test_conflict(tmp_path, action):
    src, dst = tmp_path / "source", tmp_path / "dest"
    src.write_text("old")
    dst.write_text("keep")
    files.file_controller(
        {"action": action, "path": str(src), "destination": str(dst), "new_name": "dest"}
    )
    assert src.read_text() == "old" and dst.read_text() == "keep"
    assert not undo.can_undo()


@pytest.mark.parametrize("action", ["move", "copy"])
def test_changed_copy_undo_refused(tmp_path, action):
    src, dst = tmp_path / "source", tmp_path / "dest"
    src.write_text("old")
    files.file_controller({"action": action, "path": str(src), "destination": str(dst)})
    dst.write_text("later edit")
    assert "Could not undo" in undo.undo_last()
    assert dst.read_text() == "later edit"


def test_undo_occupied_origin(tmp_path):
    src, dst = tmp_path / "source", tmp_path / "dest"
    src.write_text("old")
    files.move_file(str(src), destination=str(dst))
    src.write_text("new")
    assert "Could not undo" in undo.undo_last()
    assert src.read_text() == "new" and dst.read_text() == "old"


@pytest.mark.parametrize("new_name", ["../escape", "/tmp/escape", "a/b", "a\\b", ".."])
def test_rename_rejects_paths(tmp_path, new_name):
    src = tmp_path / "source"
    src.write_text("keep")
    assert "rejected" in files.rename_file(str(src), new_name=new_name)
    assert src.exists()


def test_symlink_refused(tmp_path):
    src = tmp_path / "source"
    src.write_text("keep")
    link = tmp_path / "link"
    link.symlink_to(src)
    assert "Symlink" in files.move_file(str(link), destination=str(tmp_path / "dest"))
    assert src.read_text() == "keep" and link.is_symlink()


def test_directory_refused(tmp_path):
    src = tmp_path / "dir"
    src.mkdir()
    assert "regular-file" in files.copy_file(str(src), destination=str(tmp_path / "new"))
    assert not (tmp_path / "new").exists()


def test_no_link_fallback(tmp_path, monkeypatch):
    src = tmp_path / "source"
    src.write_text("keep")

    def fail(*a, **k):
        raise OSError("cross-device or unsupported")

    monkeypatch.setattr(safety.os, "link", fail)
    assert "failed" in files.move_file(str(src), destination=str(tmp_path / "dest"))
    assert src.read_text() == "keep" and not (tmp_path / "dest").exists()


def test_destination_inside_directory_checked(tmp_path):
    src = tmp_path / "source"
    src.write_text("keep")
    folder = tmp_path / "folder"
    folder.mkdir()
    (folder / "source").symlink_to(src)
    files.copy_file(str(src), destination=str(folder))
    assert (folder / "source").is_symlink() and src.read_text() == "keep"


def test_organize_preview_apply_and_conflict_undo(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "b.py").write_text("b")
    assert "DRY RUN" in files.organize_desktop()
    assert not (tmp_path / "Documents").exists()
    assert "2 moved" in files.organize_desktop(False)
    (tmp_path / "a.txt").write_text("later")
    output = undo.undo_last()
    assert "Restored 1; conflicts/unchanged 1" in output
    assert (tmp_path / "a.txt").read_text() == "later"
    assert (tmp_path / "Documents" / "a.txt").read_text() == "a"
    assert (tmp_path / "b.py").read_text() == "b"
    assert not (tmp_path / "Code").exists()


def test_organize_preexisting_category_preserved(tmp_path):
    (tmp_path / "Documents").mkdir()
    (tmp_path / "a.txt").write_text("a")
    files.organize_desktop(False)
    undo.undo_last()
    assert (tmp_path / "Documents").is_dir()


def test_create_refuses_overwrite(tmp_path):
    target = tmp_path / "file"
    target.write_text("keep")
    assert "no overwrite" in files.create_file(str(target), content="replace")
    assert target.read_text() == "keep"


@pytest.mark.parametrize("edited", [True, False])
def test_write_undo_bytes(tmp_path, edited):
    target = tmp_path / "file"
    target.write_bytes(b"\xff\x00\r\n")
    assert "Written" in files.write_file(str(target), content="replacement")
    if edited:
        target.write_text("later")
    output = undo.undo_last()
    if edited:
        assert "Could not undo" in output and target.read_text() == "later"
    else:
        assert target.read_bytes() == b"\xff\x00\r\n"


def test_create_undo_refuses_later_content(tmp_path):
    target = tmp_path / "file"
    files.create_file(str(target), content="initial")
    target.write_text("later")
    assert "Could not undo" in undo.undo_last()
    assert target.read_text() == "later"


def test_unsupported_dry_run_rejected(tmp_path):
    target = tmp_path / "file"
    assert "rejected" in files.file_controller(
        {"action": "create_file", "path": str(target), "dry_run": True}
    )
    assert not target.exists()


def test_transfer_limit(tmp_path, monkeypatch):
    src = tmp_path / "source"
    src.write_text("too large")
    monkeypatch.setattr(safety, "MAX_BYTES", 2)
    assert "64 MiB" in files.move_file(str(src), destination=str(tmp_path / "dest"))
    assert src.exists() and not (tmp_path / "dest").exists()


def test_organize_journals_partial_success(tmp_path, monkeypatch):
    (tmp_path / "a.txt").write_text("first")
    (tmp_path / "b.txt").write_text("second")
    real = safety.transfer

    def partly_fail(src, dst, **kwargs):
        if src.name == "b.txt":
            raise OSError("mock failure")
        return real(src, dst, **kwargs)

    monkeypatch.setattr(safety, "transfer", partly_fail)
    output = files.organize_desktop(False)
    assert "1 moved" in output and "FAILED" in output
    assert undo.can_undo()
    undo.undo_last()
    assert (tmp_path / "a.txt").read_text() == "first"
    assert (tmp_path / "b.txt").read_text() == "second"


def test_organize_category_symlink_blocked(tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    (tmp_path / "Documents").symlink_to(other, target_is_directory=True)
    (tmp_path / "a.txt").write_text("keep")
    assert "SKIPPED" in files.organize_desktop(False)
    assert (tmp_path / "a.txt").exists() and not list(other.iterdir())


def test_target_creation_race_does_not_overwrite(tmp_path, monkeypatch):
    src, dst = tmp_path / "source", tmp_path / "dest"
    src.write_text("source")
    real = safety.os.link

    def race(source, destination, **kwargs):
        dst.write_text("competitor")
        return real(source, destination, **kwargs)

    monkeypatch.setattr(safety.os, "link", race)
    files.move_file(str(src), destination=str(dst))
    assert src.read_text() == "source" and dst.read_text() == "competitor"
    assert not undo.can_undo()


def test_write_limits(tmp_path, monkeypatch):
    target = tmp_path / "file"
    target.write_bytes(b"original")
    monkeypatch.setattr(files, "_UNDO_CONTENT_LIMIT", 3)
    assert "rejected" in files.write_file(str(target), content="x")
    assert target.read_bytes() == b"original"


def test_undo_replaced_same_content_refused(tmp_path):
    src, dst = tmp_path / "source", tmp_path / "dest"
    src.write_text("text")
    files.copy_file(str(src), destination=str(dst))
    replacement = tmp_path / "replacement"
    replacement.write_text("text")
    replacement.replace(dst)
    assert "Could not undo" in undo.undo_last()
    assert dst.read_text() == "text"
