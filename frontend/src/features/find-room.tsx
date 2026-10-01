"use client";

import { useEffect, useRef, useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/workspace";
import { DateTimeField } from "@/components/date-time-field";
import { Empty, Failure } from "@/components/ui";
import { findAvailableRooms, listAll, scheduleApi } from "@/lib/api";
import type { AvailabilityQuery, AvailableRoom, Facility, RoomType, WorkspaceRead } from "@/lib/api-types";
import { displayTime, interval, toInstant, validateTimezone } from "@/lib/schedule-time";

const message = (error: unknown) => error instanceof Error ? error.message : "Unable to load availability.";
type Metadata = { workspace: WorkspaceRead; types: RoomType[]; facilities: Facility[] };
type Result = { rooms: AvailableRoom[]; query: AvailabilityQuery };

function WorkspaceFindRoom({ workspace }: { workspace: string }) {
  const [metadata, setMetadata] = useState<Metadata | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState("");
  const [searching, setSearching] = useState(false);
  const [result, setResult] = useState<Result | null>(null);
  const [version, setVersion] = useState(0);
  const searchController = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController();
    Promise.all([scheduleApi.workspace(workspace, current.signal), listAll(workspace, "room-types", current.signal), listAll(workspace, "facilities", current.signal)])
      .then(([workspace, types, facilities]) => {
        validateTimezone(workspace.default_timezone);
        if (!current.signal.aborted) setMetadata({ workspace, types, facilities });
      }).catch(error => { if (!current.signal.aborted) setLoadError(message(error)); });
    return () => { current.abort(); searchController.current?.abort(); };
  }, [workspace, version]);
  function retryMetadata() { setLoadError(""); setMetadata(null); setResult(null); setError(""); setVersion(value => value + 1); }
  async function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    searchController.current?.abort();
    setResult(null); setError(""); setSearching(false);
    if (!metadata) return;
    const form = new FormData(event.currentTarget);
    let query: AvailabilityQuery;
    try {
      const minimum_capacity = Number(form.get("minimum_capacity"));
      if (!Number.isInteger(minimum_capacity) || minimum_capacity < 1 || minimum_capacity > 2147483647) throw new Error("Minimum capacity must be a positive integer no greater than 2147483647.");
      const starts_at = toInstant(String(form.get("starts_at") ?? ""), metadata.workspace.default_timezone, String(form.get("starts_occurrence")));
      const ends_at = toInstant(String(form.get("ends_at") ?? ""), metadata.workspace.default_timezone, String(form.get("ends_occurrence")));
      interval(starts_at, ends_at);
      const facility_ids = form.getAll("facility_ids").map(String);
      if (facility_ids.length > 100) throw new Error("Select at most 100 required facilities.");
      query = { starts_at, ends_at, minimum_capacity, facility_ids, ...(form.get("room_type_id") ? { room_type_id: String(form.get("room_type_id")) } : {}) };
    } catch (error) { setError(message(error)); return; }
    const current = new AbortController(); searchController.current = current; setSearching(true);
    try {
      const rooms = await findAvailableRooms(workspace, query, current.signal);
      if (!current.signal.aborted) setResult({ rooms, query });
    } catch (error) { if (!current.signal.aborted) setError(message(error)); }
    finally { if (!current.signal.aborted) setSearching(false); }
  }
  const zone = metadata?.workspace.default_timezone;
  return <div className="find-room-page">
    <div className="page-heading"><div><p className="eyebrow">SPACE AVAILABILITY</p><h1>Find a Room</h1><p>Find an available teaching or meeting space.</p></div></div>
    {loadError ? <Failure message={loadError} retry={retryMetadata} /> : !metadata || !zone ? <p role="status" className="panel">Loading room requirements…</p> : <>
      <section className="panel space-editor schedule-editor"><header className="schedule-editor-header"><h2>Search availability</h2><p className="muted">{metadata.workspace.name} · Times are entered in <strong>{zone}</strong>.</p></header>
        <form onSubmit={search} onChange={() => { setResult(null); setError(""); }}>
          <fieldset disabled={searching}>
            <section className="schedule-time-section" aria-labelledby="find-room-when"><h3 id="find-room-when">When</h3><p className="muted">Enter dates as YYYY-MM-DD. End time is exclusive; back-to-back use is allowed.</p>
              <div className="schedule-time-rows"><DateTimeField label="Start" name="starts_at" defaultValue="" /><DateTimeField label="End" name="ends_at" defaultValue="" /></div>
            </section>
            <fieldset className="schedule-advanced"><legend>Advanced time options</legend><p className="muted">Choose an occurrence only when a local time repeats during a clock change.</p><div className="schedule-advanced-grid">
              {(["starts", "ends"] as const).map(key => <label key={key}>Repeated {key === "starts" ? "start" : "end"} clock time<select name={`${key}_occurrence`} defaultValue="reject"><option value="reject">Ask if a time occurs twice</option><option value="earlier">Earlier occurrence</option><option value="later">Later occurrence</option></select></label>)}
            </div></fieldset>
            <fieldset className="schedule-form-section room-requirements"><legend>Room requirements</legend><div className="schedule-class-grid">
              <label>Minimum capacity *<input name="minimum_capacity" type="number" min={1} max={2147483647} step={1} required defaultValue="1" /></label>
              <label>Room type<select name="room_type_id" defaultValue=""><option value="">Any room type</option>{metadata.types.map(type => <option key={type.id} value={type.id}>{type.name}</option>)}</select></label>
            </div></fieldset>
            <fieldset className="facility-requirements"><legend>Required facilities <span className="muted">(optional)</span></legend><p className="muted">Rooms must contain ALL selected facilities.</p>
              {!metadata.facilities.length ? <p className="muted">No facilities have been configured. You can search without them.</p> : <div className="facility-checklist">{metadata.facilities.map(facility => <label key={facility.id}><input type="checkbox" name="facility_ids" value={facility.id} /><span>{facility.name}</span></label>)}</div>}
            </fieldset>
          </fieldset>
          {error && <p role="alert" className="error-box">{error} Check the requirements and try the search again.</p>}
          <div className="schedule-form-actions"><button disabled={searching}>{searching ? "Searching…" : "Find available rooms"}</button></div>
        </form>
      </section>
      <section className="availability-results" aria-labelledby="available-rooms-title" aria-busy={searching}>
        <h2 id="available-rooms-title">Available rooms</h2>
        {searching ? <p role="status" className="panel">Searching available rooms…</p> : !result ? <Empty>{error ? "No results to display. Correct the error and search again." : "Enter when you need a room and your requirements, then search."}</Empty> : <>
          <p role="status" className="result-count">{result.rooms.length} {result.rooms.length === 1 ? "room available" : "rooms available"}</p>
          <div className="availability-context"><p>{displayTime(result.query.starts_at, zone)} — {displayTime(result.query.ends_at, zone)} · {zone}</p><p>Minimum capacity: {result.query.minimum_capacity} · {metadata.types.find(type => type.id === result.query.room_type_id)?.name ?? "Any room type"}</p><p>Required facilities: {result.query.facility_ids.length ? metadata.facilities.filter(facility => result.query.facility_ids.includes(facility.id)).map(facility => facility.name).join(", ") : "None"}</p><p>Availability is a snapshot, not a booking. Search again to check for changes.</p></div>
          {!result.rooms.length ? <Empty>No rooms match this interval and all requirements. Try another time or adjust your requirements.</Empty> : <div className="available-room-grid">{result.rooms.map(room => <article className="panel available-room-card" key={room.id}>
            <div className="panel-heading"><h3>{room.code} — {room.name}</h3><span className="badge">Capacity {room.capacity}</span></div>
            <p>{room.room_type.name}</p><p className="room-location">{room.campus.name} → {room.building.name} → {room.floor.name}</p>
            <p className="muted">Requested minimum: {result.query.minimum_capacity}</p>
            <h4>Facilities</h4>{room.facilities.length ? <ul className="room-facility-tags">{room.facilities.map(facility => <li key={facility.id}>{facility.name}</li>)}</ul> : <p className="muted">No facilities listed.</p>}
          </article>)}</div>}
        </>}
      </section>
    </>}
  </div>;
}
export default function FindRoom() {
  const { workspace } = useWorkspace();
  return workspace ? <WorkspaceFindRoom key={workspace.id} workspace={workspace.id} /> : <section className="panel"><h1>Find a Room</h1><Empty>Select a workspace above to search for available rooms.</Empty></section>;
}
