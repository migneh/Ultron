"""
process_manager.py — Process and task manager action for Ultron AI.
Inspect, list, search, and terminate processes on the PC.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

import json
import os
import platform
import subprocess
import time

import psutil

from ultron.core import operation_policy as policy

_OS = platform.system()
_WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if _OS == "Windows" else {}


def list_top_processes(limit: int = 10, sort_by: str = "memory") -> str:
    """Return a formatted table of top running processes by CPU or Memory."""
    procs = []
    for p in psutil.process_iter(["pid", "name", "cpu_percent", "memory_percent"]):
        try:
            info = p.info
            if info and info.get("name"):
                procs.append(info)
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue

    key = "cpu_percent" if sort_by.lower() == "cpu" else "memory_percent"
    top = sorted(procs, key=lambda x: x.get(key) or 0.0, reverse=True)[:limit]

    lines = [f"Top {len(top)} processes (sorted by {sort_by.upper()}):"]
    for p in top:
        pid = p.get("pid", 0)
        name = p.get("name", "unknown")
        cpu = p.get("cpu_percent") or 0.0
        mem = p.get("memory_percent") or 0.0
        lines.append(f"• {name} (PID: {pid}) — RAM: {mem:.1f}% | CPU: {cpu:.1f}%")
    return "\n".join(lines)


def find_processes(query: str) -> str:
    """Search for running processes matching a query name."""
    q = (query or "").lower().strip()
    if not q:
        return "No search query provided."

    matches = []
    for p in psutil.process_iter(["pid", "name", "memory_percent"]):
        try:
            name = (p.info.get("name") or "").lower()
            if q in name:
                matches.append(f"• {p.info.get('name')} (PID: {p.info.get('pid')}) — RAM: {p.info.get('memory_percent', 0):.1f}%")
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    if not matches:
        return f"No running processes matching '{query}' found."
    return f"Found {len(matches)} process(es) matching '{query}':\n" + "\n".join(matches[:15])


def _protected_pids() -> set[int]:
    """Never let this endpoint terminate the assistant, ancestors or init."""
    return {0, 1, os.getpid(), *(p.pid for p in psutil.Process(os.getpid()).parents())}


def _process_identity(pid: int) -> dict:
    process = psutil.Process(pid)
    created = process.create_time()
    name = process.name()
    if not isinstance(created, (int, float)) or not isinstance(name, str):
        raise ValueError("Process identity unavailable")
    return {"pid": pid, "created": created, "name": name}


def _terminate_plan(plan: policy.OperationPlan) -> str:
    """Effect sink: no grant, replay or freshly constructed plan may execute."""
    policy.consume(plan)
    targets = plan.payload()["targets"]
    protected = _protected_pids()
    # Abort the entire batch before effects if any identity no longer matches.
    try:
        for target in targets:
            if target["pid"] in protected or _process_identity(target["pid"]) != target:
                return "Process snapshot changed or is protected; nothing terminated. Request a fresh preview."
    except (psutil.Error, ValueError):
        return "Process snapshot unavailable; nothing terminated. Request a fresh preview."
    lines = []
    deadline = time.monotonic() + 3
    for target in targets:
        pid = target["pid"]
        try:
            process = psutil.Process(pid)
            if process.create_time() != target["created"] or process.name() != target["name"]:
                lines.append(f"PID {pid}: identity changed; skipped.")
                continue
            # psutil also checks PID reuse in terminate(). No escalation to kill().
            process.terminate()
        except psutil.NoSuchProcess:
            lines.append(f"PID {pid}: already absent; no termination sent.")
            continue
        except psutil.AccessDenied:
            lines.append(f"PID {pid}: access denied; no confirmed termination.")
            continue
        except Exception:
            lines.append(f"PID {pid}: submission failed or uncertain; inspect status, no automatic retry.")
            continue
        try:
            process.wait(timeout=max(0, deadline - time.monotonic()))
            lines.append(f"PID {pid}: exit observed after termination request.")
        except psutil.TimeoutExpired:
            lines.append(f"PID {pid}: termination requested; exit not observed. No force-kill attempted.")
        except Exception:
            lines.append(f"PID {pid}: termination requested; final state unknown. No retry attempted.")
    return "\n".join(lines)


def kill_process(target: str | int) -> str:
    """Preview exact names/PIDs, then request single-use host approval."""
    if type(target) not in (str, int):
        return "Invalid process target: use an exact name or positive PID."
    query = str(target).strip()
    if not query or len(query) > 200 or any(ord(c) < 32 for c in query):
        return "Invalid process target: use an exact name or positive PID (at most 200 characters)."
    try:
        protected = _protected_pids()
        if query.isascii() and query.isdigit():
            pids = [int(query)]
        else:
            names = {query.lower()}
            if _OS == "Windows" and not query.lower().endswith(".exe"):
                names.add(query.lower() + ".exe")
            pids = []
            for index, process in enumerate(psutil.process_iter(["pid", "name"])):
                if index >= 4096:
                    return "Process scan limit reached; use an exact PID. Nothing approved."
                try:
                    if (process.info.get("name") or "").lower() in names:
                        pids.append(process.pid)
                except psutil.Error:
                    continue
            pids = sorted(set(pids))
        if not pids:
            return "No exact process-name match; nothing terminated. Substring termination is disabled."
        if len(pids) > 20:
            return "Too many matching processes (maximum 20); use an exact PID. Nothing approved."
        if any(pid <= 1 or pid in protected for pid in pids):
            return "Refused: target includes init, this assistant or an ancestor. Nothing approved."
        targets = [_process_identity(pid) for pid in pids]
        plan = policy.prepare("process.terminate", tuple(f"pid:{p['pid']}" for p in targets), {"targets": targets})
    except (psutil.Error, ValueError, OverflowError):
        return "Process snapshot unavailable; nothing approved or terminated."
    return policy.request(
        plan, title=f"Request termination of {len(targets)} process(es)",
        detail="Unsaved work may be lost. Exact snapshot only; no force-kill or automatic retry.\n"
               + json.dumps(targets, ensure_ascii=True), execute=_terminate_plan,
    )


def focus_window_by_name(title_or_name: str) -> str:
    """Bring a window to the front by title or app name."""
    if not isinstance(title_or_name, str):
        return "Invalid window title."
    t = title_or_name.strip()
    if not t or len(t) > 200 or any(ord(c) < 32 for c in t):
        return "Invalid window title: use 1–200 characters without controls."
    if _OS == "Windows":
        cmd = """
        Add-Type @"
            using System;
            using System.Runtime.InteropServices;
            public class WinApi {
                [DllImport("user32.dll")]
                [return: MarshalAs(UnmanagedType.Bool)]
                public static extern bool SetForegroundWindow(IntPtr hWnd);
                [DllImport("user32.dll")]
                public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
            }
"@
        $needle = $env:ULTRON_FOCUS_QUERY
        $proc = Get-Process | Where-Object { $_.MainWindowTitle.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0 -or $_.ProcessName.IndexOf($needle, [StringComparison]::OrdinalIgnoreCase) -ge 0 } | Select-Object -First 1
        if ($proc -and $proc.MainWindowHandle -ne 0) {
            [void][WinApi]::ShowWindow($proc.MainWindowHandle, 9)
            if ([WinApi]::SetForegroundWindow($proc.MainWindowHandle)) {
                Write-Output "FOCUSED"
            } else {
                Write-Output "FOCUS_FAILED"
            }
        } else {
            Write-Output "NOT_FOUND"
        }
        """
        try:
            res = subprocess.run(
                ["powershell", "-NoProfile", "-Command", cmd],
                capture_output=True, text=True, timeout=5,
                env={**os.environ, "ULTRON_FOCUS_QUERY": t}, **_WIN_HIDE
            )
            if res.returncode == 0 and (res.stdout or "").strip() == "FOCUSED":
                return "Window focus request accepted by Windows; foreground state not independently verified."
            return f"Could not find an active window matching '{t}'."
        except Exception:
            return "Window focus request failed or is uncertain."
    return f"Window focusing is not supported on {_OS}."


def process_manager_handler(parameters: dict, **kwargs) -> str:
    action = str(parameters.get("action", "list")).lower().strip()
    target = parameters.get("target") or parameters.get("name") or parameters.get("process") or ""
    limit = int(parameters.get("limit", 10))
    sort_by = str(parameters.get("sort_by", "memory")).lower().strip()

    if action in ("list", "top", "show"):
        return list_top_processes(limit=limit, sort_by=sort_by)
    elif action in ("kill", "terminate", "stop", "close"):
        return kill_process(target)
    elif action in ("find", "search", "check"):
        return find_processes(target)
    elif action in ("focus", "foreground", "switch_to"):
        return focus_window_by_name(target)
    else:
        return f"Unknown action '{action}'. Supported actions: list, kill, find, focus."


TOOL = {
    "name": "process_manager",
    "description": (
        "Inspects, lists, and manages running processes on the PC. "
        "Use when user asks to: list running tasks/processes, find what apps are using the most RAM/CPU, "
        "kill/close an app or process by name (e.g. 'kill chrome', 'close notepad', 'kill PID 1234'), "
        "search for a running process, or switch/bring a window to the front. "
        "Termination requires host approval of at most 20 exact-name/PID snapshots; "
        "no substring matching or force-kill, and assistant/ancestor/init PIDs are refused."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "Action to perform: 'list' (top processes), 'kill' (terminate process), 'find' (search processes), 'focus' (bring to front)"
            },
            "target": {
                "type": "STRING",
                "description": "Exact process name (e.g. 'chrome', 'notepad.exe'), PID (e.g. '1234'), or window title to focus"
            },
            "limit": {
                "type": "INTEGER",
                "description": "Number of processes to list (default: 10)"
            },
            "sort_by": {
                "type": "STRING",
                "description": "'memory' (default) or 'cpu'"
            }
        },
        "required": ["action"]
    },
    "handler": process_manager_handler
}
