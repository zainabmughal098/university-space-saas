import { JSDOM } from "jsdom";
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
for (const key of ["window", "document", "HTMLElement", "HTMLInputElement", "MutationObserver", "FormData"]) globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { render, screen, fireEvent, cleanup, act } = await import("@testing-library/react");
const { installDialogMock, selectCalendar } = await import("./calendar-helper.mjs");
installDialogMock(dom);
const { default: FindRoom } = await import("../src/features/find-room.tsx");
const { WorkspaceProvider, WorkspaceSelector } = await import("../src/components/workspace.tsx");
const { findAvailableRooms } = await import("../src/lib/api.ts");
afterEach(cleanup);
const a = "11111111-1111-1111-1111-111111111111", b = "22222222-2222-2222-2222-222222222222";
const id = "33333333-3333-3333-3333-333333333333", other = "44444444-4444-4444-4444-444444444444";
const base = { id, workspace_id: a, created_at: "2026-01-01T00:00:00Z", is_active: true };
const facilities = [{ ...base, name: "Projector", description: null }, { ...base, id: other, name: "Whiteboard", description: null }];
const room = { ...base, name: "Lecture Hall", code: "LT-1", capacity: 100, floor_id: id, room_type_id: id,
  room_type: { ...base, name: "Lecture Theatre", description: null }, campus: { ...base, name: "North Campus", code: "N", address: null },
  building: { ...base, name: "Science Block", code: "SC", campus_id: id }, floor: { ...base, name: "Ground Floor", floor_number: 0, building_id: id }, facilities };
const fill = (name, value) => fireEvent.change(screen.getByLabelText(name), { target: { value } });
function select(value) { fill("Workspace UUID", value); fireEvent.click(screen.getByRole("button", { name: "Use workspace" })); }
function time(label, value) {
  selectCalendar(`${label} date`, value.slice(0, 10)); const hour = Number(value.slice(11, 13));
  fill(`${label} hour`, String(hour % 12 || 12)); fill(`${label} minute`, value.slice(14, 16)); fill(`${label} AM/PM`, hour >= 12 ? "PM" : "AM");
}
const search = () => fireEvent.submit(screen.getByRole("button", { name: "Find available rooms" }).closest("form"));
function setup(t, control = {}, selected = true) {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    const parsed = new URL(url), path = parsed.pathname.split("/");
    assert.equal(options.method ?? "GET", "GET");
    requests.push({ url: parsed, signal: options.signal });
    if (path[5] === "availability") {
      if (control.delay) await control.delay;
      if (control.network) throw new Error("Network unavailable");
      if (control.failure) return Response.json({ detail: { code: "invalid_value", message: "Search rejected" } }, { status: 422 });
      return Response.json(control.rooms ?? [room]);
    }
    if (control.metadataFailure) throw new Error("Metadata unavailable");
    if (!path[4]) return Response.json({ id: path[3], name: "Test University", slug: "test", default_timezone: "America/New_York", created_at: base.created_at });
    return Response.json(control.empty ? [] : path[4] === "room-types" ? [{ ...room.room_type, workspace_id: path[3] }] : facilities.map(row => ({ ...row, workspace_id: path[3] })));
  });
  render(React.createElement(WorkspaceProvider, null, React.createElement(WorkspaceSelector), React.createElement(FindRoom)));
  if (selected) select(a);
  return { requests, control, searches: () => requests.filter(row => row.url.pathname.endsWith("/availability")) };
}
async function ready() { await screen.findByRole("button", { name: "Find available rooms" }); time("Start", "2026-10-01T09:00"); time("End", "2026-10-01T10:00"); }
test("no workspace performs no requests; initial state waits for explicit search", async t => {
  const { requests, searches } = setup(t, {}, false);
  assert.ok(screen.getByText(/Select a workspace above/)); assert.equal(requests.length, 0);
  select(a); await ready(); assert.equal(searches().length, 0);
  assert.ok(screen.getByText(/Enter when you need a room/));
  assert.equal(document.querySelector('input[type="datetime-local"]'), null);
});
test("timezone, capacity, type and ALL facilities query display human-readable results", async t => {
  const { searches } = setup(t); await ready(); fill("Minimum capacity *", "50"); fill("Room type", id);
  fireEvent.click(screen.getByLabelText("Projector")); fireEvent.click(screen.getByLabelText("Whiteboard")); search();
  await screen.findByText("1 room available");
  const url = searches()[0].url;
  assert.equal(url.pathname, `/api/workspaces/${a}/rooms/availability`);
  assert.equal(url.searchParams.get("starts_at"), "2026-10-01T13:00:00Z"); assert.equal(url.searchParams.get("ends_at"), "2026-10-01T14:00:00Z");
  assert.equal(url.searchParams.get("minimum_capacity"), "50"); assert.equal(url.searchParams.get("room_type_id"), id);
  assert.deepEqual(url.searchParams.getAll("facility_ids"), [id, other]);
  const card = screen.getByRole("article");
  for (const text of ["LT-1", "Lecture Hall", "100", "Lecture Theatre", "North Campus", "Science Block", "Ground Floor", "Projector", "Whiteboard"]) assert.ok(card.textContent.includes(text));
  fill("Minimum capacity *", "60"); assert.equal(screen.queryByRole("article"), null);
});
test("calendar dates are independent and changing a date clears stale results", async t => {
  setup(t); await ready(); search(); await screen.findByText("1 room available");
  selectCalendar("End date", "2026-10-02");
  assert.ok(screen.getByRole("button", { name: "Start date Oct 1, 2026" }));
  assert.ok(screen.getByRole("button", { name: "End date Oct 2, 2026" }));
  assert.equal(screen.queryByRole("article"), null);
  assert.equal(document.querySelector('input[placeholder="YYYY-MM-DD"]'), null);
});
test("invalid capacity, interval, missing date and DST gap never search", async t => {
  const { searches } = setup(t); await ready();
  for (const value of ["", "0", "-1", "1.5", "2147483648"]) { fill("Minimum capacity *", value); search(); assert.match(screen.getByRole("alert").textContent, /positive integer/); }
  fill("Minimum capacity *", "1");
  for (const end of ["2026-10-01T09:00", "2026-10-01T08:00"]) { time("End", end); search(); assert.match(screen.getByRole("alert").textContent, /End must be later/); }
  time("Start", "2026-03-08T02:30"); time("End", "2026-03-08T04:00"); search(); assert.ok(screen.getByRole("alert"));
  assert.equal(searches().length, 0);
});
test("repeated clock times require an occurrence choice", async t => {
  const { searches } = setup(t); await ready(); time("Start", "2026-11-01T01:30"); time("End", "2026-11-01T03:00"); search();
  assert.ok(screen.getByRole("alert")); assert.equal(searches().length, 0);
  fill("Repeated start clock time", "later"); search(); await screen.findByText("1 room available");
  assert.equal(searches()[0].url.searchParams.get("starts_at"), "2026-11-01T06:30:00Z");
});
test("loading disables search and no-results explains next step; optional filters omitted", async t => {
  let resolve; const delay = new Promise(done => { resolve = done; });
  const { searches } = setup(t, { delay, rooms: [], empty: true }); await ready();
  assert.ok(screen.getByText(/No facilities have been configured/)); search();
  assert.equal(screen.getByRole("button", { name: "Searching…" }).disabled, true);
  await act(async () => { resolve(); }); await screen.findByText("0 rooms available");
  assert.ok(screen.getByText(/No rooms match this interval/));
  assert.equal(searches()[0].url.searchParams.has("room_type_id"), false); assert.deepEqual(searches()[0].url.searchParams.getAll("facility_ids"), []);
});
test("API and network errors retain criteria and allow retry", async t => {
  const { control } = setup(t, { failure: true }); await ready(); search(); await screen.findByRole("alert");
  assert.match(screen.getByRole("alert").textContent, /Search rejected/); assert.equal(document.querySelector('input[name="starts_at"]').value.slice(0, 10), "2026-10-01");
  control.failure = false; control.network = true; search(); await screen.findByRole("alert");
  control.network = false; search(); await screen.findByText("1 room available");
});
test("metadata error has retry", async t => {
  const { control } = setup(t, { metadataFailure: true }); await screen.findByRole("alert");
  control.metadataFailure = false; fireEvent.click(screen.getByRole("button", { name: "Try again" })); await ready();
});
test("workspace change clears results and inputs and ignores an old search response", async t => {
  const { control, searches } = setup(t); await ready(); search(); await screen.findByText("1 room available");
  select(b); await screen.findByRole("button", { name: "Find available rooms" });
  assert.equal(screen.queryByRole("article"), null); assert.equal(document.querySelector('input[name="starts_at"]').value, "");
  select(a); await ready(); let resolve; control.delay = new Promise(done => { resolve = done; }); search();
  select(b); await screen.findByRole("button", { name: "Find available rooms" }); assert.equal(searches().at(-1).signal.aborted, true);
  await act(async () => { resolve(); }); assert.equal(screen.queryByRole("article"), null);
});
test("availability client loads all pages and rejects a foreign workspace", async t => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const offsets = []; let foreign = false;
  t.mock.method(globalThis, "fetch", async url => {
    const offset = new URL(url).searchParams.get("offset"); offsets.push(offset);
    return Response.json(foreign ? [{ ...room, workspace_id: b }] : offset === "0" ? Array.from({ length: 200 }, () => room) : [room]);
  });
  const query = { starts_at: "2026-10-01T13:00:00Z", ends_at: "2026-10-01T14:00:00Z", minimum_capacity: 1, facility_ids: [] };
  assert.equal((await findAvailableRooms(a, query, new AbortController().signal)).length, 201); assert.deepEqual(offsets, ["0", "200"]);
  foreign = true; await assert.rejects(findAvailableRooms(a, query, new AbortController().signal));
});
