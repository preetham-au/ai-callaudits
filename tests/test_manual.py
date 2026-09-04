"""python tests/test_manual.py   (or: python -m pytest tests/test_manual.py -q)

The parts of manual.py that can be quietly wrong: who gets which calls. A
reviewer must get ten, never someone else's call, never the same day twice over,
and never an all-Hindi list on a day that had Tamil in it.

Runs against a scratch sqlite file, not data/audits.db.
"""
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import jobs as JB  # noqa: E402

TMP = Path(tempfile.mkdtemp()) / "t.db"
JB.DB = TMP  # before manual imports anything that touches it

from api import manual as M  # noqa: E402

DATE = "2026-08-30"


def _seed(hindi: int, tamil: int, junk: bool = True, other: int = 0) -> None:
    c = sqlite3.connect(TMP)
    c.executescript("""
    CREATE TABLE IF NOT EXISTS calls (
      interaction_id INTEGER PRIMARY KEY, audit_date TEXT, agent_id INTEGER,
      started_at TEXT, duration_s INTEGER, customer_name TEXT, reg_no TEXT,
      policy_no TEXT, provider_sid TEXT, disposition TEXT, disposition_verdict TEXT,
      verdict TEXT, score REAL, turns INTEGER, transcript TEXT, variables TEXT);
    DELETE FROM calls;""")
    i = 1000

    def add(agent, **kw):
        nonlocal i
        i += 1
        row = {"interaction_id": i, "audit_date": DATE, "agent_id": agent,
               "started_at": f"{DATE}T09:00:00+05:30", "duration_s": 180,
               "customer_name": "X", "reg_no": "TN01", "policy_no": "P1",
               "provider_sid": "sid", "disposition": "call_back",
               "disposition_verdict": "pass", "verdict": "pass", "score": 90,
               "turns": 8, "transcript": json.dumps([{"role": "user", "content": "hi"}]),
               "variables": json.dumps([{"name": "red", "expected_raw": "2026-09-07"}])}
        row.update(kw)
        c.execute(f"INSERT INTO calls ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                  list(row.values()))

    for _ in range(hindi):
        add(125)
    for _ in range(tamil):
        add(127)
    # Agent 124 is real and in production: a third id the app has no name for.
    # It is labelled Hindi, so it must be downloadable as Hindi.
    for _ in range(other):
        add(124)
    if junk:
        add(125, verdict="no_transcript", turns=0, duration_s=0)
        add(125, disposition="voicemail_ivr", turns=2, duration_s=25)
        # A real conversation the platform called voicemail: it talks back, and it
        # is exactly what a human should hear -- so it must stay in.
        add(125, disposition="voicemail_ivr", turns=12)
    c.commit()
    c.close()
    with M._db() as x:
        x.execute("DELETE FROM manual_audits")


def _submit_all(*auditors: str) -> int:
    """Fill in every call dealt to these reviewers. The report is submitted rows
    only, so a test that never submits is testing an empty file."""
    n = 0
    for a in auditors:
        for item in M.queue(DATE, a)["items"]:
            M.submit(DATE, a, item["interaction_id"],
                     {"info_accuracy": "Accurate", "verdict": "Pass"})
            n += 1
    return n


def _all():
    with M._db() as c:
        return [dict(r) for r in c.execute(
            "SELECT auditor, interaction_id FROM manual_audits WHERE audit_date=?", (DATE,))]


def test_everyone_gets_ten_and_nobody_shares():
    _seed(90, 10)
    M.ensure_assigned(DATE)
    rows = _all()
    names = [a["name"] for a in M.auditors()]
    assert len(rows) == M.PER_AUDITOR * len(names), len(rows)
    for n in names:
        assert sum(r["auditor"] == n for r in rows) == M.PER_AUDITOR, n
    ids = [r["interaction_id"] for r in rows]
    assert len(set(ids)) == len(ids), "a call was dealt to two reviewers"


def test_running_it_again_changes_nothing():
    _seed(90, 10)
    M.ensure_assigned(DATE)
    before = sorted(map(str, _all()))
    M.ensure_assigned(DATE)
    M.queue(DATE, "HV")  # reads assign too
    assert sorted(map(str, _all())) == before


def test_tamil_reaches_every_reviewer():
    """10% of the day is Tamil, so a 10-call list should hold about one."""
    _seed(270, 30)
    M.ensure_assigned(DATE)
    with M._db() as c:
        by = {}
        for r in c.execute("SELECT m.auditor, calls.agent_id FROM manual_audits m "
                           "JOIN calls ON calls.interaction_id = m.interaction_id "
                           "WHERE m.audit_date=?", (DATE,)):
            by.setdefault(r["auditor"], []).append(r["agent_id"])
    for name, agents in by.items():
        assert 127 in agents, f"{name} got no Tamil call: {agents}"


def test_short_calls_are_a_top_up_not_a_blend():
    """40 proper conversations and a pile of 20-second wrong numbers: the 30
    dealt should all come from the proper ones."""
    _seed(35, 5, junk=False)
    c = sqlite3.connect(TMP)
    for i in range(2000, 2040):
        c.execute("INSERT INTO calls (interaction_id, audit_date, agent_id, verdict, turns, "
                  "duration_s) VALUES (?,?,125,'pass',3,20)",
                  (i, DATE))
    c.commit()
    c.close()
    M.ensure_assigned(DATE)
    assert all(r["interaction_id"] < 2000 for r in _all()), "a short call outranked a real one"


def test_voicemail_and_untranscribed_stay_out():
    _seed(0, 0)  # only the three junk rows
    with M._db() as c:
        pool = M._ordered_pool(c, DATE)
        got = {r["interaction_id"]: r for r in c.execute(
            "SELECT interaction_id, verdict, disposition, turns FROM calls")}
    kept = [got[i] for i in pool]
    assert all(k["verdict"] != "no_transcript" for k in kept)
    # ...and the one voicemail-labelled call that survived is the talkative one.
    assert [k["turns"] for k in kept] == [12], kept


def test_a_thin_day_deals_what_it_has_without_crashing():
    _seed(4, 1, junk=False)
    M.ensure_assigned(DATE)
    rows = _all()
    assert len(rows) == 5
    assert len({r["interaction_id"] for r in rows}) == 5


def test_submit_records_the_reviewers_call_and_refuses_other_peoples():
    _seed(90, 10)
    q = M.queue(DATE, "Preetham")
    iid = q["items"][0]["interaction_id"]
    out = M.submit(DATE, "Preetham", iid, {
        "info_accuracy": "Inaccurate",
        "verdict": "Needs Coaching", "notes": "quoted the wrong RED date"})
    row = next(i for i in out["items"] if i["interaction_id"] == iid)
    assert row["verdict"] == "Needs Coaching" and row["submitted_at"]
    assert out["done"] == 1

    try:
        M.submit(DATE, "Swarna", iid, {"verdict": "Pass"})
    except LookupError:
        pass
    else:
        raise AssertionError("a reviewer submitted against someone else's call")

    try:
        M.submit(DATE, "Preetham", iid, {"verdict": "Brilliant"})
    except ValueError:
        pass
    else:
        raise AssertionError("an off-list verdict was accepted")


def test_report_carries_the_workbook_columns():
    _seed(90, 10)
    done = _submit_all("HV")
    rows = M.report(DATE, DATE)
    assert rows and set(M.REPORT_COLS) == set(rows[0])
    r = rows[0]
    assert r["Call Date"] == DATE and r["Call Time (IST)"] == "09:00"
    assert r["Duration (mm:ss)"] == "3:00"
    assert r["Pre-Call"] == "RED: 2026-09-07"

    # Assignment deals ten to every reviewer the moment a day is opened, so the
    # table holds three times what one reviewer finished. Only the finished rows
    # belong in the file -- the rest would read as blank verdicts on calls
    # nobody had listened to.
    assert len(rows) == done, f"{len(rows)} rows exported, {done} actually submitted"
    assert len(_all()) > done, "the fixture is meant to hold unsubmitted rows too"


def test_a_zero_discount_is_not_a_value_to_quote():
    """NCB/DTD of 0 means the feed sent no discount, so the agent is supposed to
    leave the clause out. Listing "DTD: 0" as a pre-call value told the reviewer
    to listen for a figure that should never have been said."""
    _seed(0, 0, junk=False)
    with sqlite3.connect(TMP) as c:
        c.execute(
            "INSERT INTO calls (interaction_id, audit_date, agent_id, started_at, "
            "duration_s, provider_sid, disposition, verdict, score, turns, transcript, "
            "variables) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (2001, DATE, 125, f"{DATE}T09:00:00+05:30", 180, "sid", "call_back",
             "pass", 90, 8, json.dumps([{"role": "user", "content": "hi"}]),
             json.dumps([{"name": "red", "expected_raw": "2026-09-07"},
                         {"name": "ncb", "expected_raw": "0"},
                         {"name": "dtd", "expected_raw": "0.00"},
                         {"name": "premium", "expected_raw": "null"},
                         {"name": "make", "expected_raw": None}])))
    _submit_all("Preetham")
    pre = M.report(DATE, DATE)[0]["Pre-Call"]
    # Exactly one clause: the only value the feed actually supplied. ("0" cannot
    # be substring-checked here -- the RED date contains one.)
    assert pre == "RED: 2026-09-07", pre
    for gone in ("NCB", "DTD", "PREMIUM", "MAKE", "null"):
        assert gone not in pre, f"{gone!r} still in the pre-call line: {pre!r}"


def test_report_can_be_narrowed_to_one_language():
    """The download filter must cut rows, not just relabel them.

    A filter that returns every row with the Language column merely set looks
    right in the UI and is wrong in the file the reviewer opens.
    """
    # Seeded with a third agent id on purpose: 124 is in the live data and is
    # labelled Hindi. Matching agent_id == 125 exactly put it in NEITHER file.
    _seed(60, 10, other=30)
    _submit_all("HV", "Preetham", "Swarna")
    both = M.report(DATE, DATE)
    hindi = M.report(DATE, DATE, 125)
    tamil = M.report(DATE, DATE, 127)

    assert {r["Language"] for r in hindi} == {"Hindi"}
    assert {r["Language"] for r in tamil} == {"Tamil"}
    # Nothing invented and nothing dropped: the two halves are exactly the whole.
    assert len(hindi) + len(tamil) == len(both)
    assert tamil, "the Tamil half is empty -- the deal or the filter is broken"

    ids = {r["Interaction ID"] for r in both}
    assert {r["Interaction ID"] for r in hindi} | {r["Interaction ID"] for r in tamil} == ids


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("ok", name)
