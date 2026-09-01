/*
 * Fixtures.
 *
 * The engine and the API are built by another agent, so for most of this app's
 * life there is nothing on 127.0.0.1:8085. These responses are shaped exactly
 * like CONTRACT.md's — same keys, same nullability — so the UI never has to bend
 * when the real thing arrives. Anything served from here raises the mock banner:
 * a fixture must never be mistaken for an audit.
 */
import type {
  CallDetail,
  CallRow,
  CallsPage,
  Health,
  JobsPage,
  ManualItem,
  ManualOptions,
  ManualProgress,
  ManualQueue,
  Run,
  Schedule,
  Summary,
  Turn,
} from "./types";

export const AUDIT_DATE = "2026-08-30";

const HINDI: Turn[] = [
  { index: 0, role: "assistant", content: "नमस्ते, क्या मैं राजेश कुमार जी से बात कर रहा हूँ?" },
  { index: 1, role: "user", content: "हाँ जी, बोल रहा हूँ।" },
  {
    index: 2,
    role: "assistant",
    content:
      "सर, मैं प्रिया बोल रही हूँ Chola MS General Insurance से। यह कॉल quality purpose के लिए record की जा रही है। आपकी Hyundai i20, registration O-D two-seven C four-nine-six-two, की policy two September को expire हो रही है।",
  },
  { index: 3, role: "user", content: "अच्छा, हाँ। कितना आ रहा है इस बार?" },
  {
    index: 4,
    role: "assistant",
    content:
      "सर आपको eighty five परसेंट तक का discount मिल रहा है, और आपका renewal premium छह हज़ार चार सौ बीस रुपये है।",
  },
  { index: 5, role: "user", content: "पिछली बार तो कम था ना?" },
  {
    index: 6,
    role: "assistant",
    content:
      "सर पिछली बार से इसमें आपका No Claim Bonus भी जुड़ा हुआ है, इसीलिए यह आपके लिए बेहतर rate है। मैं आपको payment link भेज देती हूँ?",
  },
  { index: 7, role: "user", content: "हाँ भेज दीजिए, मैं देख लेता हूँ।" },
  {
    index: 8,
    role: "assistant",
    content:
      "जी सर, मैंने आपके registered mobile number पर payment link भेज दिया है। कोई और सवाल हो तो बताइए। धन्यवाद, आपका दिन शुभ हो।",
  },
];

const TAMIL: Turn[] = [
  { index: 0, role: "assistant", content: "வணக்கம், நான் முருகன் அவர்களிடம் பேசுகிறேனா?" },
  { index: 1, role: "user", content: "ஆமா, சொல்லுங்க." },
  {
    index: 2,
    role: "assistant",
    content:
      "சார், நான் காயத்ரி பேசுறேன், Chola MS General Insurance-ல இருந்து. இந்த call record ஆகுது சார். உங்க Maruti Swift, registration T-N zero-nine B-K one-two-three-four, policy five September-ல முடியுது.",
  },
  { index: 3, role: "user", content: "ஓ, அப்படியா. எவ்வளவு ஆகும்?" },
  {
    index: 4,
    role: "assistant",
    content: "சார் உங்களுக்கு seventy five பர்சன்ட் discount இருக்கு. Premium ஏழாயிரத்து இருநூறு ரூபாய் சார்.",
  },
  { index: 5, role: "user", content: "கொஞ்சம் யோசிச்சு சொல்றேன்." },
  {
    index: 6,
    role: "assistant",
    content: "கண்டிப்பா சார். நான் ஒரு payment link அனுப்பி வைக்கிறேன், நீங்க வசதியா பாத்துக்கலாம். நன்றி சார்.",
  },
];

interface Seed {
  name: string | null;
  reg: string | null;
  agent: 125 | 127;
  verdict: CallRow["verdict"];
  score: number | null;
  failed: number;
  flags: string[];
  /** The platform's label, and whether it survives contact with the transcript. */
  disp: string | null;
  dispVerdict: CallRow["disposition_verdict"];
  /* Reviewer phrasing, verbatim from the human sheet — misspellings included. */
  vErr: string | null;
  dErr: string | null;
}

const HUNG_UP = "Wrong Dispostion(it's a hung up call) but mention lead_premium_quotation";

const SEEDS: Seed[] = [
  { name: "Rajesh Kumar", reg: "OD-27-C-4962", agent: 125, verdict: "fail", score: 41, failed: 2, flags: ["premium_wrong", "expiry_wrong"], disp: "lead_premium_quotation", dispVerdict: "pass", vErr: "DTD and RED incorrect", dErr: null },
  { name: "Murugan S", reg: "TN-09-BK-1234", agent: 127, verdict: "warn", score: 74, failed: 0, flags: ["step4_partial"], disp: "lead_link_send", dispVerdict: "pass", vErr: null, dErr: null },
  { name: "Sunita Devi", reg: "DL-08-CA-9911", agent: 125, verdict: "pass", score: 93, failed: 0, flags: [], disp: "lead_premium_quotation", dispVerdict: "pass", vErr: null, dErr: null },
  { name: "Anand Raman", reg: "TN-22-AR-0450", agent: 127, verdict: "fail", score: 55, failed: 1, flags: ["ncb_wrong", "disposition_wrong"], disp: "lead_premium_quotation", dispVerdict: "fail", vErr: "NCB, DTD incorrect", dErr: HUNG_UP },
  { name: null, reg: "MH-12-QQ-3321", agent: 125, verdict: "no_transcript", score: null, failed: 0, flags: ["never_connected"], disp: null, dispVerdict: "no_transcript", vErr: null, dErr: null },
  { name: "Prakash Jha", reg: "UP-32-BN-7788", agent: 125, verdict: "pass", score: 88, failed: 0, flags: [], disp: "lead_link_send", dispVerdict: "pass", vErr: null, dErr: null },
  { name: "Lakshmi Narayanan", reg: "TN-01-AZ-6612", agent: 127, verdict: "fail", score: 61, failed: 0, flags: ["discount_missed", "disposition_wrong"], disp: "lead_premium_quotation", dispVerdict: "fail", vErr: null, dErr: "Wrong Dispostion(lead link send ) but mention lead_premium_quotation" },
  { name: "Imran Sheikh", reg: "RJ-14-CD-2020", agent: 125, verdict: "fail", score: 38, failed: 3, flags: ["premium_wrong", "step2_skipped"], disp: "lead_premium_quotation", dispVerdict: "pass", vErr: "Incorect RED shared", dErr: null },
  { name: "Gopal Mehta", reg: "GJ-05-KL-1177", agent: 125, verdict: "pass", score: 91, failed: 0, flags: [], disp: "lead_link_send", dispVerdict: "pass", vErr: null, dErr: null },
  { name: null, reg: null, agent: 125, verdict: "no_transcript", score: null, failed: 0, flags: ["never_connected"], disp: null, dispVerdict: "no_transcript", vErr: null, dErr: null },
  { name: "Kavitha R", reg: "TN-37-BB-8080", agent: 127, verdict: "fail", score: 58, failed: 0, flags: ["disposition_wrong"], disp: "lead_premium_quotation", dispVerdict: "fail", vErr: null, dErr: "Wrong Dispostion(it's a hung up call) but mention voicemail_ivr" },
  { name: "Deepak Verma", reg: "HR-26-DK-5544", agent: 125, verdict: "warn", score: 72, failed: 0, flags: ["expiry_missed"], disp: "lead_call_back", dispVerdict: "warn", vErr: null, dErr: "Incorrect dispostion" },
  { name: "Selvam K", reg: "TN-11-CF-3390", agent: 127, verdict: "fail", score: 49, failed: 1, flags: ["premium_wrong"], disp: "lead_not_interested", dispVerdict: "pass", vErr: "Vehicle details not confirm", dErr: null },
  { name: "Ritu Singh", reg: "MP-09-RS-4411", agent: 125, verdict: "pass", score: 96, failed: 0, flags: [], disp: "lead_link_send", dispVerdict: "pass", vErr: null, dErr: null },
  { name: "Farhan Ali", reg: "TS-07-FA-6023", agent: 125, verdict: "fail", score: 64, failed: 0, flags: ["objection_unhandled", "disposition_wrong"], disp: "lead_premium_quotation", dispVerdict: "fail", vErr: null, dErr: HUNG_UP },
  { name: null, reg: "KA-03-MN-9090", agent: 127, verdict: "no_transcript", score: null, failed: 0, flags: ["never_connected"], disp: null, dispVerdict: "no_transcript", vErr: null, dErr: null },
];

const ROWS: CallRow[] = SEEDS.map((s, i) => {
  const audited = s.verdict !== "no_transcript";
  const script = s.agent === 125 ? HINDI : TAMIL;
  return {
    interaction_id: 9100000 + i,
    agent_id: s.agent,
    campaign_id: s.agent === 125 ? 4411 : 4412,
    lead_id: 550000 + i * 7,
    started_at: `${AUDIT_DATE}T${String(10 + (i % 8)).padStart(2, "0")}:${String((i * 7) % 60).padStart(2, "0")}:00+05:30`,
    duration_s: audited ? 48 + i * 11 : null,
    status: audited ? "completed" : "no_answer",
    call_stage: audited ? "call_ended" : null,
    customer_name: s.name ?? null,
    reg_no: s.reg ?? null,
    turns: audited ? script.length : 0,
    score: s.score,
    verdict: s.verdict,
    variables_checked: audited ? 11 : 0,
    variables_failed: s.failed,
    flow_score: s.score === null ? null : Math.round(s.score * 0.2 * 10) / 10,
    flags: s.flags,
    disposition: s.disp,
    disposition_verdict: s.dispVerdict,
    verification_error: s.vErr,
    disposition_error: s.dErr,
    summary: audited
      ? "AI gave opening script and confirm customer name/ Customer said yes/ AI follow up recording script and share Vehicle details/ AI shared premium and discount/ AI shared payment link"
      : null,
  };
});

const MANUAL_OPTIONS: ManualOptions = {
  auditors: ["Preetham", "HV", "Swarna"],
  info_accuracy: ["Accurate", "Inaccurate"],
  call_flow: ["Followed", "Not Followed"],
  verdicts: ["Pass", "Needs Coaching", "Escalate", "Incomplete", "Not Applicable"],
  per_auditor: 10,
  default_date: AUDIT_DATE,
};

/* A short queue on purpose: enough to show a mixed-language list and a call
   already audited, without ten copies of the same two transcripts. */
const MANUAL_QUEUE: ManualItem[] = ROWS.filter((r) => r.verdict !== "no_transcript")
  .slice(0, 4)
  .map((r, i) => ({
    interaction_id: r.interaction_id,
    agent_id: r.agent_id,
    audit_date: AUDIT_DATE,
    auditor: "Preetham",
    language: r.agent_id === 127 ? "Tamil" : "Hindi",
    started_at: r.started_at,
    duration_s: r.duration_s,
    customer_name: r.customer_name,
    reg_no: r.reg_no,
    policy_no: `PC${900000 + i}`,
    /* One without a recording, so the "no recording" case is visible offline too. */
    recording_url: i === 1 ? null : "https://example.invalid/recording.mp3",
    pre_call: "RED: 2026-09-07; DTD: seventy five; NCB: twenty five percent",
    transcript: r.agent_id === 125 ? HINDI : TAMIL,
    turns: r.turns,
    disposition: r.disposition,
    disposition_verdict: r.disposition_verdict,
    engine_verdict: r.verdict,
    score: r.score,
    info_accuracy: i === 0 ? "Accurate" : null,
    call_flow: i === 0 ? "Followed" : null,
    verdict: i === 0 ? "Pass" : null,
    notes: i === 0 ? "Premium and RED date both read back correctly." : null,
    submitted_at: i === 0 ? `${AUDIT_DATE}T18:20:00+05:30` : null,
  }));

function detailFor(row: CallRow): CallDetail {
  const hindi = row.agent_id === 125;
  const transcript = row.verdict === "no_transcript" ? [] : hindi ? HINDI : TAMIL;
  const bad = row.verdict === "fail";
  const warn = row.verdict === "warn";
  return {
    ...row,
    transcript,
    variables:
      row.verdict === "no_transcript"
        ? []
        : [
            {
              name: "customer_name",
              required: true,
              expected_raw: row.customer_name ?? "null",
              expected_spoken: row.customer_name,
              spoken: true,
              verdict: "pass",
              turn_index: 0,
              evidence: transcript[0]?.content ?? null,
              note: null,
              checked_by: "rule",
            },
            {
              name: "reg_no",
              required: true,
              expected_raw: row.reg_no ?? "null",
              expected_spoken: hindi ? "O-D two-seven C four-nine-six-two" : "T-N zero-nine B-K one-two-three-four",
              spoken: true,
              verdict: "pass",
              turn_index: 2,
              evidence: transcript[2]?.content ?? null,
              note: "Matched after digit-to-word normalisation.",
              checked_by: "rule",
            },
            {
              name: "red",
              required: true,
              expected_raw: hindi ? "02-Sep" : "05-Sep",
              expected_spoken: hindi ? "two September" : "five September",
              spoken: true,
              verdict: bad ? "fail" : "pass",
              turn_index: 2,
              evidence: transcript[2]?.content ?? null,
              note: bad ? "Agent said an expiry date that does not match the feed." : null,
              checked_by: "rule",
            },
            {
              name: "premium",
              required: true,
              expected_raw: hindi ? "6420" : "7200",
              expected_spoken: hindi ? "छह हज़ार चार सौ बीस" : "ஏழாயிரத்து இருநூறு",
              spoken: true,
              verdict: bad ? "fail" : "pass",
              turn_index: 4,
              evidence: transcript[4]?.content ?? null,
              note: bad ? "Spoken premium differs from the injected value — reaches the customer as misinformation." : null,
              checked_by: "rule",
            },
            {
              name: "dtd",
              required: true,
              expected_raw: hindi ? "eighty five" : "seventy five",
              expected_spoken: hindi ? "eighty five" : "seventy five",
              spoken: !warn,
              verdict: warn ? "warn" : "pass",
              turn_index: warn ? null : 4,
              evidence: warn ? null : transcript[4]?.content ?? null,
              note: warn ? "Discount never spoken." : null,
              checked_by: "rule",
            },
            {
              name: "ncb",
              required: false,
              expected_raw: "fifty",
              expected_spoken: null,
              spoken: hindi,
              verdict: hindi ? "pass" : "warn",
              turn_index: hindi ? 6 : null,
              evidence: hindi ? transcript[6]?.content ?? null : null,
              note: hindi ? "Referred to as No Claim Bonus without the figure; judged acceptable." : "Not mentioned.",
              checked_by: "llm",
            },
            {
              name: "vehicle_model",
              required: true,
              expected_raw: hindi ? "Hyundai i20" : "Maruti Swift",
              expected_spoken: null,
              spoken: true,
              verdict: "pass",
              turn_index: 2,
              evidence: transcript[2]?.content ?? null,
              note: null,
              checked_by: "rule",
            },
            {
              name: "prev_insurer",
              required: false,
              expected_raw: "null",
              expected_spoken: null,
              spoken: false,
              verdict: "warn",
              turn_index: null,
              evidence: null,
              note: "Absent from the feed, so nothing to say.",
              checked_by: "rule",
            },
          ],
    flow:
      row.verdict === "no_transcript"
        ? []
        : [
            { step: "1", label: "Identity confirmation", required: true, observed: true, turn_index: 0, verdict: "pass", note: null },
            {
              step: "2",
              label: "Disclosure, vehicle, expiry anchor",
              required: true,
              observed: true,
              turn_index: 2,
              verdict: bad ? "fail" : "pass",
              note: bad ? "Disclosure given, but the expiry anchor was wrong." : null,
            },
            {
              step: "3",
              label: "Discount and premium",
              required: true,
              observed: !warn,
              turn_index: warn ? null : 4,
              verdict: warn ? "warn" : "pass",
              note: warn ? "Premium quoted without the discount that precedes it." : null,
            },
            {
              step: "4",
              label: "Payment link",
              required: true,
              observed: true,
              turn_index: hindi ? 8 : 6,
              verdict: "pass",
              note: null,
            },
            {
              step: "5",
              label: "Objection handling",
              required: false,
              observed: hindi,
              turn_index: hindi ? 6 : null,
              verdict: hindi ? "pass" : "warn",
              note: hindi ? null : "Customer deferred; no objection was worked.",
            },
          ],
    disposition_check: {
      assigned: row.disposition,
      source: row.disposition === null ? null : "lead_stage_computed",
      reasoning:
        row.disposition === null
          ? null
          : `group=${row.disposition?.replace(/^lead_/, "")} sub=${row.disposition} decision=AUTO_APPLY conf=0.85`,
      expected: row.disposition_verdict === "fail" ? "lead_customer_hung_up" : row.disposition,
      verdict: row.disposition_verdict === "no_transcript" ? "warn" : row.disposition_verdict,
      note: row.disposition_error,
    },
    judge: { model: "Qwen3.5-4B", latency_ms: 1830, raw: null },
  };
}

const SUMMARY: Summary = {
  date: AUDIT_DATE,
  totals: { calls: 687, audited: 168, no_transcript: 519, pass: 79, warn: 51, fail: 38, avg_score: 73.4 },
  by_agent: [
    { agent_id: 125, name: "Priya", language: "Hindi", calls: 617, audited: 141, pass: 68, warn: 42, fail: 31, avg_score: 73.9 },
    { agent_id: 127, name: "Gayathri", language: "Tamil", calls: 70, audited: 27, pass: 11, warn: 9, fail: 7, avg_score: 70.8 },
  ],
  variables: [
    { name: "premium", required_in: 168, spoken: 151, missed: 17, wrong: 29, accuracy: 47.6 },
    { name: "red", required_in: 168, spoken: 149, missed: 19, wrong: 22, accuracy: 51.8 },
    { name: "dtd", required_in: 168, spoken: 122, missed: 46, wrong: 8, accuracy: 67.9 },
    { name: "reg_no", required_in: 168, spoken: 160, missed: 8, wrong: 11, accuracy: 88.7 },
    { name: "ncb", required_in: 121, spoken: 88, missed: 33, wrong: 3, accuracy: 70.2 },
    { name: "vehicle_model", required_in: 168, spoken: 163, missed: 5, wrong: 2, accuracy: 95.8 },
    { name: "customer_name", required_in: 168, spoken: 166, missed: 2, wrong: 1, accuracy: 98.2 },
    { name: "payment_link", required_in: 168, spoken: 140, missed: 28, wrong: 0, accuracy: 83.3 },
    { name: "idv", required_in: 44, spoken: 21, missed: 23, wrong: 4, accuracy: 38.6 },
    { name: "prev_insurer", required_in: 31, spoken: 24, missed: 7, wrong: 1, accuracy: 74.2 },
  ],
  flow: [
    { step: "1", label: "Identity confirmation", reached: 168, correct: 161, skipped: 7 },
    { step: "2", label: "Disclosure, vehicle, expiry anchor", reached: 158, correct: 118, skipped: 10 },
    { step: "3", label: "Discount and premium", reached: 141, correct: 96, skipped: 27 },
    { step: "4", label: "Payment link", reached: 117, correct: 104, skipped: 24 },
    { step: "5", label: "Objections", reached: 63, correct: 48, skipped: 15 },
  ],
};

const RUNS: Run[] = [
  {
    id: 1,
    audit_date: AUDIT_DATE,
    started_at: `${AUDIT_DATE}T21:04:00+05:30`,
    finished_at: `${AUDIT_DATE}T21:29:00+05:30`,
    calls: 168,
    model: "Qwen3.5-4B",
  },
];

const HEALTH: Health = {
  ok: true,
  model: "Qwen3.5-4B",
  audit_date: AUDIT_DATE,
  calls_audited: 168,
  running_job: null,
};

/* Deliberately one finished run and no live one: the Runs page must look right
   when nothing is happening, which is its usual state. */
const JOBS: JobsPage = {
  items: [
    {
      id: 1,
      audit_date: AUDIT_DATE,
      trigger: "schedule",
      status: "done",
      started_at: `${AUDIT_DATE}T23:30:00+05:30`,
      finished_at: `${AUDIT_DATE}T23:55:00+05:30`,
      exit_code: 0,
      pid: 4242,
      duration_s: 1500,
    },
  ],
  running: null,
  default_date: AUDIT_DATE,
};

const SCHEDULE: Schedule = {
  enabled: true,
  time: "23:30",
  target: "today",
  timezone: "Asia/Kolkata",
  last_fired: AUDIT_DATE,
  next_run: "2026-08-31T23:30:00+05:30",
  next_target_date: "2026-08-31",
};

/** Answers a contract path with fixture data, applying the same filters the API would. */
export function mockFor(path: string): unknown {
  const [route, query] = path.split("?");
  const p = new URLSearchParams(query ?? "");

  if (route === "/health") return HEALTH;
  if (route === "/summary") return SUMMARY;
  if (route === "/runs") return RUNS;
  if (route === "/jobs") return JOBS;
  if (route === "/schedule") return SCHEDULE;

  const jobDetail = /^\/jobs\/(\d+)$/.exec(route);
  if (jobDetail) {
    const job = JOBS.items.find((j) => j.id === Number(jobDetail[1]));
    if (!job) throw new Error(`No mock job ${jobDetail[1]}`);
    return { ...job, log: "168 calls, 168 with transcripts\njudge: 0 cached, 168 to send\n  judged 168/168 (884s)" };
  }

  const detail = /^\/calls\/(\d+)$/.exec(route);
  if (detail) {
    const row = ROWS.find((r) => r.interaction_id === Number(detail[1]));
    if (!row) throw new Error(`No mock call ${detail[1]}`);
    return detailFor(row);
  }

  if (route === "/calls") {
    const agent = p.get("agent_id");
    const verdict = p.get("verdict");
    const q = (p.get("q") ?? "").trim().toLowerCase();
    const page = Number(p.get("page") ?? 1);
    const size = Number(p.get("page_size") ?? 50);
    const items = ROWS.filter(
      (r) =>
        (!agent || r.agent_id === Number(agent)) &&
        (!verdict || r.verdict === verdict) &&
        (!q ||
          [r.reg_no, r.customer_name, String(r.interaction_id)].some((v) => v?.toLowerCase().includes(q))),
    );
    const out: CallsPage = {
      items: items.slice((page - 1) * size, page * size),
      page,
      page_size: size,
      total: items.length,
    };
    return out;
  }

  if (route === "/manual/options") return MANUAL_OPTIONS;
  if (route === "/manual/progress") {
    const out: ManualProgress = {
      date: p.get("date") ?? AUDIT_DATE,
      items: MANUAL_OPTIONS.auditors.map((auditor, i) => ({
        auditor,
        assigned: MANUAL_QUEUE.length,
        done: i === 0 ? 1 : 0,
      })),
    };
    return out;
  }
  if (route === "/manual/queue") {
    const items = MANUAL_QUEUE;
    const out: ManualQueue = {
      date: p.get("date") ?? AUDIT_DATE,
      auditor: p.get("auditor") ?? MANUAL_OPTIONS.auditors[0],
      items,
      assigned: items.length,
      done: items.filter((i) => i.submitted_at).length,
    };
    return out;
  }

  throw new Error(`No mock for ${path}`);
}
