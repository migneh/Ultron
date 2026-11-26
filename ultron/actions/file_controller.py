import os
import platform
import shutil
from datetime import datetime
from pathlib import Path

from ultron.core.undo import push_undo

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Small-write snapshots are bounded to fit both byte states in an immutable
# approval plan. The adapter independently enforces the same byte ceiling.
_UNDO_CONTENT_LIMIT = 16000


def _undo_create(target: Path):
    def unavailable():
        raise PermissionError("Legacy raw create/download inverse disabled; use registered exact-entry undo")
    return unavailable


def _undo_write(target: Path, previous: bytes | None):
    def unavailable():
        raise PermissionError("Legacy direct write inverse disabled; use registered exact-entry undo")
    return unavailable


def _restore_from_trash(original: Path) -> str:
    from ultron.core.file_trash import restore_disabled
    return restore_disabled()


_SAFE_ROOTS: list[Path] = [
    Path.home(),
]


def _is_safe_path(target: Path) -> bool:
    """Is the given path inside _SAFE_ROOTS? If not, reject the operation."""
    try:
        resolved = target.resolve()
        return any(
            resolved == root.resolve() or resolved.is_relative_to(root.resolve())
            for root in _SAFE_ROOTS
        )
    except Exception:
        return False


def _get_desktop() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DESKTOP_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Desktop"


def _get_downloads() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOWNLOAD_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Downloads"


def _get_documents() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_DOCUMENTS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Documents"


def _get_pictures() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_PICTURES_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Pictures"


def _get_music() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_MUSIC_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Music"


def _get_videos() -> Path:
    if _OS == "Linux":
        xdg = os.environ.get("XDG_VIDEOS_DIR", "")
        if xdg and Path(xdg).exists():
            return Path(xdg)
    return Path.home() / "Videos"


def _resolve_path(raw: str) -> Path:
    shortcuts: dict[str, Path] = {
        "desktop": _get_desktop(),
        "downloads": _get_downloads(),
        "documents": _get_documents(),
        "pictures": _get_pictures(),
        "music": _get_music(),
        "videos": _get_videos(),
        "home": Path.home(),
    }
    raw = raw.strip().strip('"').strip("'")
    lower = raw.lower()
    if lower in shortcuts:
        return shortcuts[lower]

    # "desktop/notes/a.md" and "desktop\notes\a.md" — a shortcut followed by a
    # sub-path.  Without this branch the whole string falls through to the
    # relative-path return below and is resolved against the process CWD instead
    # of the real Desktop: an "Access denied" when the project lives outside the
    # home directory, or — worse — a silent write into a stray "desktop" folder
    # inside the project when it lives inside it.
    head, sep, rest = raw.replace("\\", "/").partition("/")
    if sep and head.lower() in shortcuts:
        rest = rest.strip("/")
        return shortcuts[head.lower()] / rest if rest else shortcuts[head.lower()]

    return Path(raw).expanduser()


def _format_size(b: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"


def _safe_trash(target: Path) -> str:

    from ultron.core import file_trash
    return file_trash.request(target, allowed=_is_safe_path)


def list_files(path: str = "desktop", show_hidden: bool = False) -> str:
    try:
        target = _resolve_path(path)
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Path not found: {target}"
        if not target.is_dir():
            return f"Not a directory: {target}"

        items = []
        for item in sorted(target.iterdir()):
            if not show_hidden and item.name.startswith("."):
                continue
            if item.is_dir():
                items.append(f"📁 {item.name}/")
            else:
                size = _format_size(item.stat().st_size)
                items.append(f"📄 {item.name} ({size})")

        if not items:
            return f"Directory is empty: {target.name}/"

        return f"Contents of {target.name}/ ({len(items)} items):\n" + "\n".join(items)

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Error listing files: {e}"


def create_file(path: str, name: str = "", content: str = "") -> str:
    from ultron.core import file_mutations
    try:
        base = _resolve_path(path)
        return file_mutations.request(base / name if name else base, "create", content=content, allowed=_is_safe_path)
    except Exception:
        return "Create rejected: invalid path; no overwrite or implicit parent creation."


def create_folder(path: str, name: str = "") -> str:
    from ultron.core import file_mutations
    try:
        base = _resolve_path(path)
        return file_mutations.request(base / name if name else base, "mkdir", allowed=_is_safe_path)
    except Exception:
        return "Folder creation rejected: invalid path; no implicit parents."


def delete_file(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        return _safe_trash(base / name if name else base)
    except Exception:
        return "Trash request rejected: invalid path; nothing submitted, no permanent-delete fallback."


def _transfer_file(
    path: str, name: str, destination: str, *, copy: bool, dry_run: bool = False
) -> str:
    from ultron.core.file_safety import transfer

    try:
        if not destination:
            return "No destination specified."
        base = _resolve_path(path)
        src = base / name if name else base
        message, undo = transfer(
            src, _resolve_path(destination), copy=copy, allowed=_is_safe_path, dry_run=dry_run
        )
        if undo is not None:
            push_undo(message, undo)
        return message
    except Exception as error:
        return f"Transfer refused/failed: {error}"


def move_file(path: str, name: str = "", destination: str = "", dry_run: bool = False) -> str:
    return _transfer_file(path, name, destination, copy=False, dry_run=dry_run)


def copy_file(path: str, name: str = "", destination: str = "", dry_run: bool = False) -> str:
    return _transfer_file(path, name, destination, copy=True, dry_run=dry_run)


def rename_file(path: str, name: str = "", new_name: str = "", dry_run: bool = False) -> str:
    if (
        not isinstance(new_name, str)
        or not new_name
        or new_name in {".", ".."}
        or any(c in new_name for c in ("/", "\\", "\x00"))
        or Path(new_name).is_absolute()
    ):
        return "Rename rejected: new_name must be a single filename."
    base = _resolve_path(path)
    target = base / name if name else base
    return _transfer_file(
        str(target), "", str(target.parent / new_name), copy=False, dry_run=dry_run
    )


def read_file(path: str, name: str = "", max_chars: int = 4000) -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"File not found: {target.name}"
        if not target.is_file():
            return f"Not a file: {target.name}"

        content = target.read_text(encoding="utf-8", errors="ignore")
        if len(content) > max_chars:
            content = content[:max_chars] + f"\n\n[Truncated — {len(content)} total chars]"
        return content

    except Exception as e:
        return f"Could not read file: {e}"


def write_file(path: str, name: str = "", content: str = "", append: bool = False) -> str:
    from ultron.core import file_mutations
    if not isinstance(content, str) or type(append) is not bool:
        return "Write rejected: invalid content/append."
    try:
        if len(content.encode("utf-8")) > _UNDO_CONTENT_LIMIT:
            return "Write rejected: input content limit exceeded."
        base = _resolve_path(path)
        return file_mutations.request(base / name if name else base, "write", content=content, append=append, allowed=_is_safe_path)
    except Exception:
        return "Write rejected: invalid path; no implicit parent creation."


def find_files(
    name: str = "", extension: str = "", path: str = "home", max_results: int = 20
) -> str:
    """Compatibility entrypoint using the bounded read-only search engine."""
    from ultron.actions.file_search import file_search

    return file_search(
        {"path": path, "query": name, "extension": extension, "max_results": max_results}
    )


def get_largest_files(path: str = "downloads", count: int = 10) -> str:
    count = min(count, 50)  # maksimum 50
    try:
        search_path = _resolve_path(path)
        if not _is_safe_path(search_path):
            return f"Access denied: {search_path}"
        if not search_path.exists():
            return f"Path not found: {path}"

        files = []
        for item in search_path.rglob("*"):
            if item.is_file():
                try:
                    files.append((item.stat().st_size, item))
                except Exception:
                    continue

        files.sort(reverse=True)
        top = files[:count]

        if not top:
            return "No files found."

        lines = [f"Top {len(top)} largest files in {search_path.name}/:"]
        for size, f in top:
            lines.append(f"  {_format_size(size):>10}  {f.name}  ({f.parent})")

        return "\n".join(lines)

    except Exception as e:
        return f"Error: {e}"


def get_disk_usage(path: str = "home") -> str:
    try:
        target = _resolve_path(path)
        usage = shutil.disk_usage(target)
        pct = usage.used / usage.total * 100
        return (
            f"Disk usage ({target}):\n"
            f"  Total : {_format_size(usage.total)}\n"
            f"  Used  : {_format_size(usage.used)} ({pct:.1f}%)\n"
            f"  Free  : {_format_size(usage.free)}"
        )
    except Exception as e:
        return f"Could not get disk usage: {e}"


def organize_desktop(dry_run: bool = True) -> str:
    if dry_run is False:
        return "Desktop organization apply disabled: requires an approved immutable batch and conflict-aware reversal. Use dry_run preview and individually approved transfers."
    type_map = {
        "Images": {".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp", ".svg", ".ico", ".heic"},
        "Documents": {
            ".pdf",
            ".doc",
            ".docx",
            ".txt",
            ".xls",
            ".xlsx",
            ".ppt",
            ".pptx",
            ".csv",
            ".odt",
            ".ods",
            ".odp",
        },
        "Videos": {".mp4", ".avi", ".mkv", ".mov", ".wmv", ".flv", ".webm", ".m4v"},
        "Music": {".mp3", ".wav", ".flac", ".aac", ".ogg", ".wma", ".m4a"},
        "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz"},
        "Code": {
            ".py",
            ".js",
            ".ts",
            ".html",
            ".css",
            ".json",
            ".xml",
            ".cpp",
            ".java",
            ".cs",
            ".go",
            ".rs",
            ".sh",
        },
    }

    from ultron.core.file_safety import LOCK, checked, fingerprint

    if type(dry_run) is not bool:
        return "dry_run must be a boolean"
    lines = []
    try:
        with LOCK:
            desktop = checked(_get_desktop(), _is_safe_path)
            if not desktop.is_dir():
                return "Desktop directory not found."
            import itertools

            items = list(itertools.islice(desktop.iterdir(), 501))
            if len(items) > 500:
                return "Organization refused: more than 500 desktop entries."
            for item in sorted(items):
                if item.name.startswith(".") or item.is_symlink() or not item.is_file():
                    continue
                category = next((folder for folder, exts in type_map.items()
                                 if item.suffix.lower() in exts), "Others")
                destination = desktop / category / item.name
                try:
                    checked(destination, _is_safe_path)
                    if os.path.lexists(destination):
                        lines.append(f"SKIPPED conflict: {destination}")
                        continue
                    fingerprint(item)
                    lines.append(f"PLAN: {item} -> {destination}")
                except Exception:
                    lines.append(f"SKIPPED: {item.name}; validation failed")
    except Exception:
        return "Organization preview unavailable; no changes made."
    return ("DRY RUN: no changes made. Batch apply disabled; use individually approved transfers "
            "with existing destination parents.\n" + ("\n".join(lines) or "No eligible files."))


def get_file_info(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        stat = target.stat()
        info = {
            "Name": target.name,
            "Type": "Folder" if target.is_dir() else "File",
            "Size": _format_size(stat.st_size),
            "Location": str(target.parent),
            "Created": datetime.fromtimestamp(stat.st_ctime).strftime("%Y-%m-%d %H:%M"),
            "Modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "Extension": target.suffix or "—",
        }
        return "\n".join(f"  {k}: {v}" for k, v in info.items())

    except Exception as e:
        return f"Could not get file info: {e}"


def download_file(url: str, destination: str = "downloads", name: str = "") -> str:
    from ultron.core import downloads
    try:
        if not isinstance(destination, str) or not destination.strip():
            return "Download rejected: destination must name an existing directory."
        return downloads.request(url, _resolve_path(destination), name, _is_safe_path)
    except Exception:
        return "Download request rejected: invalid destination; no request submitted."


def file_controller(
    parameters: dict | None = None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    if not isinstance(parameters, dict):
        return "File request rejected: parameters must be an object"
    params = parameters
    if not isinstance(params.get("action", ""), str):
        return "File request rejected: action must be a string"
    if "dry_run" in params and not isinstance(params["dry_run"], bool):
        return "File request rejected: dry_run must be a boolean"
    if "dry_run" in params and params.get("action", "").lower().strip() not in {
        "move",
        "copy",
        "rename",
        "organize_desktop",
    }:
        return "File request rejected: dry_run supported only for move/copy/rename/organize_desktop"
    action = params.get("action", "").lower().strip()
    path = params.get("path", "desktop")
    name = params.get("name", "")

    if player:
        player.write_log(f"[file] {action} {name or path}")

    try:
        if action == "list":
            return list_files(path)

        elif action == "create_file":
            return create_file(path, name=name, content=params.get("content", ""))

        elif action == "create_folder":
            return create_folder(path, name=name)

        elif action == "delete":
            return delete_file(path, name=name)

        elif action == "move":
            return move_file(
                path,
                name=name,
                destination=params.get("destination", ""),
                dry_run=params.get("dry_run", False),
            )

        elif action == "copy":
            return copy_file(
                path,
                name=name,
                destination=params.get("destination", ""),
                dry_run=params.get("dry_run", False),
            )

        elif action == "rename":
            return rename_file(
                path,
                name=name,
                new_name=params.get("new_name", ""),
                dry_run=params.get("dry_run", False),
            )

        elif action == "read":
            return read_file(path, name=name)

        elif action == "write":
            return write_file(
                path,
                name=name,
                content=params.get("content", ""),
                append=params.get("append", False),
            )

        elif action == "download":
            return download_file(
                url=params.get("url", ""),
                destination=params.get("destination", "") or params.get("path", "") or "downloads",
                name=name or params.get("filename", ""),
            )

        elif action == "find":
            return find_files(
                name=name or params.get("name", ""),
                extension=params.get("extension", ""),
                path=path,
                max_results=min(int(params.get("max_results", 20)), 50),
            )

        elif action == "largest":
            return get_largest_files(
                path=path,
                count=int(params.get("count", 10)),
            )

        elif action == "disk_usage":
            return get_disk_usage(path)

        elif action == "organize_desktop":
            return organize_desktop(dry_run=params.get("dry_run", True))

        elif action == "info":
            return get_file_info(path, name=name)

        else:
            return f"Unknown action: '{action}'"

    except Exception as e:
        return f"File controller error ({action}): {e}"


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "file_controller",
    "description": "File utilities. Move/copy/rename support regular files up to 64 MiB only, no overwrite, no symlinks, existing parent required; moves require same-volume hard-link support. dry_run previews supported for transfers and organize_desktop (organize defaults to preview). Undo refuses changed targets or occupied origins. Downloads: public HTTP(S), existing destination directory, 16 MiB/20-second caller limit, no overwrite, no server filename override. Transfers require exact host approval and undo requires separate approval. Desktop organization apply disabled (preview only). Create/folder/write/append require exact host approval, existing parents and <=16000 before/after bytes; replacing existing entries may change metadata/hardlink behavior. Delete requests require separate exact regular-file approval (64 MiB cap, no directories); Trash receipt/recoverability unverified and automatic restoration disabled. Downloads require two host approvals: URL receipt into memory, then exact hash/size/path publication. Redirects refused, undo separately approved; native race/time/retention limits remain.",
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "dry_run": {
                "type": "BOOLEAN",
                "description": "Preview move/copy/rename/organize_desktop without mutation. Organization defaults true; other transfers default false.",
            },
            "action": {
                "type": "STRING",
                "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | download | find | largest | disk_usage | organize_desktop | info",
            },
            "path": {
                "type": "STRING",
                "description": "File/folder path or shortcut: desktop, downloads, documents, home",
            },
            "url": {
                "type": "STRING",
                "description": "Public HTTP/HTTPS URL on standard ports; download capped at 16 MiB",
            },
            "destination": {
                "type": "STRING",
                "description": "Destination path for move/copy; download requires an existing directory",
            },
            "new_name": {"type": "STRING", "description": "New name for rename"},
            "content": {"type": "STRING", "description": "Content for create_file/write"},
            "name": {"type": "STRING", "description": "File name to search for or save as"},
            "extension": {"type": "STRING", "description": "File extension to search (e.g. .pdf)"},
            "max_results": {
                "type": "INTEGER",
                "description": "Maximum find results, 1–50 (default 20)",
            },
            "count": {"type": "INTEGER", "description": "Number of results for largest"},
        },
        "required": ["action"],
    },
    "handler": file_controller,
}
