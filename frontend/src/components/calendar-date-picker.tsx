"use client";

import { useId, useRef, useState, type KeyboardEvent } from "react";
import { Temporal } from "@js-temporal/polyfill";

const friendly = (date: string) => Temporal.PlainDate.from(date).toLocaleString("en", { month: "short", day: "numeric", year: "numeric" });

/** Date-only selection. Callers own timezone conversion and the meaning of today. */
export function CalendarDatePicker({ label, value, onChange, today, clearable = false }: {
  label: string; value: string; onChange: (value: string) => void; today: string; clearable?: boolean;
}) {
  const id = useId(), dialog = useRef<HTMLDialogElement>(null), trigger = useRef<HTMLButtonElement>(null);
  const [cursor, setCursor] = useState(value || today);
  const date = Temporal.PlainDate.from(cursor), month = date.with({ day: 1 });
  const first = month.subtract({ days: month.dayOfWeek % 7 });
  const days = Array.from({ length: 42 }, (_, index) => first.add({ days: index }));
  function focusDay(next: Temporal.PlainDate) {
    setCursor(next.toString());
    requestAnimationFrame(() => dialog.current?.querySelector<HTMLButtonElement>(`[data-date="${next}"]`)?.focus());
  }
  function close() { dialog.current?.close(); trigger.current?.focus(); }
  function select(date: string) { onChange(date); close(); }
  function keyboard(event: KeyboardEvent<HTMLButtonElement>, day: Temporal.PlainDate) {
    const moves: Record<string, number> = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7, Home: -(day.dayOfWeek % 7), End: 6 - day.dayOfWeek % 7 };
    if (event.key in moves) { event.preventDefault(); focusDay(day.add({ days: moves[event.key] })); }
    if (event.key === "PageUp" || event.key === "PageDown") { event.preventDefault(); focusDay(day.add({ months: event.key === "PageUp" ? -1 : 1 })); }
  }
  return <div className="calendar-field"><span id={`${id}-label`} className="calendar-label">{label}</span>
    <button className="calendar-trigger secondary" type="button" ref={trigger} aria-labelledby={`${id}-label ${id}-value`} aria-haspopup="dialog" onClick={() => {
      setCursor(value || today); dialog.current?.showModal();
      requestAnimationFrame(() => dialog.current?.querySelector<HTMLButtonElement>(`[data-date="${value || today}"]`)?.focus());
    }}><svg aria-hidden="true" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7"><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 11h18" /></svg><span id={`${id}-value`}>{value ? friendly(value) : "Select date"}</span></button>
    {clearable && value && <button type="button" className="secondary calendar-clear" onClick={() => onChange("")}>Clear {label.toLowerCase()}</button>}
    <dialog className="calendar-dialog" ref={dialog} aria-labelledby={`${id}-title`} onCancel={() => trigger.current?.focus()}>
      <div className="calendar-heading"><h2 id={`${id}-title`}>Choose {label.toLowerCase()}</h2><button type="button" className="secondary" aria-label="Close calendar" onClick={close}>✕</button></div>
      <div className="calendar-month"><button type="button" className="secondary" aria-label="Previous month" onClick={() => setCursor(date.subtract({ months: 1 }).toString())}>‹</button><strong aria-live="polite">{month.toLocaleString("en", { month: "long", year: "numeric" })}</strong><button type="button" className="secondary" aria-label="Next month" onClick={() => setCursor(date.add({ months: 1 }).toString())}>›</button></div>
      <div className="calendar-days" role="group" aria-label="Days"><div className="calendar-weekdays" aria-hidden="true">{["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"].map(day => <span key={day}>{day}</span>)}</div>
        <div className="calendar-grid">{days.map(day => <button type="button" key={day.toString()} data-date={day.toString()} tabIndex={day.toString() === cursor ? 0 : -1} aria-label={friendly(day.toString())} aria-pressed={value === day.toString()} aria-current={today === day.toString() ? "date" : undefined} className={`${day.month !== month.month ? "outside-month" : ""}`} onKeyDown={event => keyboard(event, day)} onClick={() => select(day.toString())}>{day.day}</button>)}</div>
      </div>
      <div className="calendar-footer"><button type="button" className="secondary" onClick={() => select(today)}>Today</button><p className="muted">Arrow keys move by day or week. Page Up/Down changes month.</p></div>
    </dialog>
  </div>;
}
