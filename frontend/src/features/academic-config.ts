import type { Resources, AcademicResource, AcademicInputs } from "../lib/api-types";
export const resources = ["departments", "faculty", "courses", "sections"] as const;
export const labels: Record<AcademicResource, string> = { departments: "Departments", faculty: "Faculty", courses: "Courses", sections: "Sections" };
export type AcademicData = { [K in AcademicResource]: Resources[K][] };
export type AcademicRecord = Resources[AcademicResource];
type Field = { key: string; label: string; type?: "number" | "email"; parent?: "departments" | "courses"; min?: number; max?: number; length?: number };
const name: Field = { key: "name", label: "Name", length: 255 };
const code: Field = { key: "code", label: "Code", length: 64 };
const department: Field = { key: "department_id", label: "Department", parent: "departments" };
export const fields: Record<AcademicResource, Field[]> = {
  departments: [name, code],
  faculty: [name, { key: "email", label: "Email", type: "email", length: 320 }, department],
  courses: [name, code, department],
  sections: [name, { key: "student_count", label: "Student count", type: "number", min: 1, max: 2147483647 }, { key: "course_id", label: "Course", parent: "courses" }],
};
export function contextLabel(data: AcademicData, resource: "departments" | "courses", id: string): string {
  const row = data[resource].find(item => item.id === id);
  if (!row) return "Unavailable parent";
  const prefix = "department_id" in row && typeof row.department_id === "string" ? contextLabel(data, "departments", row.department_id) + " / " : "";
  return `${prefix}${row.name} (${row.code})${row.is_active ? "" : " · inactive"}`;
}
export function parentOptions(data: AcademicData, parent: "departments" | "courses", current?: string) {
  return data[parent].filter(row => row.is_active || row.id === current);
}
export function formBody<K extends AcademicResource>(resource: K, values: FormData): AcademicInputs[K] {
  const result: Record<string, string | number> = {};
  for (const field of fields[resource]) {
    const value = String(values.get(field.key) ?? "").trim();
    if (!value) throw new Error(`${field.label} is required.`);
    if (field.length && value.length > field.length) throw new Error(`${field.label} must be at most ${field.length} characters.`);
    if (field.type === "number") {
      const number = Number(value);
      if (!Number.isInteger(number) || number < field.min! || number > field.max!) throw new Error(`${field.label} must be a positive integer no greater than ${field.max}.`);
      result[field.key] = number;
    } else {
      if (field.type === "email" && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(value)) throw new Error("Enter a valid email address, for example name@university.edu.");
      result[field.key] = value;
    }
  }
  return result as unknown as AcademicInputs[K];
}
