# Call-audit contract

Two agents build against this file: one owns the engine + API, one owns the web
UI. Neither reads the other's code — this document is the whole interface, so
if something here is wrong, fix it here first and say so.

## Ground truth — read this before designing anything

Humans already do this audit by hand. Their sheet for 27-Aug is at
`data/ground_truth/human_audits_2026-08-27.csv` (gitignored — it carries
transcripts, phone numbers and policy numbers). 20 audited calls. **It is both
the definition of the job and the output format**, so the engine is graded
against it: reproduce those 20 verdicts before trusting any of the 168.

What the reviewers actually record, and how often, tells you where the value is:

| column | findings in 20 calls |
|---|---|
| `Verfication Error` | 5 — `NCB, DTD incorrect`, `Incorrect DTD inform to the customer`, `Incorect RED shared`, `DTD and RED incorrect`, `Vehicle details not confirm` |
| `Dispostion Error` | **12** — `Wrong Dispostion(it's a hung up call) but mention lead_premium_quotation`, `... but mention voicemail_ivr`, `Wrong Dispostion(lead link send ) but mention lead_premium_quotation`, `Incorrect dispostion` |

Two lessons. The verification errors cluster on **`dtd`, `ncb`, `red` and the
vehicle fields** — weight those. And **disposition error is the single most
common finding**, so an auditor that only checks variables and flow would miss
the majority of what humans catch.

The reviewer's own phrasing shows the test: the call was a hang-up, yet the
engine labelled it `lead_premium_quotation`. So the check is *does the assigned
disposition match what the transcript shows actually happened*.

## What the audit is

Each Chola renewal call is placed by a voice agent driven by a large Jinja
prompt (`prompts/125.md` Hindi, `prompts/127.md` Tamil). Before the call, the
platform injects ~90 variables into that prompt. The audit answers three
questions per call:

1. **Flow** — did the agent walk the prompt's Call Workflow in order
   (Step 1 identity → Step 2 disclosure + vehicle + expiry anchor → Step 3
   discount + premium → Step 4 payment link → Step 5 objections), and did it
   skip or collapse a step the prompt calls fatal?
2. **Pre-call variables** — every variable the prompt requires the agent to
   *say* — was it actually said, and said with the right value?

3. **Disposition** — `interactions.lead_stage_computed` holds the label the
   platform's disposition engine assigned (e.g. `lead_premium_quotation`),
   with `lead_stage_source` and `lead_stage_reasoning` alongside it
   (`group=… sub=… decision=AUTO_APPLY conf=0.85`). Does that label match what
   the transcript shows? A two-turn call where the customer hangs up is not a
   premium quotation.

Questions 2 and 3 are the reason this exists. A wrong premium or expiry date
read to a customer is a compliance problem, not a UX one; a wrong disposition
silently routes the lead into the wrong follow-up campaign.

## The one hard constraint

The judge model is **Qwen3.5-4B on self-hosted vLLM with `max_model_len` 8192**.
The agent prompts are ~50k tokens each. **The main prompt cannot be sent to the
model.** It must be distilled once, offline, into a compact rubric (see
`rubric/`), and only the rubric plus one call's transcript ever reaches Qwen.

Budget per call: rubric ≤ 1200 tokens, transcript ≤ 4000 tokens, leaving room
for the answer. Truncate the transcript from the middle if it overruns — the
opener and the close are what carry the graded content.

## Data (already verified against live Metabase)

`public.interactions`, `outlet_id = 1497`. For 2026-08-30: 687 calls —
617 on `agent_id` 125, 70 on 127. **168 have a non-null `messages`; the rest
never connected.** Those are `no_transcript`, not failures — never score them.

- `messages` — jsonb, the transcript, exactly `[{"role": "assistant"|"user",
  "content": "..."}]`. Hindi/Tamil mixed with English, in Devanagari/Tamil script.
- `additional_variables` — json, present on all 687, the injected values.
  Keys match the `{{ name }}` placeholders in the prompt.
- Missing values arrive as the **string** `"null"`, not JSON null. Treat
  `"null"`, `""` and `None` alike as absent.

### Values arrive pre-spoken

The prompt's "Spoken-value resolver" says the feed supplies the WORDS and the
agent converts nothing. So `additional_variables` holds `"dtd": "eighty five"`,
`"ncb": "fifty"`. But the agent still reformats some of them out loud:

| variable | injected | actually spoken |
|---|---|---|
| `reg_no` | `OD-27-C-4962` | `O-D two-seven C four-nine-six-two` |
| `red` | `02-Sep` | `two September` |
| `dtd` | `eighty five` | `eighty five` |

So matching is **not** string equality. Normalise (case, spaces, hyphens,
digit↔word both ways, month name↔number) and match on that; hand the residue
to Qwen with the transcript turn as evidence. Deterministic first, model second
— a regex that finds the premium is worth more than a 4B model's opinion of it.

## Layout — agents own disjoint subtrees

```
call-audits/
  prompts/125.md, 127.md    given, read-only
  CONTRACT.md               this file
  rubric/{125,127}.json     ENGINE writes
  audit/                    ENGINE
  api/                      ENGINE
  data/audits.db            ENGINE, gitignored
  web/                      UI
```

Neither agent runs `git commit`, `git push`, or edits the other's subtree.

## Config

`.env` at the repo root, `.env.example` committed with blank secrets.

```
METABASE_URL=      METABASE_API_KEY=      METABASE_DB_ID=2
QWEN_BASE_URL=http://13.206.118.151:8000/v1
QWEN_API_KEY=      QWEN_MODEL=/home/ubuntu/models/Qwen3.5-4B
QWEN_MAX_CONCURRENCY=8
AUDIT_DATE=2026-08-30
```

vLLM is OpenAI-compatible: `POST {QWEN_BASE_URL}/chat/completions` with
`Authorization: Bearer {QWEN_API_KEY}`.

## HTTP API — the interface between the two agents

FastAPI on `127.0.0.1:8085`. Every response is JSON. `date` is `YYYY-MM-DD`
and defaults to `AUDIT_DATE`. A verdict is always one of
`"pass" | "warn" | "fail"`, and a call with no transcript has verdict
`"no_transcript"` and a null score.

```
GET /api/health
  -> {"ok": true, "model": str, "audit_date": str, "calls_audited": int}

GET /api/summary?date=
  -> {"date": str,
      "totals": {"calls": int, "audited": int, "no_transcript": int,
                 "pass": int, "warn": int, "fail": int, "avg_score": float,
                 "disposition_wrong": int},
      "dispositions": [{"assigned": str, "calls": int, "wrong": int,
                        "accuracy": float}],
      "by_agent": [{"agent_id": int, "name": str, "language": str,
                    "calls": int, "audited": int, "pass": int, "warn": int,
                    "fail": int, "avg_score": float}],
      "variables": [{"name": str, "required_in": int, "spoken": int,
                     "missed": int, "wrong": int, "accuracy": float}],
      "flow":      [{"step": str, "label": str, "reached": int,
                     "correct": int, "skipped": int}]}

GET /api/calls?date=&agent_id=&verdict=&q=&page=1&page_size=50
  q filters on reg_no / policy_no / customer_name / interaction_id.
  -> {"items": [{"interaction_id": int, "agent_id": int, "campaign_id": int,
                 "lead_id": int, "started_at": str, "duration_s": int|null,
                 "status": str, "call_stage": str|null,
                 "customer_name": str|null, "reg_no": str|null,
                 "turns": int, "score": float|null, "verdict": str,
                 "variables_checked": int, "variables_failed": int,
                 "flow_score": float|null, "flags": [str],
                 "disposition": str|null, "disposition_verdict": str,
                 "verification_error": str|null, "disposition_error": str|null,
                 "summary": str|null}],
      "page": int, "page_size": int, "total": int}

GET /api/calls/{interaction_id}
  -> {... every field from the list item, plus:
      "transcript": [{"role": str, "content": str, "index": int}],
      "variables": [{"name": str, "required": bool, "expected_raw": str,
                     "expected_spoken": str|null, "spoken": bool,
                     "verdict": str, "turn_index": int|null,
                     "evidence": str|null, "note": str|null,
                     "checked_by": "rule"|"llm"}],
      "flow": [{"step": str, "label": str, "required": bool,
                "observed": bool, "turn_index": int|null,
                "verdict": str, "note": str|null}],
      "disposition_check": {"assigned": str|null, "source": str|null,
                            "reasoning": str|null, "expected": str|null,
                            "verdict": str, "note": str|null,
                            "turn_index": int|null},
      "judge": {"model": str, "latency_ms": int|null, "raw": str|null}}

GET /api/export.csv?date=&agent_id=&verdict=
  The human sheet, byte-compatible. See "CSV export" below.

GET /api/runs   -> [{"id": int, "audit_date": str, "started_at": str,
                     "finished_at": str|null, "calls": int, "model": str}]
```

`turn_index` indexes into `transcript`, so the UI can scroll to and highlight
the exact turn a verdict came from. That link is the point of the whole
detail view — a verdict the operator cannot check against the words is
not worth showing. **This applies hardest to `disposition_check`**, which is
the highest-value verdict: cite the turn that proves it (the hang-up, or the
turn where the link was actually sent). Return null only when genuinely no
single turn is responsible.

### Value domains — no free-form strings

- `verdict` and `disposition_verdict`: `"pass" | "warn" | "fail" |
  "no_transcript"`. A call that never connected is `no_transcript` on both,
  with a null score — there is no transcript to contradict a label.
- `flags`: a closed vocabulary, lowercase snake_case. Currently
  `missing_variable`, `wrong_variable`, `flow_skipped`, `flow_collapsed`,
  `wrong_disposition`, `short_call`, `llm_parse_failed`. Extend the list here
  before emitting a new one; the UI may filter on them.
- `flow_score`: 0–20, matching its weight in the score.
- `turns` is the **true** turn count. If the transcript in the detail response
  was truncated to fit the 4000-token budget, `turns` still reports the real
  total, so the UI can say "showing N of M". Set
  `"transcript_truncated": true` on the detail response when that happens.

Serve the built SPA from `/` and return `index.html` for unknown non-`/api`
paths so client-side routes survive a refresh.

## Scoring

`score` is 0–100: **50 variables, 20 flow, 30 disposition** — disposition is
weighted for being the most common human finding. Two things force `fail`
regardless of score: a required variable that was *said but wrong*, and a
disposition that contradicts the transcript. Both reach the business as
misinformation. A missed non-required variable is `warn`.

## CSV export — must match the human sheet exactly

The operator downloads results and works them in the same sheet they use today,
so the export is byte-compatible with
`data/ground_truth/human_audits_2026-08-27.csv`. Same columns, same order,
**including the two misspellings and the one empty unnamed column** — they are
load-bearing for whatever consumes the sheet downstream, so do not "fix" them:

```
interaction_id, contact_id, campaign_name, Call_date, , transcript,
customer_name, call_stage, call_recording_url, call_duration,
Calling Summary, Verfication Error, Dispostion Error, Remarks, policy_no
```

- `transcript` — one cell, turns as `ASSISTANT: …` / `USER: …` separated by
  newlines, matching the sheet.
- `call_recording_url` — `https://formi-prod-2.s3.eu-north-1.amazonaws.com/onboarding/{provider_sid}`.
- `campaign_name` — join `campaigns` on `campaign_id`.
- `call_duration` — the reports repo already solved where this really lives
  (commit "Read the contact number and duration from where they are actually
  stored"); reuse that logic rather than re-deriving it.
- `Calling Summary` — Qwen writes it, in the clipped operational register the
  humans use: *"AI gave opening script and confirm customer name/ Customer said
  yes/ AI follow up recording script and share Vehicle details…"*. Slash-separated
  beats, not prose.
- `Verfication Error` / `Dispostion Error` — the finding in the reviewers'
  phrasing, or `NA` when clean. Match their vocabulary (`DTD and RED incorrect`,
  `Wrong Dispostion(it's a hung up call) but mention lead_premium_quotation`)
  so the two sources read alike in one sheet.
- `Remarks` — free text, left blank unless there is something to say.

Serve it as `GET /api/export.csv?date=&agent_id=&verdict=` with
`Content-Disposition: attachment`, honouring the same filters as `/api/calls`,
UTF-8 with BOM so the sheet opens correctly.

## UI

Follow the dashboard's design language, tokens copied from
`../dashboard/web/src/styles/global.css`: `--paper #faf9fe`, `--nav-bg #1b1b20`,
`--accent #f3dd6d`, `--radius 28px`, Plus Jakarta Sans for UI and JetBrains
Mono for data, the `--s1..--s12` spacing scale and `--t-micro..--t-hero` type
scale. Light scheme.

Three screens: overview (the summary numbers, per-agent split, worst
variables), call list (filterable table, with a Download CSV button hitting
`/api/export.csv`), call detail (transcript beside the variable, flow and
disposition verdicts, each verdict clickable to its turn).

Simple and easy to use is the brief, not impressive. The dashboard is the
reference for that too: generous whitespace, few colours, one clear action per
screen, plain labels. No dense control-room styling, no chart for a number that
reads better as a number, no feature the operator did not ask for. If a screen
needs explaining, it is wrong.

Built with `vite build --base=/audits/` so it can sit behind the shared
tunnel next to the other apps.
