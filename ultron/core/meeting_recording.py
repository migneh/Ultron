"""Bounded single-session audio capture; no microphone is opened at import time.

Native stream open/read/close may block. A join timeout is NOT cancellation:
keep that session owned and reject replacement until its worker actually exits.
Audio stays in memory until explicit stop/save; it is not crash-durable.
"""
from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from typing import Callable
from uuid import uuid4

import numpy as np


@dataclass
class Recording:
    title: str
    session_id: str = field(default_factory=lambda: uuid4().hex)
    started_wall: float = field(default_factory=time.time)
    started_mono: float = field(default_factory=time.monotonic)
    ended_mono: float | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    chunks: list[np.ndarray] = field(default_factory=list)
    samples: int = 0
    bytes_used: int = 0
    overflows: int = 0
    reason: str = ""
    state: str = "STARTING"
    worker: threading.Thread | None = None
    saving: bool = False


class Recorder:
    def __init__(self, *, sample_rate=16000, max_seconds=900, max_bytes=32 * 1024 * 1024,
                 block_frames=1024, join_timeout=2.0):
        if min(sample_rate, max_seconds, max_bytes, block_frames) <= 0 or join_timeout < 0:
            raise ValueError("Invalid recorder limits")
        self.sample_rate = sample_rate
        self.max_seconds = max_seconds
        self.max_bytes = max_bytes
        self.block_frames = block_frames
        self.join_timeout = join_timeout
        self.max_samples = min(int(sample_rate * max_seconds), max_bytes // 2)
        if self.max_samples < 1:
            raise ValueError("Recorder budget too small")
        # Bound Python/NumPy object overhead even if a driver returns tiny reads.
        self.max_chunks = math.ceil(self.max_samples / block_frames)
        self._lock = threading.Lock()
        self._session: Recording | None = None

    def start(self, title: str, stream_factory: Callable) -> str:
        if not isinstance(title, str) or not title.strip() or len(title) > 200 or any(ord(c) < 32 for c in title):
            return "[REJECTED] Recording title must be 1–200 characters without control characters."
        with self._lock:
            if self._session is not None:
                return "[BUSY] A recording is active, stopping, or awaiting save. Use status/stop first."
            session = Recording(title.strip())
            self._session = session
            try:
                session.worker = threading.Thread(target=self._capture, args=(session, stream_factory),
                                                  daemon=True, name=f"meeting-{session.session_id[:8]}")
                session.worker.start()
            except Exception:
                self._session = None
                return "[FAILED] Could not start the recording worker. No audio captured."
        return (f"[STARTING] Recording requested for '{session.title}'. Check status for input readiness. "
                f"Default audio input only, not guaranteed system/call audio. "
                f"Limits: {self.max_seconds}s, {self.max_bytes} PCM bytes, {self.max_chunks} chunks. "
                "Use stop to finish and save locally; no automatic sharing.")

    def _capture(self, session: Recording, stream_factory: Callable) -> None:
        try:
            # A stop received before open should not acquire a microphone.
            if session.stop_event.is_set():
                return
            with stream_factory(samplerate=self.sample_rate, channels=1, dtype="int16") as stream:
                with self._lock:
                    session.state = "RECORDING" if not session.stop_event.is_set() else "STOPPING"
                while not session.stop_event.is_set():
                    if time.monotonic() - session.started_mono >= self.max_seconds:
                        session.reason = "Capture duration limit reached."
                        break
                    data, overflowed = stream.read(self.block_frames)
                    # Stop may have been requested during a blocking native read.
                    if session.stop_event.is_set():
                        break
                    if time.monotonic() - session.started_mono >= self.max_seconds:
                        session.reason = "Capture duration limit reached."
                        break
                    if (not isinstance(data, np.ndarray) or data.dtype != np.int16
                            or data.ndim != 2 or data.shape[1] != 1
                            or not 0 < len(data) <= self.block_frames):
                        session.reason = "Audio input returned invalid or empty PCM data."
                        break
                    with self._lock:
                        remaining = self.max_samples - session.samples
                        if remaining <= 0 or len(session.chunks) >= self.max_chunks:
                            session.reason = "Audio buffer limit reached."
                            break
                        chunk = data[:remaining].copy()
                        session.chunks.append(chunk)
                        session.samples += len(chunk)
                        session.bytes_used += chunk.nbytes
                        session.overflows += int(bool(overflowed))
                        if session.samples >= self.max_samples or len(session.chunks) >= self.max_chunks:
                            session.reason = "Audio buffer limit reached."
                            break
        except Exception:
            # Driver exceptions can contain device paths/user data. Retain only
            # a safe reason and preserve any captured audio for explicit save.
            session.reason = "Audio input failed; capture may be incomplete."
        finally:
            with self._lock:
                session.ended_mono = time.monotonic()
                session.state = "READY"
                session.stop_event.set()

    def stop(self, save: Callable[[Recording], str]) -> str:
        with self._lock:
            session = self._session
            if session is None:
                return "[IDLE] No recording awaiting stop/save."
            if session.saving:
                return "[SAVING] Audio save is already in progress."
            session.stop_event.set()
            worker = session.worker
            if worker and worker.is_alive():
                session.state = "STOPPING"
        # Never join under the lock needed by the worker's finally block.
        if worker and worker.is_alive():
            worker.join(timeout=self.join_timeout)
        with self._lock:
            if worker and worker.is_alive():
                return "[STOPPING] Audio driver has not exited. Nothing saved yet; new sessions remain blocked. Use status/stop again."
            if self._session is not session:
                return "[IDLE] Recording was already finalized."
            if session.saving:
                return "[SAVING] Audio save is already in progress."
            if not session.chunks:
                self._session = None
                return "[NO_AUDIO] No audio captured. " + session.reason
            session.saving = True
            session.state = "SAVING"
        try:
            result = save(session)
        except Exception:
            with self._lock:
                session.saving = False
                session.state = "SAVE_FAILED"
            return "[SAVE_FAILED] Could not archive audio. Captured buffer retained in memory; retry stop. New sessions remain blocked."
        with self._lock:
            self._session = None
        return result

    def status(self) -> str:
        with self._lock:
            session = self._session
            if session is None:
                return "[IDLE] No active or unsaved recording."
            elapsed = max(0, (session.ended_mono or time.monotonic()) - session.started_mono)
            return (f"[{session.state}] {session.title}\n"
                    f"Session elapsed: {elapsed:.1f}s; captured audio: {session.samples / self.sample_rate:.3f}s\n"
                    f"Buffered: {session.samples} samples, {session.bytes_used}/{self.max_bytes} PCM bytes, "
                    f"{len(session.chunks)}/{self.max_chunks} chunks\n"
                    f"Input overflow reports: {session.overflows}. {session.reason}\n"
                    "READY/SAVE_FAILED audio needs stop to save. No transcription or automatic sharing.")
