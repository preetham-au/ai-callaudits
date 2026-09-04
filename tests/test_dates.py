"""python -m pytest tests/test_dates.py -q   (or just: python tests/test_dates.py)

The date picker in the UI is only as good as the `date` parameter behind it.
This checks the one thing that would make it look like it works while lying:
that /summary, /calls and /export.csv actually scope to the day asked for, and
that a day with no audits comes back empty rather than falling through to the
newest one.

Builds its own two-day SQLite database; no network, no real audits.
"""
import csv
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import main as M  # noqa: E402
from audit import run as RUN  # noqa: E402

DAY_A, DAY_B, EMPTY = "2026-08-27", "2026-08-30", "2026-08-29"


def build_db() -> Path:
    """The real schema, not a copy of it.

    This fixture used to hand-list the columns, so a column added to
    audit.run.SCHEMA was missing here and every read fell through to an empty
    result -- the API's own reads look identical to "nothing audited yet".
    """
    db = Path(tempfile.mkdtemp()) / "audits.db"
    real, RUN.DB = RUN.DB, db
    try:
        RUN.db().close()
    finally:
        RUN.DB = real
    conn = sqlite3.connect(db)
    # Each call gets a different mix, so a filter that ignores its arguments and
    # returns everything cannot pass.
    def vars_(**kw):
        return json.dumps([{"name": n, "verdict": v} for n, v in kw.items()])

    # duration/disposition vary so the length and voicemail filters have
    # something to separate. NULL duration is the common case in real data --
    # a call that never connected has no length -- and must not clear a
    # "longer than 20s" bar.
    rows = [(DAY_A, 1, 125, "pass", vars_(premium="ok", red="missed"), 45, "hung_up"),
            (DAY_A, 2, 125, "fail", vars_(premium="wrong", red="ok"), None, "voicemail_ivr"),
            (DAY_B, 3, 127, "pass", vars_(premium="ok", red="not_reached"), 12, "voicemail_ivr")]
    for date, iid, agent, verdict, v, dur, disp in rows:
        conn.execute(
            "INSERT INTO calls (interaction_id, audit_date, agent_id, started_at, "
            "duration_s, disposition, turns, score, verdict, variables_failed, "
            "transcript, variables, flow, flags, disposition_check, judge) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (iid, date, agent, f"{date}T10:00:00+05:30", dur, disp, 4, 80.0, verdict, 0,
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

    def n(**kw):
        return M.calls(**kw)["total"]

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

    # The whole point of the filters: the Overview count, the list count and the
    # CSV row count are one query. If they can differ, the operator downloads the
    # sheet to find out which of the three was telling the truth.
    def rows_in(**kw):
        body = M.export_csv(**kw).body.decode("utf-8-sig")
        return len(list(csv.DictReader(io.StringIO(body))))

    for kw in ({"voicemail": "exclude"}, {"voicemail": "only"}, {"min_duration": 20},
               {"voicemail": "exclude", "min_duration": 20}):
        want = M.summary(date=DAY_A, **kw)["totals"]["calls"]
        assert n(date=DAY_A, **kw) == want, (kw, want)
        assert rows_in(date=DAY_A, **kw) == want, (kw, want)

    # Call 1 is 45s and not voicemail; call 2 is voicemail with no duration.
    assert n(date=DAY_A, voicemail="exclude") == 1
    assert n(date=DAY_A, voicemail="only") == 1
    assert n(date=DAY_A, voicemail="exclude") + n(date=DAY_A, voicemail="only") == n(date=DAY_A)
    # An unknown length is not a long call: NULL must not pass the bar.
    assert n(date=DAY_A, min_duration=20) == 1
    assert n(date=DAY_A, min_duration=45) == 0, "strictly greater, not >="
    # 12s, under the bar, so the day empties out rather than falling back to all.
    assert n(date=DAY_B, min_duration=20) == 0
    # An unrecognised value must not silently widen the filter back to everything.
    assert n(date=DAY_A, voicemail="banana") == 2

    print("ok")


if __name__ == "__main__":
    main()


def test_dates_scope_every_read():
    main()
