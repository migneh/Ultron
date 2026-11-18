"""
tests/test_imports.py — static guard against the "silently dead import" bug class.

Two real bugs shipped in this repo because of this pattern:

    try:
        from actions.sentry_protocol import arm_sentry      # no such function
        arm_sentry()
    except Exception:
        report("Sentry: Standby")                            # looks intentional

    try:
        from actions.network_auditor import run_security_audit   # no such function
    except Exception:
        report("Cyber Audit: Network telemetry online")          # claims success

Nothing raises, so nothing is noticed, and a headline feature does nothing forever.
A plain `ImportError` would have been a five-second fix on the first run. This test
makes that class of drift fail loudly instead: every `from <local module> import X`
is checked against what the module actually defines.

Run: python -m unittest discover -s tests -t .
"""
from __future__ import annotations

import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCAL_ROOTS = {"core", "actions", "memory", "dashboard", "plugins", "config", "tests"}

# Imports that are intentionally allowed to fail at runtime: the module is an
# optional drop-in plugin the user may or may not have installed.
OPTIONAL_IMPORTS = {
    ("actions.send_message", "plugins", "_whatsapp_core"),
}


def _scan() -> tuple[dict[str, set[str]], set[str]]:
    """Map every local module to the names it defines, and list module paths."""
    names_by_module: dict[str, set[str]] = {}
    module_paths: set[str] = set()

    for path in ROOT.rglob("*.py"):
        if any(part in {".venv", ".git", "build", "dist", "__pycache__"} for part in path.parts):
            continue
        rel = path.relative_to(ROOT).with_suffix("")
        module = ".".join(rel.parts) if rel.name != "__init__" else ".".join(rel.parts[:-1])
        module_paths.add(module)

        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue

        defined: set[str] = set()
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                defined.add(node.name)
            elif isinstance(node, ast.Assign):
                defined.update(t.id for t in node.targets if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                defined.add(node.target.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                # a name bound by an import is importable from this module too
                defined.update((a.asname or a.name).split(".")[0] for a in node.names)
        names_by_module[module] = defined

    return names_by_module, module_paths


class BrokenSymbolImportTests(unittest.TestCase):
    def test_no_intra_repo_import_of_missing_symbols(self):
        names_by_module, module_paths = _scan()
        broken = []

        for path in ROOT.rglob("*.py"):
            if any(part in {".venv", ".git", "build", "dist", "__pycache__"} for part in path.parts):
                continue
            rel = path.relative_to(ROOT).with_suffix("")
            source_module = ".".join(rel.parts) if rel.name != "__init__" else ".".join(rel.parts[:-1])
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue

            for node in ast.walk(tree):
                if not isinstance(node, ast.ImportFrom):
                    continue
                if not node.module or node.level:        # relative imports: skip
                    continue
                if node.module.split(".")[0] not in LOCAL_ROOTS:
                    continue                              # stdlib / third-party
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    if f"{node.module}.{alias.name}" in module_paths:
                        continue                          # importing a submodule
                    if alias.name in names_by_module.get(node.module, set()):
                        continue
                    if (source_module, node.module, alias.name) in OPTIONAL_IMPORTS:
                        continue
                    broken.append(f"{path.relative_to(ROOT)}:{node.lineno} "
                                  f"from {node.module} import {alias.name}")

        self.assertEqual(
            broken, [],
            "imports of names that do not exist — these raise ImportError at call "
            "time and are usually swallowed by a broad except:\n  " + "\n  ".join(broken),
        )

    def test_scanner_actually_sees_modules(self):
        """Guard against the scanner silently finding nothing (e.g. bad ROOT)."""
        names_by_module, module_paths = _scan()
        self.assertIn("core.action_loader", module_paths)
        self.assertGreater(len(module_paths), 50)
        self.assertIn("discover_actions", names_by_module["core.action_loader"])


if __name__ == "__main__":
    unittest.main(verbosity=2)


class AnnotationEvaluationTests(unittest.TestCase):
    """Guard: annotations that raise at import time.

    `dashboard/server.py` shipped with

        _GLOBAL_DASHBOARD: "DashboardServer" | None = None

    Because that module has no `from __future__ import annotations`, the union was
    evaluated when the module was imported and `str | None` raised TypeError. The
    dashboard never imported, and an `except Exception` upstream turned it into one
    muted log line — the whole phone-remote feature was dead and looked optional.

    A string is only lazy when the WHOLE annotation is a string: quote `"X | None"`,
    not `"X" | None`.
    """

    def test_no_runtime_evaluated_string_unions(self):
        offenders = []
        for path in ROOT.rglob("*.py"):
            if any(part in {".venv", ".git", "build", "dist", "__pycache__"} for part in path.parts):
                continue
            try:
                tree = ast.parse(path.read_text(encoding="utf-8"))
            except (SyntaxError, UnicodeDecodeError):
                continue

            lazy = any(
                isinstance(node, ast.ImportFrom) and node.module == "__future__"
                and any(a.name == "annotations" for a in node.names)
                for node in tree.body
            )
            if lazy:
                continue

            annotations = []
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if node.returns:
                        annotations.append((node.returns, node.lineno))
                    args = list(node.args.args) + list(node.args.kwonlyargs)
                    args += [a for a in (node.args.vararg, node.args.kwarg) if a]
                    annotations += [(a.annotation, node.lineno) for a in args if a.annotation]
                elif isinstance(node, ast.AnnAssign) and node.annotation:
                    annotations.append((node.annotation, node.lineno))

            for annotation, lineno in annotations:
                for sub in ast.walk(annotation):
                    if (isinstance(sub, ast.BinOp) and isinstance(sub.op, ast.BitOr)
                            and any(isinstance(side, ast.Constant) and isinstance(side.value, str)
                                    for side in (sub.left, sub.right))):
                        offenders.append(f"{path.relative_to(ROOT)}:{lineno} "
                                         f"{ast.unparse(annotation)}")
                        break

        self.assertEqual(offenders, [],
                         "these annotations are evaluated at import and will raise "
                         "TypeError ('str' | None):\n  " + "\n  ".join(offenders))
