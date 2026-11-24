"""Bounded binary downloads. Network workers never write to the filesystem.

Only the waiting caller may publish a completed result, using a same-directory
private staging file and atomic no-clobber hard link. No execution/extraction.
"""

from __future__ import annotations

import os
import re
import tempfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urljoin, urlsplit

from core import web_research as web
from core.file_safety import LOCK, checked

MAX_BYTES = 16 * 1024 * 1024
TOTAL_SECONDS = 20


class DownloadError(ValueError):
    pass


def filename(value: str) -> str:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or value in {".", ".."}
        or value.endswith((".", " "))
        or len(value.encode("utf-8")) > 180
        or any(c in '<>:"/\\|?*' or unicodedata.category(c).startswith("C") for c in value)
        or re.fullmatch(r"(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?", value, re.I)
    ):
        raise DownloadError(
            "Unsafe filename: use one plain filename, no paths, controls or reserved names"
        )
    return value


def target_path(url: str, directory: Path, name: str, allowed: Callable[[Path], bool]) -> Path:
    if not isinstance(name, str):
        raise DownloadError("Download name must be a string")
    directory = checked(directory, allowed)
    if not directory.is_dir():
        raise DownloadError(
            "Download destination must be an existing directory; create it explicitly first"
        )
    candidate = name or unquote(urlsplit(url).path.rsplit("/", 1)[-1]) or "downloaded_file"
    target = checked(directory / filename(candidate), allowed)
    if os.path.lexists(target):
        raise DownloadError("Download destination conflict: existing files are never overwritten")
    return target


@dataclass
class Payload:
    data: bytes
    source_url: str
    retrieved_at: str


def _receive(url: str, budget: web.Budget) -> Payload:
    redirects = 0
    while True:
        if budget.remaining(1) <= 0:
            raise DownloadError("Download deadline exhausted")
        ips = web.addresses(url)
        if budget.remaining(1) <= 0:
            raise DownloadError("Download deadline exhausted during DNS")
        with web._open(
            url, ips[0], budget.remaining(3), budget.remaining(4), accept="*/*"
        ) as response:
            if budget.remaining(1) <= 0:
                raise DownloadError("Download deadline exhausted")
            if response.status in {301, 302, 303, 307, 308}:
                location = response.headers.get("Location")
                if not location or redirects >= 3:
                    raise DownloadError("Download redirect limit reached or missing target")
                target = web.public_url(urljoin(url, location))
                if url.startswith("https:") and target.startswith("http:"):
                    raise DownloadError("HTTPS downgrade redirect blocked")
                url = target
                redirects += 1
                continue
            if response.status != 200:
                raise DownloadError(f"Download HTTP {response.status}; no file published")
            if response.headers.get("Content-Encoding", "identity").strip().lower() not in {
                "",
                "identity",
            }:
                raise DownloadError("Compressed HTTP response rejected; no file published")
            length = response.headers.get("Content-Length")
            expected = None
            if length is not None:
                if not re.fullmatch(r"[0-9]{1,12}", length.strip()):
                    raise DownloadError("Invalid Content-Length")
                if response.headers.get("Transfer-Encoding"):
                    raise DownloadError("Ambiguous HTTP body framing")
                expected = int(length)
                if expected > MAX_BYTES:
                    raise DownloadError("Download exceeds 16 MiB limit")
            data = bytearray()
            for chunk in response.stream(65536, decode_content=False):
                if budget.remaining(1) <= 0:
                    raise DownloadError("Download read deadline exhausted")
                if len(data) + len(chunk) > MAX_BYTES:
                    raise DownloadError("Download exceeds 16 MiB limit; no partial file published")
                data.extend(chunk)
            if budget.remaining(1) <= 0:
                raise DownloadError("Download deadline exhausted")
            if expected is not None and len(data) != expected:
                raise DownloadError("Incomplete/mismatched download length; no file published")
            return Payload(bytes(data), url, web.utc_now())


def receive(url: str) -> Payload:
    url = web.public_url(url)
    budget = web.Budget(TOTAL_SECONDS)

    def work():
        try:
            return _receive(url, budget)
        except (DownloadError, web.WebError) as error:
            return DownloadError(str(error))
        except Exception:
            return DownloadError("Network/TLS/read failure; no file published")

    result = web.bounded_call(work, budget.remaining(TOTAL_SECONDS), "download")
    if result.error:
        raise DownloadError(result.error + "; no file published by this request")
    if isinstance(result.value, DownloadError):
        raise result.value
    if not isinstance(result.value, Payload):
        raise DownloadError("Download provider unavailable; no file published")
    return result.value


def publish(target: Path, data: bytes, allowed: Callable[[Path], bool]) -> str:
    if not isinstance(data, bytes) or len(data) > MAX_BYTES:
        raise DownloadError("Invalid or oversized completed download")
    with LOCK:
        target = checked(target, allowed)
        if os.path.lexists(target):
            raise DownloadError("Download destination conflict: no file overwritten")
        # mkstemp defaults to mode 0600 (subject to platform semantics); final
        # file inherits that mode, never a server-provided executable mode.
        fd, raw = tempfile.mkstemp(prefix=".ultron-download-", suffix=".part", dir=target.parent)
        staging = Path(raw)
        published = False
        warning = ""
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            checked(target, allowed)
            os.link(staging, target, follow_symlinks=False)
            published = True
        finally:
            try:
                staging.unlink(missing_ok=True)
            except OSError:
                if published:
                    warning = " WARNING: saved successfully, but private .ultron-download-*.part staging cleanup failed; inspect destination directory."
                else:
                    raise DownloadError(
                        "Publication failed and staging cleanup failed; inspect .ultron-download-*.part files in destination"
                    ) from None
        return warning
