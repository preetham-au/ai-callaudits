import { useEffect, useState } from "react";
import { CalendarClock, Play, Square } from "lucide-react";
import { send, useResource } from "../api/client";
import type { Job, JobsPage, Schedule } from "../api/types";
import { ErrorState, LoadingBlock, Section, clockIst, duration, text } from "../components/common";

/* A run takes minutes, so the page polls — but only while something is actually
   running. An idle console must not sit there hitting the API every 3 seconds. */
const POLL_MS = 3000;

const STATUS_PILL: Record<Job["status"], string> = {
  running: "warn",
  done: "pass",
  failed: "fail",
  /* Not a failure of the audit: someone pressed stop, or the service restarted
     under it. Shown grey so it never reads as "the audit found something bad". */
  cancelled: "no_transcript",
  interrupted: "no_transcript",
};

const STATUS_LABEL: Record<Job["status"], string> = {
  running: "Running",
  done: "Done",
  failed: "Failed",
  cancelled: "Cancelled",
  interrupted: "Interrupted",
};

function day(iso: string | null): string {
  return iso ? new Date(iso).toLocaleDateString("en-IN", { timeZone: "Asia/Kolkata", day: "2-digit", month: "short" }) : "—";
}

export function RunsPage() {
  const [tick, setTick] = useState(0);
  const [selected, setSelected] = useState<number | null>(null);
  const [date, setDate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  const jobs = useResource<JobsPage>("/jobs?limit=25", tick);
  const sched = useResource<Schedule>("/schedule", tick);

  const running = jobs.data?.running ?? null;
  const shownId = selected ?? running?.id ?? jobs.data?.items[0]?.id ?? null;
  const detail = useResource<Job>(shownId === null ? null : `/jobs/${shownId}`, tick);

  // Poll only while a job is live. The effect re-arms off `tick`, so it stops of
  // its own accord the moment the job leaves `running`.
  useEffect(() => {
    if (!running) return;
    const t = setTimeout(() => setTick((n) => n + 1), POLL_MS);
    return () => clearTimeout(t);
  }, [running, tick]);

  // The date box starts on yesterday, which the API works out in IST — the
  // browser's own date is the wrong clock when the operator is not in India.
  useEffect(() => {
    if (!date && jobs.data?.default_date) setDate(jobs.data.default_date);
  }, [jobs.data, date]);

  const [enabled, setEnabled] = useState(false);
  const [time, setTime] = useState("23:30");
  const [target, setTarget] = useState<Schedule["target"]>("today");
  const [loadedSchedule, setLoadedSchedule] = useState(false);
  useEffect(() => {
    if (loadedSchedule || !sched.data) return;
    setEnabled(sched.data.enabled);
    setTime(sched.data.time);
    setTarget(sched.data.target);
    setLoadedSchedule(true);
  }, [sched.data, loadedSchedule]);

  async function act<T>(fn: () => Promise<T>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      setTick((n) => n + 1);
    }
  }

  const startRun = () =>
    act(async () => {
      const job = await send<Job>("/jobs", "POST", { date });
      setSelected(job.id);
    });

  const saveSchedule = () =>
    act(async () => {
      await send<Schedule>("/schedule", "PUT", { enabled, time, target });
      setSaved(true);
      setTimeout(() => setSaved(false), 2500);
    });

  return (
    <>
      <div className="page-head">
        <h1>Runs</h1>
        <p>
          {running
            ? `Auditing ${running.audit_date} — started ${clockIst(running.started_at)}`
            : "Start an audit by hand, or leave it to the nightly schedule."}
        </p>
      </div>

      <div className="workspace">
        <Section
          title="Run an audit"
          subtitle="Fetches that day's calls from Metabase, judges each transcript, and writes the results the rest of this console reads."
          tone="sky"
        >
          <div className="toolbar">
            <div className="field">
              <label htmlFor="run-date">Date to audit</label>
              <input
                id="run-date"
                className="text-input"
                type="date"
                value={date}
                max={new Date().toISOString().slice(0, 10)}
                onChange={(e) => setDate(e.target.value)}
              />
            </div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || !date || Boolean(running)}
              onClick={startRun}
            >
              <Play size={14} aria-hidden /> Run now
            </button>
            {running ? (
              <button type="button" className="btn" disabled={busy} onClick={() => act(() => send<Job>(`/jobs/${running.id}/cancel`, "POST"))}>
                <Square size={14} aria-hidden /> Stop
              </button>
            ) : null}
          </div>

          <p className="card-sub" style={{ marginTop: "var(--s3)" }}>
            {running
              ? "One audit at a time — they would otherwise overwrite each other's rows."
              : "Re-running a date replaces that day's results. Judgements already made are cached, so a repeat run is quick and costs no GPU time."}
          </p>
          {error ? <ErrorState error={new Error(error)} /> : null}
        </Section>

        <Section
          title="Nightly schedule"
          subtitle={`Fires once a day in ${sched.data?.timezone ?? "Asia/Kolkata"}, on the server. Nothing needs to be open.`}
          tone="sage"
        >
          <div className="toolbar">
            <div className="field">
              <label htmlFor="sch-on">Automatic audits</label>
              <label className="check-row">
                <input id="sch-on" type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} />
                <span>{enabled ? "On" : "Off"}</span>
              </label>
            </div>

            <div className="field">
              <label htmlFor="sch-time">Time (IST)</label>
              <input
                id="sch-time"
                className="text-input"
                type="time"
                value={time}
                onChange={(e) => setTime(e.target.value)}
              />
            </div>

            <div className="field">
              <label htmlFor="sch-target">Audit</label>
              <select
                id="sch-target"
                className="select-input"
                value={target}
                onChange={(e) => setTarget(e.target.value as Schedule["target"])}
              >
                <option value="today">Calls from that same day</option>
                <option value="yesterday">Calls from the day before</option>
              </select>
            </div>

            <button type="button" className="btn btn-primary" disabled={busy} onClick={saveSchedule}>
              {saved ? "Saved" : "Save schedule"}
            </button>
          </div>

          <p className="card-sub" style={{ marginTop: "var(--s3)" }}>
            <CalendarClock size={13} aria-hidden style={{ verticalAlign: "-2px", marginRight: 6 }} />
            {sched.data?.enabled && sched.data.next_run
              ? `Next run ${day(sched.data.next_run)} at ${clockIst(sched.data.next_run)}, covering ${sched.data.next_target_date}.`
              : "Off — no audit will run unless you press Run now."}
            {sched.data?.last_fired ? ` Last fired ${sched.data.last_fired}.` : ""}
          </p>
          <p className="card-sub">
            {/* Said plainly because it is the one way the schedule quietly does nothing. */}
            If the server is down across the scheduled time and only returns the next day, that night is skipped — start it by hand.
          </p>
        </Section>

        <Section title="Recent runs" subtitle="Pick a run to read its log." wide>
          {jobs.error ? <ErrorState error={jobs.error} /> : null}
          {jobs.loading && !jobs.data ? (
            <LoadingBlock rows={5} />
          ) : !jobs.data?.items.length ? (
            <div className="empty-state">
              <strong>No runs yet</strong>
              Press Run now, or switch the nightly schedule on.
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Audit runs, newest first</caption>
                <thead>
                  <tr>
                    <th scope="col">Run</th>
                    <th scope="col">Audited date</th>
                    <th scope="col">Started</th>
                    <th scope="col">Trigger</th>
                    <th scope="col">Status</th>
                    <th scope="col" className="num">Took</th>
                  </tr>
                </thead>
                <tbody>
                  {jobs.data.items.map((j) => (
                    <tr
                      key={j.id}
                      onClick={() => setSelected(j.id)}
                      style={{ cursor: "pointer", background: j.id === shownId ? "var(--surface-2)" : undefined }}
                    >
                      <th scope="row" className="figure" style={{ textAlign: "left" }}>
                        #{j.id}
                      </th>
                      <td className="figure">{j.audit_date}</td>
                      <td className="figure">
                        {day(j.started_at)} {clockIst(j.started_at)}
                      </td>
                      <td>{j.trigger === "schedule" ? "Scheduled" : "By hand"}</td>
                      <td>
                        <span className={`pill ${STATUS_PILL[j.status]}`}>{STATUS_LABEL[j.status]}</span>
                        {j.exit_code ? <div className="metric-note">exit {j.exit_code}</div> : null}
                      </td>
                      <td className="num">{duration(j.duration_s)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {shownId !== null ? (
            <>
              <h3 className="card-title" style={{ marginTop: "var(--s5)", fontSize: "var(--t-body)" }}>
                Log — run #{shownId}
              </h3>
              <pre className="log-pane" aria-live={running ? "polite" : "off"}>
                {detail.data?.log?.trim() || (detail.loading ? "Loading…" : "No output yet.")}
              </pre>
              {detail.data && detail.data.status === "failed" ? (
                <p className="card-sub">
                  Exit code {text(String(detail.data.exit_code))}. The last lines above say why — most often Metabase or the
                  judge was unreachable. Nothing was written for that date.
                </p>
              ) : null}
            </>
          ) : null}
        </Section>
      </div>
    </>
  );
}
