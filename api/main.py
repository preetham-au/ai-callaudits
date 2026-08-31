"""HTTP API. Reads only what audit.run wrote — no auditing happens here.

uvicorn api.main:app --host 127.0.0.1 --port 8085
"""
from __future__ import annotations

import csv
import io
import json
import sqlite3
from collections import defaultdict
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from api import jobs as JOBS
from audit.data import AUDIT_DATE, ROOT
from audit.judge import MODEL, TRANSCRIPT_BUDGET, est_tokens
from audit.run import DB


@asynccontextmanager
async def lifespan(_app: FastAPI):
    JOBS.startup()
    yield


app = FastAPI(title="Chola call audits", lifespan=lifespan)
WEB = ROOT / "web" / "dist"

AGENTS = {125: ("Simran", "Hindi"), 127: ("Aarthi", "Tamil")}
_J = ("flags", "transcript", "variables", "flow", "disposition_check", "judge")


def q(sql: str, args=()) -> list[dict]:
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        rows = [dict(r) for r in conn.execute(sql, args)]
    except sqlite3.OperationalError:  # nothing audited yet
        return []
    finally:
        conn.close()
    for r in rows:
        for k in _J:
            if k in r:
                r[k] = json.loads(r[k]) if r[k] else ([] if k != "judge" else {})
    return rows


LIST_COLS = ("interaction_id, agent_id, campaign_id, lead_id, started_at, duration_s, status, "
             "call_stage, customer_name, reg_no, policy_no, turns, score, verdict, "
             "variables_checked, variables_failed, flow_score, flags, disposition, "
             "disposition_verdict, verification_error, disposition_error, summary")


def _filters(date, agent_id, verdict, text):
    where, args = ["audit_date = ?"], [date]
    if agent_id:
        where.append("agent_id = ?"); args.append(agent_id)
    if verdict:
        where.append("verdict = ?"); args.append(verdict)
    if text:
        where.append("(IFNULL(reg_no,'') LIKE ? OR IFNULL(policy_no,'') LIKE ? "
                     "OR IFNULL(customer_name,'') LIKE ? OR CAST(interaction_id AS TEXT) LIKE ?)")
        args += [f"%{text}%"] * 4
    return " AND ".join(where), args


def latest_date() -> str:
    """The newest day that has been audited.

    Not AUDIT_DATE: once the nightly schedule is on, the .env date is frozen at
    whatever day the service was deployed and every screen would keep showing it
    while fresh audits piled up behind it.
    """
    r = q("SELECT MAX(audit_date) d FROM calls")
    return (r[0]["d"] if r and r[0]["d"] else None) or AUDIT_DATE


@app.get("/api/health")
def health():
    date = latest_date()
    n = q("SELECT COUNT(*) c FROM calls WHERE audit_date = ?", (date,))
    return {"ok": True, "model": MODEL, "audit_date": date,
            "calls_audited": n[0]["c"] if n else 0,
            "running_job": JOBS.current()}


@app.get("/api/dates")
def dates():
    return q("SELECT audit_date AS date, COUNT(*) AS calls, "
             "SUM(verdict != 'no_transcript') AS audited "
             "FROM calls GROUP BY audit_date ORDER BY audit_date DESC")


@app.get("/api/summary")
def summary(date: str | None = None):
    date = date or latest_date()
    rows = q(f"SELECT {LIST_COLS} FROM calls WHERE audit_date = ?", (date,))
    det = q("SELECT variables, flow FROM calls WHERE audit_date = ? AND turns > 0", (date,))
    aud = [r for r in rows if r["verdict"] != "no_transcript"]
    scored = [r["score"] for r in aud if r["score"] is not None]

    def bucket(rs):
        s = [r["score"] for r in rs if r["score"] is not None]
        return {"calls": len(rs), "audited": sum(r["verdict"] != "no_transcript" for r in rs),
                "pass": sum(r["verdict"] == "pass" for r in rs),
                "warn": sum(r["verdict"] == "warn" for r in rs),
                "fail": sum(r["verdict"] == "fail" for r in rs),
                "avg_score": round(sum(s) / len(s), 1) if s else 0.0}

    disp = defaultdict(lambda: {"calls": 0, "wrong": 0})
    for r in aud:
        d = disp[r["disposition"] or "(none)"]
        d["calls"] += 1
        d["wrong"] += r["disposition_verdict"] == "fail"

    var = defaultdict(lambda: {"required_in": 0, "spoken": 0, "missed": 0, "wrong": 0})
    step = {}
    for r in det:
        for v in r["variables"]:
            if v["verdict"] not in ("ok", "missed", "wrong"):
                continue
            s = var[v["name"]]
            s["required_in"] += 1
            s["spoken"] += v["verdict"] in ("ok", "wrong")
            s["missed"] += v["verdict"] == "missed"
            s["wrong"] += v["verdict"] == "wrong"
        for f in r["flow"]:
            s = step.setdefault(f["step"], {"step": f["step"], "label": f["label"],
                                            "reached": 0, "correct": 0, "skipped": 0})
            if f["required"] or f["observed"]:
                s["reached"] += 1
            s["correct"] += f["observed"]
            s["skipped"] += f["required"] and not f["observed"]

    return {
        "date": date,
        "totals": {**bucket(rows), "no_transcript": sum(r["verdict"] == "no_transcript" for r in rows),
                   "avg_score": round(sum(scored) / len(scored), 1) if scored else 0.0,
                   "disposition_wrong": sum(r["disposition_verdict"] == "fail" for r in aud)},
        "dispositions": sorted(
            ({"assigned": k, "calls": v["calls"], "wrong": v["wrong"],
              "accuracy": round((v["calls"] - v["wrong"]) / v["calls"], 3) if v["calls"] else 0.0}
             for k, v in disp.items()), key=lambda d: -d["calls"]),
        "by_agent": [{"agent_id": a, "name": AGENTS.get(a, ("?", "?"))[0],
                      "language": AGENTS.get(a, ("?", "?"))[1],
                      **bucket([r for r in rows if r["agent_id"] == a])}
                     for a in sorted({r["agent_id"] for r in rows})],
        "variables": sorted(
            ({"name": k, **v,
              "accuracy": round((v["required_in"] - v["missed"] - v["wrong"]) / v["required_in"], 3)
              if v["required_in"] else 0.0} for k, v in var.items()),
            key=lambda d: d["accuracy"]),
        "flow": [step[k] for k in sorted(step)],
    }


@app.get("/api/calls")
def calls(date: str | None = None, agent_id: int | None = None, verdict: str | None = None,
          q_: str | None = Query(None, alias="q"), page: int = 1, page_size: int = 50):
    where, args = _filters(date or latest_date(), agent_id, verdict, q_)
    total = q(f"SELECT COUNT(*) c FROM calls WHERE {where}", args)
    page, page_size = max(1, page), min(max(1, page_size), 500)
    items = q(f"SELECT {LIST_COLS} FROM calls WHERE {where} ORDER BY started_at, interaction_id "
              f"LIMIT ? OFFSET ?", (*args, page_size, (page - 1) * page_size))
    for it in items:
        it.pop("policy_no", None)
    return {"items": items, "page": page, "page_size": page_size,
            "total": total[0]["c"] if total else 0}


@app.get("/api/calls/{interaction_id}")
def call_detail(interaction_id: int):
    rows = q("SELECT * FROM calls WHERE interaction_id = ?", (interaction_id,))
    if not rows:
        raise HTTPException(404, "unknown interaction")
    r = rows[0]
    for k in ("run_id", "audit_date", "contact_id", "provider_sid", "campaign_name"):
        r.pop(k, None)
    # `turns` stays the true count; the flag tells the UI it is showing a subset.
    r["transcript_truncated"] = bool(r.get("transcript_truncated")) or \
        est_tokens("\n".join(t["content"] for t in r["transcript"])) > TRANSCRIPT_BUDGET
    return r


CSV_COLS = ["interaction_id", "contact_id", "campaign_name", "Call_date", "", "transcript",
            "customer_name", "call_stage", "call_recording_url", "call_duration",
            "Calling Summary", "Verfication Error", "Dispostion Error", "Remarks", "policy_no"]
REC_BASE = "https://formi-prod-2.s3.eu-north-1.amazonaws.com/onboarding/"


@app.get("/api/export.csv")
def export_csv(date: str | None = None, agent_id: int | None = None, verdict: str | None = None):
    date = date or latest_date()
    where, args = _filters(date, agent_id, verdict, None)
    rows = q(f"SELECT * FROM calls WHERE {where} ORDER BY started_at, interaction_id", args)
    buf = io.StringIO()
    w = csv.DictWriter(buf, CSV_COLS, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({
            "interaction_id": r["interaction_id"], "contact_id": r["contact_id"] or "",
            "campaign_name": r["campaign_name"] or "", "Call_date": "", "": "",
            "transcript": "\n".join(f"{t['role'].upper()}: {t['content']}" for t in r["transcript"]),
            "customer_name": r["customer_name"] or "", "call_stage": r["call_stage"] or "",
            "call_recording_url": REC_BASE + (r["provider_sid"] or ""),
            "call_duration": r["duration_s"] if r["duration_s"] is not None else "",
            "Calling Summary": r["summary"] or "",
            "Verfication Error": r["verification_error"] or "NA",
            "Dispostion Error": r["disposition_error"] or "NA",
            "Remarks": "", "policy_no": r["policy_no"] or "",
        })
    return Response(
        # BOM so Excel opens the Devanagari/Tamil transcript column correctly.
        content="﻿" + buf.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="call_audits_{date}.csv"'})


@app.get("/api/runs")
def runs():
    return q("SELECT id, audit_date, started_at, finished_at, calls, model "
             "FROM runs ORDER BY id DESC")


class StartJob(BaseModel):
    date: str | None = None


class ScheduleIn(BaseModel):
    enabled: bool
    time: str
    target: str = "today"


@app.get("/api/jobs")
def list_jobs(limit: int = 20):
    return {"items": JOBS.jobs(limit), "running": JOBS.current(),
            "default_date": JOBS.default_date()}


@app.post("/api/jobs", status_code=201)
def start_job(body: StartJob):
    try:
        return JOBS.start(body.date or JOBS.default_date(), "manual")
    except JOBS.Busy as e:
        # 409, not 500: nothing is broken, the operator just has to wait.
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/api/jobs/{job_id}")
def get_job(job_id: int, tail: int = 200):
    j = JOBS.job(job_id, tail)
    if not j:
        raise HTTPException(404, "unknown job")
    return j


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: int):
    j = JOBS.cancel(job_id)
    if not j:
        raise HTTPException(404, "unknown job")
    return j


@app.get("/api/schedule")
def get_schedule():
    return JOBS.schedule()


@app.put("/api/schedule")
def put_schedule(body: ScheduleIn):
    try:
        return JOBS.set_schedule(body.enabled, body.time, body.target)
    except ValueError as e:
        raise HTTPException(422, str(e))


@app.get("/{path:path}")
def spa(path: str):
    """Serve the built UI if it exists; index.html for client-side routes."""
    if path.startswith("api/"):
        raise HTTPException(404, "unknown endpoint")
    f = (WEB / path) if path else None
    if f is not None and f.is_file() and WEB in f.resolve().parents:
        return FileResponse(f)
    index = WEB / "index.html"
    if index.is_file():
        return FileResponse(index)
    return Response("UI not built yet — run `npm run build` in web/.", media_type="text/plain")
