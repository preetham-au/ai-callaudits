"""Manual audits: which calls a reviewer gets by hand, and what they said about them.

The engine audits every call in a day. This is the small sample three reviewers
listen to themselves — ten each, from yesterday — and it replaces the
"Chola Call Audits.xlsx" tracker: one sheet per reviewer, ten rows, filled in
from the previous day's calls. The fields and their allowed values are that
sheet's, so the CSV that comes out can go straight where the workbook went.

Assignment is lazy: nothing schedules it. The first time anyone opens a day, the
ten are dealt and written down, and every later read returns the same ten. That
keeps a reviewer's list stable across refreshes without another timer to babysit.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

from api.jobs import IST, check_date
from api.jobs import _db as _jobs_db

PER_AUDITOR = 10

# The three reviewers the workbook has a sheet each for. Seeded once; the table
# is the source of truth afterwards so a name can be added without a deploy.
SEED_AUDITORS = ["Preetham", "HV", "Swarna"]

INFO_ACCURACY = ("Accurate", "Inaccurate")
CALL_FLOW = ("Followed", "Not Followed")
# The workbook's dropdown for the reviewer's own call: it is a judgement on the
# call, not a re-pick of the platform's disposition, which is shown beside it.
VERDICTS = ("Pass", "Needs Coaching", "Escalate", "Incomplete", "Not Applicable")

NOTES_MAX = 2000

SCHEMA = """
CREATE TABLE IF NOT EXISTS auditors (
  name TEXT PRIMARY KEY, active INTEGER NOT NULL DEFAULT 1, seq INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS manual_audits (
  audit_date TEXT NOT NULL,          -- the day the calls were made, not the day reviewed
  auditor TEXT NOT NULL,
  interaction_id INTEGER NOT NULL,
  assigned_at TEXT NOT NULL,
  info_accuracy TEXT, call_flow TEXT, verdict TEXT, notes TEXT,
  submitted_at TEXT,
  PRIMARY KEY (audit_date, auditor, interaction_id));
-- One call belongs to one reviewer on a given day: two people auditing the same
-- call is wasted listening and two contradictory rows in the report.
CREATE UNIQUE INDEX IF NOT EXISTS manual_one_owner
  ON manual_audits(audit_date, interaction_id);
"""

REC_BASE = "https://formi-prod-2.s3.eu-north-1.amazonaws.com/onboarding/"


_ready = False


@contextmanager
def _db():
    """The jobs connection with these tables added — same file, same WAL setup."""
    global _ready
    with _jobs_db() as c:
        if not _ready:
            c.executescript(SCHEMA)
            _ready = True
        yield c


# ---------------------------------------------------------------- auditors ---

def auditors(include_inactive: bool = False) -> list[dict]:
    with _db() as c:
        if not c.execute("SELECT COUNT(*) FROM auditors").fetchone()[0]:
            c.executemany("INSERT INTO auditors (name, seq) VALUES (?,?)",
                          [(n, i) for i, n in enumerate(SEED_AUDITORS)])
        where = "" if include_inactive else " WHERE active = 1"
        return [dict(r) for r in c.execute(
            f"SELECT name, active, seq FROM auditors{where} ORDER BY seq, name")]


def set_auditors(names: list[str]) -> list[dict]:
    """Replaces the roster. Names already holding assignments are deactivated
    rather than deleted, so their finished audits stay in the report."""
    clean = [n.strip() for n in names if n and n.strip()]
    if not clean:
        raise ValueError("at least one auditor is required")
    if len(set(clean)) != len(clean):
        raise ValueError("auditor names must be unique")
    with _db() as c:
        c.execute("UPDATE auditors SET active = 0")
        for i, n in enumerate(clean):
            c.execute("INSERT INTO auditors (name, active, seq) VALUES (?,1,?) "
                      "ON CONFLICT(name) DO UPDATE SET active=1, seq=excluded.seq", (n, i))
    return auditors()


# -------------------------------------------------------------------- pool ---

# A reviewer's ten are meant to be calls worth listening to. A call with no
# transcript never connected; a genuine voicemail is thirty seconds of an
# answering machine. Both are the engine's job, not a person's.
#
# Voicemail is excluded by the platform label *only where the engine agrees* with
# it: `disposition_verdict = 'fail'` on a voicemail label is the rule that fires
# when a real conversation was mislabelled, and those are exactly the calls a
# human most wants to hear.
_POOL = """
SELECT interaction_id, agent_id FROM calls
 WHERE audit_date = ?
   AND verdict != 'no_transcript'
   AND NOT (IFNULL(disposition,'') = 'voicemail_ivr' AND IFNULL(disposition_verdict,'') != 'fail')
   AND turns >= ? AND IFNULL(duration_s, 0) >= ?
"""

# Strict first. A thin day (a half-day of dialling, a bank holiday) then tops up
# from shorter calls rather than handing someone a list of four.
TIERS = ((4, 60), (2, 20))


def _interleave(groups: list[list[int]]) -> list[int]:
    """Round-robin proportional to each group's size.

    So a language that is 12% of the day is roughly 12% of every reviewer's ten,
    rather than absent from all of them — which is how Tamil went unaudited by
    hand for a fortnight while the Hindi campaign filled every sheet.
    """
    groups = [g for g in groups if g]
    pos = [0] * len(groups)
    out: list[int] = []
    while True:
        live = [i for i in range(len(groups)) if pos[i] < len(groups[i])]
        if not live:
            return out
        i = min(live, key=lambda i: pos[i] / len(groups[i]))
        out.append(groups[i][pos[i]])
        pos[i] += 1


def _shuffled(date: str, ids: list[int]) -> list[int]:
    """Stable across processes — Python's own hash() is salted per interpreter,
    so using it here would deal a different ten every time the API restarted."""
    return sorted(ids, key=lambda i: hashlib.md5(f"{date}:{i}".encode()).hexdigest())


def _ordered_pool(c: sqlite3.Connection, date: str) -> list[int]:
    """Tier by tier, language-interleaved within each.

    One flat interleave over both tiers would blend them, and a 20-second
    wrong-number would be dealt ahead of a four-minute conversation on a day
    that had plenty of both. Tier 2 must only ever be a top-up.
    """
    out: list[int] = []
    seen: set[int] = set()
    for turns, secs in TIERS:
        by_agent: dict[int, list[int]] = {}
        for r in c.execute(_POOL, (date, turns, secs)):
            if r["interaction_id"] in seen:
                continue
            seen.add(r["interaction_id"])
            by_agent.setdefault(r["agent_id"], []).append(r["interaction_id"])
        out += _interleave([_shuffled(date, by_agent[a]) for a in sorted(by_agent)])
    return out


# -------------------------------------------------------------- assignment ---

def ensure_assigned(date: str) -> None:
    """Deals each active reviewer up to PER_AUDITOR calls for `date`, once.

    Idempotent: a reviewer who already has ten gets nothing, a reviewer added
    later is dealt from what nobody holds. Never reassigns a call that is
    already someone's — the unique index would refuse it anyway.
    """
    check_date(date)
    names = [a["name"] for a in auditors()]
    if not names:
        return
    with _db() as c:
        held = {r["auditor"]: r["n"] for r in c.execute(
            "SELECT auditor, COUNT(*) n FROM manual_audits WHERE audit_date=? GROUP BY auditor",
            (date,))}
        if all(held.get(n, 0) >= PER_AUDITOR for n in names):
            return
        taken = {r[0] for r in c.execute(
            "SELECT interaction_id FROM manual_audits WHERE audit_date=?", (date,))}
        free = [i for i in _ordered_pool(c, date) if i not in taken]
        now, k = datetime.now(IST).isoformat(), 0
        for name in names:
            for _ in range(PER_AUDITOR - held.get(name, 0)):
                if k >= len(free):
                    return  # the day simply does not hold enough real conversations
                c.execute("INSERT INTO manual_audits "
                          "(audit_date, auditor, interaction_id, assigned_at) VALUES (?,?,?,?)",
                          (date, name, free[k], now))
                k += 1


def default_date() -> str:
    """Yesterday in IST — the day a reviewer comes in to audit."""
    return (datetime.now(IST).date() - timedelta(days=1)).isoformat()


# ------------------------------------------------------------------- reads ---

# Qualified: manual_audits and calls share interaction_id, audit_date and verdict.
_CALL_COLS = ("calls.agent_id, calls.started_at, calls.duration_s, calls.customer_name, "
              "calls.reg_no, calls.policy_no, calls.provider_sid, calls.disposition, "
              "calls.disposition_verdict, calls.verdict AS engine_verdict, calls.score, "
              "calls.turns, calls.transcript, calls.variables")


def _precall(variables_json: str | None) -> str:
    """The injected values, in the workbook's own `RED: ...; DTD: ...` shape."""
    try:
        rows = json.loads(variables_json or "[]")
    except ValueError:
        return ""
    return "; ".join(f"{v['name'].upper()}: {v['expected_raw']}"
                     for v in rows if v.get("expected_raw"))


def _hydrate(r: sqlite3.Row) -> dict:
    d = dict(r)
    d["transcript"] = json.loads(d["transcript"]) if d.get("transcript") else []
    d["pre_call"] = _precall(d.pop("variables", None))
    # Null, not a base URL with nothing on the end: a call the provider never
    # gave a sid for has no recording, and the player should say so rather than
    # offer a link to a 404.
    sid = d.pop("provider_sid", None)
    d["recording_url"] = REC_BASE + sid if sid else None
    d["language"] = "Tamil" if d.get("agent_id") == 127 else "Hindi"
    return d


def queue(date: str, auditor: str) -> dict:
    """One reviewer's ten for a day, with everything needed to audit them."""
    check_date(date)
    ensure_assigned(date)
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT m.*, {_CALL_COLS} FROM manual_audits m "
            "JOIN calls ON calls.interaction_id = m.interaction_id "
            "WHERE m.audit_date=? AND m.auditor=? ORDER BY calls.started_at",
            (date, auditor))]
    items = [_hydrate(r) for r in rows]
    return {"date": date, "auditor": auditor, "items": items,
            "done": sum(1 for i in items if i["submitted_at"]), "assigned": len(items)}


def progress(date: str) -> list[dict]:
    check_date(date)
    ensure_assigned(date)
    with _db() as c:
        by = {r["auditor"]: dict(r) for r in c.execute(
            "SELECT auditor, COUNT(*) assigned, COUNT(submitted_at) done "
            "FROM manual_audits WHERE audit_date=? GROUP BY auditor", (date,))}
    return [{"auditor": a["name"], "assigned": by.get(a["name"], {}).get("assigned", 0),
             "done": by.get(a["name"], {}).get("done", 0)} for a in auditors()]


# ------------------------------------------------------------------ submit ---

def _one_of(value, allowed, field):
    if value in (None, ""):
        return None
    if value not in allowed:
        raise ValueError(f"{field} must be one of {', '.join(allowed)}")
    return value


def submit(date: str, auditor: str, interaction_id: int, body: dict) -> dict:
    """Saves one row. Partial saves are allowed — a reviewer half way through a
    call should not lose the fields they have already picked."""
    check_date(date)
    info = _one_of(body.get("info_accuracy"), INFO_ACCURACY, "info_accuracy")
    flow = _one_of(body.get("call_flow"), CALL_FLOW, "call_flow")
    verdict = _one_of(body.get("verdict"), VERDICTS, "verdict")
    notes = (body.get("notes") or "").strip()[:NOTES_MAX] or None
    # "Submitted" means the reviewer has made their call; notes alone is a draft.
    done = datetime.now(IST).isoformat() if verdict else None
    with _db() as c:
        n = c.execute(
            "UPDATE manual_audits SET info_accuracy=?, call_flow=?, verdict=?, notes=?, "
            "submitted_at=? WHERE audit_date=? AND auditor=? AND interaction_id=?",
            (info, flow, verdict, notes, done, date, auditor, interaction_id)).rowcount
    if not n:
        raise LookupError("that call is not assigned to you")
    return queue(date, auditor)


# ------------------------------------------------------------------ report ---

REPORT_COLS = ["Interaction ID", "Audit Owner", "Language", "Call Date", "Call Time (IST)",
               "Duration (mm:ss)", "Recording URL", "Pre-Call", "Transcript",
               "During-Call Info Accuracy", "Call Flow", "Platform Disposition",
               "Final Disposition", "Notes", "Engine Verdict", "Engine Score", "Submitted At"]


def _mmss(seconds) -> str:
    if seconds in (None, ""):
        return ""
    s = int(seconds)
    return f"{s // 60}:{s % 60:02d}"


def report(date_from: str, date_to: str, agent_id: int | None = None) -> list[dict]:
    """Submitted audits as report rows. `agent_id` narrows to one language.

    Filtered on agent_id rather than the "Language" column it produces: the
    column is derived (127 -> Tamil, everything else Hindi), so matching on the
    word would tie the filter to a label that is only ever computed for display.
    """
    check_date(date_from)
    check_date(date_to)
    where, args = "m.audit_date BETWEEN ? AND ?", [date_from, date_to]
    if agent_id is not None:
        where += " AND calls.agent_id = ?"
        args.append(int(agent_id))
    with _db() as c:
        rows = [dict(r) for r in c.execute(
            f"SELECT m.*, {_CALL_COLS} FROM manual_audits m "
            "JOIN calls ON calls.interaction_id = m.interaction_id "
            f"WHERE {where} "
            "ORDER BY m.audit_date, m.auditor, calls.started_at", args)]
    out = []
    for r in rows:
        h = _hydrate(r)
        started = h.get("started_at") or ""
        out.append({
            "Interaction ID": h["interaction_id"], "Audit Owner": h["auditor"],
            "Language": h["language"], "Call Date": h["audit_date"],
            "Call Time (IST)": started[11:16],
            "Duration (mm:ss)": _mmss(h.get("duration_s")),
            "Recording URL": h["recording_url"] or "", "Pre-Call": h["pre_call"],
            "Transcript": "\n".join(f"{t['role'].upper()}: {t['content']}"
                                    for t in h["transcript"]),
            "During-Call Info Accuracy": h.get("info_accuracy") or "",
            "Call Flow": h.get("call_flow") or "",
            "Platform Disposition": h.get("disposition") or "",
            "Final Disposition": h.get("verdict") or "",
            "Notes": h.get("notes") or "",
            "Engine Verdict": h.get("engine_verdict") or "",
            "Engine Score": h.get("score") if h.get("score") is not None else "",
            "Submitted At": (h.get("submitted_at") or "")[:19].replace("T", " "),
        })
    return out
