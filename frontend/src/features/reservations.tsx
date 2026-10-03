"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { Temporal } from "@js-temporal/polyfill";
import { useWorkspace } from "@/components/workspace";
import { Empty, Failure } from "@/components/ui";
import { CalendarDatePicker } from "@/components/calendar-date-picker";
import { APIError, listWorkspaceMembers, listAll, reservationApi, scheduleApi } from "@/lib/api";
import type { Building, Campus, Floor, Reservation, ReservationInput, Room, WorkspaceRead, WorkspaceMember } from "@/lib/api-types";
import { interval, localInput, toInstant, validateTimezone } from "@/lib/schedule-time";
import { DevelopmentMemberSelect } from "@/components/development-member-select";
import { clearReservationPrefill, readReservationPrefill, type ReservationPrefill } from "@/lib/reservation-prefill";
import { ReservationFields } from "./reservation-form";

const statuses = ["pending", "approved", "rejected", "cancelled"] as const;
const titleCase = (value: string) => value[0].toUpperCase() + value.slice(1);
type Data = { members: WorkspaceMember[]; workspace: WorkspaceRead; reservations: Reservation[]; rooms: Room[]; floors: Floor[]; buildings: Building[]; campuses: Campus[] };
type Panel = { kind: "create"; prefill?: ReservationPrefill } | { kind: "view" | "approve" | "reject" | "cancel"; record: Reservation };
const time = (value: string, zone: string) => new Intl.DateTimeFormat("en", { timeZone: zone, year: "numeric", month: "short", day: "numeric", hour: "numeric", minute: "2-digit", hour12: true, timeZoneName: "short" }).format(new Date(value));
const failure = (error: unknown) => error instanceof Error ? error.message : "Unable to complete the request.";

function WorkspaceReservations({ workspace, prefillSearch }: { workspace: string; prefillSearch: string }) {
  const [data, setData] = useState<Data | null>(null), [loading, setLoading] = useState(true), [loadError, setLoadError] = useState("");
  const [version, setVersion] = useState(0), [panel, setPanel] = useState<Panel | null>(null);
  const [error, setError] = useState<unknown>(null), [success, setSuccess] = useState(""), [busy, setBusy] = useState(false);
  const [status, setStatus] = useState(""), [roomFilter, setRoomFilter] = useState(""), [dateFilter, setDateFilter] = useState("");
  const prefillHandled = useRef(false);
  const [prefillNotice, setPrefillNotice] = useState("");
  const mutation = useRef<AbortController | null>(null), pending = useRef(false);
  const createButton = useRef<HTMLButtonElement>(null), panelRef = useRef<HTMLElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    Promise.all([listWorkspaceMembers(workspace, controller.signal), scheduleApi.workspace(workspace, controller.signal), listAll(workspace, "reservations", controller.signal), listAll(workspace, "rooms", controller.signal), listAll(workspace, "floors", controller.signal), listAll(workspace, "buildings", controller.signal), listAll(workspace, "campuses", controller.signal)])
      .then(([members, workspace, reservations, rooms, floors, buildings, campuses]) => {
        validateTimezone(workspace.default_timezone);
        if (!controller.signal.aborted) { setData({ members, workspace, reservations, rooms, floors, buildings, campuses }); setLoading(false);
          if (!prefillHandled.current) {
            prefillHandled.current = true;
            // Read the current URL so a consumed context cannot return on workspace switches.
            const incoming = readReservationPrefill(prefillSearch ? window.location.search : "", workspace.id, workspace.default_timezone, rooms);
            if (incoming.present) {
              setPanel({ kind: "create", prefill: incoming.value });
              if (!incoming.value) {
                clearReservationPrefill();
                setPrefillNotice("The availability selection could not be applied. Please choose a room and times for this workspace.");
              }
            }
          }
        }
      }).catch(error => { if (!controller.signal.aborted) { setLoadError(failure(error)); setLoading(false); } });
    return () => controller.abort();
  }, [workspace, version, prefillSearch]);
  useEffect(() => () => mutation.current?.abort(), []);
  useEffect(() => { if (panel) panelRef.current?.focus(); else createButton.current?.focus(); }, [panel]);
  function refresh() { clearReservationPrefill(); setPrefillNotice(""); setLoadError(""); setLoading(true); setPanel(null); setError(null); setSuccess(""); setVersion(value => value + 1); }
  function open(next: Panel) { clearReservationPrefill(); setPrefillNotice(""); setPanel(next); setError(null); setSuccess(""); }
  function close() { clearReservationPrefill(); setPrefillNotice(""); setPanel(null); setError(null); createButton.current?.focus(); }
  function roomLabel(id: string) {
    const room = data?.rooms.find(row => row.id === id), floor = data?.floors.find(row => row.id === room?.floor_id);
    const building = data?.buildings.find(row => row.id === floor?.building_id), campus = data?.campuses.find(row => row.id === building?.campus_id);
    return room ? `${room.code} — ${room.name} · Capacity ${room.capacity} · ${[campus?.name, building?.name, floor?.name].filter(Boolean).join(" / ")}${room.is_active ? "" : " (inactive)"}` : "Room unavailable";
  }
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); if (!data || !panel || panel.kind === "view" || pending.current) return;
    const form = new FormData(event.currentTarget); setError(null); setSuccess("");
    let body: ReservationInput | undefined, reviewer = "";
    try {
      if (panel.kind === "create") {
        const requested_by_user_id = String(form.get("requested_by_user_id") ?? "").trim();
        if (!data.members.some(member => member.user_id === requested_by_user_id && member.is_active)) throw new Error("Select an active workspace member as the development requester.");
        const room_id = String(form.get("room_id") ?? ""), title = String(form.get("title") ?? "").trim();
        if (!title || title.length > 255) throw new Error("Title is required and must be at most 255 characters.");
        if (!data.rooms.some(room => room.id === room_id && room.is_active)) throw new Error("Choose an active room.");
        const expected_attendees = Number(form.get("expected_attendees"));
        if (!Number.isInteger(expected_attendees) || expected_attendees < 1 || expected_attendees > 2147483647) throw new Error("Expected attendees must be a positive integer no greater than 2147483647.");
        const starts_at = toInstant(String(form.get("starts_at") ?? ""), data.workspace.default_timezone, String(form.get("starts_occurrence")), panel.prefill?.starts_at);
        const ends_at = toInstant(String(form.get("ends_at") ?? ""), data.workspace.default_timezone, String(form.get("ends_occurrence")), panel.prefill?.ends_at);
        interval(starts_at, ends_at);
        body = { room_id, title, requested_by_user_id, expected_attendees, starts_at, ends_at, description: String(form.get("description") ?? "").trim() || null };
      } else if (panel.kind !== "cancel") {
        reviewer = String(form.get("reviewed_by_user_id") ?? "").trim();
        if (!data.members.some(member => member.user_id === reviewer && member.is_active)) throw new Error("Select an active workspace member as the development reviewer.");
      }
    } catch (error) { setError(error); return; }
    const controller = new AbortController(); mutation.current = controller; pending.current = true; setBusy(true);
    try {
      const record = panel.kind === "create" ? await reservationApi.create(workspace, body!, controller.signal)
        : panel.kind === "cancel" ? await reservationApi.cancel(workspace, panel.record.id, controller.signal)
        : panel.kind === "approve" ? await reservationApi.approve(workspace, panel.record.id, { reviewed_by_user_id: reviewer }, controller.signal)
        : await reservationApi.reject(workspace, panel.record.id, { reviewed_by_user_id: reviewer, rejection_reason: String(form.get("rejection_reason") ?? "").trim() || null }, controller.signal);
      if (!controller.signal.aborted) {
        setData(previous => previous && ({ ...previous, reservations: [...previous.reservations.filter(row => row.id !== record.id), record] }));
        setSuccess(`Reservation ${record.status === "pending" ? "request created" : record.status}.`); close();
      }
    } catch (error) { if (!controller.signal.aborted) setError(error); }
    finally { if (!controller.signal.aborted) { setBusy(false); pending.current = false; } }
  }
  if (!data || loading || loadError) return <><h1>Reservations</h1>{loadError ? <Failure message={loadError} retry={refresh} /> : <p role="status" className="panel">Loading reservations…</p>}</>;
  const hasMembers = data.members.some(member => member.is_active);
  const memberLabel = (id: string | null) => { const member = data.members.find(row => row.user_id === id); return member ? `${member.display_name} — ${member.email}${member.is_active ? "" : " (inactive)"}` : id ? "Member unavailable" : "Not reviewed"; };
  const zone = data.workspace.default_timezone, today = Temporal.Now.plainDateISO(zone).toString();
  const visible = data.reservations.filter(row => (!status || row.status === status) && (!roomFilter || row.room_id === roomFilter) && (!dateFilter || localInput(row.starts_at, zone).slice(0, 10) === dateFilter)).sort((a, b) => Temporal.Instant.compare(a.starts_at, b.starts_at));
  const detail = error instanceof APIError ? error.detail : null;
  return <div className="reservations-page">
    <div className="page-heading"><div><p className="eyebrow">ROOM REQUESTS</p><h1>Reservations</h1><p>Manage room requests for {data.workspace.name}. Times shown in <strong>{zone}</strong>.</p></div><button type="button" className="secondary" disabled={busy} onClick={refresh}>Refresh data</button></div>
    <div className="spaces-summary" aria-label="Reservation summary">{["total", ...statuses].map(value => <div key={value}><strong>{value === "total" ? data.reservations.length : data.reservations.filter(row => row.status === value).length}</strong><span>{titleCase(value)}</span></div>)}</div>
    <p className="muted reservation-identity-note">Development identity selector — not authenticated.</p>
    {!hasMembers && <p role="status" className="panel">No active workspace members are available. A development member is required before reservations can be created or reviewed.</p>}
    {success && <p role="status" className="success">{success}</p>}
    <section className="panel reservation-filters" aria-label="Reservation filters"><label>Status<select value={status} onChange={event => setStatus(event.target.value)}><option value="">All statuses</option>{statuses.map(value => <option key={value} value={value}>{titleCase(value)}</option>)}</select></label><label>Room<select value={roomFilter} onChange={event => setRoomFilter(event.target.value)}><option value="">All rooms</option>{data.rooms.map(room => <option key={room.id} value={room.id}>{roomLabel(room.id)}</option>)}</select></label><CalendarDatePicker label="Start date filter" value={dateFilter} onChange={setDateFilter} today={today} clearable /><button type="button" className="secondary" onClick={() => { setStatus(""); setRoomFilter(""); setDateFilter(""); }}>Clear filters</button><button type="button" ref={createButton} disabled={busy || !hasMembers || !data.rooms.some(room => room.is_active)} onClick={() => open({ kind: "create" })}>Create reservation</button></section>
    {!data.rooms.some(room => room.is_active) && <p className="muted">Create an active room in Spaces before requesting a reservation.</p>}
    {panel && <section key={panel.kind === "create" ? "create" : `${panel.kind}-${panel.record.id}`} className="panel space-editor schedule-editor reservation-editor" aria-label="Reservation panel" tabIndex={-1} ref={panelRef}>
      <header className="schedule-editor-header">{prefillNotice && <p role="status">{prefillNotice}</p>}{panel.kind === "create" && panel.prefill && <p className="muted">Room selected from availability search. Availability is a snapshot, not a booking; the server validates your request.</p>}<h2>{panel.kind === "create" ? "Create reservation" : panel.kind === "view" ? panel.record.title : `${titleCase(panel.kind)} reservation`}</h2><p className="muted">Times are entered and displayed in {zone}.</p></header>
      {panel.kind === "view" ? <><dl className="reservation-details">{Object.entries({ Room: roomLabel(panel.record.room_id), Start: time(panel.record.starts_at, zone), "End (exclusive)": time(panel.record.ends_at, zone), Status: titleCase(panel.record.status), "Expected attendees": panel.record.expected_attendees, Description: panel.record.description || "No description", "Requester": memberLabel(panel.record.requested_by_user_id), "Reviewer": memberLabel(panel.record.reviewed_by_user_id), "Review / rejection information": panel.record.rejection_reason || "No reason recorded", Created: time(panel.record.created_at, zone), Updated: time(panel.record.updated_at, zone), Reviewed: panel.record.reviewed_at ? time(panel.record.reviewed_at, zone) : "Not reviewed" }).map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{value}</dd></div>)}</dl><button type="button" className="secondary" onClick={close}>Close details</button></> : <form onSubmit={submit}>
        <fieldset disabled={busy}>
          {panel.kind === "create" ? <ReservationFields prefill={panel.prefill} zone={zone} members={data.members} rooms={data.rooms} roomLabel={roomLabel} today={today} /> : <div className="reservation-confirmation"><p>{panel.kind === "cancel" ? "Cancel this reservation? This action cannot be undone." : panel.kind === "reject" ? "Reject this pending request? This action cannot be undone." : "Approve this request? The backend will recheck room occupancy and capacity."}</p><p><strong>{panel.record.title}</strong> · {roomLabel(panel.record.room_id)}</p><p>{time(panel.record.starts_at, zone)} — {time(panel.record.ends_at, zone)}</p>{panel.kind !== "cancel" && <DevelopmentMemberSelect label="Development reviewer" name="reviewed_by_user_id" members={data.members} />}{panel.kind === "reject" && <label>Rejection reason (optional)<textarea name="rejection_reason" rows={3} /></label>}</div>}
        </fieldset>
        {error != null && <div role="alert" className="error-box"><p>{failure(error)}</p>{detail && <ul>{detail.conflicts?.map(row => <li key={row.schedule_entry_id}>Scheduled class · {roomLabel(row.room_id)} · {time(row.starts_at, zone)} — {time(row.ends_at, zone)}</li>)}{detail.reservation_conflicts?.map(row => <li key={row.reservation_id}>Approved reservation · {roomLabel(row.room_id)} · {time(row.starts_at, zone)} — {time(row.ends_at, zone)}</li>)}</ul>}<p>For an uncertain network outcome, refresh data before retrying.</p></div>}
        <div className="schedule-form-actions"><button type="button" className="secondary" disabled={busy} onClick={close}>{panel.kind === "create" && panel.prefill ? "Cancel" : "Back"}</button><button disabled={busy || (panel.kind !== "cancel" && !hasMembers)}>{busy ? "Saving…" : panel.kind === "create" ? "Create request" : `Confirm ${panel.kind}`}</button></div>
      </form>}
    </section>}
    <section className="panel" aria-label="Reservations list"><div className="panel-heading"><h2>Room reservations</h2><span>{visible.length} shown</span></div><p className="muted">Filters apply to all loaded reservations. Date filters use the start date in {zone}.</p>
      {!visible.length ? <Empty>{data.reservations.length ? "No reservations match these filters." : "No reservations yet. Create a request to get started."}</Empty> : <div className="table-scroll"><table className="spaces-table"><thead><tr><th>Room / request</th><th>Date &amp; time</th><th>Requester</th><th>Status</th><th>Actions</th></tr></thead><tbody>{visible.map(row => <tr key={row.id}><td><strong>{row.title}</strong><small>{roomLabel(row.room_id)}</small></td><td>{time(row.starts_at, zone)}<small>to {time(row.ends_at, zone)}</small></td><td>{memberLabel(row.requested_by_user_id)}</td><td><span className={`badge reservation-status status-${row.status}`}>{titleCase(row.status)}</span></td><td><div className="reservation-actions"><button type="button" className="secondary" disabled={busy} onClick={() => open({ kind: "view", record: row })}>View</button>{row.status === "pending" && <><button type="button" disabled={busy || !hasMembers} onClick={() => open({ kind: "approve", record: row })}>Approve</button><button type="button" className="secondary" disabled={busy || !hasMembers} onClick={() => open({ kind: "reject", record: row })}>Reject</button></>}{(row.status === "pending" || row.status === "approved") && <button type="button" className="secondary" disabled={busy} onClick={() => open({ kind: "cancel", record: row })}>Cancel</button>}</div></td></tr>)}</tbody></table></div>}
    </section>
  </div>;
}

export default function Reservations({ prefillSearch = "" }: { prefillSearch?: string }) {
  const { workspace } = useWorkspace();
  const previousWorkspace = useRef(workspace?.id);
  useEffect(() => {
    if (previousWorkspace.current && previousWorkspace.current !== workspace?.id) clearReservationPrefill();
    previousWorkspace.current = workspace?.id;
  }, [workspace?.id]);
  return workspace ? <WorkspaceReservations key={`${workspace.id}:${prefillSearch}`} workspace={workspace.id} prefillSearch={prefillSearch} /> : <section className="panel"><h1>Reservations</h1><Empty>Select a workspace above to manage reservations.</Empty></section>;
}
