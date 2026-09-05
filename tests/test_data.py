"""python -m pytest tests/test_data.py -q   (or just: python tests/test_data.py)

The one thing in data.py that can be silently wrong: how many rows come back.
Metabase caps a native query at 2000 and reports nothing, so a day bigger than
that used to read as complete while missing its back half. Nothing here touches
the network -- requests.post and run_native_sql are replaced by fakes.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from audit import data as D  # noqa: E402

REAL_RUN = D.run_native_sql


def _fake_table(n: int):
    """Stands in for Metabase: honours `i.id > N` and LIMIT."""
    rows = [{"id": i, "agent_id": 125 if i <= n * 0.9 else 127} for i in range(1, n + 1)]
    seen = []

    def run(sql, timeout=300):
        after = int(sql.split("i.id > ")[1].split(" ")[0])
        page = rows[after:][:int(sql.split("LIMIT ")[1])]
        seen.append(len(page))
        return page

    return run, seen


def test_paging_returns_the_whole_day():
    try:
        for n in (0, 1, D.PAGE, D.PAGE + 1, 5757):
            D.run_native_sql, seen = _fake_table(n)
            got = D._paged("1=1")
            assert [r["id"] for r in got] == list(range(1, n + 1)), n
            # A day landing exactly on a page boundary needs one more request to
            # learn it is over; stopping on a full page would drop the tail.
            assert sum(seen) == n and seen[-1] < D.PAGE, (n, seen)
    finally:
        D.run_native_sql = REAL_RUN


def test_tamil_survives_a_day_over_the_cap():
    """Agent 127 dials after 125, so truncation takes Tamil first and entirely."""
    try:
        D.run_native_sql, _ = _fake_table(5757)
        got = D._paged("1=1")
        assert len(got) > D.METABASE_ROW_CAP
        assert sum(r["agent_id"] == 127 for r in got) > 0
    finally:
        D.run_native_sql = REAL_RUN


class _Resp:
    status_code = 200

    def __init__(self, n):
        self.n = n

    def raise_for_status(self):
        pass

    def json(self):
        return {"data": {"cols": [{"name": "id"}], "rows": [[i] for i in range(self.n)]}}


def test_a_capped_response_raises_rather_than_truncating():
    real_post, real_env = D.requests.post, dict(D.ENV)
    D.ENV.update(METABASE_URL="http://x", METABASE_API_KEY="x", METABASE_DB_ID="1")
    try:
        D.requests.post = lambda *a, **k: _Resp(D.METABASE_ROW_CAP)
        try:
            REAL_RUN("SELECT 1")
        except RuntimeError as e:
            assert "truncated" in str(e)
        else:
            raise AssertionError("a capped response was accepted as complete")
        D.requests.post = lambda *a, **k: _Resp(D.METABASE_ROW_CAP - 1)
        assert len(REAL_RUN("SELECT 1")) == D.METABASE_ROW_CAP - 1
    finally:
        D.requests.post = real_post
        D.ENV.clear()
        D.ENV.update(real_env)


def test_disposition_comes_from_the_reasoning_sub():
    """The sub is the label; `lead_stage_computed` is only its coarse half."""
    rows = D._clean([
        # Same outcome the engine split across two `computed` values.
        {"lead_stage_computed": "did_not_pick",
         "lead_stage_reasoning": "group=NOT_CONTACTED sub=did_not_pick decision=AUTO_APPLY conf=0.98"},
        {"lead_stage_computed": "not_contacted",
         "lead_stage_reasoning": "group=NOT_CONTACTED sub=did_not_pick decision=AUTO_APPLY conf=0.98"},
        # Mixed-case sub, folded so it does not count as a separate outcome.
        {"lead_stage_computed": "voicemail_ivr",
         "lead_stage_reasoning": "group=CONTACTED sub=Voicemail_IVR decision=AUTO_APPLY conf=1.00"},
        # No sub: the engine deferred. Fall back rather than blank the row.
        {"lead_stage_computed": "contacted",
         "lead_stage_reasoning": "group=CONTACTED decision=HUMAN_REVIEW conf=1.00"},
        # Non-engine source writes prose, which must not parse into a sub.
        {"lead_stage_computed": "telephony_failed",
         "lead_stage_reasoning": "Telephony provider failed before customer connection."},
        # Pre-cutover era (before 31 Aug 2026): the sub sat in `computed` under a
        # `sub_` prefix and the reasoning carried no `sub=` to find. This repo
        # audits across the cutover, so both eras have to land on one label or the
        # same outcome is counted twice under two names.
        {"lead_stage_computed": "sub_did_not_pick",
         "lead_stage_reasoning": "group=NOT_CONTACTED decision=AUTO_APPLY conf=0.98"},
        {"lead_stage_computed": "sub_Hung_Up", "lead_stage_reasoning": None},
        {"lead_stage_computed": None, "lead_stage_reasoning": None},
    ])
    assert [r["disposition"] for r in rows] == [
        "did_not_pick", "did_not_pick", "voicemail_ivr",
        "contacted", "telephony_failed", "did_not_pick", "hung_up", None]
    assert rows[0]["disposition_group"] == "NOT_CONTACTED"
    assert rows[0]["disposition_decision"] == "AUTO_APPLY"
    assert rows[0]["disposition_conf"] == 0.98
    assert rows[3]["disposition_sub"] is None
    assert rows[4]["disposition_group"] is None


def test_a_day_is_bucketed_on_scheduled_time():
    """Which day a call belongs to, and it has been wrong twice.

    `created_at` is when the batch was queued, hours before anyone is dialled:
    on 3 Sep 2026 it filed 1,596 calls under a day they were not placed on, and
    that was the unexplained gap between this repo's 8,857 and the daily
    report's 7,167. The dashboard and the reports repo both anchor on
    `scheduled_time`. The IST shift is on the literal, not the column, or the
    index is lost.
    """
    seen = []
    try:
        D.run_native_sql = lambda sql, timeout=300: seen.append(sql) or []
        D.fetch_day("2026-09-03")
        where = seen[0].split("WHERE", 1)[1]
        assert where.count("i.scheduled_time") == 2, "both bounds, or the day is open-ended"
        assert "i.created_at" not in where, "created_at is the queue instant, not the call"
        assert where.count("interval '5 hours 30 minutes'") == 2, where
    finally:
        D.run_native_sql = REAL_RUN


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
