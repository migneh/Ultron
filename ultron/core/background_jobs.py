"""Durable bounded host jobs with cooperative cancellation, never automatic replay.

One OS advisory owner lock per database prevents a second runtime exceeding the
admission limit. After ownership transfers, unfinished records become uncertain
(or interrupted if never started). Payloads/callables are not persisted. Threads
cannot be forcibly stopped: overdue/blocked workers keep their admission slots.
"""
from __future__ import annotations

import contextlib
import json
import os
import sqlite3
import threading
import time
from pathlib import Path
from uuid import uuid4

ACTIVE = ("queued", "running", "cancel_requested")
TERMINAL = {"completed", "partial", "failed", "cancelled", "deadline_exceeded", "outcome_unknown", "interrupted"}


def database_path():
    return Path.home() / ".ultron" / "background_jobs.sqlite3"


class JobStopped(Exception):
    pass


class OwnerLock:
    def __init__(self, path):
        self.path = path
        self.file = None

    def acquire(self):
        if self.file is not None:
            return True
        flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(self.path, flags, 0o600)
        stream = os.fdopen(fd, "r+b", buffering=0)
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    stream.write(b"0")
                stream.seek(0)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            stream.close()
            return False
        self.file = stream
        return True

    def release(self):
        if self.file is not None:
            # Closing releases the OS lock, including at process exit/crash.
            self.file.close()
            self.file = None


class JobContext:
    def __init__(self, service, job_id, seconds, call_limit):
        self.service, self.job_id = service, job_id
        self.end = time.monotonic() + seconds
        self.call_limit = call_limit
        self.stop_event = threading.Event()
        self.calls = 0
        self.effect_started = False

    def checkpoint(self):
        if time.monotonic() >= self.end:
            raise JobStopped("deadline_exceeded")
        if self.stop_event.is_set() or self.service.get(self.job_id)["cancel_requested"]:
            raise JobStopped("cancelled")

    def call(self):
        self.checkpoint()
        if self.calls >= self.call_limit:
            raise ValueError("Logical call budget exhausted")
        self.calls += 1
        self.service._update(self.job_id, calls=self.calls)

    def wait(self, seconds):
        self.checkpoint()
        end = min(self.end, time.monotonic() + max(0, seconds))
        while time.monotonic() < end:
            self.stop_event.wait(min(1, max(0, end - time.monotonic())))
            self.checkpoint()
        self.checkpoint()

    def begin_effect(self):
        self.checkpoint()
        self.effect_started = True
        self.service._update(self.job_id, effect_started=1)


class JobService:
    def __init__(self, path=None, *, capacity=2, history_limit=1000, on_terminal=None):
        if type(history_limit) is not int or not 1 <= history_limit <= 10000:
            raise ValueError("History limit must be 1–10000")
        if type(capacity) is not int or not 1 <= capacity <= 4:
            raise ValueError("Capacity must be 1–4")
        self.path = Path(path or database_path())
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.capacity, self.history_limit = capacity, history_limit
        self._on_terminal = on_terminal
        self._lock = threading.RLock()
        self._workers = {}
        self._closed = False
        self._owner = OwnerLock(self.path.with_suffix(".lock"))
        with self._db() as db:
            db.execute("""CREATE TABLE IF NOT EXISTS jobs(
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, state TEXT NOT NULL,
                created REAL NOT NULL, updated REAL NOT NULL, deadline REAL NOT NULL,
                calls INTEGER NOT NULL, call_limit INTEGER NOT NULL,
                cancel_requested INTEGER NOT NULL, effect_started INTEGER NOT NULL,
                result TEXT NOT NULL)""")
        self.recover()

    @contextlib.contextmanager
    def _db(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            if os.name != "nt":
                self.path.chmod(0o600)
            with db:
                yield db
        finally:
            db.close()

    def recover(self):
        with self._lock:
            if self._closed:
                raise ValueError("Job service closed")
            if self._owner.file is not None:
                return True
            if not self._owner.acquire():
                return False
            try:
                with self._db() as db:
                    db.execute("""UPDATE jobs SET state=CASE WHEN state='queued' THEN 'interrupted'
                        ELSE 'outcome_unknown' END,updated=?,result=?
                        WHERE state IN ('queued','running','cancel_requested')""",
                               (time.time(), json.dumps({"note": "Previous runtime ended. No automatic retry/replay; inspect artifacts before restarting."})))
            except Exception:
                self._owner.release()
                raise
            return True

    def _update(self, job_id, **values):
        allowed = {"state", "calls", "cancel_requested", "effect_started", "result"}
        if not values or values.keys() - allowed:
            raise ValueError("Invalid job update")
        with self._db() as db:
            db.execute("UPDATE jobs SET " + ",".join(f"{key}=?" for key in values) + ",updated=? WHERE id=?",
                       (*values.values(), time.time(), job_id))

    @staticmethod
    def _identifier(job_id):
        if not isinstance(job_id, str) or len(job_id) != 32 or any(c not in "0123456789abcdef" for c in job_id):
            raise ValueError("Use the exact full job ID")

    def get(self, job_id):
        self._identifier(job_id)
        with self._db() as db:
            row = db.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if row is None:
            raise ValueError("Job not found")
        result = dict(row)
        result["result"] = json.loads(result["result"])
        result["overdue"] = result["state"] in ACTIVE and time.time() >= result["deadline"]
        result["cancel_requested"] = bool(result["cancel_requested"])
        return result

    def list(self, maximum=20):
        if type(maximum) is not int or not 1 <= maximum <= 100:
            raise ValueError("Use limit 1–100")
        with self._db() as db:
            rows = db.execute("SELECT id FROM jobs ORDER BY created DESC,id LIMIT ?", (maximum,)).fetchall()
        return [self.get(row["id"]) for row in rows]

    def submit(self, kind, run, *, seconds=120, call_limit=3):
        if kind not in {"swarm_research", "swarm_market", "swarm_system"} or not callable(run):
            raise ValueError("Only host-registered job kinds are admitted")
        if type(seconds) is not int or not 1 <= seconds <= 300 or type(call_limit) is not int or not 1 <= call_limit <= 10:
            raise ValueError("Invalid job budget")
        with self._lock:
            if self._closed or not self.recover():
                raise ValueError("Another runtime owns background jobs, or service is closed")
            # Threads remain here until they return; timeout/cancel never frees a slot early.
            if len(self._workers) >= self.capacity:
                raise ValueError("Background job capacity busy; no work queued")
            with self._db() as db:
                if db.execute("SELECT count(*) FROM jobs").fetchone()[0] >= self.history_limit:
                    raise ValueError("Job journal full; clear terminal metadata explicitly")
                job_id = uuid4().hex
                ctx = JobContext(self, job_id, seconds, call_limit)
                now = time.time()
                db.execute("INSERT INTO jobs VALUES(?,?,'queued',?,?,?,?,?,0,0,'{}')",
                           (job_id, kind, now, now, now + seconds, 0, call_limit))
            try:
                thread = threading.Thread(target=self._run, args=(ctx, run), daemon=True, name=f"job-{job_id[:8]}")
                self._workers[job_id] = (thread, ctx)
                thread.start()
            except Exception:
                self._workers.pop(job_id, None)
                self._update(job_id, state="failed", result='{"note":"Worker could not start; no work attempted."}')
            return self.get(job_id)

    def _run(self, ctx, run):
        state, result = "failed", {"note": "Worker failed; error details omitted."}
        try:
            ctx.checkpoint()
            with self._db() as db:
                admitted = db.execute("UPDATE jobs SET state='running',updated=? WHERE id=? AND state='queued' AND cancel_requested=0",
                                      (time.time(), ctx.job_id)).rowcount
            if not admitted:
                raise JobStopped("cancelled")
            ctx.checkpoint()
            outcome = run(ctx)
            ctx.checkpoint()
            if not isinstance(outcome, dict) or outcome.get("state") not in {"completed", "partial", "failed"}:
                raise ValueError("Invalid host worker outcome")
            candidate = {key: value for key, value in outcome.items() if key != "state"}
            if len(json.dumps(candidate, allow_nan=False)) > 8000:
                raise ValueError("Worker result too large")
            state, result = outcome["state"], candidate
        except JobStopped as error:
            state = "outcome_unknown" if ctx.effect_started else str(error)
            result = {"note": "Stopped cooperatively; no automatic retry. Check artifacts if any effect began."}
        except BaseException:
            state = "outcome_unknown" if ctx.effect_started else "failed"
        finally:
            with self._lock:
                try:
                    # A cancellation can arrive between checkpoint and this lock.
                    with self._db() as db:
                        db.execute("BEGIN IMMEDIATE")
                        row = db.execute("SELECT cancel_requested FROM jobs WHERE id=?", (ctx.job_id,)).fetchone()
                        if state in {"completed", "partial"} and (row[0] or time.monotonic() >= ctx.end):
                            state = "outcome_unknown" if ctx.effect_started else "cancelled" if row[0] else "deadline_exceeded"
                        db.execute("UPDATE jobs SET state=?,result=?,updated=? WHERE id=?",
                                   (state, json.dumps(result), time.time(), ctx.job_id))
                    if self._on_terminal is not None:
                        try:
                            self._on_terminal(ctx.job_id, state)
                        except Exception:
                            pass  # event enqueue failure cannot replay or invalidate the completed job
                finally:
                    self._workers.pop(ctx.job_id, None)
                    if self._closed and not self._workers:
                        self._owner.release()

    def cancel(self, job_id):
        self._identifier(job_id)
        with self._lock:
            self.get(job_id)  # fail on unknown ID, never fuzzy-match
            with self._db() as db:
                changed = db.execute("UPDATE jobs SET cancel_requested=1,state='cancel_requested',updated=? WHERE id=? AND state IN ('queued','running','cancel_requested')",
                                     (time.time(), job_id)).rowcount
            local = self._workers.get(job_id)
            if changed and local:
                local[1].stop_event.set()
            return self.get(job_id)

    def clear_terminal(self):
        with self._lock, self._db() as db:
            result = db.execute("DELETE FROM jobs WHERE state NOT IN ('queued','running','cancel_requested')")
            return result.rowcount  # never deletes reports or active records

    def shutdown(self, timeout=2):
        with self._lock:
            self._closed = True
            workers = list(self._workers.items())
            for job_id, (_thread, ctx) in workers:
                ctx.stop_event.set()
                self._update(job_id, cancel_requested=1, state="cancel_requested")
        deadline = time.monotonic() + max(0, min(timeout, 5))
        for _job_id, (thread, _ctx) in workers:
            thread.join(max(0, deadline - time.monotonic()))
        with self._lock:
            pending = len(self._workers)
            if not pending:
                self._owner.release()
            return {"workers_still_running": pending, "note": "No hard thread termination or replay."}


_SERVICE = None
_SERVICE_LOCK = threading.Lock()


def get_service():
    global _SERVICE
    with _SERVICE_LOCK:
        if _SERVICE is None:
            from ultron.core.local_notifications import enqueue_job_outcome
            _SERVICE = JobService(on_terminal=enqueue_job_outcome)
        return _SERVICE


def shutdown_jobs():
    with _SERVICE_LOCK:
        service = _SERVICE
    return service.shutdown() if service is not None else {"workers_still_running": 0}
