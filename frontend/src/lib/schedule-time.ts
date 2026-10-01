import { Temporal } from "@js-temporal/polyfill";

export function validateTimezone(zone: string) {
  if (!zone || /^[+-]/.test(zone)) throw new Error("Workspace default_timezone must be a valid named timezone.");
  Temporal.Instant.from("2026-01-01T00:00:00Z").toZonedDateTimeISO(zone);
  return zone;
}
export function localInput(instant: string, zone: string) {
  return Temporal.Instant.from(instant).toZonedDateTimeISO(zone).toPlainDateTime().toString();
}
export function toInstant(local: string, zone: string, occurrence = "reject", original?: string) {
  if (!local) throw new Error("Start and end date/time are required.");
  const time = Temporal.PlainDateTime.from(local);
  if (occurrence === "reject" && original && time.equals(Temporal.PlainDateTime.from(localInput(original, zone)))) return original;
  const earlier = time.toZonedDateTime(zone, { disambiguation: "earlier" });
  const later = time.toZonedDateTime(zone, { disambiguation: "later" });
  if (!earlier.toPlainDateTime().equals(time) || !later.toPlainDateTime().equals(time)) throw new Error("This local time does not exist because of a timezone clock change. Choose another time.");
  if (earlier.epochNanoseconds !== later.epochNanoseconds && occurrence === "reject") throw new Error("This local time occurs twice. Choose the earlier or later occurrence explicitly.");
  return (occurrence === "later" ? later : earlier).toInstant().toString();
}
export function interval(start: string, end: string) {
  if (Temporal.Instant.compare(end, start) <= 0) throw new Error("End must be later than start.");
}
export function displayTime(instant: string, zone: string) {
  return new Intl.DateTimeFormat("en", { timeZone: zone, year: "numeric", month: "short", day: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false, timeZoneName: "shortOffset" }).format(new Date(instant));
}
