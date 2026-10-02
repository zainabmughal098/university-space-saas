"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useWorkspace } from "@/components/workspace";
import { Empty, Failure } from "@/components/ui";
import { Temporal } from "@js-temporal/polyfill";
import { CalendarDatePicker } from "@/components/calendar-date-picker";
import { DateTimeField } from "@/components/date-time-field";
import { APIError, listAll, scheduleApi } from "@/lib/api";
import type { ScheduleEntry, ScheduleInput, WorkspaceRead } from "@/lib/api-types";
import { displayTime, interval, localInput, toInstant, validateTimezone } from "@/lib/schedule-time";
import { label, resources, type Parent, type ScheduleData } from "./schedule-data";

const message = (error: unknown) => error instanceof Error ? error.message : "Unable to complete the request.";
const parents = [["sections", "section_id", "Section"], ["faculty", "faculty_id", "Faculty"], ["rooms", "room_id", "Room"]] as const;

function ScheduleError({ error, data, zone, proposed }: { error: unknown; data: ScheduleData; zone: string; proposed?: Partial<ScheduleInput> }) {
  if (!error) return null;
  const detail = error instanceof APIError ? error.detail : undefined;
  const room = data.rooms.find(row => row.id === proposed?.room_id);
  const section = data.sections.find(row => row.id === proposed?.section_id);
  return <div className="error-box" role="alert"><p>{detail?.code === "insufficient_capacity" ? "The selected room cannot accommodate this section." : message(error)}</p>
    {detail?.code === "insufficient_capacity" && room && section && <p>Section: {section.student_count} students. Room capacity: {room.capacity}.</p>}
    {!!detail?.conflicts?.length && <ul>{detail.conflicts.map(conflict => <li key={conflict.schedule_entry_id}>
      <strong>{conflict.conflict_types.map(type => `${type[0].toUpperCase()}${type.slice(1)} conflict`).join(", ")}</strong>
      <p>{label(data, "sections", conflict.section_id)} · {label(data, "faculty", conflict.faculty_id)} · {label(data, "rooms", conflict.room_id)}</p>
      <p>{displayTime(conflict.starts_at, zone)} — {displayTime(conflict.ends_at, zone)}</p>
    </li>)}</ul>}
    {!!detail?.reservation_conflicts?.length && <ul>{detail.reservation_conflicts.map(conflict => <li key={conflict.reservation_id}><strong>Approved reservation conflict</strong><p>{label(data, "rooms", conflict.room_id)}</p><p>{displayTime(conflict.starts_at, zone)} — {displayTime(conflict.ends_at, zone)}</p></li>)}</ul>}
  </div>;
}

function Editor({ record, data, zone, saving, error, save, cancel }: { record?: ScheduleEntry; data: ScheduleData; zone: string; saving: boolean; error: unknown; save: (body: ScheduleInput) => void; cancel: () => void }) {
  const [selected, setSelected] = useState({ section_id: record?.section_id ?? "", faculty_id: record?.faculty_id ?? "", room_id: record?.room_id ?? "" });
  const [validation, setValidation] = useState("");
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const options = (resource: Parent, key: keyof typeof selected) => data[resource].filter(row => row.is_active || row.id === record?.[key]);
  const missing = parents.filter(([resource, key]) => !options(resource, key).length);
  const room = data.rooms.find(row => row.id === selected.room_id);
  const section = data.sections.find(row => row.id === selected.section_id);
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setValidation("");
    const form = new FormData(event.currentTarget);
    try {
      if (parents.some(([, key]) => !selected[key])) throw new Error("Select a section, faculty member, and room.");
      const starts_at = toInstant(String(form.get("starts_at")), zone, String(form.get("starts_occurrence")), record?.starts_at);
      const ends_at = toInstant(String(form.get("ends_at")), zone, String(form.get("ends_occurrence")), record?.ends_at);
      interval(starts_at, ends_at);
      save({ ...selected, starts_at, ends_at, is_active: form.get("is_active") === "on" });
    } catch (error) { setValidation(message(error)); }
  }
  return <section className="panel space-editor schedule-editor"><header className="schedule-editor-header"><h2 tabIndex={-1} ref={heading}>{record ? "Edit schedule entry" : "Create schedule entry"}</h2>
    <p className="muted">Times are entered in <strong>{zone}</strong>.</p></header>
    {missing.length > 0 && <p className="error">Create or reactivate {missing.map(([, , text]) => text.toLowerCase()).join(", ")} first.</p>}
    <form onSubmit={submit}><fieldset disabled={saving}>
      <fieldset className="schedule-form-section"><legend>Class details</legend><div className="schedule-class-grid">
      {parents.map(([resource, key, text]) => <div className={key === "room_id" ? "schedule-room-field" : undefined} key={key}><label>{text} *<select required name={key} value={selected[key]} onChange={event => setSelected({ ...selected, [key]: event.target.value })}><option value="">Select {text.toLowerCase()}</option>{options(resource, key).map(row => <option key={row.id} value={row.id}>{label(data, resource, row.id)}</option>)}</select></label>{key === "room_id" && selected.room_id && <span className="muted schedule-room-context">{label(data, "rooms", selected.room_id)}</span>}</div>)}
      </div></fieldset>
      <section className="schedule-time-section" aria-labelledby="schedule-time-heading"><h3 id="schedule-time-heading">Date &amp; time</h3><p className="muted">End time is exclusive; back-to-back entries are allowed.</p><div className="schedule-time-rows">
      <DateTimeField label="Start" name="starts_at" defaultValue={record ? localInput(record.starts_at, zone) : ""} calendarToday={Temporal.Now.plainDateISO(zone).toString()} />
      <DateTimeField label="End" name="ends_at" defaultValue={record ? localInput(record.ends_at, zone) : ""} calendarToday={Temporal.Now.plainDateISO(zone).toString()} />
      </div></section>
      <fieldset className="schedule-advanced"><legend>Advanced time options</legend><p className="muted">For repeated local times during a clock change. Otherwise, keep the default.</p><div className="schedule-advanced-grid">
      {(["starts", "ends"] as const).map(key => <label key={key}>Repeated {key === "starts" ? "start" : "end"} clock time<select name={`${key}_occurrence`} defaultValue="reject"><option value="reject">Ask if a time occurs twice</option><option value="earlier">Earlier occurrence</option><option value="later">Later occurrence</option></select></label>)}
      </div></fieldset>
      <label className="schedule-active"><input name="is_active" type="checkbox" defaultChecked={record?.is_active ?? true} />Active</label>
    </fieldset>
    {room && section && room.capacity < section.student_count && <p role="status" className="error">Capacity warning: {section.student_count} students; room capacity {room.capacity}. The backend will validate this entry.</p>}
    {validation && <p role="alert" className="error">{validation}</p>}
    <ScheduleError error={error} data={data} zone={zone} proposed={selected} />
    <div className="schedule-form-actions"><button type="button" className="secondary" disabled={saving} onClick={cancel}>Cancel</button><button disabled={saving || missing.length > 0}>{saving ? "Saving…" : "Save changes"}</button></div>
    </form>
  </section>;
}

function WorkspaceSchedule({ workspace }: { workspace: string }) {
  const [loaded, setLoaded] = useState<{ data: ScheduleData; metadata: WorkspaceRead; now: number } | null>(null);
  const [loadError, setLoadError] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [editor, setEditor] = useState<{ record?: ScheduleEntry } | null>(null);
  const [proposed, setProposed] = useState<Partial<ScheduleInput>>();
  const [filters, setFilters] = useState({ date: "", rooms: "", faculty: "", sections: "", courses: "", status: "all" });
  const [version, setVersion] = useState(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController(); controller.current = current;
    Promise.all([scheduleApi.workspace(workspace, current.signal), Promise.all(resources.map(async key => [key, await listAll(workspace, key, current.signal)] as const))]).then(([metadata, entries]) => {
      validateTimezone(metadata.default_timezone);
      if (!current.signal.aborted) setLoaded({ metadata, data: Object.fromEntries(entries) as ScheduleData, now: Date.now() });
    }).catch(error => { if (!current.signal.aborted) setLoadError(message(error)); });
    return () => current.abort();
  }, [workspace, version]);
  function reload() { setLoaded(null); setLoadError(""); setVersion(value => value + 1); }
  async function mutate(action: (signal: AbortSignal) => Promise<unknown>, body?: Partial<ScheduleInput>) {
    const signal = controller.current!.signal; setSaving(true); setError(null); setNotice(""); setProposed(body);
    try { await action(signal); if (!signal.aborted) { setEditor(null); setNotice("Schedule updated successfully."); reload(); } }
    catch (error) { if (!signal.aborted) setError(error); }
    finally { if (!signal.aborted) setSaving(false); }
  }
  const data = loaded?.data, zone = loaded?.metadata.default_timezone;
  const rows = data && zone ? data["schedule-entries"].filter(row =>
    (!filters.date || localInput(row.starts_at, zone).slice(0, 10) === filters.date) &&
    (!filters.rooms || row.room_id === filters.rooms) && (!filters.faculty || row.faculty_id === filters.faculty) &&
    (!filters.sections || row.section_id === filters.sections) && (!filters.courses || data.sections.find(section => section.id === row.section_id)?.course_id === filters.courses) &&
    (filters.status === "all" || row.is_active === (filters.status === "active"))
  ).sort((a, b) => Date.parse(a.starts_at) - Date.parse(b.starts_at) || a.id.localeCompare(b.id)) : [];
  return <>
    <div className="page-heading"><div><p className="eyebrow">OFFICIAL CLASSES</p><h1>Schedule</h1><p>{loaded ? `${loaded.metadata.name} · All times in ${zone}` : "Manage your university’s teaching schedule."}</p></div><button className="secondary" disabled={saving || !!editor} onClick={reload}>Refresh data</button></div>
    {notice && <p role="status" className="success">{notice}</p>}
    {loadError ? <Failure message={loadError} retry={reload} /> : !loaded || !data || !zone ? <p role="status">Loading schedule…</p> : <>
      <div className="spaces-summary"><div><strong>{data["schedule-entries"].length}</strong><span>Total entries</span></div><div><strong>{data["schedule-entries"].filter(row => row.is_active).length}</strong><span>Active entries</span></div><div><strong>{data["schedule-entries"].filter(row => row.is_active && Date.parse(row.starts_at) >= loaded.now).length}</strong><span>Upcoming active entries</span></div></div>
      {editor ? <Editor key={editor.record?.id ?? "new"} record={editor.record} data={data} zone={zone} saving={saving} error={error} cancel={() => { setEditor(null); setError(null); }} save={body => void mutate(signal => editor.record ? scheduleApi.update(workspace, editor.record.id, body, signal) : scheduleApi.create(workspace, body, signal), body)} /> : <section className="panel">
        <div className="panel-heading"><h2>Chronological schedule</h2><button disabled={saving} onClick={() => { setEditor({}); setError(null); }}>Create new</button></div>
        <div className="space-fields"><CalendarDatePicker label={`Start date (${zone})`} value={filters.date} onChange={date => setFilters({ ...filters, date })} today={Temporal.Now.plainDateISO(zone).toString()} clearable />
          {(["rooms", "faculty", "sections", "courses"] as const).map(key => <label key={key}>Filter {key}<select value={filters[key]} onChange={event => setFilters({ ...filters, [key]: event.target.value })}><option value="">All {key}</option>{data[key].map(row => <option key={row.id} value={row.id}>{label(data, key, row.id)}</option>)}</select></label>)}
          <label>Status<select value={filters.status} onChange={event => setFilters({ ...filters, status: event.target.value })}><option value="all">All statuses</option><option value="active">Active</option><option value="inactive">Inactive</option></select></label>
        </div><button className="secondary" onClick={() => setFilters({ date: "", rooms: "", faculty: "", sections: "", courses: "", status: "all" })}>Clear filters</button>
        <ScheduleError error={error} data={data} zone={zone} proposed={proposed} />
        {!rows.length ? <Empty>{data["schedule-entries"].length ? "No entries match these filters." : "No schedule entries yet."}</Empty> : <div className="table-scroll" role="region" aria-label="Schedule entries" tabIndex={0}><table className="spaces-table"><thead><tr><th scope="col">Class / faculty</th><th scope="col">Room / location</th><th scope="col">Interval ({zone})</th><th scope="col">Status / actions</th></tr></thead><tbody>{rows.map(row => <tr key={row.id}>
          <td><strong>{label(data, "sections", row.section_id)}</strong><p>{label(data, "faculty", row.faculty_id)}</p></td><td>{label(data, "rooms", row.room_id)}</td><td><time dateTime={row.starts_at}>{displayTime(row.starts_at, zone)}</time><p>to <time dateTime={row.ends_at}>{displayTime(row.ends_at, zone)}</time></p></td>
          <td><span className="badge">{row.is_active ? "Active" : "Inactive"}</span><div className="space-actions"><button className="secondary" disabled={saving} onClick={() => { setEditor({ record: row }); setError(null); }}>Edit</button><button className="secondary" disabled={saving} onClick={() => void mutate(signal => row.is_active ? scheduleApi.deactivate(workspace, row.id, signal) : scheduleApi.update(workspace, row.id, { is_active: true }, signal), row)}>{row.is_active ? "Deactivate" : "Reactivate"}</button></div></td>
        </tr>)}</tbody></table></div>}
      </section>}
    </>}
  </>;
}
export default function Schedule() {
  const { workspace } = useWorkspace();
  return workspace ? <WorkspaceSchedule key={workspace.id} workspace={workspace.id} /> : <section className="panel"><h1>Schedule</h1><Empty>Select a workspace above to manage its schedule.</Empty></section>;
}
