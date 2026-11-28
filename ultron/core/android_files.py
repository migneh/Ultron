"""Scoped Android file effects. Host/device checks reduce races, not a sandbox."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import stat
import subprocess
import tempfile
import threading
import time
from pathlib import Path
from uuid import uuid4

from ultron.core import file_safety
from ultron.core import operation_policy as policy
from ultron.core import productivity_store as store

MAX_BYTES = 64 * 1024 * 1024


def _bridge():
    from ultron.actions import android_bridge
    return android_bridge


def _prefix(device):
    return [device["binary"], "-H", "127.0.0.1", "-P", "5037", "-t", device["transport_id"]]


def _remote_path(value):
    if (not isinstance(value, str) or len(value) > 512
            or not value.startswith("/sdcard/Download/")
            or any(not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", part)
                   for part in value[len("/sdcard/Download/"):].split("/"))):
        raise ValueError("Use one simple file path under /sdcard/Download; no traversal or shell syntax")
    return value


def _remote_snapshot(device, path):
    bridge = _bridge()
    command = _prefix(device) + ["shell", f"stat -c '%F:%s' {path}"]
    code, text, _ = bridge._run_cmd(command, timeout=5)
    match = re.fullmatch(r"regular file:(\d+)", text)
    if code or not match or int(match[1]) > MAX_BYTES:
        raise ValueError("Remote source must be a regular file up to 64 MiB (stat required)")
    code, digest, _ = bridge._run_cmd(_prefix(device) + ["shell", "sha256sum " + path], timeout=15)
    checksum = digest.split()[0] if digest.split() else ""
    if code or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("Remote SHA-256 unavailable")
    code, after, _ = bridge._run_cmd(command, timeout=5)
    if code or after != text:
        raise ValueError("Remote source changed")
    return {"size": int(match[1]), "sha256": checksum}


def _local_snapshot(value):
    path = store.allowed_path(value)
    identity = list(file_safety.fingerprint(path))
    return str(path), identity


def _stage_source(path, expected, staged):
    # Recheck grants, symlinks and approved identity, then copy into a private
    # snapshot. ADB never reads the mutable original pathname.
    source, identity = _local_snapshot(path)
    if identity != expected:
        raise ValueError("Local source changed")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_BINARY", 0)
    digest, total = hashlib.sha256(), 0
    with os.fdopen(os.open(source, flags), "rb") as stream, staged.open("xb") as output:
        before = os.fstat(stream.fileno())
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("Not a regular source")
        while chunk := stream.read(65536):
            total += len(chunk)
            if total > MAX_BYTES:
                raise ValueError("Source grew beyond limit")
            digest.update(chunk)
            output.write(chunk)
        after = os.fstat(stream.fileno())
    observed = [after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode, digest.hexdigest()]
    if (observed != expected or total != expected[2]
            or (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns, before.st_mode)
            != (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns, after.st_mode)):
        raise ValueError("Source changed while staging")
    staged.chmod(0o400)


def _receive(cmd, output, expected_size, timeout=60, *, max_bytes=MAX_BYTES):
    """Bounded stdout queue; only caller writes the file. No unbounded communicate.

    Reader is daemonized and never holds the destination handle. On timeout the
    direct child is killed; descendant/process-tree isolation is not claimed.
    """
    if (type(max_bytes) is not int or not 0 < max_bytes <= MAX_BYTES
            or (expected_size is not None and (type(expected_size) is not int or not 0 <= expected_size <= max_bytes))):
        raise ValueError("Invalid receive byte budget")
    proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    chunks = queue.Queue(maxsize=2)
    stop = threading.Event()

    def read():
        try:
            while not stop.is_set():
                chunk = proc.stdout.read1(65536)
                while not stop.is_set():
                    try:
                        chunks.put(chunk, timeout=.1)
                        break
                    except queue.Full:
                        pass
                if not chunk:
                    break
        except Exception:
            while not stop.is_set():
                try:
                    chunks.put(None, timeout=.1)
                    break
                except queue.Full:
                    pass
        finally:
            proc.stdout.close()

    reader = threading.Thread(target=read, daemon=True, name="android-bounded-receive")
    deadline = time.monotonic() + timeout
    digest, size = hashlib.sha256(), 0
    try:
        reader.start()
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise ValueError("Receive deadline exceeded")
            try:
                chunk = chunks.get(timeout=remaining)
            except queue.Empty as error:
                raise ValueError("Receive deadline exceeded") from error
            if chunk is None:
                raise ValueError("Receive failed")
            if not chunk:
                break
            size += len(chunk)
            if size > (expected_size if expected_size is not None else max_bytes):
                raise ValueError("Receive size exceeded approved source")
            output.write(chunk)
            digest.update(chunk)
        if (proc.wait(timeout=max(.01, deadline - time.monotonic())) != 0
                or (expected_size is not None and size != expected_size)):
            raise ValueError("Receive incomplete")
        return digest.hexdigest()
    finally:
        stop.set()
        if proc.poll() is None:
            proc.kill()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                pass
        reader.join(timeout=.2) if reader.ident is not None else proc.stdout.close()


def _pull(payload, plan):
    target = store.allowed_path(payload["local_path"])
    if not target.parent.is_dir() or os.path.lexists(target):
        return "Local destination conflict; nothing downloaded or overwritten."
    if _remote_snapshot(payload["device"], payload["phone_path"]) != payload["remote"]:
        return "Remote source changed; nothing downloaded."
    if _bridge()._adb_snapshot(payload["device"]["serial"]) != payload["device"]:
        return "Device changed during source validation; nothing downloaded."
    # Same-directory staging permits exclusive hard-link publication, never replace().
    temporary = target.parent / f".ultron-pull-{plan.operation_id}.part"
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "wb") as output:
            checksum = _receive(_prefix(payload["device"]) + ["exec-out", "cat", payload["phone_path"]], output, payload["remote"]["size"])
            output.flush()
            os.fsync(output.fileno())
        if checksum != payload["remote"]["sha256"]:
            return "Received content did not match approved SHA-256; not published."
        # Recheck the host grant immediately before publication. Same-user path
        # races remain possible; no descriptor-relative filesystem sandbox claimed.
        store.allowed_path(str(target))
        file_safety.checked(temporary, lambda _: True)
        os.link(temporary, target)
        return f"Downloaded file published without overwrite: {target}. SHA-256: {checksum}. Content remains untrusted."
    finally:
        if created:
            temporary.unlink(missing_ok=True)


def _execute(plan):
    policy.consume(plan)
    payload = plan.payload()
    if _bridge()._adb_snapshot(payload["device"]["serial"]) != payload["device"]:
        return "Android executable/transport changed; no transfer/install attempted."
    if payload["action"] == "pull":
        return _pull(payload, plan)
    # Snapshot exists only after approval, outside user source/auto-discovery.
    with tempfile.TemporaryDirectory(prefix="ultron-adb-") as temp:
        staged = Path(temp) / ("payload.apk" if payload["action"] == "install" else "payload.bin")
        _stage_source(payload["local_path"], payload["local_identity"], staged)
        # Large-file staging may outlast a device connection; check again.
        if _bridge()._adb_snapshot(payload["device"]["serial"]) != payload["device"]:
            return "Device changed during staging; no transfer/install attempted."
        prefix = _prefix(payload["device"])
        if payload["action"] == "install":
            cmd = prefix + ["install"] + (["-r"] if payload["replace_existing"] else []) + [str(staged)]
            code, output, _ = _bridge()._run_cmd(cmd, timeout=180)
            if code == 0 and "Success" in output.splitlines():
                return "ADB reported package installation Success; app behavior/signing/safety not independently verified."
            return "APK installation failed or outcome is uncertain. Inspect device packages; no automatic retry."
        remote_dir = payload["remote_directory"]
        code, _, _ = _bridge()._run_cmd(prefix + ["shell", "mkdir -- " + remote_dir], timeout=10)
        if code:
            return "Could not exclusively create remote operation directory; no file pushed."
        if _bridge()._adb_snapshot(payload["device"]["serial"]) != payload["device"]:
            return "Device changed after directory creation; no file pushed. Inspect the operation directory manually."
        code, _, _ = _bridge()._run_cmd(prefix + ["push", str(staged), payload["phone_path"]], timeout=120)
        if code:
            return "Push failed or outcome is uncertain. Operation directory may contain partial data; inspect it manually. No retry."
        code, result, _ = _bridge()._run_cmd(prefix + ["shell", "sha256sum " + payload["phone_path"]], timeout=15)
        expected = payload["local_identity"][-1]
        if not code and result.split() and result.split()[0] == expected:
            return f"Push SHA-256 readback matched: {payload['phone_path']}. No existing destination was intentionally reused."
        return f"ADB accepted push to {payload['phone_path']}; checksum not verified. Inspect before reuse; no retry."


def request(action, serial, *, local_path="", phone_path="/sdcard/Download/", replace_existing=False):
    try:
        if action not in {"push", "pull", "install"} or type(replace_existing) is not bool:
            raise ValueError("Unsupported transfer options")
        payload = {"action": action, "device": _bridge()._adb_snapshot(serial)}
        if action == "pull":
            remote = _remote_path(phone_path)
            target = store.allowed_path(local_path)
            if not target.parent.is_dir() or os.path.lexists(target):
                raise ValueError("Use a new exact destination file with an existing approved parent")
            payload.update(local_path=str(target), phone_path=remote, remote=_remote_snapshot(payload["device"], remote))
        else:
            source, identity = _local_snapshot(local_path)
            if action == "install" and Path(source).suffix.lower() != ".apk":
                raise ValueError("Select an APK")
            if action == "push" and phone_path.rstrip("/") != "/sdcard/Download":
                raise ValueError("Push only supports fresh directories under /sdcard/Download")
            payload.update(local_path=source, local_identity=identity, replace_existing=replace_existing)
        if action == "push":
            # Include the actual generated remote destination in the immutable plan.
            remote_dir = "/sdcard/Download/ultron-" + uuid4().hex
            name = Path(payload["local_path"]).name
            if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", name):
                name = "transferred-file.bin"
            payload.update(remote_directory=remote_dir, phone_path=remote_dir + "/" + name)
        plan = policy.prepare("android.file." + action, ("android:" + serial, "local_android_file"), payload)
        return policy.request(plan, title=f"Android {action}: {serial}",
                              detail="Exact single-file operation, up to 64 MiB. No automatic retry. "
                              "Device/filesystem state is not atomically locked. APKs may execute privileged app code; replacement is explicit. "
                              "Remote partial data may remain after failure.\n" + json.dumps(payload, ensure_ascii=True), execute=_execute)
    except Exception:
        return "Android file preview unavailable. Use an explicit authorized serial, approved local root and supported exact file paths. No transfer/install performed."
