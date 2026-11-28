"""Exact-content approved inert drafts. Not an arbitrary file writer or sandbox."""
from __future__ import annotations

import hashlib
import os
from pathlib import Path

from ultron.core import file_safety
from ultron.core import operation_policy as policy

MAX_BYTES = 64000
MAX_DRAFTS = 1000


def directory() -> Path:
    return Path.home() / ".ultron" / "review_drafts"


def _save(plan: policy.OperationPlan) -> str:
    policy.consume(plan)
    payload = plan.payload()
    root = directory()
    if str(root) != payload["directory"]:
        return "Draft destination changed; nothing written. Request a new preview."
    file_safety.checked(root, lambda p: p == root)
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    file_safety.checked(root, lambda p: p == root)
    with os.scandir(root) as entries:
        for count, _entry in enumerate(entries, 1):
            if count >= MAX_DRAFTS:
                return "Review draft directory full; remove old drafts manually. Nothing written."
    # Names never come from model-supplied paths, labels, extensions or code.
    path = root / f"{plan.operation_id}.txt"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(payload["source"])
        stream.flush()
        os.fsync(stream.fileno())
    return f"Review-only text draft saved: {path}\nSHA-256: {payload['sha256']}\nNot installed, imported, executed or tested. No original file changed."


def request(source: str, label: str = "Source draft") -> str:
    if not isinstance(source, str) or not source.strip() or "\x00" in source:
        raise ValueError("Draft must be non-empty text without NUL")
    if len(source.encode("utf-8")) > MAX_BYTES:
        raise ValueError("Draft limited to 64000 UTF-8 bytes")
    if not isinstance(label, str) or not label or len(label) > 120:
        raise ValueError("Invalid draft label")
    root = directory()
    file_safety.checked(root, lambda p: p == root)
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    plan = policy.prepare("source_draft.save", ("local_review_drafts",),
                          {"directory": str(root), "source": source, "sha256": digest})
    return policy.request(plan, title=label,
                          detail="Save inert .txt outside auto-discovery; not a safety certification. "
                          f"No execution or original-file overwrite.\nSHA-256: {digest}\nFull draft:\n{source}", execute=_save)
