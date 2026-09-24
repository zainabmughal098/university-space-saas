"use client";
import { createContext, useContext, useState, type ReactNode, type FormEvent } from "react";
import { isWorkspaceId } from "@/lib/api";
type Workspace = { id: string; name: string };
const Context = createContext<{ workspace: Workspace | null; select: (value: Workspace) => void } | null>(null);
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [workspace, select] = useState<Workspace | null>(null);
  return <Context.Provider value={{ workspace, select }}>{children}</Context.Provider>;
}
export function useWorkspace() {
  const value = useContext(Context);
  if (!value) throw new Error("WorkspaceProvider is required");
  return value;
}
export function WorkspaceSelector() {
  const { workspace, select } = useWorkspace();
  const [error, setError] = useState("");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    const id = String(data.get("workspace") ?? "").trim().toLowerCase();
    const name = String(data.get("name") ?? "").trim();
    if (!isWorkspaceId(id)) { setError("Enter a valid workspace UUID."); return; }
    setError(""); select({ id, name: name || "University workspace" });
  }
  return <details className="workspace-picker" open={workspace ? undefined : true}>
    <summary>{workspace ? "Change workspace" : "Connect your workspace"} <span className="badge">Development</span></summary>
    <p>Enter an existing workspace UUID and a display label. This selector does not authenticate you or verify membership.</p>
    <form onSubmit={submit}>
      <label>Workspace UUID<input name="workspace" required defaultValue={workspace?.id} placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx" aria-describedby={error ? "workspace-error" : undefined} /></label>
      <label>Workspace display name<input name="name" maxLength={255} defaultValue={workspace?.name} placeholder="Your university" /></label>
      <button type="submit">Use workspace</button>
    </form>
    {error && <p id="workspace-error" role="alert" className="error">{error}</p>}
  </details>;
}
