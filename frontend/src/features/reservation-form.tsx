"use client";
import type { ReservationPrefill } from "@/lib/reservation-prefill";
import { localInput } from "@/lib/schedule-time";
import { DateTimeField } from "@/components/date-time-field";
import type { Room, WorkspaceMember } from "@/lib/api-types";
import { DevelopmentMemberSelect } from "@/components/development-member-select";

export function ReservationFields({ rooms, roomLabel, today, members, prefill, zone }: { rooms: Room[]; roomLabel: (id: string) => string; today: string; members: WorkspaceMember[]; prefill?: ReservationPrefill; zone: string }) {
  return <>
    <fieldset className="schedule-form-section"><legend>Request details</legend><div className="schedule-class-grid">
      <label className="schedule-room-field">Room *<select name="room_id" required defaultValue={prefill?.room_id ?? ""}><option value="">Select a room</option>{rooms.filter(room => room.is_active).map(room => <option key={room.id} value={room.id}>{roomLabel(room.id)}</option>)}</select></label>
      <label>Title *<input name="title" required maxLength={255} /></label><label>Expected attendees *<input name="expected_attendees" type="number" required min={1} max={2147483647} step={1} /></label>
      <DevelopmentMemberSelect label="Development requester" name="requested_by_user_id" members={members} />
      <label className="schedule-room-field">Description<textarea name="description" rows={3} /></label>
    </div></fieldset>
    <section className="schedule-time-section"><h3>Date &amp; time</h3><div className="schedule-time-rows"><DateTimeField label="Start" name="starts_at" defaultValue={prefill ? localInput(prefill.starts_at, zone) : ""} calendarToday={today} /><DateTimeField label="End" name="ends_at" defaultValue={prefill ? localInput(prefill.ends_at, zone) : ""} calendarToday={today} /></div></section>
    <fieldset className="schedule-advanced"><legend>Advanced time options</legend><p className="muted">Choose an occurrence only when a local clock time repeats.</p><div className="schedule-advanced-grid">{["starts", "ends"].map(key => <label key={key}>Repeated {key === "starts" ? "start" : "end"} clock time<select name={`${key}_occurrence`} defaultValue="reject"><option value="reject">Ask if a time occurs twice</option><option value="earlier">Earlier occurrence</option><option value="later">Later occurrence</option></select></label>)}</div></fieldset>
  </>;
}
