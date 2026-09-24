"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { listAll, spacesApi } from "@/lib/api";
import type { Facility, Resources, SpaceResource } from "@/lib/api-types";
import { useWorkspace } from "@/components/workspace";
import { Empty, Failure } from "@/components/ui";
import { resources, labels, fields, contextLabel, formBody, type SpaceData, type SpaceRecord } from "./spaces-config";

const message = (error: unknown) => error instanceof Error ? error.message : "Unable to complete the request.";

function Editor({ resource, record, data, saving, error, save, cancel }: {
  resource: SpaceResource; record?: SpaceRecord; data: SpaceData; saving: boolean; error: string;
  save: (values: FormData) => void; cancel: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const missing = fields[resource].filter(field => field.parent && data[field.parent].length === 0);
  return <section className="panel space-editor" aria-labelledby="editor-title">
    <h2 id="editor-title" tabIndex={-1} ref={heading}>{record ? `Edit ${record.name}` : `Create in ${labels[resource]}`}</h2>
    <p className="muted">{missing.length ? `Create ${missing.map(field => labels[field.parent!].toLowerCase()).join(" and ")} first.` : "Required fields are marked *. Inactive parents remain selectable, as supported by the API."}</p>
    <form onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); save(new FormData(event.currentTarget)); }}>
      <fieldset disabled={saving}><div className="space-fields">{fields[resource].map(field => {
        const value = record && field.key in record ? String(record[field.key as keyof typeof record] ?? "") : "";
        return <label key={field.key}>{field.label}{!field.optional && " *"}
          {field.parent ? <select name={field.key} required defaultValue={value}><option value="">Select {field.label.toLowerCase()}</option>{data[field.parent].map(parent => <option value={parent.id} key={parent.id}>{contextLabel(data, field.parent!, parent.id)}</option>)}</select>
            : field.type === "textarea" ? <textarea name={field.key} defaultValue={value} rows={3} />
            : <input name={field.key} type={field.type ?? "text"} required={!field.optional} defaultValue={value} min={field.min} max={field.max} step={field.type === "number" ? 1 : undefined} maxLength={field.length} />}
        </label>;
      })}</div></fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="space-actions"><button disabled={saving || missing.length > 0} type="submit">{saving ? "Saving…" : "Save changes"}</button><button disabled={saving} type="button" className="secondary" onClick={cancel}>Cancel</button></div>
    </form>
  </section>;
}

function RoomFacilities({ workspace, room, available, close }: { workspace: string; room: Resources["rooms"]; available: Facility[]; close: () => void }) {
  const [assigned, setAssigned] = useState<Facility[] | null>(null);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [saving, setSaving] = useState(false);
  const [version, setVersion] = useState(0);
  const controller = useRef<AbortController | null>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    heading.current?.focus();
    const current = new AbortController(); controller.current = current;
    spacesApi.facilities(workspace, room.id, current.signal).then(rows => { if (!current.signal.aborted) setAssigned(rows); }).catch(error => { if (!current.signal.aborted) setError(message(error)); });
    return () => current.abort();
  }, [workspace, room.id, version]);
  const reload = () => { setAssigned(null); setError(""); setVersion(value => value + 1); };
  async function change(id: string, remove: boolean) {
    const signal = controller.current!.signal;
    setSaving(true); setError(""); setNotice("");
    try {
      if (remove) await spacesApi.remove(workspace, room.id, id, signal);
      else await spacesApi.assign(workspace, room.id, id, signal);
      if (!signal.aborted) { setNotice(remove ? "Facility removed." : "Facility assigned."); reload(); }
    } catch (error) { if (!signal.aborted) setError(message(error)); }
    finally { if (!signal.aborted) setSaving(false); }
  }
  return <section className="panel space-editor" aria-labelledby="facilities-title"><div className="panel-heading"><h2 ref={heading} tabIndex={-1} id="facilities-title">Facilities · {room.name}</h2><button className="secondary" disabled={saving} onClick={close}>Close</button></div>
    {notice && <p role="status" className="success">{notice}</p>}
    {error && <Failure message={error} retry={reload} />}
    {!assigned ? !error && <p role="status">Loading assigned facilities…</p> : <>
      {!assigned.length ? <Empty>No facilities assigned.</Empty> : <ul className="facility-list">{assigned.map(item => <li key={item.id}>{item.name}<button disabled={saving} className="secondary" onClick={() => change(item.id, true)} aria-label={`Remove ${item.name}`}>Remove</button></li>)}</ul>}
      <form onSubmit={event => { event.preventDefault(); const id = String(new FormData(event.currentTarget).get("facility")); void change(id, false); }}>
        <label>Facility<select required name="facility" disabled={saving} defaultValue=""><option value="">Select a facility</option>{available.filter(item => !assigned.some(link => link.id === item.id)).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <button disabled={saving || available.every(item => assigned.some(link => link.id === item.id))}>Assign facility</button>
      </form>
      {!available.length && <p className="muted">Create a facility in the Facilities tab first.</p>}
    </>}
  </section>;
}

export function WorkspaceSpaces({ workspace }: { workspace: string }) {
  const [data, setData] = useState<SpaceData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [resource, setResource] = useState<SpaceResource>("campuses");
  const [editor, setEditor] = useState<{ record?: SpaceRecord } | null>(null);
  const [room, setRoom] = useState<Resources["rooms"] | null>(null);
  const [saving, setSaving] = useState(false);
  const [version, setVersion] = useState(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController(); controller.current = current;
    Promise.all(resources.map(async key => [key, await listAll(workspace, key, current.signal)] as const))
      .then(entries => { if (!current.signal.aborted) setData(Object.fromEntries(entries) as SpaceData); })
      .catch(error => { if (!current.signal.aborted) setLoadError(message(error)); });
    return () => current.abort();
  }, [workspace, version]);
  function reload() { setData(null); setLoadError(""); setVersion(value => value + 1); }
  async function mutate(action: (signal: AbortSignal) => Promise<unknown>, success: string) {
    const signal = controller.current!.signal;
    setSaving(true); setActionError(""); setNotice("");
    try {
      await action(signal);
      if (!signal.aborted) { setNotice(success); setEditor(null); reload(); }
    } catch (error) { if (!signal.aborted) setActionError(message(error)); }
    finally { if (!signal.aborted) setSaving(false); }
  }
  function save(values: FormData) {
    try {
      const body = formBody(resource, values);
      void mutate(signal => editor?.record ? spacesApi.update(workspace, resource, editor.record.id, body, signal) : spacesApi.create(workspace, resource, body, signal), "Saved successfully.");
    } catch (error) { setActionError(message(error)); }
  }
  return <>
    <div className="page-heading"><div><p className="eyebrow">UNIVERSITY INFRASTRUCTURE</p><h1>Spaces</h1><p>Organize your campuses, rooms, and the facilities inside them.</p></div><button className="secondary" disabled={saving || !!editor || !!room} onClick={reload}>Refresh data</button></div>
    {notice && <p role="status" className="success">{notice}</p>}
    {loadError ? <Failure message={loadError} retry={reload} /> : !data ? <p role="status" className="panel">Loading spaces…</p> : <>
      <div className="spaces-summary">{resources.map(key => <div key={key}><strong>{data[key].length}</strong><span>{labels[key]}</span></div>)}<div><strong>{data.rooms.filter(room => room.is_active).length}</strong><span>Active rooms</span></div></div>
      <div className="space-tabs" role="group" aria-label="Space resources">{resources.map(key => <button key={key} className="secondary" aria-pressed={resource === key} disabled={saving} onClick={() => { setResource(key); setEditor(null); setRoom(null); setActionError(""); setNotice(""); }}>{labels[key]}</button>)}</div>
      {editor ? <Editor key={`${resource}:${editor.record?.id ?? "new"}`} resource={resource} record={editor.record} data={data} saving={saving} error={actionError} save={save} cancel={() => { setEditor(null); setActionError(""); }} /> : room ? <RoomFacilities key={room.id} workspace={workspace} room={room} available={data.facilities} close={() => setRoom(null)} /> : <section className="panel">
        <div className="panel-heading"><h2>{labels[resource]}</h2><button disabled={saving} onClick={() => { setEditor({}); setActionError(""); }}>Create new</button></div>
        {actionError && <p role="alert" className="error">{actionError}</p>}
        {!data[resource].length ? <Empty>No {labels[resource].toLowerCase()} yet. Create your first record to get started.</Empty> : <div className="table-scroll" tabIndex={0} role="region" aria-label={`${labels[resource]} records`}><table className="spaces-table"><thead><tr><th scope="col">Name / code</th><th scope="col">Details</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead><tbody>{data[resource].map(row => <tr key={row.id}>
          <td><strong>{row.name}</strong>{"code" in row && <small>{row.code}</small>}</td>
          <td>{fields[resource].filter(field => !["name", "code"].includes(field.key)).map(field => <div key={field.key}><span className="muted">{field.label}: </span>{field.parent ? contextLabel(data, field.parent, String(row[field.key as keyof typeof row])) : String(row[field.key as keyof typeof row] ?? "—")}</div>)}</td>
          <td>{"is_active" in row ? <span className="badge">{row.is_active ? "Active" : "Inactive"}</span> : "—"}</td>
          <td><div className="space-actions"><button disabled={saving} className="secondary" onClick={() => { setEditor({ record: row }); setActionError(""); }} aria-label={`Edit ${row.name}`}>Edit</button>
            {"is_active" in row && <button disabled={saving} className="secondary" onClick={() => void mutate(signal => row.is_active ? spacesApi.deactivate(workspace, resource as "campuses" | "buildings" | "floors" | "rooms", row.id, signal) : spacesApi.update(workspace, resource, row.id, { is_active: true }, signal), row.is_active ? "Record deactivated. Children are unchanged." : "Record reactivated.")}>{row.is_active ? "Deactivate" : "Reactivate"}</button>}
            {resource === "rooms" && <button disabled={saving} className="secondary" onClick={() => setRoom(row as Resources["rooms"])} aria-label={`Facilities for ${row.name}`}>Facilities</button>}
          </div></td>
        </tr>)}</tbody></table></div>}
      </section>}
    </>}
  </>;
}
export default function Spaces() {
  const { workspace } = useWorkspace();
  return workspace ? <WorkspaceSpaces key={workspace.id} workspace={workspace.id} /> : <section className="panel"><h1>Spaces</h1><Empty>Select a workspace above to manage its spaces.</Empty></section>;
}
