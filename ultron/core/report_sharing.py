"""Explicit text-only report sharing through the verified message outbox.

No configured/default recipient, automatic sends, file attachments, truncation or
legacy Telegram transport. Reading a report is not authorization to transmit it.
"""
import os
import stat
from pathlib import Path

MAX_REPORT_BYTES = 16000


def read_report(root: Path, filename: str) -> str:
    """Read one exact, bounded markdown report; never fuzzy-match or follow links."""
    if (not isinstance(filename, str) or not filename or filename in {".", ".."}
            or "/" in filename or "\\" in filename or "\x00" in filename
            or Path(filename).suffix.lower() != ".md"):
        raise ValueError("Choose an exact .md report filename from the archive.")
    root = Path(root).resolve()
    path = root / filename
    if path.is_symlink() or path.resolve().parent != root or not path.is_file():
        raise ValueError("Report not found or is not a regular local archive file.")
    # Bounded read even if the file grows between the metadata check and open.
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    try:
        fd = os.open(path, flags)
    except OSError:
        raise ValueError("Report could not be opened safely.") from None
    with os.fdopen(fd, "rb") as stream:
        if not stat.S_ISREG(os.fstat(stream.fileno()).st_mode):
            raise ValueError("Report must be a regular file.")
        raw = stream.read(MAX_REPORT_BYTES + 1)
    if len(raw) > MAX_REPORT_BYTES:
        raise ValueError("Report too large to share as one message. Select an explicit excerpt with send_message; no truncation or splitting was performed.")
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        raise ValueError("Report is not valid UTF-8 text.") from None


def request_telegram_share(receiver: str, text: str) -> str:
    """Delegate exact recipient/text preview and execution to the existing outbox."""
    from ultron.actions.send_message import send_message
    from ultron.core.messaging import recipient_id

    receiver = recipient_id(receiver)  # fail before transport/identity lookup
    if not isinstance(text, str) or not text.strip() or "\x00" in text:
        raise ValueError("Sharing requires non-empty text without NUL bytes.")
    try:
        size = len(text.encode("utf-16-le")) // 2
    except UnicodeEncodeError:
        raise ValueError("Report contains invalid Unicode.") from None
    if size > 4000:
        raise ValueError("Report exceeds 4000 UTF-16 units. Select an explicit excerpt with send_message; nothing was truncated or split.")
    return send_message({"action": "send", "platform": "telegram",
                         "receiver": receiver, "message_text": text})
