"""
tests/test_browser_control.py — the browser tool's pure logic, without a browser.

No Chromium can be downloaded in this environment (`playwright install chromium`
needs network), so nothing here claims a browser was launched. What *is* tested
is every part that decides what happens before Chromium is involved, using a
faked session object:

  * `_normalize_url` — "localhost:8000" (this app's own dashboard) used to
    become "https://localhost:8000.com", and "about:blank" became
    "https://about:blank.com", so both were unreachable
  * `_SessionRegistry.close_one` — every other registry call resolved aliases
    ("google chrome" → "chrome"), close_one did not: closing by alias reported
    "No active session for: google chrome" while the session kept running, and
    a session whose close() timed out raised out of browser_control() entirely
  * the TOOL schema — it advertised an `incognito` parameter that no code path
    ever read, so "open this in incognito" silently used the user's real,
    logged-in profile
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    from actions import browser_control as bc
    _IMPORT_ERROR = ""
except Exception as exc:                      # pragma: no cover - environment only
    bc = None
    _IMPORT_ERROR = f"{type(exc).__name__}: {exc}"

needs_module = unittest.skipUnless(bc is not None, f"browser_control unavailable ({_IMPORT_ERROR})")


class _FakeSession:
    """Stands in for a _BrowserSession: records closes, can fail on purpose."""

    def __init__(self, name: str, fail: bool = False):
        self.browser_name = name
        self.fail         = fail
        self.closed       = False

    def close(self):
        if self.fail:
            raise TimeoutError("close hung")
        self.closed = True


@needs_module
class NormalizeUrlTests(unittest.TestCase):
    def test_bare_word_becomes_dot_com(self):
        self.assertEqual(bc._normalize_url("instagram"), "https://instagram.com")

    def test_domain_gets_https(self):
        self.assertEqual(bc._normalize_url("instagram.com"), "https://instagram.com")

    def test_full_url_is_untouched(self):
        for url in ("https://x.com/a?b=1", "http://neverssl.com", "file:///tmp/a.html"):
            self.assertEqual(bc._normalize_url(url), url)

    def test_localhost_with_port_keeps_http_and_port(self):
        # The dashboard this repo ships listens on localhost:8000.
        self.assertEqual(bc._normalize_url("localhost:8000"), "http://localhost:8000")
        self.assertEqual(bc._normalize_url("localhost:8000/api/state"),
                         "http://localhost:8000/api/state")

    def test_loopback_and_lan_addresses_keep_http(self):
        self.assertEqual(bc._normalize_url("127.0.0.1:8000"), "http://127.0.0.1:8000")
        self.assertEqual(bc._normalize_url("192.168.1.5:5000/admin"),
                         "http://192.168.1.5:5000/admin")

    def test_about_blank_is_not_mangled(self):
        self.assertEqual(bc._normalize_url("about:blank"), "about:blank")

    def test_empty_becomes_about_blank(self):
        self.assertEqual(bc._normalize_url("   "), "about:blank")

    def test_public_host_keeps_its_scheme(self):
        self.assertEqual(bc._normalize_url("example.com:8080/path"),
                         "https://example.com:8080/path")


@needs_module
class SessionRegistryTests(unittest.TestCase):
    def setUp(self):
        self.reg = bc._SessionRegistry()

    def _add(self, key, **kw):
        sess = _FakeSession(key, **kw)
        self.reg._sessions[key] = sess
        self.reg._active_browser = key
        return sess

    def test_close_one_resolves_aliases_like_the_other_calls(self):
        sess = self._add("chrome")
        self.assertTrue(self.reg.has("google chrome"))

        result = self.reg.close_one("google chrome")

        self.assertEqual(result, "chrome closed.")
        self.assertTrue(sess.closed)
        self.assertNotIn("chrome", self.reg._sessions)
        self.assertEqual(self.reg._active_browser, "")

    def test_close_one_is_case_insensitive(self):
        sess = self._add("edge")
        self.assertEqual(self.reg.close_one("  EDGE "), "edge closed.")
        self.assertTrue(sess.closed)

    def test_close_one_reports_unknown_browser_without_raising(self):
        self.assertEqual(self.reg.close_one("firefox"), "No active session for: firefox")

    def test_a_hung_close_does_not_escape_the_registry(self):
        sess = self._add("chrome", fail=True)

        result = self.reg.close_one("chrome")     # must not raise

        self.assertEqual(result, "chrome closed.")
        self.assertFalse(sess.closed)
        self.assertNotIn("chrome", self.reg._sessions)
        self.assertEqual(self.reg._active_browser, "")

    def test_list_sessions_marks_the_active_browser(self):
        self._add("chrome")
        self.reg._sessions["firefox"] = _FakeSession("firefox")
        listing = self.reg.list_sessions()
        self.assertIn("chrome ◀ active", listing)
        self.assertIn("firefox", listing)
        self.assertNotIn("firefox ◀ active", listing)

    def test_native_url_is_consumed_once(self):
        self.reg.note_native_url("https://a.example")
        self.assertEqual(self.reg.pop_native_url(), "https://a.example")
        self.assertEqual(self.reg.pop_native_url(), "")


@needs_module
class ToolSchemaTests(unittest.TestCase):
    """The declaration the model sees must match what the handler can do."""

    def setUp(self):
        import inspect
        self.source = inspect.getsource(bc)

    def test_every_declared_parameter_is_read_somewhere(self):
        declared = set(bc.TOOL["parameters"]["properties"])
        unread = {p for p in declared if f'params.get("{p}"' not in self.source}
        self.assertEqual(unread, set(),
                         f"declared in TOOL but never read: {sorted(unread)}")

    def test_every_advertised_action_is_routed(self):
        actions = bc.TOOL["parameters"]["properties"]["action"]["description"]
        names = [a.strip() for a in actions.split("|") if a.strip()]
        self.assertGreater(len(names), 10)
        missing = [a for a in names if f'"{a}"' not in self.source]
        self.assertEqual(missing, [], f"advertised but not routed: {missing}")


class PersonaIndependenceTests(unittest.TestCase):
    """main.py must not hard-code another language into every prompt."""

    def test_main_delegates_language_text_to_core_persona(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("speech_protocol(_lang)", source)
        self.assertIn("address_line(_user_name, _lang)", source)

    def test_english_prompt_carries_no_other_language_block(self):
        # Both of these used to be unconditional, so every user — including an
        # English-only one — was told to answer in Hindi.
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertFalse("'बॉस' in Hindi" in source,
                         "the address line still hard-codes a Hindi form")
        self.assertFalse("HINDI & BILINGUAL SPEECH PROTOCOL" in source,
                         "the Hindi protocol is still inlined into every prompt")


if __name__ == "__main__":
    unittest.main(verbosity=2)
