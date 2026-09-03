"""Orchestration: fetch -> rules -> judge -> SQLite.

One axis only: variable accuracy. Flow and disposition are no longer verified,
so the score is 100% variables and no call can be failed for how the agent
sequenced its script or for the label the platform put on it. Flow detection
still runs, purely so `check_variables` knows how far the call got.


python -m audit.run                 audit AUDIT_DATE
python -m audit.run --date 2026-08-30
python -m audit.run --ids 5681202,5681544
python -m audit.run --no-llm        rules only (fast, for checking the matcher)
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timezone

from . import judge as J
from . import rules as R
from .data import AUDIT_DATE, ENV, ROOT, fetch_day, fetch_ids

DB = ROOT / "data" / "audits.db"

FLAGS = {"missing_variable", "wrong_variable", "short_call", "llm_parse_failed"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT, audit_date TEXT, started_at TEXT,
  finished_at TEXT, calls INTEGER, model TEXT);
CREATE TABLE IF NOT EXISTS calls (
  interaction_id INTEGER PRIMARY KEY, run_id INTEGER, audit_date TEXT, agent_id INTEGER,
  campaign_id INTEGER, campaign_name TEXT, lead_id INTEGER, contact_id TEXT,
  provider_sid TEXT, started_at TEXT, duration_s INTEGER, status TEXT, call_stage TEXT,
  customer_name TEXT, reg_no TEXT, policy_no TEXT, turns INTEGER,
  score REAL, verdict TEXT, variables_checked INTEGER, variables_failed INTEGER,
  flow_score REAL, flags TEXT, disposition TEXT, disposition_verdict TEXT,
  verification_error TEXT, disposition_error TEXT, summary TEXT,
  transcript TEXT, variables TEXT, flow TEXT, disposition_check TEXT, judge TEXT,
  transcript_truncated INTEGER);
CREATE INDEX IF NOT EXISTS calls_date ON calls(audit_date);
-- Cached so a re-run after a scoring change costs nothing in GPU time.
CREATE TABLE IF NOT EXISTS llm_cache (
  interaction_id INTEGER PRIMARY KEY, model TEXT, raw TEXT, parsed TEXT,
  latency_ms INTEGER, error TEXT, est_prompt_tokens INTEGER, created_at TEXT);
"""


def db() -> sqlite3.Connection:
    DB.parent.mkdir(parents=True, exist_ok=True)
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.executescript(SCHEMA)
    return c


def _turns(row) -> list[dict]:
    return [{"role": m.get("role"), "content": str(m.get("content") or "")}
            for m in (row.get("messages") or []) if m.get("role") in ("assistant", "user")]


def _score(vars_):
    """The whole score: what fraction of the checkable variables were said right.

    A call with nothing to check scores 100, not 0 -- there was no opportunity to
    get anything wrong, and a day of short calls must not read as a day of bad
    ones.
    """
    considered = [v for v in vars_ if v["verdict"] in ("ok", "missed", "wrong")]
    if not considered:
        return 100.0, considered
    return round(100.0 * sum(v["verdict"] == "ok" for v in considered) / len(considered), 1), considered


def audit_one(row: dict, llm: bool, cached: dict | None) -> dict:
    av = row.get("additional_variables") or {}
    turns = _turns(row)
    base = {
        "interaction_id": row["id"], "agent_id": row["agent_id"],
        "campaign_id": row["campaign_id"], "campaign_name": row.get("campaign_name"),
        "lead_id": row["lead_id"], "contact_id": str(row.get("contact_id") or "") or None,
        "provider_sid": row.get("provider_sid"),
        "started_at": str(row["created_at"]), "duration_s": row.get("duration_s"),
        "status": row.get("status"), "call_stage": row.get("call_stage"),
        "customer_name": av.get("customer_name"), "reg_no": av.get("reg_no"),
        "policy_no": av.get("policy_no"), "turns": len(turns),
        "disposition": row.get("lead_stage_computed"),
    }
    if not turns:
        return {**base, "score": None, "verdict": "no_transcript", "flow_score": None,
                "variables_checked": 0, "variables_failed": 0, "flags": [],
                "disposition_verdict": None, "verification_error": None,
                "disposition_error": None, "summary": None, "transcript": [],
                "variables": [], "flow": [], "disposition_check": None,
                "judge": {"model": J.MODEL, "latency_ms": None, "raw": None},
                "transcript_truncated": False}

    # Flow is computed for one reason only: it tells check_variables how far the
    # call got, so a call that died in the greeting is not marked down for the
    # six values it never reached. Nothing is scored or flagged on it.
    det = R.detect_flow(turns, row["agent_id"])
    flow = R.flow_rows(turns, row["agent_id"], det)
    vars_ = R.check_variables(turns, av, flow)
    rub = R.load_rubric(row["agent_id"])

    residue = [v for v in vars_ if v["verdict"] == "missed"]
    res = cached
    if res is None and llm:
        res = J.judge(rub, turns, residue)
    res = res or {"ok": False, "parsed": None, "raw": None, "latency_ms": None,
                  "error": "llm_skipped", "transcript_truncated": False}
    p = res.get("parsed") or {}

    flags: list[str] = []
    # The judge may only *clear* a 'missed' — it sees paraphrase the matcher
    # cannot. It may not create a 'wrong': that forces fail, and a 4B's opinion
    # is not evidence enough to call a call non-compliant. Deterministic wins.
    for name, v in (p.get("variables") or {}).items():
        if not isinstance(v, dict):
            continue
        for row_ in vars_:
            if row_["name"] == name and row_["verdict"] == "missed" and v.get("verdict") == "ok":
                row_.update(verdict=v["verdict"], checked_by="llm",
                            note=str(v.get("note") or "")[:120] or None,
                            turn_index=v.get("turn_index") if isinstance(v.get("turn_index"), int) else None,
                            spoken=True)

    score, considered = _score(vars_)
    failed = sum(v["verdict"] in ("missed", "wrong") for v in considered)
    if any(v["verdict"] == "wrong" for v in considered):
        flags.append("wrong_variable")
    if any(v["verdict"] == "missed" for v in considered):
        flags.append("missing_variable")
    if len(turns) <= 2:
        flags.append("short_call")
    if not res.get("ok") and llm:
        flags.append("llm_parse_failed")

    # Saying a wrong value out loud is categorical: the customer heard a figure
    # that was not theirs. Silence is a warn -- bad, but nobody was misinformed.
    if any(v["verdict"] == "wrong" for v in considered):
        verdict = "fail"
    elif failed:
        verdict = "warn"
    else:
        verdict = "pass"

    def _txt(k, fallback=None):
        v = p.get(k)
        return None if not isinstance(v, str) or v.strip().upper() in ("", "NA", "NONE") else v.strip()[:300]

    # Verification findings come from the matcher, never from the judge: on the
    # 20 human-audited calls the judge invented six value errors the rules (and
    # the reviewers) found nothing wrong with. Its wording is reused only to
    # describe a finding the rules already made.
    wrong = [v["name"] for v in considered if v["verdict"] == "wrong"]
    verr = None
    if wrong:
        verr = _txt("verification_error") or ""
        if not all(w.split("_")[0][:3].lower() in verr.lower() for w in wrong):
            verr = ", ".join(w.upper() for w in wrong) + " incorrect"

    # `flow`, `flow_score`, `disposition_verdict`, `disposition_error` and
    # `disposition_check` keep their columns but are no longer written: dropping
    # them would mean migrating a live database for nothing, and leaving them
    # empty makes it obvious the engine has stopped having an opinion rather than
    # leaving a stale one behind.
    return {**base, "score": score, "verdict": verdict, "flow_score": None,
            "variables_checked": len(considered), "variables_failed": failed,
            "flags": sorted(set(flags) & FLAGS), "disposition_verdict": None,
            "verification_error": verr, "disposition_error": None,
            "summary": _txt("summary"),
            "transcript": [{"role": t["role"], "content": t["content"], "index": i}
                           for i, t in enumerate(turns)],
            "variables": vars_, "flow": [], "disposition_check": None,
            "judge": {"model": J.MODEL, "latency_ms": res.get("latency_ms"),
                      "raw": res.get("raw"), "error": res.get("error")},
            "transcript_truncated": bool(res.get("transcript_truncated"))}


_JSON_COLS = ("flags", "transcript", "variables", "flow", "disposition_check", "judge")


def save(conn, run_id: int, date: str, recs: list[dict]):
    cols = [d[1] for d in conn.execute("PRAGMA table_info(calls)")]
    for r in recs:
        row = {**r, "run_id": run_id, "audit_date": date}
        vals = [json.dumps(row.get(c), ensure_ascii=False) if c in _JSON_COLS else row.get(c)
                for c in cols]
        conn.execute(f"INSERT OR REPLACE INTO calls ({','.join(cols)}) "
                     f"VALUES ({','.join('?' * len(cols))})", vals)
    conn.commit()


def _cache_get(conn, iid) -> dict | None:
    r = conn.execute("SELECT * FROM llm_cache WHERE interaction_id=? AND error IS NULL",
                     (iid,)).fetchone()
    if not r:
        return None
    return {"ok": True, "parsed": json.loads(r["parsed"]), "raw": r["raw"],
            "latency_ms": r["latency_ms"], "error": None, "transcript_truncated": False}


def _cache_put(conn, iid, res):
    conn.execute("INSERT OR REPLACE INTO llm_cache VALUES (?,?,?,?,?,?,?,?)",
                 (iid, J.MODEL, res.get("raw"),
                  json.dumps(res.get("parsed"), ensure_ascii=False) if res.get("parsed") else None,
                  res.get("latency_ms"), res.get("error"), res.get("est_prompt_tokens"),
                  datetime.now(timezone.utc).isoformat()))


def run(date: str, ids: list[int] | None = None, llm: bool = True, save_db: bool = True) -> list[dict]:
    rows = fetch_ids(ids) if ids else fetch_day(date)
    conn = db()
    started = datetime.now(timezone.utc).isoformat()
    run_id = conn.execute(
        "INSERT INTO runs (audit_date, started_at, calls, model) VALUES (?,?,?,?)",
        (date, started, len(rows), J.MODEL)).lastrowid
    conn.commit()

    with_tx = [r for r in rows if _turns(r)]
    print(f"{len(rows)} calls, {len(with_tx)} with transcripts", flush=True)

    # One judge call per transcribed call, cached by interaction id.
    cache = {}
    if llm:
        todo = []
        for r in with_tx:
            hit = _cache_get(conn, r["id"])
            if hit:
                cache[r["id"]] = hit
            else:
                todo.append(r)
        print(f"judge: {len(cache)} cached, {len(todo)} to send", flush=True)
        for i in range(0, len(todo), 40):
            chunk = todo[i:i + 40]
            jobs = [(R.load_rubric(r["agent_id"]), _turns(r),
                     [v for v in R.check_variables(_turns(r), r["additional_variables"],
                                                   R.flow_rows(_turns(r), r["agent_id"],
                                                               R.detect_flow(_turns(r), r["agent_id"])))
                      if v["verdict"] == "missed"])
                    for r in chunk]
            t0 = time.time()
            for r, res in zip(chunk, J.judge_many(jobs)):
                cache[r["id"]] = res
                _cache_put(conn, r["id"], res)
            conn.commit()
            print(f"  judged {min(i + 40, len(todo))}/{len(todo)} ({time.time() - t0:.0f}s)", flush=True)

    recs = [audit_one(r, llm, cache.get(r["id"])) for r in rows]
    if save_db:
        save(conn, run_id, date, recs)
    conn.execute("UPDATE runs SET finished_at=? WHERE id=?",
                 (datetime.now(timezone.utc).isoformat(), run_id))
    conn.commit()
    return recs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=AUDIT_DATE)
    ap.add_argument("--ids", default=None)
    ap.add_argument("--no-llm", action="store_true")
    a = ap.parse_args()
    ids = [int(x) for x in a.ids.split(",")] if a.ids else None
    recs = run(a.date, ids, llm=not a.no_llm)
    n = {}
    for r in recs:
        n[r["verdict"]] = n.get(r["verdict"], 0) + 1
    scored = [r["score"] for r in recs if r["score"] is not None]
    wrong = sum("wrong_variable" in r["flags"] for r in recs)
    print(json.dumps({"verdicts": n,
                      "avg_score": round(sum(scored) / len(scored), 1) if scored else None,
                      "calls_with_a_wrong_value": wrong}, indent=2))
    print(J.calibration_report(), file=sys.stderr)


if __name__ == "__main__":
    main()
