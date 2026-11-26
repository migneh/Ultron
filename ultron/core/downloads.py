"""Bounded binary downloads. Network workers never write to the filesystem.

URL receipt and exact hash/size/path publication require separate host approvals.
Only the publication callback writes, using a private same-directory staging file
and no-clobber hard link. Redirects refused. No execution/extraction.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import stat
import tempfile
import unicodedata
from contextvars import copy_context
from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from urllib.parse import unquote, urlsplit

from ultron.core import file_safety as safety
from ultron.core import operation_policy as policy
from ultron.core import web_research as web
from ultron.core.file_safety import LOCK, checked
from ultron.core.undo import push_undo

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


@dataclass(frozen=True)
class Payload:
    data: bytes
    source_url: str
    retrieved_at: str


def _receive(url: str, budget: web.Budget) -> Payload:
    policy.require_consumed(("download.fetch",))
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
                raise DownloadError("Download redirect refused; approve the final public URL separately")
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
    policy.require_consumed(("download.fetch",))
    url = web.public_url(url)
    budget = web.Budget(TOTAL_SECONDS)

    def work():
        try:
            return _receive(url, budget)
        except (DownloadError, web.WebError) as error:
            return DownloadError(str(error))
        except Exception:
            return DownloadError("Network/TLS/read failure; no file published")

    context = copy_context()
    result = web.bounded_call(lambda: context.run(work), budget.remaining(TOTAL_SECONDS), "download")
    if result.error:
        raise DownloadError(result.error + "; no file published by this request")
    if isinstance(result.value, DownloadError):
        raise result.value
    if not isinstance(result.value, Payload):
        raise DownloadError("Download provider unavailable; no file published")
    return result.value


def _parent(target, allowed):
    parent = checked(target.parent, allowed)
    info = parent.stat()
    if not stat.S_ISDIR(info.st_mode):
        raise DownloadError("Download parent must be an existing directory")
    return [str(parent), info.st_dev, info.st_ino, info.st_mode]


def _destination(target, parent, allowed):
    checked(target, allowed)
    if _parent(target, allowed) != parent:
        raise DownloadError("Download parent changed; nothing published")
    if os.path.lexists(target):
        raise DownloadError("Download destination conflict: no file overwritten")


def publish(target: Path, data: bytes, allowed: Callable[[Path], bool], *, plan=None) -> str:
    policy.consume(plan)
    if plan.kind != "download.publish":
        raise PermissionError("Wrong publication operation")
    payload = plan.payload()
    if (str(target) != payload["target"] or not isinstance(data, bytes)
            or len(data) != payload["bytes"] or len(data) > MAX_BYTES
            or hashlib.sha256(data).hexdigest() != payload["sha256"]):
        raise DownloadError("Publication does not match approved bytes/path")
    with LOCK:
        _destination(target, payload["parent"], allowed)
        fd, raw = tempfile.mkstemp(prefix=".ultron-download-", suffix=".part", dir=target.parent)
        staging = Path(raw)
        owner = os.fstat(fd)
        published, warning = False, ""
        after = None
        try:
            with os.fdopen(fd, "wb") as output:
                output.write(data)
                output.flush()
                os.fsync(output.fileno())
            staged = safety.fingerprint(staging)
            if staged[-1] != payload["sha256"] or staged[2] != payload["bytes"]:
                raise DownloadError("Download staging changed")
            _destination(target, payload["parent"], allowed)
            os.link(staging, target, follow_symlinks=False)
            published = True
            after = safety.fingerprint(target)
            if after != staged:
                raise DownloadError("Published target changed; inspect destination")
        finally:
            try:
                info = staging.lstat()
                if (info.st_dev, info.st_ino) != (owner.st_dev, owner.st_ino):
                    raise DownloadError("Download staging replaced; inspect destination")
                staging.unlink()
            except OSError:
                if published:
                    warning = " WARNING: publication occurred, but private .ultron-download-*.part cleanup failed; inspect destination directory."
                else:
                    raise DownloadError("Publication/cleanup failed; inspect .ultron-download-*.part staging") from None
        def reverse():
            policy.require_consumed(("session.undo",))
            with LOCK:
                checked(target, allowed)
                if _parent(target, allowed) != payload["parent"] or safety.fingerprint(target) != after:
                    raise ValueError("Download inverse conflict: file/parent changed")
                target.unlink()
                return f"Removed unchanged downloaded file: {target}; native metadata/staging copies not removed."
        push_undo("downloaded " + target.name, reverse,
                  detail=f"Remove only unchanged downloaded file: {target}; expected identity {after}; parent {payload['parent']}. No recursion or staging cleanup; path/unlink races remain.")
        return warning


def _execute_publish(plan, data, allowed):
    try:
        payload = plan.payload()
        target = Path(payload["target"])
        warning = publish(target, data, allowed, plan=plan)
        return (f"Downloaded: {target} ({len(data)} bytes); SHA256 {payload['sha256']}. "
                "Saved only; not opened, executed, extracted or malware-scanned. "
                "Remote filenames ignored; content is untrusted." + warning)
    except Exception:
        return "Download publication failed or outcome unknown; inspect target and .ultron-download-*.part files. No retry or destructive cleanup of destination."


def _execute_fetch(plan, allowed):
    policy.consume(plan)
    payload = plan.payload()
    target = Path(payload["target"])
    try:
        with LOCK:
            _destination(target, payload["parent"], allowed)
        received = receive(payload["url"])
        if (not isinstance(received, Payload) or not isinstance(received.data, bytes)
                or len(received.data) > MAX_BYTES or received.source_url != payload["url"]):
            raise DownloadError("Invalid or redirected receipt; no file published")
        with LOCK:
            _destination(target, payload["parent"], allowed)
        snapshot = {**payload, "bytes": len(received.data), "sha256": hashlib.sha256(received.data).hexdigest()}
        publication = policy.prepare("download.publish", ("download_destination",), snapshot)
        return policy.request(publication, title="Save these exact received download bytes",
                              detail=json.dumps(publication.payload(), ensure_ascii=True)
                              + "\nSecond approval: the HTTP request already happened. Exact bytes held only in memory; "
                              "denial/expiry does not publish. File may be malicious; a hash is not a safety scan. "
                              "Private staged no-clobber publication; no execution, extraction or automatic retry. "
                              "External filesystem races and metadata/retention limits remain. Undo separately approved.",
                              execute=lambda approved: _execute_publish(approved, received.data, allowed))
    except (DownloadError, web.WebError) as error:
        return f"Download refused/unavailable: {error}"
    except Exception:
        return "Download failed: receipt/path validation unavailable; nothing published by this receipt path. No retry."


def request(url, directory, name, allowed):
    try:
        url = web.public_url(url)  # structural only, no DNS before consent
        with LOCK:
            target = target_path(url, directory, name, allowed)
            snapshot = {"url": url, "target": str(target), "parent": _parent(target, allowed)}
        plan = policy.prepare("download.fetch", ("public_network", "download_destination"), snapshot)
        return policy.request(plan, title="Fetch one exact public URL into memory",
                              detail=json.dumps(plan.payload(), ensure_ascii=True)
                              + "\nFirst approval: disclose request/path/query and your network address to this server. "
                              "No redirects, credentials, environment proxies or private DNS addresses; standard HTTP(S) ports only. "
                              "HTTP without TLS can be modified in transit. Up to 16 MiB, 20-second caller budget; "
                              "background network work may finish later but cannot publish. A separate hash/size-bound "
                              "approval is required to save received bytes at the exact vacant destination. "
                              "URL queries can contain secrets; review this preview and existing UI retention behavior.",
                              execute=lambda approved: _execute_fetch(approved, allowed))
    except (DownloadError, web.WebError) as error:
        return f"Download refused/unavailable: {error}"
    except Exception:
        return "Download failed: network/filesystem/path validation unavailable; no request submitted."
