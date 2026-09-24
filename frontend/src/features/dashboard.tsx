"use client";
import { useEffect, useState } from "react";
import { listAll } from "@/lib/api";
import type { Resources } from "@/lib/api-types";
import { useWorkspace } from "@/components/workspace";
import { Empty, Failure } from "@/components/ui";
function useRecords<K extends keyof Resources>(workspace: string, resource: K) {
  const [state, setState] = useState<{ data?: Resources[K][]; error?: string }>({});
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    listAll(workspace, resource, controller.signal).then(data => {
      if (!controller.signal.aborted) setState({ data });
    }).catch(error => {
      if (!controller.signal.aborted) setState({ error: error instanceof Error ? error.message : "Unable to load data." });
    });
    return () => controller.abort();
  }, [workspace, resource, attempt]);
  return { ...state, retry: () => { setState({}); setAttempt(value => value + 1); } };
}
function Metric({ workspace, resource, label, active = false }: { workspace: string; resource: keyof Resources; label: string; active?: boolean }) {
  const { data, error, retry } = useRecords(workspace, resource);
  const count = data?.filter(row => !active || ("is_active" in row && row.is_active)).length;
  return <article className="metric"><h3>{label}</h3>{error ? <Failure message={error} retry={retry} /> : <><strong aria-live="polite">{count === undefined ? "…" : count.toLocaleString()}</strong><p>{count === undefined ? "Loading records…" : count === 0 ? "No records yet" : active ? "Currently active" : "Across this workspace"}</p></>}</article>;
}
const formatTime = (value: string) => new Intl.DateTimeFormat("en", { timeZone: "UTC", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date(value));
function Activity({ workspace, kind }: { workspace: string; kind: "schedule-entries" | "reservations" }) {
  const { data, error, retry } = useRecords(workspace, kind);
  const [now] = useState(() => Date.now());
  const rows = data && (kind === "schedule-entries" ? data.filter(row => "is_active" in row && row.is_active && Date.parse(row.starts_at) >= now).sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at)) : [...data].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))).slice(0, 5);
  return <section className="panel"><div className="panel-heading"><h2>{kind === "schedule-entries" ? "Upcoming classes" : "Recent reservations"}</h2><span className="badge">Up to 5</span></div>
    <p className="muted">{kind === "schedule-entries" ? "Active entries starting after this view was opened." : "Latest requests, including pending approvals."} Times in UTC.</p>
    {error ? <Failure message={error} retry={retry} /> : !rows ? <p role="status" className="empty">Loading activity…</p> : !rows.length ? <Empty>{kind === "schedule-entries" ? "No upcoming classes." : "No reservations yet."}</Empty> : <ul className="activity-list">{rows.map(row => <li key={row.id}><div><strong>{"title" in row ? row.title : `Section ${row.section_id}`}</strong><p>Room {row.room_id}</p><time dateTime={row.starts_at}>{formatTime(row.starts_at)} — {formatTime(row.ends_at)} UTC</time></div>{"status" in row && <span className={`badge ${row.status}`}>{row.status}</span>}</li>)}</ul>}
  </section>;
}
function WorkspaceDashboard({ id }: { id: string }) {
  return <><div className="metrics">{([ ["campuses", "Total campuses"], ["buildings", "Total buildings"], ["rooms", "Total rooms"], ["rooms", "Active rooms"], ["departments", "Departments"], ["faculty", "Faculty"], ["courses", "Courses"], ["sections", "Sections"] ] as const).map(([resource, label]) => <Metric key={label} workspace={id} resource={resource} label={label} active={label === "Active rooms"} />)}</div><div className="activity-grid"><Activity workspace={id} kind="schedule-entries" /><Activity workspace={id} kind="reservations" /></div></>;
}
export default function Dashboard() {
  const { workspace } = useWorkspace();
  const [refresh, setRefresh] = useState(0);
  return <><div className="page-heading"><div><p className="eyebrow">UNIVERSITY OVERVIEW</p><h1>Your campus, at a glance.</h1><p>Spaces, academics, and room activity in one place.</p></div>{workspace && <button className="secondary" onClick={() => setRefresh(value => value + 1)}>Refresh data</button>}</div>{workspace ? <WorkspaceDashboard key={`${workspace.id}:${refresh}`} id={workspace.id} /> : <section className="panel"><Empty>Select a workspace above to load your university’s dashboard.</Empty></section>}</>;
}
