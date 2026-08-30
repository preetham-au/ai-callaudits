"""python -m pytest tests/ -q   (or just: python tests/test_audit.py)

Real fixtures, from calls that actually ran: the two spoken transformations
CONTRACT documents, the wrong-value case that must force `fail`, and the
disposition rules graded against the human sheet's own labels.
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
    rec = audit_one(row, ["lead_link_sent_online"], llm=False, cached=None)
    prem = [v for v in rec["variables"] if v["name"] == "premium"][0]
    assert prem["verdict"] == "wrong"           # 9000 spoken, 10693 injected
    assert rec["verdict"] == "fail" and "wrong_variable" in rec["flags"]
    assert rec["disposition_verdict"] == "pass"  # the link really was sent
    assert rec["score"] < 100


def test_disposition_rules_match_the_human_sheet():
    """The four contradiction rules, on the shapes the reviewers flagged."""
    talk = [{"role": "assistant", "content": "नमस्ते"}, {"role": "user", "content": "हां बोलिए"},
            {"role": "assistant", "content": "premium है"}, {"role": "user", "content": "ठीक है"},
            {"role": "assistant", "content": "क्या मैं link भेज दूं?"}]
    assert R.check_disposition(talk, "voicemail_ivr")[0] == "fail"     # a live conversation
    assert R.check_disposition(talk, "lead_link_sent_online")[0] == "fail"  # no link sent
    assert R.check_disposition(talk, "lead_premium_quotation")[0] == "fail"  # customer dropped
    assert R.check_disposition(talk, "hung_up")[0] == "pass"
    assert R.check_disposition([], "hung_up")[0] == "no_transcript"


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
