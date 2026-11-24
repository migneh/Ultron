"""
system_command.py — Run shell, PowerShell, and terminal commands on the computer.
Auto-discovered by core/action_loader.py.

Security model (Phase 0 hardening)
----------------------------------
* Safe read-only inspection commands run immediately.
* Anything that can modify files, install software, alter network or services,
  or stop processes is parked behind the on-screen confirmation gate
  (core/confirm.py) and does not run until the user presses CONFIRM. The model
  cannot forge that consent.
* A short list of outright destructive commands is refused, never offered for
  confirmation.
* Every attempt — direct, confirmed, or refused — is appended to an audit log
  so there is a durable trail of what the assistant was asked to run.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Optional

from core import confirm as confirm_gate

_OS = platform.system()
_WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if _OS == "Windows" else {}

# Directory for the command audit trail. *.log is gitignored, so this never
# lands in version control. Created lazily on first write.
_AUDIT_DIR = Path(__file__).resolve().parent.parent / "logs"
_AUDIT_FILE = _AUDIT_DIR / "command_audit.log"
_AUDIT_LOCK = threading.Lock()


# ── Classification ───────────────────────────────────────────────────────
# Commands that only inspect system state and never modify files, network, or
# services. Match is on the executable token (first whitespace-delimited word),
# compared case-insensitively after stripping a leading ./ or .\ .
_SAFE_READ_ONLY = {
    # Windows
    "ipconfig", "hostname", "whoami", "date", "time", "tasklist", "systeminfo",
    "dir", "cd", "ver", "driverquery", "netstat", "ping", "tracert", "nslookup",
    "getmac", "qwinsta",
    # macOS / Linux
    "ls", "pwd", "whoami", "hostname", "date", "uptime", "ps", "df", "du", "free",
    "uname", "ifconfig", "ip", "ping", "traceroute", "nslookup", "dig",
    "netstat", "ss", "lscpu", "lsmem", "lsblk",
    # Cross-platform (git subcommands filtered separately)
    "git",
}
_GIT_READ_ONLY = {"status", "log", "diff", "branch", "show", "rev-parse", "remote"}

# Outright destructive — refused even with confirmation.
_DESTRUCTIVE = (
    "format ", "mkfs", "fdisk ", "shutdown /s", "shutdown -s",
    "reboot", "poweroff", "halt", "bcdedit ", "cipher /w",
    "rm -rf ", "rm -r -f ", "del /f /s /q ", "deltree ",
    "reg delete ", "net user ", "net localgroup ",
    "taskkill /f ", "pkill -9 ", "kill -9 ",
)

# State-changing but not on the destroy list — these require confirmation.
_STATE_CHANGING_HINTS = (
    "pip install", "pip uninstall", "npm install", "npm uninstall",
    "winget ", "choco ", "brew install", "apt-get install", "apt install ",
    "yum install ", "dnf install ", "pacman -s ", "apk add ",
    "reg add ", "netsh ", "sc start ", "sc stop ", "systemctl start ",
    "systemctl stop ", "systemctl enable ", "systemctl disable ",
    "service ", "mount ", "umount ", "> ", ">> ", "| sh", "| bash",
    "| sh ", "| bash ", "curl |", "wget |",
)


def _first_token(cmd: str) -> str:
    """Return the executable token of a command line, lowercased."""
    c = cmd.strip()
    if c.startswith((".\\", "./")):
        c = c[2:]
    parts = c.split()
    return parts[0].strip("\"'").lower() if parts else ""


def _classify(cmd: str) -> str:
    """'direct' | 'confirm' | 'refuse'."""
    low = cmd.lower()
    for pat in _DESTRUCTIVE:
        if pat in low:
            return "refuse"
    token = _first_token(cmd)
    if token in _SAFE_READ_ONLY:
        if token == "git":
            parts = low.split()
            if len(parts) > 1 and parts[1] not in _GIT_READ_ONLY:
                return "confirm"
            return "direct"
        return "direct"
    for hint in _STATE_CHANGING_HINTS:
        if hint in low:
            return "confirm"
    # Unknown command — cannot assume it is safe. Require confirmation.
    return "confirm"


def _audit_log(cmd: str, shell_type: str, disposition: str, result: str) -> None:
    """Append one JSON line to the command audit trail. Never raises."""
    try:
        _AUDIT_DIR.mkdir(parents=True, exist_ok=True)
        record = {
            "when": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "os": _OS,
            "shell": shell_type,
            "disposition": disposition,   # direct | confirmed | refused
            "command": cmd[:500],
            "result": (result or "")[:800],
        }
        with _AUDIT_LOCK:
            with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass  # auditing must never break command execution


def _run_command(cmd: str, shell_type: str, timeout: int) -> str:
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
            return f"Command executed successfully (exit code 0, no output)."
        if len(output) > 1500:
            output = output[:1500] + "\n... [output truncated for brevity]"
        return output
    err = stderr or stdout or f"Exit code {res.returncode}"
    if len(err) > 1200:
        err = err[:1200] + "... [truncated]"
    return f"Command failed (exit code {res.returncode}):\n{err}"


def system_command_handler(parameters: dict, speak=None, **kwargs) -> str:
    cmd = (parameters.get("command") or "").strip()
    if not cmd:
        return "No command provided to execute."

    shell_type = parameters.get("shell", "powershell")
    try:
        timeout = int(parameters.get("timeout", 20) or 20)
    except Exception:
        timeout = 20

    disposition = _classify(cmd)

    if disposition == "refuse":
        _audit_log(cmd, shell_type, "refused", "blocked by destructive-pattern rule")
        return (
            f"Command blocked: '{cmd}' matches a destructive pattern and will not run. "
            "Ask for a narrower, read-only inspection instead."
        )

    if disposition == "direct":
        result = _run_command(cmd, shell_type, timeout)
        _audit_log(cmd, shell_type, "direct", result)
        return result

    # disposition == "confirm": park behind the on-screen gate.
    def _run_confirmed() -> None:
        result = _run_command(cmd, shell_type, timeout)
        _audit_log(cmd, shell_type, "confirmed", result)
        if speak:
            try:
                short = (result or "").replace("\n", " ")[:160]
                speak(f"Command finished: {short}" if short else "Command finished with no output.")
            except Exception:
                pass

    confirm_key = f"system_command:{hashlib.sha256(cmd.encode()).hexdigest()[:16]}"
    return confirm_gate.request(
        key=confirm_key,
        title="Run system command",
        detail=cmd[:400],
        run=_run_confirmed,
    )


TOOL = {
    "name": "system_command",
    "description": (
        "Executes a system shell / PowerShell / Command Prompt command on the PC. "
        "Read-only inspection commands (ipconfig, ping, dir, ls, ps, git status, …) run immediately. "
        "Any command that can change files, install software, alter network or services, or stop "
        "processes is parked behind an on-screen confirmation banner and only runs after the user "
        "presses CONFIRM — never claim it is done before that. "
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
