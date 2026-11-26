"""Single-frame Android PNG capture: explicit consent, bounded private local output.

No upload/display/phone recording, no overwrite or implicit default-device choice.
PNG checks are structural, not a decoder/content-safety certification.
"""
from __future__ import annotations

import hashlib
import json
import os
import struct
import zlib
from pathlib import Path

from ultron.core import android_files, file_safety
from ultron.core import operation_policy as policy
from ultron.core import productivity_store as store

MAX_BYTES = 16 * 1024 * 1024
MAX_PIXELS = 40_000_000


def _validate_png(path: Path, checksum: str) -> tuple[int, int]:
    file_safety.checked(path, lambda _: True)
    if not path.is_file() or path.stat().st_size > MAX_BYTES:
        raise ValueError("Capture too large or not regular")
    with path.open("rb") as stream:
        data = stream.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES or hashlib.sha256(data).hexdigest() != checksum or data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Invalid capture bytes")
    position, dimensions, seen_data = 8, None, False
    for _ in range(4096):
        if position + 12 > len(data):
            break
        length = int.from_bytes(data[position:position + 4], "big")
        kind = data[position + 4:position + 8]
        end = position + 12 + length
        if end > len(data) or any(not (65 <= char <= 90 or 97 <= char <= 122) for char in kind):
            raise ValueError("Invalid PNG chunk")
        body = data[position + 8:end - 4]
        crc = int.from_bytes(data[end - 4:end], "big")
        if zlib.crc32(kind + body) & 0xffffffff != crc:
            raise ValueError("Invalid PNG CRC")
        if kind in {b"acTL", b"fcTL", b"fdAT"}:
            raise ValueError("Animated PNG not supported")
        if dimensions is None:
            if kind != b"IHDR" or length != 13:
                raise ValueError("Missing PNG header")
            width, height, depth, color, compression, filtering, interlace = struct.unpack(">IIBBBBB", body)
            depths = {0: {1, 2, 4, 8, 16}, 2: {8, 16}, 3: {1, 2, 4, 8}, 4: {8, 16}, 6: {8, 16}}
            if (not 0 < width <= 16384 or not 0 < height <= 16384 or width * height > MAX_PIXELS
                    or depth not in depths.get(color, set()) or compression or filtering or interlace not in {0, 1}):
                raise ValueError("Unsupported PNG dimensions/format")
            dimensions = width, height
        elif kind == b"IHDR":
            raise ValueError("Duplicate PNG header")
        elif kind == b"IDAT":
            seen_data = True
        elif kind == b"IEND":
            if length or end != len(data) or not seen_data:
                raise ValueError("Incomplete PNG")
            return dimensions
        position = end
    raise ValueError("PNG incomplete or too many chunks")


def _execute(plan):
    policy.consume(plan)
    payload = plan.payload()
    bridge = android_files._bridge()
    target = store.allowed_path(payload["destination"])
    if os.path.lexists(target) or not target.parent.is_dir():
        return "Screenshot destination conflict; no capture attempted."
    if bridge._adb_snapshot(payload["device"]["serial"]) != payload["device"]:
        return "Android executable/transport changed; no capture attempted."
    temporary = target.parent / f".ultron-capture-{plan.operation_id}.part"
    created = False
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        created = True
        with os.fdopen(fd, "wb") as output:
            checksum = android_files._receive(
                android_files._prefix(payload["device"]) + ["exec-out", "screencap", "-p"],
                output, None, timeout=15, max_bytes=MAX_BYTES)
            output.flush()
            os.fsync(output.fileno())
        width, height = _validate_png(temporary, checksum)
        store.allowed_path(str(target))
        os.link(temporary, target)
        return (f"Single Android screenshot saved locally: {target}. {width}x{height}; SHA-256: {checksum}. "
                "PNG structure checked, not decoded or safety-certified. No upload/display performed by this path.")
    finally:
        if created:
            temporary.unlink(missing_ok=True)


def request(destination: str, serial: str) -> str:
    try:
        target = store.allowed_path(destination)
        if target.suffix.lower() != ".png" or os.path.lexists(target) or not target.parent.is_dir():
            raise ValueError("Select a new exact .png file with existing approved parent")
        payload = {"destination": str(target), "device": android_files._bridge()._adb_snapshot(serial),
                   "maximum_bytes": MAX_BYTES, "maximum_pixels": MAX_PIXELS, "timeout_seconds": 15}
        plan = policy.prepare("android.capture.single_png", ("android:" + serial, "local_screenshot"), payload)
        return policy.request(
            plan, title=f"Capture one Android screenshot: {serial}",
            detail="Sensitive screen contents visible WHEN EXECUTION STARTS will be captured, not a pre-approved image. "
                   "One frame only, 15s/16 MiB/40MP limits. Exact new local file; no upload/display or overwrite. "
                   "Keep the destination private; other software may watch/sync it. Manual deletion/retention is your responsibility. Host/device races are not sandboxed.\n"
                   + json.dumps(payload, ensure_ascii=True), execute=_execute)
    except Exception:
        return "Screenshot preview unavailable. Supply an explicit authorized serial and a new exact .png file in a host-approved root. No capture performed."
