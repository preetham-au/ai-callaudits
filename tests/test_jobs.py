"""python -m pytest tests/test_jobs.py -q   (or just: python tests/test_jobs.py)

Covers the two bits of jobs.py that can silently be wrong: the date guard (it
stands between an HTTP body and a string interpolated into SQL) and the
nightly-fire decision. Nothing here starts a subprocess or touches Metabase —
the DB is redirected at a temp file first.
"""
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api import jobs as J  # noqa: E402

J.DB = Path(tempfile.mkdtemp()) / "jobs_test.db"


def test_date_guard_rejects_injection():
    for bad in ["2026-13-01", "2026-8-3", "", "2026-08-30'; DROP TABLE calls; --", None]:
        try:
            J.check_date(bad)
        except (ValueError, TypeError):
            continue
        raise AssertionError(f"accepted {bad!r}")
    assert J.check_date("2026-08-30") == "2026-08-30"


def test_schedule_roundtrip_and_validation():
    s = J.set_schedule(True, "23:30", "today")
    assert s["enabled"] and s["time"] == "23:30" and s["next_run"]
    for bad_time in ["24:00", "7:30", "23:60", "night"]:
        try:
            J.set_schedule(True, bad_time, "today")
        except ValueError:
            continue
        raise AssertionError(f"accepted {bad_time!r}")
    try:
        J.set_schedule(True, "23:30", "tomorrow")
    except ValueError:
        pass
    else:
        raise AssertionError("accepted target 'tomorrow'")
    # Disabling must not lose the time, or re-enabling silently reschedules.
    assert J.set_schedule(False, "23:30", "today")["time"] == "23:30"


def test_fire_decision():
    """_maybe_fire is the whole scheduler; it is checked without the clock."""
    fired = []
    J.start = lambda date, trigger: fired.append((date, trigger))
    now = datetime(2026, 9, 1, 23, 45, tzinfo=J.IST)
    fire_at = J._maybe_fire

    J.set_schedule(True, "23:30", "today")
    J._write({"schedule_last_fired": ""})

    fire_at(now - timedelta(hours=2))          # before the scheduled minute
    assert fired == []
    fire_at(now)                               # after it, first time today
    assert fired == [("2026-09-01", "schedule")]
    fire_at(now + timedelta(minutes=1))        # same night, must not double-fire
    assert len(fired) == 1
    fire_at(now + timedelta(days=1))           # next night
    assert fired[-1] == ("2026-09-02", "schedule")

    J.set_schedule(True, "23:30", "yesterday")
    J._write({"schedule_last_fired": ""})
    fire_at(now)
    assert fired[-1] == ("2026-08-31", "schedule")

    J.set_schedule(False, "23:30", "today")
    J._write({"schedule_last_fired": ""})
    n = len(fired)
    fire_at(now)
    assert len(fired) == n, "fired while disabled"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print(f"ok  {name}")
