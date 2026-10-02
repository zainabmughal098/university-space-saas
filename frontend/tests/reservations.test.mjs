import { JSDOM } from "jsdom";
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";
const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
for (const key of ["window", "document", "HTMLElement", "HTMLInputElement", "MutationObserver", "FormData"]) globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.requestAnimationFrame = callback => { callback(); return 0; };
// jsdom has no top-layer dialog implementation. Exercise component state and labels.
dom.window.HTMLDialogElement.prototype.showModal = function () { this.setAttribute("open", ""); };
dom.window.HTMLDialogElement.prototype.close = function () { this.removeAttribute("open"); };
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { render, screen, fireEvent, cleanup, within, act } = await import("@testing-library/react");
const { default: Reservations } = await import("../src/features/reservations.tsx");
const { CalendarDatePicker } = await import("../src/components/calendar-date-picker.tsx");
const { listWorkspaceMembers } = await import("../src/lib/api.ts");
const { WorkspaceProvider, WorkspaceSelector } = await import("../src/components/workspace.tsx");
afterEach(cleanup);
const a = "11111111-1111-1111-1111-111111111111", b = "22222222-2222-2222-2222-222222222222", id = "33333333-3333-3333-3333-333333333333";
const base = { id, workspace_id: a, created_at: "2026-10-01T12:00:00Z", is_active: true };
const reservation = { ...base, room_id: id, requested_by_user_id: id, title: "Planning meeting", description: "Term planning", starts_at: "2026-10-05T13:00:00Z", ends_at: "2026-10-05T14:00:00Z", expected_attendees: 20, status: "pending", reviewed_by_user_id: null, reviewed_at: null, rejection_reason: null, updated_at: base.created_at };
const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
function selectWorkspace(value) { fill("Workspace UUID", value); fireEvent.click(screen.getByRole("button", { name: "Use workspace" })); }
function setup(t, entries = [], control = {}, selected = true) {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const data = structuredClone({ reservations: entries, members: control.members ?? [{ user_id: id, display_name: "Sara Ahmed", email: "sara@example.test", role: "member", is_active: true }, { user_id: b, display_name: "Inactive member", email: "inactive@example.test", role: "viewer", is_active: false }], rooms: [{ ...base, name: "Lecture Hall", code: "LT-1", capacity: 100, floor_id: id, room_type_id: id }], floors: [{ ...base, name: "Ground", building_id: id, floor_number: 0 }], buildings: [{ ...base, name: "Science", campus_id: id, code: "SC" }], campuses: [{ ...base, name: "North", code: "N", address: null }] });
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    const path = new URL(url).pathname.split("/"), workspace = path[3], resource = path[4], method = options.method ?? "GET";
    requests.push({ workspace, resource, method, action: path[6], signal: options.signal, body: options.body && JSON.parse(options.body) });
    if (control.memberDelay && resource === "members" && workspace === a) await control.memberDelay;
    if (control.loadDelay && workspace === a && method === "GET") await control.loadDelay;
    if (control.loadError && method === "GET") throw new Error("Offline");
    if (!resource) return Response.json({ id: workspace, name: "Test University", slug: "test", default_timezone: control.zone ?? "America/New_York", created_at: base.created_at });
    if (method === "GET") return Response.json(workspace === a ? data[resource] : []);
    if (control.delay) await control.delay;
    if (control.network) throw new Error("Offline");
    if (control.error) return Response.json({ detail: control.error }, { status: 409 });
    if (!path[5]) { const row = { ...reservation, ...JSON.parse(options.body), id: crypto.randomUUID() }; data.reservations.push(row); return Response.json(row, { status: 201 }); }
    const row = data.reservations.find(row => row.id === path[5]);
    row.status = { approve: "approved", reject: "rejected", cancel: "cancelled" }[path[6]];
    if (options.body) Object.assign(row, JSON.parse(options.body), { reviewed_at: base.created_at });
    return Response.json(row);
  });
  render(React.createElement(WorkspaceProvider, null, React.createElement(WorkspaceSelector), React.createElement(Reservations)));
  if (selected) selectWorkspace(a);
  return { data, requests, control, writes: () => requests.filter(row => row.method !== "GET") };
}
const ready = () => screen.findByRole("heading", { name: "Room reservations" });
const table = () => screen.getByRole("region", { name: "Reservations list" });
function chooseDay(day) {
  const dialog = screen.getByRole("dialog");
  const months = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];
  const [shortMonth, , year] = day.split(" ");
  const target = Number(year) * 12 + months.findIndex(month => month.startsWith(shortMonth));
  for (let attempt = 0; attempt < 240; attempt++) {
    const [month, year] = dialog.querySelector(".calendar-month strong").textContent.split(" ");
    const current = Number(year) * 12 + months.indexOf(month);
    if (current === target) break;
    fireEvent.click(within(dialog).getByRole("button", { name: current < target ? "Next month" : "Previous month" }));
  }
  fireEvent.click(within(dialog).getByRole("button", { name: day }));
}
function date(label, day = "Oct 5, 2026") { fireEvent.click(within(screen.getByRole("region", { name: "Reservation panel" })).getByRole("button", { name: new RegExp(`^${label} date `) })); chooseDay(day); }
function clock(label, hour, minute = "00", period = "AM") { fill(`${label} hour`, hour); fill(`${label} minute`, minute); fill(`${label} AM/PM`, period); }
async function openCreate() { await ready(); fireEvent.click(screen.getByRole("button", { name: "Create reservation" })); }
function values() { fill("Room *", id); fill("Title *", "Workshop"); fill("Expected attendees *", "30"); fill("Development requester *", id); date("Start"); date("End"); clock("Start", "9"); clock("End", "10"); }
const submit = name => fireEvent.submit(screen.getByRole("button", { name }).closest("form"));

test("calendar opens, navigates months, selects friendly date, highlights selection and supports arrows", () => {
  function Harness() { const [value, setValue] = React.useState("2026-10-05"); return React.createElement(CalendarDatePicker, { label: "Test date", today: "2026-10-01", value, onChange: setValue }); }
  render(React.createElement(Harness)); fireEvent.click(screen.getByRole("button", { name: "Test date Oct 5, 2026" }));
  const dialog = screen.getByRole("dialog"); assert.ok(within(dialog).getByText("October 2026"));
  assert.equal(within(dialog).getByRole("button", { name: "Oct 5, 2026" }).getAttribute("aria-pressed"), "true");
  assert.equal(within(dialog).getByRole("button", { name: "Oct 1, 2026" }).getAttribute("aria-current"), "date");
  fireEvent.click(within(dialog).getByRole("button", { name: "Next month" })); assert.ok(within(dialog).getByText("November 2026"));
  fireEvent.click(within(dialog).getByRole("button", { name: "Previous month" }));
  fireEvent.keyDown(within(dialog).getByRole("button", { name: "Oct 5, 2026" }), { key: "ArrowRight" });
  assert.equal(within(dialog).getByRole("button", { name: "Oct 6, 2026" }).tabIndex, 0);
  fireEvent.click(within(dialog).getByRole("button", { name: "Oct 6, 2026" })); assert.equal(screen.queryByRole("dialog"), null);
  assert.equal(document.activeElement, screen.getByRole("button", { name: "Test date Oct 6, 2026" }));
  fireEvent.click(screen.getByRole("button", { name: "Test date Oct 6, 2026" }));
  fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Today" }));
  assert.ok(screen.getByRole("button", { name: "Test date Oct 1, 2026" }));
  assert.equal(screen.queryByRole("dialog"), null);
});
test("no workspace, loading, and empty reservation states", async t => {
  let resolve; const { requests } = setup(t, [], { loadDelay: new Promise(done => { resolve = done; }) }, false);
  assert.ok(screen.getByText(/Select a workspace above/)); assert.equal(requests.length, 0);
  selectWorkspace(a); assert.ok(screen.getByText("Loading reservations…")); await act(async () => resolve()); await ready(); assert.ok(screen.getByText(/No reservations yet/));
});
test("list, summaries, status/room/calendar filters and details are readable", async t => {
  setup(t, [reservation, { ...reservation, id: b, title: "Approved workshop", status: "approved", reviewed_by_user_id: id, reviewed_at: base.created_at }]); await ready();
  assert.match(table().textContent, /LT-1.*Lecture Hall.*North.*Science.*Ground/); assert.match(table().textContent, /9:00 AM/);
  assert.match(screen.getByLabelText("Reservation summary").textContent, /2Total1Pending1Approved0Rejected0Cancelled/);
  fill("Status", "approved"); assert.equal(within(table()).queryByText("Planning meeting"), null);
  fill("Room", id); assert.ok(within(table()).getByText("Approved workshop"));
  fireEvent.click(screen.getByRole("button", { name: "Start date filter Select date" })); chooseDay("Oct 6, 2026"); assert.ok(screen.getByText(/No reservations match/));
  fireEvent.click(screen.getByRole("button", { name: "Clear start date filter" })); fireEvent.click(within(table()).getByRole("button", { name: "View" }));
  assert.ok(within(screen.getByRole("region", { name: "Reservation panel" })).getByText("Requester")); assert.ok(screen.getByText("Term planning")); assert.ok(screen.getByText("Reviewed"));
});
test("calendar dates are independent and creation uses exact timezone-aware contract", async t => {
  const { writes } = setup(t); await openCreate(); values();
  date("End", "Oct 6, 2026"); assert.ok(screen.getByRole("button", { name: "Start date Oct 5, 2026" })); assert.ok(screen.getByRole("button", { name: "End date Oct 6, 2026" }));
  date("End"); submit("Create request"); await screen.findByText("Reservation request created.");
  assert.deepEqual(writes()[0].body, { room_id: id, requested_by_user_id: id, title: "Workshop", description: null, expected_attendees: 30, starts_at: "2026-10-05T13:00:00Z", ends_at: "2026-10-05T14:00:00Z" });
  assert.equal(writes()[0].workspace, a); assert.match(screen.getByLabelText("Reservation summary").textContent, /1Total1Pending/);
});
test("missing required values, attendee validation and invalid interval do not write", async t => {
  const { writes } = setup(t); await openCreate(); submit("Create request"); assert.ok(screen.getByRole("alert"));
  fill("Development requester *", id); submit("Create request"); assert.match(screen.getByRole("alert").textContent, /Title is required/);
  fill("Title *", "Test"); submit("Create request"); assert.match(screen.getByRole("alert").textContent, /Choose an active room/);
  values(); for (const value of ["0", "-1", "1.5", "2147483648"]) { fill("Expected attendees *", value); submit("Create request"); assert.match(screen.getByRole("alert").textContent, /positive integer/); }
  fill("Expected attendees *", "20"); clock("End", "9"); submit("Create request"); assert.match(screen.getByRole("alert").textContent, /End must be later/); assert.equal(writes().length, 0);
});
for (const [state, action, expected] of [["pending", "Approve", "approved"], ["pending", "Reject", "rejected"], ["pending", "Cancel", "cancelled"], ["approved", "Cancel", "cancelled"]]) {
  test(`${action} ${state} requires confirmation and updates actions/counts only after success`, async t => {
    const { writes } = setup(t, [{ ...reservation, status: state }]); await ready(); fireEvent.click(within(table()).getByRole("button", { name: action })); assert.equal(writes().length, 0);
    if (action !== "Cancel") fill("Development reviewer *", id);
    if (action === "Reject") fill("Rejection reason (optional)", "Not suitable");
    submit(`Confirm ${action.toLowerCase()}`); await screen.findByText(`Reservation ${expected}.`);
    assert.equal(writes()[0].action, action.toLowerCase());
    assert.deepEqual(writes()[0].body, action === "Cancel" ? undefined : action === "Reject" ? { reviewed_by_user_id: id, rejection_reason: "Not suitable" } : { reviewed_by_user_id: id });
    assert.ok(within(table()).getByText(expected[0].toUpperCase() + expected.slice(1))); assert.equal(within(table()).queryByRole("button", { name: "Approve" }), null);
  });
}
test("rejected and cancelled records have details only", async t => {
  setup(t, [{ ...reservation, status: "rejected" }, { ...reservation, id: b, status: "cancelled" }]); await ready(); assert.equal(within(table()).getAllByRole("button").length, 2);
  assert.equal(within(table()).queryByRole("button", { name: "Cancel" }), null);
});
test("backend class conflicts are readable and preserve create form", async t => {
  const { control } = setup(t, [], { error: { code: "schedule_conflict", message: "Room conflicts with a scheduled class.", conflicts: [{ schedule_entry_id: id, room_id: id, starts_at: reservation.starts_at, ends_at: reservation.ends_at }] } });
  await openCreate(); values(); submit("Create request"); await screen.findByRole("alert"); assert.match(screen.getByRole("alert").textContent, /Scheduled class.*Lecture Hall.*9:00 AM/); assert.equal(screen.getByLabelText("Title *").value, "Workshop");
  control.error = null; submit("Create request"); await screen.findByText("Reservation request created.");
});
test("approval conflicts and invalid transitions retain pending data; duplicate requests blocked", async t => {
  let resolve; const { control, writes } = setup(t, [reservation], { delay: new Promise(done => { resolve = done; }), error: { code: "reservation_conflict", message: "Room is occupied.", reservation_conflicts: [{ reservation_id: b, room_id: id, starts_at: reservation.starts_at, ends_at: reservation.ends_at }] } });
  await ready(); fireEvent.click(within(table()).getByRole("button", { name: "Approve" })); fill("Development reviewer *", id); submit("Confirm approve");
  const button = screen.getByRole("button", { name: "Saving…" }); assert.equal(button.disabled, true); fireEvent.submit(button.closest("form")); assert.equal(writes().length, 1);
  await act(async () => resolve()); await screen.findByRole("alert"); assert.match(screen.getByRole("alert").textContent, /Approved reservation.*Lecture Hall/); assert.ok(within(table()).getByText("Pending"));
  control.error = { code: "invalid_state_transition", message: "Cannot approve a cancelled reservation." }; submit("Confirm approve"); await screen.findByText("Cannot approve a cancelled reservation.");
});
test("load and mutation network failures allow refresh/retry without false success", async t => {
  const { control } = setup(t, [], { loadError: true }); await screen.findByRole("alert"); control.loadError = false; fireEvent.click(screen.getByRole("button", { name: "Try again" })); await openCreate(); values(); control.network = true; submit("Create request"); await screen.findByRole("alert"); assert.match(screen.getByRole("alert").textContent, /Refresh/); assert.equal(screen.queryByText("Reservation request created."), null);
});
test("workspace switch clears filters/panel and ignores delayed mutation response", async t => {
  let resolve; const { writes } = setup(t, [reservation], { delay: new Promise(done => { resolve = done; }) }); await ready(); fill("Status", "pending"); fireEvent.click(within(table()).getByRole("button", { name: "Cancel" })); submit("Confirm cancel");
  selectWorkspace(b); await ready(); assert.equal(writes()[0].signal.aborted, true); assert.equal(screen.getByLabelText("Status").value, ""); assert.equal(screen.queryByRole("region", { name: "Reservation panel" }), null);
  await act(async () => resolve()); assert.equal(screen.queryByText("Planning meeting"), null); assert.ok(screen.getByText(/No reservations yet/));
});
test("missing calendar dates and nonexistent DST times cannot be submitted", async t => {
  const { writes } = setup(t); await openCreate();
  fill("Room *", id); fill("Title *", "DST test"); fill("Expected attendees *", "10"); fill("Development requester *", id); clock("Start", "2", "30"); clock("End", "4");
  submit("Create request"); assert.match(screen.getByRole("alert").textContent, /required/);
  date("Start", "Mar 8, 2026"); date("End", "Mar 8, 2026"); submit("Create request"); assert.match(screen.getByRole("alert").textContent, /does not exist/); assert.equal(writes().length, 0);
});
test("ambiguous reservation times require an explicit occurrence", async t => {
  const { writes } = setup(t); await openCreate();
  fill("Room *", id); fill("Title *", "DST test"); fill("Expected attendees *", "10"); fill("Development requester *", id);
  date("Start", "Nov 1, 2026"); date("End", "Nov 1, 2026"); clock("Start", "1", "30"); clock("End", "3"); submit("Create request");
  assert.match(screen.getByRole("alert").textContent, /occurs twice/); assert.equal(writes().length, 0); fill("Repeated start clock time", "later"); submit("Create request"); await screen.findByText("Reservation request created.");
  assert.equal(writes()[0].body.starts_at, "2026-11-01T06:30:00Z");
});
test("members load before identity controls; options show only active named members", async t => {
  let resolve;
  setup(t, [], { memberDelay: new Promise(done => { resolve = done; }) });
  assert.ok(screen.getByText("Loading reservations…"));
  assert.equal(screen.queryByRole("button", { name: "Create reservation" }), null);
  await act(async () => resolve()); await openCreate();
  const select = screen.getByLabelText("Development requester *");
  assert.equal(select.value, "");
  assert.ok(within(select).getByRole("option", { name: "Sara Ahmed — sara@example.test (member)" }));
  assert.equal(within(select).queryByRole("option", { name: /Inactive member/ }), null);
  assert.equal(document.querySelector('input[name="requested_by_user_id"]'), null);
});
for (const members of [[], [{ user_id: id, display_name: "Inactive", email: "inactive@example.test", role: "member", is_active: false }]]) {
  test(`no active members (${members.length} records) blocks creation/review but permits cancellation`, async t => {
    setup(t, [reservation], { members }); await ready();
    assert.ok(screen.getByText(/No active workspace members are available/));
    for (const name of ["Create reservation", "Approve", "Reject"]) assert.equal(screen.getByRole("button", { name }).disabled, true);
    assert.equal(screen.getByRole("button", { name: "Cancel" }).disabled, false);
    assert.equal(document.querySelector('input[name="requested_by_user_id"]'), null);
  });
}
test("workspace switches reset requester and reviewer selections", async t => {
  setup(t, [reservation]); await openCreate(); fill("Development requester *", id);
  selectWorkspace(b); await ready(); selectWorkspace(a); await openCreate();
  assert.equal(screen.getByLabelText("Development requester *").value, "");
  fireEvent.click(screen.getByRole("button", { name: "Back" }));
  fireEvent.click(within(table()).getByRole("button", { name: "Approve" })); fill("Development reviewer *", id);
  assert.equal(screen.queryByRole("option", { name: /Inactive member/ }), null);
  selectWorkspace(b); await ready(); selectWorkspace(a); await ready();
  fireEvent.click(within(table()).getByRole("button", { name: "Reject" }));
  assert.equal(screen.getByLabelText("Development reviewer *").value, "");
});
test("late member responses from the previous workspace are ignored", async t => {
  let resolve; const { requests } = setup(t, [], { memberDelay: new Promise(done => { resolve = done; }) });
  selectWorkspace(b); await ready();
  assert.equal(requests.find(row => row.resource === "members" && row.workspace === a).signal.aborted, true);
  await act(async () => resolve());
  assert.ok(screen.getByText(/No active workspace members are available/));
  assert.equal(screen.queryByText(/Sara Ahmed/), null);
});
test("member client paginates and validates the minimal response", async t => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const row = { user_id: id, display_name: "Member", email: "member@example.test", role: "admin", is_active: true };
  const offsets = []; let malformed = false;
  t.mock.method(globalThis, "fetch", async url => {
    const parsed = new URL(url); assert.equal(parsed.pathname, `/api/workspaces/${a}/members`);
    const offset = parsed.searchParams.get("offset"); offsets.push(offset);
    return Response.json(malformed ? [{ user_id: id }] : offset === "0" ? Array.from({ length: 200 }, () => row) : [row]);
  });
  assert.equal((await listWorkspaceMembers(a, new AbortController().signal)).length, 201); assert.deepEqual(offsets, ["0", "200"]);
  malformed = true; await assert.rejects(listWorkspaceMembers(a, new AbortController().signal), /invalid member response/);
});
