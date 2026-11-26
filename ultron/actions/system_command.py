"""
system_command.py — Run shell, PowerShell, and terminal commands on the computer.
Auto-discovered by core/action_loader.py.

Security model
--------------
All non-refused commands require exact-plan host approval, including inspection
commands and Git. Name/argument heuristics cannot authorize shell execution.
Approved commands run with account privileges, not in a sandbox. The destructive
pattern list is advisory defense-in-depth, not comprehensive command analysis.
Audit records contain metadata/hashes only, never commands or captured output.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
import threading
from pathlib import Path

from ultron.core import confirm as confirm_gate
from ultron.paths import PROJECT_ROOT

_OS = platform.system()
_WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if _OS == "Windows" else {}

# Directory for the command audit trail. *.log is gitignored, so this never
# lands in version control. Created lazily on first write.
_AUDIT_DIR = PROJECT_ROOT / "logs"
_AUDIT_FILE = _AUDIT_DIR / "command_audit.log"
_AUDIT_LOCK = threading.Lock()


# ── Classification ───────────────────────────────────────────────────────
# Outright destructive — refused even with confirmation.
_DESTRUCTIVE = (
    "format ", "mkfs", "fdisk ", "shutdown /s", "shutdown -s",
    "reboot", "poweroff", "halt", "bcdedit ", "cipher /w",
    "rm -rf ", "rm -r -f ", "del /f /s /q ", "deltree ",
    "reg delete ", "net user ", "net localgroup ",
    "taskkill /f ", "pkill -9 ", "kill -9 ",
)

def _classify(cmd: str) -> str:
    """'confirm' | 'refuse'; no string classifier may authorize execution."""
    return "refuse" if any(pattern in cmd.lower() for pattern in _DESTRUCTIVE) else "confirm"


def _audit_log(cmd: str, shell_type: str, disposition: str, result: str) -> None:
    """Append one JSON line to the command audit trail. Never raises."""
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "when": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "os": _OS,
            "shell": shell_type,
            "disposition": disposition,   # direct | confirmed | refused
            "command_sha256": hashlib.sha256(cmd.encode("utf-8")).hexdigest(),
            "command_chars": len(cmd),
            "outcome": result if result in {"submitted", "returned", "blocked", "cancelled", "expired", "unavailable", "busy"} else "unknown",
        }
        with _AUDIT_LOCK:
            with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # auditing must never break command execution


def _run_command(cmd: str, shell_type: str, timeout: int, *, cwd: str | None = None) -> str:
    """Run a command and return captured output. Mirrors the old behaviour."""
    timeout = max(2, min(int(timeout or 20), 60))
    shell_choice = (shell_type or "powershell").lower().strip()

    if _OS == "Windows":
        if shell_choice == "cmd":
            args = ["cmd.exe", "/c", cmd]
        else:
            args = [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-Command", cmd,
            ]
    else:
        args = ["/bin/bash", "-c", cmd]

    try:
        res = subprocess.run(
            args,
            capture_output=True,
            cwd=cwd,
            text=True,
            timeout=timeout,
            encoding="utf-8",
            errors="replace",
            **_WIN_HIDE,
        )
    except subprocess.TimeoutExpired:
        return f"Command timed out after {timeout} seconds: '{cmd}'"
    except Exception as e:
        return f"Execution error: {e}"

    stdout = (res.stdout or "").strip()
    stderr = (res.stderr or "").strip()
    if res.returncode == 0:
        output = stdout or stderr
        if not output:
            return "Command executed successfully (exit code 0, no output)."
        if len(output) > 1500:
            output = output[:1500] + "\n... [output truncated for brevity]"
        return output
    err = stderr or stdout or f"Exit code {res.returncode}"
    if len(err) > 1200:
        err = err[:1200] + "... [truncated]"
    return f"Command failed (exit code {res.returncode}):\n{err}"


def system_command_handler(parameters: dict, speak=None, **kwargs) -> str:
    raw = parameters.get("command", "")
    if not isinstance(raw, str) or len(raw) > 8000 or "\x00" in raw:
        return "Command refused: use text of at most 8,000 characters without NUL."
    cmd = raw.strip()
    if not cmd:
        return "No command provided to execute."

    shell_type = parameters.get("shell", "powershell")
    if not isinstance(shell_type, str) or shell_type not in {"powershell", "cmd", "bash"}:
        return "Command refused: unsupported shell choice."
    if _OS == "Windows" and shell_type == "bash":
        return "Command refused: use powershell or cmd on Windows."
    # Snapshot immutable execution details before requesting approval.
    cwd = os.getcwd()
    try:
        timeout = int(parameters.get("timeout", 20) or 20)
    except Exception:
        timeout = 20

    timeout = max(2, min(timeout, 60))
    disposition = _classify(cmd)

    if disposition == "refuse":
        _audit_log(cmd, shell_type, "refused", "blocked")
        return (
            f"Command blocked: '{cmd}' matches a destructive pattern and will not run. "
            "Ask for a narrower, read-only inspection instead."
        )

    # disposition == "confirm": park behind the on-screen gate.
    def _run_confirmed() -> str:
        result = _run_command(cmd, shell_type, timeout, cwd=cwd)
        _audit_log(cmd, shell_type, "confirmed", "returned")
        if speak:
            try:
                short = (result or "").replace("\n", " ")[:160]
                speak(f"Command finished: {short}" if short else "Command finished with no output.")
            except Exception:
                pass

        return result

    plan = json.dumps([cmd, shell_type, timeout, cwd], ensure_ascii=False)
    confirm_key = f"system_command:{hashlib.sha256(plan.encode()).hexdigest()}"
    _audit_log(cmd, shell_type, "approval_requested", "submitted")
    return confirm_gate.request(
        key=confirm_key,
        title="Run system command",
        detail=f"Full account privileges; NOT sandboxed. Configured helpers may execute.\nShell: {shell_type if _OS == 'Windows' else '/bin/bash'}\nWorking directory: {cwd}\nTimeout: {timeout}s\nCommand:\n{cmd}",
        run=_run_confirmed,
        on_cancel=lambda reason: _audit_log(cmd, shell_type, "not_executed", reason),
    )


TOOL = {
    "name": "system_command",
    "description": (
        "Executes a system shell / PowerShell / Command Prompt command on the PC. "
        "ALL commands, including inspection and Git, require on-screen host approval. "
        "Approved commands run with account privileges, not in a sandbox. "
        "Never claim execution before confirmation. "
        "Destructive commands (format, rm -rf, shutdown, reg delete, …) are refused outright. "
        "Use shell 'powershell' (default), 'cmd' on Windows, or omit on macOS/Linux. "
        "Timeout in seconds, default 20, max 60."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "command": {
                "type": "STRING",
                "description": "The exact command line string to run.",
            },
            "shell": {
                "type": "STRING",
                "description": "Shell to use: 'powershell' (default) or 'cmd' (Windows). Ignored on macOS/Linux.",
            },
            "timeout": {
                "type": "INTEGER",
                "description": "Timeout in seconds (default: 20, max: 60).",
            },
        },
        "required": ["command"],
    },
    "handler": system_command_handler,
}
