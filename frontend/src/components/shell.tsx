"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { WorkspaceProvider, WorkspaceSelector, useWorkspace } from "./workspace";
const navigation = [["dashboard", "Dashboard", "01"], ["spaces", "Spaces", "02"], ["academic", "Academic", "03"], ["schedule", "Schedule", "04"], ["find-room", "Find a Room", "05"], ["reservations", "Reservations", "06"]];
function Layout({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const { workspace } = useWorkspace();
  const title = navigation.find(([route]) => path === `/${route}`)?.[1] ?? "University Space";
  return <div className="shell">
    <a className="skip-link" href="#main">Skip to content</a>
    <aside className="sidebar">
      <Link className="brand" href="/dashboard"><span className="brand-mark">U</span><span>University Space<small>Campus operations</small></span></Link>
      <p className="nav-label">WORKSPACE</p>
      <nav aria-label="Main navigation">{navigation.map(([route, label, number]) => <Link key={route} href={`/${route}`} aria-current={path === `/${route}` ? "page" : undefined}><span aria-hidden="true">{number}</span>{label}</Link>)}</nav>
      <div className="sidebar-note"><span className="status-dot" />Development environment<p>Authentication is pending.</p></div>
    </aside>
    <div className="main-column">
      <header className="topbar"><div><span className="eyebrow">{workspace?.name ?? "No workspace selected"}</span><strong>{title}</strong></div><span className="account">DEV <span>Unauthenticated session</span></span></header>
      <main id="main"><WorkspaceSelector />{children}</main>
      <footer>University Space <span>Workspace operations · Phase 4A</span></footer>
    </div>
  </div>;
}
export function Shell({ children }: { children: React.ReactNode }) { return <WorkspaceProvider><Layout>{children}</Layout></WorkspaceProvider>; }
