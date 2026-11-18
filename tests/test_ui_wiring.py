"""
tests/test_ui_wiring.py — Qt cannot be started here, so the wiring is checked by
reading the source.

This exists because of a specific near-miss: a `self._open_ai_model` button
handler was added inside `MainWindow` while it could have been added to a
sibling widget class, where Qt would have raised `AttributeError` on the first
click and nowhere earlier. The checks below are the kind that fail on a typo or
a misplaced method; they are not a substitute for opening the window, and this
file does not claim the GUI was run.
"""
from __future__ import annotations

import ast
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

UI = ROOT / "ui.py"


def _classes() -> dict[str, ast.ClassDef]:
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    return {n.name: n for n in ast.walk(tree) if isinstance(n, ast.ClassDef)}


def _methods(node: ast.ClassDef) -> set[str]:
    return {n.name for n in node.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _attributes(node: ast.ClassDef) -> set[str]:
    """Names assigned to self.<name> anywhere in the class."""
    found = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Attribute) and isinstance(sub.ctx, ast.Store):
            found.add(sub.attr)
    return found


class HandlerResolutionTests(unittest.TestCase):
    """Every `clicked.connect(self._x)` must name a method that exists."""

    def test_no_button_is_connected_to_a_missing_method(self):
        classes = _classes()
        missing = []
        for name, node in classes.items():
            methods = _methods(node)
            for sub in ast.walk(node):
                if not isinstance(sub, ast.Call):
                    continue
                # self._something.connect(self._other)
                func = sub.func
                if not (isinstance(func, ast.Attribute) and func.attr == "connect"):
                    continue
                # Only private names are checked: a public one like `.hide` is
                # inherited from QWidget, and a widget assigned in __init__ is a
                # receiver, not a handler.
                assigned = _attributes(node)
                for arg in sub.args:
                    if (isinstance(arg, ast.Attribute)
                            and isinstance(arg.value, ast.Name)
                            and arg.value.id == "self"
                            and arg.attr.startswith("_")
                            and arg.attr not in methods
                            and arg.attr not in assigned):
                        missing.append(f"{name}.{arg.attr} (line {arg.lineno})")
        self.assertEqual(missing, [], f"handlers referenced but not defined: {missing}")

    def test_the_ai_model_button_lands_in_mainwindow(self):
        classes = _classes()
        main = classes["MainWindow"]
        self.assertIn("_open_ai_model", _methods(main))
        # the button text and its connect must be in the same class body
        source = UI.read_text(encoding="utf-8").splitlines()
        line = next(i for i, l in enumerate(source, 1)
                    if 'QPushButton("◈  AI MODEL")' in l)
        self.assertTrue(main.lineno <= line <= main.end_lineno,
                        f"AI MODEL button at line {line} is outside MainWindow")


class CallbackAttributeTests(unittest.TestCase):
    """A callback used as `if self.x:` must be assigned somewhere first."""

    def test_on_ai_provider_change_is_initialised(self):
        main = _classes()["MainWindow"]
        self.assertIn("on_ai_provider_change", _attributes(main))

    def test_the_overlay_signal_exists_and_is_connected(self):
        source = UI.read_text(encoding="utf-8")
        self.assertIn("_ai_model_sig   = pyqtSignal()", source)
        self.assertIn("self._ai_model_sig.connect(self._open_ai_model)", source)

    def test_the_overlay_reference_is_kept(self):
        # An overlay with no strong reference is garbage-collected mid-click.
        body = UI.read_text(encoding="utf-8")
        start = body.index("def _open_ai_model(self):")
        self.assertIn("self._ai_overlay = ov", body[start:start + 400])


class ThreadSafeMirrorTests(unittest.TestCase):
    """UltronUI mirrors the signals used by main.py; keep the set consistent."""

    def test_no_wrapper_emits_a_signal_that_does_not_exist(self):
        # Not every signal needs exposing (a few are internal), but every
        # `self._win._X_sig.emit()` in UltronUI must name a real signal —
        # otherwise main.py calls a thread-safe wrapper that raises on use.
        classes = _classes()
        main, fac = classes["MainWindow"], classes["UltronUI"]
        declared = {n.targets[0].id for n in main.body
                    if isinstance(n, ast.Assign)
                    and isinstance(n.targets[0], ast.Name)
                    and isinstance(n.value, ast.Call)
                    and getattr(n.value.func, "id", "") == "pyqtSignal"}
        emitted = {sub.func.value.attr
                   for sub in ast.walk(fac)
                   if isinstance(sub, ast.Call)
                   and isinstance(sub.func, ast.Attribute)
                   and sub.func.attr == "emit"
                   and isinstance(sub.func.value, ast.Attribute)}
        self.assertEqual(sorted(emitted - declared), [],
                         "UltronUI emits signals MainWindow never declares")

    def test_pick_reaches_the_panel(self):
        source = UI.read_text(encoding="utf-8")
        start = source.index("def open_ai_model_panel(self):")
        self.assertIn("_ai_model_sig.emit()", source[start:start + 200])


class OverlayContractTests(unittest.TestCase):
    def test_the_panel_carries_the_signal_main_expects(self):
        classes = _classes()
        applied = [n for n in classes["AiModelOverlay"].body
                   if isinstance(n, ast.Assign)
                   and getattr(n.targets[0], "id", "") == "applied"]
        self.assertTrue(applied, "AiModelOverlay must declare an `applied` signal")
        self.assertIn("str", ast.get_source_segment(UI.read_text(encoding="utf-8"),
                                                    applied[0].value))

    def test_the_panel_uses_the_shared_catalogue(self):
        source = UI.read_text(encoding="utf-8")
        start = source.index("class AiModelOverlay")
        body = source[start:source.index("class TelegramOverlay", start)]
        self.assertIn("from core import providers", body)
        self.assertIn("P.PROVIDERS", body)
        self.assertIn("P.apply_choice", body)
        # no second copy of the catalogue inside the panel
        self.assertNotIn('"gemini-2.5-flash":', body)


if __name__ == "__main__":
    unittest.main(verbosity=2)
