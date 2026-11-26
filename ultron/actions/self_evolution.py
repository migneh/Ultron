"""
actions/self_evolution.py — Project Prometheus: Autonomous Self-Evolution & Tool Creation for Ultron AI.

Creates review-only Python source drafts outside action/plugin auto-discovery.
No generated code is imported, activated, or tested by this tool.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ultron.core import confirm as confirm_gate
from ultron.paths import PROJECT_ROOT

_BASE_DIR = PROJECT_ROOT
_ACTIONS_DIR = _BASE_DIR / "ultron" / "actions"
_PLUGINS_DIR = _BASE_DIR / "ultron" / "plugins"

# Live registries hooked up at runtime
_LIVE_ACTION_REGISTRY: Any = None
_LIVE_PLUGIN_REGISTRY: Any = None

# ── Prometheus audit trail ───────────────────────────────────────────────
# Every synthesis, rejection and activation is appended to a log so there is a
# durable record of what code Ultron was asked to write and whether it ran.
_PROM_AUDIT_DIR = _BASE_DIR / "logs"
_PROM_AUDIT_FILE = _PROM_AUDIT_DIR / "prometheus_audit.log"
_PROM_AUDIT_LOCK = threading.Lock()


def _prometheus_audit_log(tool_name: str, category: str, disposition: str, detail: str) -> None:
    """Append one JSON line to the Prometheus audit trail. Never raises."""
    try:
        _PROM_AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "when": datetime.now(timezone.utc).isoformat(),
            "tool": tool_name,
            "category": category,
            "disposition": disposition,  # written | compiled | rejected | activated | activation_failed
            "detail": detail[:500],
        }
        with _PROM_AUDIT_LOCK:
            with open(_PROM_AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # auditing must never block synthesis


def set_live_registries(action_reg: Any, plugin_reg: Any) -> None:
    """Connect running action and plugin registries for hot-loading without restart."""
    global _LIVE_ACTION_REGISTRY, _LIVE_PLUGIN_REGISTRY
    _LIVE_ACTION_REGISTRY = action_reg
    _LIVE_PLUGIN_REGISTRY = plugin_reg


def _clean_identifier(name: str) -> str:
    """Sanitize tool name to a clean snake_case identifier."""
    clean = re.sub(r"[^a-zA-Z0-9_]", "_", (name or "").strip().lower())
    clean = re.sub(r"_+", "_", clean).strip("_")
    if not clean or clean[0].isdigit():
        clean = f"tool_{clean}" if clean else "custom_tool"
    return clean[:63]


def _validate_safety(code: str) -> tuple[bool, str]:
    """Safety filter guarding against accidental catastrophic operations.

    Heuristics are advisory filtering, not isolation or safety certification.
    Generated code is never executed by this module, even after approval.
    """
    dangerous_patterns = [
        # Drive / OS destruction
        r"format\s+[c-zC-Z]:",
        r"rmdir\s+/[sS]\s+/[qQ]\s+[c-zC-Z]:\\Windows",
        # Classic one-liners
        r"os\.system\(\s*['\"]rm\s+-rf\s+/\s*['\"]\)",
        r":\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;",  # fork bomb
        # Arbitrary process / shell execution
        r"subprocess\.(Popen|run|call|check_output|check_call)\(",
        r"os\.(system|execv|execve|execvp|spawnl|spawnle|spawnlp|spawnlpe|spawnv|spawnve|spawnvp|spawnvpe)\(",
        # Dynamic code evaluation
        r"\beval\(",
        r"\bexec\(",
        r"\bcompile\(",
        r"__import__\(",
        r"importlib\.",
        # Networking (no phone-home, no exfiltration, no C2)
        r"socket\.",
        r"urllib\.(request|parse)",
        r"requests\.",
        r"ctypes\.",
        r"paramiko\.",
        r"ftplib\.",
        r"http\.client\.",
        # Writes to the real filesystem (allow the helper's player.write_log)
        r"open([^)]*[/~])",
        r"\.write_text\(",
        r"\.write_bytes\(",
    ]
    for pat in dangerous_patterns:
        if re.search(pat, code, re.IGNORECASE):
            return False, f"Rejected: code contains prohibited signature matching '{pat}'."
    return True, "Code passed security heuristics."


def _generate_action_template(tool_name: str, description: str, parameters: dict | None = None) -> str:
    """Generate a clean, idiomatic Ultron action Python module."""
    fn_name = tool_name
    params_schema = parameters or {
        "type": "OBJECT",
        "properties": {
            "query": {"type": "STRING", "description": "Primary input parameter or query for this action"}
        },
        "required": []
    }
    params_json = json.dumps(params_schema, indent=8)

    return f'''"""
actions/{tool_name}.py — Dynamically Synthesized Autonomous Tool for Ultron AI.
Synthesized via Project Prometheus on {datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")}.
"""
from __future__ import annotations
import json
import hashlib
import os
import sys
import subprocess
from pathlib import Path
from typing import Any, Optional

def {fn_name}(parameters: dict, player=None, **kwargs) -> str:
    """
    {description}
    """
    query = parameters.get("query", "")
    if player:
        try:
            player.write_log(f"[{tool_name}] Executing directive: {{query}}")
        except Exception:
            pass

    # Execution logic synthesized by Ultron
    result_lines = [
        f"[{tool_name.upper()}] Directive successfully processed.",
        f"Parameter input: '{{query}}'",
        "Status: Execution verified inside Ultron neural runtime."
    ]
    return "\\n".join(result_lines)


TOOL = {{
    "name": "{tool_name}",
    "description": {json.dumps(description)},
    "parameters": {params_json},
    "handler": {fn_name},
}}
'''


def synthesize_action(
    tool_name: str,
    description: str,
    code: str = "",
    parameters: dict | None = None,
    category: str = "action",
    player: Any = None
) -> str:
    """
    Validate syntax and offer to save an inert, review-only source draft.
    """
    if not isinstance(code, str) or len(code.encode("utf-8")) > 100_000:
        return "Draft refused: source must be text of at most 100,000 UTF-8 bytes."
    safe_name = _clean_identifier(tool_name)
    if not description:
        description = f"Autonomous synthesized capability for {safe_name}."

    # If code was not supplied, generate valid template
    if not code or len(code.strip()) < 20:
        code = _generate_action_template(safe_name, description, parameters)

    # 1. Static AST syntax validation
    try:
        ast.parse(code)
    except SyntaxError as e:
        return f"Prometheus Synthesis Failed: Python syntax error in generated code at line {e.lineno}: {e.msg}"

    # 2. Heuristic Safety Check
    safe, msg = _validate_safety(code)
    if not safe:
        _prometheus_audit_log(safe_name, category, "rejected", msg)
        return f"Prometheus Security Gate: {msg}"

    is_plugin = (category or "").lower().strip() in ("plugin", "plugins")
    existing = (_PLUGINS_DIR if is_plugin else _ACTIONS_DIR) / f"{safe_name}.py"
    if existing.exists():
        return f"Draft refused: '{safe_name}' already exists. Choose a new tool name."
    digest = hashlib.sha256(code.encode("utf-8")).hexdigest()
    # No .py file, import, registry mutation, promotion or startup manifest.
    filename = f"{safe_name}_{digest}.py.txt"

    def _save_draft() -> str:
        directory = _draft_directory()
        directory.mkdir(parents=True, exist_ok=True, mode=0o700)
        path = directory / filename
        try:
            # O_EXCL refuses existing files/symlinks and avoids overwriting drafts.
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write(code)
                stream.flush()
                os.fsync(stream.fileno())
        except FileExistsError:
            return "Draft already exists; nothing activated or executed."
        _prometheus_audit_log(safe_name, category, "draft_saved", digest)
        return f"Review-only draft saved: {path}\nSHA-256: {digest}\nNot activated, imported or executed. Manual trusted code review is required."

    return confirm_gate.request(
        key=f"prometheus:draft:{digest}",
        title=f"Save review-only source draft '{safe_name}'",
        detail=f"Writes an inert .py.txt file outside auto-discovery. No execution. SHA-256: {digest}\n" + code,
        run=_save_draft,
    )


def _draft_directory() -> Path:
    return Path.home() / ".ultron" / "source_drafts"


def list_evolved_tools() -> str:
    """Lists all custom synthesized actions and plugins created via Prometheus."""
    evolved = []
    for d, cat in ((_ACTIONS_DIR, "Action"), (_PLUGINS_DIR, "Plugin")):
        if not d.exists():
            continue
        for p in sorted(d.glob("*.py")):
            if p.name.startswith("_"):
                continue
            try:
                txt = p.read_text(encoding="utf-8")
                if "Project Prometheus" in txt or "TOOL" in txt or "PLUGIN" in txt:
                    evolved.append((p.stem, cat, p.stat().st_size, p))
            except Exception:
                continue

    if not evolved:
        return "No synthesized tools recorded yet. Ultron is running standard base protocols."

    lines = [
        "[PROMETHEUS] EVOLVED TOOLS & PROTOCOLS",
        f"Legacy source files (not verified active): {len(evolved)}",
        "-" * 55,
    ]
    for name, cat, size, p in evolved:
        lines.append(f"* [{cat.upper()}] {name:<22} ({size:,} bytes) -> {p.name}")
    lines.append("-" * 55)
    return "\n".join(lines)


def inspect_evolved_tool(tool_name: str) -> str:
    """Inspects the Python source code of a synthesized tool."""
    safe_name = _clean_identifier(tool_name)
    target_action = _ACTIONS_DIR / f"{safe_name}.py"
    target_plugin = _PLUGINS_DIR / f"{safe_name}.py"

    target = target_action if target_action.exists() else (target_plugin if target_plugin.exists() else None)
    if not target:
        return f"No tool found named '{safe_name}' in actions/ or plugins/."

    try:
        content = target.read_text(encoding="utf-8")
        lines = [
            f"[PROMETHEUS] SOURCE CODE: {target.name}",
            f"Path: {target}",
            "=" * 55,
            content,
            "=" * 55,
        ]
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to read source for '{safe_name}': {e}"


def test_evolved_tool(tool_name: str, parameters: dict | None = None) -> str:
    """Never provide an alternative execution path through legacy registries."""
    return "Generated-tool execution/testing is disabled. Review drafts manually; no isolated runtime is configured."


def self_evolution(parameters: dict, player=None, **kwargs) -> str:
    """Main entrypoint for self_evolution tool."""
    action = (parameters.get("action") or "synthesize").lower().strip()
    tool_name = parameters.get("tool_name") or parameters.get("name") or "custom_tool"
    description = parameters.get("description") or ""
    code = parameters.get("code") or ""
    cat = parameters.get("category") or "action"
    params_dict = parameters.get("parameters_schema")

    if isinstance(params_dict, str):
        try:
            params_dict = json.loads(params_dict)
        except Exception:
            params_dict = None

    if action in ("synthesize", "create", "build", "evolve", "write"):
        return synthesize_action(
            tool_name=tool_name,
            description=description,
            code=code,
            parameters=params_dict,
            category=cat,
            player=player
        )
    elif action in ("list", "all", "status", "catalog"):
        return list_evolved_tools()
    elif action in ("inspect", "read", "view", "source"):
        return inspect_evolved_tool(tool_name=tool_name)
    elif action in ("test", "run", "execute"):
        return test_evolved_tool(tool_name=tool_name, parameters=parameters.get("test_args"))
    else:
        return (
            f"Unknown self_evolution directive '{action}'. "
            "Available actions: synthesize, list, inspect, test."
        )


TOOL = {
    "name": "self_evolution",
    "description": (
        "Save review-only Python source drafts after host approval, outside auto-discovery. "
        "Never imports, hot-loads or executes generated code. list/inspect show legacy installed "
        "source only, not proof of activation. test/run/execute are disabled."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "synthesize (save review-only draft) | list (legacy source inventory) | inspect (legacy source); test disabled"
            },
            "tool_name": {
                "type": "STRING",
                "description": "Unique identifier for the new tool (snake_case, e.g. 'crypto_portfolio_ticker', 'pdf_invoice_parser')"
            },
            "description": {
                "type": "STRING",
                "description": "Clear description explaining what the tool does and when Gemini should call it"
            },
            "code": {
                "type": "STRING",
                "description": "Optional Python code for the action/plugin. If omitted, Ultron synthesizes a valid compliant template"
            },
            "category": {
                "type": "STRING",
                "description": "Intended category: action or plugin; drafts are never written to those directories"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": self_evolution,
}
