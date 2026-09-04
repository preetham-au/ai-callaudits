import { useRef, useState } from "react";
import { ArrowLeft, CornerDownRight } from "lucide-react";
import { useResource } from "../api/client";
import type { CallDetail, VariableCheck, VariableVerdict } from "../api/types";
import {
  ErrorState,
  LoadingBlock,
  Nul,
  Section,
  VariablePill,
  VerdictPill,
  clockIst,
  duration,
  langOf,
  num,
  score,
  text,
  varTone,
} from "../components/common";
import { href } from "../route";

/**
 * One verdict, and the way back to the words behind it.
 *
 * Every verdict that cites a turn is a real button: clicking it scrolls that turn
 * into view, rings it, and moves focus there so a screen reader lands on the
 * evidence rather than being told a highlight happened somewhere off-screen. A
 * verdict with no citation is deliberately not a button — nothing to go to.
 */
function VerdictRow({
  name,
  verdict,
  turnIndex,
  onCite,
  children,
}: {
  name: string;
  verdict: VariableVerdict;
  turnIndex: number | null;
  onCite: (index: number) => void;
  children: React.ReactNode;
}) {
  const body = (
    <>
      <span className="verdict-name">{name}</span>
      <VariablePill verdict={verdict} />
      {children}
      <span className="verdict-meta">
        {turnIndex === null ? (
          <span>No turn cited</span>
        ) : (
          <span>
            <CornerDownRight size={11} aria-hidden /> Turn {turnIndex + 1}
          </span>
        )}
      </span>
    </>
  );

  if (turnIndex === null) return <div className={`verdict-row ${varTone(verdict)}`}>{body}</div>;

  return (
    <button type="button" className={`verdict-row ${varTone(verdict)}`} onClick={() => onCite(turnIndex)}>
      {body}
    </button>
  );
}

function VariableRow({ v, onCite }: { v: VariableCheck; onCite: (i: number) => void }) {
  return (
    <VerdictRow name={v.name} verdict={v.verdict} turnIndex={v.turn_index} onCite={onCite}>
      <dl className="kv">
        <dt>Expected</dt>
        <dd className="expected">
          {/* Same set the engine treats as "not injected" (rules.ABSENT). A zero
              NCB or DTD is no discount at all, so there was nothing to say —
              printing "0" read as a value the agent had failed to quote. */}
          {["", "null", "none", "na", "n/a", "nil", "-", "0", "0.0", "0.00", "zero"].includes(
            (v.expected_raw ?? "").trim().toLowerCase(),
          ) ? (
            <Nul />
          ) : (
            v.expected_raw
          )}
          {v.expected_spoken ? <span className="muted"> · spoken as “{v.expected_spoken}”</span> : null}
        </dd>
        <dt>Found</dt>
        <dd>{v.spoken ? v.evidence ?? "Spoken, no evidence turn recorded" : "Not spoken"}</dd>
        {v.note ? (
          <>
            <dt>Note</dt>
            <dd>{v.note}</dd>
          </>
        ) : null}
      </dl>
      <span className="verdict-meta">
        <span className={`src ${v.checked_by}`}>{v.checked_by === "rule" ? "Rule" : "Model"}</span>
        <span className="tag">{v.required ? "Required" : "Optional"}</span>
      </span>
    </VerdictRow>
  );
}

export function CallDetailPage({ id }: { id: number }) {
  const { data, error, loading } = useResource<CallDetail>(`/calls/${id}`);
  const [cited, setCited] = useState<number | null>(null);
  const turns = useRef(new Map<number, HTMLDivElement>());

  function cite(index: number) {
    setCited(index);
    const el = turns.current.get(index);
    el?.scrollIntoView({ block: "center", behavior: "smooth" });
    el?.focus({ preventScroll: true });
  }

  if (error) return <div className="workspace"><ErrorState error={error} /></div>;
  if (loading || !data) return <div className="workspace"><LoadingBlock rows={8} /></div>;

  const lang = langOf(data.agent_id);
  const audited = data.verdict !== "no_transcript";

  return (
    <>
      <div className="page-head">
        <a className="btn btn-ghost" href={href({ name: "calls" })} style={{ marginBottom: "var(--s3)" }}>
          <ArrowLeft size={14} aria-hidden /> All calls
        </a>
        <h1>{text(data.customer_name)}</h1>
        <p>
          Call <span className="figure">{data.interaction_id}</span> · agent {data.agent_id} ·{" "}
          {lang === "ta" ? "Tamil" : "Hindi"} · {clockIst(data.started_at)} · {duration(data.duration_s)} ·{" "}
          {data.status}
          {data.call_stage ? ` · ${data.call_stage}` : ""}
        </p>
        {data.flags.length > 0 ? (
          <p className="flags">
            {data.flags.map((f) => (
              <span key={f} className="tag">
                {f}
              </span>
            ))}
          </p>
        ) : null}
      </div>

      <div className="workspace" style={{ display: "grid", gap: "var(--s4)" }}>
        <Section title="Verdict" subtitle={data.summary ?? undefined} tone="lilac">
          <div className="metrics">
            <div className="metric">
              <span className="metric-label">Score</span>
              <span className="metric-value figure">{score(data.score)}</span>
            </div>
            <div className="metric">
              <span className="metric-label">Overall</span>
              <span className="metric-value" style={{ fontSize: "var(--t-lead)" }}>
                <VerdictPill verdict={data.verdict} />
              </span>
            </div>
            <div className="metric">
              <span className="metric-label">Disposition</span>
              <span className="metric-value figure" style={{ fontSize: "var(--t-lead)" }}>
                {data.disposition ?? "null"}
              </span>
              <span className="metric-note">as the platform labelled it</span>
            </div>
            {/* Two columns, not one "failed" count. Saying a value wrong and never
                saying it are different mistakes with different remedies, and rolling
                them together read as "2 failed" on a call where every value the
                agent actually spoke was correct — the same conflation the score
                itself dropped. Counted here from the verdicts rather than the stored
                `variables_failed`, which is their sum. */}
            <div className="metric">
              <span className="metric-label">Wrong</span>
              <span className="metric-value figure">
                {num(data.variables.filter((v) => v.verdict === "wrong").length)}
              </span>
              <span className="metric-note">said, but not the customer's value</span>
            </div>
            <div className="metric">
              <span className="metric-label">Not spoken</span>
              <span className="metric-value figure">
                {num(data.variables.filter((v) => v.verdict === "missed").length)}{" "}
                <span className="metric-note">of {data.variables_checked} required</span>
              </span>
              <span className="metric-note">no value to be accurate about</span>
            </div>
            <div className="metric">
              <span className="metric-label">Reg no</span>
              <span className="metric-value figure" style={{ fontSize: "var(--t-lead)" }}>
                {text(data.reg_no)}
              </span>
            </div>
          </div>

          {/* Reviewer phrasing, verbatim — this is the vocabulary of the sheet. */}
          <dl className="kv">
            <dt>Verfication Error</dt>
            <dd>{text(data.verification_error)}</dd>
          </dl>
        </Section>

        {!audited ? (
          <div className="empty-state">
            <strong>Not audited</strong>
            This call never connected, so there is no transcript to check. It is not a failure.
          </div>
        ) : (
          <div className="detail-split">
            <Section title="Transcript" subtitle={`${data.transcript.length} turns`}>
              <div className="transcript pane-scroll" lang={lang}>
                {data.transcript.map((t) => (
                  <div
                    key={t.index}
                    ref={(el) => {
                      if (el) turns.current.set(t.index, el);
                      else turns.current.delete(t.index);
                    }}
                    tabIndex={-1}
                    aria-current={cited === t.index ? "true" : undefined}
                    className={`turn turn-${t.role === "user" ? "user" : "assistant"}${
                      cited === t.index ? " cited" : ""
                    }`}
                  >
                    <span className="turn-role" lang="en">
                      {t.role === "user" ? "Customer" : "Agent"} · turn {t.index + 1}
                    </span>
                    <p className="turn-text">{t.content}</p>
                  </div>
                ))}
              </div>
            </Section>

            <div style={{ display: "grid", gap: "var(--s4)" }}>
              <Section title="Variables" subtitle="Click a variable to jump to the turn it was judged on.">
                <div className="verdict-list">
                  {data.variables.map((v) => (
                    <VariableRow key={v.name} v={v} onCite={cite} />
                  ))}
                </div>
              </Section>

            </div>
          </div>
        )}
      </div>
    </>
  );
}
