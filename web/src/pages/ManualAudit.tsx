import { useEffect, useState } from "react";
import { Check, Download, ExternalLink } from "lucide-react";
import { API_BASE, send, useResource } from "../api/client";
import type { ManualItem, ManualOptions, ManualProgress, ManualQueue } from "../api/types";
import {
  ErrorState,
  LoadingBlock,
  Nul,
  Section,
  VerdictPill,
  clockIst,
  dayIst,
  duration,
  langOf,
  text,
} from "../components/common";

/*
 * Manual audits — the by-hand replacement for "Chola Call Audits.xlsx".
 *
 * A reviewer picks their name, gets ten of yesterday's real conversations, and
 * fills in the same four fields the workbook had, next to the transcript rather
 * than in a separate tab. There is no login: the workbook had none either, and
 * the name is a label on the row, not a claim about who is typing.
 *
 * The dropdown values come from /manual/options rather than being written out
 * here, so the workbook's allowed answers have exactly one definition.
 */

const REMEMBER = "audits:auditor";

export function ManualAuditPage() {
  const options = useResource<ManualOptions>("/manual/options");
  const [who, setWho] = useState(() => localStorage.getItem(REMEMBER) ?? "");
  const [date, setDate] = useState("");
  const [open, setOpen] = useState<number | null>(null);
  // Bumped after every save so the queue, and the progress strip beside it,
  // both re-read rather than showing an answer that is one submit stale.
  const [saved, setSaved] = useState(0);

  const day = date || options.data?.default_date || "";
  // A reviewer who has picked a name before goes straight to their list.
  useEffect(() => {
    if (!who && options.data?.auditors.length) setWho(options.data.auditors[0]);
  }, [options.data, who]);
  useEffect(() => {
    if (who) localStorage.setItem(REMEMBER, who);
  }, [who]);

  const queue = useResource<ManualQueue>(
    who && day ? `/manual/queue?auditor=${encodeURIComponent(who)}&date=${day}` : null,
    saved,
  );
  const progress = useResource<ManualProgress>(day ? `/manual/progress?date=${day}` : null, saved);

  const items = queue.data?.items ?? [];
  const current = items.find((i) => i.interaction_id === open) ?? null;

  return (
    <>
      <div className="page-head">
        <h1>Manual audits</h1>
        <p>
          {options.data
            ? `${options.data.per_auditor} of the previous day's real conversations each — voicemail and unanswered calls are the engine's job.`
            : "Loading"}
        </p>
      </div>

      <div className="workspace">
        <Section
          title="Your queue"
          subtitle={
            queue.data ? `${queue.data.done} of ${queue.data.assigned} audited` : "Pick your name to start"
          }
          wide
          actions={
            <a className="btn" href={`${API_BASE}/manual/export.csv?date_from=${day}&date_to=${day}`} download>
              <Download size={14} aria-hidden /> Download report
            </a>
          }
        >
          <div className="toolbar">
            <div className="field">
              <label htmlFor="m-who">I am</label>
              <select
                id="m-who"
                className="select-input"
                value={who}
                onChange={(e) => {
                  setWho(e.target.value);
                  setOpen(null);
                }}
              >
                {(options.data?.auditors ?? []).map((n) => (
                  <option key={n} value={n}>
                    {n}
                  </option>
                ))}
              </select>
            </div>

            <div className="field">
              <label htmlFor="m-date">Call date</label>
              {/* Native date input: no picker dependency, and it already knows
                  the operator's locale format. */}
              <input
                id="m-date"
                className="text-input"
                type="date"
                value={day}
                max={options.data?.default_date}
                onChange={(e) => {
                  setDate(e.target.value);
                  setOpen(null);
                }}
              />
            </div>

            <span className="spacer" />

            {(progress.data?.items ?? []).map((p) => (
              <span key={p.auditor} className="sync-pill">
                {p.auditor} {p.done}/{p.assigned}
              </span>
            ))}
          </div>

          {options.error ? <ErrorState error={options.error} /> : null}
          {queue.error ? <ErrorState error={queue.error} /> : null}
          {queue.loading ? <LoadingBlock rows={6} /> : null}

          {queue.data && items.length === 0 ? (
            <div className="empty-state">
              <strong>Nothing assigned for {day}</strong>
              That day has no audited calls yet, or none of them were real conversations. Run the
              engine for it first.
            </div>
          ) : null}

          {items.length > 0 ? (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Calls assigned to {who} on {day}</caption>
                <thead>
                  <tr>
                    <th scope="col">Call</th>
                    <th scope="col">Call date</th>
                    <th scope="col">Customer</th>
                    <th scope="col">Reg no</th>
                    <th scope="col" className="num">Length</th>
                    <th scope="col">Platform disposition</th>
                    <th scope="col">Your verdict</th>
                    <th scope="col" />
                  </tr>
                </thead>
                <tbody>
                  {items.map((c) => (
                    <tr key={c.interaction_id} aria-selected={open === c.interaction_id}>
                      <th scope="row" className="figure" style={{ textAlign: "left" }}>
                        {c.interaction_id}
                        <div className="metric-note">{c.language}</div>
                      </th>
                      <td className="figure">
                        {dayIst(c.started_at)}
                        <div className="metric-note">{clockIst(c.started_at)} IST</div>
                      </td>
                      <td>{text(c.customer_name)}</td>
                      <td className="figure">{text(c.reg_no)}</td>
                      <td className="num">{duration(c.duration_s)}</td>
                      <td>
                        <div className="figure" style={{ fontSize: "var(--t-micro)" }}>
                          {text(c.disposition)}
                        </div>
                      </td>
                      <td>
                        {c.verdict ? (
                          <strong>{c.verdict}</strong>
                        ) : (
                          <span className="nul">not audited</span>
                        )}
                      </td>
                      <td>
                        <button
                          type="button"
                          className="btn"
                          onClick={() =>
                            setOpen(open === c.interaction_id ? null : c.interaction_id)
                          }
                        >
                          {open === c.interaction_id ? "Close" : c.submitted_at ? "Review" : "Audit"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Section>

        {current && options.data ? (
          <AuditPanel
            key={current.interaction_id}
            call={current}
            options={options.data}
            date={day}
            auditor={who}
            onSaved={() => setSaved((n) => n + 1)}
          />
        ) : null}
      </div>
    </>
  );
}

function AuditPanel({
  call,
  options,
  date,
  auditor,
  onSaved,
}: {
  call: ManualItem;
  options: ManualOptions;
  date: string;
  auditor: string;
  onSaved: () => void;
}) {
  const [form, setForm] = useState({
    info_accuracy: call.info_accuracy ?? "",
    call_flow: call.call_flow ?? "",
    verdict: call.verdict ?? "",
    notes: call.notes ?? "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const [done, setDone] = useState(false);

  function set(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLSelectElement | HTMLTextAreaElement>) => {
      setForm((f) => ({ ...f, [key]: e.target.value }));
      setDone(false);
    };
  }

  async function save(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await send(
        `/manual/${call.interaction_id}?auditor=${encodeURIComponent(auditor)}&date=${date}`,
        "POST",
        form,
      );
      setDone(true);
      onSaved();
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="detail-split span-full">
      <Section title="Transcript" subtitle={`${call.transcript.length} turns · call ${call.interaction_id}`}>
        <div className="transcript pane-scroll" lang={langOf(call.agent_id)}>
          {call.transcript.map((t) => (
            <div key={t.index} className={`turn turn-${t.role === "user" ? "user" : "assistant"}`}>
              <span className="turn-role" lang="en">
                {t.role === "user" ? "Customer" : "Agent"} · turn {t.index + 1}
              </span>
              <p className="turn-text">{t.content}</p>
            </div>
          ))}
        </div>
      </Section>

      <div style={{ display: "grid", gap: "var(--s4)" }}>
        <Section title="What was fed to the agent" subtitle="Check these against what was said">
          <p className="figure" style={{ margin: 0, fontSize: "var(--t-micro)", lineHeight: 1.7 }}>
            {call.pre_call || <Nul />}
          </p>
          <p style={{ marginBottom: 0 }}>
            <a className="btn btn-ghost" href={call.recording_url} target="_blank" rel="noreferrer">
              <ExternalLink size={14} aria-hidden /> Recording
            </a>
          </p>
        </Section>

        <Section title="Your audit" tone="sage">
          <form onSubmit={save} style={{ display: "grid", gap: "var(--s3)" }}>
            <Pick
              id="f-info"
              label="During-call info accuracy"
              value={form.info_accuracy}
              options={options.info_accuracy}
              onChange={set("info_accuracy")}
            />
            <Pick
              id="f-flow"
              label="Call flow"
              value={form.call_flow}
              options={options.call_flow}
              onChange={set("call_flow")}
            />

            {/* The platform's label sits beside the reviewer's own call rather
                than being re-picked: they are two different judgements and the
                report needs both. */}
            <div className="field">
              <label>Platform disposition</label>
              <div>
                <span className="figure">{text(call.disposition)}</span>{" "}
                <VerdictPill verdict={call.disposition_verdict} />
              </div>
            </div>

            <Pick
              id="f-verdict"
              label="Final disposition"
              value={form.verdict}
              options={options.verdicts}
              onChange={set("verdict")}
            />

            <div className="field">
              <label htmlFor="f-notes">Notes</label>
              <textarea
                id="f-notes"
                className="text-input"
                rows={4}
                value={form.notes}
                onChange={set("notes")}
              />
            </div>

            {error ? <ErrorState error={error} /> : null}

            <div className="card-actions">
              <button type="submit" className="btn btn-primary" disabled={busy}>
                {busy ? "Saving" : "Save"}
              </button>
              {/* Notes alone is a draft; a call only counts as audited once a
                  final disposition is picked, which is what the report asks for. */}
              {done ? (
                <span className="sync-pill">
                  <Check size={14} aria-hidden /> {form.verdict ? "Audited" : "Draft saved"}
                </span>
              ) : null}
            </div>
          </form>
        </Section>
      </div>
    </div>
  );
}

function Pick({
  id,
  label,
  value,
  options,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  options: string[];
  onChange: (e: React.ChangeEvent<HTMLSelectElement>) => void;
}) {
  return (
    <div className="field">
      <label htmlFor={id}>{label}</label>
      <select id={id} className="select-input" value={value} onChange={onChange}>
        <option value="">Not picked</option>
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </div>
  );
}
