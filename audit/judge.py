"""Qwen judge. Only the residue the rules could not settle goes here.

One job per call: adjudicate the variables the rules only 'missed' — absent, or
merely phrased oddly? Flow and disposition are no longer verified, so they are
no longer asked about. The rubric still ships the workflow, because a variable
is identified by the step it belongs to.
"""
from __future__ import annotations

import json
import re
import time
from concurrent.futures import ThreadPoolExecutor

import requests

from .data import ENV

MODEL = ENV.get("QWEN_MODEL", "")
BASE = ENV.get("QWEN_BASE_URL", "").rstrip("/")
CONCURRENCY = int(ENV.get("QWEN_MAX_CONCURRENCY", "8"))

CTX = 8192
RUBRIC_BUDGET = 1200
TRANSCRIPT_BUDGET = 4000
ANSWER_RESERVE = 1400

# vLLM exposes no /tokenize endpoint (404 on /v1/tokenize), and tiktoken cannot
# download its BPE from this host, so the count is estimated locally: ~3.3 chars
# per token for Latin, but Devanagari/Tamil fragment badly and run closer to one
# token per character. Deliberately an over-estimate — truncating slightly early
# is cheap, a 400 from the server mid-run is not. Calibrated against the
# usage.prompt_tokens the server returns (see calibration_report()).
_INDIC = re.compile(r"[ऀ-ॿ஀-௿]")
_seen_ratio: list[float] = []


def est_tokens(text: str) -> int:
    indic = len(_INDIC.findall(text))
    return int(indic * 1.0 + (len(text) - indic) / 3.3) + 8


def calibration_report() -> str:
    if not _seen_ratio:
        return "no server token counts observed"
    return (f"estimate/actual ratio over {len(_seen_ratio)} calls: "
            f"min {min(_seen_ratio):.2f} mean {sum(_seen_ratio)/len(_seen_ratio):.2f} "
            f"max {max(_seen_ratio):.2f} (>=1.0 means the estimate is safe)")


# ------------------------------------------------------------------- prompting

def rubric_text(rub: dict) -> str:
    """The rubric compressed to what a 4B can actually act on inside 1200 tokens."""
    lines = [f"AGENT {rub['agent_id']} — {rub['persona']}, {rub['language']}. {rub['call_purpose']}",
             "WORKFLOW (must run in this order, one step per turn):"]
    for s in rub["flow"]:
        lines.append(f"- {s['step']} {s['label']}: " + "; ".join(s["must_contain"][:3]))
    lines.append("REQUIRED SPOKEN VARIABLES: " + ", ".join(
        f"{v['name']} (in {v['step']})" for v in rub["required_variables"]))
    lines.append("FATAL: " + "; ".join(f"{f['code']} {f['what'].split('.')[0]}"
                                       for f in rub["fatal_rules"][:10]))
    txt = "\n".join(lines)
    while est_tokens(txt) > RUBRIC_BUDGET:
        txt = txt[: int(len(txt) * 0.9)]
    return txt


def transcript_text(turns: list[dict]) -> tuple[str, bool]:
    """Numbered turns, middle-dropped if over budget: the opener and the close
    carry the graded content (disclosure, premium, link, hang-up)."""
    lines = [f"[{i}] {t['role'].upper()}: {' '.join(str(t.get('content') or '').split())}"
             for i, t in enumerate(turns)]
    txt = "\n".join(lines)
    if est_tokens(txt) <= TRANSCRIPT_BUDGET:
        return txt, False
    head, tail = [], []
    used = 40
    hi, ti = 0, len(lines) - 1
    while hi <= ti:
        # Two thirds of the budget to the opening, a third to the close.
        take_head = used < TRANSCRIPT_BUDGET * 0.66 or ti < hi
        ln = lines[hi] if take_head else lines[ti]
        if used + est_tokens(ln) > TRANSCRIPT_BUDGET:
            break
        used += est_tokens(ln)
        if take_head:
            head.append(ln); hi += 1
        else:
            tail.insert(0, ln); ti -= 1
    return "\n".join(head + [f"... [{ti - hi + 1} turns omitted] ..."] + tail), True


SYSTEM = (
    "You audit Indian insurance-renewal voice-agent calls. Reply with ONE JSON object, "
    "no prose, no markdown. Be strict and literal: judge only what the transcript shows."
)

_SCHEMA = """{
 "variables": {"<only unresolved names>": {"verdict": "ok|missed|wrong", "turn_index": 3|null, "note": "<8 words"}},
 "summary": "beat/ beat/ beat",
 "verification_error": "NA"
}"""


def build_prompt(rub: dict, turns: list[dict], residue: list[dict]) -> tuple[str, bool]:
    tx, truncated = transcript_text(turns)
    unresolved = "\n".join(
        f"- {r['name']}: expected to be spoken as \"{r['expected_spoken']}\" "
        f"(feed value \"{r['expected_raw']}\"); the string matcher did not find it"
        for r in residue) or "- none"
    user = f"""{rubric_text(rub)}

TRANSCRIPT ({len(turns)} turns, [i] is the turn index):
{tx}

A rule-based matcher already checked every variable. These it could not find:
{unresolved}

Answer these, in this exact JSON shape:
1. variables — ONLY the unresolved variables listed above (if the list says none, return an empty object). Do not mention any other variable. For each: "ok" if the transcript does say it (give the turn index), "missed" if the agent never said it, "wrong" if the agent said a different value for that field.
2. summary — what happened, in clipped slash-separated beats in the reviewer register, e.g. "AI gave opening script and confirm customer name/ Customer said yes/ AI share premium and asking payment/ call drop". Max 40 words.
3. verification_error — short reviewer-style phrase if a value was said wrong (e.g. "DTD and RED incorrect", "Vehicle details not confirm"), else "NA".

{_SCHEMA}"""
    return user, truncated


# ---------------------------------------------------------------------- client

def _post(messages: list[dict], timeout: int = 180) -> dict:
    r = requests.post(
        f"{BASE}/chat/completions",
        headers={"Authorization": f"Bearer {ENV.get('QWEN_API_KEY','')}",
                 "Content-Type": "application/json"},
        json={"model": MODEL, "messages": messages, "temperature": 0,
              "max_tokens": ANSWER_RESERVE, "response_format": {"type": "json_object"}},
        timeout=timeout,
    )
    r.raise_for_status()
    return r.json()


def _parse(text: str) -> dict | None:
    """The model sometimes wraps JSON in a fence or trails a sentence."""
    for candidate in (text, text[text.find("{"): text.rfind("}") + 1]):
        try:
            v = json.loads(candidate)
            if isinstance(v, dict):
                return v
        except (ValueError, TypeError):
            continue
    return None


def judge(rub: dict, turns: list[dict], residue: list[dict]) -> dict:
    """Never raises. A parse failure is recorded as a parse failure, not as a
    verdict — a 4B failing to close a brace must not become "the call failed"."""
    user, truncated = build_prompt(rub, turns, residue)
    est = est_tokens(SYSTEM) + est_tokens(user)
    out = {"ok": False, "parsed": None, "raw": None, "latency_ms": None,
           "error": None, "est_prompt_tokens": est, "transcript_truncated": truncated}
    t0 = time.time()
    try:
        body = _post([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}])
    except Exception as e:  # noqa: BLE001 — one bad call must not kill the run
        out["error"] = f"{type(e).__name__}: {e}"[:300]
        out["latency_ms"] = int((time.time() - t0) * 1000)
        return out
    out["latency_ms"] = int((time.time() - t0) * 1000)
    actual = (body.get("usage") or {}).get("prompt_tokens")
    if actual:
        _seen_ratio.append(est / actual)
    raw = (body.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    out["raw"] = raw[:4000]
    parsed = _parse(raw)
    if parsed is None:
        out["error"] = "json_parse_failed"
        return out
    out["ok"] = True
    out["parsed"] = parsed
    return out


def judge_many(jobs: list[tuple], workers: int | None = None) -> list[dict]:
    with ThreadPoolExecutor(max_workers=workers or CONCURRENCY) as ex:
        return list(ex.map(lambda a: judge(*a), jobs))
