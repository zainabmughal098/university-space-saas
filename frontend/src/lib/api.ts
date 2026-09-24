import type { Resources } from "./api-types";
export const isWorkspaceId = (value: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

/** Fetch every page: list APIs have no total count or server-side date sorting. */
export async function listAll<K extends keyof Resources>(workspace: string, resource: K, signal: AbortSignal): Promise<Resources[K][]> {
  if (!isWorkspaceId(workspace)) throw new Error("Select a valid workspace UUID.");
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!base) throw new Error("Set NEXT_PUBLIC_API_BASE_URL in frontend/.env.local and restart the frontend.");
  const rows: Resources[K][] = [];
  for (let offset = 0; ; offset += 200) {
    const url = `${base}/api/workspaces/${encodeURIComponent(workspace)}/${resource}?limit=200&offset=${offset}`;
    let response: Response;
    try { response = await fetch(url, { signal, cache: "no-store", credentials: "omit" }); }
    catch (error) {
      if (signal.aborted) throw error;
      throw new Error("Cannot reach the API. Check the backend, API URL, and allowed frontend origin.");
    }
    if (!response.ok) {
      const body = await response.json().catch(() => null);
      const message = body?.detail?.message;
      throw new Error(typeof message === "string" ? message : `API request failed (${response.status}).`);
    }
    const page: Resources[K][] = await response.json();
    if (!Array.isArray(page) || page.some(row => row.workspace_id !== workspace.toLowerCase())) throw new Error("The API returned unexpected workspace data.");
    rows.push(...page);
    if (page.length < 200) return rows;
  }
}
