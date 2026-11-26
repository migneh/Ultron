"""Conservative regular-file transfers and conflict-aware session undo.

Not a filesystem sandbox: another process can race path checks. No directory
transfers or cross-filesystem moves are attempted; existing targets never merge.
"""

from __future__ import annotations

import hashlib
import os
import stat
import tempfile
import threading
from pathlib import Path
from typing import Callable

from ultron.core import operation_policy as policy

LOCK = threading.RLock()
MAX_BYTES = 64 * 1024 * 1024


def checked(path: Path, allowed: Callable[[Path], bool]) -> Path:
    path = Path(os.path.abspath(path))
    if not allowed(path):
        raise ValueError("Access denied: path outside allowed roots")
    for part in (path, *path.parents):
        if part.is_symlink() or (hasattr(part, "is_junction") and part.is_junction()):
            raise ValueError("Symlink/junction paths are not supported for mutations")
    return path


def fingerprint(path: Path) -> tuple:
    flags = (
        os.O_RDONLY
        | getattr(os, "O_BINARY", 0)
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
    )
    with os.fdopen(os.open(path, flags), "rb") as stream:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_BYTES:
            raise ValueError("Only regular files up to 64 MiB are supported")
        digest = hashlib.sha256()
        total = 0
        while chunk := stream.read(65536):
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("File grew beyond safety limit")
            digest.update(chunk)
        after = os.fstat(stream.fileno())

    def identity(s):
        return (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_mode)

    if identity(before) != identity(after):
        raise ValueError("File changed while reading")
    return (*identity(after), digest.hexdigest())


def _apply_transfer(
    plan: policy.OperationPlan, allowed: Callable[[Path], bool]
) -> str:
    policy.consume(plan)
    payload = plan.payload()
    src, dst, copy = Path(payload["src"]), Path(payload["dst"]), payload["copy"]
    with LOCK:
        src, dst = checked(src, allowed), checked(dst, allowed)
        if src == dst or os.path.lexists(dst):
            raise ValueError("Destination conflict: nothing overwritten or merged")
        if not dst.parent.is_dir():
            raise ValueError("Destination parent must already exist")
        if not src.is_file():
            raise ValueError("Only regular-file transfers supported; directories left untouched")
        before = fingerprint(src)
        if (list(before) != payload["source_identity"]
                or _parent_identity(src, allowed) != payload["source_parent"]
                or _parent_identity(dst, allowed) != payload["destination_parent"]):
            return "Transfer rejected: source or parent identity changed; nothing transferred."
        if copy:
            fd, raw = tempfile.mkstemp(prefix=".ultron-copy-", suffix=".part", dir=dst.parent)
            staging = Path(raw)
            staging_stat = os.fstat(fd)
            try:
                with os.fdopen(fd, "wb") as output:
                    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)
                    with os.fdopen(os.open(src, flags), "rb") as source:
                        current = os.fstat(source.fileno())
                        if (current.st_dev, current.st_ino, current.st_size, current.st_mtime_ns, current.st_mode) != before[:-1]:
                            raise ValueError("Source replaced before copy")
                        total = 0
                        while chunk := source.read(65536):
                            total += len(chunk)
                            if total > MAX_BYTES:
                                raise ValueError("Source grew beyond safety limit")
                            output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
                staged = fingerprint(staging)
                if fingerprint(src) != before or staged[-1] != before[-1]:
                    raise ValueError("Source changed or copy content mismatch")
                checked(dst, allowed)
                if _parent_identity(dst, allowed) != payload["destination_parent"]:
                    raise ValueError("Destination parent changed during copy")
                os.link(staging, dst, follow_symlinks=False)
                after = fingerprint(dst)
                if after != staged:
                    raise ValueError("Published copy changed; inspect destination")
            finally:
                # Do not deliberately unlink an observed replacement staging file.
                # A final stat/unlink race remains; this is not fd-relative isolation.
                info = staging.lstat()
                if (info.st_dev, info.st_ino) != (staging_stat.st_dev, staging_stat.st_ino):
                    raise ValueError("Staging changed; inspect .ultron-copy-*.part manually")
                staging.unlink()
        else:
            # Atomic no-clobber publication, NOT an atomic rename transaction.
            os.link(src, dst, follow_symlinks=False)
            if fingerprint(src) != before or fingerprint(dst) != before:
                raise ValueError("Source changed during move; destination retained for inspection")
            # Do not delete destination on an uncertain unlink failure: it may
            # now be the only remaining copy, or have been replaced externally.
            src.unlink()
            after = fingerprint(dst)
            if after != before:
                raise ValueError("Moved file changed; inspect destination")

        def undo():
            with LOCK:
                checked(dst, allowed)
                if (_parent_identity(src, allowed) != payload["source_parent"]
                        or _parent_identity(dst, allowed) != payload["destination_parent"]):
                    raise ValueError("Undo conflict: parent changed")
                if not dst.exists() or fingerprint(dst) != after:
                    raise ValueError(
                        "Undo conflict: target missing, replaced or edited; left untouched"
                    )
                if copy:
                    dst.unlink()
                    return f"Removed unchanged copy: {dst}"
                checked(src, allowed)
                if os.path.lexists(src):
                    raise ValueError("Undo conflict: original path occupied; nothing overwritten")
                os.link(dst, src, follow_symlinks=False)
                if fingerprint(src) != after or fingerprint(dst) != after:
                    raise ValueError("Undo interrupted after publication; inspect both paths")
                dst.unlink()
                return f"Restored: {src}"

        message = f"{'Copied' if copy else 'Moved'}: {src} -> {dst}"
        from ultron.core.undo import push_undo
        push_undo(message, undo, detail=(
            f"Inverse: {'remove unchanged copy' if copy else 'move unchanged destination back to vacant source'}."
            f"\nSource: {src}\nDestination: {dst}\nExpected destination identity/hash: {after}"
            f"\nParent identities must match: {payload['source_parent']}, {payload['destination_parent']}."
            "\nNo overwrite; changed targets/occupied origins refuse. No guaranteed atomic rollback."))
        return message


def _parent_identity(path: Path, allowed: Callable[[Path], bool]) -> list:
    parent = checked(path.parent, allowed)
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise ValueError("Destination/source parent must already exist")
    return [str(parent), info.st_dev, info.st_ino, info.st_mode]


def transfer(
    src: Path, dst: Path, *, copy: bool, allowed: Callable[[Path], bool], dry_run: bool = False
) -> tuple[str, None]:
    """Preview/approve exact regular-file transfer, never return a raw undo effect.

    Undo is registered only inside the approved sink, after a completed transfer.
    Callers' root predicates are re-evaluated on execution; not an OS sandbox.
    """
    if type(dry_run) is not bool or type(copy) is not bool:
        raise ValueError("copy/dry_run must be boolean")
    with LOCK:
        src, dst = checked(src, allowed), checked(dst, allowed)
        if dst.is_dir():
            dst = checked(dst / src.name, allowed)
        if src == dst or os.path.lexists(dst):
            raise ValueError("Destination conflict: no overwrite")
        if not src.is_file():
            raise ValueError("Only regular-file transfers supported")
        before = fingerprint(src)
        payload = {"src": str(src), "dst": str(dst), "copy": copy,
                   "source_identity": list(before),
                   "source_parent": _parent_identity(src, allowed),
                   "destination_parent": _parent_identity(dst, allowed)}
        plan = policy.prepare("files.copy" if copy else "files.move", (str(src), str(dst)), payload)
    detail = (f"{'Copy' if copy else 'Move'} regular file\nSource: {src}\nDestination: {dst}"
              f"\nBytes: {before[2]}\nSHA256: {before[-1]}"
              "\nNo overwrite; existing parents only. Move requires same-volume hard-link support. "
              "Filesystem races remain; no process isolation or guaranteed rollback. Undo requires separate approval.")
    if dry_run:
        return "DRY RUN: " + detail + "; no changes made", None
    return policy.request(plan, title="Transfer one exact regular file", detail=detail,
                          execute=lambda approved: _apply_transfer(approved, allowed)), None
