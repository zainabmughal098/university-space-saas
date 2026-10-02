"use client";

import { useState } from "react";
import { CalendarDatePicker } from "./calendar-date-picker";

/** Compose local wall-clock text; timezone conversion stays in the schedule form. */
export function DateTimeField({ label, name, defaultValue, calendarToday, onDateChange }: { label: string; name: string; defaultValue: string; calendarToday: string; onDateChange?: () => void }) {
  const initialHour = defaultValue ? Number(defaultValue.slice(11, 13)) : null;
  const [date, setDate] = useState(defaultValue.slice(0, 10));
  const [hour, setHour] = useState(initialHour === null ? "" : String(initialHour % 12 || 12));
  const [minute, setMinute] = useState(defaultValue.slice(14, 16));
  const [period, setPeriod] = useState(initialHour === null ? "" : initialHour >= 12 ? "PM" : "AM");
  const clockHour = String(Number(hour) % 12 + (period === "PM" ? 12 : 0)).padStart(2, "0");
  const local = date && hour && minute && period ? `${date}T${clockHour}:${minute}` : "";
  // Preserve existing seconds/fractions when the displayed date and minute are unchanged.
  const value = local && local === defaultValue.slice(0, 16) ? defaultValue : local;
  return <fieldset className="date-time-field">
    <legend>{label} *</legend>
    <div className="date-time-controls">
      <CalendarDatePicker label={`${label} date`} value={date} onChange={value => { setDate(value); onDateChange?.(); }} today={calendarToday} />
      <label>{label} hour<select required value={hour} onChange={event => setHour(event.target.value)}><option value="">Hour</option>{Array.from({ length: 12 }, (_, index) => index + 1).map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>{label} minute<select required value={minute} onChange={event => setMinute(event.target.value)}><option value="">Minute</option>{Array.from({ length: 60 }, (_, index) => String(index).padStart(2, "0")).map(value => <option key={value} value={value}>{value}</option>)}</select></label>
      <label>{label} AM/PM<select required value={period} onChange={event => setPeriod(event.target.value)}><option value="">AM/PM</option><option value="AM">AM</option><option value="PM">PM</option></select></label>
    </div>
    <input type="hidden" name={name} value={value} />
  </fieldset>;
}
