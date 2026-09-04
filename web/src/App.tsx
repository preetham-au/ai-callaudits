import { useEffect, useState } from "react";
import { ClipboardCheck, LayoutDashboard, ListChecks, Menu, PlayCircle } from "lucide-react";
import { MOCK_EVENT, isMocking, useResource } from "./api/client";
import type { AuditDay, Health } from "./api/types";
import { todayIst } from "./components/common";
import { EMPTY_SCOPE, ScopeFilters, type Scope } from "./components/scope";
import { href, useRoute, type Route } from "./route";
import { CallDetailPage } from "./pages/CallDetail";
import { CallListPage } from "./pages/CallList";
import { ManualAuditPage } from "./pages/ManualAudit";
import { OverviewPage } from "./pages/Overview";
import { RunsPage } from "./pages/Runs";

const NAV: Array<{ route: Route; label: string; icon: typeof LayoutDashboard }> = [
  { route: { name: "overview" }, label: "Overview", icon: LayoutDashboard },
  { route: { name: "calls" }, label: "Calls", icon: ListChecks },
  { route: { name: "manual" }, label: "Manual audits", icon: ClipboardCheck },
  { route: { name: "runs" }, label: "Runs", icon: PlayCircle },
];

export default function App() {
  const route = useRoute();
  const [navOpen, setNavOpen] = useState(false);
  const [mock, setMock] = useState(isMocking);
  const health = useResource<Health>("/health");
  const dates = useResource<AuditDay[]>("/dates");

  /*
   * The day Overview and Calls are both reading. Held here rather than per page
   * so switching between the two does not silently jump back to the newest day
   * mid-investigation. Empty until /health answers; the pages fetch nothing
   * until then, which is what stops them loading the latest day and immediately
   * re-loading the chosen one.
   */
  const [picked, setPicked] = useState("");
  // Same reasoning as the date: the scope belongs to the investigation, not to
  // one page. Overview and Calls read it, and the CSV link is built from it, so
  // the figure on screen and the row count in the download are the same query.
  const [scope, setScope] = useState<Scope>(EMPTY_SCOPE);
  const date = picked || health.data?.audit_date || "";
  const days = dates.data ?? [];
  const dated = route.name === "overview" || route.name === "calls";

  useEffect(() => {
    const on = () => setMock(true);
    window.addEventListener(MOCK_EVENT, on);
    return () => window.removeEventListener(MOCK_EVENT, on);
  }, []);

  useEffect(() => setNavOpen(false), [route]);

  // A call detail is still "Calls" as far as the rail is concerned.
  const active = route.name === "call" ? "calls" : route.name;

  return (
    <div className="app-shell">
      <a className="skip-link" href="#content">
        Skip to content
      </a>

      <nav className={`nav ${navOpen ? "open" : ""}`} aria-label="Main">
        <div className="brand">
          <span className="brand-title">call audits</span>
          <span className="brand-sub">Chola renewals</span>
        </div>

        <div className="nav-group">
          <span className="nav-group-label">General</span>
          {NAV.map((item) => (
            <a
              key={item.label}
              className={`nav-item${active === item.route.name ? " active" : ""}`}
              aria-current={active === item.route.name ? "page" : undefined}
              href={href(item.route)}
            >
              <item.icon size={16} aria-hidden />
              {item.label}
            </a>
          ))}
        </div>

        <div className="nav-group nav-foot">
          <div className="nav-meta">
            {/* "Latest", not "Audit date": the topbar picker owns that phrase
                now, and two labels reading differently would look like a bug. */}
            <span>Latest audit {health.data?.audit_date ?? "—"}</span>
            <span>Judge {health.data?.model ?? "—"}</span>
          </div>
        </div>
      </nav>

      <div className="main">
        {mock ? (
          <div className="mock-banner" role="status">
            Mock data — the audit API is not reachable. Nothing on screen is a real audit.
          </div>
        ) : null}

        <header className="topbar">
          <button
            type="button"
            className="btn btn-icon btn-ghost nav-toggle"
            aria-label="Open navigation"
            aria-expanded={navOpen}
            onClick={() => setNavOpen((v) => !v)}
          >
            <Menu size={18} aria-hidden />
          </button>
          <div className="topbar-actions">
            {dated ? (
              <label className="topbar-date">
                <span>Audit date</span>
                {/* Native date input: no picker dependency, it knows the
                    operator's locale format, and unlike a dropdown of audited
                    days it can select a day that was never audited — which is
                    exactly the gap worth seeing. */}
                {/* Bounded by the oldest audit and today, NOT by the newest
                    audit: the days between the last run and now are exactly the
                    ones worth being able to select, because that is where a
                    missed nightly run hides. */}
                <input
                  className="text-input"
                  type="date"
                  value={date}
                  min={days.length ? days[days.length - 1].date : undefined}
                  max={todayIst()}
                  onChange={(e) => setPicked(e.target.value)}
                />
              </label>
            ) : null}
            {dated ? <ScopeFilters value={scope} onChange={setScope} /> : null}
            <span className="sync-pill">
              <span className={`sync-dot${mock ? " stale" : ""}`} aria-hidden />
              {mock ? "Fixtures" : `${health.data?.calls_audited ?? 0} calls audited`}
            </span>
          </div>
        </header>

        <main id="content" tabIndex={-1}>
          {route.name === "overview" ? <OverviewPage date={date} scope={scope} /> : null}
          {route.name === "calls" ? (
            <CallListPage
              date={date}
              scope={scope}
              variable={route.variable}
              variableVerdict={route.variableVerdict}
            />
          ) : null}
          {route.name === "call" ? <CallDetailPage id={route.id} /> : null}
          {route.name === "manual" ? <ManualAuditPage /> : null}
          {route.name === "runs" ? <RunsPage /> : null}
        </main>
      </div>
    </div>
  );
}
