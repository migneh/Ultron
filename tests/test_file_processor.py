"""
tests/test_file_processor.py — document handling, exercised with real fixtures.

Bugs these lock down (all found by running the tool, not reading it):

  * every CSV action failed with `read_csv() got an unexpected keyword argument
    'errors'` — pandas spells it `encoding_errors`
  * asking a .txt file for its text wrote a copy next to it: the branch compared
    against "txt", but _detect_type() returns "text", so the inline return was
    unreachable
  * an unrecognised action with no instruction sent the model "\\n\\n<document>" —
    text with no task in it; and `translate` was documented nowhere and
    implemented nowhere
  * line counts were newline counts, so a file without a trailing newline
    reported one line fewer than it has

Optional dependencies (pandas, python-docx) are skipped cleanly where absent.
"""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import actions.file_processor as fp


class _FakeModel:
    """Captures the prompt instead of calling a real provider."""

    def __init__(self):
        self.prompt = ""

    def generate_content(self, prompt):
        self.prompt = prompt
        return types.SimpleNamespace(text="MODEL-OUTPUT")


class TextProcessorTests(unittest.TestCase):
    def setUp(self):
        self.dir = Path(tempfile.mkdtemp())
        self.txt = self.dir / "notes.txt"
        self.txt.write_text("Bonjour le monde.\nComment allez-vous?", encoding="utf-8")

    def test_extract_text_returns_content_instead_of_writing_a_copy(self):
        out = fp.file_processor({"file_path": str(self.txt), "action": "extract_text"})
        self.assertIn("Bonjour le monde", out)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["notes.txt"],
                         "extract_text wrote a redundant copy next to a text file")

    def test_word_count_counts_the_last_line(self):
        out = fp.file_processor({"file_path": str(self.txt), "action": "word_count"})
        self.assertIn("2 lines", out)          # file has no trailing newline

    def test_unknown_action_still_sends_a_task_to_the_model(self):
        fake = _FakeModel()
        original = fp._gemini_client
        fp._gemini_client = lambda tier="smart": fake
        try:
            fp.file_processor({"file_path": str(self.txt), "action": "summarise_and_tag"})
        finally:
            fp._gemini_client = original
        first_line = fake.prompt.splitlines()[0] if fake.prompt else ""
        self.assertTrue(first_line.strip(),
                        f"model received a prompt with no instruction: {fake.prompt[:60]!r}")
        self.assertIn("summarise_and_tag", first_line)

    def test_translate_uses_the_requested_language(self):
        fake = _FakeModel()
        original = fp._gemini_client
        fp._gemini_client = lambda tier="smart": fake
        try:
            fp.file_processor({"file_path": str(self.txt), "action": "translate",
                               "instruction": "English"})
        finally:
            fp._gemini_client = original
        self.assertIn("Translate", fake.prompt)
        self.assertIn("English", fake.prompt.splitlines()[0])

    def test_translate_without_instruction_defaults_to_english(self):
        fake = _FakeModel()
        original = fp._gemini_client
        fp._gemini_client = lambda tier="smart": fake
        try:
            fp.file_processor({"file_path": str(self.txt), "action": "translate"})
        finally:
            fp._gemini_client = original
        self.assertIn("English", fake.prompt.splitlines()[0])


class SpreadsheetTests(unittest.TestCase):
    def setUp(self):
        try:
            import pandas  # noqa: F401
        except ImportError:
            self.skipTest("pandas not installed — CSV/Excel analysis is optional")
        self.dir = Path(tempfile.mkdtemp())
        self.csv = self.dir / "data.csv"
        self.csv.write_text("name,qty\nwidget,3\ngadget,7\n", encoding="utf-8")

    def test_csv_info_reads_the_file(self):
        out = fp.file_processor({"file_path": str(self.csv), "action": "info"})
        self.assertIn("Rows: 2", out, out)
        self.assertIn("name", out)
        self.assertNotIn("unexpected keyword argument", out)

    def test_csv_stats_does_not_crash(self):
        out = fp.file_processor({"file_path": str(self.csv), "action": "stats"})
        self.assertNotIn("Could not read file", out, out)
        self.assertNotIn("unexpected keyword argument", out)

    def test_excel_info(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl not installed")
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.append(["name", "qty"]); ws.append(["widget", 3])
        book = self.dir / "book.xlsx"
        wb.save(book)
        out = fp.file_processor({"file_path": str(book), "action": "info"})
        self.assertIn("Rows: 1", out, out)


class DocxTests(unittest.TestCase):
    def test_docx_word_count_and_extract(self):
        try:
            from docx import Document
        except ImportError:
            self.skipTest("python-docx not installed")
        d = Path(tempfile.mkdtemp())
        doc = Document()
        doc.add_paragraph("Alpha paragraph")
        doc.add_paragraph("Beta paragraph")
        path = d / "doc.docx"
        doc.save(path)

        counted = fp.file_processor({"file_path": str(path), "action": "word_count"})
        self.assertIn("2 lines", counted, counted)

        extracted = fp.file_processor({"file_path": str(path), "action": "extract_text"})
        self.assertIn("Saved:", extracted)         # binary doc: saving a .txt is right here


class TypeDetectionTests(unittest.TestCase):
    def test_text_files_are_detected_as_text_not_txt(self):
        d = Path(tempfile.mkdtemp())
        for ext in ("txt", "md", "log"):
            f = d / f"x.{ext}"
            f.write_text("hi", encoding="utf-8")
            self.assertEqual(fp._detect_type(f), "text", f".{ext} misclassified")


if __name__ == "__main__":
    unittest.main(verbosity=2)
