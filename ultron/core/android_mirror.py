"""Owned, finite, view-only scrcpy sessions. Not recording or a process sandbox.

Native --time-limit complements the host watchdog. Crash cleanup/native option
support is not certified; never kill arbitrary PIDs or an unrelated scrcpy.
"""
from __future__ import annotations

import json
import os
import subprocess
import threading
from pathlib import Path
from uuid import uuid4

from ultron.core import android_files, file_safety
from ultron.core import operation_policy as policy
from ultron.core.background_jobs import OwnerLock


def _scrcpy_snapshot():
    path = Path(android_files._bridge()._find_binary("scrcpy"))
    if not path.is_absolute():
        raise ValueError("scrcpy unavailable")
    file_safety.checked(path, lambda _: True)
    return {"path": str(path), "identity": list(file_safety.fingerprint(path))}


class MirrorService:
    def __init__(self):
        self.lock = threading.RLock()
        self.current = None
        self.last = None
        self.closed = False
        self.owner = None

    def _reap(self):
        if self.current and self.current["process"].poll() is not None:
            self.last = {"mirror_id": self.current["id"], "state": "process_exited"}
            self.current = None
            self.owner.release()
            self.owner = None

    def launch(self, payload):
        with self.lock:
            self._reap()
            if self.closed or self.current:
                return {"state": "unavailable_or_busy", "started": False}
            path = Path.home() / ".ultron" / "android-mirror.owner.lock"
            file_safety.checked(path, lambda _: True)
            path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            owner = OwnerLock(path)
            if not owner.acquire():
                return {"state": "another_runtime_owns_mirror", "started": False}
            self.owner = owner
            mirror_id = uuid4().hex
            command = [payload["scrcpy"]["path"], "--serial=" + payload["device"]["serial"],
                       "--no-control", "--no-audio", "--no-clipboard-autosync", "--no-power-on",
                       "--max-size=1280", "--max-fps=30", "--window-title=Ultron view-only Android mirror",
                       "--time-limit=" + str(payload["seconds"])]
            # Do not inherit a remote ADB server or choose a different binary.
            env = {**os.environ, "ADB": payload["device"]["binary"],
                   "ADB_SERVER_SOCKET": "tcp:127.0.0.1:5037", "ANDROID_SERIAL": payload["device"]["serial"]}
            try:
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env)
            except Exception:
                owner.release()
                self.owner = None
                return {"state": "launch_failed", "started": False}
            self.current = {"id": mirror_id, "process": process, "seconds": payload["seconds"]}
            try:
                threading.Thread(target=self._watch, args=(mirror_id, process, payload["seconds"]),
                                 daemon=True, name="android-mirror-watchdog").start()
            except Exception:
                self._stop_owned(mirror_id)
                return {"state": "watchdog_failed_stop_attempted", "started": True, "mirror_id": mirror_id}
            return {"state": "process_started_display_not_verified", "started": True,
                    "mirror_id": mirror_id, "requested_maximum_seconds": payload["seconds"]}

    def _watch(self, mirror_id, process, seconds):
        try:
            process.wait(timeout=seconds)
        except Exception:
            self._stop_owned(mirror_id)
        finally:
            with self.lock:
                self._reap()

    def _stop_owned(self, mirror_id):
        with self.lock:
            self._reap()
            if not self.current or self.current["id"] != mirror_id:
                return {"state": "no_matching_owned_session"}
            process = self.current["process"]
            try:
                process.terminate()
                process.wait(timeout=2)
            except Exception:
                try:
                    process.kill()
                    process.wait(timeout=1)
                except Exception:
                    pass
            self._reap()
            return {"state": "stop_uncertain_slot_retained" if self.current else "process_exit_observed"}

    def stop(self, mirror_id):
        if not isinstance(mirror_id, str) or len(mirror_id) != 32 or any(c not in "0123456789abcdef" for c in mirror_id):
            return {"state": "invalid_mirror_id"}
        return self._stop_owned(mirror_id)

    def status(self):
        with self.lock:
            self._reap()
            if self.current:
                return {"state": "owned_process_alive_display_not_verified", "mirror_id": self.current["id"],
                        "requested_maximum_seconds": self.current["seconds"]}
            return self.last or {"state": "no_owned_session"}

    def shutdown(self):
        with self.lock:
            self.closed = True
            return self._stop_owned(self.current["id"]) if self.current else {"state": "no_owned_session"}


_SERVICE = None
_SHUTDOWN = False
_SERVICE_LOCK = threading.Lock()


def _service():
    global _SERVICE
    with _SERVICE_LOCK:
        if _SHUTDOWN:
            raise RuntimeError("Mirroring service shut down")
        if _SERVICE is None:
            _SERVICE = MirrorService()
        return _SERVICE


def _execute(plan):
    policy.consume(plan)
    payload = plan.payload()
    if (android_files._bridge()._adb_snapshot(payload["device"]["serial"]) != payload["device"]
            or _scrcpy_snapshot() != payload["scrcpy"]):
        return "Mirror device/executable changed; nothing launched."
    return json.dumps(_service().launch(payload))


def request(serial, seconds=60):
    if type(seconds) is not int or not 5 <= seconds <= 300:
        return "Mirror duration must be an integer from 5 to 300 seconds."
    try:
        payload = {"device": android_files._bridge()._adb_snapshot(serial),
                   "scrcpy": _scrcpy_snapshot(), "seconds": seconds,
                   "view_only": True, "audio": False, "clipboard": False}
        plan = policy.prepare("android.mirror.view_only", ("android:" + serial, "local_mirror_window"), payload)
        return policy.request(plan, title=f"View-only Android mirror: {serial}",
                              detail="Live sensitive phone screen will be visible on this desktop. "
                              "Finite session, no keyboard/mouse control, audio forwarding or clipboard sync. "
                              "scrcpy deploys/runs its server on the phone. No recording/upload requested by this path. Other desktop software can capture the window. "
                              "Native tool/version/crash cleanup are not certified; stop only Ultron's owned session by mirror_id.\n"
                              + json.dumps(payload, ensure_ascii=True), execute=_execute)
    except Exception:
        return "Mirror preview unavailable. Select an authorized serial and stable ADB/scrcpy executables. Nothing launched."


def stop(mirror_id):
    return json.dumps(_SERVICE.stop(mirror_id) if _SERVICE is not None else {"state": "no_owned_session"})


def status():
    return json.dumps(_SERVICE.status() if _SERVICE is not None else {"state": "no_owned_session"})


def shutdown_mirrors():
    global _SHUTDOWN
    with _SERVICE_LOCK:
        _SHUTDOWN = True
        return _SERVICE.shutdown() if _SERVICE is not None else {"state": "no_owned_session"}
