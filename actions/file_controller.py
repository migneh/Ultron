import os
import platform
import shutil
from datetime import datetime
from pathlib import Path

try:
    import send2trash

    _SEND2TRASH = True
except ImportError:
    _SEND2TRASH = False

from core.undo import push_undo

_OS = platform.system()  # "Windows" | "Darwin" | "Linux"

# Undo keeps a file's previous contents in memory so `write` can be reversed.
# Above this size it does not — a 200 MB log would sit in RAM for the rest of
# the session to protect an edit nobody is going to take back.
_UNDO_CONTENT_LIMIT = 1_000_000


def _undo_create(target: Path):
    from core.file_safety import LOCK, checked, fingerprint

    target = target.absolute()
    try:
        checked(target, _is_safe_path)
        directory = target.is_dir()
        state = (target.stat().st_dev, target.stat().st_ino) if directory else fingerprint(target)
    except Exception:

        def unavailable():
            raise ValueError("Undo unavailable: target could not be safely snapshotted")

        return unavailable

    def undo():
        with LOCK:
            checked(target, _is_safe_path)
            current = (
                (target.stat().st_dev, target.stat().st_ino) if directory else fingerprint(target)
            )
            if current != state:
                raise ValueError("Undo conflict: target changed/replaced; left untouched")
            if directory:
                target.rmdir()  # never remove a populated directory
            else:
                target.unlink()
            return f"Removed unchanged target: {target}"

    return undo


def _undo_write(target: Path, previous: bytes | None):
    from core.file_safety import LOCK, checked, fingerprint

    target = target.absolute()
    try:
        checked(target, _is_safe_path)
        state = fingerprint(target)
    except Exception:

        def unavailable():
            raise ValueError("Undo unavailable: target could not be safely snapshotted")

        return unavailable

    def undo():
        with LOCK:
            checked(target, _is_safe_path)
            if fingerprint(target) != state:
                raise ValueError("Undo conflict: file edited/replaced; left untouched")
            if previous is None:
                target.unlink()
            else:
                target.write_bytes(previous)
            return f"Restored previous state: {target}"

    return undo


def _restore_from_trash(original: Path) -> str:
    """Best-effort undelete.

    delete_file uses send2trash, which is the right call: the file lands in the
    Recycle Bin / Trash where the person can also find it themselves. Getting it
    back out again is shell work and only reliable on Windows, where pywin32 is
    already a dependency. Everywhere else this says where the file is instead of
    pretending it failed — the file is not lost either way."""
    if _OS == "Windows":
        try:
            import win32com.client

            shell = win32com.client.Dispatch("Shell.Application")
            bin_folder = shell.NameSpace(10)  # ssfBITBUCKET
            for item in bin_folder.Items():
                if (
                    str(bin_folder.GetDetailsOf(item, 1)).strip().lower()
                    == str(original.parent).strip().lower()
                ):
                    if str(item.Name).strip().lower() == original.name.strip().lower():
                        item.InvokeVerb("UNDELETE")
                        return f"'{original.name}' restored from the Recycle Bin."
        except Exception as e:
            print(f"[file] Recycle Bin restore failed: {e}")
    return (
        f"'{original.name}' is in the Recycle Bin — I could not pull it back "
        f"automatically, but it is there and can be restored by hand."
    )


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

    if not _SEND2TRASH:
        return (
            "send2trash is not installed. "
            "Run: pip install send2trash — "
            "Permanent deletion is disabled for safety."
        )
    send2trash.send2trash(str(target))
    return f"Moved to Trash: {target.name}"


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
    from core.file_safety import LOCK, checked

    try:
        with LOCK:
            if not isinstance(content, str) or len(content.encode("utf-8")) > _UNDO_CONTENT_LIMIT:
                return "Create rejected: text content must be at most 1 MB."
            base = _resolve_path(path)
            target = checked(base / name if name else base, _is_safe_path)
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("x", encoding="utf-8") as stream:
                stream.write(content)
            push_undo(f"created {target.name}", _undo_create(target))
            return f"File created: {target.name}"
    except Exception as error:
        return f"Could not create file (no overwrite): {error}"


def create_folder(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        already = target.exists()
        target.mkdir(parents=True, exist_ok=True)
        # Only offer to undo a folder we actually made. "mkdir -p" on something
        # that was already there is not a change, and undoing it would delete a
        # directory the user has had for years.
        if not already:
            push_undo(f"created folder {target.name}", _undo_create(target))
        return f"Folder created: {target.name}"
    except Exception as e:
        return f"Could not create folder: {e}"


def delete_file(path: str, name: str = "") -> str:
    try:
        base = _resolve_path(path)
        target = (base / name) if name else base
        if not _is_safe_path(target):
            return f"Access denied: {target}"
        if not target.exists():
            return f"Not found: {target.name}"

        # Safe-directory check — protect critical user folders
        protected = {
            _get_desktop(),
            _get_downloads(),
            _get_documents(),
            _get_pictures(),
            _get_music(),
            _get_videos(),
            Path.home(),
        }
        if target.resolve() in {p.resolve() for p in protected}:
            return f"Protected directory, cannot delete: {target.name}"

        original = target.resolve()
        result = _safe_trash(target)
        if result.startswith("Moved to Trash"):

            def restore() -> str:
                return _restore_from_trash(original)

            push_undo(f"deleted {original.name}", restore)
        return result

    except PermissionError:
        return f"Permission denied: {path}"
    except Exception as e:
        return f"Could not delete: {e}"


def _transfer_file(
    path: str, name: str, destination: str, *, copy: bool, dry_run: bool = False
) -> str:
    from core.file_safety import transfer

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
    from core.file_safety import LOCK, checked

    try:
        if not isinstance(content, str) or not isinstance(append, bool):
            return "Write rejected: content must be text and append must be boolean."
        encoded = content.encode("utf-8")
        if len(encoded) > _UNDO_CONTENT_LIMIT:
            return "Write rejected: input exceeds 1 MB safety limit."
        with LOCK:
            base = _resolve_path(path)
            target = checked(base / name if name else base, _is_safe_path)
            previous = None
            if target.exists():
                if not target.is_file() or target.stat().st_size > _UNDO_CONTENT_LIMIT:
                    return (
                        "Write rejected: existing file must be regular and at most 1 MB for undo."
                    )
                with target.open("rb") as stream:
                    previous = stream.read(_UNDO_CONTENT_LIMIT + 1)
                if len(previous) > _UNDO_CONTENT_LIMIT:
                    return "Write rejected: file grew beyond undo limit."
            result = (previous or b"") + encoded if append else encoded
            if len(result) > _UNDO_CONTENT_LIMIT:
                return "Write rejected: resulting file exceeds 1 MB safety limit."
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("wb" if previous is not None else "xb") as stream:
                stream.write(result)
            push_undo(f"wrote to {target.name}", _undo_write(target, previous))
            return f"Written to: {target.name}"
    except Exception as error:
        return f"Could not write file: {error}"


def find_files(
    name: str = "", extension: str = "", path: str = "home", max_results: int = 20
) -> str:
    """Compatibility entrypoint using the bounded read-only search engine."""
    from actions.file_search import file_search

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

    from core.file_safety import LOCK, checked, transfer

    if not isinstance(dry_run, bool):
        return "dry_run must be a boolean"
    journal, created, lines = [], [], []
    try:
        with LOCK:
            desktop = checked(_get_desktop(), _is_safe_path)
            if not desktop.is_dir():
                return "Desktop directory not found."
            # Bound directory enumeration and refuse rather than apply a hidden
            # partial plan. Each item is revalidated when executed.
            import itertools

            items = list(itertools.islice(desktop.iterdir(), 501))
            if len(items) > 500:
                return "Organization refused: more than 500 desktop entries."
            for item in sorted(items):
                if item.name.startswith(".") or item.is_symlink() or not item.is_file():
                    continue
                category = next(
                    (folder for folder, exts in type_map.items() if item.suffix.lower() in exts),
                    "Others",
                )
                folder = desktop / category
                destination = folder / item.name
                try:
                    checked(destination, _is_safe_path)
                    if os.path.lexists(destination):
                        lines.append(f"SKIPPED conflict: {destination}")
                        continue
                    if dry_run:
                        from core.file_safety import fingerprint

                        fingerprint(item)
                        lines.append(f"PLAN: {item} -> {destination}")
                        continue
                    if not folder.exists():
                        folder.mkdir()
                        created.append(folder)
                    message, undo = transfer(item, destination, copy=False, allowed=_is_safe_path)
                    journal.append(undo)
                    lines.append(message)
                except Exception as error:
                    lines.append(f"SKIPPED/FAILED {item.name}: {error}")
    except Exception as error:
        lines.append(f"Organization stopped: {error}")
    finally:
        if journal:

            def undo_batch():
                restored, conflicts = 0, 0
                for undo in reversed(journal):
                    try:
                        undo()
                        restored += 1
                    except Exception:
                        conflicts += 1
                for folder in reversed(created):
                    try:
                        checked(folder, _is_safe_path).rmdir()
                    except Exception:
                        pass
                return f"Restored {restored}; conflicts/unchanged {conflicts}."

            push_undo(f"organized desktop ({len(journal)} files)", undo_batch)
        elif not dry_run:
            for folder in reversed(created):
                try:
                    checked(folder, _is_safe_path).rmdir()
                except Exception:
                    pass
    heading = (
        "DRY RUN: no changes made; rerun with dry_run=false to apply a fresh plan."
        if dry_run
        else f"Organization finished: {len(journal)} moved (not atomic)."
    )
    return heading + "\n" + ("\n".join(lines) or "No eligible files.")


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
    """Bounded binary download; publish only complete content without overwrite."""
    from core import downloads
    from core.file_safety import LOCK
    from core.web_research import public_url

    try:
        url = public_url(url)
        if not isinstance(destination, str) or not destination.strip():
            return "Download rejected: destination must name an existing directory."
        # Fail invalid/conflicting paths before requesting any network data.
        target = downloads.target_path(url, _resolve_path(destination), name, _is_safe_path)
        payload = downloads.receive(url)
        with LOCK:
            warning = downloads.publish(target, payload.data, _is_safe_path)
            push_undo(f"downloaded {target.name}", _undo_create(target))
        return (
            f"Downloaded: {target} ({_format_size(len(payload.data))}). "
            f"Retrieved UTC: {payload.retrieved_at}. "
            "Saved only; not opened, executed, extracted or malware-scanned. "
            "Server Content-Disposition filenames are ignored." + warning
        )
    except Exception as error:
        # Only expose deliberate validation messages; low-level errors can
        # contain signed URLs, local network details or credentials.
        from core.web_research import WebError

        if isinstance(error, (downloads.DownloadError, WebError)):
            return f"Download refused/unavailable: {error}"
        return "Download failed safely: network, filesystem or path validation failure; check destination before retrying."


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
    "description": "File utilities. Move/copy/rename support regular files up to 64 MiB only, no overwrite, no symlinks, existing parent required; moves require same-volume hard-link support. dry_run previews supported for transfers and organize_desktop (organize defaults to preview). Undo refuses changed targets or occupied origins. Downloads: public HTTP(S), existing destination directory, 16 MiB/20-second caller limit, no overwrite, no server filename override. Other legacy operations have separate limitations.",
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
