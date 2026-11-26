"""Approval-bound single regular-file native Trash submission.

No directories, permanent-delete fallback or automatic restore. Native Trash
location/receipt and physical recoverability are not verified by Send2Trash.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

from ultron.core import file_safety as safety
from ultron.core import operation_policy as policy


def _backend():
    # Import lazily; resolving the callable does not delete anything.
    from send2trash import send2trash
    return send2trash


def _snapshot(path, allowed):
    path = safety.checked(Path(path), allowed)
    parent = safety.checked(path.parent, allowed)
    info = path.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError("Only regular files supported, not directories/special files")
    identity = list(safety.fingerprint(path))
    final = path.lstat()
    if (final.st_dev, final.st_ino, final.st_size, final.st_mtime_ns, final.st_mode) != tuple(identity[:-1]):
        raise ValueError("Target changed during snapshot")
    parent_info = parent.stat()
    if not stat.S_ISDIR(parent_info.st_mode):
        raise ValueError("Parent not a directory")
    return {"path": str(path), "identity": identity, "links": final.st_nlink,
            "parent": [str(parent), parent_info.st_dev, parent_info.st_ino, parent_info.st_mode]}


def _execute(plan, allowed, backend):
    policy.consume(plan)
    payload = plan.payload()
    with safety.LOCK:
        try:
            if _snapshot(payload["path"], allowed) != payload:
                return "Trash refused: target or parent changed; no native request made."
            if _backend() is not backend:
                return "Trash refused: backend changed; no native request made."
        except Exception:
            return "Trash refused: target, root policy, parent or backend unavailable/changed; no native request made."
        try:
            backend(payload["path"])  # exactly once; never retry or unlink on error
        except Exception:
            return "Trash request failed or outcome unknown. Inspect original path and native Trash manually; no retry, permanent-delete fallback or automatic restore attempted."
        if os.path.lexists(payload["path"]):
            return "Native Trash call returned, but original path still exists or was recreated. Outcome unverified; no retry or automatic restore."
        return ("Native Trash call returned and original path is now absent. "
                "Trash receipt, stored item identity and recoverability are NOT verified. "
                "No automatic undo registered; inspect native Trash manually. No permanent-delete fallback.")


def request(path, *, allowed):
    try:
        with safety.LOCK:
            snapshot = _snapshot(path, allowed)
            backend = _backend()
            if not callable(backend):
                raise ValueError("Invalid Trash adapter")
            plan = policy.prepare("files.trash", (snapshot["path"],), snapshot)
        detail = ("Submit exactly one regular-file path to the installed native Send2Trash adapter.\n"
                  + json.dumps(plan.payload(), ensure_ascii=True)
                  + "\nThis removes this directory entry, not every hardlink/copy. Native implementation, "
                  "filesystem and Trash policy are trusted; Trash may use another volume or implementation-specific storage. "
                  "No directories, batches, unlink/permanent-delete fallback or automatic retry. "
                  "No stable native Trash receipt is available: automatic restoration/undo is disabled. "
                  "Source absence is not proof of recoverability. Concurrent path replacement races remain; "
                  "this is not a filesystem sandbox. Check native Trash manually after submission.")
        return policy.request(plan, title="Move one exact regular file to native Trash",
                              detail=detail, execute=lambda approved: _execute(approved, allowed, backend))
    except Exception:
        return ("Trash unavailable/refused: require a safe existing regular file up to 64 MiB, "
                "non-symlink path/parents and installed Send2Trash adapter. Directories and special files "
                "are unsupported. Nothing submitted; no permanent-delete fallback.")


def restore_disabled():
    return ("Automatic Trash restoration disabled: no stable native receipt identifies the exact deleted item. "
            "No Trash enumeration, guessed name/path restore or overwrite attempted. Inspect native Trash manually; "
            "item existence and recoverability are not guaranteed.")
