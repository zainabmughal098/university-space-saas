import { Temporal } from "@js-temporal/polyfill";
import { isWorkspaceId } from "./api";
import type { Room } from "./api-types";
import { interval, localInput } from "./schedule-time";

const keys = ["request_workspace", "request_room", "request_start", "request_end", "request_timezone"] as const;
export interface ReservationPrefill { room_id: string; starts_at: string; ends_at: string }

export function reservationRequestHref(workspace: string, room: string, start: string, end: string, zone: string) {
  return `/reservations?${new URLSearchParams(Object.fromEntries(keys.map((key, i) => [key, [workspace, room, start, end, zone][i]])))}`;
}

export function readReservationPrefill(search: string, workspace: string, zone: string, rooms: Room[]): { present: boolean; value?: ReservationPrefill } {
  const params = new URLSearchParams(search);
  const present = keys.some(key => params.has(key));
  if (!present) return { present: false };
  try {
    if (keys.some(key => params.getAll(key).length !== 1 || !params.get(key) || params.get(key)!.length > 150)) throw new Error();
    const [owner, room, start, end, timezone] = keys.map(key => params.get(key)!);
    if (!isWorkspaceId(owner) || owner.toLowerCase() !== workspace || !isWorkspaceId(room) || timezone !== zone) throw new Error();
    if (!rooms.some(row => row.id === room.toLowerCase() && row.workspace_id === workspace && row.is_active)) throw new Error();
    const starts_at = Temporal.Instant.from(start).toString(), ends_at = Temporal.Instant.from(end).toString();
    interval(starts_at, ends_at);
    // Current calendar/time controls support ordinary four-digit calendar years.
    if (![starts_at, ends_at].every(value => /^\d{4}-/.test(localInput(value, zone)))) throw new Error();
    return { present: true, value: { room_id: room.toLowerCase(), starts_at, ends_at } };
  } catch { return { present: true }; }
}

export function clearReservationPrefill() {
  const url = new URL(window.location.href);
  for (const key of keys) url.searchParams.delete(key);
  window.history.replaceState(window.history.state, "", `${url.pathname}${url.search}${url.hash}`);
}
