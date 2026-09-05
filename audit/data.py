"""Config and Metabase access.

The reports repo (CHOLA CR RAG) has a working `run_native_sql`, but importing it
would drag in its `formi_auth` dotenv loader from a third directory and its own
`config/.env`, both of which we would immediately have to override. The useful
part is ~30 lines, so it is lifted rather than imported and this stays a
standalone repo.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent


def load_env() -> dict:
    env = {}
    f = ROOT / ".env"
    if f.exists():
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip()
    env.update({k: v for k, v in os.environ.items() if k in env or k.startswith(("METABASE_", "QWEN_", "AUDIT_"))})
    return env


ENV = load_env()
AUDIT_DATE = ENV.get("AUDIT_DATE", "2026-08-30")
OUTLET_ID = 1497

# The gateway in front of Metabase intermittently 504s on queries that succeed
# moments later on a retry.
RETRY_STATUSES = (502, 503, 504)
MAX_ATTEMPTS = 4

# /api/dataset caps a native query at 2000 rows and says nothing about it: no
# error, no flag in the body, just a short list. 31 Aug had 5757 calls and came
# back as 2000, and because the query was ORDER BY i.id the 3757 dropped were
# the whole back half of the day -- including every Tamil call, since agent 127's
# campaign is dialled after agent 125's. The day looked audited and was not.
METABASE_ROW_CAP = 2000
PAGE = 1000


def run_native_sql(sql: str, timeout: int = 300) -> list[dict]:
    url = ENV["METABASE_URL"].rstrip("/") + "/api/dataset"
    payload = {"type": "native", "native": {"query": sql}, "database": int(ENV["METABASE_DB_ID"])}
    headers = {"x-api-key": ENV["METABASE_API_KEY"], "Content-Type": "application/json"}
    for attempt in range(1, MAX_ATTEMPTS + 1):
        last = attempt == MAX_ATTEMPTS
        try:
            r = requests.post(url, json=payload, headers=headers, timeout=timeout)
            if r.status_code not in RETRY_STATUSES or last:
                break
            reason = str(r.status_code)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if last:
                raise
            reason = type(e).__name__
        wait = 5 * 2 ** (attempt - 1)
        print(f"  metabase {reason}; retry in {wait}s", file=sys.stderr, flush=True)
        time.sleep(wait)
    r.raise_for_status()
    body = r.json()
    if body.get("status") == "failed":
        raise RuntimeError(f"Metabase query failed: {body.get('error') or body}")
    data = body.get("data", {})
    cols = [c["name"] for c in data.get("cols", [])]
    rows = [dict(zip(cols, row)) for row in data.get("rows", [])]
    # Anything that lands exactly on the cap has almost certainly been cut. Better
    # a loud failure than another day that reads as complete and is missing half
    # its calls; use `_paged` for queries that legitimately return this many.
    if len(rows) >= METABASE_ROW_CAP:
        raise RuntimeError(
            f"Metabase returned {len(rows)} rows, its cap — the result is truncated. "
            "Page the query instead of raising the limit.")
    return rows


def _paged(where: str) -> list[dict]:
    """Every row matching `where`, in id order, a page at a time.

    Keyset, not OFFSET: the interactions table is being written to while an audit
    runs, and OFFSET over a moving table skips rows. `id` is the primary key, so
    `id > last` is both stable and indexed.
    """
    out: list[dict] = []
    last = 0
    while True:
        page = run_native_sql(
            f"{_SELECT} WHERE {where} AND i.id > {last} ORDER BY i.id LIMIT {PAGE}")
        out.extend(page)
        if len(page) < PAGE:
            return out
        last = int(page[-1]["id"])


# `ended_time - created_at` spans the whole dial attempt, not the conversation:
# it reads 5860s on a one-turn call. The real figure is in interaction_metadata,
# which is what the reports repo settled on too.
#
# Both timestamps are `timestamp WITHOUT time zone` holding NAIVE UTC -- the same
# convention the reports repo documents (interaction_export.sql). Metabase's own
# report timezone is Asia/Kolkata, so it stamps "+05:30" onto the naive value on
# the way out: the string said 06:18:44+05:30 for a call actually placed at
# 11:48 IST, and every clock in the UI was 5h30m early. Converted here, at the
# one place that knows the convention, so nothing downstream has to.
_SELECT = """
SELECT i.id, i.agent_id, i.campaign_id, i.lead_id, i.contact_id, i.provider_sid,
       (i.created_at AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS created_at,
       (i.ended_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS ended_time,
       i.status, i.call_stage,
       i.lead_stage_computed, i.lead_stage_source, i.lead_stage_reasoning,
       (i.interaction_metadata->>'call_duration') AS call_duration,
       c.name AS campaign_name,
       i.additional_variables, i.messages
FROM public.interactions i
LEFT JOIN public.campaigns c ON c.id = i.campaign_id
"""


# `lead_stage_reasoning` carries the engine's own verdict as `group=… sub=…
# decision=… conf=…`. `lead_stage_computed` is only the coarse half of it: the
# engine writes sub=did_not_pick under both computed='did_not_pick' and
# computed='not_contacted', and writes computed='contacted' with no sub at all
# when it defers to HUMAN_REVIEW. Counting on `computed` therefore splits one
# outcome across two labels. The sub is the label the reviewers audit against.
#
# Only rows from the disposition engine carry the pattern; `immediate_*` sources
# write prose ("Telephony provider failed before customer connection."), which
# matches nothing and correctly yields no sub.
_REASON_KV = re.compile(r"\b(group|sub|decision|conf)=(\S+)")


def _parse_reasoning(text) -> dict:
    kv = dict(_REASON_KV.findall(str(text or "")))
    conf = kv.get("conf")
    try:
        conf = float(conf) if conf is not None else None
    except ValueError:
        conf = None
    return {"disposition_group": kv.get("group"), "disposition_sub": kv.get("sub"),
            "disposition_decision": kv.get("decision"), "disposition_conf": conf}


def _clean(rows: list[dict]) -> list[dict]:
    for r in rows:
        for k in ("additional_variables", "messages"):
            v = r.get(k)
            if isinstance(v, str):
                try:
                    v = json.loads(v)
                except ValueError:
                    v = None
            r[k] = v
        r["additional_variables"] = r["additional_variables"] or {}
        r["messages"] = r["messages"] or []
        d = r.get("call_duration")
        r["duration_s"] = int(float(d)) if d not in (None, "") else None
        # Best available, in order: the conversation, the end of the last dial
        # attempt, the moment the batch was queued. Only the last is shared by
        # thousands of rows, so it is the last resort.
        r["started_at"] = (_call_start(r.get("ended_time"), r["duration_s"])
                           or r.get("ended_time") or r.get("created_at"))
        r.update(_parse_reasoning(r.get("lead_stage_reasoning")))
        # Subs are written in mixed case (`did_not_pick` next to `Voicemail_IVR`),
        # so they are folded to one case or the same outcome counts as two.
        sub = r.get("disposition_sub")
        r["disposition"] = sub.lower() if sub else r.get("lead_stage_computed")
    return rows


def _call_start(ended, duration_s):
    """When the conversation began: the attempt's end, less the time spoken.

    `created_at` is not it. That is when the platform queued the row, so a whole
    batch shares one microsecond -- five leads stamped 06:27:53.302174, one of
    which ended 49 minutes later -- and the call list piled thousands of calls
    onto a single instant. `ended_time` is per-row and real, and an interaction
    can hold several dial attempts, so the conversation is the tail of the last
    one. With no duration nobody spoke, and the end of the attempt is the truest
    time there is.
    """
    if not ended or not duration_s:
        return None
    try:
        return (datetime.fromisoformat(str(ended)) - timedelta(seconds=duration_s)).isoformat()
    except ValueError:
        return None


def fetch_day(date: str) -> list[dict]:
    # An audit day is an IST day anchored on `scheduled_time` -- when the dialler
    # was asked to place the call.
    #
    # NOT `created_at`, which is when the platform queued the batch, and which
    # `_call_start` below already refuses as a call time for the same reason: a
    # whole batch shares one instant, hours before anyone is dialled. Measured
    # outlet-wide on 3 Sep 2026, of the 8,857 rows created_at filed under that
    # day, 1,596 were dialled on the 4th and 4 more between four and ten days
    # later, while only 11 arrived from an earlier day. That is the gap between
    # this repo's 8,857 for the date and the daily report's 7,167, which nobody
    # could reconcile. The dashboard (server/src/db/syncSql.ts) and the reports
    # repo both anchor on scheduled_time, so all three now agree on which day a
    # call belongs to.
    #
    # The column is naive UTC, so the window is shifted rather than the column
    # converted -- `scheduled_time >= x` can use the index,
    # `scheduled_time AT TIME ZONE ... >= x` cannot.
    return _clean(_paged(
        f"i.outlet_id = {OUTLET_ID} "
        f"AND i.scheduled_time >= '{date}'::timestamp - interval '5 hours 30 minutes' "
        f"AND i.scheduled_time <  '{date}'::date + 1 - interval '5 hours 30 minutes'"))


def fetch_ids(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    joined = ",".join(str(int(i)) for i in ids)
    return _clean(_paged(f"i.id IN ({joined})"))
