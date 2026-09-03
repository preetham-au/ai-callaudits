# Call audits — engine + API

Audits Chola renewal voice-agent calls on one axis: **variables** — did the agent
say the injected value, and say it right. The score is that, out of 100 — and it
grades **spoken values only**: `ok / (ok + wrong)`. A value the agent never said
is reported (`missed` column, `missing_variable` flag, `warn` verdict) but not
scored, because there is no spoken value to be accurate about.

Flow and disposition verification were removed on 3 Sep 2026. Flow detection
still runs, but only to decide how far a call got, so a call that died in the
greeting is not marked down for values it never had the chance to say. The
platform's disposition is shown as assigned and is not second-guessed.

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

| what | decided by | why |
|---|---|---|
| variables | rules (`audit/rules.py`) | normalise both sides to integers/dates and compare. The judge may only *clear* a value the matcher missed, never create a `wrong` — a 4B's opinion is not evidence enough to fail a call. |
| reachability | rules | per-agent step markers, used only to mark a variable `not_reached` rather than `missed`. Nothing is scored or flagged on a step. |
| summary, error wording | judge | free text in the reviewers' clipped register, for the CSV. |

Verdict is a gate, not a threshold: any `wrong` value is a `fail` (a customer
heard a figure that was not theirs), any `missed` is a `warn`, otherwise `pass`.

Qwen sees one call at a time: compact rubric (≤1200 tok) + transcript (≤4000
tok, middle-dropped if it overruns). Results are cached in `llm_cache` by
interaction id, so re-running after a scoring change costs no GPU time.

Full design record, with pipeline diagrams and the reasoning behind each
decision: [docs/architecture.md](docs/architecture.md).

## Layout

```
rubric/{125,127}.json   distilled from prompts/*.md, one per agent
audit/data.py           .env + Metabase
audit/rules.py          normaliser, variable checks, flow (reachability only)
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
