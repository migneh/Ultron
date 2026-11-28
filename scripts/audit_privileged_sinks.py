"""Reproducible static call-site leads, NOT proof of permission coverage.

Run from repo root: python scripts/audit_privileged_sinks.py > reports/PRIVILEGED_SINK_INVENTORY.csv
Does not import application modules or execute effects. Aliases, dynamic dispatch,
FFI and transitive calls require manual review. Gates must be traced separately.
"""
from __future__ import annotations

import ast
import csv
import sys
from pathlib import Path

PROCESS = {"run", "Popen", "call", "check_call", "check_output", "system", "exec_module", "exec", "eval", "terminate", "kill", "startfile"}
FILES = {"write_text", "write_bytes", "unlink", "rmdir", "rmtree", "remove", "rename", "replace", "copy", "copy2", "copytree", "move", "mkdir", "makedirs", "send2trash"}
CAPTURE = {"screenshot", "grab", "VideoCapture", "InputStream", "rec", "listen", "record"}
INPUT = {"click", "doubleClick", "press", "hotkey", "typewrite", "write", "moveTo", "mouseDown", "keyDown"}
NETWORK = {"post", "put", "patch", "delete", "send_message", "send_document", "sendmail"}


def name(node):
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return name(node.value) + "." + node.attr
    return "<dynamic>"


def inventory():
    paths = {Path("main.py"), Path("ultron/app.py"), Path("ultron/ui.py")}
    for root in ("ultron/actions", "ultron/core", "ultron/memory", "ultron/dashboard", "ultron/plugins"):
        paths.update(Path(root).rglob("*.py"))
    for path in sorted(paths):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[child] = node
        for call in ast.walk(tree):
            if not isinstance(call, ast.Call):
                continue
            callee = name(call.func)
            leaf = callee.rsplit(".", 1)[-1]
            category = next((kind for kind, terms in (
                ("process_or_execution", PROCESS), ("filesystem", FILES),
                ("capture", CAPTURE), ("input_or_write", INPUT), ("network_mutation", NETWORK)
            ) if leaf in terms), None)
            if category is None and leaf == "open":
                # Include all opens: static flags/modes need manual classification.
                category = "file_open_review_mode"
            if category is None:
                continue
            parent = parents.get(call)
            while parent is not None and not isinstance(parent, (ast.FunctionDef, ast.AsyncFunctionDef)):
                parent = parents.get(parent)
            yield (str(path), call.lineno, parent.name if parent else "<module>", category, callee, "unclassified_manual_trace_required")


if __name__ == "__main__":
    writer = csv.writer(sys.stdout, lineterminator="\n")
    writer.writerow(("file", "line", "function", "category", "callee", "approval_coverage"))
    writer.writerows(sorted(inventory()))
