"""python -m pytest tests/test_dates.py -q   (or just: python tests/test_dates.py)

The date picker in the UI is only as good as the `date` parameter behind it.
This checks the one thing that would make it look like it works while lying:
that /summary, /calls and /export.csv actually scope to the day asked for, and
that a day with no audits comes back empty rather than falling through to the
newest one.

Builds its own two-day SQLite database; no network, no real audits.
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import main as M  # noqa: E402

DAY_A, DAY_B, EMPTY = "2026-08-27", "2026-08-30", "2026-08-29"

COLS = """interaction_id INTEGER PRIMARY KEY, run_id INTEGER, audit_date TEXT,
agent_id INTEGER, campaign_id INTEGER, campaign_name TEXT, lead_id INTEGER,
contact_id TEXT, provider_sid TEXT, started_at TEXT, duration_s REAL,
status TEXT, call_stage TEXT, customer_name TEXT, reg_no TEXT, policy_no TEXT,
turns INTEGER, score REAL, verdict TEXT, variables_checked INTEGER,
variables_failed INTEGER, flow_score REAL, flags TEXT, disposition TEXT,
disposition_verdict TEXT, verification_error TEXT, disposition_error TEXT,
summary TEXT, transcript TEXT, variables TEXT, flow TEXT,
disposition_check TEXT, judge TEXT, transcript_truncated INTEGER"""


def build_db() -> Path:
    db = Path(tempfile.mkdtemp()) / "audits.db"
    conn = sqlite3.connect(db)
    conn.execute(f"CREATE TABLE calls ({COLS})")
    # Each call gets a different mix, so a filter that ignores its arguments and
    # returns everything cannot pass.
    def vars_(**kw):
        return json.dumps([{"name": n, "verdict": v} for n, v in kw.items()])

    rows = [(DAY_A, 1, 125, "pass", vars_(premium="ok", red="missed")),
            (DAY_A, 2, 125, "fail", vars_(premium="wrong", red="ok")),
            (DAY_B, 3, 127, "pass", vars_(premium="ok", red="not_reached"))]
    for date, iid, agent, verdict, v in rows:
        conn.execute(
            "INSERT INTO calls (interaction_id, audit_date, agent_id, started_at, "
            "turns, score, verdict, variables_failed, transcript, variables, flow, "
            "flags, disposition_check, judge) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, date, agent, f"{date}T10:00:00+05:30", 4, 80.0, verdict, 0,
             json.dumps([{"role": "agent", "content": "hi"}]), v, "[]", "[]",
             "{}", "{}"))
    conn.commit()
    conn.close()
    return db


def main() -> None:
    M.DB = build_db()

    assert M.latest_date() == DAY_B, "latest_date must be the newest audited day"

    days = {d["date"]: d for d in M.dates()}
    assert set(days) == {DAY_A, DAY_B}, days
    assert days[DAY_A]["calls"] == 2 and days[DAY_B]["calls"] == 1, days

    # The whole point of the picker: an older day must not return the newest.
    a = M.summary(DAY_A)
    assert a["date"] == DAY_A and a["totals"]["calls"] == 2, a["totals"]
    assert a["totals"]["pass"] == 1 and a["totals"]["fail"] == 1, a["totals"]

    # The four count columns are printed side by side, so they must be disjoint
    # and add up. They did not: "spoken" was ok+wrong, over-counting every row.
    v = {d["name"]: d for d in a["variables"]}
    for d in v.values():
        assert d["correct"] + d["missed"] + d["wrong"] == d["required_in"], d
    # Accuracy is out of what was SPOKEN. premium: 1 ok of 1 ok + 1 wrong.
    assert (v["premium"]["required_in"], v["premium"]["accuracy"]) == (2, 50.0), v["premium"]
    # red: 1 ok, 1 never spoken. The silence shows in its own column and does
    # not score -- 100.0, not 50.0.
    assert (v["red"]["missed"], v["red"]["accuracy"]) == (1, 100.0), v["red"]

    b = M.summary(DAY_B)
    assert b["date"] == DAY_B and b["totals"]["calls"] == 1, b["totals"]

    # No date at all still falls back to the newest, as it did before.
    assert M.summary(None)["date"] == DAY_B

    # A day nothing was audited on is empty, NOT a silent fallback to DAY_B.
    e = M.summary(EMPTY)
    assert e["date"] == EMPTY and e["totals"]["calls"] == 0, e["totals"]
    assert e["by_agent"] == [] and e["variables"] == [], e

    # q_ passed explicitly: called as a plain function its default is FastAPI's
    # Query object, which only resolves to None inside a real request.
    def n(**kw):
        return M.calls(q_=None, **kw)["total"]

    # Clicking a count on the Overview lands here: the calls behind that number.
    assert n(date=DAY_A, variable="premium") == 1, "only call 2 got premium wrong"
    assert n(date=DAY_A, variable="premium", variable_verdict="wrong") == 1
    assert n(date=DAY_A, variable="premium", variable_verdict="missed") == 0
    assert n(date=DAY_A, variable="red") == 1, "only call 1 missed red"
    assert n(date=DAY_A, variable="red", variable_verdict="missed") == 1
    # 'not_reached' is not an error: nobody had the chance to say it.
    assert n(date=DAY_B, variable="red") == 0
    assert n(date=DAY_A, variable="no_such_variable") == 0
    # Composes with the other filters rather than replacing them.
    assert n(date=DAY_A, variable="premium", verdict="fail") == 1
    assert n(date=DAY_A, variable="premium", verdict="pass") == 0
    assert n(date=DAY_A, variable="premium", agent_id=127) == 0
    # An unknown verdict word must not silently widen the filter to everything.
    assert n(date=DAY_A, variable="premium", variable_verdict="banana") == 1

    assert n(date=DAY_A) == 2
    assert n(date=DAY_B) == 1
    assert n(date=EMPTY) == 0
    assert n() == 1, "no date still means the newest day"
    # Date and the other filters compose, rather than one overriding the other.
    assert n(date=DAY_A, agent_id=125) == 2
    assert n(date=DAY_A, agent_id=127) == 0
    assert n(date=DAY_A, verdict="fail") == 1

    csv_a = M.export_csv(date=DAY_A).body.decode("utf-8")
    assert csv_a.count("\n") >= 3, "header plus two rows"
    assert M.export_csv(date=EMPTY).body.decode("utf-8").count("2026") == 0

    print("ok")


if __name__ == "__main__":
    main()


def test_dates_scope_every_read():
    main()
