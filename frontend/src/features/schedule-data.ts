import type { Resources } from "../lib/api-types";
export const resources = ["schedule-entries", "rooms", "campuses", "buildings", "floors", "departments", "faculty", "courses", "sections"] as const;
export type ScheduleData = { [K in typeof resources[number]]: Resources[K][] };
export type Parent = "rooms" | "faculty" | "sections";
export function label(data: ScheduleData, resource: typeof resources[number], id: string): string {
  const row = data[resource].find(item => item.id === id);
  if (!row || !("name" in row)) return "Unavailable record";
  const own = `${"code" in row ? `${row.code} · ` : ""}${row.name}${"is_active" in row && !row.is_active ? " (inactive)" : ""}`;
  if ("course_id" in row) return `${label(data, "courses", row.course_id)} / ${own}`;
  if ("department_id" in row) return `${own} / ${label(data, "departments", row.department_id)}`;
  if ("floor_id" in row) return `${own} · capacity ${row.capacity} / ${label(data, "floors", row.floor_id)}`;
  if ("building_id" in row) return `${label(data, "buildings", row.building_id)} / ${own}`;
  if ("campus_id" in row) return `${label(data, "campuses", row.campus_id)} / ${own}`;
  return own;
}
