import type { ReactNode } from "react";
import { NavLink } from "react-router-dom";

const navItems = [
  { to: "/", label: "Home", end: true },
  { to: "/onboarding", label: "Onboarding" },
  { to: "/scan", label: "Scan" },
  { to: "/search", label: "Search" },
  { to: "/files/sample-file", label: "File Detail" },
  { to: "/settings", label: "Settings" },
  { to: "/audit", label: "Audit" },
];

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="app-shell">
      <aside className="sidebar" aria-label="Primary">
        <div className="brand">
          <span className="brand-mark">DG</span>
          <div>
            <p className="brand-name">DocGraph V4</p>
            <p className="brand-mode">Local</p>
          </div>
        </div>
        <nav className="nav-list">
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              end={item.end}
              to={item.to}
              className={({ isActive }) => (isActive ? "nav-link active" : "nav-link")}
            >
              {item.label}
            </NavLink>
          ))}
        </nav>
      </aside>
      <div className="content-shell">
        <header className="topbar">
          <div>
            <p className="eyebrow">Local-first workspace</p>
            <h1>DocGraph</h1>
          </div>
          <span className="privacy-pill">Local mode</span>
        </header>
        <main className="page-shell">{children}</main>
      </div>
    </div>
  );
}

