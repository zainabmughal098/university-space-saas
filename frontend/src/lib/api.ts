import type { Resources, SpaceResource, SpaceInputs, Facility, RoomFacility, AcademicResource, AcademicInputs } from "./api-types";
import type { APIErrorDetail, WorkspaceRead, ScheduleInput, ScheduleEntry } from "./api-types";
export class APIError extends Error {
  constructor(public status: number, public detail: APIErrorDetail) { super(detail.message); this.name = "APIError"; }
}
export const isWorkspaceId = (value: string) => /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value);

async function request<T>(workspace: string, path: string, method: string, signal: AbortSignal, body?: unknown): Promise<T> {
  if (!isWorkspaceId(workspace)) throw new Error("Select a valid workspace UUID.");
  const base = process.env.NEXT_PUBLIC_API_BASE_URL?.replace(/\/$/, "");
  if (!base) throw new Error("Set NEXT_PUBLIC_API_BASE_URL in frontend/.env.local and restart the frontend.");
  let response: Response;
  try {
    response = await fetch(`${base}/api/workspaces/${encodeURIComponent(workspace)}${path ? "/" + path : ""}`, {
      method, signal, cache: "no-store", credentials: "omit",
      ...(body === undefined ? {} : { headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }),
    });
  } catch (error) {
    if (signal.aborted) throw error;
    throw new Error(method === "GET" ? "Cannot reach the API. Check the backend and local CORS configuration." : "Could not confirm the change. Refresh the data before retrying.");
  }
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new APIError(response.status, typeof data?.detail?.message === "string" ? data.detail : { code: "api_error", message: `API request failed (${response.status}).` });
  }
  if (response.status === 204) return undefined as T;
  const result = await response.json();
  const rows = Array.isArray(result) ? result : [result];
  if (rows.some(row => (path ? row.workspace_id : row.id) !== workspace.toLowerCase())) throw new Error("The API returned unexpected workspace data.");
  return result as T;
}

export const academicApi = {
  create: <K extends AcademicResource>(workspace: string, resource: K, body: AcademicInputs[K], signal: AbortSignal) => request<Resources[K]>(workspace, resource, "POST", signal, body),
  update: <K extends AcademicResource>(workspace: string, resource: K, id: string, body: Partial<AcademicInputs[K]>, signal: AbortSignal) => request<Resources[K]>(workspace, `${resource}/${encodeURIComponent(id)}`, "PATCH", signal, body),
  deactivate: <K extends AcademicResource>(workspace: string, resource: K, id: string, signal: AbortSignal) => request<Resources[K]>(workspace, `${resource}/${encodeURIComponent(id)}/deactivate`, "POST", signal),
};

export const scheduleApi = {
  workspace: (workspace: string, signal: AbortSignal) => request<WorkspaceRead>(workspace, "", "GET", signal),
  create: (workspace: string, body: ScheduleInput, signal: AbortSignal) => request<ScheduleEntry>(workspace, "schedule-entries", "POST", signal, body),
  update: (workspace: string, id: string, body: Partial<ScheduleInput>, signal: AbortSignal) => request<ScheduleEntry>(workspace, `schedule-entries/${encodeURIComponent(id)}`, "PATCH", signal, body),
  deactivate: (workspace: string, id: string, signal: AbortSignal) => request<ScheduleEntry>(workspace, `schedule-entries/${encodeURIComponent(id)}/deactivate`, "POST", signal),
};

export const spacesApi = {
  create: <K extends SpaceResource>(workspace: string, resource: K, body: SpaceInputs[K], signal: AbortSignal) => request<Resources[K]>(workspace, resource, "POST", signal, body),
  update: <K extends SpaceResource>(workspace: string, resource: K, id: string, body: Partial<SpaceInputs[K]>, signal: AbortSignal) => request<Resources[K]>(workspace, `${resource}/${encodeURIComponent(id)}`, "PATCH", signal, body),
  deactivate: (workspace: string, resource: "campuses" | "buildings" | "floors" | "rooms", id: string, signal: AbortSignal) => request(workspace, `${resource}/${encodeURIComponent(id)}/deactivate`, "POST", signal),
  async facilities(workspace: string, room: string, signal: AbortSignal) {
    const result: Facility[] = [];
    for (let offset = 0; ; offset += 200) {
      const page = await request<Facility[]>(workspace, `rooms/${encodeURIComponent(room)}/facilities?limit=200&offset=${offset}`, "GET", signal);
      result.push(...page);
      if (page.length < 200) return result;
    }
  },
  assign: (workspace: string, room: string, facility: string, signal: AbortSignal) => request<RoomFacility>(workspace, `rooms/${encodeURIComponent(room)}/facilities/${encodeURIComponent(facility)}`, "POST", signal),
  remove: (workspace: string, room: string, facility: string, signal: AbortSignal) => request<void>(workspace, `rooms/${encodeURIComponent(room)}/facilities/${encodeURIComponent(facility)}`, "DELETE", signal),
};

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
