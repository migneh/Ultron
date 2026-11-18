"""
tests/test_backlog.py — the backlog items, closed one at a time.

Each test corresponds to an entry in docs/BACKLOG.md that has now been dealt
with, so the claim can be checked rather than taken on trust.
"""
from __future__ import annotations

import importlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import ui_currency
from memory import config_manager as cm


class _TempConfig(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._saved = cm.CONFIG_FILE
        cm.CONFIG_FILE = Path(self._dir.name) / "api_keys.json"

    def tearDown(self):
        cm.CONFIG_FILE = self._saved
        self._dir.cleanup()


class CurrencyTests(_TempConfig):
    """bounty_hunter printed every price with a hard-coded $."""

    def test_a_detected_currency_wins_over_the_setting(self):
        self.assertEqual(ui_currency.money(74999, ui_currency.detect_symbol("Rs. 74,999")),
                         "Rs 74,999.00")

    def test_the_configured_symbol_is_used_when_nothing_was_detected(self):
        cm.save_currency_symbol("DT")
        self.assertEqual(cm.get_currency_symbol(), "DT ")
        self.assertEqual(ui_currency.money(60_000, cm.get_currency_symbol()),
                         "DT 60,000.00")

    def test_no_configuration_means_dollars(self):
        self.assertEqual(cm.get_currency_symbol(), "$")

    def test_an_unknown_symbol_falls_back_rather_than_printing_nonsense(self):
        self.assertEqual(ui_currency.normalise_symbol("a-very-long-thing"), "$")
        self.assertEqual(ui_currency.normalise_symbol(""), "$")

    def test_symbols_are_recognised_in_search_text(self):
        cases = {"Samsung at Rs 74,999": "Rs ",
                 "only €20 today": "€",
                 "£15.50": "£",
                 "no price here": ""}
        for text, expected in cases.items():
            with self.subTest(text=text):
                self.assertEqual(ui_currency.detect_symbol(text), expected)


class BountyHunterTests(unittest.TestCase):
    def setUp(self):
        from actions import bounty_hunter as bh
        self.bh = bh
        self._saved_file = bh._BOUNTIES_FILE
        self._dir = tempfile.TemporaryDirectory()
        bh._BOUNTIES_FILE = Path(self._dir.name) / "bounty_targets.json"
        self._saved_config = cm.CONFIG_FILE
        cm.CONFIG_FILE = Path(self._dir.name) / "api_keys.json"

    def tearDown(self):
        self.bh._BOUNTIES_FILE = self._saved_file
        cm.CONFIG_FILE = self._saved_config
        self._dir.cleanup()

    def _with_search(self, text: str) -> str:
        # bounty_hunter imports web_search *inside* the function, so the patch
        # has to land on the source module, not on the caller.
        import actions.web_search as web_search_module
        original = web_search_module.web_search
        web_search_module.web_search = lambda params: text
        self.addCleanup(setattr, web_search_module, "web_search", original)
        return self.bh.bounty_hunter({"product": "Samsung S24", "target_price": 60000})

    def test_a_rupee_price_is_not_reported_as_dollars(self):
        out = self._with_search("Samsung S24 — Rs. 74,999 today")
        self.assertIn("Rs 74,999.00", out)
        self.assertNotIn("$74,999", out)

    def test_a_dollar_price_still_reads_as_dollars(self):
        out = self._with_search("Samsung S24 — $749.99 today")
        self.assertIn("$749.99", out)

    def test_the_currency_is_stored_with_the_bounty(self):
        self._with_search("Rs. 74,999")
        saved = json.loads(Path(self.bh._BOUNTIES_FILE).read_text(encoding="utf-8"))
        self.assertEqual(saved[-1]["currency"], "Rs ")
        self.assertIn("Rs 60,000.00", self.bh.list_bounties())

    def test_no_price_found_is_stated_plainly(self):
        out = self._with_search("nothing useful on this page")
        self.assertIn("Market Price Probe", out)


class WakeWordTests(_TempConfig):
    """The wake phrase is a setting, because the model is not renameable."""

    def test_defaults_stay_the_pretrained_pair(self):
        from core import wake_word
        self.assertEqual(wake_word.WAKE_MODEL, "hey_jarvis")
        self.assertEqual(wake_word.WAKE_PHRASE, "Hey Jarvis")

    def test_a_configured_pair_is_honoured(self):
        cm.save_wake_word("ultron_v1", "Hey Ultron")
        self.assertEqual(cm.load_api_keys()["wake_phrase"], "Hey Ultron")
        self.assertEqual(cm.load_api_keys()["wake_model"], "ultron_v1")

        from core import wake_word
        reloaded = importlib.reload(wake_word)
        try:
            self.assertEqual(reloaded.WAKE_PHRASE, "Hey Ultron")
            self.assertEqual(reloaded.WAKE_MODEL, "ultron_v1")
        finally:
            # restore the real path *and* re-read, or the next test inherits
            # this configuration
            cm.CONFIG_FILE = self._saved
            importlib.reload(wake_word)

    def test_an_empty_setting_does_not_blank_the_phrase(self):
        model, phrase = cm.save_wake_word("", "")
        self.assertEqual((model, phrase), ("hey_jarvis", "Hey Jarvis"))


class DashboardLegacyNameTests(unittest.TestCase):
    """Legacy jarvis_* names are read for old phones, never written."""

    def test_login_no_longer_writes_the_old_names(self):
        text = (ROOT / "dashboard" / "static" / "login.html").read_text(encoding="utf-8")
        self.assertNotIn("setItem('jarvis_token'", text)
        self.assertNotIn("setItem('jarvis_key'", text)

    def test_the_app_still_reads_them_for_an_already_paired_phone(self):
        text = (ROOT / "dashboard" / "static" / "app.html").read_text(encoding="utf-8")
        self.assertIn("getItem('jarvis_token')", text)


class UploadOffTheLoopTests(unittest.TestCase):
    def test_the_upload_write_happens_in_a_thread(self):
        text = (ROOT / "dashboard" / "server.py").read_text(encoding="utf-8")
        self.assertIn("await asyncio.to_thread(fout.write, chunk)", text)


class DeadCodeTests(unittest.TestCase):
    def test_code_helper_no_longer_encodes_an_unused_screenshot(self):
        text = (ROOT / "actions" / "code_helper.py").read_text(encoding="utf-8")
        self.assertNotIn("image_base64", text)

    def test_removing_the_dead_encoder_kept_its_neighbours(self):
        # The first attempt cut from `def _image_to_base64` to the next `def `,
        # which took _VALID_INTENTS with it. ruff saw it (F821); this test keeps
        # it seen.
        from actions import code_helper
        self.assertEqual(code_helper._VALID_INTENTS,
                         {"write", "edit", "explain", "run", "build",
                          "screen_debug", "optimize"})

    def test_bounty_hunter_has_no_unused_title(self):
        text = (ROOT / "actions" / "bounty_hunter.py").read_text(encoding="utf-8")
        self.assertNotIn("detected_title", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class BrowserPrivacyTests(unittest.TestCase):
    """Private browsing: a throwaway profile, never the user's own."""

    def setUp(self):
        from actions import browser_control
        self.bc = browser_control

    def test_the_schema_offers_the_flag(self):
        self.assertIn("private", self.bc.TOOL["parameters"]["properties"])

    def test_a_private_session_is_launched_before_the_real_profile_is_chosen(self):
        source = (ROOT / "actions" / "browser_control.py").read_text(encoding="utf-8")
        launch = source[source.index("    async def _launch(self):"):]
        launch = launch[:launch.index("    async def _launch_incognito")]
        self.assertIn("if self.incognito:", launch)
        # ... and before the real profile is even resolved
        self.assertLess(launch.index("if self.incognito:"),
                        launch.index("_real_profile_dir(self.browser_name)"))

    def test_a_private_profile_is_deleted_on_close(self):
        import tempfile
        sess = self.bc._BrowserSession.__new__(self.bc._BrowserSession)
        sess._incognito_dir = tempfile.mkdtemp(prefix="ultron-test-private-")
        Path(sess._incognito_dir, "Cookies").write_text("x", encoding="utf-8")
        gone = sess._incognito_dir
        sess._discard_incognito_dir()
        self.assertFalse(Path(gone).exists())
        self.assertIsNone(sess._incognito_dir)

    def test_the_private_launcher_has_no_fallback_to_the_real_profile(self):
        source = (ROOT / "actions" / "browser_control.py").read_text(encoding="utf-8")
        body = source[source.index("async def _launch_incognito"):]
        body = body[:body.index("def _discard_incognito_dir")]
        self.assertNotIn("_real_profile_dir", body)
        self.assertIn("mkdtemp", body)


class WindowsOcrTests(unittest.TestCase):
    """The OCR fallback that used to be a PowerShell string nobody ran."""

    def test_non_windows_returns_empty_rather_than_raising(self):
        from actions import optical_hud
        self.assertEqual(optical_hud._windows_ocr("/tmp/definitely-not-here.png"), "")

    def test_the_recogniser_is_actually_invoked(self):
        source = (ROOT / "actions" / "optical_hud.py").read_text(encoding="utf-8")
        body = source[source.index("def _extract_text_from_image"):]
        body = body[:body.index("def _windows_ocr")]
        self.assertIn("_windows_ocr(image_path)", body)
        self.assertNotIn("ps_script", body)

    def test_the_script_is_complete_enough_to_return_text(self):
        from actions import optical_hud
        script = optical_hud._WINDOWS_OCR_SCRIPT
        for fragment in ("Windows.Media.Ocr.OcrEngine", "RecognizeAsync",
                         "ULTRON_OCR_IMAGE", "Write-Output"):
            with self.subTest(fragment=fragment):
                self.assertIn(fragment, script)

    def test_a_failing_recogniser_is_not_an_exception(self):
        from actions import optical_hud
        import subprocess
        original = subprocess.run

        def boom(*a, **k):
            raise OSError("powershell missing")

        subprocess.run = boom
        try:
            import sys
            saved = sys.platform
            sys.platform = "win32"                     # take the Windows branch
            try:
                self.assertEqual(optical_hud._windows_ocr("C:/x.png"), "")
            finally:
                sys.platform = saved
        finally:
            subprocess.run = original
