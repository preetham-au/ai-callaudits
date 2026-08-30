# Call audits — engine + API

Audits Chola renewal voice-agent calls on three axes: **variables** (did the
agent say the injected value, and say it right), **flow** (did it walk the
prompt's workflow), **disposition** (does the platform's `lead_stage_computed`
match what the transcript shows). Score is 50 / 20 / 30 on those.

```bash
pip install -r requirements.txt
cp .env.example .env          # fill in the two keys

python -m audit.run                       # audit AUDIT_DATE, write data/audits.db
python -m audit.run --no-llm              # rules only, no GPU
python -m audit.validate                  # grade against the 20 human-audited calls
python tests/test_audit.py                # or: pytest tests/ -q
uvicorn api.main:app --host 127.0.0.1 --port 8085
```

## How it decides

| axis | decided by | why |
|---|---|---|
| variables | rules (`audit/rules.py`) | normalise both sides to integers/dates and compare. The judge may only *clear* a value the matcher missed, never create a `wrong` — a 4B's opinion is not evidence enough to fail a call. |
| flow | rules, judge annotates | step markers per agent; a step is only required once the call actually reached it. |
| disposition | rules, judge as second opinion | four contradiction rules (voicemail with a real conversation, hang-up label on a long call, link-sent with no link, completed label on a call the customer dropped). Unaided, the judge scored 3 hits / 3 false alarms on the human set; the rules scored 13 / 0. A judge-only objection surfaces as `warn`. |
| summary, error wording | judge | free text in the reviewers' clipped register, for the CSV. |

Qwen sees one call at a time: compact rubric (≤1200 tok) + transcript (≤4000
tok, middle-dropped if it overruns). Results are cached in `llm_cache` by
interaction id, so re-running after a scoring change costs no GPU time.

## Layout

```
rubric/{125,127}.json   distilled from prompts/*.md, one per agent
audit/data.py           .env + Metabase
audit/rules.py          normaliser, variable checks, flow, disposition rules
audit/judge.py          Qwen client, token budgeting, defensive parsing
audit/run.py            orchestration, scoring, SQLite
audit/validate.py       grade against data/ground_truth/, write the fixture
api/main.py             the contract endpoints + CSV export + SPA
tests/                  one runnable check + the de-identified label fixture
```

## Where CONTRACT.md is wrong

- **Duration** is not `ended_time - created_at` (5860s on a one-turn call). It
  is `interaction_metadata->>'call_duration'`, which matches the human sheet
  exactly on all 20 rows.
- **Values do not arrive pre-spoken.** Most rows carry digits (`"ncb": "20"`,
  `"premium": "26113"`, `"red": "03-09-2026"`), not words. Both are handled.
- **`red` is day-first** (`08-09-2026` → "eight September"), not the `M/D/YYYY`
  the prompt claims, and it also arrives as `Friday, August 21, 2026`.
- vLLM exposes **no `/tokenize`**, so token counts are estimated locally and
  calibrated against `usage.prompt_tokens` (`audit.judge.calibration_report()`).
