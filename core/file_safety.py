"""Conservative regular-file transfers and conflict-aware session undo.

Not a filesystem sandbox: another process can race path checks. No directory
transfers or cross-filesystem moves are attempted; existing targets never merge.
"""

from __future__ import annotations

import hashlib
import os
import stat
import threading
from pathlib import Path
from typing import Callable

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


def transfer(
    src: Path, dst: Path, *, copy: bool, allowed: Callable[[Path], bool], dry_run: bool = False
) -> tuple[str, Callable[[], str] | None]:
    if not isinstance(dry_run, bool):
        raise ValueError("dry_run must be a boolean")
    with LOCK:
        src, dst = checked(src, allowed), checked(dst, allowed)
        if dst.is_dir():
            dst = checked(dst / src.name, allowed)
        if src == dst or os.path.lexists(dst):
            raise ValueError("Destination conflict: nothing overwritten or merged")
        if not dst.parent.is_dir():
            raise ValueError("Destination parent must already exist")
        if not src.is_file():
            raise ValueError("Only regular-file transfers supported; directories left untouched")
        before = fingerprint(src)
        if dry_run:
            return f"DRY RUN: {'copy' if copy else 'move'} {src} -> {dst}; no changes made", None
        if copy:
            created = False
            try:
                with dst.open("xb") as output:
                    created = True
                    with src.open("rb") as source:
                        total = 0
                        while chunk := source.read(65536):
                            total += len(chunk)
                            if total > MAX_BYTES:
                                raise ValueError("Source grew beyond safety limit")
                            output.write(chunk)
                if fingerprint(src) != before:
                    raise ValueError("Source changed during copy")
                after = fingerprint(dst)
                if after[-1] != before[-1]:
                    raise ValueError("Copy content mismatch")
            except Exception:
                if created:
                    dst.unlink(missing_ok=True)
                raise
        else:
            # link is an atomic no-clobber publication on supported same-volume
            # filesystems. No unsafe rename/shutil.move fallback.
            os.link(src, dst, follow_symlinks=False)
            try:
                if fingerprint(src) != before or fingerprint(dst) != before:
                    raise ValueError("Source changed during move")
                src.unlink()
            except Exception:
                dst.unlink(missing_ok=True)
                raise
            after = fingerprint(dst)

        def undo():
            with LOCK:
                checked(dst, allowed)
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
                dst.unlink()
                return f"Restored: {src}"

        return f"{'Copied' if copy else 'Moved'}: {src} -> {dst}", undo
