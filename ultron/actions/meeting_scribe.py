"""
actions/meeting_scribe.py — Omniscient Meeting & Call Scribe ("Black Box Protocol") for Ultron AI.

Records meetings and voice calls in background threads, generates structured executive debriefs
(recording metadata only; no transcription), and archives WAV audio to ~/Documents/Ultron_Meetings/.
Auto-discovered by core/action_loader.py.
"""
from __future__ import annotations

import json
import os
import tempfile
import wave
from datetime import datetime
from pathlib import Path

from ultron.core.meeting_recording import Recorder, Recording

try:
    import sounddevice as sd
    _SD = True
except ImportError:
    _SD = False

_MEETINGS_DIR = Path.home() / "Documents" / "Ultron_Meetings"
_MEETINGS_LOG = _MEETINGS_DIR / "meetings_index.json"

_SAMPLE_RATE = 16000
_RECORDER = Recorder(sample_rate=_SAMPLE_RATE)
_MAX_INDEX_BYTES = 2 * 1024 * 1024


def _load_index() -> list:
    if not _MEETINGS_LOG.exists():
        return []
    with _MEETINGS_LOG.open("rb") as stream:
        raw = stream.read(_MAX_INDEX_BYTES + 1)
    if len(raw) > _MAX_INDEX_BYTES:
        raise ValueError("Meeting index too large.")
    records = json.loads(raw)
    if not isinstance(records, list):
        raise ValueError("Invalid meeting index.")
    return records


def _save_recording(session: Recording) -> str:
    """Write bounded chunks without concatenate; never overwrite an existing WAV."""
    clean_title = "".join(c for c in session.title if c.isalnum() or c in ("-", "_"))[:60] or "Meeting"
    filename = f"{clean_title}_{session.session_id}.wav"
    filepath = _MEETINGS_DIR / filename
    _MEETINGS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    # Exclusive creation also fails safely on an existing file or symlink.
    fd = os.open(filepath, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            with wave.open(stream, "wb") as output:
                output.setnchannels(1)
                output.setsampwidth(2)
                output.setframerate(_SAMPLE_RATE)
                for chunk in session.chunks:
                    output.writeframesraw(chunk.tobytes())
            size_bytes = stream.tell()
            stream.flush()
            os.fsync(stream.fileno())
    except Exception:
        filepath.unlink(missing_ok=True)  # only this call's exclusively created file
        raise

    elapsed = max(0, (session.ended_mono or session.started_mono) - session.started_mono)
    audio_seconds = session.samples / _SAMPLE_RATE
    filesize_mb = size_bytes / (1024 * 1024)
    brief = (
        f"MEETING RECORDING SAVED — {session.title}\n"
        f"Timestamp: {datetime.fromtimestamp(session.started_wall).isoformat()}\n"
        f"Session elapsed: {elapsed:.1f}s; captured audio: {audio_seconds:.3f}s\n"
        f"Audio File: {filename} ({filesize_mb:.2f} MB)\n"
        f"Storage Path: {filepath}\n"
        f"Input overflow reports: {session.overflows}. {session.reason}\n"
        "No transcription or content analysis was performed.\n"
        "Decisions, action items and speakers have not been identified.\n"
        "Saved locally. No Telegram notification sent."
    )
    temporary = None
    try:
        records = _load_index()
        records.append({"title": session.title, "filename": filename, "filepath": str(filepath),
                        "timestamp": datetime.fromtimestamp(session.started_wall).isoformat(),
                        "duration_sec": round(elapsed, 1), "audio_duration_sec": audio_seconds,
                        "size_mb": round(filesize_mb, 2), "summary": brief,
                        "capture_note": session.reason, "input_overflows": session.overflows})
        encoded = json.dumps(records, indent=2, ensure_ascii=True)
        if len(encoded.encode("utf-8")) > _MAX_INDEX_BYTES:
            raise ValueError("Meeting index full")
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=_MEETINGS_DIR,
                                         prefix=".meeting-index-", suffix=".tmp", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, _MEETINGS_LOG)
    except Exception:
        brief += "\nWarning: the archive index could not be updated; audio was saved but metadata sharing/listing may be unavailable."
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
    return brief


def start_recording(title: str = "Meeting") -> str:
    if not _SD:
        return "sounddevice library is not available for audio recording."
    try:
        _MEETINGS_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
    except OSError:
        return "[FAILED] Archive directory unavailable. No recording started."
    return _RECORDER.start(title, sd.InputStream)


def stop_recording() -> str:
    return _RECORDER.stop(_save_recording)


def recording_status() -> str:
    return _RECORDER.status()


def list_meetings() -> str:
    """List archived meeting recordings."""
    if not _MEETINGS_LOG.exists():
        return "No archived meeting recordings found in ~/Documents/Ultron_Meetings/."
    try:
        data = _load_index()
        if not data:
            return "No meetings logged yet."
        lines = [
            f"📁 ARCHIVED MEETING SESSIONS ({len(data)} total):",
            "─" * 55,
        ]
        for m in data[-6:]:
            lines.append(f"• {m['title']} | {m['timestamp'][:16]} | {m['duration_sec']}s | {m['size_mb']} MB")
            lines.append(f"    └─ File: {m['filename']}")
        lines.append("─" * 55)
        return "\n".join(lines)
    except Exception as e:
        return f"Failed to read meeting archive: {e}"


def share_meeting(filename: str, receiver: str) -> str:
    """Share selected stored metadata only, never the recording itself."""
    from ultron.core.report_sharing import request_telegram_share

    if (not isinstance(filename, str) or not filename
            or "/" in filename or "\\" in filename or "\x00" in filename):
        raise ValueError("Choose an exact recording filename from the meeting archive.")
    records = _load_index()
    matches = [record for record in records
               if isinstance(record, dict) and record.get("filename") == filename]
    if len(matches) != 1:
        raise ValueError("Recording missing or ambiguous; choose an exact unique filename.")
    # Older index entries have no trustworthy content summary. Do not reconstruct
    # the former invented decisions or read any filepath from the index.
    text = matches[0].get("summary")
    if not isinstance(text, str) or not text.strip():
        raise ValueError("No saved metadata summary for this older recording. Use send_message with explicitly selected text.")
    return request_telegram_share(receiver, text)


def meeting_scribe(parameters: dict, player=None, **kwargs) -> str:
    """Main entrypoint for meeting_scribe tool."""
    action = (parameters.get("action") or "status").lower().strip()
    title = parameters.get("title") or "Executive Meeting"

    if player:
        try:
            player.write_log(f"[Meeting Scribe] Action: {action} (Title: {title})")
        except Exception:
            pass

    try:
        if action in ("start", "record", "begin"):
            return start_recording(title=title)
        elif action in ("stop", "finish", "end", "conclude"):
            return stop_recording()
        elif action == "share":
            return share_meeting(parameters.get("filename", ""), parameters.get("receiver", ""))
        elif action in ("status", "check"):
            return recording_status()
        elif action in ("list", "history", "archive", "recordings"):
            return list_meetings()
        else:
            return (
                f"Unknown scribe action '{action}'. "
                "Available actions: start, stop, status, list, share."
            )
    except ValueError as error:
        return f"Meeting request rejected: {error}"
    except Exception:
        return "Meeting operation failed. Check local archive/outbox status before retrying."


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "meeting_scribe",
    "description": (
        "Omniscient Meeting & Call Scribe ('Black Box Protocol') for Ultron. "
        "Requests bounded default-input audio recording in a background thread (start; check status for readiness). "
        "Capture is limited to 15 minutes/32 MiB PCM with bounded chunks; native driver shutdown may remain pending. "
        "An unsaved/stopping session blocks new starts; stop saves limit-ended or failed partial captures. "
        "stops recording and saves WAV audio with recording metadata to ~/Documents/Ultron_Meetings/, "
        "with no transcription or inferred decisions and no automatic external sends (stop). "
        "share requests HUD approval to send saved metadata (not audio) to an explicit numeric Telegram receiver. "
        "checks active recording status (status), and lists past archived sessions (list). "
        "Use for recording audio, not for transcription or extracting meeting decisions."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "start (begin recording audio session) | stop (save audio and recording metadata; no transcription) | share (filename and receiver; HUD approval required) | status (check if recording is active) | list (view archived recordings)"
            },
            "filename": {"type": "STRING", "description": "Exact recording filename from list, required for share."},
            "receiver": {"type": "STRING", "description": "Explicit numeric Telegram chat ID, required for share."},
            "title": {
                "type": "STRING",
                "description": "Optional title for the meeting session (e.g. 'Client Strategy Sync', 'Architecture Review'). Default: 'Meeting'"
            }
        },
        "required": [
            "action"
        ]
    },
    "handler": meeting_scribe,
}
