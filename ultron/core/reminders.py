"""Durable reminder registry, OS adapters and a standalone stdlib-only runner.

Native jobs invoke this file with --database/--id; they never embed message text
or generated Python. SQLite arbitrates cancellation and delivery across processes.
A claimed delivery is not retried after a crash: avoid duplicate notifications.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import platform
import plistlib
import re
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from xml.etree import ElementTree as ET
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
ACTIVE_STATES = ("registering", "scheduled", "firing")
MAX_ACTIVE = 100
RUNNER = Path(__file__).resolve()


def database_path() -> Path:
    return Path.home() / ".ultron" / "reminders" / "registry.sqlite3"


def _now() -> datetime:
    return datetime.now(UTC)


def _identifier(value: str) -> str:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{32}", value) is None:
        raise ValueError("Use the full reminder_id returned by create or list.")
    return value


def parse_target(date: str, clock: str, zone: str = "", fold: int | None = None) -> datetime:
    """Resolve a wall time, rejecting missing times and unchosen DST ambiguity."""
    if not all(isinstance(value, str) for value in (date, clock, zone)):
        raise ValueError("date, time and timezone must be text.")
    if fold is not None and (
        isinstance(fold, bool) or not isinstance(fold, int) or fold not in (0, 1)
    ):
        raise ValueError("fold must be 0 (earlier occurrence) or 1 (later occurrence).")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", date) or not re.fullmatch(r"\d{2}:\d{2}", clock):
        raise ValueError("Use YYYY-MM-DD and HH:MM (24-hour time).")
    try:
        naive = datetime.strptime(f"{date} {clock}", "%Y-%m-%d %H:%M")
        tz = ZoneInfo(zone) if zone else None
    except ZoneInfoNotFoundError:
        raise ValueError(
            "Unknown/unavailable IANA timezone. Use e.g. Africa/Tunis; install tzdata if needed."
        ) from None
    except ValueError:
        raise ValueError("Invalid calendar date or time.") from None
    candidates = {}
    for occurrence in (0, 1):
        wall = naive.replace(fold=occurrence)
        aware = wall.replace(tzinfo=tz) if tz is not None else wall.astimezone()
        instant = aware.astimezone(UTC)
        back = (
            instant.astimezone(tz).replace(tzinfo=None)
            if tz is not None
            else instant.astimezone().replace(tzinfo=None)
        )
        if back == naive:
            candidates[occurrence] = instant
    distinct = set(candidates.values())
    if not distinct:
        raise ValueError("That local time does not exist because of a daylight-saving transition.")
    if len(distinct) > 1 and fold is None:
        raise ValueError("That local time occurs twice. Choose fold=0 (earlier) or fold=1 (later).")
    if fold is not None and fold in candidates:
        return candidates[fold]
    return next(iter(distinct))


@contextlib.contextmanager
def connection(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(path, timeout=10)
    db.row_factory = sqlite3.Row
    try:
        if os.name != "nt":
            path.chmod(0o600)
        db.execute("""CREATE TABLE IF NOT EXISTS reminders (
            id TEXT PRIMARY KEY, message TEXT NOT NULL, target_utc TEXT NOT NULL,
            wall_time TEXT NOT NULL, zone TEXT NOT NULL, platform TEXT NOT NULL,
            state TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
            cleanup_error TEXT NOT NULL DEFAULT '', created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL
        )""")
        db.commit()
        yield db
    finally:
        db.close()


class ReminderStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()

    def get(self, reminder_id: str) -> dict:
        _identifier(reminder_id)
        with connection(self.path) as db:
            row = db.execute("SELECT * FROM reminders WHERE id=?", (reminder_id,)).fetchone()
        if row is None:
            raise ValueError("Reminder not found. List reminders to get its ID.")
        return dict(row)

    def list(self, include_finished: bool = False, limit: int = 50) -> list[dict]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
            raise ValueError("limit must be an integer from 1 to 100.")
        with connection(self.path) as db:
            where = (
                "" if include_finished else "WHERE state IN ('registering','scheduled','firing')"
            )
            rows = db.execute(
                f"SELECT * FROM reminders {where} ORDER BY target_utc, id LIMIT ?", (limit,)
            ).fetchall()
        return [dict(row) for row in rows]

    def create(
        self, message: str, target: datetime, wall_time: str, zone: str, system: str
    ) -> dict:
        reminder_id = uuid4().hex
        now = _now().isoformat()
        with connection(self.path) as db:
            with db:
                db.execute("BEGIN IMMEDIATE")
                count = db.execute(
                    "SELECT count(*) FROM reminders WHERE state IN ('registering','scheduled','firing')"
                ).fetchone()[0]
                if count >= MAX_ACTIVE:
                    raise ValueError(f"At most {MAX_ACTIVE} active reminders are allowed.")
                db.execute(
                    "INSERT INTO reminders (id,message,target_utc,wall_time,zone,platform,state,created_utc,updated_utc) VALUES (?,?,?,?,?,?,'registering',?,?)",
                    (
                        reminder_id,
                        message,
                        target.astimezone(UTC).isoformat(),
                        wall_time,
                        zone or "system-local at creation",
                        system,
                        now,
                        now,
                    ),
                )
        return self.get(reminder_id)

    def update(self, reminder_id: str, **changes):
        _identifier(reminder_id)
        if not changes or set(changes) - {"state", "error", "cleanup_error"}:
            raise ValueError("Invalid reminder update.")
        changes["updated_utc"] = _now().isoformat()
        with connection(self.path) as db, db:
            db.execute(
                "UPDATE reminders SET " + ", ".join(f"{key}=?" for key in changes) + " WHERE id=?",
                (*changes.values(), reminder_id),
            )

    def cancel(self, reminder_id: str) -> dict:
        _identifier(reminder_id)
        with connection(self.path) as db, db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT state FROM reminders WHERE id=?", (reminder_id,)).fetchone()
            if row is None:
                raise ValueError("Reminder not found.")
            if row[0] == "firing":
                raise ValueError("Notification has already started; cancellation cannot recall it.")
            if row[0] in ("registering", "scheduled"):
                db.execute(
                    "UPDATE reminders SET state='cancelled', updated_utc=? WHERE id=?",
                    (_now().isoformat(), reminder_id),
                )
        return self.get(reminder_id)

    def claim(self, reminder_id: str) -> dict | None:
        _identifier(reminder_id)
        with connection(self.path) as db, db:
            cursor = db.execute(
                "UPDATE reminders SET state='firing',updated_utc=? WHERE id=? AND state='scheduled' AND target_utc<=?",
                (_now().isoformat(), reminder_id, _now().isoformat()),
            )
            if cursor.rowcount != 1:
                return None
        return self.get(reminder_id)


def _run(args: list[str], *, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    result = subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=20,
        env=env,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0,
    )
    if result.returncode:
        raise RuntimeError(
            (result.stderr or result.stdout or f"{args[0]} exited {result.returncode}").strip()[
                :400
            ]
        )
    return result


def _command(record: dict, database: Path) -> list[str]:
    return [
        sys.executable,
        str(RUNNER),
        "--database",
        str(database),
        "--id",
        _identifier(record["id"]),
    ]


def _job_name(record: dict) -> str:
    return "UltronReminder_" + _identifier(record["id"])


def _unit_dir() -> Path:
    # XDG_CONFIG_HOME is the native systemd user-unit lookup location.
    base = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    if not base.is_absolute():
        raise ValueError("XDG_CONFIG_HOME must be absolute.")
    return base / "systemd" / "user"


def _launch_dir() -> Path:
    return Path.home() / "Library" / "LaunchAgents"


def _write_private(path: Path, content: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    # IDs are random; exclusive creation refuses collisions instead of overwriting.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "wb") as stream:
        stream.write(content)


def _systemd_arg(value: str) -> str:
    if any(char in value for char in "\r\n\x00"):
        raise ValueError("Scheduler paths cannot contain control characters.")
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("%", "%%") + '"'


def install_job(record: dict, database: Path):
    system, name = record["platform"], _job_name(record)
    command = _command(record, database)
    if system == "Windows":
        ns = "http://schemas.microsoft.com/windows/2004/02/mit/task"
        ET.register_namespace("", ns)

        def element(parent, tag, text=None):
            child = ET.SubElement(parent, f"{{{ns}}}{tag}")
            child.text = text
            return child

        task = ET.Element(f"{{{ns}}}Task", {"version": "1.2"})
        registration = element(task, "RegistrationInfo")
        element(registration, "Description", "ULTRON Reminder")
        trigger = element(element(task, "Triggers"), "TimeTrigger")
        element(trigger, "StartBoundary", record["target_utc"])
        element(trigger, "Enabled", "true")
        principal = element(element(task, "Principals"), "Principal", None)
        principal.set("id", "Author")
        element(principal, "LogonType", "InteractiveToken")
        element(principal, "RunLevel", "LeastPrivilege")
        settings = element(task, "Settings")
        element(settings, "MultipleInstancesPolicy", "IgnoreNew")
        element(settings, "DisallowStartIfOnBatteries", "false")
        element(settings, "StopIfGoingOnBatteries", "false")
        element(settings, "StartWhenAvailable", "true")
        element(settings, "ExecutionTimeLimit", "PT1M")
        actions = element(task, "Actions")
        actions.set("Context", "Author")
        execute = element(actions, "Exec")
        element(execute, "Command", command[0])
        element(execute, "Arguments", subprocess.list2cmdline(command[1:]))
        xml = database.parent / f"{record['id']}.xml"
        _write_private(xml, ET.tostring(task, encoding="utf-16", xml_declaration=True))
        try:
            _run(["schtasks", "/Create", "/TN", name, "/XML", str(xml)])
        finally:
            xml.unlink(missing_ok=True)
    elif system == "Darwin":
        # launchd calendar triggers have no absolute UTC/year field. Poll due
        # timestamps instead of silently repeating yearly or misreading DST.
        label = "com.ultron.reminder." + record["id"]
        plist = _launch_dir() / f"{label}.plist"
        _write_private(
            plist,
            plistlib.dumps(
                {
                    "Label": label,
                    "ProgramArguments": command,
                    "RunAtLoad": True,
                    "StartInterval": 60,
                    "StandardOutPath": "/dev/null",
                    "StandardErrorPath": "/dev/null",
                }
            ),
        )
        _run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(plist)])
    elif system == "Linux":
        units = _unit_dir()
        service = (
            "[Unit]\nDescription=ULTRON Reminder\n[Service]\nType=oneshot\n"
            "TimeoutStartSec=45s\nExecStart=:" + " ".join(map(_systemd_arg, command)) + "\n"
        )
        target = datetime.fromisoformat(record["target_utc"]).astimezone(UTC)
        timer = (
            "[Unit]\nDescription=ULTRON Reminder\n[Timer]\n"
            f"OnCalendar={target.strftime('%Y-%m-%d %H:%M:%S')} UTC\n"
            f"Unit={name}.service\nPersistent=true\nAccuracySec=1s\n[Install]\nWantedBy=timers.target\n"
        )
        _write_private(units / f"{name}.service", service.encode())
        _write_private(units / f"{name}.timer", timer.encode())
        _run(["systemctl", "--user", "daemon-reload"])
        _run(["systemctl", "--user", "enable", "--now", f"{name}.timer"])
    else:
        raise ValueError("Unsupported reminder platform.")


def remove_job(record: dict):
    system, name = record["platform"], _job_name(record)
    if system == "Windows":
        _run(["schtasks", "/Delete", "/TN", name, "/F"])
    elif system == "Darwin":
        label = "com.ultron.reminder." + record["id"]
        (_launch_dir() / f"{label}.plist").unlink(missing_ok=True)
        _run(["launchctl", "bootout", f"gui/{os.getuid()}/{label}"])
    elif system == "Linux":
        # Keep the unit files if disabling fails; cancellation in SQLite still
        # suppresses delivery, and the user can retry native cleanup.
        _run(["systemctl", "--user", "disable", "--now", f"{name}.timer"])
        for suffix in ("timer", "service"):
            (_unit_dir() / f"{name}.{suffix}").unlink(missing_ok=True)
        _run(["systemctl", "--user", "daemon-reload"])


def cleanup(store: ReminderStore, record: dict):
    try:
        remove_job(record)
    except Exception as error:
        store.update(record["id"], cleanup_error=str(error)[:400])
    else:
        store.update(record["id"], cleanup_error="")


def create_reminder(
    store: ReminderStore,
    date: str,
    clock: str,
    message: str,
    zone: str = "",
    fold: int | None = None,
) -> dict:
    if getattr(sys, "frozen", False):
        raise ValueError(
            "Persistent reminders need a Python installation; frozen-app runner packaging is not supported yet."
        )
    if (
        not isinstance(message, str)
        or not message.strip()
        or len(message) > 500
        or "\x00" in message
    ):
        raise ValueError("message must contain 1–500 characters without NUL bytes.")
    target = parse_target(date, clock, zone, fold)
    if (target - _now()).total_seconds() < 60:
        raise ValueError(
            "Choose a time at least 60 seconds in the future to allow OS registration."
        )
    record = store.create(message.strip(), target, f"{date} {clock}", zone, platform.system())
    try:
        install_job(record, store.path)
    except Exception as error:
        store.update(record["id"], state="scheduling_failed", error=str(error)[:400])
        cleanup(store, record)
    else:
        # Do not resurrect a reminder cancelled during native registration.
        with connection(store.path) as db, db:
            db.execute(
                "UPDATE reminders SET state='scheduled',updated_utc=? WHERE id=? AND state='registering'",
                (_now().isoformat(), record["id"]),
            )
        if store.get(record["id"])["state"] != "scheduled":
            cleanup(store, record)
    return store.get(record["id"])


def notify(message: str):
    """Report OS command acceptance, not proof the person saw a notification."""
    system = platform.system()
    if system == "Darwin":
        script = 'on run argv\ndisplay notification (item 1 of argv) with title "ULTRON Reminder"\nend run'
        _run(["osascript", "-e", script, "--", message])
    elif system == "Windows":
        script = (
            "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Windows.Forms; "
            "Add-Type -AssemblyName System.Drawing; "
            "$n=New-Object System.Windows.Forms.NotifyIcon; "
            "$n.Icon=[System.Drawing.SystemIcons]::Information; $n.Visible=$true; "
            "$n.ShowBalloonTip(10000,'ULTRON Reminder',$env:ULTRON_REMINDER_MESSAGE,"
            "[System.Windows.Forms.ToolTipIcon]::Info); Start-Sleep -Seconds 12; $n.Dispose()"
        )
        _run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            env={**os.environ, "ULTRON_REMINDER_MESSAGE": message},
        )
    elif system == "Linux":
        _run(["notify-send", "--", "ULTRON Reminder", message])
    else:
        raise ValueError("Unsupported notification platform.")


def deliver(path: Path, reminder_id: str) -> bool:
    """Atomic at-most-once claim; process exit or notification failure is visible."""
    if not path.is_file():
        return False
    store = ReminderStore(path)
    record = store.claim(reminder_id)
    if record is None:
        return False
    try:
        notify(record["message"])
    except Exception as error:
        store.update(reminder_id, state="notification_failed", error=str(error)[:400])
    else:
        store.update(reminder_id, state="notified", error="")
    cleanup(store, record)
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deliver one registered Ultron reminder")
    parser.add_argument("--database", required=True, type=Path)
    parser.add_argument("--id", required=True)
    args = parser.parse_args()
    deliver(args.database, args.id)
