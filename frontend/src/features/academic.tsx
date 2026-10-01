"use client";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { listAll, academicApi } from "@/lib/api";
import type { AcademicResource } from "@/lib/api-types";
import { useWorkspace } from "@/components/workspace";
import { Empty, Failure } from "@/components/ui";
import { resources, labels, fields, contextLabel, formBody, parentOptions, type AcademicData, type AcademicRecord } from "./academic-config";

const message = (error: unknown) => error instanceof Error ? error.message : "Unable to complete the request.";

function Editor({ resource, record, data, saving, error, save, cancel }: {
  resource: AcademicResource; record?: AcademicRecord; data: AcademicData; saving: boolean; error: string;
  save: (values: FormData) => void; cancel: () => void;
}) {
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => { heading.current?.focus(); }, []);
  const missing = fields[resource].filter(field => field.parent && parentOptions(data, field.parent, record && field.key in record ? String(record[field.key as keyof typeof record]) : undefined).length === 0);
  return <section className="panel space-editor" aria-labelledby="editor-title">
    <h2 id="editor-title" tabIndex={-1} ref={heading}>{record ? `Edit ${record.name}` : `Create in ${labels[resource]}`}</h2>
    <p className="muted">{missing.length ? `Create or reactivate ${missing.map(field => labels[field.parent!].toLowerCase()).join(" and ")} first.` : "Required fields are marked *. Active parents are offered; an existing inactive parent can be retained."}</p>
    <form onSubmit={(event: FormEvent<HTMLFormElement>) => { event.preventDefault(); save(new FormData(event.currentTarget)); }}>
      <fieldset disabled={saving}><div className="space-fields">{fields[resource].map(field => {
        const value = record && field.key in record ? String(record[field.key as keyof typeof record] ?? "") : "";
        return <label key={field.key}>{field.label}{" *"}
          {field.parent ? <select name={field.key} required defaultValue={value}><option value="">Select {field.label.toLowerCase()}</option>{parentOptions(data, field.parent, value).map(parent => <option value={parent.id} key={parent.id}>{contextLabel(data, field.parent!, parent.id)}</option>)}</select>
            : <input name={field.key} type={field.type ?? "text"} required defaultValue={value} min={field.min} max={field.max} step={field.type === "number" ? 1 : undefined} maxLength={field.length} />}
        </label>;
      })}</div></fieldset>
      {error && <p className="error" role="alert">{error}</p>}
      <div className="space-actions"><button disabled={saving || missing.length > 0} type="submit">{saving ? "Saving…" : "Save changes"}</button><button disabled={saving} type="button" className="secondary" onClick={cancel}>Cancel</button></div>
    </form>
  </section>;
}

export function WorkspaceAcademic({ workspace }: { workspace: string }) {
  const [data, setData] = useState<AcademicData | null>(null);
  const [loadError, setLoadError] = useState("");
  const [actionError, setActionError] = useState("");
  const [notice, setNotice] = useState("");
  const [resource, setResource] = useState<AcademicResource>("departments");
  const [editor, setEditor] = useState<{ record?: AcademicRecord } | null>(null);
  const [saving, setSaving] = useState(false);
  const [version, setVersion] = useState(0);
  const controller = useRef<AbortController | null>(null);
  useEffect(() => {
    const current = new AbortController(); controller.current = current;
    Promise.all(resources.map(async key => [key, await listAll(workspace, key, current.signal)] as const))
      .then(entries => { if (!current.signal.aborted) setData(Object.fromEntries(entries) as AcademicData); })
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
      void mutate(signal => editor?.record ? academicApi.update(workspace, resource, editor.record.id, body, signal) : academicApi.create(workspace, resource, body, signal), "Saved successfully.");
    } catch (error) { setActionError(message(error)); }
  }
  return <>
    <div className="page-heading"><div><p className="eyebrow">ACADEMIC STRUCTURE</p><h1>Academic</h1><p>Manage departments, faculty, courses, and sections.</p></div><button className="secondary" disabled={saving || !!editor} onClick={reload}>Refresh data</button></div>
    {notice && <p role="status" className="success">{notice}</p>}
    {loadError ? <Failure message={loadError} retry={reload} /> : !data ? <p role="status" className="panel">Loading academic records…</p> : <>
      <div className="spaces-summary">{resources.flatMap(key => [<div key={key}><strong>{data[key].length}</strong><span>Total {labels[key].toLowerCase()}</span></div>, <div key={`${key}-active`}><strong>{data[key].filter(row => row.is_active).length}</strong><span>Active {labels[key].toLowerCase()}</span></div>])}</div>
      <div className="space-tabs" role="group" aria-label="Academic resources">{resources.map(key => <button key={key} className="secondary" aria-pressed={resource === key} disabled={saving} onClick={() => { setResource(key); setEditor(null); setActionError(""); setNotice(""); }}>{labels[key]}</button>)}</div>
      {editor ? <Editor key={`${resource}:${editor.record?.id ?? "new"}`} resource={resource} record={editor.record} data={data} saving={saving} error={actionError} save={save} cancel={() => { setEditor(null); setActionError(""); }} /> : <section className="panel">
        <div className="panel-heading"><h2>{labels[resource]}</h2><button disabled={saving} onClick={() => { setEditor({}); setActionError(""); }}>Create new</button></div>
        {actionError && <p role="alert" className="error">{actionError}</p>}
        {!data[resource].length ? <Empty>No {labels[resource].toLowerCase()} yet. Create your first record to get started.</Empty> : <div className="table-scroll" tabIndex={0} role="region" aria-label={`${labels[resource]} records`}><table className="spaces-table"><thead><tr><th scope="col">Name / code</th><th scope="col">Details</th><th scope="col">Status</th><th scope="col">Actions</th></tr></thead><tbody>{data[resource].map(row => <tr key={row.id}>
          <td><strong>{row.name}</strong>{"code" in row && <small>{row.code}</small>}</td>
          <td>{fields[resource].filter(field => !["name", "code"].includes(field.key)).map(field => <div key={field.key}><span className="muted">{field.label}: </span>{field.parent ? contextLabel(data, field.parent, String(row[field.key as keyof typeof row])) : String(row[field.key as keyof typeof row] ?? "—")}</div>)}</td>
          <td>{"is_active" in row ? <span className="badge">{row.is_active ? "Active" : "Inactive"}</span> : "—"}</td>
          <td><div className="space-actions"><button disabled={saving} className="secondary" onClick={() => { setEditor({ record: row }); setActionError(""); }} aria-label={`Edit ${row.name}`}>Edit</button>
            {"is_active" in row && <button disabled={saving} className="secondary" onClick={() => void mutate(signal => row.is_active ? academicApi.deactivate(workspace, resource, row.id, signal) : academicApi.update(workspace, resource, row.id, { is_active: true }, signal), row.is_active ? "Record deactivated. Children are unchanged." : "Record reactivated.")}>{row.is_active ? "Deactivate" : "Reactivate"}</button>}
          </div></td>
        </tr>)}</tbody></table></div>}
      </section>}
    </>}
  </>;
}
export default function Academic() {
  const { workspace } = useWorkspace();
  return workspace ? <WorkspaceAcademic key={workspace.id} workspace={workspace.id} /> : <section className="panel"><h1>Academic</h1><Empty>Select a workspace above to manage its academic records.</Empty></section>;
}
