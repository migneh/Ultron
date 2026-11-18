"""
tests/test_config_manager.py — the first five minutes of a fresh clone.

The README's quickstart was `cp config/api_keys.json.example config/api_keys.json`,
and the file it copied did not match what the code reads:

  * it said `"provider": "gemini"` while every reader asks for `ai_provider`, so
    the app considered itself unconfigured and showed the setup overlay anyway;
  * it carried `"gemini_api_key": "YOUR_GEMINI_API_KEY_HERE"`, and the "is it
    configured?" test was `len(key) > 3` — so an untouched placeholder counted
    as a real key and the app started, then failed with an opaque auth error;
  * the gate also demanded `os_system`, although every consumer already falls
    back to platform detection — a good config without it re-opened the setup
    overlay on every launch.

Every test points the module at a temporary api_keys.json; the real one is never
read or written.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory import config_manager as cm

EXAMPLE = ROOT / "config" / "api_keys.json.example"


class _TempConfig(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._saved = cm.CONFIG_FILE
        cm.CONFIG_FILE = Path(self._dir.name) / "api_keys.json"

    def tearDown(self):
        cm.CONFIG_FILE = self._saved
        self._dir.cleanup()

    def write(self, data: dict) -> None:
        cm.CONFIG_FILE.write_text(json.dumps(data), encoding="utf-8")


class ExampleFileTests(_TempConfig):
    def test_the_shipped_example_is_a_config_the_code_understands(self):
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual(example["ai_provider"], "gemini")
        self.assertIn("ai_model", example)

        cm.CONFIG_FILE.write_text(json.dumps(example), encoding="utf-8")
        self.assertEqual(cm.get_ai_provider(), "gemini")
        self.assertNotEqual(cm.get_ai_model(), "")

    def test_the_shipped_example_is_not_mistaken_for_a_working_key(self):
        cm.CONFIG_FILE.write_text(EXAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
        self.assertFalse(cm.is_configured(),
                         "an untouched placeholder must send the user to setup")

    def test_the_example_works_once_the_key_is_replaced(self):
        example = json.loads(EXAMPLE.read_text(encoding="utf-8"))
        example["gemini_api_key"] = "AIzaSy" + "b" * 33
        self.write(example)
        self.assertTrue(cm.is_configured())


class ConfiguredTests(_TempConfig):
    def test_no_file_means_not_configured(self):
        self.assertFalse(cm.is_configured())

    def test_a_real_gemini_key_is_configured(self):
        self.write({"ai_provider": "gemini", "gemini_api_key": "AIzaSy" + "c" * 33})
        self.assertTrue(cm.is_configured())

    def test_a_missing_provider_is_not_configured(self):
        self.write({"gemini_api_key": "AIzaSy" + "c" * 33})
        self.assertFalse(cm.is_configured())

    def test_os_system_is_not_required(self):
        # Every consumer auto-detects the platform; demanding the key here showed
        # the setup overlay on every launch for an otherwise good config.
        self.write({"ai_provider": "gpt", "openai_api_key": "sk-" + "d" * 20})
        self.assertTrue(cm.is_configured())

    def test_ollama_needs_no_key(self):
        self.write({"ai_provider": "ollama"})
        self.assertTrue(cm.is_configured())

    def test_each_provider_reads_its_own_key(self):
        cases = {
            "gemini":      ("gemini_api_key", "AIzaSy" + "e" * 33),
            "gpt":         ("openai_api_key", "sk-" + "f" * 20),
            "claude":      ("anthropic_api_key", "sk-ant-" + "g" * 20),
            "deepseek":    ("deepseek_api_key", "sk-" + "h" * 20),
            "groq":        ("groq_api_key", "gsk_" + "i" * 20),
            "openrouter":  ("openrouter_api_key", "sk-or-" + "j" * 20),
            "nvidia_nim":  ("nvidia_api_key", "nvapi-" + "k" * 20),
            "opencode_zen": ("opencode_api_key", "zen-" + "l" * 20),
        }
        for provider, (field, key) in cases.items():
            with self.subTest(provider=provider):
                self.write({"ai_provider": provider, field: key})
                self.assertTrue(cm.is_configured())
                self.assertEqual(cm.get_provider_key(), key)


class PlaceholderTests(unittest.TestCase):
    def test_shipped_and_hand_typed_placeholders_are_recognised(self):
        for value in ("YOUR_GEMINI_API_KEY_HERE", "your-api-key", "<your key>",
                      "replace_me", "paste_key_here", "changeme", "API_KEY_HERE",
                      "xxxxxxxx", "sk-example", "", "   ", None):
            with self.subTest(value=value):
                self.assertTrue(cm.looks_like_placeholder(value))

    def test_real_looking_keys_pass(self):
        for value in ("AIzaSyD-1234567890abcdefghijklmnopqrstu",
                      "sk-proj-abc123DEF456ghi789",
                      "gsk_0123456789abcdef",
                      "nvapi-ABCdef123456"):
            with self.subTest(value=value):
                self.assertFalse(cm.looks_like_placeholder(value))


class ModelNameTests(_TempConfig):
    def test_whitespace_model_falls_back_to_the_provider_default(self):
        # `if cfg["ai_model"]` was true for "   ", so the stripped-to-empty value
        # was returned: a model name of "" on a provider that has a default.
        self.write({"ai_provider": "gemini", "ai_model": "   ",
                    "gemini_api_key": "AIzaSy" + "m" * 33})
        self.assertEqual(cm.get_ai_model(), "gemini-2.5-flash")

    def test_configured_model_wins(self):
        self.write({"ai_provider": "gemini", "ai_model": "gemini-2.5-pro"})
        self.assertEqual(cm.get_ai_model(), "gemini-2.5-pro")

    def test_unknown_provider_still_gets_a_model(self):
        self.write({"ai_provider": "something_new"})
        self.assertNotEqual(cm.get_ai_model(), "")


class ProviderAgreementTests(_TempConfig):
    def test_missing_provider_does_not_mean_ollama(self):
        # main.py's unified helpers used to fall back to "ollama" here, sending a
        # user with a Gemini key to a local server that is not running.
        self.write({"gemini_api_key": "AIzaSy" + "n" * 33})
        self.assertEqual(cm.get_ai_provider() or "gemini", "gemini")
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertFalse('get_ai_provider() or "ollama"' in source,
                         "main.py must agree with llm_client on the default provider")


if __name__ == "__main__":
    unittest.main(verbosity=2)
