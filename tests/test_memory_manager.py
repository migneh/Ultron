"""
tests/test_memory_manager.py — the store the user's personal facts live in.

Everything here runs against a temporary `long_term.json`: no test touches the
real memory of the machine it runs on.

Bugs these lock down (each reproduced first, then fixed):

  * an invented category was written to disk but could never be read back.
    `save_memory` takes its category from the model as free text; a value like
    "work" became a new top-level key, and both the prompt builder and the
    `[ALSO REMEMBERED]` index only look at the six known categories — so the
    fact existed, the assistant said "I don't know", and nothing told anyone.
  * category="sessions" replaced the session-summary *list* with a dict; the
    next save_session_summary() reset it to [] and the previous summaries were
    gone.
  * a bare string for a whole category ("notes": "hates cilantro") replaced that
    category wholesale.
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

from memory import memory_manager as mm


class _TempMemory(unittest.TestCase):
    """Points the module at a throwaway file and restores everything after."""

    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self._saved_path = mm.MEMORY_PATH
        self._saved_max = mm.MEMORY_MAX_CHARS
        self._saved_notifier = mm._trim_notifier
        mm.MEMORY_PATH = Path(self._dir.name) / "long_term.json"
        mm._trim_notifier = None

    def tearDown(self):
        mm.MEMORY_PATH = self._saved_path
        mm.MEMORY_MAX_CHARS = self._saved_max
        mm._trim_notifier = self._saved_notifier
        self._dir.cleanup()


class CategoryRoutingTests(_TempMemory):
    def test_an_invented_category_is_kept_and_visible(self):
        mm.update_memory({"work": {"employer": {"value": "Acme Robotics"}}})

        memory = mm.load_memory()
        self.assertIn("employer", memory["notes"])
        self.assertNotIn("work", memory)

        prompt = mm.format_memory_for_prompt(memory)
        self.assertIn("Acme Robotics", prompt)

    def test_two_invented_categories_both_survive(self):
        mm.update_memory({"work": {"employer": {"value": "Acme"}}})
        mm.update_memory({"hobbies": {"climbing": {"value": "bouldering"}}})

        notes = mm.load_memory()["notes"]
        self.assertIn("employer", notes)
        self.assertIn("climbing", notes)

    def test_a_fact_in_an_invented_category_is_recallable(self):
        mm.update_memory({"work": {"employer": {"value": "Acme Robotics"}}})
        self.assertIn("Acme", mm.search_memory("employer"))

    def test_session_summaries_survive_a_write_into_sessions(self):
        mm.save_session_summary("Talked about the rover project.")
        mm.update_memory({"sessions": {"day1": {"value": "oops"}}})

        sessions = mm.load_memory()["sessions"]
        self.assertIsInstance(sessions, list)
        self.assertIn("rover", json.dumps(sessions))

    def test_a_bare_string_does_not_replace_a_whole_category(self):
        mm.update_memory({"notes": {"allergy": {"value": "penicillin"}}})
        mm.update_memory({"notes": "hates cilantro"})

        notes = mm.load_memory()["notes"]
        self.assertIn("allergy", notes)
        self.assertIn("cilantro", mm.format_memory_for_prompt(mm.load_memory()))

    def test_known_categories_are_untouched(self):
        mm.update_memory({"identity": {"name": {"value": "Ada"}},
                          "projects": {"rover": {"value": "building a rover"}}})
        memory = mm.load_memory()
        self.assertIn("name", memory["identity"])
        self.assertIn("rover", memory["projects"])

    def test_empty_or_invalid_updates_change_nothing(self):
        mm.update_memory({"identity": {"name": {"value": "Ada"}}})
        before = mm.load_memory()
        for payload in ({}, None, {"notes": ""}, {"notes": None}, 42):
            mm.update_memory(payload)
        self.assertEqual(mm.load_memory(), before)


class PromptBlockTests(_TempMemory):
    def test_identity_is_always_shown(self):
        mm.update_memory({"identity": {"name": {"value": "Ada"},
                                       "city": {"value": "Tunis"}}})
        prompt = mm.format_memory_for_prompt(mm.load_memory())
        self.assertIn("Name: Ada", prompt)
        self.assertIn("City: Tunis", prompt)

    def test_language_is_labelled_as_an_observation(self):
        # A bare "Language: English" line reads like a standing order and made
        # the assistant answer older questions in the wrong language.
        mm.update_memory({"identity": {"language": {"value": "English"}}})
        prompt = mm.format_memory_for_prompt(mm.load_memory())
        self.assertIn("Has spoken to you in: English", prompt)
        self.assertIn("CURRENT message", prompt)

    def test_overflowing_entries_are_indexed_not_lost(self):
        for i in range(40):
            mm.update_memory({"preferences": {f"pref_{i}": {"value": "x" * 40}}})

        prompt = mm.format_memory_for_prompt(mm.load_memory())
        self.assertIn("ALSO REMEMBERED", prompt)
        self.assertLess(len(prompt), 4000)
        # The entry that did not fit is still named in the index. Keys are
        # humanised there ("pref_39" → "pref 39"), which recall_memory still
        # matches because it scores word by word.
        self.assertIn("pref 39", prompt)
        self.assertIn("x", mm.search_memory("pref_39"))

    def test_empty_memory_produces_no_block(self):
        self.assertEqual(mm.format_memory_for_prompt({}), "")
        self.assertEqual(mm.format_memory_for_prompt(None), "")


class RecallTests(_TempMemory):
    def test_the_exact_snake_case_key_can_be_looked_up(self):
        # The schema tells the model keys are snake_case ("sister_name"), and
        # the block shows them humanised ("sister name"). Querying the key as
        # written used to score zero: "Nothing stored about 'sister_name'".
        mm.update_memory({"relationships": {"sister_name": {"value": "Ada"}}})
        for query in ("sister_name", "sister", "Sister name", "ada"):
            self.assertIn("Ada", mm.search_memory(query), query)

    def test_an_unknown_query_says_nothing_is_stored(self):
        mm.update_memory({"notes": {"allergy": {"value": "penicillin"}}})
        self.assertIn("Nothing stored", mm.search_memory("helicopter"))

    def test_empty_query_lists_what_is_stored(self):
        mm.update_memory({"notes": {"allergy": {"value": "penicillin"}}})
        listing = mm.search_memory("")
        self.assertIn("Everything currently stored", listing)
        self.assertIn("penicillin", listing)

    def test_empty_memory_says_so_plainly(self):
        self.assertIn("not stored anything", mm.search_memory(""))


class CorruptStoreTests(_TempMemory):
    def test_startup_survives_an_unreadable_store(self):
        mm.MEMORY_PATH.write_text("{not json at all", encoding="utf-8")
        memory = mm.load_memory()
        self.assertEqual(memory["identity"], {})

    def test_the_unreadable_bytes_are_kept_rather_than_overwritten(self):
        mm.MEMORY_PATH.write_text("{not json at all", encoding="utf-8")
        mm.load_memory()

        kept = list(mm.MEMORY_PATH.parent.glob("long_term.corrupt-*.json"))
        self.assertEqual(len(kept), 1, "the unreadable file must not simply vanish")
        self.assertIn("not json", kept[0].read_text(encoding="utf-8"))

    def test_a_valid_but_wrong_shaped_file_is_also_set_aside(self):
        mm.MEMORY_PATH.write_text("[1, 2, 3]", encoding="utf-8")
        self.assertEqual(mm.load_memory()["identity"], {})
        self.assertEqual(len(list(mm.MEMORY_PATH.parent.glob("long_term.corrupt-*.json"))), 1)

    def test_a_missing_store_is_not_an_error(self):
        self.assertFalse(mm.MEMORY_PATH.exists())
        self.assertEqual(mm.load_memory()["identity"], {})
        self.assertEqual(list(mm.MEMORY_PATH.parent.glob("*corrupt*")), [])


class TrimTests(_TempMemory):
    def test_oldest_entries_are_dropped_first_and_reported(self):
        mm.MEMORY_MAX_CHARS = 600
        noticed: list[str] = []
        mm._trim_notifier = noticed.append

        mm.update_memory({"notes": {"old": {"value": "a" * 200, "updated": "2020-01-01"}}})
        mm.update_memory({"notes": {"new": {"value": "b" * 200}}})
        mm.update_memory({"notes": {"newest": {"value": "c" * 200}}})
        mm.save_memory(mm.load_memory())          # force the trim check

        notes = mm.load_memory()["notes"]
        self.assertNotIn("old", notes)
        self.assertIn("newest", notes)
        self.assertTrue(noticed, "a trim must tell the user, not just the console")
        self.assertIn("forgot", noticed[0])


class RememberForgetTests(_TempMemory):
    def test_remember_clamps_an_unknown_category(self):
        mm.remember("employer", "Acme", category="work")
        memory = mm.load_memory()
        self.assertIn("employer", memory["notes"])
        self.assertIn("Acme", memory["notes"]["employer"]["value"])

    def test_forget_removes_one_entry(self):
        mm.remember("allergy", "penicillin", category="notes")
        self.assertIn("allergy", mm.load_memory()["notes"])
        self.assertIn("Forgotten", mm.forget("allergy"))
        self.assertNotIn("allergy", mm.load_memory()["notes"])

    def test_forget_of_a_missing_key_says_so(self):
        self.assertIn("Not found", mm.forget("nothing_here"))


if __name__ == "__main__":
    unittest.main(verbosity=2)
