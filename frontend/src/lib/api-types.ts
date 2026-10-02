/** UUIDs and ISO 8601 timestamps are serialized strings from FastAPI. */
interface RecordRead { id: string; workspace_id: string; created_at: string }
interface ActiveRecord extends RecordRead { name: string; is_active: boolean }
export interface Campus extends ActiveRecord { code: string; address: string | null }
export interface Building extends ActiveRecord { campus_id: string; code: string }
export interface Floor extends ActiveRecord { building_id: string; floor_number: number }
export interface RoomType extends RecordRead { name: string; description: string | null }
export type Facility = RoomType;
export interface RoomFacility { workspace_id: string; room_id: string; facility_id: string }
export interface Room extends ActiveRecord { floor_id: string; room_type_id: string; code: string; capacity: number }
export interface AvailableRoom extends Room {
  room_type: RoomType; campus: Campus; building: Building; floor: Floor; facilities: Facility[];
}
export interface AvailabilityQuery {
  starts_at: string; ends_at: string; minimum_capacity: number;
  room_type_id?: string; facility_ids: string[];
}
export interface Department extends ActiveRecord { code: string }
export interface Faculty extends ActiveRecord { department_id: string; email: string }
export interface Course extends ActiveRecord { department_id: string; code: string }
export interface Section extends ActiveRecord { course_id: string; student_count: number }
export interface ScheduleEntry extends RecordRead {
  room_id: string; section_id: string; faculty_id: string;
  starts_at: string; ends_at: string; is_active: boolean;
}
export interface WorkspaceRead { id: string; name: string; slug: string; default_timezone: string; created_at: string }
export type ScheduleInput = Omit<ScheduleEntry, "id" | "workspace_id" | "created_at">;
export interface ScheduleConflict {
  schedule_entry_id: string; conflict_types: ("room" | "faculty" | "section")[];
  room_id: string; faculty_id: string; section_id: string; starts_at: string; ends_at: string;
}
export interface ReservationConflict { reservation_id: string; room_id: string; starts_at: string; ends_at: string }
export interface APIErrorDetail {
  code: string; message: string; has_conflicts?: boolean;
  conflicts?: ScheduleConflict[]; reservation_conflicts?: ReservationConflict[];
}
export interface Reservation extends RecordRead {
  room_id: string; requested_by_user_id: string; title: string; description: string | null;
  starts_at: string; ends_at: string; expected_attendees: number;
  status: "pending" | "approved" | "rejected" | "cancelled";
  reviewed_by_user_id: string | null; reviewed_at: string | null;
  rejection_reason: string | null; updated_at: string;
}
export type ReservationInput = Pick<Reservation, "room_id" | "requested_by_user_id" | "title" | "description" | "starts_at" | "ends_at" | "expected_attendees">;
export interface ReservationReview { reviewed_by_user_id: string; rejection_reason?: string | null }
export interface WorkspaceMember {
  user_id: string; display_name: string; email: string;
  role: "owner" | "admin" | "member" | "viewer"; is_active: boolean;
}
export interface Resources {
  floors: Floor; "room-types": RoomType; facilities: Facility;
  campuses: Campus; buildings: Building; rooms: Room; departments: Department;
  faculty: Faculty; courses: Course; sections: Section;
  "schedule-entries": ScheduleEntry; reservations: Reservation;
}
export type SpaceResource = "campuses" | "buildings" | "floors" | "rooms" | "room-types" | "facilities";
export type AcademicResource = "departments" | "faculty" | "courses" | "sections";
export type AcademicInputs = { [K in AcademicResource]: Omit<Resources[K], "id" | "workspace_id" | "created_at" | "is_active"> & { is_active?: boolean } };
export type SpaceInputs = { [K in SpaceResource]: Omit<Resources[K], "id" | "workspace_id" | "created_at" | "is_active"> & (K extends "campuses" | "buildings" | "floors" | "rooms" ? { is_active?: boolean } : object) };
