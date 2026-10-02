import type { WorkspaceMember } from "@/lib/api-types";

export function DevelopmentMemberSelect({ label, name, members }: { label: string; name: string; members: WorkspaceMember[] }) {
  return <label className="schedule-room-field">{label} *<select name={name} required defaultValue="">
    <option value="">Select workspace member</option>
    {members.filter(member => member.is_active).map(member => <option key={member.user_id} value={member.user_id}>{member.display_name} — {member.email} ({member.role})</option>)}
  </select></label>;
}
