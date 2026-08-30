import { useEffect, useState } from "react";
import { LayoutDashboard, ListChecks, Menu } from "lucide-react";
import { MOCK_EVENT, isMocking, useResource } from "./api/client";
import type { Health } from "./api/types";
import { href, useRoute, type Route } from "./route";
import { CallDetailPage } from "./pages/CallDetail";
import { CallListPage } from "./pages/CallList";
import { OverviewPage } from "./pages/Overview";

const NAV: Array<{ route: Route; label: string; icon: typeof LayoutDashboard }> = [
  { route: { name: "overview" }, label: "Overview", icon: LayoutDashboard },
  { route: { name: "calls" }, label: "Calls", icon: ListChecks },
];

export default function App() {
  const route = useRoute();
  const [navOpen, setNavOpen] = useState(false);
  const [mock, setMock] = useState(isMocking);
  const health = useResource<Health>("/health");

  useEffect(() => {
    const on = () => setMock(true);
    window.addEventListener(MOCK_EVENT, on);
    return () => window.removeEventListener(MOCK_EVENT, on);
  }, []);

  useEffect(() => setNavOpen(false), [route]);

  const active = route.name === "overview" ? "overview" : "calls";

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
            <span>Audit date {health.data?.audit_date ?? "—"}</span>
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
            <span className="sync-pill">
              <span className={`sync-dot${mock ? " stale" : ""}`} aria-hidden />
              {mock ? "Fixtures" : `${health.data?.calls_audited ?? 0} calls audited`}
            </span>
          </div>
        </header>

        <main id="content" tabIndex={-1}>
          {route.name === "overview" ? <OverviewPage /> : null}
          {route.name === "calls" ? <CallListPage /> : null}
          {route.name === "call" ? <CallDetailPage id={route.id} /> : null}
        </main>
      </div>
    </div>
  );
}
