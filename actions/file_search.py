"""Bounded, read-only local filename and opt-in UTF-8 text search.

Search results may contain private text and may be sent to the configured AI
provider. This is not a content-redaction/DLP system or a filesystem sandbox.
"""

from __future__ import annotations

import os
import stat
import time
from pathlib import Path

from actions import file_controller

MAX_ENTRIES = 10_000
MAX_DIRECTORIES = 500
MAX_SECONDS = 3.0
MAX_FILE_BYTES = 256 * 1024
MAX_CONTENT_BYTES = 4 * 1024 * 1024
_SKIP_DIRS = {
    "node_modules",
    "venv",
    ".venv",
    "__pycache__",
    "dist",
    "build",
    "target",
    "vendor",
    "coverage",
}
_TEXT_SUFFIXES = {
    ".txt",
    ".md",
    ".rst",
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".csv",
    ".html",
    ".css",
    ".sql",
    ".ini",
    ".cfg",
    ".xml",
    ".sh",
    ".log",
}
_SECRET_NAMES = {"api_keys.json", "api_keys.json.example", "id_rsa", "id_ed25519"}
_SECRET_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".kdbx"}


def _private(path: Path) -> bool:
    name = path.name.casefold()
    return (
        name.startswith(".")
        or name in _SECRET_NAMES
        or path.suffix.casefold() in _SECRET_SUFFIXES
        or any(word in name for word in ("credential", "password", "secret", "token"))
    )


def _integer(value, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise ValueError(f"{name} must be an integer from {minimum} to {maximum}.")
    return value


def _text_match(path: Path, needle: str, budget: dict) -> dict | None:
    """Never read more than the per-file and per-search byte budgets."""
    if path.suffix.casefold() not in _TEXT_SUFFIXES:
        budget["skipped"] += 1
        return None
    flags = (
        os.O_RDONLY
        | getattr(os, "O_NOFOLLOW", 0)
        | getattr(os, "O_NONBLOCK", 0)
        | getattr(os, "O_BINARY", 0)
    )
    fd = os.open(path, flags)
    with os.fdopen(fd, "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_FILE_BYTES:
            budget["skipped"] += 1
            return None
        allowance = min(MAX_FILE_BYTES + 1, budget["left"])
        if info.st_size >= allowance:
            budget["skipped"] += 1
            if budget["left"] < MAX_FILE_BYTES + 1:
                budget["exhausted"] = True
            return None
        raw = stream.read(allowance)
        budget["left"] -= len(raw)
    if len(raw) > MAX_FILE_BYTES or b"\x00" in raw:
        budget["skipped"] += 1
        return None
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        budget["skipped"] += 1
        return None
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line.casefold():
            # Keep source text intact but bound its exposure to a single short line.
            return {"line": number, "snippet": line.strip()[:180]}
    return None


def search_files(
    path: str = "documents",
    query: str = "",
    extension: str = "",
    content: str = "",
    max_results: int = 20,
    max_depth: int = 6,
    min_size_bytes: int = 0,
    max_size_bytes: int | None = None,
    modified_within_days: int | None = None,
) -> dict:
    """Return matching metadata and explicit coverage limits. Never modifies files."""
    for name, value in (
        ("path", path),
        ("query", query),
        ("extension", extension),
        ("content", content),
    ):
        if not isinstance(value, str):
            raise ValueError(f"{name} must be text.")
    if not path.strip():
        raise ValueError("Provide a search directory or shortcut.")
    max_results = _integer(max_results, "max_results", 1, 50)
    max_depth = _integer(max_depth, "max_depth", 0, 12)
    min_size_bytes = _integer(min_size_bytes, "min_size_bytes", 0, 10**15)
    if max_size_bytes is not None:
        max_size_bytes = _integer(max_size_bytes, "max_size_bytes", min_size_bytes, 10**15)
    if modified_within_days is not None:
        modified_within_days = _integer(modified_within_days, "modified_within_days", 1, 36500)
    if len(query) > 200 or len(content) > 200:
        raise ValueError("query/content must contain at most 200 characters.")
    suffix = extension.strip().casefold()
    if suffix:
        suffix = "." + suffix.lstrip(".")
        if not suffix[1:] or any(c in suffix for c in "/\\*?[]"):
            raise ValueError("extension must be a literal suffix such as pdf or .py.")
    root = file_controller._resolve_path(path)
    if root.is_symlink():
        raise ValueError("Choose the real directory rather than a symbolic link.")
    root = root.resolve()
    if not file_controller._is_safe_path(root):
        raise ValueError(
            "Access denied: search is restricted to the configured safe roots (home by default)."
        )
    if not root.is_dir():
        raise ValueError("Search directory not found or not a directory.")
    safe_root = max(
        (
            allowed.resolve()
            for allowed in file_controller._SAFE_ROOTS
            if root.is_relative_to(allowed.resolve())
        ),
        key=lambda item: len(item.parts),
    )
    if any(
        _private(Path(part)) or part.casefold() in _SKIP_DIRS
        for part in root.relative_to(safe_root).parts
    ):
        raise ValueError(
            "Hidden, credential-like and dependency directories are excluded from search."
        )

    cutoff = time.time() - modified_within_days * 86400 if modified_within_days else None
    deadline = time.monotonic() + MAX_SECONDS
    budget = {"left": MAX_CONTENT_BYTES, "skipped": 0, "exhausted": False}
    results = []
    limits: set[str] = set()
    errors = entries = directories = 0
    stack = [(root, 0)]
    name_needle, content_needle = query.casefold(), content.casefold()
    while stack:
        if time.monotonic() >= deadline:
            limits.add("time_limit")
            break
        if directories >= MAX_DIRECTORIES:
            limits.add("directory_limit")
            break
        directory, depth = stack.pop()
        directories += 1
        try:
            with os.scandir(directory) as iterator:
                for item in iterator:
                    if entries >= MAX_ENTRIES or time.monotonic() >= deadline:
                        limits.add("entry_limit" if entries >= MAX_ENTRIES else "time_limit")
                        break
                    entries += 1
                    candidate = Path(item.path)
                    try:
                        if item.is_symlink() or _private(candidate):
                            continue
                        resolved = candidate.resolve()
                        if not resolved.is_relative_to(root):
                            continue
                        if item.is_dir(follow_symlinks=False):
                            if candidate.name.casefold() in _SKIP_DIRS:
                                continue
                            if depth < max_depth:
                                stack.append((candidate, depth + 1))
                            else:
                                limits.add("depth_limit")
                            continue
                        if not item.is_file(follow_symlinks=False):
                            continue
                        if name_needle not in candidate.name.casefold():
                            continue
                        if suffix and candidate.suffix.casefold() != suffix:
                            continue
                        info = item.stat(follow_symlinks=False)
                        if (
                            info.st_size < min_size_bytes
                            or (max_size_bytes is not None and info.st_size > max_size_bytes)
                            or (cutoff is not None and info.st_mtime < cutoff)
                        ):
                            continue
                        match = (
                            _text_match(candidate, content_needle, budget) if content_needle else {}
                        )
                        if match is None:
                            continue
                        results.append(
                            {
                                "path": str(candidate),
                                "size_bytes": info.st_size,
                                "modified_unix": info.st_mtime,
                                **match,
                            }
                        )
                    except (OSError, ValueError, RuntimeError):
                        errors += 1
        except OSError:
            errors += 1
        if "entry_limit" in limits or "time_limit" in limits:
            break
    if budget["exhausted"]:
        limits.add("content_byte_limit")
    if len(results) > max_results:
        limits.add("result_limit")
    results.sort(key=lambda row: (-row["modified_unix"], row["path"].casefold()))
    return {
        "root": str(root),
        "results": results[:max_results],
        "matched_in_scanned_scope": len(results),
        "scanned_entries": entries,
        "scanned_directories": directories,
        "skipped_errors": errors,
        "skipped_content_files": budget["skipped"],
        "content_bytes_read": MAX_CONTENT_BYTES - budget["left"],
        "limits": sorted(limits),
    }


def format_results(report: dict) -> str:
    results = report["results"]
    lines = [f"Found {len(results)} file(s) in scanned scope: {report['root']}"]
    for row in results:
        lines.append(f"- {row['path']} ({row['size_bytes']} bytes)")
        if "line" in row:
            lines.append(f"  Line {row['line']}: {row['snippet']}")
    lines.append(
        f"Scanned {report['scanned_entries']} entries in {report['scanned_directories']} directories."
    )
    if report["limits"]:
        lines.append(
            "Partial coverage/results: "
            + ", ".join(report["limits"])
            + ". Narrow the directory or filters."
        )
    if report["skipped_errors"] or report["skipped_content_files"]:
        lines.append(
            f"Skipped {report['skipped_errors']} inaccessible entries and "
            f"{report['skipped_content_files']} unsupported/oversized/budget-limited content files."
        )
    lines.append(
        "Excludes hidden/credential-like paths, symlinks and dependency/build folders; not an exhaustive disk search."
    )
    return "\n".join(lines)


def file_search(parameters: dict, **kwargs) -> str:
    try:
        if not isinstance(parameters, dict):
            raise ValueError("Search parameters must be an object.")
        allowed = {
            "path",
            "query",
            "extension",
            "content",
            "max_results",
            "max_depth",
            "min_size_bytes",
            "max_size_bytes",
            "modified_within_days",
        }
        unknown = set(parameters) - allowed
        if unknown:
            raise ValueError("Unknown search fields: " + ", ".join(sorted(unknown)))
        return format_results(search_files(**parameters))
    except (ValueError, TypeError, OSError, RuntimeError) as error:
        return f"File search rejected: {error}"


TOOL = {
    "name": "file_search",
    "description": (
        "Read-only bounded local file search. Filter literal filename substring, extension, size and recency; "
        "optionally search a literal phrase inside small UTF-8 text files with line-numbered snippets. "
        "Use instead of shell find/grep. Default directory documents; safe roots only (home by default). "
        "Excludes hidden/credential-like paths, symlinks, dependencies and build folders. "
        "Partial coverage is reported. No regex or PDF/Office parsing. Only use content when the user wants text search; "
        "returned snippets may be shared with the configured AI provider."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "path": {
                "type": "STRING",
                "description": "Directory or home/documents/downloads/desktop shortcut; default documents",
            },
            "query": {
                "type": "STRING",
                "description": "Literal case-insensitive filename substring (not glob)",
            },
            "extension": {"type": "STRING", "description": "File extension such as pdf or .py"},
            "content": {
                "type": "STRING",
                "description": "Optional literal text phrase; small UTF-8 text files only",
            },
            "max_results": {"type": "INTEGER", "description": "1–50; default 20"},
            "max_depth": {
                "type": "INTEGER",
                "description": "0–12; default 6; 0 searches root files only",
            },
            "min_size_bytes": {"type": "INTEGER", "description": "Minimum file size in bytes"},
            "max_size_bytes": {
                "type": "INTEGER",
                "description": "Optional maximum file size in bytes",
            },
            "modified_within_days": {
                "type": "INTEGER",
                "description": "Modified in last 1–36500 days",
            },
        },
        "required": [],
    },
    "handler": file_search,
}
