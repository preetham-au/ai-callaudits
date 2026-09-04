import { useEffect, useRef, useState } from "react";
import { Check, Download, ExternalLink, X } from "lucide-react";
import { API_BASE, send, useResource } from "../api/client";
import type { ManualItem, ManualOptions, ManualProgress, ManualQueue } from "../api/types";
import {
  ErrorState,
  LoadingBlock,
  Nul,
  Section,
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
 * fills in the same four fields the workbook had, over the transcript rather
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
  // Download-only. It deliberately does NOT narrow the queue: a reviewer's ten
  // are dealt across both languages on purpose, and quietly hiding half of them
  // would look like the deal was short.
  const [lang, setLang] = useState("");
  // Bumped after every save so the queue, and the progress beside it, both
  // re-read rather than showing an answer that is one save stale.
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
          subtitle="Every answer saves itself, so you can stop anywhere and pick it up later."
          wide
          actions={
            <>
              <select
                className="select-input"
                aria-label="Language to download"
                value={lang}
                onChange={(e) => setLang(e.target.value)}
              >
                <option value="">Both languages</option>
                <option value="125">Hindi only</option>
                <option value="127">Tamil only</option>
              </select>
              <a
                className="btn"
                href={`${API_BASE}/manual/export.csv?date_from=${day}&date_to=${day}${
                  lang ? `&agent_id=${lang}` : ""
                }`}
                download
              >
                {/* Says "submitted" because it means it: assignment deals ten to
                    everyone the moment a day is opened, so the file is always a
                    fraction of what is on screen. */}
                <Download size={14} aria-hidden /> Download submitted
              </a>
            </>
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

            <div className="field" style={{ flex: "1 1 240px" }}>
              <label>Your progress</label>
              <Progress done={queue.data?.done ?? 0} of={queue.data?.assigned ?? 0} />
            </div>
          </div>

          {/* Everyone's progress, so a supervisor does not have to switch names
              one by one to see where the day stands. */}
          {(progress.data?.items ?? []).length > 0 ? (
            <div className="toolbar" style={{ gap: "var(--s6)" }}>
              {progress.data?.items.map((p) => (
                <div key={p.auditor} className="field" style={{ flex: "1 1 180px" }}>
                  <label>{p.auditor}</label>
                  <Progress done={p.done} of={p.assigned} />
                </div>
              ))}
            </div>
          ) : null}

          {options.error ? <ErrorState error={options.error} /> : null}
          {queue.error ? <ErrorState error={queue.error} /> : null}
          {queue.loading && !queue.data ? <LoadingBlock rows={6} /> : null}

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
                <caption className="sr-only">
                  Calls assigned to {who} on {day}
                </caption>
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
                    <tr key={c.interaction_id}>
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
                        {c.verdict ? <strong>{c.verdict}</strong> : <span className="nul">not audited</span>}
                      </td>
                      <td>
                        <button
                          type="button"
                          className={c.submitted_at ? "btn" : "btn btn-primary"}
                          onClick={() => setOpen(c.interaction_id)}
                        >
                          {c.submitted_at ? "Review" : "Audit"}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Section>
      </div>

      {current && options.data ? (
        <AuditDialog
          key={current.interaction_id}
          call={current}
          options={options.data}
          date={day}
          auditor={who}
          position={items.findIndex((i) => i.interaction_id === current.interaction_id) + 1}
          total={items.length}
          onClose={() => setOpen(null)}
          onNext={() => {
            const i = items.findIndex((c) => c.interaction_id === current.interaction_id);
            setOpen(i + 1 < items.length ? items[i + 1].interaction_id : null);
          }}
          onSaved={() => setSaved((n) => n + 1)}
        />
      ) : null}
    </>
  );
}

function Progress({ done, of }: { done: number; of: number }) {
  const pct = of > 0 ? Math.round((done / of) * 100) : 0;
  return (
    <div className="progress-row">
      <div
        className="progress-bar"
        role="progressbar"
        aria-valuenow={done}
        aria-valuemin={0}
        aria-valuemax={of}
        aria-label={`${done} of ${of} audited`}
      >
        <span style={{ width: `${pct}%` }} />
      </div>
      <span className="figure" style={{ fontSize: "var(--t-micro)" }}>
        {done}/{of}
      </span>
    </div>
  );
}

type SaveState = "clean" | "saving" | "saved" | "failed";

/** How long after the last keystroke a save fires. Long enough not to POST per
 *  character, short enough that closing the tab mid-thought keeps the note. */
const AUTOSAVE_MS = 700;

function AuditDialog({
  call,
  options,
  date,
  auditor,
  position,
  total,
  onClose,
  onNext,
  onSaved,
}: {
  call: ManualItem;
  options: ManualOptions;
  date: string;
  auditor: string;
  position: number;
  total: number;
  onClose: () => void;
  onNext: () => void;
  onSaved: () => void;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const [form, setForm] = useState({
    info_accuracy: call.info_accuracy ?? "",
    verdict: call.verdict ?? "",
    notes: call.notes ?? "",
  });
  const [state, setState] = useState<SaveState>("clean");
  const [error, setError] = useState<string | null>(null);

  const url = `/manual/${call.interaction_id}?auditor=${encodeURIComponent(auditor)}&date=${date}`;
  // What the server last accepted, and what the form holds right now. Both are
  // refs so the unmount flush below can compare them without re-subscribing.
  const stored = useRef(JSON.stringify(form));
  const latest = useRef(form);
  latest.current = form;

  // showModal() rather than the `open` attribute: only the former puts the
  // dialog in the top layer, with a backdrop and Escape handled for us.
  useEffect(() => {
    const el = ref.current;
    if (el && !el.open) el.showModal();
  }, []);

  // Autosave. The reviewer never presses Save; leaving mid-call keeps whatever
  // was picked, and reopening the row shows it back. Skips the first render so
  // merely opening a call does not write a row.
  const first = useRef(true);
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    setState("saving");
    const body = JSON.stringify(form);
    const t = setTimeout(async () => {
      try {
        await send(url, "POST", form);
        stored.current = body;
        setState("saved");
        setError(null);
        onSaved();
      } catch (e) {
        setState("failed");
        setError(e instanceof Error ? e.message : String(e));
      }
    }, AUTOSAVE_MS);
    return () => clearTimeout(t);
    // onSaved is a fresh closure each render; only the form should trigger a save.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [form, url]);

  /* Closing cancels the pending debounce, so anything picked in the last
     AUTOSAVE_MS would be lost — which is precisely the moment a reviewer picks
     a verdict and moves on. Flush it on the way out. */
  useEffect(() => {
    const flush = () => {
      if (JSON.stringify(latest.current) !== stored.current) {
        void send(url, "POST", latest.current).catch(() => undefined);
      }
    };
    window.addEventListener("pagehide", flush);
    return () => {
      window.removeEventListener("pagehide", flush);
      flush();
    };
  }, [url]);

  function set(key: keyof typeof form) {
    return (e: React.ChangeEvent<HTMLSelectElement | HTMLTextAreaElement>) =>
      setForm((f) => ({ ...f, [key]: e.target.value }));
  }

  const filled = [form.info_accuracy, form.verdict].filter(Boolean).length;

  return (
    <dialog
      ref={ref}
      className="audit-dialog"
      aria-label={`Audit call ${call.interaction_id}`}
      onClose={onClose}
      // A click on the backdrop lands on the dialog itself, never on its content.
      onClick={(e) => {
        if (e.target === ref.current) ref.current?.close();
      }}
    >
      <div className="audit-dialog-head">
        <div style={{ flex: "1 1 auto", minWidth: 0 }}>
          <h2>
            {text(call.customer_name)} · <span className="figure">{call.interaction_id}</span>
          </h2>
          <p className="card-sub" style={{ margin: 0 }}>
            Call {position} of {total} · {call.language} · {dayIst(call.started_at)}{" "}
            {clockIst(call.started_at)} IST · {duration(call.duration_s)} · {call.turns} turns
          </p>
        </div>

        <Saved state={state} error={error} filled={filled} />

        <button type="button" className="btn btn-icon btn-ghost" aria-label="Close" onClick={() => ref.current?.close()}>
          <X size={18} aria-hidden />
        </button>
      </div>

      <div className="audit-dialog-body">
        <div className="detail-split">
          <Section title="Transcript" subtitle={`${call.transcript.length} turns`}>
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
            <Section title="Recording" subtitle="Listen while you read the transcript">
              <Recording url={call.recording_url} />
            </Section>

            <Section title="What was fed to the agent" subtitle="Check these against what was said">
              <p className="figure" style={{ margin: 0, fontSize: "var(--t-micro)", lineHeight: 1.7 }}>
                {call.pre_call || <Nul />}
              </p>
            </Section>

            <Section title="Your audit" tone="sage">
              <div style={{ display: "grid", gap: "var(--s3)" }}>
                <Pick
                  id="f-info"
                  label="During-call info accuracy"
                  value={form.info_accuracy}
                  options={options.info_accuracy}
                  onChange={set("info_accuracy")}
                />
                {/* The platform's label sits beside the reviewer's own call rather
                    than being re-picked: they are two different judgements and the
                    report needs both. */}
                <div className="field">
                  <label>Platform disposition</label>
                  <div>
                    <span className="figure">{text(call.disposition)}</span>
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
                  <textarea id="f-notes" className="text-input" rows={4} value={form.notes} onChange={set("notes")} />
                </div>

                {error ? <ErrorState error={new Error(error)} /> : null}

                <div className="card-actions">
                  {/* Straight to the next call without closing: the parent
                      swaps in a new dialog, keyed by call, and this one's
                      unmount flushes whatever was just picked. */}
                  <button type="button" className="btn btn-primary" disabled={position >= total} onClick={onNext}>
                    Next call
                  </button>
                  <button type="button" className="btn" onClick={() => ref.current?.close()}>
                    Done for now
                  </button>
                </div>
              </div>
            </Section>
          </div>
        </div>
      </div>
    </dialog>
  );
}

/**
 * The call, played here rather than in a new tab.
 *
 * A plain <audio>: the bucket serves audio/mpeg and honours range requests, so
 * the browser's own controls already give play, seek and speed, and none of it
 * is worth a player dependency. `preload="none"` so opening a call does not
 * pull a recording nobody asked to hear.
 */
function Recording({ url }: { url: string | null }) {
  const [broken, setBroken] = useState(false);

  if (!url) {
    return <p className="nul" style={{ margin: 0 }}>No recording for this call.</p>;
  }
  return (
    <>
      <audio
        controls
        preload="none"
        src={url}
        style={{ width: "100%" }}
        onError={() => setBroken(true)}
      >
        Your browser cannot play audio.
      </audio>
      {broken ? (
        <p className="autosave failed" style={{ margin: 0 }}>
          The recording would not load — open it directly to check it exists.
        </p>
      ) : null}
      {/* Kept as a way out: downloading it is the only option if the browser
          refuses the codec, or the reviewer wants it offline. */}
      <p style={{ margin: 0 }}>
        <a className="btn btn-ghost" href={url} target="_blank" rel="noreferrer">
          <ExternalLink size={14} aria-hidden /> Open the file
        </a>
      </p>
    </>
  );
}

function Saved({ state, error, filled }: { state: SaveState; error: string | null; filled: number }) {
  if (state === "failed") {
    return (
      <span className="autosave failed" role="status">
        Not saved — {error}
      </span>
    );
  }
  if (state === "saving") {
    return (
      <span className="autosave" role="status">
        Saving…
      </span>
    );
  }
  if (state === "saved") {
    return (
      <span className="autosave" role="status">
        <Check size={13} aria-hidden /> Saved {filled}/2
      </span>
    );
  }
  return (
    <span className="autosave" role="status">
      Saves as you go
    </span>
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
