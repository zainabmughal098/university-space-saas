import type { Resources, SpaceResource, SpaceInputs } from "../lib/api-types";
export const resources = ["campuses", "buildings", "floors", "rooms", "room-types", "facilities"] as const;
export const labels: Record<SpaceResource, string> = { campuses: "Campuses", buildings: "Buildings", floors: "Floors", rooms: "Rooms", "room-types": "Room types", facilities: "Facilities" };
export type SpaceData = { [K in SpaceResource]: Resources[K][] };
export type SpaceRecord = Resources[SpaceResource];
type Field = { key: string; label: string; type?: "number" | "textarea"; parent?: SpaceResource; optional?: boolean; min?: number; max?: number; length?: number };
const name: Field = { key: "name", label: "Name", length: 255 };
const code: Field = { key: "code", label: "Code", length: 64 };
const description: Field = { key: "description", label: "Description", type: "textarea", optional: true };
export const fields: Record<SpaceResource, Field[]> = {
  campuses: [name, code, { key: "address", label: "Address", type: "textarea", optional: true }],
  buildings: [name, code, { key: "campus_id", label: "Campus", parent: "campuses" }],
  floors: [name, { key: "floor_number", label: "Floor number", type: "number", min: -2147483648, max: 2147483647 }, { key: "building_id", label: "Building", parent: "buildings" }],
  rooms: [name, code, { key: "capacity", label: "Capacity", type: "number", min: 1, max: 2147483647 }, { key: "floor_id", label: "Floor", parent: "floors" }, { key: "room_type_id", label: "Room type", parent: "room-types" }],
  "room-types": [name, description], facilities: [name, description],
};
export function contextLabel(data: SpaceData, resource: SpaceResource, id: string): string {
  const row = data[resource].find(item => item.id === id);
  if (!row) return "Unavailable parent";
  let parent = "";
  if ("campus_id" in row) parent = contextLabel(data, "campuses", row.campus_id);
  if ("building_id" in row) parent = contextLabel(data, "buildings", row.building_id);
  if ("floor_id" in row) parent = contextLabel(data, "floors", row.floor_id);
  return `${parent ? parent + " / " : ""}${row.name}${"code" in row ? ` (${row.code})` : ""}${"is_active" in row && !row.is_active ? " · inactive" : ""}`;
}
export function formBody<K extends SpaceResource>(resource: K, values: FormData): SpaceInputs[K] {
  const result: Record<string, string | number | null> = {};
  for (const field of fields[resource]) {
    const value = String(values.get(field.key) ?? "").trim();
    if (!field.optional && !value) throw new Error(`${field.label} is required.`);
    if (field.type === "number") {
      const number = Number(value);
      if (!Number.isInteger(number) || number < field.min! || number > field.max!) throw new Error(`${field.label} must be an integer from ${field.min} to ${field.max}.`);
      result[field.key] = number;
    } else result[field.key] = field.optional && !value ? null : value;
  }
  // Only configured editable fields are sent; active state has a separate action.
  return result as unknown as SpaceInputs[K];
}
