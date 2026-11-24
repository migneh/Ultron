import contextlib
import threading

import pytest

from actions import file_controller as files
from core import downloads as downloads
from core import undo
from core import web_research as web


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(files, "_SAFE_ROOTS", [tmp_path])
    undo.clear()
    yield
    undo.clear()


class Response:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status = status
        self.headers = headers or {}
        self.chunks = [b"binary\x00\xff"] if chunks is None else chunks
        self.closed = False

    def stream(self, *args, **kwargs):
        assert kwargs == {"decode_content": False}
        yield from self.chunks


def transport(monkeypatch, responses):
    visited = []
    monkeypatch.setattr(web, "addresses", lambda _: ["8.8.8.8"])

    @contextlib.contextmanager
    def opened(url, address, connect, read, **kwargs):
        assert kwargs == {"accept": "*/*"}
        assert address == "8.8.8.8" and 0 < connect <= 3 and 0 < read <= 4
        visited.append(url)
        response = responses.pop(0)
        try:
            yield response
        finally:
            response.closed = True

    monkeypatch.setattr(web, "_open", opened)
    return visited


def test_binary_download_and_undo(tmp_path, monkeypatch):
    response = Response(headers={"Content-Disposition": 'attachment; filename="other.exe"'})
    transport(monkeypatch, [response])
    output = files.download_file("https://example.com/file.bin", str(tmp_path))
    target = tmp_path / "file.bin"
    assert "Downloaded:" in output and "not opened" in output
    assert target.read_bytes() == b"binary\x00\xff" and response.closed
    assert not (tmp_path / "other.exe").exists()
    assert not list(tmp_path.glob("*.part"))
    undo.undo_last()
    assert not target.exists()


@pytest.mark.parametrize(
    "name",
    [
        "../escape",
        "a/b",
        "a\\b",
        "CON",
        "nul.txt",
        "COM1.zip",
        "a:stream",
        "trailing.",
        " leading",
        "bad\x00name",
        "bad\nname",
        "a\u202eb",
        "a" * 181,
    ],
)
def test_unsafe_names_before_network(tmp_path, monkeypatch, name):
    monkeypatch.setattr(downloads, "receive", lambda _: pytest.fail("network before validation"))
    output = files.download_file("https://example.com/file", str(tmp_path), name)
    assert "Unsafe filename" in output
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/file",
        "file:///etc/passwd",
        "https://user:pass@example.com/file",
        "https://example.com:444/file",
    ],
)
def test_private_or_invalid_url(tmp_path, url):
    assert "refused" in files.download_file(url, str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_encoded_url_filename_path_rejected(tmp_path):
    assert "Unsafe filename" in files.download_file(
        "https://example.com/%2e%2e%2fescape", str(tmp_path)
    )


def test_explicit_name_wins(tmp_path, monkeypatch):
    transport(monkeypatch, [Response()])
    assert "Downloaded:" in files.download_file(
        "https://example.com/%2f", str(tmp_path), "safe.bin"
    )
    assert (tmp_path / "safe.bin").exists()


@pytest.mark.parametrize("name", ["", "existing"])
def test_existing_file_never_overwritten(tmp_path, monkeypatch, name):
    (tmp_path / "existing").write_text("keep")
    monkeypatch.setattr(downloads, "receive", lambda _: pytest.fail("network on conflict"))
    assert "conflict" in files.download_file("https://example.com/existing", str(tmp_path), name)
    assert (tmp_path / "existing").read_text() == "keep"


def test_destination_requires_existing_directory(tmp_path):
    assert "existing directory" in files.download_file(
        "https://example.com/f", str(tmp_path / "missing")
    )
    assert not (tmp_path / "missing").exists()


@pytest.mark.parametrize(
    "response",
    [
        Response(404),
        Response(206),
        Response(headers={"Content-Encoding": "gzip"}),
        Response(headers={"Content-Length": "999999999"}),
        Response(headers={"Content-Length": "-1"}),
        Response(headers={"Content-Length": "9", "Transfer-Encoding": "chunked"}),
        Response(headers={"Content-Length": "999"}),
        Response(302, {"Location": "http://127.0.0.1/f"}),
        Response(302, {"Location": "http://example.com/f"}),
    ],
)
def test_rejected_responses_leave_no_files(tmp_path, monkeypatch, response):
    transport(monkeypatch, [response])
    assert "refused" in files.download_file("https://example.com/file", str(tmp_path))
    assert response.closed and not list(tmp_path.iterdir()) and not undo.can_undo()


def test_unknown_length_limit_no_partial_file(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, "MAX_BYTES", 3)
    response = Response(chunks=[b"12", b"34"])
    transport(monkeypatch, [response])
    assert "limit" in files.download_file("https://example.com/file", str(tmp_path))
    assert response.closed and not list(tmp_path.iterdir())


def test_redirects_and_dns_revalidated(tmp_path, monkeypatch):
    visited = transport(
        monkeypatch, [Response(302, {"Location": "https://other.example/file"}), Response()]
    )
    resolved = []

    def addresses(url):
        resolved.append(url)
        return ["8.8.8.8"]

    monkeypatch.setattr(web, "addresses", addresses)
    assert "Downloaded:" in files.download_file("https://example.com/file", str(tmp_path))
    assert visited == resolved and len(visited) == 2


def test_redirect_limit(tmp_path, monkeypatch):
    visited = transport(monkeypatch, [Response(302, {"Location": "/next"}) for _ in range(4)])
    assert "redirect limit" in files.download_file("https://example.com/file", str(tmp_path))
    assert len(visited) == 4 and not list(tmp_path.iterdir())


def test_stream_failure_no_publication(tmp_path, monkeypatch):
    class Broken(Response):
        def stream(self, *a, **k):
            yield b"partial"
            raise OSError("SECRET signed URL")

    response = Broken()
    transport(monkeypatch, [response])
    output = files.download_file("https://example.com/file", str(tmp_path))
    assert "SECRET" not in output and "failure" in output
    assert response.closed and not list(tmp_path.iterdir())


def test_publish_race_preserves_competitor(tmp_path, monkeypatch):
    transport(monkeypatch, [Response()])
    real = downloads.os.link

    def race(src, dst, **kwargs):
        dst.write_text("competitor")
        return real(src, dst, **kwargs)

    monkeypatch.setattr(downloads.os, "link", race)
    assert "failed" in files.download_file("https://example.com/file", str(tmp_path))
    assert (tmp_path / "file").read_text() == "competitor"
    assert len(list(tmp_path.iterdir())) == 1 and not undo.can_undo()


def test_undo_refuses_later_edit(tmp_path, monkeypatch):
    transport(monkeypatch, [Response()])
    files.download_file("https://example.com/file", str(tmp_path))
    (tmp_path / "file").write_text("edit")
    assert "Could not undo" in undo.undo_last()
    assert (tmp_path / "file").read_text() == "edit"


def test_timeout_worker_cannot_publish_later(tmp_path, monkeypatch):
    monkeypatch.setattr(downloads, "TOTAL_SECONDS", 0.02)
    release, finished = threading.Event(), threading.Event()

    def late(*args):
        release.wait(2)
        finished.set()
        return downloads.Payload(b"late", "https://example.com/file", "now")

    monkeypatch.setattr(downloads, "_receive", late)
    try:
        assert "deadline" in files.download_file("https://example.com/file", str(tmp_path))
        assert not list(tmp_path.iterdir())
    finally:
        release.set()
        assert finished.wait(2)
    assert not list(tmp_path.iterdir()) and not undo.can_undo()


def test_empty_file_valid(tmp_path, monkeypatch):
    transport(monkeypatch, [Response(headers={"Content-Length": "0"}, chunks=[])])
    assert "Downloaded:" in files.download_file("https://example.com/empty", str(tmp_path))
    assert (tmp_path / "empty").read_bytes() == b""


def test_symlink_destination_rejected_before_network(tmp_path, monkeypatch):
    actual = tmp_path / "actual"
    actual.mkdir()
    (tmp_path / "link").symlink_to(actual, target_is_directory=True)
    monkeypatch.setattr(downloads, "receive", lambda _: pytest.fail("network before path check"))
    assert "failed" in files.download_file("https://example.com/file", str(tmp_path / "link"))
    assert not list(actual.iterdir())


def test_private_dns_redirect_blocked(tmp_path, monkeypatch):
    response = Response(302, {"Location": "https://private.example/file"})
    transport(monkeypatch, [response])

    def addresses(url):
        if "private.example" in url:
            raise web.WebError("DNS blocked: every resolved address must be public")
        return ["8.8.8.8"]

    monkeypatch.setattr(web, "addresses", addresses)
    assert "DNS blocked" in files.download_file("https://example.com/file", str(tmp_path))
    assert response.closed and not list(tmp_path.iterdir())


def test_busy_worker_pool_no_publication(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "_SLOTS", threading.BoundedSemaphore(0))
    assert "busy" in files.download_file("https://example.com/file", str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_publish_failure_cleans_staging(tmp_path, monkeypatch):
    transport(monkeypatch, [Response()])

    def fail(*args, **kwargs):
        raise OSError("unsupported filesystem")

    monkeypatch.setattr(downloads.os, "link", fail)
    assert "failed" in files.download_file("https://example.com/file", str(tmp_path))
    assert not list(tmp_path.iterdir()) and not undo.can_undo()


def test_cleanup_failure_reports_success_and_warning(tmp_path, monkeypatch):
    from pathlib import Path

    transport(monkeypatch, [Response()])
    real = Path.unlink

    def fail_staging(path, **kwargs):
        if path.name.endswith(".part"):
            raise OSError("cleanup unavailable")
        return real(path, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_staging)
    output = files.download_file("https://example.com/file", str(tmp_path))
    assert "Downloaded:" in output and "WARNING" in output
    assert (tmp_path / "file").read_bytes() == b"binary\x00\xff" and undo.can_undo()


def test_disk_flush_failure_no_final_file(tmp_path, monkeypatch):
    transport(monkeypatch, [Response()])

    def fail(*args):
        raise OSError("disk failure")

    monkeypatch.setattr(downloads.os, "fsync", fail)
    assert "failed" in files.download_file("https://example.com/file", str(tmp_path))
    assert not list(tmp_path.iterdir())


def test_private_posix_permissions(tmp_path, monkeypatch):
    import os

    if os.name != "posix":
        pytest.skip("POSIX permissions only")
    transport(monkeypatch, [Response()])
    files.download_file("https://example.com/file", str(tmp_path))
    assert (tmp_path / "file").stat().st_mode & 0o777 == 0o600
