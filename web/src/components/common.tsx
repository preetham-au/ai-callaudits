import type { ReactNode } from "react";
import { AlertTriangle } from "lucide-react";
import type { CallVerdict, VariableVerdict } from "../api/types";

export type Tone = "plain" | "yellow" | "pink" | "sage" | "sky" | "lilac";

export function Section({
  title,
  subtitle,
  actions,
  tone = "plain",
  wide = false,
  children,
}: {
  title: string;
  subtitle?: string;
  actions?: ReactNode;
  tone?: Tone;
  /** Span both columns of the page grid. */
  wide?: boolean;
  children: ReactNode;
}) {
  return (
    <section
      className={`card${tone === "plain" ? "" : ` tone-${tone}`}${wide ? " span-full" : ""}`}
      aria-label={title}
    >
      <div className="card-head">
        <div>
          <h2 className="card-title">{title}</h2>
          {subtitle ? <div className="card-sub">{subtitle}</div> : null}
        </div>
        {actions ? <div className="card-actions">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export function LoadingBlock({ rows = 4 }: { rows?: number }) {
  return (
    <div style={{ display: "grid", gap: 10 }} aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="skeleton" style={{ height: 16 }} role="presentation" />
      ))}
    </div>
  );
}

export function ErrorState({ error }: { error: Error }) {
  return (
    <div className="error-state" role="alert">
      <AlertTriangle size={22} aria-hidden />
      <p style={{ margin: 0 }}>{error.message}</p>
    </div>
  );
}

const VERDICT_LABEL: Record<CallVerdict, string> = {
  pass: "Pass",
  warn: "Warn",
  fail: "Fail",
  /* Never "fail": nobody picked up, so there was nothing to audit. */
  no_transcript: "Not audited",
};

export function VerdictPill({ verdict }: { verdict: CallVerdict }) {
  return <span className={`pill ${verdict}`}>{VERDICT_LABEL[verdict]}</span>;
}

/**
 * A variable's verdict is not a call's verdict, and was never displayable.
 *
 * The engine says ok/missed/wrong/n-a/not_reached; this map was pass/warn/fail,
 * so every variable pill rendered its label as `undefined` (blank) and its row
 * carried a class no stylesheet matches. Rather than five new colours, each one
 * borrows the tone it means: a wrong value reads like a failure, silence like a
 * warning, and the two "nothing to judge" cases like an unaudited call.
 */
const VAR_VERDICT: Record<string, { label: string; tone: string }> = {
  ok: { label: "Correct", tone: "pass" },
  wrong: { label: "Wrong", tone: "fail" },
  missed: { label: "Not spoken", tone: "warn" },
  "n/a": { label: "Not injected", tone: "no_transcript" },
  not_reached: { label: "Call ended first", tone: "no_transcript" },
};

/** Falls back to the raw word: an unknown verdict must still be readable. */
export function varTone(verdict: string): string {
  return VAR_VERDICT[verdict]?.tone ?? "no_transcript";
}

export function VariablePill({ verdict }: { verdict: VariableVerdict }) {
  return <span className={`pill ${varTone(verdict)}`}>{VAR_VERDICT[verdict]?.label ?? verdict}</span>;
}

/**
 * A field the source genuinely has no value for.
 *
 * Shown as the word, not as `0` or `—`: "no premium was injected" and "the
 * premium is zero" are different facts and the operator acts on them differently.
 */
export function Nul() {
  return <span className="nul">null</span>;
}

export function text(value: string | null | undefined): ReactNode {
  return value === null || value === undefined || value === "" ? <Nul /> : value;
}

export function num(value: number | null | undefined): ReactNode {
  return value === null || value === undefined ? <Nul /> : new Intl.NumberFormat("en-IN").format(value);
}

export function score(value: number | null | undefined): ReactNode {
  return value === null || value === undefined ? <span className="nul">not audited</span> : value.toFixed(0);
}

export function pct(value: number | null | undefined): ReactNode {
  return value === null || value === undefined ? <Nul /> : `${value.toFixed(1)}%`;
}

export function duration(seconds: number | null): ReactNode {
  if (seconds === null) return <Nul />;
  return `${String(Math.floor(seconds / 60)).padStart(2, "0")}:${String(Math.round(seconds % 60)).padStart(2, "0")}`;
}

export function clockIst(iso: string | null): ReactNode {
  if (!iso) return <Nul />;
  return new Date(iso).toLocaleTimeString("en-IN", { timeZone: "Asia/Kolkata", hour: "2-digit", minute: "2-digit" });
}

/**
 * Today in IST as `yyyy-mm-dd`, for a date input's upper bound.
 *
 * en-CA because it is the one common locale whose short date IS the ISO form,
 * which is what `<input type="date">` wants. The VM's clock is UTC, so before
 * 05:30 IST a naive `toISOString()` would name yesterday and quietly forbid
 * picking the day the operator is actually in.
 */
export function todayIst(): string {
  return new Date().toLocaleDateString("en-CA", { timeZone: "Asia/Kolkata" });
}

/** The day the call was made, in IST — a run started at 23:30 UTC audits "yesterday". */
export function dayIst(iso: string | null): ReactNode {
  if (!iso) return <Nul />;
  return new Date(iso).toLocaleDateString("en-IN", {
    timeZone: "Asia/Kolkata",
    day: "2-digit",
    month: "short",
  });
}

/** BCP-47 tag for a transcript, so screen readers switch voice and fonts pick the right face. */
export function langOf(agentId: number): "hi" | "ta" {
  return agentId === 127 ? "ta" : "hi";
}
