import { useResource } from "../api/client";
import type { Summary } from "../api/types";
import { ErrorState, LoadingBlock, Section, num, pct } from "../components/common";

/** Segment width, floored so a small-but-real slice never disappears entirely. */
function share(part: number, whole: number): string {
  return whole > 0 ? `${Math.max((part / whole) * 100, 3)}%` : "0%";
}

function Bar({ value }: { value: number }) {
  const level = value < 60 ? "bad" : value < 85 ? "warn" : "";
  return (
    <div className={`bar ${level}`} role="img" aria-label={`${value.toFixed(1)} percent accurate`}>
      <span style={{ width: `${Math.max(Math.min(value, 100), 0)}%` }} />
    </div>
  );
}

export function OverviewPage({ date }: { date: string }) {
  const { data, error, loading } = useResource<Summary>(date ? `/summary?date=${date}` : null);

  return (
    <>
      <div className="page-head">
        <h1>Overview</h1>
        <p>{data ? `Audit for ${data.date}` : "Loading the day's audit"}</p>
      </div>

      <div className="workspace">
        {error ? <ErrorState error={error} /> : null}
        {loading || !data ? (
          <LoadingBlock rows={6} />
        ) : data.totals.calls === 0 ? (
          /* A day nobody audited is not the same as a day that went perfectly.
             Say so, rather than rendering a wall of confident zeroes. */
          <div className="empty-state">
            <strong>No audit for {data.date}</strong>
            Nothing has been audited for this date. Pick another day, or start a
            run for it on the Runs page.
          </div>
        ) : (
          <div className="grid">
            <Section
              title="The day"
              subtitle={`${data.totals.calls} calls placed, ${data.totals.audited} with a transcript to audit`}
              tone="lilac"
              wide
            >
              <div className="metrics">
                <div className="metric">
                  <span className="metric-label">Audited</span>
                  <span className="metric-value figure">{num(data.totals.audited)}</span>
                  <span className="metric-note">of {num(data.totals.calls)} calls</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Pass</span>
                  <span className="metric-value figure">{num(data.totals.pass)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Warn</span>
                  <span className="metric-value figure">{num(data.totals.warn)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Fail</span>
                  <span className="metric-value figure">{num(data.totals.fail)}</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Average score</span>
                  <span className="metric-value figure">{data.totals.avg_score.toFixed(1)}</span>
                  <span className="metric-note">audited calls only</span>
                </div>
                <div className="metric">
                  <span className="metric-label">Not audited</span>
                  <span className="metric-value figure">{num(data.totals.no_transcript)}</span>
                  {/* Never connected is not a bad call, and must not read as one. */}
                  <span className="metric-note">never connected</span>
                </div>
              </div>

              <div className="split-bar">
                <span className="split-seg pass" style={{ width: share(data.totals.pass, data.totals.audited) }}>
                  {data.totals.pass} pass
                </span>
                <span className="split-seg warn" style={{ width: share(data.totals.warn, data.totals.audited) }}>
                  {data.totals.warn} warn
                </span>
                <span className="split-seg fail" style={{ width: share(data.totals.fail, data.totals.audited) }}>
                  {data.totals.fail} fail
                </span>
              </div>
            </Section>

            <Section title="By agent" subtitle="One prompt per language">
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Agent</th>
                      <th scope="col" className="num">Calls</th>
                      <th scope="col" className="num">Audited</th>
                      <th scope="col" className="num">Pass</th>
                      <th scope="col" className="num">Warn</th>
                      <th scope="col" className="num">Fail</th>
                      <th scope="col" className="num">Avg score</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.by_agent.map((a) => (
                      <tr key={a.agent_id}>
                        <th scope="row" style={{ textAlign: "left", fontWeight: 600 }}>
                          {a.agent_id} · {a.language}
                          <div className="metric-note">{a.name}</div>
                        </th>
                        <td className="num">{num(a.calls)}</td>
                        <td className="num">{num(a.audited)}</td>
                        <td className="num">{num(a.pass)}</td>
                        <td className="num">{num(a.warn)}</td>
                        <td className="num">{num(a.fail)}</td>
                        <td className="num">{a.avg_score.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Section>

            <Section
              title="Variable accuracy"
              subtitle="Worst first. Correct + missed + wrong = required in. A wrong value was said out loud to a customer."
              wide
            >
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th scope="col">Variable</th>
                      <th scope="col" className="num">Required in</th>
                      <th scope="col" className="num">Correct</th>
                      <th scope="col" className="num">Missed</th>
                      <th scope="col" className="num">Wrong</th>
                      <th scope="col" className="num">Accuracy</th>
                      <th scope="col"><span className="sr-only">Accuracy bar</span></th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...data.variables]
                      .sort((a, b) => a.accuracy - b.accuracy)
                      .map((v, i) => (
                        <tr key={v.name} className={i < 3 ? "worst" : undefined}>
                          <th scope="row" className="var-name" style={{ textAlign: "left" }}>
                            {v.name}
                          </th>
                          <td className="num">{num(v.required_in)}</td>
                          <td className="num">{num(v.correct)}</td>
                          <td className="num">{num(v.missed)}</td>
                          <td className="num">{num(v.wrong)}</td>
                          <td className="num">{pct(v.accuracy)}</td>
                          <td>
                            <Bar value={v.accuracy} />
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
            </Section>
          </div>
        )}
      </div>
    </>
  );
}
