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
import sys
import time
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
_SELECT = """
SELECT i.id, i.agent_id, i.campaign_id, i.lead_id, i.contact_id, i.provider_sid,
       i.created_at, i.ended_time, i.status, i.call_stage,
       i.lead_stage_computed, i.lead_stage_source, i.lead_stage_reasoning,
       (i.interaction_metadata->>'call_duration') AS call_duration,
       c.name AS campaign_name,
       i.additional_variables, i.messages
FROM public.interactions i
LEFT JOIN public.campaigns c ON c.id = i.campaign_id
"""


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
    return rows


def fetch_day(date: str) -> list[dict]:
    return _clean(_paged(f"i.outlet_id = {OUTLET_ID} "
                         f"AND i.created_at >= '{date}' AND i.created_at < '{date}'::date + 1"))


def fetch_ids(ids: list[int]) -> list[dict]:
    if not ids:
        return []
    joined = ",".join(str(int(i)) for i in ids)
    return _clean(_paged(f"i.id IN ({joined})"))
