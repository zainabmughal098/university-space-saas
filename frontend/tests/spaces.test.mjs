import { JSDOM } from "jsdom";
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
for (const key of ["window", "document", "HTMLElement", "HTMLInputElement", "MutationObserver", "FormData"]) globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { render, screen, fireEvent, waitFor, cleanup } = await import("@testing-library/react");
const { default: Spaces } = await import("../src/features/spaces.tsx");
const { WorkspaceProvider, WorkspaceSelector } = await import("../src/components/workspace.tsx");
afterEach(cleanup);

const a = "11111111-1111-1111-1111-111111111111";
const b = "22222222-2222-2222-2222-222222222222";
const base = { id: "33333333-3333-3333-3333-333333333333", workspace_id: a, created_at: "2026-01-01T00:00:00Z", is_active: true };
function setup(t, initial = {}, fail = false) {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const data = { campuses: [], buildings: [], floors: [], rooms: [], "room-types": [], facilities: [], ...initial };
  const requests = [];
  const assigned = [];
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    const path = new URL(url).pathname.split("/");
    const workspace = path[3], resource = path[4];
    const method = options.method ?? "GET";
    requests.push({ workspace, resource, method, body: options.body && JSON.parse(options.body) });
    if (fail) return Response.json({ detail: { message: "Unable to load this workspace." } }, { status: 503 });
    if (path[6] === "facilities") {
      if (method === "GET") return Response.json(assigned);
      if (method === "POST") { assigned.push(data.facilities.find(row => row.id === path[7])); return Response.json({ workspace_id: workspace, room_id: path[5], facility_id: path[7] }, { status: 201 }); }
      assigned.splice(assigned.findIndex(row => row.id === path[7]), 1); return new Response(null, { status: 204 });
    }
    if (method === "PATCH" || path[6] === "deactivate") {
      const row = data[resource].find(row => row.id === path[5]);
      Object.assign(row, method === "PATCH" ? JSON.parse(options.body) : { is_active: false });
      return Response.json(row);
    }
    if (method === "POST" && path.length === 5) {
      const row = { ...base, ...JSON.parse(options.body), workspace_id: workspace };
      data[resource].push(row); return Response.json(row, { status: 201 });
    }
    return Response.json(workspace === a ? data[resource] : []);
  });
  render(React.createElement(WorkspaceProvider, null, React.createElement(WorkspaceSelector), React.createElement(Spaces)));
  selectWorkspace(a);
  return { requests, data };
}
function selectWorkspace(id) {
  fireEvent.change(screen.getByLabelText("Workspace UUID"), { target: { value: id } });
  fireEvent.click(screen.getByRole("button", { name: "Use workspace" }));
}
test("empty state and no parent options guide setup", async t => {
  setup(t);
  await screen.findByText(/No campuses yet/);
  fireEvent.click(screen.getByRole("button", { name: "Buildings" }));
  fireEvent.click(screen.getByRole("button", { name: "Create new" }));
  assert.ok(screen.getByText("Create campuses first."));
  assert.equal(screen.getByRole("button", { name: "Save changes" }).disabled, true);
});
test("building creation uses human-readable campus selector and refreshes rows", async t => {
  const { requests } = setup(t, { campuses: [{ ...base, name: "North campus", code: "N", address: "North Road" }] });
  await screen.findByText("North campus");
  assert.ok(screen.getByText("North Road"));
  fireEvent.click(screen.getByRole("button", { name: "Buildings" }));
  fireEvent.click(screen.getByRole("button", { name: "Create new" }));
  fireEvent.change(screen.getByLabelText("Name *"), { target: { value: "Science Hall" } });
  fireEvent.change(screen.getByLabelText("Code *"), { target: { value: "SCI" } });
  const parent = screen.getByLabelText("Campus *");
  assert.ok(screen.getByRole("option", { name: "North campus (N)" }));
  fireEvent.change(parent, { target: { value: base.id } });
  fireEvent.submit(screen.getByRole("button", { name: "Save changes" }).closest("form"));
  await screen.findByText("Science Hall");
  assert.deepEqual(requests.find(item => item.method === "POST").body, { name: "Science Hall", code: "SCI", campus_id: base.id });
  assert.ok(screen.getByText("Saved successfully."));
});
test("room form rejects invalid capacity before sending a mutation", async t => {
  const { requests } = setup(t, {
    campuses: [{ ...base, name: "North", code: "N", address: null }],
    buildings: [{ ...base, name: "Science", code: "S", campus_id: base.id }],
    floors: [{ ...base, name: "Ground", floor_number: 0, building_id: base.id }],
    "room-types": [{ ...base, name: "Seminar", description: null }],
  });
  await screen.findByText("North");
  fireEvent.click(screen.getByRole("button", { name: "Rooms" }));
  fireEvent.click(screen.getByRole("button", { name: "Create new" }));
  for (const [label, value] of [["Name *", "Room one"], ["Code *", "R1"], ["Capacity *", "0"], ["Floor *", base.id], ["Room type *", base.id]]) fireEvent.change(screen.getByLabelText(label), { target: { value } });
  assert.ok(screen.getByRole("option", { name: "North (N) / Science (S) / Ground" }));
  fireEvent.submit(screen.getByRole("button", { name: "Save changes" }).closest("form"));
  assert.match(screen.getByRole("alert").textContent, /Capacity must be an integer/);
  assert.equal(requests.filter(item => item.method !== "GET").length, 0);
});
test("workspace switch clears old rows and uses only the new workspace", async t => {
  const { requests } = setup(t, { campuses: [{ ...base, name: "Private North", code: "N", address: null }] });
  await screen.findByText("Private North");
  selectWorkspace(b);
  assert.equal(screen.queryByText("Private North"), null);
  await screen.findByText(/No campuses yet/);
  assert.equal(requests.at(-1).workspace, b);
});
test("API errors are visible and retry reloads data", async t => {
  const { requests } = setup(t, {}, true);
  await screen.findByRole("alert");
  assert.ok(screen.getByText("Unable to load this workspace."));
  const count = requests.length;
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await waitFor(() => assert.ok(requests.length > count));
});

test("campus edits clear nullable fields and active actions refresh status", async t => {
  const { requests } = setup(t, { campuses: [{ ...base, name: "North campus", code: "N", address: "Old Road" }] });
  await screen.findByText("North campus");
  fireEvent.click(screen.getByRole("button", { name: "Edit North campus" }));
  fireEvent.change(screen.getByLabelText("Address"), { target: { value: "" } });
  fireEvent.submit(screen.getByRole("button", { name: "Save changes" }).closest("form"));
  await screen.findByText("North campus");
  assert.equal(requests.find(row => row.method === "PATCH").body.address, null);
  fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
  await screen.findByRole("button", { name: "Reactivate" });
  fireEvent.click(screen.getByRole("button", { name: "Reactivate" }));
  await screen.findByRole("button", { name: "Deactivate" });
  assert.equal(requests.filter(row => row.method === "DELETE").length, 0);
});

test("room facilities assign and remove using named selectors", async t => {
  const { requests } = setup(t, {
    rooms: [{ ...base, name: "Meeting room", code: "M", capacity: 10, floor_id: base.id, room_type_id: base.id }],
    facilities: [{ ...base, name: "Projector", description: null }],
  });
  await screen.findByText(/No campuses yet/);
  fireEvent.click(screen.getByRole("button", { name: "Rooms" }));
  fireEvent.click(screen.getByRole("button", { name: "Facilities for Meeting room" }));
  await screen.findByText("No facilities assigned.");
  fireEvent.change(screen.getByLabelText("Facility"), { target: { value: base.id } });
  fireEvent.submit(screen.getByRole("button", { name: "Assign facility" }).closest("form"));
  await screen.findByRole("button", { name: "Remove Projector" });
  fireEvent.click(screen.getByRole("button", { name: "Remove Projector" }));
  await screen.findByText("No facilities assigned.");
  assert.ok(requests.some(row => row.method === "DELETE"));
});
