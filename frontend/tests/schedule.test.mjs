import { JSDOM } from "jsdom";
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
for (const key of ["window", "document", "HTMLElement", "HTMLInputElement", "MutationObserver", "FormData"]) globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { render, screen, fireEvent, cleanup, within, act } = await import("@testing-library/react");
const { default: Schedule } = await import("../src/features/schedule.tsx");
const { WorkspaceProvider, WorkspaceSelector } = await import("../src/components/workspace.tsx");
afterEach(cleanup);
const a = "11111111-1111-1111-1111-111111111111", b = "22222222-2222-2222-2222-222222222222";
const id = "33333333-3333-3333-3333-333333333333";
const base = { id, workspace_id: a, created_at: "2026-01-01T00:00:00Z", is_active: true };
const entry = { ...base, room_id: id, section_id: id, faculty_id: id, starts_at: "2026-10-01T13:00:00Z", ends_at: "2026-10-01T14:00:00Z" };
function setup(t, entries = [], control = {}) {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const data = structuredClone({
    "schedule-entries": entries,
    campuses: [{ ...base, name: "North", code: "N", address: null }],
    buildings: [{ ...base, name: "Science", code: "SC", campus_id: id }],
    floors: [{ ...base, name: "Ground", floor_number: 0, building_id: id }],
    rooms: [{ ...base, name: "Lecture room", code: "R1", floor_id: id, room_type_id: id, capacity: control.capacity ?? 40 }],
    departments: [{ ...base, name: "Computing", code: "CS" }],
    faculty: [{ ...base, name: "Alex Reed", email: "alex@example.test", department_id: id }],
    courses: [{ ...base, name: "Algorithms", code: "CS101", department_id: id }],
    sections: [{ ...base, name: "Section A", course_id: id, student_count: 30 }],
  });
  if (control.inactive) for (const key of ["rooms", "faculty", "sections"]) data[key][0].is_active = false;
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    const path = new URL(url).pathname.split("/");
    const workspace = path[3], resource = path[4], method = options.method ?? "GET";
    requests.push({ workspace, resource, method, signal: options.signal, body: options.body && JSON.parse(options.body) });
    if (control.network) throw new Error("Network unavailable");
    if (control.delay && workspace === a) await control.delay;
    if (!resource) return Response.json({ id: workspace, name: "Test University", slug: "test", default_timezone: control.zone ?? "America/New_York", created_at: base.created_at });
    if (method !== "GET" && control.failure) return Response.json({ detail: control.failure }, { status: control.failure.code === "insufficient_capacity" ? 422 : 409 });
    if (method === "PATCH" || path[6] === "deactivate") {
      const row = data[resource].find(row => row.id === path[5]);
      Object.assign(row, method === "PATCH" ? JSON.parse(options.body) : { is_active: false });
      return Response.json(row);
    }
    if (method === "POST") {
      const row = { ...base, id: crypto.randomUUID(), ...JSON.parse(options.body) };
      data[resource].push(row); return Response.json(row, { status: 201 });
    }
    return Response.json(workspace === a ? data[resource] : []);
  });
  render(React.createElement(WorkspaceProvider, null, React.createElement(WorkspaceSelector), React.createElement(Schedule)));
  selectWorkspace(a);
  return { data, requests, control };
}
function selectWorkspace(value) { fireEvent.change(screen.getByLabelText("Workspace UUID"), { target: { value } }); fireEvent.click(screen.getByRole("button", { name: "Use workspace" })); }
const fill = (name, value) => fireEvent.change(screen.getByLabelText(name), { target: { value } });
function fillTime(label, value) {
  fill(`${label} date`, value.slice(0, 10));
  const hour = Number(value.slice(11, 13));
  fill(`${label} hour`, String(hour % 12 || 12));
  fill(`${label} minute`, value.slice(14, 16));
  fill(`${label} AM/PM`, hour >= 12 ? "PM" : "AM");
}
const save = () => fireEvent.submit(screen.getByRole("button", { name: "Save changes" }).closest("form"));
async function openCreate() {
  await screen.findByRole("heading", { name: "Chronological schedule" });
  fireEvent.click(screen.getByRole("button", { name: "Create new" }));
  for (const name of ["Section *", "Faculty *", "Room *"]) fill(name, id);
  fillTime("Start", "2026-10-01T09:00"); fillTime("End", "2026-10-01T10:00");
}
const table = () => screen.getByRole("region", { name: "Schedule entries" });

test("empty schedule and create use readable selectors and timezone-aware payload", async t => {
  const { requests } = setup(t);
  await screen.findByText("No schedule entries yet.");
  await openCreate();
  assert.match(screen.getByLabelText("Section *").textContent, /CS101.*Algorithms.*Section A/);
  assert.match(screen.getByLabelText("Faculty *").textContent, /Alex Reed.*Computing/);
  assert.match(screen.getByLabelText("Room *").textContent, /R1.*Lecture room.*40.*North.*Science.*Ground/);
  save(); await screen.findByRole("region", { name: "Schedule entries" });
  const request = requests.find(row => row.method === "POST");
  assert.deepEqual(request.body, { section_id: id, faculty_id: id, room_id: id, starts_at: "2026-10-01T13:00:00Z", ends_at: "2026-10-01T14:00:00Z", is_active: true });
  assert.equal(request.workspace, a);
  assert.match(table().textContent, /Algorithms.*Section A.*Alex Reed.*Lecture room.*North.*Science/s);
  assert.match(table().textContent, /09:00:00.*GMT-4/);
});
test("invalid intervals preserve form and make no mutation", async t => {
  const { requests } = setup(t); await openCreate();
  for (const end of ["2026-10-01T09:00", "2026-10-01T08:00"]) {
    fillTime("End", end); save(); assert.match(screen.getByRole("alert").textContent, /End must be later/);
  }
  assert.equal(requests.filter(row => row.method !== "GET").length, 0);
});
test("split controls handle midnight/noon and expose no native datetime popup", async t => {
  const { requests } = setup(t); await openCreate();
  assert.equal(document.querySelector('input[type="datetime-local"]'), null);
  assert.equal(screen.queryByRole("button", { name: /Choose|picker/i }), null);
  fillTime("Start", "2026-10-01T00:05"); fillTime("End", "2026-10-01T12:15");
  assert.equal(screen.getByLabelText("Start hour").value, "12");
  assert.equal(screen.getByLabelText("Start AM/PM").value, "AM");
  assert.equal(screen.getByLabelText("End AM/PM").value, "PM");
  save(); await screen.findByRole("region", { name: "Schedule entries" });
  const payload = requests.find(row => row.method === "POST").body;
  assert.equal(payload.starts_at, "2026-10-01T04:05:00Z");
  assert.equal(payload.ends_at, "2026-10-01T16:15:00Z");
});
test("manual dates and DST gaps are validated without mutations", async t => {
  const { requests } = setup(t); await openCreate();
  fill("Start date", "2026-02-30"); save(); assert.ok(screen.getByRole("alert"));
  fill("Start date", ""); save(); assert.match(screen.getByRole("alert").textContent, /required/);
  fillTime("Start", "2026-03-08T02:30"); fillTime("End", "2026-03-08T04:00");
  save(); assert.match(screen.getByRole("alert").textContent, /does not exist/);
  assert.equal(requests.filter(row => row.method !== "GET").length, 0);
});
test("editing without changing split controls preserves existing seconds", async t => {
  const precise = { ...entry, starts_at: "2026-10-01T13:00:23.456Z", ends_at: "2026-10-01T14:00:45Z" };
  const { requests } = setup(t, [precise]); await screen.findByRole("region", { name: "Schedule entries" });
  fireEvent.click(within(table()).getByRole("button", { name: "Edit" }));
  save(); await screen.findByRole("region", { name: "Schedule entries" });
  const payload = requests.find(row => row.method === "PATCH").body;
  assert.equal(payload.starts_at, precise.starts_at);
  assert.equal(payload.ends_at, precise.ends_at);
});
test("fall-back interval can choose different start and end occurrences", async t => {
  const { requests } = setup(t); await openCreate();
  fillTime("Start", "2026-11-01T01:45"); fillTime("End", "2026-11-01T01:15");
  save(); assert.match(screen.getByRole("alert").textContent, /occurs twice/);
  fill("Repeated start clock time", "earlier"); fill("Repeated end clock time", "later");
  save(); await screen.findByRole("region", { name: "Schedule entries" });
  const payload = requests.find(row => row.method === "POST").body;
  assert.equal(payload.starts_at, "2026-11-01T05:45:00Z");
  assert.equal(payload.ends_at, "2026-11-01T06:15:00Z");
});
test("capacity warning and authoritative backend capacity error show both sizes", async t => {
  setup(t, [], { capacity: 20, failure: { code: "insufficient_capacity", message: "Too small" } });
  await openCreate(); assert.match(screen.getByText(/Capacity warning/).textContent, /30.*20/);
  save(); const error = await screen.findByRole("alert");
  assert.match(error.textContent, /cannot accommodate.*30.*20/);
  assert.equal(screen.getByLabelText("Section *").value, id);
});
for (const kind of ["room", "faculty", "section", "reservation"]) test(`${kind} conflict response is shown with interval and named resource`, async t => {
  const failure = { code: kind === "reservation" ? "reservation_conflict" : "schedule_conflict", message: "Overlapping occupancy", has_conflicts: true,
    conflicts: kind === "reservation" ? [] : [{ ...entry, schedule_entry_id: id, conflict_types: [kind] }],
    reservation_conflicts: kind === "reservation" ? [{ ...entry, reservation_id: id }] : [],
  };
  setup(t, [], { failure }); await openCreate(); save();
  const error = await screen.findByRole("alert");
  assert.match(error.textContent, new RegExp(kind === "reservation" ? "Approved reservation conflict" : `${kind[0].toUpperCase()}${kind.slice(1)} conflict`));
  assert.match(error.textContent, /Lecture room.*09:00:00/s);
  assert.ok(screen.getByRole("button", { name: "Save changes" }));
});
test("edit converts existing times, patch and deactivate/reactivate refresh", async t => {
  const { requests } = setup(t, [entry]); await screen.findByRole("region", { name: "Schedule entries" });
  fireEvent.click(within(table()).getByRole("button", { name: "Edit" }));
  assert.equal(screen.getByLabelText("Start date").value, "2026-10-01");
  assert.equal(screen.getByLabelText("Start hour").value, "9");
  fillTime("End", "2026-10-01T11:00"); save(); await screen.findByRole("region", { name: "Schedule entries" });
  assert.equal(requests.find(row => row.method === "PATCH").body.ends_at, "2026-10-01T15:00:00Z");
  fireEvent.click(within(table()).getByRole("button", { name: "Deactivate" }));
  await screen.findByRole("button", { name: "Reactivate" });
  fireEvent.click(screen.getByRole("button", { name: "Reactivate" }));
  await screen.findByRole("button", { name: "Deactivate" });
  assert.equal(requests.filter(row => row.method === "DELETE").length, 0);
});
test("inactive parents are retained on edit but excluded from creation", async t => {
  setup(t, [{ ...entry, is_active: false }], { inactive: true });
  await screen.findByRole("region", { name: "Schedule entries" });
  fireEvent.click(within(table()).getByRole("button", { name: "Edit" }));
  for (const name of ["Section *", "Faculty *", "Room *"]) { assert.equal(screen.getByLabelText(name).value, id); assert.match(screen.getByLabelText(name).textContent, /inactive/); }
  assert.equal(screen.getByLabelText("Active").checked, false);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "Create new" }));
  assert.equal(screen.getByRole("button", { name: "Save changes" }).disabled, true);
});
test("date and relationship/status filters use workspace date and can be cleared", async t => {
  setup(t, [entry]); await screen.findByRole("region", { name: "Schedule entries" });
  fill("Start date (America/New_York)", "2026-10-02"); assert.ok(screen.getByText("No entries match these filters."));
  fireEvent.click(screen.getByRole("button", { name: "Clear filters" }));
  for (const key of ["rooms", "faculty", "sections", "courses"]) fill(`Filter ${key}`, id);
  assert.ok(table()); fill("Status", "inactive"); assert.ok(screen.getByText("No entries match these filters."));
});
test("workspace change clears forms and ignores delayed old responses", async t => {
  let resolve;
  const delay = new Promise(done => { resolve = done; });
  const { requests } = setup(t, [entry], { delay });
  selectWorkspace(b); await screen.findByText("No schedule entries yet.");
  assert.ok(requests.filter(row => row.workspace === a).every(row => row.signal.aborted));
  await act(async () => { resolve(); await delay; });
  assert.equal(screen.queryByRole("region", { name: "Schedule entries" }), null);
});
test("network failures retry and invalid workspace timezone blocks management", async t => {
  const control = { network: true };
  setup(t, [], control); await screen.findByRole("alert");
  control.network = false; fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText("No schedule entries yet.");
  control.zone = "Invalid/Timezone"; fireEvent.click(screen.getByRole("button", { name: "Refresh data" }));
  await screen.findByRole("alert"); assert.equal(screen.queryByRole("button", { name: "Create new" }), null);
});
