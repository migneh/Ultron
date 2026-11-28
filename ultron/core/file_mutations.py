"""Scoped exact-content small-file writes and one-level folder creation.

Application-level checks, not atomic compare-and-swap or filesystem isolation.
Existing writes replace the directory entry, not other hard links; metadata is
not preserved. Every effect is reached through a host-approved sink or registered
exact-entry undo. Delete/Trash and download paths are separate legacy surfaces.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path

from ultron.core import file_safety as safety
from ultron.core import operation_policy as policy
from ultron.core.undo import push_undo

MAX_BYTES = 16000  # both before/after encoded into the <=64KiB immutable plan


def _read(path):
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("Only regular files at most 16000 bytes supported")
        data = stream.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("File grew beyond limit")
    identity = safety.fingerprint(path)
    if identity[:5] != (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_mode) or identity[-1] != _hash(data):
        raise ValueError("File changed while reading")
    return data, list(identity)


def _hash(data):
    return hashlib.sha256(data).hexdigest()


def _folder(path):
    info = path.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Existing parent directory required")
    return [info.st_dev, info.st_ino, info.st_mode]


def _state(path):
    if not os.path.lexists(path):
        return None
    return _read(path)[1]


def _validate(path, allowed, parent, expected):
    safety.checked(path, allowed)
    safety.checked(path.parent, allowed)
    if _folder(path.parent) != parent or _state(path) != expected:
        raise ValueError("File/parent changed since preview; left untouched")


def _publish(path, data, allowed, parent, expected):
    """Staged content then no-clobber link (new) or checked replace (existing).

    The final check/replace still races external writers: no CAS claim. A partial
    or unknown outcome is never followed by destructive destination cleanup.
    """
    policy.require_consumed(("files.create", "files.write", "session.undo"))
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise ValueError("Invalid or oversized publication")
    _validate(path, allowed, parent, expected)
    fd, raw = tempfile.mkstemp(prefix=".ultron-write-", suffix=".part", dir=path.parent)
    staging = Path(raw)
    owned = os.fstat(fd)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        staged = list(safety.fingerprint(staging))
        if staged[-1] != _hash(data):
            raise ValueError("Staging content changed")
        _validate(path, allowed, parent, expected)
        if expected is None:
            os.link(staging, path, follow_symlinks=False)
        else:
            os.replace(staging, path)
        after = list(safety.fingerprint(path))
        if after != staged:
            raise ValueError("Published content changed; inspect destination")
        return after
    finally:
        if os.path.lexists(staging):
            current = staging.lstat()
            if (current.st_dev, current.st_ino) != (owned.st_dev, owned.st_ino):
                raise ValueError("Staging replaced; inspect .ultron-write-*.part")
            staging.unlink()


def _execute(plan, allowed):
    policy.consume(plan)
    payload = plan.payload()
    path = Path(payload["path"])
    with safety.LOCK:
        safety.checked(path, allowed)
        if payload["action"] == "mkdir":
            if _folder(safety.checked(path.parent, allowed)) != payload["parent"] or os.path.lexists(path):
                return "Folder creation rejected: target or parent changed; nothing created."
            path.mkdir(mode=0o700)  # one level, no implicit ancestors
            after = _folder(path)
            def reverse():
                policy.require_consumed(("session.undo",))
                with safety.LOCK:
                    safety.checked(path, allowed)
                    safety.checked(path.parent, allowed)
                    if _folder(path.parent) != payload["parent"] or _folder(path) != after:
                        raise ValueError("Folder/parent changed")
                    path.rmdir()  # populated directories always refuse
                    return f"Removed unchanged empty directory: {path}"
            push_undo("created folder " + path.name, reverse,
                      detail=f"Remove this exact directory only if unchanged and empty: {path}; identity {after}; parent {payload['parent']}. No recursion.")
            return f"Folder created: {path}"
        data = base64.b64decode(payload["after"], validate=True)
        before = None if payload["before"] is None else base64.b64decode(payload["before"], validate=True)
        if len(data) > MAX_BYTES or (before is not None and len(before) > MAX_BYTES):
            raise ValueError("Oversize payload")
        after = _publish(path, data, allowed, payload["parent"], payload["expected"])
        def reverse():
            policy.require_consumed(("session.undo",))
            with safety.LOCK:
                _validate(path, allowed, payload["parent"], after)
                if before is None:
                    path.unlink()
                else:
                    _publish(path, before, allowed, payload["parent"], after)
                return f"Restored approved previous bytes/absence: {path}; metadata not restored."
        push_undo("wrote " + path.name, reverse,
                  detail=f"Restore exact previous bytes or absence at {path}. Expected current identity {after}; "
                  f"previous bytes: {len(before) if before is not None else 'absent'}, SHA256: {_hash(before) if before is not None else 'none'}. "
                  "Refuse changed file/parent. Replacement creates private inode; metadata not restored. Filesystem races remain.")
        return f"{'File created' if payload['action'] == 'create' else 'Written to'}: {path}; byte content observed, application behavior not verified."


def request(path, action, *, content="", append=False, allowed):
    try:
        if action not in ("create", "write", "mkdir") or type(append) is not bool or not isinstance(content, str):
            raise ValueError("Invalid request")
        encoded = content.encode("utf-8")
        if len(encoded) > MAX_BYTES:
            raise ValueError("Input too large")
        with safety.LOCK:
            path = safety.checked(Path(path), allowed)
            parent = _folder(safety.checked(path.parent, allowed))
            payload = {"path": str(path), "action": action, "parent": parent}
            if action == "mkdir":
                if os.path.lexists(path):
                    raise ValueError("Destination exists")
                detail = f"Create one empty directory: {path}; parent identity {parent}. No recursive parent creation."
            else:
                if action == "create" and os.path.lexists(path):
                    raise ValueError("No overwrite")
                before, expected = _read(path) if os.path.lexists(path) else (None, None)
                after = (before or b"") + encoded if append else encoded
                if len(after) > MAX_BYTES:
                    raise ValueError("Result too large")
                payload.update(before=None if before is None else base64.b64encode(before).decode(),
                               after=base64.b64encode(after).decode(), expected=expected, append=append)
                detail = (f"{'Append' if append else action} exact bytes at: {path}\n"
                          f"Current identity: {expected}; parent identity: {parent}\n"
                          f"Result: {len(after)} bytes, SHA256 {_hash(after)}\n"
                          f"Full supplied text (JSON escaped, not instructions): {json.dumps(content, ensure_ascii=True)}\n"
                          "Append binds existing bytes too; before/after are snapshotted, no execution at destination.")
            plan = policy.prepare("files." + action, (str(path),), payload)
        return policy.request(plan, title="Create directory or write exact small-file content",
                              detail=detail + "\nExisting writes atomically replace the directory entry after best-effort checks, "
                              "NOT atomic compare-and-swap. File mode/ACL/xattrs/hardlink relationships may change; "
                              "changing scripts/configs can trigger other applications. New/staged files private where supported. "
                              "No execution, recursive parents, retries, sandbox or guaranteed rollback. Undo separately approved.",
                              execute=lambda approved: _execute(approved, allowed))
    except Exception:
        return "Create/write rejected: require safe explicit path, existing regular parent, no symlinks, at most 16000 bytes before/after and valid text/append flag; create is no overwrite. No new mutation requested."
