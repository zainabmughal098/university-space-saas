import { test } from "node:test";
import assert from "node:assert/strict";
import { toInstant, localInput, interval, validateTimezone } from "../src/lib/schedule-time.ts";

test("timezone conversion uses workspace zone, preserves seconds and validates interval", () => {
  assert.equal(toInstant("2026-10-01T09:00", "America/New_York"), "2026-10-01T13:00:00Z");
  assert.equal(localInput("2026-10-01T13:00:23.456Z", "America/New_York"), "2026-10-01T09:00:23.456");
  assert.throws(() => interval("2026-10-01T09:00Z", "2026-10-01T09:00Z"), /End must/);
  assert.throws(() => validateTimezone("invalid/zone"));
});
test("DST gaps rejected, repeated times require explicit choice, unchanged edits preserve instant", () => {
  const zone = "America/New_York";
  for (const choice of ["reject", "earlier", "later"]) assert.throws(() => toInstant("2026-03-08T02:30", zone, choice), /does not exist/);
  assert.throws(() => toInstant("2026-11-01T01:30", zone), /occurs twice/);
  assert.equal(toInstant("2026-11-01T01:30", zone, "earlier"), "2026-11-01T05:30:00Z");
  assert.equal(toInstant("2026-11-01T01:30", zone, "later"), "2026-11-01T06:30:00Z");
  assert.equal(toInstant("2026-11-01T01:30", zone, "reject", "2026-11-01T06:30:00Z"), "2026-11-01T06:30:00Z");
});
