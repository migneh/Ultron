"""Optional local wake detector with operator-configurable ONNX model.

The default remains hey_jarvis (spoken 'hey jarvis'), not 'hey ultron'. Changing
text cannot train a phrase; custom phrases require a trusted compatible model.
No dependencies imported or models downloaded until explicitly requested.
"""
from __future__ import annotations

import math
import queue
import re
import subprocess
import sys
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

# Backward-compatible default; the configured selection never mutates this constant.
WAKE_MODEL = "hey_jarvis"
BUILTIN_MODELS = ("hey_jarvis", "alexa", "hey_mycroft", "timer", "weather")


@dataclass(frozen=True)
class WakeSettings:
    model: str = WAKE_MODEL
    threshold: float = 0.5
    label: str = "hey jarvis"

    @property
    def score_key(self):
        return Path(self.model).stem


def settings(config=None) -> WakeSettings:
    if config is None:
        from ultron.memory.config_manager import load_api_keys
        config = load_api_keys()
    if not isinstance(config, dict):
        raise ValueError("Wake configuration must be an object")
    model = config.get("wake_word_model", WAKE_MODEL)
    if not isinstance(model, str) or not model or len(model) > 4096:
        raise ValueError("Invalid wake model")
    if model not in BUILTIN_MODELS:
        path = Path(model).expanduser()
        if not path.is_absolute() or path.suffix.lower() != ".onnx" or not path.is_file():
            raise ValueError("Choose a supported builtin or an existing absolute trusted .onnx file")
        model = str(path.resolve())
    threshold = config.get("wake_word_threshold", 0.5)
    if type(threshold) not in (int, float) or not 0 < threshold <= 1 or not math.isfinite(threshold):
        raise ValueError("Wake threshold must be finite, greater than 0 and at most 1")
    label = config.get("wake_word_label", model.replace("_", " ") if model in BUILTIN_MODELS else "custom wake phrase")
    if not isinstance(label, str) or not 1 <= len(label) <= 80 or any(not c.isprintable() for c in label):
        raise ValueError("Invalid wake label")
    return WakeSettings(model, float(threshold), label)


def configured_label() -> str:
    try:
        return settings().label
    except ValueError:
        return "configured wake phrase (invalid settings; use WAKE NOW)"


def _model_file(models_dir, model):
    if model not in BUILTIN_MODELS:
        return Path(model).is_file()
    return any(path.stem == model or re.fullmatch(re.escape(model) + r"_v[0-9.]+", path.stem)
               for path in models_dir.glob("*.onnx"))


# Score in [0,1]; above this counts as a detection. Tunable per environment.
DEFAULT_THRESHOLD = 0.5
# Mic frames arrive at 16 kHz int16; this is just the detector's input rate.
SAMPLE_RATE = 16000


def is_installed() -> bool:
    """True if the openwakeword package is importable (no model check)."""
    try:
        import importlib.util
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def is_ready(selection: WakeSettings | None = None) -> bool:
    """True if openwakeword is installed AND its model files are present on disk.

    This is a cheap, DETERMINISTIC file-existence check. It deliberately does NOT
    construct a Model to probe readiness — doing that is slow and, worse, can clash
    with the detector's own Model when it's already running, which intermittently
    returned False and made the UI flicker to 'not downloaded'. Never raises.
    """
    if not is_installed():
        return False
    try:
        selected = selection or settings()
        import openwakeword
        models_dir = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        if not models_dir.is_dir():
            return False
        has_wake = _model_file(models_dir, selected.model)
        has_mel = any(models_dir.glob("melspectrogram*.onnx"))
        has_emb = any(models_dir.glob("embedding_model*.onnx"))
        return bool(has_wake and has_mel and has_emb)
    except Exception:
        return False


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """
    One-click setup for the UI button: pip-install openwakeword if missing, then
    download the wake model. Returns (ok, message). Never raises — every failure
    is reported through the returned message and the logger.
    """
    _tell = notify or (lambda _msg: None)
    try:
        selected = settings()  # validate before installing/downloading anything
        if selected.model not in BUILTIN_MODELS:
            if is_ready(selected):
                return True, "Custom model and ONNX feature files present; load/inference not yet verified."
            return False, "Custom wake models require manually provisioned openwakeword and ONNX feature models; no automatic download attempted."
        if not is_installed():
            logger("Wake word: installing openwakeword (one-time)…")
            _tell("Wake word: installing openwakeword (one-time)…")
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "openwakeword"],
                capture_output=True, text=True,
            )
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install failed: {tail[0][:160]}"
        # Download the pretrained melspectrogram/embedding + wake models.
        logger("Wake word: downloading models…")
        _tell("Wake word: downloading models…")
        try:
            import openwakeword.utils as _u
            # No older-signature/all-model fallback.
            _u.download_models([selected.model])
        except Exception as e:
            return False, f"model download failed: {e}"

        if not is_ready(selected):
            return False, "installed, but the wake model could not be loaded."
        logger("Wake word: ready.")
        return True, "Wake word installed and ready."
    except Exception as e:
        return False, f"setup error: {e}"


class WakeWordDetector:
    """
    Runs the wake model in a dedicated thread. The mic thread calls feed() with
    raw int16 frames; detections invoke on_detect() (called from this thread —
    the callback must marshal to whatever loop/UI it needs).
    """

    def __init__(self, on_detect: Callable[[], None],
                 threshold: float | None = None,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None,
                 selection: WakeSettings | None = None):
        selected = selection or settings()
        # Validate explicit selections too; no bypass through direct construction.
        self.selection = settings({"wake_word_model": selected.model,
                                   "wake_word_threshold": selected.threshold if threshold is None else threshold,
                                   "wake_word_label": selected.label})
        self._on_detect = on_detect
        self._threshold = self.selection.threshold
        self._logger    = logger
        # See PluginRegistry: `logger` is the console and gets everything,
        # `notify` is the activity log and gets only what the user must act on.
        self._notify    = notify or (lambda _msg: None)
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._running = False
        self._model = None
        self._ready = False
        self._lifecycle = threading.RLock()
        self._stop_event = threading.Event()

    def start(self) -> bool:
        """Start one generation only; refuse while a prior worker is stopping."""
        with self._lifecycle:
            if self._thread is not None and self._thread.is_alive():
                return self._running and not self._stop_event.is_set()
            try:
                from openwakeword.model import Model
                model = Model(wakeword_models=[self.selection.model], inference_framework="onnx")
                frames = queue.Queue(maxsize=50)
                stop = threading.Event()
                self._queue, self._stop_event, self._model = frames, stop, model
                self._running, self._ready = True, True
                self._thread = threading.Thread(target=self._loop, args=(model, frames, stop),
                                                daemon=True, name="WakeWordThread")
                self._thread.start()
            except Exception:
                self._running, self._ready, self._model = False, False, None
                self._stop_event.set()
                self._logger("Wake word: model/thread startup failed; use WAKE NOW.")
                self._notify("Wake word unavailable — use the WAKE NOW button.")
                return False
        self._logger(f"Wake word: listening for '{self.selection.label}'.")
        return True

    def stop(self) -> bool:
        """Request stop and join for at most 0.5s; blocked native inference may remain.

        A still-live worker retains its model/generation and prevents restart.
        Never join ourselves when stop was called from an on_detect callback.
        """
        with self._lifecycle:
            self._running, self._ready = False, False
            self._stop_event.set()
            worker = self._thread
            try:
                self._queue.put_nowait(None)
            except queue.Full:
                pass
        if worker is not None and worker is not threading.current_thread():
            worker.join(timeout=.5)
        with self._lifecycle:
            stopped = worker is None or not worker.is_alive()
            if stopped and self._thread is worker:
                self._model = None
            return stopped

    @property
    def ready(self) -> bool:
        return self._ready

    def feed(self, frame_int16) -> None:
        """Called from the mic callback (real-time thread). Must stay cheap and
        never block — the frame is copied and dropped if the queue is backed up."""
        if not self._running:
            return
        try:
            # frame_int16 is a numpy int16 array (possibly 2-D mono) — flatten to 1-D
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            self._queue.put_nowait(data)
        except queue.Full:
            pass
        except Exception:
            pass

    def _loop(self, model=None, frames=None, stop=None) -> None:
        # Each worker retains its own model/queue/event, never a restarted one's.
        model = self._model if model is None else model
        frames = self._queue if frames is None else frames
        stop = self._stop_event if stop is None else stop
        try:
            import numpy as np
            while self._running and not stop.is_set():
                try:
                    frame = frames.get()
                    if frame is None or stop.is_set():
                        break
                    scores = model.predict(np.asarray(frame, dtype=np.int16))
                    if stop.is_set():
                        break  # stopped during native inference: do not wake afterwards
                    score = 0.0
                    if isinstance(scores, dict):
                        key = self.selection.score_key
                        for name, value in scores.items():
                            if not isinstance(name, str) or not (name == key or re.fullmatch(re.escape(key) + r"_v[0-9.]+", name)):
                                continue
                            try:
                                candidate = float(value)
                            except (TypeError, ValueError, OverflowError):
                                continue
                            if math.isfinite(candidate) and 0 <= candidate <= 1:
                                score = max(score, candidate)
                    if score >= self._threshold:
                        while True:
                            try:
                                frames.get_nowait()
                            except queue.Empty:
                                break
                        if not stop.is_set():
                            self._on_detect()
                except Exception:
                    self._logger("Wake word: inference/callback failed; no detection confirmed.")
        finally:
            with self._lifecycle:
                if self._stop_event is stop:
                    self._running, self._ready, self._model = False, False, None

    def _drain(self) -> None:
        try:
            while True:
                self._queue.get_nowait()
        except Exception:
            pass
