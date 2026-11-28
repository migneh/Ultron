"""Local-first release storage and host-managed document access grants.

Database contains private user content; filesystem permissions are not encryption.
No model tool can grant roots. Use core.productivity_setup on the host machine.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
from pathlib import Path
from uuid import uuid4


def database_path() -> Path:
    return Path.home() / ".ultron" / "productivity.sqlite3"


@contextlib.contextmanager
def connection():
    path = database_path()
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    db = sqlite3.connect(path, timeout=5)
    db.row_factory = sqlite3.Row
    try:
        if os.name != "nt":
            path.chmod(0o600)
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript("""
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS tasks(
            id TEXT PRIMARY KEY, title TEXT NOT NULL, notes TEXT NOT NULL,
            state TEXT NOT NULL, due_date TEXT, version INTEGER NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS evidence(
            id TEXT PRIMARY KEY, claim TEXT NOT NULL, url TEXT NOT NULL,
            quote TEXT NOT NULL, locator TEXT NOT NULL, created TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS notices(
            id TEXT PRIMARY KEY, dedupe TEXT UNIQUE NOT NULL, title TEXT NOT NULL,
            body TEXT NOT NULL, created TEXT NOT NULL, expires TEXT NOT NULL,
            acknowledged INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS notice_deliveries(
            notice_id TEXT PRIMARY KEY REFERENCES notices(id) ON DELETE CASCADE,
            state TEXT NOT NULL, attempted TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS previews(
            id TEXT PRIMARY KEY, source TEXT NOT NULL, source_hash TEXT NOT NULL,
            body TEXT NOT NULL, body_hash TEXT NOT NULL, created REAL NOT NULL);
        """)
        db.execute("BEGIN IMMEDIATE")
        with db:
            yield db
    finally:
        db.close()


def setting(key, default=None):
    with connection() as db:
        row = db.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else default


def set_setting(key, value):
    with connection() as db:
        db.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (key, json.dumps(value)))


def text(value, label, maximum=2000, *, empty=False):
    if (not isinstance(value, str) or len(value) > maximum or "\x00" in value
            or (not empty and not value.strip())):
        raise ValueError(f"{label} must be {'optional ' if empty else 'non-empty '}text, at most {maximum} characters, without NUL.")
    return value


def identifier(value):
    if not isinstance(value, str) or len(value) != 32 or any(c not in "0123456789abcdef" for c in value):
        raise ValueError("Use the full host-issued ID returned by the tool.")
    return value


def new_id():
    return uuid4().hex


def allowed_path(value: str) -> Path:
    from ultron.core.file_safety import checked
    text(value, "path", 4096)
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ValueError("Use an absolute path inside a host-approved document root.")
    roots = [Path(root) for root in setting("document_roots", [])]
    return checked(path, lambda candidate: any(candidate.is_relative_to(root) for root in roots))
