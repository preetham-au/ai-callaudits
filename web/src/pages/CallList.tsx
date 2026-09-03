import { useEffect, useState } from "react";
import { Download } from "lucide-react";
import { API_BASE, useResource } from "../api/client";
import type { CallsPage } from "../api/types";
import { ErrorState, LoadingBlock, Section, VerdictPill, clockIst, dayIst, num, score, text } from "../components/common";
import { href } from "../route";

const PAGE_SIZE = 50;

function query(filters: { date: string; agent: string; verdict: string; q: string }, page?: number): string {
  const p = new URLSearchParams();
  if (filters.date) p.set("date", filters.date);
  if (filters.agent) p.set("agent_id", filters.agent);
  if (filters.verdict) p.set("verdict", filters.verdict);
  if (filters.q) p.set("q", filters.q);
  if (page !== undefined) {
    p.set("page", String(page));
    p.set("page_size", String(PAGE_SIZE));
  }
  return p.toString();
}

export function CallListPage({ date }: { date: string }) {
  const [agent, setAgent] = useState("");
  const [verdict, setVerdict] = useState("");
  const [q, setQ] = useState("");
  // Typing is not searching: the box only takes effect on submit, so every
  // keystroke does not fire a request against 687 rows.
  const [applied, setApplied] = useState("");
  const [page, setPage] = useState(1);

  // Page 4 of one day is rarely page 4 of another, and an out-of-range page
  // reads as "no calls" when the day is in fact full of them.
  useEffect(() => setPage(1), [date]);

  const filters = { date, agent, verdict, q: applied };
  const { data, error, loading } = useResource<CallsPage>(date ? `/calls?${query(filters, page)}` : null);
  const pages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  function change(set: (v: string) => void) {
    return (e: React.ChangeEvent<HTMLSelectElement>) => {
      set(e.target.value);
      setPage(1);
    };
  }

  return (
    <>
      <div className="page-head">
        <h1>Calls</h1>
        <p>{data ? `${data.total} calls match on ${date}` : "Loading calls"}</p>
      </div>

      <div className="workspace">
        <Section
          title="Audited calls"
          subtitle="Open a call to check every verdict against the words that were said."
          actions={
            /* Server-rendered, in the operator's existing sheet format. Nothing is
               assembled here — the CSV is the API's job, not the browser's. */
            <a className="btn" href={`${API_BASE}/export.csv?${query(filters)}`} download>
              <Download size={14} aria-hidden /> Download CSV
            </a>
          }
        >
          <form
            className="toolbar"
            onSubmit={(e) => {
              e.preventDefault();
              setApplied(q.trim());
              setPage(1);
            }}
          >
            <div className="field">
              <label htmlFor="f-agent">Agent</label>
              <select id="f-agent" className="select-input" value={agent} onChange={change(setAgent)}>
                <option value="">All agents</option>
                <option value="125">125 · Hindi</option>
                <option value="127">127 · Tamil</option>
              </select>
            </div>

            <div className="field">
              <label htmlFor="f-verdict">Verdict</label>
              <select id="f-verdict" className="select-input" value={verdict} onChange={change(setVerdict)}>
                <option value="">All verdicts</option>
                <option value="pass">Pass</option>
                <option value="warn">Warn</option>
                <option value="fail">Fail</option>
                <option value="no_transcript">Not audited</option>
              </select>
            </div>

            <div className="field" style={{ flex: "1 1 260px" }}>
              <label htmlFor="f-q">Search</label>
              <input
                id="f-q"
                className="text-input"
                type="search"
                placeholder="Reg no, policy no, customer or call id"
                value={q}
                onChange={(e) => setQ(e.target.value)}
              />
            </div>

            <button type="submit" className="btn btn-primary">
              Search
            </button>
          </form>

          {error ? <ErrorState error={error} /> : null}
          {loading || !data ? (
            <LoadingBlock rows={8} />
          ) : data.items.length === 0 ? (
            <div className="empty-state">
              <strong>No calls match these filters on {date}</strong>
              Clear the search, pick a different verdict, or choose another audit
              date.
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">Audited calls, most recent filters applied</caption>
                <thead>
                  <tr>
                    <th scope="col">Call</th>
                    <th scope="col">Call date</th>
                    <th scope="col">Customer</th>
                    <th scope="col">Reg no</th>
                    <th scope="col" className="num">Turns</th>
                    <th scope="col" className="num">Score</th>
                    <th scope="col">Verdict</th>
                    <th scope="col">Disposition</th>
                    <th scope="col" className="num">Vars failed</th>
                    <th scope="col">Verfication Error</th>
                  </tr>
                </thead>
                <tbody>
                  {data.items.map((c) => (
                    <tr key={c.interaction_id}>
                      <th scope="row" className="figure" style={{ textAlign: "left" }}>
                        <a href={href({ name: "call", id: c.interaction_id })}>{c.interaction_id}</a>
                        <div className="metric-note">{c.agent_id === 127 ? "Tamil" : "Hindi"}</div>
                      </th>
                      {/* Both IST: the dial times are stored with a +05:30 offset,
                          and the VM's own clock is UTC. */}
                      <td className="figure">
                        {dayIst(c.started_at)}
                        <div className="metric-note">{clockIst(c.started_at)} IST</div>
                      </td>
                      <td>{text(c.customer_name)}</td>
                      <td className="figure">{text(c.reg_no)}</td>
                      <td className="num">{num(c.turns)}</td>
                      <td className="num">{score(c.score)}</td>
                      <td>
                        <VerdictPill verdict={c.verdict} />
                      </td>
                      <td className="figure" style={{ fontSize: "var(--t-micro)" }}>
                        {text(c.disposition)}
                      </td>
                      <td className="num">
                        {c.variables_failed > 0 ? (
                          <strong>{c.variables_failed}</strong>
                        ) : (
                          num(c.variables_failed)
                        )}
                      </td>
                      {/* The reviewers' own phrasing, misspellings included, so this
                          reads the same as the sheet they already work in. */}
                      <td>{text(c.verification_error)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="pager">
            <span>
              Page {data?.page ?? page} of {pages}
            </span>
            <span className="spacer" />
            <button type="button" className="btn" disabled={page <= 1} onClick={() => setPage((p) => p - 1)}>
              Previous
            </button>
            <button type="button" className="btn" disabled={page >= pages} onClick={() => setPage((p) => p + 1)}>
              Next
            </button>
          </div>
        </Section>
      </div>
    </>
  );
}
