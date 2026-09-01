/** Mirrors the "HTTP API" section of ../../CONTRACT.md, field for field. */

export type Verdict = "pass" | "warn" | "fail";
/** A call with no transcript is not a failure — it was never audited. */
export type CallVerdict = Verdict | "no_transcript";

export interface Health {
  ok: boolean;
  model: string;
  /** The newest day audited, not the deploy-time .env date. */
  audit_date: string;
  calls_audited: number;
  running_job: Job | null;
}

/** One attempt at running an audit — the trigger, not the audit's findings. */
export type JobStatus = "running" | "done" | "failed" | "cancelled" | "interrupted";

export interface Job {
  id: number;
  audit_date: string;
  trigger: "manual" | "schedule";
  status: JobStatus;
  started_at: string | null;
  finished_at: string | null;
  exit_code: number | null;
  pid: number | null;
  duration_s: number | null;
  /** Tail of the run's stdout. Only on GET /jobs/{id}. */
  log?: string;
}

export interface JobsPage {
  items: Job[];
  running: Job | null;
  /** Yesterday in IST — the sensible default for a hand-started run. */
  default_date: string;
}

export interface Schedule {
  enabled: boolean;
  /** HH:MM, 24-hour, in `timezone`. */
  time: string;
  /** Whose calls a nightly run audits: the day it fires, or the one before. */
  target: "today" | "yesterday";
  timezone: string;
  last_fired: string | null;
  next_run: string | null;
  next_target_date: string | null;
}

export interface Totals {
  calls: number;
  audited: number;
  no_transcript: number;
  pass: number;
  warn: number;
  fail: number;
  avg_score: number;
}

export interface AgentSummary {
  agent_id: number;
  name: string;
  language: string;
  calls: number;
  audited: number;
  pass: number;
  warn: number;
  fail: number;
  avg_score: number;
}

export interface VariableStat {
  name: string;
  required_in: number;
  spoken: number;
  missed: number;
  wrong: number;
  accuracy: number;
}

export interface FlowStat {
  step: string;
  label: string;
  reached: number;
  correct: number;
  skipped: number;
}

export interface Summary {
  date: string;
  totals: Totals;
  by_agent: AgentSummary[];
  variables: VariableStat[];
  flow: FlowStat[];
}

export interface CallRow {
  interaction_id: number;
  agent_id: number;
  campaign_id: number;
  lead_id: number;
  started_at: string;
  duration_s: number | null;
  status: string;
  call_stage: string | null;
  customer_name: string | null;
  reg_no: string | null;
  turns: number;
  score: number | null;
  verdict: CallVerdict;
  variables_checked: number;
  variables_failed: number;
  flow_score: number | null;
  flags: string[];
  /** The label the platform's disposition engine assigned. */
  disposition: string | null;
  disposition_verdict: CallVerdict;
  /** Reviewer phrasing, straight from the sheet — misspellings and all. */
  verification_error: string | null;
  disposition_error: string | null;
  summary: string | null;
}

export interface CallsPage {
  items: CallRow[];
  page: number;
  page_size: number;
  total: number;
}

export interface Turn {
  role: string;
  content: string;
  index: number;
}

export interface VariableCheck {
  name: string;
  required: boolean;
  expected_raw: string;
  expected_spoken: string | null;
  spoken: boolean;
  verdict: Verdict;
  /** Index into `transcript`. The link that makes a verdict checkable. */
  turn_index: number | null;
  evidence: string | null;
  note: string | null;
  checked_by: "rule" | "llm";
}

export interface FlowCheck {
  step: string;
  label: string;
  required: boolean;
  observed: boolean;
  turn_index: number | null;
  verdict: Verdict;
  note: string | null;
}

export interface DispositionCheck {
  assigned: string | null;
  source: string | null;
  reasoning: string | null;
  expected: string | null;
  verdict: Verdict;
  note: string | null;
}

export interface CallDetail extends CallRow {
  transcript: Turn[];
  variables: VariableCheck[];
  flow: FlowCheck[];
  disposition_check: DispositionCheck;
  judge: { model: string; latency_ms: number | null; raw: string | null };
}

/* Manual audits — the ten-a-day sample a reviewer listens to by hand. The
   allowed values live on the server (`/manual/options`) so the workbook's
   dropdowns have one definition, not two. */

export interface ManualOptions {
  auditors: string[];
  info_accuracy: string[];
  call_flow: string[];
  verdicts: string[];
  per_auditor: number;
  /** Yesterday in IST — the day a reviewer comes in to audit. */
  default_date: string;
}

export interface ManualItem {
  interaction_id: number;
  agent_id: number;
  audit_date: string;
  auditor: string;
  language: string;
  started_at: string;
  duration_s: number | null;
  customer_name: string | null;
  reg_no: string | null;
  policy_no: string | null;
  recording_url: string;
  /** The injected values, in the workbook's `RED: ...; DTD: ...` shape. */
  pre_call: string;
  transcript: Turn[];
  turns: number;
  /** What the platform decided, shown but not editable. */
  disposition: string | null;
  disposition_verdict: CallVerdict;
  engine_verdict: CallVerdict;
  score: number | null;
  info_accuracy: string | null;
  call_flow: string | null;
  verdict: string | null;
  notes: string | null;
  submitted_at: string | null;
}

export interface ManualQueue {
  date: string;
  auditor: string;
  items: ManualItem[];
  assigned: number;
  done: number;
}

export interface ManualProgress {
  date: string;
  items: Array<{ auditor: string; assigned: number; done: number }>;
}

export interface Run {
  id: number;
  audit_date: string;
  started_at: string;
  finished_at: string | null;
  calls: number;
  model: string;
}
