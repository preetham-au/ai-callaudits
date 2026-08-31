"""Deciding *when* an audit runs. The audit itself is still `audit.run`.

Two triggers: an operator pressing "Run now", and a nightly schedule. Both end
up in the same place — a `python -m audit.run --date X` subprocess, one at a
time, with its output kept so a failed night can be read the next morning.

Why a subprocess rather than calling `run()` on a thread: an audit that dies
(OOM on a long transcript, a Metabase error that escapes the retry loop) then
takes only its own process down, and the API keeps serving the dashboard. It
also means the CLI stays the single definition of what an audit is.
"""
from __future__ import annotations

import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from contextlib import contextmanager
from datetime import date as Date
from datetime import datetime, time as Time, timedelta
from zoneinfo import ZoneInfo

from audit.data import ROOT
from audit.run import DB

# The calls are dialled in India, so "last night" and "today's calls" only mean
# anything in IST. The VM's own clock is UTC and must not be used here.
IST = ZoneInfo("Asia/Kolkata")
LOGS = ROOT / "data" / "job_logs"

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, audit_date TEXT NOT NULL, trigger TEXT NOT NULL,
  status TEXT NOT NULL, started_at TEXT, finished_at TEXT, exit_code INTEGER,
  pid INTEGER, log_name TEXT);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""

DEFAULTS = {
    "schedule_enabled": "0",
    "schedule_time": "23:30",
    # Which day's calls a nightly run audits: the day it fires, or the one before.
    "schedule_target": "today",
    "schedule_last_fired": "",
}

STATUS_RUNNING = "running"


class Busy(RuntimeError):
    """An audit is already running. Two at once would fight over the same rows."""


def check_date(d: str) -> str:
    """`fetch_day` interpolates the date straight into SQL, so it is validated here."""
    if not DATE_RE.match(d or ""):
        raise ValueError("date must be YYYY-MM-DD")
    Date.fromisoformat(d)  # rejects 2026-13-40
    return d


@contextmanager
def _db():
    c = sqlite3.connect(DB, timeout=30)
    c.row_factory = sqlite3.Row
    # The audit subprocess writes to this file for minutes at a stretch. Without
    # WAL every dashboard read during a run risks "database is locked".
    c.execute("PRAGMA journal_mode=WAL")
    c.executescript(SCHEMA)
    try:
        yield c
        c.commit()
    finally:
        c.close()


# ---------------------------------------------------------------- settings ---

def _settings() -> dict:
    with _db() as c:
        have = {r["key"]: r["value"] for r in c.execute("SELECT key, value FROM settings")}
    return {**DEFAULTS, **{k: v for k, v in have.items() if k in DEFAULTS}}


def _write(vals: dict) -> None:
    with _db() as c:
        c.executemany("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                      [(k, str(v)) for k, v in vals.items() if k in DEFAULTS])


def _at(day: Date, hhmm: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(day, Time(h, m), IST)


def _target_date(s: dict, now: datetime) -> str:
    day = now.date() if s["schedule_target"] == "today" else now.date() - timedelta(days=1)
    return day.isoformat()


def schedule() -> dict:
    s = _settings()
    now = datetime.now(IST)
    nxt = _at(now.date(), s["schedule_time"])
    if nxt <= now or s["schedule_last_fired"] == now.date().isoformat():
        nxt += timedelta(days=1)
    return {
        "enabled": s["schedule_enabled"] == "1",
        "time": s["schedule_time"],
        "target": s["schedule_target"],
        "timezone": "Asia/Kolkata",
        "last_fired": s["schedule_last_fired"] or None,
        "next_run": nxt.isoformat() if s["schedule_enabled"] == "1" else None,
        "next_target_date": _target_date(s, nxt) if s["schedule_enabled"] == "1" else None,
    }


def set_schedule(enabled: bool, hhmm: str, target: str) -> dict:
    if not TIME_RE.match(hhmm or ""):
        raise ValueError("time must be HH:MM, 24-hour")
    if target not in ("today", "yesterday"):
        raise ValueError("target must be 'today' or 'yesterday'")
    _write({"schedule_enabled": "1" if enabled else "0",
            "schedule_time": hhmm, "schedule_target": target})
    return schedule()


# -------------------------------------------------------------------- jobs ---

_lock = threading.Lock()
_proc: subprocess.Popen | None = None


def _row(r: sqlite3.Row) -> dict:
    d = dict(r)
    d.pop("log_name", None)
    started, finished = d.get("started_at"), d.get("finished_at")
    d["duration_s"] = round((datetime.fromisoformat(finished) - datetime.fromisoformat(started))
                            .total_seconds()) if started and finished else None
    return d


def jobs(limit: int = 20) -> list[dict]:
    with _db() as c:
        return [_row(r) for r in c.execute(
            "SELECT * FROM jobs ORDER BY id DESC LIMIT ?", (max(1, min(limit, 200)),))]


def _tail(log_name: str | None, lines: int) -> str:
    if not log_name:
        return ""
    f = LOGS / log_name
    if not f.is_file():
        return ""
    with f.open("rb") as fh:  # only the tail: a judged-in-chunks log grows steadily
        fh.seek(0, os.SEEK_END)
        fh.seek(max(0, fh.tell() - 16_384))
        text = fh.read().decode("utf-8", "replace")
    return "\n".join(text.splitlines()[-lines:])


def job(jid: int, tail: int = 200) -> dict | None:
    with _db() as c:
        r = c.execute("SELECT * FROM jobs WHERE id = ?", (jid,)).fetchone()
    if not r:
        return None
    return {**_row(r), "log": _tail(r["log_name"], tail)}


def current() -> dict | None:
    with _db() as c:
        r = c.execute("SELECT * FROM jobs WHERE status = ? ORDER BY id DESC LIMIT 1",
                      (STATUS_RUNNING,)).fetchone()
    return _row(r) if r else None


def start(audit_date: str, trigger: str = "manual") -> dict:
    global _proc
    check_date(audit_date)
    with _lock:
        if _proc is not None and _proc.poll() is None:
            raise Busy("an audit is already running")
        LOGS.mkdir(parents=True, exist_ok=True)
        with _db() as c:
            jid = c.execute(
                "INSERT INTO jobs (audit_date, trigger, status, started_at) VALUES (?,?,?,?)",
                (audit_date, trigger, STATUS_RUNNING, datetime.now(IST).isoformat())).lastrowid
        name = f"job-{jid}.log"
        fh = (LOGS / name).open("wb")
        # No start_new_session: the child stays in the API's cgroup so systemd
        # takes it down with the service. Otherwise a restart would orphan an
        # audit that keeps writing rows nothing is tracking.
        p = subprocess.Popen([sys.executable, "-u", "-m", "audit.run", "--date", audit_date],
                             cwd=ROOT, stdout=fh, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL,
                             env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        with _db() as c:
            c.execute("UPDATE jobs SET pid=?, log_name=? WHERE id=?", (p.pid, name, jid))
        _proc = p
        threading.Thread(target=_reap, args=(p, fh, jid), daemon=True).start()
    return job(jid)


def _reap(p: subprocess.Popen, fh, jid: int) -> None:
    rc = p.wait()
    fh.close()
    status = "done" if rc == 0 else "cancelled" if rc < 0 else "failed"
    with _db() as c:
        c.execute("UPDATE jobs SET status=?, exit_code=?, finished_at=? WHERE id=?",
                  (status, rc, datetime.now(IST).isoformat(), jid))


def cancel(jid: int) -> dict | None:
    with _lock:
        row = job(jid, tail=0)
        if row and row["status"] == STATUS_RUNNING and _proc is not None and _proc.poll() is None:
            _proc.terminate()
    return job(jid, tail=0)


# --------------------------------------------------------------- scheduler ---

def _maybe_fire(now: datetime | None = None) -> None:
    """The whole scheduler. `now` is a parameter so it can be tested off-clock."""
    s = _settings()
    if s["schedule_enabled"] != "1":
        return
    now = now or datetime.now(IST)
    today = now.date().isoformat()
    if s["schedule_last_fired"] == today or now < _at(now.date(), s["schedule_time"]):
        return
    try:
        start(_target_date(s, now), "schedule")
    except Busy:
        return  # a manual run has the slot; the next tick tries again
    _write({"schedule_last_fired": today})


def _loop() -> None:
    # ponytail: no catch-up window. If the service is down for the whole evening
    # and returns the next day, that night is skipped and the operator presses
    # Run now. Add a window if that ever actually bites.
    while True:
        time.sleep(30)
        try:
            _maybe_fire()
        except Exception as e:  # a bad setting must not kill the scheduler
            print(f"[schedule] {e!r}", file=sys.stderr, flush=True)


def startup() -> None:
    """Reconcile, then start the clock. Called once, from the app's lifespan."""
    with _db() as c:
        c.execute("UPDATE jobs SET status='interrupted', finished_at=? WHERE status=?",
                  (datetime.now(IST).isoformat(), STATUS_RUNNING))
    threading.Thread(target=_loop, daemon=True).start()


def default_date() -> str:
    """Yesterday in IST — what an operator most often wants to audit by hand."""
    return (datetime.now(IST).date() - timedelta(days=1)).isoformat()
