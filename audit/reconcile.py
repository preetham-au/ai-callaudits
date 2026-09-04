"""Prove a day's reported numbers are real, and that every report agrees.

    python -m audit.reconcile                  # newest audited day
    python -m audit.reconcile --date 2026-09-03
    python -m audit.reconcile --all            # every audited day
    python -m audit.reconcile --offline        # internal checks only, no Metabase

Exit code 1 on any mismatch, so a stale day cannot pass a nightly run quietly.

Every number wrong here so far was wrong *silently*: the 2000-row cap returned
half a day as a complete one, 1,569 rows kept a date they had left, the stored
clocks stayed UTC after the fix landed, and the disposition column collapsed
`hung_up_silent` into `contacted`. None of those raised anything. This is the
check that would have caught all four the day they happened.

Two classes:
  SOURCE   - SQLite against Metabase. Is the day complete, and does the stored
             row still say what the platform says?
  INTERNAL - each report against every other. `/api/dates`, `/api/summary`,
             `/api/calls` and `export.csv` all count the same day; a client who
             adds up two of them must not get two answers.
"""
from __future__ import annotations

import argparse
import csv
import io
import sqlite3
import sys

from .data import fetch_day
from .run import DB, db


class Check:
    """One assertion with the two numbers behind it, so a failure is readable."""

    def __init__(self):
        self.rows: list[tuple[str, str, bool, str]] = []

    def eq(self, group: str, name: str, a, b, a_label="stored", b_label="expected"):
        ok = a == b
        detail = f"{a}" if ok else f"{a_label}={a}  {b_label}={b}  diff={_diff(a, b)}"
        self.rows.append((group, name, ok, detail))
        return ok

    def zero(self, group: str, name: str, n: int, note: str = ""):
        ok = n == 0
        self.rows.append((group, name, ok, "0" if ok else f"{n}{note}"))
        return ok

    @property
    def failed(self):
        return [r for r in self.rows if not r[2]]


def _diff(a, b):
    try:
        return f"{a - b:+}"
    except TypeError:
        return "!="


def _sql(q, args=()):
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    try:
        return [dict(r) for r in conn.execute(q, args)]
    finally:
        conn.close()


def source_checks(c: Check, day: str):
    """SQLite against the platform. Metabase is the only source of truth here."""
    fresh = {int(r["id"]): r for r in fetch_day(day)}
    stored = {r["interaction_id"]: r for r in
              _sql("SELECT interaction_id, started_at, turns, disposition, "
                   "disposition_sub FROM calls WHERE audit_date = ?", (day,))}

    c.eq("SOURCE", "row count", len(stored), len(fresh), "sqlite", "metabase")
    c.zero("SOURCE", "calls missing from sqlite", len(set(fresh) - set(stored)),
           " not fetched - re-run the day")
    c.zero("SOURCE", "calls in sqlite but not metabase", len(set(stored) - set(fresh)),
           " stale - a re-run will drop them")

    both = set(fresh) & set(stored)
    # A transcript that arrived after the audit ran is an unaudited call, not an
    # absent one: `turns` is 0 while the platform now has messages for it.
    c.zero("SOURCE", "transcripts not yet audited",
           sum(1 for i in both
               if bool(fresh[i]["messages"]) and not (stored[i]["turns"] or 0)),
           " - re-run the day")
    # The stored clock is derived at write time, so a row written before the
    # timezone fix keeps its UTC value forever unless the day is re-run.
    c.zero("SOURCE", "started_at disagrees with metabase",
           sum(1 for i in both
               if str(stored[i]["started_at"] or "") != str(fresh[i]["started_at"] or "")),
           " - stale clocks, re-run the day")
    c.zero("SOURCE", "disposition disagrees with metabase",
           sum(1 for i in both
               if str(stored[i]["disposition"] or "") != str(fresh[i]["disposition"] or "")),
           " - re-run the day")


def internal_checks(c: Check, day: str):
    """Every report against every other. No network."""
    from api import main as M

    s = M.summary(day)
    t = s["totals"]
    listed = M.calls(date=day, page_size=1)["total"]
    dates = {d["date"]: d for d in M.dates()}.get(day, {"calls": 0, "audited": 0})
    exported = list(csv.DictReader(io.StringIO(
        M.export_csv(date=day).body.decode("utf-8-sig"))))

    c.eq("INTERNAL", "/api/dates vs /api/summary calls", dates["calls"], t["calls"],
         "dates", "summary")
    c.eq("INTERNAL", "/api/calls total vs /api/summary", listed, t["calls"],
         "calls", "summary")
    c.eq("INTERNAL", "export.csv rows vs /api/summary", len(exported), t["calls"],
         "export", "summary")
    c.eq("INTERNAL", "/api/dates audited vs /api/summary", dates["audited"], t["audited"],
         "dates", "summary")

    # The four verdicts partition the day. If they do not add up, one of them is
    # being counted twice or a fifth value has appeared.
    c.eq("INTERNAL", "pass+warn+fail+no_transcript = calls",
         t["pass"] + t["warn"] + t["fail"] + t["no_transcript"], t["calls"],
         "sum", "calls")
    c.eq("INTERNAL", "audited = calls - no_transcript",
         t["audited"], t["calls"] - t["no_transcript"], "audited", "derived")

    # Per-agent rows are the same day sliced; a call belonging to no agent bucket
    # would vanish from the breakdown while still counting in the total.
    for key in ("calls", "audited", "pass", "warn", "fail"):
        c.eq("INTERNAL", f"by_agent {key} sums to total",
             sum(a[key] for a in s["by_agent"]), t[key], "by_agent", "total")

    # correct/missed/wrong are disjoint by construction; this is what catches it
    # if they stop being.
    bad = [v["name"] for v in s["variables"]
           if v["correct"] + v["missed"] + v["wrong"] != v["required_in"]]
    c.zero("INTERNAL", "variables: correct+missed+wrong = required_in", len(bad),
           f" - {', '.join(bad[:5])}")

    # A variable cannot be required more often than there were calls to require
    # it in; if it is, a call is being counted twice.
    over = [v["name"] for v in s["variables"] if v["required_in"] > t["audited"]]
    c.zero("INTERNAL", "variables: required_in <= audited", len(over),
           f" - {', '.join(over[:5])}")

    # The headline score, recomputed from the rows the export actually contains.
    rows = _sql("SELECT score FROM calls WHERE audit_date = ? AND score IS NOT NULL", (day,))
    want = round(sum(r["score"] for r in rows) / len(rows), 1) if rows else 0.0
    c.eq("INTERNAL", "avg_score recomputed from rows", t["avg_score"], want,
         "reported", "recomputed")

    # Every exported row must carry the clock and the label the client counts on.
    c.zero("INTERNAL", "export rows with no Call_date",
           sum(1 for r in exported if not r["Call_date"]))
    c.zero("INTERNAL", "export Call_date on the wrong day",
           sum(1 for r in exported if r["Call_date"][:10] != day),
           " - re-run the day")

    # The filters are the point of the download button: whatever the Overview
    # says under a filter is what the CSV must contain under the same filter.
    # A filter wired into one endpoint and not the others is invisible until
    # someone adds up two sheets and gets two answers.
    for label, f in (("voicemail only", {"voicemail": "only"}),
                     ("no voicemail", {"voicemail": "exclude"}),
                     ("over 20s", {"min_duration": 20}),
                     ("no voicemail + over 20s", {"voicemail": "exclude", "min_duration": 20}),
                     ("no voicemail + over 20s, Tamil", {"voicemail": "exclude",
                                                         "min_duration": 20, "agent_id": 127})):
        n = M.summary(day, **f)["totals"]["calls"]
        c.eq("FILTERS", f"{label}: /api/calls = summary",
             M.calls(date=day, page_size=1, **f)["total"], n, "calls", "summary")
        c.eq("FILTERS", f"{label}: export.csv = summary",
             len(list(csv.DictReader(io.StringIO(
                 M.export_csv(date=day, **f).body.decode("utf-8-sig"))))), n, "export", "summary")

    # The two halves of a partition must rebuild the whole, or a call is either
    # counted twice or falling through both filters.
    only = M.summary(day, voicemail="only")["totals"]["calls"]
    excl = M.summary(day, voicemail="exclude")["totals"]["calls"]
    c.eq("FILTERS", "voicemail + no-voicemail = all calls", only + excl, t["calls"],
         "split", "total")


def audited_days() -> list[str]:
    return [r["audit_date"] for r in
            _sql("SELECT DISTINCT audit_date FROM calls ORDER BY audit_date")]


def reconcile(day: str, offline: bool) -> Check:
    c = Check()
    internal_checks(c, day)
    if not offline:
        source_checks(c, day)
    return c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date")
    ap.add_argument("--all", action="store_true", help="every audited day")
    ap.add_argument("--offline", action="store_true",
                    help="report-vs-report only; skips Metabase")
    a = ap.parse_args()

    db().close()  # bring the schema up to date before reading it
    days = audited_days() if a.all else [a.date or (audited_days() or [None])[-1]]
    if not days or days == [None]:
        sys.exit("nothing audited yet")

    bad = 0
    for day in days:
        c = reconcile(day, a.offline)
        print(f"\n{day}")
        group = None
        for g, name, ok, detail in c.rows:
            if g != group:
                print(f"  {g}")
                group = g
            print(f"    {'ok  ' if ok else 'FAIL'}  {name:<44} {detail}")
        bad += len(c.failed)
        print(f"  -> {len(c.rows) - len(c.failed)}/{len(c.rows)} checks pass")

    print(f"\n{'MISMATCHES: ' + str(bad) if bad else 'all numbers reconcile'}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
