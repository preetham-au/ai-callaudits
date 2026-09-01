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


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn(); print("ok", name)
