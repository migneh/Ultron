"""Bounded search tests: only temporary directories, no user file access."""

import os
import time

import pytest

from actions import file_controller as fc
from actions import file_search as fs
from core.action_loader import ActionRegistry, _validate


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    monkeypatch.setattr(fc, "_SAFE_ROOTS", [root])
    return root


def test_literal_filename_extension_and_metadata(workspace):
    (workspace / "Report.PDF").write_text("example")
    (workspace / "notes.txt").write_text("hello")
    report = fs.search_files(str(workspace), query="REPORT", extension="pdf")
    assert len(report["results"]) == 1
    assert report["results"][0]["path"].endswith("Report.PDF")
    assert "snippet" not in report["results"][0]
    assert report["content_bytes_read"] == 0


def test_opt_in_content_returns_line_number(workspace):
    path = workspace / "notes.md"
    path.write_text("heading\nThe release is READY today\nfooter", encoding="utf-8")
    report = fs.search_files(str(workspace), content="release is ready")
    assert report["results"][0]["line"] == 2
    assert "READY" in report["results"][0]["snippet"]


def test_excludes_credentials_hidden_and_dependency_paths(workspace):
    for name in ("api_keys.json", "access_token.txt", "credentials.json", ".env", "server.key"):
        (workspace / name).write_text("sensitive")
    for name in ("node_modules", ".git", "build", "secrets"):
        directory = workspace / name
        directory.mkdir()
        (directory / "notes.txt").write_text("sensitive")
    (workspace / "normal.txt").write_text("ordinary")
    report = fs.search_files(str(workspace))
    assert [os.path.basename(row["path"]) for row in report["results"]] == ["normal.txt"]
    assert "rejected" in fs.file_search({"path": str(workspace / "secrets")})


def test_depth_limit_is_explicit(workspace):
    (workspace / "root.txt").write_text("root")
    (workspace / "sub").mkdir()
    (workspace / "sub" / "nested.txt").write_text("nested")
    report = fs.search_files(str(workspace), max_depth=0)
    assert len(report["results"]) == 1
    assert "depth_limit" in report["limits"]
    assert len(fs.search_files(str(workspace), max_depth=1)["results"]) == 2


def test_result_cap_and_recent_sort(workspace):
    for index in range(3):
        path = workspace / f"report{index}.txt"
        path.write_text("hello")
        os.utime(path, (1000 + index, 1000 + index))
    report = fs.search_files(str(workspace), max_results=1)
    assert report["results"][0]["path"].endswith("report2.txt")
    assert report["matched_in_scanned_scope"] == 3
    assert "result_limit" in report["limits"]


def test_size_and_modified_filters(workspace):
    old = workspace / "old.txt"
    old.write_text("old")
    os.utime(old, (time.time() - 10 * 86400,) * 2)
    (workspace / "new.txt").write_text("new data")
    report = fs.search_files(str(workspace), modified_within_days=1, min_size_bytes=5)
    assert report["results"][0]["path"].endswith("new.txt")
    assert not fs.search_files(str(workspace), max_size_bytes=2)["results"]


def test_entry_and_directory_budgets_are_reported(workspace, monkeypatch):
    for index in range(4):
        (workspace / f"file{index}.txt").write_text("x")
    monkeypatch.setattr(fs, "MAX_ENTRIES", 2)
    report = fs.search_files(str(workspace))
    assert report["scanned_entries"] == 2
    assert "entry_limit" in report["limits"]
    monkeypatch.setattr(fs, "MAX_ENTRIES", 100)
    monkeypatch.setattr(fs, "MAX_DIRECTORIES", 1)
    (workspace / "sub").mkdir()
    report = fs.search_files(str(workspace))
    assert "directory_limit" in report["limits"]


def test_time_budget_is_reported(workspace, monkeypatch):
    (workspace / "file.txt").write_text("x")
    monkeypatch.setattr(fs, "MAX_SECONDS", -1)
    assert "time_limit" in fs.search_files(str(workspace))["limits"]


def test_content_limits_and_binary_files(workspace, monkeypatch):
    (workspace / "large.txt").write_text("needle" * 20)
    (workspace / "binary.txt").write_bytes(b"needle\x00data")
    (workspace / "bad.txt").write_bytes(b"\xffneedle")
    (workspace / "document.pdf").write_bytes(b"needle")
    monkeypatch.setattr(fs, "MAX_FILE_BYTES", 50)
    report = fs.search_files(str(workspace), content="needle")
    assert not report["results"]
    assert report["skipped_content_files"] == 4
    monkeypatch.setattr(fs, "MAX_CONTENT_BYTES", 4)
    assert "content_byte_limit" in fs.search_files(str(workspace), content="needle")["limits"]


def test_symlinks_cannot_escape_or_loop(workspace, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("needle")
    try:
        (workspace / "escape.txt").symlink_to(outside)
        (workspace / "loop").symlink_to(workspace, target_is_directory=True)
    except OSError:
        pytest.skip("Symlinks unavailable on this platform")
    assert not fs.search_files(str(workspace), content="needle")["results"]
    assert "rejected" in fs.file_search({"path": str(workspace / "loop")})


def test_outside_safe_roots_is_denied(workspace, tmp_path):
    assert "Access denied" in fs.file_search({"path": str(tmp_path)})
    assert "rejected" in fs.file_search({"path": str(workspace / "missing")})


@pytest.mark.parametrize(
    "options",
    [
        {"max_results": 0},
        {"max_results": 100},
        {"max_depth": -1},
        {"max_depth": True},
        {"min_size_bytes": -1},
        {"modified_within_days": "today"},
        {"content": 5},
        {"extension": "*.py"},
        {"unexpected": "value"},
        {"min_size_bytes": 20, "max_size_bytes": 10},
    ],
)
def test_invalid_options_return_actionable_errors(workspace, options):
    assert "rejected" in fs.file_search({"path": str(workspace), **options})


def test_legacy_find_uses_same_bounded_engine(workspace):
    (workspace / "notes.txt").write_text("hello")
    output = fc.find_files(name="notes", extension="txt", path=str(workspace))
    assert "Found 1 file" in output
    assert "Scanned" in output


def test_search_registry_contract(workspace):
    (workspace / "report.md").write_text("Hello")
    record = _validate(fs, "file_search.py")
    assert record.valid
    registry = ActionRegistry({record.name: record}, logger=lambda _: None)
    assert "Found 1 file" in registry.run(
        "file_search", {"path": str(workspace), "query": "report"}
    )


def test_tools_are_auto_discovered_without_main_dispatch_changes(tmp_path):
    from pathlib import Path

    from actions import quick_timer
    from core.action_loader import discover_actions

    directory = tmp_path / "bundled_actions"
    directory.mkdir()
    for module in (fs, quick_timer):
        source = Path(module.__file__)
        (directory / source.name).write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    registry = discover_actions(directory, logger=lambda _: None)
    assert registry.names() == {"file_search", "quick_timer"}
    assert "No active timers" in registry.run("quick_timer", {"action": "list"})
