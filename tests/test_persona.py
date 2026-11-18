"""
tests/test_persona.py — the system prompt must follow the user's own language.

What used to happen: `_build_full_system_prompt()` concatenated a Hindi speech
protocol into *every* prompt, and the address line always carried
"(or 'बॉस' in Hindi)". An English-only user paid those tokens on every turn and
was instructed to answer in a language they had not chosen — the fork author's
language, baked into the assistant's persona.

Now the decision is a pure function of `memory.identity.language`, so it is
testable without the GUI, the microphone or a model.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from core import persona


class NormalizeLanguageTests(unittest.TestCase):
    def test_empty_falls_back_to_english(self):
        for value in (None, "", "   "):
            self.assertEqual(persona.normalize_language(value), "English")

    def test_aliases_are_canonicalised(self):
        for raw in ("hi", "HI", "hi-IN", "Hinglish", "हिंदी", " hindi "):
            self.assertEqual(persona.normalize_language(raw), "hindi", raw)

    def test_unknown_language_survives_unchanged(self):
        # A language with no protocol block still reaches the session summary,
        # which asks the model to summarise in that language.
        self.assertEqual(persona.normalize_language("Arabic"), "Arabic")


class SpeechProtocolTests(unittest.TestCase):
    def test_english_gets_no_extra_block(self):
        for value in ("English", "en", "en-GB", None, ""):
            self.assertEqual(persona.speech_protocol(value), "", repr(value))

    def test_hindi_gets_its_protocol(self):
        block = persona.speech_protocol("Hindi")
        self.assertIn("HINDI & BILINGUAL SPEECH PROTOCOL", block)
        self.assertIn("बॉस", block)

    def test_protocol_is_a_single_block_ending_in_a_blank_line(self):
        block = persona.speech_protocol("hi")
        self.assertTrue(block.endswith("\n\n"))
        self.assertEqual(block.count("HINDI & BILINGUAL"), 1)


class AddressLineTests(unittest.TestCase):
    def test_english_user_is_never_shown_another_script(self):
        line = persona.address_line("Ada", "English")
        self.assertIn("Boss Ada", line)
        self.assertTrue(all(ord(ch) < 128 for ch in line), line)

    def test_named_user_gets_named_address(self):
        self.assertEqual(persona.address_line("Ada", None),
                         "ADDRESS: Always address the user as 'Boss Ada' or 'Boss'.")

    def test_unnamed_user_keeps_the_ultron_wording(self):
        line = persona.address_line("", "English")
        self.assertIn('address the user as "Boss"', line)
        self.assertIn("Never say \"sir\"", line)

    def test_hindi_user_gets_the_native_form(self):
        line = persona.address_line("Ada", "hindi")
        self.assertIn("'बॉस' in Hindi", line)

    def test_whitespace_only_name_is_treated_as_missing(self):
        self.assertIn("as \"Boss\"", persona.address_line("   ", "English"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
