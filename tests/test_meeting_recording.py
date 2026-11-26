"""Fake PCM streams only: no microphone, native capture or external services."""
import json
import threading
import wave
from types import SimpleNamespace

import numpy as np
import pytest

from ultron.actions import meeting_scribe as action
from ultron.core import meeting_recording as capture


class Stream:
    def __init__(self, read):
        self.read = read

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def pcm(n):
    return np.zeros((n, 1), dtype=np.int16)


def ready(recorder):
    worker = recorder._session.worker
    worker.join(2)
    assert not worker.is_alive(), "Fake worker failed to exit"
    return recorder._session


def recorder(**kwargs):
    return capture.Recorder(sample_rate=8, max_seconds=10, max_bytes=16,
                            block_frames=4, join_timeout=0.01, **kwargs)


def test_exact_byte_sample_and_chunk_limits():
    rec = capture.Recorder(sample_rate=8, max_seconds=10, max_bytes=10, block_frames=4)
    reads = []
    assert "STARTING" in rec.start("Test", lambda **_: Stream(lambda n: (reads.append(n) or pcm(n), False)))
    session = ready(rec)
    assert session.samples == 5 and session.bytes_used == 10
    assert len(session.chunks) == 2 and len(reads) == 2
    assert "limit" in session.reason
    assert "READY" in rec.status()
    assert "BUSY" in rec.start("Other", lambda **_: pytest.fail("Must not open"))
    saved = []
    assert rec.stop(lambda s: saved.append(s.samples) or "saved") == "saved"
    assert saved == [5] and "IDLE" in rec.status()


def test_tiny_driver_reads_cannot_create_unbounded_array_objects():
    rec = capture.Recorder(sample_rate=8, max_seconds=10, max_bytes=32, block_frames=4)
    rec.start("Tiny", lambda **_: Stream(lambda _: (pcm(1), False)))
    session = ready(rec)
    assert len(session.chunks) == rec.max_chunks == 4
    assert session.samples == 4


def test_blocked_read_retains_session_and_rejects_late_frame():
    rec = capture.Recorder(sample_rate=8, max_seconds=100, max_bytes=64,
                           block_frames=4, join_timeout=0.01)
    blocked, release = threading.Event(), threading.Event()
    calls = []

    def read(n):
        calls.append(n)
        if len(calls) == 2:
            blocked.set()
            assert release.wait(2)
        return pcm(n), False

    rec.start("First", lambda **_: Stream(read))
    try:
        assert blocked.wait(2)
        assert "STOPPING" in rec.stop(lambda _: pytest.fail("Cannot save live worker"))
        assert "BUSY" in rec.start("Second", lambda **_: pytest.fail("Must not overlap"))
        assert rec._session.samples == 4
    finally:
        release.set()
    session = ready(rec)
    assert session.samples == 4  # data returned after stop was not appended
    assert rec.stop(lambda s: f"saved:{s.samples}") == "saved:4"


def test_blocked_stream_open_is_not_misreported_as_recording_or_cancelled():
    rec = recorder()
    opening, release = threading.Event(), threading.Event()

    class SlowOpen(Stream):
        def __enter__(self):
            opening.set()
            assert release.wait(2)
            return self

    rec.start("Opening", lambda **_: SlowOpen(lambda _: pytest.fail("No read after stop")))
    try:
        assert opening.wait(2)
        assert "STARTING" in rec.status()
        assert "STOPPING" in rec.stop(lambda _: pytest.fail("No data"))
        assert "BUSY" in rec.start("Other", lambda **_: None)
    finally:
        release.set()
    ready(rec)
    assert "NO_AUDIO" in rec.stop(lambda _: pytest.fail("No data"))


def test_driver_open_failure_is_visible_and_sanitized():
    rec = recorder()

    def fail(**_):
        raise RuntimeError("SECRET device path")

    rec.start("Failure", fail)
    ready(rec)
    assert "Audio input failed" in rec.status()
    assert "SECRET" not in rec.status()
    assert "NO_AUDIO" in rec.stop(lambda _: pytest.fail("Nothing to save"))
    assert "IDLE" in rec.status()


def test_driver_failure_preserves_partial_audio_and_overflow_warning():
    rec = recorder()
    calls = []

    def read(n):
        if calls:
            raise RuntimeError("SECRET")
        calls.append(n)
        return pcm(n), True

    rec.start("Partial", lambda **_: Stream(read))
    session = ready(rec)
    assert session.samples == 4 and session.overflows == 1
    assert "failed" in session.reason
    assert rec.stop(lambda s: f"partial:{s.samples}") == "partial:4"


@pytest.mark.parametrize("data", [np.zeros((4, 1), dtype=np.float32), pcm(0), pcm(5),
                                  np.zeros((4, 2), dtype=np.int16), [1, 2]])
def test_invalid_driver_data_is_rejected(data):
    rec = recorder()
    rec.start("Invalid", lambda **_: Stream(lambda _: (data, False)))
    assert ready(rec).samples == 0
    assert "invalid or empty" in rec.status()


def test_duration_deadline_checks_after_read(monkeypatch):
    rec = recorder()

    def read(n):
        rec._session.started_mono -= 100
        return pcm(n), False

    rec.start("Deadline", lambda **_: Stream(read))
    session = ready(rec)
    assert session.samples == 0 and "duration limit" in session.reason


def test_save_failure_retains_buffer_for_explicit_retry():
    rec = recorder()
    rec.start("Retry", lambda **_: Stream(lambda n: (pcm(n), False)))
    session = ready(rec)

    def fail(_):
        raise OSError("SECRET disk details")

    result = rec.stop(fail)
    assert "SAVE_FAILED" in result and "SECRET" not in result
    assert rec._session is session and session.samples == 8
    assert "BUSY" in rec.start("Other", lambda **_: None)
    assert rec.stop(lambda s: "saved") == "saved"


def test_concurrent_stop_only_saves_once_and_blocks_new_start():
    rec = recorder()
    rec.start("Concurrent", lambda **_: Stream(lambda n: (pcm(n), False)))
    ready(rec)
    saving, release = threading.Event(), threading.Event()
    writes = []

    def save(_):
        writes.append(True)
        saving.set()
        assert release.wait(2)
        return "saved"

    worker = threading.Thread(target=lambda: rec.stop(save))
    worker.start()
    try:
        assert saving.wait(2)
        assert "SAVING" in rec.stop(save)
        assert "BUSY" in rec.start("Other", lambda **_: None)
    finally:
        release.set()
        worker.join(2)
    assert writes == [True] and "IDLE" in rec.status()


def test_thread_start_failure_does_not_leave_busy_state(monkeypatch):
    rec = recorder()

    class BrokenThread:
        def __init__(self, **_):
            pass

        def start(self):
            raise RuntimeError("SECRET")

    monkeypatch.setattr(capture.threading, "Thread", BrokenThread)
    assert "FAILED" in rec.start("Test", lambda **_: None)
    assert "IDLE" in rec.status()


@pytest.mark.parametrize("title", [None, {}, "", " ", "line\nbreak", "x" * 201])
def test_invalid_title_does_not_start(title):
    rec = recorder()
    assert "REJECTED" in rec.start(title, lambda **_: pytest.fail("Must not open"))
    assert "IDLE" in rec.status()


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(action, "_MEETINGS_DIR", tmp_path)
    monkeypatch.setattr(action, "_MEETINGS_LOG", tmp_path / "meetings_index.json")
    session = capture.Recording("Test")
    session.chunks = [pcm(4), pcm(2)]
    session.samples, session.bytes_used = 6, 12
    session.ended_mono = session.started_mono + 10
    return SimpleNamespace(root=tmp_path, session=session)


def test_archive_writes_chunks_and_exact_wav_duration(archive, monkeypatch):
    monkeypatch.setattr(np, "concatenate", lambda *a, **k: pytest.fail("No second full audio allocation"))
    result = action._save_recording(archive.session)
    records = json.loads(action._MEETINGS_LOG.read_text())
    assert "Session elapsed: 10.0s" in result
    assert records[0]["audio_duration_sec"] == 6 / 16000
    with wave.open(str(archive.root / records[0]["filename"]), "rb") as wav:
        assert wav.getnframes() == 6 and wav.getnchannels() == 1 and wav.getsampwidth() == 2
    assert not list(archive.root.glob("*.tmp"))


def test_existing_wav_is_never_overwritten(archive):
    path = archive.root / f"Test_{archive.session.session_id}.wav"
    path.write_bytes(b"existing")
    with pytest.raises(FileExistsError):
        action._save_recording(archive.session)
    assert path.read_bytes() == b"existing"


def test_corrupt_index_is_preserved_while_audio_save_warns(archive):
    action._MEETINGS_LOG.write_text("not-json")
    result = action._save_recording(archive.session)
    assert "Warning" in result and "audio was saved" in result
    assert action._MEETINGS_LOG.read_text() == "not-json"
    assert len(list(archive.root.glob("*.wav"))) == 1


def test_partial_wav_is_removed_on_write_failure_and_buffer_retained(archive, monkeypatch):
    rec = recorder()
    rec._session = archive.session

    def fail(*_):
        raise OSError("SECRET")

    monkeypatch.setattr(action.wave.Wave_write, "writeframesraw", fail)
    assert "SAVE_FAILED" in rec.stop(action._save_recording)
    assert rec._session is archive.session and archive.session.samples == 6
    assert not list(archive.root.glob("*.wav"))


def test_blocked_native_close_does_not_release_session_early():
    rec = recorder()
    closing, release = threading.Event(), threading.Event()

    class SlowClose(Stream):
        def __exit__(self, *_):
            closing.set()
            assert release.wait(2)
            return False

    rec.start("Close", lambda **_: SlowClose(lambda n: (pcm(n), False)))
    try:
        assert closing.wait(2)
        assert "STOPPING" in rec.stop(lambda _: pytest.fail("Worker still closing"))
        assert "BUSY" in rec.start("Other", lambda **_: None)
    finally:
        release.set()
    ready(rec)
    assert rec.stop(lambda _: "saved") == "saved"


def test_unique_session_filenames_and_atomic_index_append(archive):
    action._save_recording(archive.session)
    second = capture.Recording("Test")
    second.chunks = [pcm(2)]
    second.samples, second.bytes_used = 2, 4
    second.ended_mono = second.started_mono + 1
    action._save_recording(second)
    records = json.loads(action._MEETINGS_LOG.read_text())
    assert len(records) == 2 and records[0]["filename"] != records[1]["filename"]
    assert len(list(archive.root.glob("*.wav"))) == 2
    assert not list(archive.root.glob("*.tmp"))


def test_atomic_index_failure_preserves_original_and_saved_audio(archive, monkeypatch):
    original = '[{"filename": "old.wav"}]'
    action._MEETINGS_LOG.write_text(original)

    def fail(*_):
        raise OSError("Cannot replace index")

    monkeypatch.setattr(action.os, "replace", fail)
    assert "Warning" in action._save_recording(archive.session)
    assert action._MEETINGS_LOG.read_text() == original
    assert len(list(archive.root.glob("*.wav"))) == 1
    assert not list(archive.root.glob("*.tmp"))


def test_archive_unavailable_prevents_microphone_request(tmp_path, monkeypatch):
    occupied = tmp_path / "not-a-directory"
    occupied.write_text("existing")
    monkeypatch.setattr(action, "_SD", True)
    monkeypatch.setattr(action, "_MEETINGS_DIR", occupied)
    monkeypatch.setattr(action, "sd", SimpleNamespace(InputStream=lambda **_: pytest.fail("No microphone")), raising=False)
    assert "No recording started" in action.start_recording("Test")
