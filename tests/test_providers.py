"""
tests/test_providers.py — one catalogue, believed by everything else.

The provider list used to exist in three shapes: a dropdown in `ui.py`, a
key-field map in `memory/config_manager.py`, and the branches of
`core/llm_client.py`. They drifted, and the drift was not theoretical: the setup
screen wrote `anthropic_api_key` for Claude while the reader derived
`claude_api_key`, so three providers could never be configured.

These tests hold the catalogue to the rest of the code: what the UI offers is
what the client can speak to, what is stored is what is read, and a model name
that reaches an API is never a placeholder.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import cli, providers
from memory import config_manager as cm


class CatalogueTests(unittest.TestCase):
    def test_every_provider_is_complete(self):
        self.assertGreaterEqual(len(providers.PROVIDERS), 8)
        for key, entry in providers.PROVIDERS.items():
            with self.subTest(provider=key):
                for field in ("name", "models", "default_model"):
                    self.assertTrue(entry.get(field), f"{key} has no {field}")
                self.assertIn(entry["default_model"], entry["models"])

    def test_every_provider_that_needs_a_key_has_a_field_and_a_docs_link(self):
        for key in providers.PROVIDERS:
            with self.subTest(provider=key):
                self.assertTrue(providers.docs_url(key).startswith("http"))
                if providers.needs_key(key):
                    self.assertIn(key, providers.KEY_FIELDS)
                else:
                    self.assertNotIn(key, providers.KEY_FIELDS,
                                     "a provider with no key must not claim a field")

    def test_only_gemini_claims_a_realtime_session(self):
        self.assertEqual(set(providers.REALTIME), {"gemini"})
        self.assertTrue(providers.is_realtime("gemini"))
        for other in ("claude", "gpt", "ollama", "openrouter"):
            self.assertFalse(providers.is_realtime(other))

    def test_no_provider_claims_a_key_it_does_not_need(self):
        self.assertFalse(providers.needs_key("ollama"))
        self.assertTrue(providers.needs_key("gemini"))


class CatalogueMatchesClientTests(unittest.TestCase):
    """The UI must not offer a provider that `call_unified` cannot speak to."""

    def test_every_offered_provider_is_implemented(self):
        source = (ROOT / "core" / "llm_client.py").read_text(encoding="utf-8")
        tree = ast.parse(source)

        compared: set[str] = set()
        for node in ast.walk(tree):
            if (isinstance(node, ast.Compare) and isinstance(node.left, ast.Name)
                    and node.left.id == "p"):
                for comparator in node.comparators:
                    if isinstance(comparator, ast.Constant) and isinstance(comparator.value, str):
                        compared.add(comparator.value)

        # Providers with their own branch. The rest are served by the shared
        # OpenAI-compatible path, which is exercised by the default-URL check below.
        dedicated = {"gemini", "claude", "ollama", "openrouter"}
        self.assertTrue(dedicated <= compared,
                        f"missing branches: {sorted(dedicated - compared)}")

        for key in set(providers.PROVIDERS) - dedicated:
            with self.subTest(provider=key):
                self.assertIn(key, providers.KEY_FIELDS,
                              "an OpenAI-compatible provider needs a known key field")

    def test_openai_compatible_providers_have_a_default_url(self):
        for key in ("gpt", "deepseek", "groq", "nvidia_nim", "opencode_zen"):
            with self.subTest(provider=key):
                self.assertTrue(providers.default_url(key).startswith("http"))


class NormaliseTests(unittest.TestCase):
    def test_aliases_resolve_to_canonical_ids(self):
        cases = {"OpenAI": "gpt", "chatgpt": "gpt", "Anthropic": "claude",
                 "local": "ollama", "Google": "gemini", "NVIDIA": "nvidia_nim"}
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(providers.normalise(raw), expected)

    def test_empty_means_the_default_provider(self):
        for value in (None, "", "   "):
            self.assertEqual(providers.normalise(value), "gemini")

    def test_an_unknown_name_survives_rather_than_becoming_gemini(self):
        # Silently substituting Gemini for a typo would hide the typo.
        self.assertEqual(providers.normalise("mistral_local"), "mistral_local")
        self.assertFalse(providers.exists("mistral_local"))


class ModelResolutionTests(unittest.TestCase):
    def test_placeholders_never_reach_an_api(self):
        for raw in ("", "   ", "default", "DEFAULT", "none", "null"):
            with self.subTest(raw=raw):
                self.assertEqual(providers.resolve_model("claude", raw),
                                 "claude-3-7-sonnet-20250219")

    def test_a_custom_model_name_is_kept_verbatim(self):
        self.assertEqual(providers.resolve_model("ollama", "my-finetune:7b"),
                         "my-finetune:7b")

    def test_curated_list_is_a_menu_not_a_cage(self):
        self.assertNotIn("my-finetune:7b", providers.models("ollama"))
        self.assertEqual(providers.resolve_model("ollama", "my-finetune:7b"),
                         "my-finetune:7b")


class SessionChoiceTests(unittest.TestCase):
    def test_no_overrides_uses_the_saved_choice(self):
        self.assertEqual(
            providers.session_choice("gemini", "gemini-2.5-flash"),
            ("gemini", "gemini-2.5-flash"))

    def test_provider_override_brings_its_own_default_model(self):
        # Without this, `--provider ollama` would inherit Gemini's model name.
        self.assertEqual(providers.session_choice("gemini", "gemini-2.5-flash", "ollama"),
                         ("ollama", "llama3.2"))

    def test_model_override_keeps_the_saved_provider(self):
        self.assertEqual(
            providers.session_choice("gemini", "gemini-2.5-flash", None, "gemini-2.5-pro"),
            ("gemini", "gemini-2.5-pro"))

    def test_both_overrides_win(self):
        self.assertEqual(
            providers.session_choice("gemini", "gemini-2.5-flash", "openai", "gpt-4o-mini"),
            ("gpt", "gpt-4o-mini"))


class WriterTests(unittest.TestCase):
    """save_ai_choice() is the only writer of ai_provider — so it must be right."""

    def setUp(self):
        import tempfile
        self._dir = tempfile.TemporaryDirectory()
        self._saved = cm.CONFIG_FILE
        cm.CONFIG_FILE = Path(self._dir.name) / "api_keys.json"

    def tearDown(self):
        cm.CONFIG_FILE = self._saved
        self._dir.cleanup()

    def test_saving_a_choice_writes_provider_model_and_key(self):
        cm.save_ai_choice("Claude", "claude-3-5-haiku-20241022", api_key="sk-ant-xyz")
        cfg = cm.load_api_keys()
        self.assertEqual(cfg["ai_provider"], "claude")
        self.assertEqual(cfg["ai_model"], "claude-3-5-haiku-20241022")
        self.assertEqual(cfg["anthropic_api_key"], "sk-ant-xyz")
        self.assertTrue(cm.is_configured())

    def test_an_empty_model_falls_back_to_the_provider_default(self):
        cm.save_ai_choice("groq", "")
        self.assertEqual(cm.load_api_keys()["ai_model"], providers.default_model("groq"))

    def test_saving_keeps_keys_that_were_already_there(self):
        cm.save_ai_choice("gemini", "gemini-2.5-flash", api_key="AIzaSy" + "z" * 33)
        cm.save_ai_choice("ollama", "llama3.2")
        cfg = cm.load_api_keys()
        self.assertEqual(cfg["gemini_api_key"], "AIzaSy" + "z" * 33)
        self.assertEqual(cfg["ai_provider"], "ollama")

    def test_changing_only_the_model_keeps_provider_and_key(self):
        cm.save_ai_choice("claude", "claude-3-7-sonnet-20250219", api_key="sk-ant-abc")
        self.assertEqual(cm.set_ai_model("claude-3-5-haiku-20241022"),
                         "claude-3-5-haiku-20241022")
        cfg = cm.load_api_keys()
        self.assertEqual(cfg["ai_provider"], "claude")
        self.assertEqual(cfg["anthropic_api_key"], "sk-ant-abc")

    def test_forget_key_removes_only_that_provider(self):
        cm.save_ai_choice("claude", "claude-3-7-sonnet-20250219", api_key="sk-ant-abc")
        cm.forget_key("claude")
        self.assertNotIn("anthropic_api_key", cm.load_api_keys())

    def test_a_corrupt_config_is_rewritten_rather_than_crashing(self):
        cm.CONFIG_FILE.write_text("{not json", encoding="utf-8")
        cm.save_ai_choice("gemini", "gemini-2.5-flash", api_key="AIzaSy" + "q" * 33)
        self.assertEqual(cm.load_api_keys()["ai_provider"], "gemini")


class CommandLineTests(unittest.TestCase):
    def test_no_arguments_means_last_used_choice(self):
        args = cli.parse_args([])
        self.assertEqual((args.provider, args.model, args.pick), (None, None, False))

    def test_provider_and_model_are_parsed(self):
        args = cli.parse_args(["--provider", "openai", "--model", "gpt-4o-mini", "--pick"])
        self.assertEqual((args.provider, args.model, args.pick),
                         ("openai", "gpt-4o-mini", True))

    def test_an_unknown_provider_is_rejected_with_the_list(self):
        import contextlib
        import io
        err = io.StringIO()
        with contextlib.redirect_stderr(err), self.assertRaises(SystemExit) as caught:
            cli.parse_args(["--provider", "nonsense"])
        self.assertEqual(caught.exception.code, 2)
        self.assertIn("unknown provider", err.getvalue())
        self.assertIn("gemini", err.getvalue())

    def test_an_unknown_flag_is_rejected_not_ignored(self):
        import contextlib
        import io
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            cli.parse_args(["--provder", "ollama"])
        self.assertEqual(caught.exception.code, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)


class ApplyChoiceTests(unittest.TestCase):
    """The rule behind the AI MODEL panel's Apply button."""

    def test_gemini_reconnects_because_the_stream_carries_the_model(self):
        d = providers.apply_choice("gemini", "gemini-2.5-flash", "gemini")
        self.assertTrue(d["ok"] and d["reconnect"])
        self.assertIn("reconnecting", d["message"])

    def test_switching_away_from_gemini_also_reconnects(self):
        # The live session has to be torn down before another provider takes over.
        self.assertTrue(providers.apply_choice("ollama", "llama3.2", "gemini")["reconnect"])

    def test_two_non_gemini_providers_need_no_reconnect(self):
        d = providers.apply_choice("ollama", "llama3.2", "claude")
        self.assertTrue(d["ok"])
        self.assertFalse(d["reconnect"])
        self.assertIn("next sentence", d["message"])

    def test_an_empty_model_becomes_the_provider_default(self):
        self.assertEqual(providers.apply_choice("groq", "")["model"],
                         providers.default_model("groq"))

    def test_an_unknown_provider_is_refused_without_saving(self):
        d = providers.apply_choice("mistral_local", "x", "gemini")
        self.assertFalse(d["ok"])
        self.assertIn("Unknown provider", d["message"])


class UnifiedVoiceTests(unittest.TestCase):
    def test_an_unreachable_ollama_says_what_to_do(self):
        from core import llm_client
        with self.assertRaises(RuntimeError) as caught:
            llm_client.call_unified("hi", provider="ollama", model="llama3.2", timeout=3)
        message = str(caught.exception)
        self.assertIn("not reachable", message)
        self.assertIn("ollama serve", message)

    def test_every_non_gemini_provider_is_routed_to_the_local_loop(self):
        # The switch lives in main.py's run(); the rule it must follow is that
        # only Gemini-with-a-live-model takes the realtime path.
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn('"live" in (model or "").lower()', source)
        self.assertIn("if not is_live_gemini:", source)

    def test_the_local_loop_reports_which_voice_path_is_running(self):
        source = (ROOT / "main.py").read_text(encoding="utf-8")
        self.assertIn("Voice: local speech loop", source)
