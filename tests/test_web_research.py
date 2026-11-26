import contextlib
import threading

import pytest

from ultron.actions import web_autopilot as auto
from ultron.actions import web_search as search
from ultron.core import web_research as web


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "http://127.0.0.1/",
        "http://[::1]/",
        "https://user:pass@example.com",
        "https://example.com:444/",
        "http://localhost/",
        "http://a.local/",
        "https://example.com/\nsecret",
        "http://169.254.169.254/",
        "http://10.0.0.1/",
    ],
)
def test_block_urls(url):
    with pytest.raises(web.WebError):
        web.public_url(url)


def test_mixed_dns_blocked(monkeypatch):
    monkeypatch.setattr(
        web.socket,
        "getaddrinfo",
        lambda *a, **k: [(0, 0, 0, "", ("8.8.8.8", 80)), (0, 0, 0, "", ("127.0.0.1", 80))],
    )
    with pytest.raises(web.WebError):
        web.addresses("https://example.com/")


class Response:
    def __init__(self, status=200, headers=None, chunks=None):
        self.status = status
        self.headers = headers if headers is not None else {"Content-Type": "text/html"}
        self.chunks = chunks or [b"<title>Title</title><p>Hello world</p>"]
        self.closed = False

    def stream(self, *a, **k):
        yield from self.chunks


def setup_fetch(monkeypatch, responses):
    visited = []
    monkeypatch.setattr(web, "addresses", lambda url: ["8.8.8.8"])

    @contextlib.contextmanager
    def opened(url, *args):
        visited.append(url)
        response = responses.pop(0)
        try:
            yield response
        finally:
            response.closed = True

    monkeypatch.setattr(web, "_open", opened)
    return visited


def test_fetch_redirect_and_close(monkeypatch):
    first = Response(302, {"Location": "/article"})
    second = Response(headers={"Content-Type": "text/html", "Last-Modified": "yesterday"})
    visited = setup_fetch(monkeypatch, [first, second])
    page = web.fetch_page("https://example.com/")
    assert visited == ["https://example.com/", "https://example.com/article"]
    assert first.closed and second.closed
    assert page.last_modified == "yesterday"
    assert web.extract_document(page)["title"] == "Title"


@pytest.mark.parametrize(
    "response",
    [
        Response(302, {"Location": "http://127.0.0.1/"}),
        Response(200, {"Content-Type": "application/pdf"}),
        Response(200, {"Content-Type": "text/plain", "Content-Length": "999999"}),
        Response(200, {"Content-Type": "text/plain", "Content-Encoding": "gzip"}),
    ],
)
def test_fetch_rejects_unsafe_response(monkeypatch, response):
    setup_fetch(monkeypatch, [response])
    with pytest.raises(web.WebError):
        web.fetch_page("https://example.com/")
    assert response.closed


def test_stream_cap(monkeypatch):
    response = Response(headers={"Content-Type": "text/plain"}, chunks=[b"1234", b"5678"])
    setup_fetch(monkeypatch, [response])
    page = web.fetch_page("https://example.com/", web.FetchPolicy(max_bytes=6))
    assert page.text == "123456" and page.truncated and response.closed


def test_retry_bound(monkeypatch):
    responses = [Response(503), Response(503)]
    visited = setup_fetch(monkeypatch, responses)
    monkeypatch.setattr(web.time, "sleep", lambda _: None)
    with pytest.raises(web.WebError, match="503"):
        web.fetch_page("https://example.com/")
    assert len(visited) == 2


def test_worker_capacity(monkeypatch):
    monkeypatch.setattr(web, "_SLOTS", threading.BoundedSemaphore(1))
    release, finished = threading.Event(), threading.Event()

    def slow():
        release.wait(2)
        finished.set()

    try:
        assert "deadline" in web.bounded_call(slow, 0.01).error
        assert "busy" in web.bounded_call(lambda: None, 0.01).error
    finally:
        release.set()
        assert finished.wait(2)


def test_source_dates_dedupe_and_urls():
    rows = [
        {"title": "A", "href": "https://example.com/a", "date": "2026-11-23"},
        {"url": "https://example.com/a"},
        {"url": "file:///secret"},
    ]
    found = web.sources(rows, "test")
    assert len(found) == 1
    assert found[0]["published_at"] == "2026-11-23"
    assert "+00:00" in found[0]["retrieved_at"]


def test_ddgs_timeout_and_news_date(monkeypatch):
    class Client:
        def __init__(self, **kwargs):
            assert kwargs == {"timeout": 5}

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def news(self, *a, **k):
            return iter([{"url": "https://example.com/", "date": "today"}])

    monkeypatch.setattr(search, "_get_ddgs", lambda: Client)
    report = search._ddg_report("topic", news=True)
    assert report.results[0]["published_at"] == "today"


def test_grounding_required():
    response = {"candidates": [{"content": {"parts": [{"text": "Invented fact"}]}}]}
    report = search._parse_grounding(response, "q")
    assert not report.summary and report.issues
    response["candidates"][0]["grounding_metadata"] = {
        "grounding_chunks": [{"web": {"uri": "https://example.com/", "title": "Source"}}]
    }
    assert search._parse_grounding(response, "q").results


def test_fallback_reports_failure(monkeypatch):
    monkeypatch.setattr(
        search, "_gemini_report", lambda *a: web.ResearchReport("q", issues=["provider timed out"])
    )
    monkeypatch.setattr(
        search,
        "_ddg_report",
        lambda *a, **k: web.ResearchReport(
            "q", provider="DDGS", results=web.sources([{"url": "https://example.com/"}], "DDGS")
        ),
    )
    result = search.web_search({"query": "topic"})
    assert "timed out" in result and "PARTIAL" in result and "https://example.com/" in result


@pytest.mark.parametrize(
    "params",
    [
        None,
        {"query": 42},
        {"query": "a", "max_results": True},
        {"mode": []},
        {"mode": "compare", "items": ["a"]},
        {"query": "a", "unexpected": True},
    ],
)
def test_validation_without_network(params):
    assert "rejected" in search.web_search(params)


def test_excerpts_honest(monkeypatch):
    monkeypatch.setattr(
        auto,
        "fetch_page",
        lambda _: web.Page(
            "https://example.com/",
            "<script>evil()</script><p>Actual text</p>",
            "text/html",
            "now",
            truncated=True,
        ),
    )
    output = auto.summarize_web_page("https://example.com/")
    assert "Actual text" in output and "evil()" not in output
    assert "PARTIAL" in output and "not a synthesized summary" in output
    assert "No persistent memory" in output


def test_flights_no_invention_or_implicit_open(monkeypatch):
    import webbrowser

    monkeypatch.setattr(webbrowser, "open", lambda _: pytest.fail("implicit browser open"))
    monkeypatch.setattr(auto, "research", lambda *a: web.ResearchReport("flights"))
    assert "Specify both" in auto.flight_autopilot()
    output = auto.flight_autopilot(origin="Tunis", destination="Paris")
    assert "Browser not requested" in output and "No reservation" in output
    assert "IndiGo" not in output and "2h 10m" not in output
