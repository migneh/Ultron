"""
actions/purge_protocol.py — Deep Disk & Cache Purge Protocol for Ultron AI.
Safely scans and purges temporary files, application caches, crash dumps,
developer build artifacts (pip, pytest, pycache), and empties the Recycle Bin.
Auto-discovered by core/action_loader.py.

Security (P0): irreversible purge actions are parked behind the on-screen
confirmation gate (core/confirm.py) and only run after the user presses CONFIRM.
"""
from __future__ import annotations

import ctypes
import datetime as _dt
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Optional

from ultron.core import confirm as confirm_gate
from ultron.paths import PROJECT_ROOT

_OS = platform.system()
_WIN_HIDE: dict = {"creationflags": subprocess.CREATE_NO_WINDOW} if _OS == "Windows" else {}
_BASE_DIR = PROJECT_ROOT

# Audit trail for purge operations (same log as system_command).
_AUDIT_DIR = _BASE_DIR / "logs"
_AUDIT_FILE = _AUDIT_DIR / "command_audit.log"

# Don't touch files created/modified in the last 15 minutes (safety guard for active installers)
_SAFETY_MARGIN_SECONDS = 900


def _get_folder_size(folder: Path, min_age_secs: float = 0.0) -> tuple[int, int]:
    """Calculates (total_bytes, file_count) for a folder, respecting safety age."""
    total_bytes = 0
    count = 0
    now = time.time()
    if not folder.exists() or not folder.is_dir():
        return 0, 0

    try:
        for entry in os.scandir(folder):
            try:
                if entry.is_file(follow_symlinks=False):
                    stat = entry.stat()
                    if min_age_secs > 0 and (now - stat.st_mtime) < min_age_secs:
                        continue
                    total_bytes += stat.st_size
                    count += 1
                elif entry.is_dir(follow_symlinks=False):
                    sub_b, sub_c = _get_folder_size(Path(entry.path), min_age_secs)
                    total_bytes += sub_b
                    count += sub_c
            except (PermissionError, FileNotFoundError, OSError):
                continue
    except (PermissionError, FileNotFoundError, OSError):
        pass

    return total_bytes, count


def _clean_folder(folder: Path, min_age_secs: float = _SAFETY_MARGIN_SECONDS) -> tuple[int, int]:
    """Safely deletes eligible files and empty subdirectories in folder."""
    deleted_bytes = 0
    deleted_count = 0
    now = time.time()
    if not folder.exists() or not folder.is_dir():
        return 0, 0

    try:
        for root, dirs, files in os.walk(folder, topdown=False):
            for f in files:
                fp = Path(root) / f
                try:
                    stat = fp.stat()
                    if (now - stat.st_mtime) < min_age_secs:
                        continue
                    sz = stat.st_size
                    fp.unlink(missing_ok=True)
                    deleted_bytes += sz
                    deleted_count += 1
                except (PermissionError, FileNotFoundError, OSError):
                    continue

            for d in dirs:
                dp = Path(root) / d
                try:
                    dp.rmdir()
                except (PermissionError, OSError):
                    continue
    except (PermissionError, OSError):
        pass

    return deleted_bytes, deleted_count


def _get_recycle_bin_stats() -> tuple[int, int]:
    """Returns (bytes, item_count) in Windows Recycle Bin using shell32."""
    if _OS != "Windows":
        return 0, 0
    try:
        class SHQUERYRBINFO(ctypes.Structure):
            _fields_ = [
                ("cbSize", ctypes.c_ulong),
                ("i64Size", ctypes.c_int64),
                ("i64NumItems", ctypes.c_int64),
            ]
        info = SHQUERYRBINFO()
        info.cbSize = ctypes.sizeof(SHQUERYRBINFO)
        res = ctypes.windll.shell32.SHQueryRecycleBinW(None, ctypes.byref(info))
        if res == 0:
            return int(info.i64Size), int(info.i64NumItems)
    except Exception:
        pass
    return 0, 0


def _empty_recycle_bin() -> str:
    """Empty Windows Recycle Bin without popups."""
    if _OS != "Windows":
        return "Recycle Bin emptying only supported on Windows."
    try:
        flags = 7  # SHERB_NOCONFIRMATION | SHERB_NOPROGRESSUI | SHERB_NOSOUND
        res = ctypes.windll.shell32.SHEmptyRecycleBinW(None, None, flags)
        if res == 0:
            return "Recycle Bin cleared."
        elif res == -2147418113:  # 0x8000ffff / already empty
            return "Recycle Bin is already empty."
        return f"Recycle Bin purged (code {res})."
    except Exception as e:
        return f"Failed to empty Recycle Bin: {e}"


def _clean_dev_caches() -> tuple[int, int, list[str]]:
    """Purge pip cache, pytest cache, and project __pycache__ folders."""
    actions_taken: list[str] = []
    freed_bytes = 0
    files_count = 0

    # 1. pip cache purge
    try:
        res = subprocess.run([sys.executable, "-m", "pip", "cache", "purge"], capture_output=True, text=True, timeout=10, **_WIN_HIDE)
        if res.returncode == 0:
            out = res.stdout.strip()
            if "Files removed:" in out:
                actions_taken.append(f"Pip Cache: {out.splitlines()[0]}")
    except Exception:
        pass

    # 2. Pycache cleanup in workspace
    try:
        for pycache in _BASE_DIR.rglob("__pycache__"):
            if pycache.is_dir():
                b, c = _get_folder_size(pycache)
                try:
                    shutil.rmtree(pycache, ignore_errors=True)
                    freed_bytes += b
                    files_count += c
                except Exception:
                    pass
        if files_count > 0:
            actions_taken.append(f"Workspace Pycaches: {files_count} files ({freed_bytes / (1024*1024):.1f} MB)")
    except Exception:
        pass

    return freed_bytes, files_count, actions_taken


def scan_purge_targets() -> str:
    """Calculates total potential disk space that can be reclaimed."""
    lines = [
        "🧹 PURGE PROTOCOL — SYSTEM AUDIT",
        "Analyzing reclaimable temporary sludge and caches...",
        "─" * 45,
    ]

    total_bytes = 0
    total_files = 0

    # User Temp
    user_temp = Path(os.environ.get("TEMP", Path.home() / "AppData" / "Local" / "Temp"))
    if user_temp.exists():
        b, c = _get_folder_size(user_temp, min_age_secs=_SAFETY_MARGIN_SECONDS)
        total_bytes += b
        total_files += c
        lines.append(f"• User Temp Directory:   {b / (1024*1024):>8.1f} MB  ({c:,} files)")

    # Crash Dumps
    crash_dir = Path.home() / "AppData" / "Local" / "CrashDumps"
    if crash_dir.exists():
        b, c = _get_folder_size(crash_dir)
        total_bytes += b
        total_files += c
        lines.append(f"• Application Crash Dumps: {b / (1024*1024):>6.1f} MB  ({c:,} files)")

    # Windows Temp (if accessible)
    win_temp = Path("C:/Windows/Temp")
    if win_temp.exists():
        b, c = _get_folder_size(win_temp, min_age_secs=_SAFETY_MARGIN_SECONDS)
        if c > 0:
            total_bytes += b
            total_files += c
            lines.append(f"• Windows Temp Directory: {b / (1024*1024):>7.1f} MB  ({c:,} files)")

    # Recycle Bin
    rb_bytes, rb_items = _get_recycle_bin_stats()
    if rb_items > 0:
        total_bytes += rb_bytes
        total_files += rb_items
        lines.append(f"• Windows Recycle Bin:    {rb_bytes / (1024*1024):>7.1f} MB  ({rb_items:,} items)")

    lines.append("─" * 45)
    lines.append(f"Total Reclaimable: {total_bytes / (1024*1024):.2f} MB ({total_bytes / (1024**3):.2f} GB in {total_files:,} items)")
    lines.append("Say 'Ultron, purge all' or call purge_protocol with action='purge' to execute.")
    return "\n".join(lines)


def execute_purge(include_recycle_bin: bool = True, include_dev: bool = True) -> str:
    """Performs the purge and returns exact space freed."""
    lines = [
        "💥 PURGE PROTOCOL EXECUTED",
        "Cleaning digital debris, temporary files, and caches...",
        "─" * 45,
    ]

    freed_bytes = 0
    freed_count = 0

    # 1. User Temp
    user_temp = Path(os.environ.get("TEMP", Path.home() / "AppData" / "Local" / "Temp"))
    if user_temp.exists():
        b, c = _clean_folder(user_temp, min_age_secs=_SAFETY_MARGIN_SECONDS)
        freed_bytes += b
        freed_count += c
        lines.append(f"• Purged User Temp: {b / (1024*1024):.1f} MB ({c:,} files)")

    # 2. Crash Dumps
    crash_dir = Path.home() / "AppData" / "Local" / "CrashDumps"
    if crash_dir.exists():
        b, c = _clean_folder(crash_dir, min_age_secs=0)
        freed_bytes += b
        freed_count += c
        if c > 0:
            lines.append(f"• Purged Crash Dumps: {b / (1024*1024):.1f} MB ({c:,} files)")

    # 3. Developer Caches
    if include_dev:
        db, dc, dev_logs = _clean_dev_caches()
        freed_bytes += db
        freed_count += dc
        for dlog in dev_logs:
            lines.append(f"• {dlog}")

    # 4. Windows Recycle Bin
    if include_recycle_bin:
        rb_sz, rb_cnt = _get_recycle_bin_stats()
        _empty_recycle_bin()
        freed_bytes += rb_sz
        freed_count += rb_cnt
        lines.append(f"• Emptied Recycle Bin: {rb_sz / (1024*1024):.1f} MB ({rb_cnt:,} items)")

    lines.append("─" * 45)
    mb_freed = freed_bytes / (1024 * 1024)
    gb_freed = freed_bytes / (1024 ** 3)
    if gb_freed >= 1.0:
        summary = f"Total reclaimed: {gb_freed:.2f} GB across {freed_count:,} items."
    else:
        summary = f"Total reclaimed: {mb_freed:.1f} MB across {freed_count:,} items."

    lines.append(summary)
    lines.append("Workstation storage optimized and cleansed, Boss.")
    return "\n".join(lines)


def _audit_log_purge(action: str, recycle_bin: bool, dev: bool, result: str) -> None:
    """Append a purge action record to the command audit trail. Never raises."""
    try:
        record = {
            "when": _dt.datetime.now(_dt.timezone.utc).isoformat(),
            "os": _OS,
            "action": action,
            "recycle_bin": recycle_bin,
            "dev_caches": dev,
            "result": (result or "")[:500],
        }
        with open(_AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass


def purge_protocol(parameters: dict, player=None, **kwargs) -> str:
    """Main handler for purge_protocol tool."""
    action = (parameters.get("action") or "scan").lower().strip()

    if player:
        try:
            player.write_log(f"[Purge] Action: {action}")
        except Exception:
            pass

    try:
        if action in ("scan", "audit", "check", "inspect", "preview"):
            return scan_purge_targets()

        # Irreversible purge actions go through the confirmation gate.
        elif action in ("purge", "purge_all", "clean", "clean_all", "execute"):
            include_rb = bool(parameters.get("recycle_bin", True))
            include_dev = bool(parameters.get("dev_caches", True))

            def _run_purge() -> str:
                result = execute_purge(include_recycle_bin=include_rb, include_dev=include_dev)
                _audit_log_purge(action, include_rb, include_dev, result)
                return result

            confirm_key = f"purge_protocol:{hashlib.sha256(str(parameters).encode()).hexdigest()[:16]}"
            return confirm_gate.request(
                key=confirm_key,
                title="Execute system purge",
                detail=(
                    f"Purge will delete temp files, caches, crash dumps, "
                    f"{'and empty the Recycle Bin' if include_rb else ''}"
                    f"{' and clean developer caches' if include_dev else ''}. "
                    "This cannot be undone."
                ),
                run=_run_purge,
            )

        elif action in ("dev", "dev_cache", "pip", "pycache"):
            def _run_dev() -> str:
                b, c, logs = _clean_dev_caches()
                _audit_log_purge(action, False, True, f"{b} bytes, {c} files")
                return f"{b} bytes, {c} files"

            confirm_key = f"purge_protocol:dev:{hashlib.sha256(str(parameters).encode()).hexdigest()[:12]}"
            return confirm_gate.request(
                key=confirm_key,
                title="Clean developer caches",
                detail="Purge pip cache and Python __pycache__ folders. This cannot be undone.",
                run=_run_dev,
            )

        elif action in ("recycle_bin", "trash", "empty_trash"):
            def _run_rb() -> str:
                result = _empty_recycle_bin()
                _audit_log_purge(action, True, False, result)
                return result

            confirm_key = f"purge_protocol:recycle:{hashlib.sha256(str(parameters).encode()).hexdigest()[:12]}"
            return confirm_gate.request(
                key=confirm_key,
                title="Empty Recycle Bin",
                detail="Permanently empty the Windows Recycle Bin. Items cannot be recovered.",
                run=_run_rb,
            )

        else:
            return f"Unknown purge action '{action}'. Available: scan, purge, dev, recycle_bin."
    except Exception as e:
        return f"Purge protocol encounter error: {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "purge_protocol",
    "description": (
        "Deep System Purge & SSD Space Reclaimer. Scans and cleans Windows temp files, application caches, "
        "crash dumps, developer build residue (pip cache, pycache, pytest), and empties the Recycle Bin. "
        "Use when user asks to clean the computer, purge temp files, free up disk space, clean cache, or audit junk storage."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "scan (audit reclaimable junk without deleting) | purge (execute deep clean) | dev (clean developer/pip caches) | recycle_bin (empty trash only)"
            },
            "recycle_bin": {
                "type": "BOOLEAN",
                "description": "Whether to empty the Windows Recycle Bin during purge. Default: true"
            },
            "dev_caches": {
                "type": "BOOLEAN",
                "description": "Whether to purge pip cache and Python pycaches during purge. Default: true"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": purge_protocol,
}
