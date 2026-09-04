"""python -m pytest tests/ -q   (or just: python tests/test_audit.py)

Real fixtures, from calls that actually ran: the two spoken transformations
CONTRACT documents, the wrong-value case that must force `fail`, and the
variable checks graded against the human sheet's own labels.
"""
import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit import rules as R  # noqa: E402


def test_spoken_forms():
    assert R.spoken_reg("OD-27-C-4962") == "O-D two-seven C four-nine-six-two"
    assert R.expected_spoken("red", "02-Sep") == "two September"
    assert R.expected_spoken("dtd", "eighty five").startswith("eighty-five")
    assert R.words_to_num("six thousand eight hundred twenty six") == 6826
    assert R.to_int("26113") == 26113                    # the feed sends digits too
    assert R.words_of(91894) == "ninety-one thousand eight hundred ninety-four"
    assert R.parse_red("Friday, August 21, 2026") == (21, 8)
    assert R.parse_red("08-09-2026") == (8, 9)           # day-first, per live data


def test_matcher_finds_and_faults_values():
    # Interaction 5680387: the feed said 21 August, the agent said "चार August".
    turns = [{"role": "assistant", "content": "आपकी Ashok Leyland की Chola MS policy चार August "
                                              "twenty twenty-six को expire हो रही है"}]
    v, i, ev = R._find_date(turns, 21, 8)
    assert (v, i) == ("wrong", 0) and "August" in ev
    assert R._find_date(turns, 4, 8)[0] == "ok"          # Devanagari day word still matches
    # Interaction 5681062: premium 7655 read out in Devanagari — not found, not faulted.
    assert R._find_money([{"role": "assistant", "content": "premium है सात हज़ार छः सौ पचपन rupees."}],
                         7655)[0] == "missed"
    assert R._find_money([{"role": "assistant", "content": "premium is seven thousand six hundred "
                                                           "fifty-five rupees"}], 7655)[0] == "ok"


def test_wrong_value_forces_fail():
    from audit.run import audit_one
    row = {"id": 1, "agent_id": 125, "campaign_id": 1, "lead_id": 1, "contact_id": "x",
           "provider_sid": "s", "created_at": "2026-08-30", "status": "done", "call_stage": None,
           "lead_stage_computed": "lead_link_sent_online", "duration_s": 60,
           "additional_variables": {"customer_name": "Asha", "make": "Maruti", "model": "Swift",
                                    "reg_no": "OD01AP4344", "red": "02-09-2026",
                                    "ncb": "20", "dtd": "70", "premium": "10693"},
           "messages": [
               {"role": "assistant", "content": "Simran from Cholamandalam MS, Asha जी?"},
               {"role": "user", "content": "हां"},
               {"role": "assistant", "content": "record की जा रही है। आपकी Maruti Swift, number "
                "O-D zero-one A-P four-three-four-four, policy two September को expire"},
               {"role": "user", "content": "ठीक है बताइए"},
               {"role": "assistant", "content": "आपको twenty percent एन-सी-बी और seventy percent "
                "de-tariff discount, renewal premium है nine thousand rupees"},
               {"role": "user", "content": "हां भेज दीजिए"},
               {"role": "assistant", "content": "Link आपके WhatsApp पर भेज दिया है। धन्यवाद।"}]}
    rec = audit_one(row, llm=False, cached=None)
    prem = [v for v in rec["variables"] if v["name"] == "premium"][0]
    assert prem["verdict"] == "wrong"           # 9000 spoken, 10693 injected
    assert rec["verdict"] == "fail" and "wrong_variable" in rec["flags"]
    assert rec["score"] < 100


def test_silence_is_reported_but_not_scored():
    """Accuracy answers one question: when the agent read a value out, was it the
    customer's value? A value never spoken has nothing to be accurate about, so
    it must not move the number -- but it must still hold the call at warn."""
    from audit.run import _score
    v = lambda name, verdict: {"name": name, "verdict": verdict}  # noqa: E731

    assert _score([v("a", "ok"), v("b", "ok")])[0] == 100.0
    assert _score([v("a", "ok"), v("b", "missed")])[0] == 100.0, "silence must not score"
    assert _score([v("a", "ok"), v("b", "wrong")])[0] == 50.0
    assert _score([v("a", "ok"), v("b", "wrong"), v("c", "missed")])[0] == 50.0
    # Nothing spoken at all: no opportunity to get anything wrong.
    assert _score([v("a", "missed"), v("b", "not_reached")])[0] == 100.0
    assert _score([])[0] == 100.0

    from audit.run import audit_one
    row = {"id": 2, "agent_id": 125, "campaign_id": 1, "lead_id": 1, "contact_id": "x",
           "provider_sid": "s", "created_at": "2026-08-30", "status": "done", "call_stage": None,
           "lead_stage_computed": "lead_link_sent_online", "duration_s": 60,
           "additional_variables": {"customer_name": "Asha", "make": "Maruti", "model": "Swift",
                                    "reg_no": "OD01AP4344", "red": "02-09-2026",
                                    "ncb": "20", "dtd": "70", "premium": "10693"},
           "messages": [
               {"role": "assistant", "content": "Simran from Cholamandalam MS, Asha जी?"},
               {"role": "user", "content": "हां"},
               {"role": "assistant", "content": "record की जा रही है। आपकी Maruti Swift, number "
                "O-D zero-one A-P four-three-four-four, policy two September को expire"},
               {"role": "user", "content": "ठीक है बताइए"},
               {"role": "assistant", "content": "renewal premium है ten thousand six hundred "
                "ninety-three rupees"},
               {"role": "user", "content": "हां भेज दीजिए"},
               {"role": "assistant", "content": "Link भेज दिया है। धन्यवाद।"}]}
    rec = audit_one(row, llm=False, cached=None)
    missed = [v_["name"] for v_ in rec["variables"] if v_["verdict"] == "missed"]
    assert missed, "ncb and dtd were never spoken; the fixture is meant to have silences"
    assert rec["score"] == 100.0, f"spoken values were all right: {rec['score']}"
    assert rec["verdict"] == "warn" and "missing_variable" in rec["flags"]
    assert rec["variables_failed"] == len(missed), "silence still counted as not-right"


def test_the_call_clock_is_the_conversation_not_the_queue():
    """A batch of leads shares one `created_at`; the call happened much later.

    Real values from interaction 5788410 and its batch-mates, which is what made
    the call list stack thousands of calls onto a single 06:27:53.302174 and
    print every clock 5h30m early.
    """
    from audit.data import _call_start

    # Metabase hands back the IST-converted value; the tail of the attempt is
    # the conversation, so a 35s call that ended 11:48:44 began 11:48:09.
    assert _call_start("2026-09-03T11:48:44.699286+05:30", 35) == \
        "2026-09-03T11:48:09.699286+05:30"
    # Nobody spoke, so there is no conversation to back up to -- the caller
    # falls back rather than getting a wrong time that looks precise.
    assert _call_start("2026-09-03T11:48:44.699286+05:30", None) is None
    assert _call_start(None, 35) is None
    # A duration longer than the day still yields a real instant, not a crash.
    assert _call_start("2026-09-03T00:00:10+05:30", 60).startswith("2026-09-02T23:59:10")
    assert _call_start("not a timestamp", 35) is None


def test_a_rerun_drops_calls_that_left_the_day():
    """Re-running a day must not leave yesterday's answer lying underneath it."""
    import tempfile
    from audit import run as RUN

    RUN.DB = Path(tempfile.mkdtemp()) / "audits.db"
    conn = RUN.db()

    def n():
        return conn.execute("SELECT COUNT(*) FROM calls WHERE audit_date='2026-09-03'").fetchone()[0]

    RUN.save(conn, 1, "2026-09-03", [{"interaction_id": 1}, {"interaction_id": 2}])
    assert n() == 2
    # The day boundary moves: call 2 is no longer part of the 3rd, call 3 now is.
    RUN.save(conn, 2, "2026-09-03", [{"interaction_id": 1}, {"interaction_id": 3}])
    assert n() == 2, "the row that left the day is still filed under it"
    assert {r[0] for r in conn.execute(
        "SELECT interaction_id FROM calls WHERE audit_date='2026-09-03'")} == {1, 3}
    # A run that fetched nothing is a failure, not an empty day.
    RUN.save(conn, 3, "2026-09-03", [])
    assert n() == 2, "an empty fetch erased a real day"


def test_ground_truth_fixture_is_deidentified():
    f = Path(__file__).parent / "ground_truth_labels_2026-08-27.csv"
    rows = list(csv.DictReader(f.open(encoding="utf-8")))
    assert len(rows) == 20
    assert set(rows[0]) == {"interaction_id", "Verfication Error", "Dispostion Error"}
    assert sum(r["Dispostion Error"] != "NA" for r in rows) == 13


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
