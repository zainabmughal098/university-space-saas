import { JSDOM } from "jsdom";
import { test, afterEach } from "node:test";
import assert from "node:assert/strict";
import React from "react";

const dom = new JSDOM("<!doctype html><html><body></body></html>", { url: "http://localhost:3000" });
for (const key of ["window", "document", "HTMLElement", "HTMLInputElement", "MutationObserver", "FormData"]) globalThis[key] = dom.window[key];
Object.defineProperty(globalThis, "navigator", { value: dom.window.navigator, configurable: true });
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const { render, screen, fireEvent, cleanup } = await import("@testing-library/react");
const { default: Academic } = await import("../src/features/academic.tsx");
const { WorkspaceProvider, WorkspaceSelector } = await import("../src/components/workspace.tsx");
afterEach(cleanup);

const a = "11111111-1111-1111-1111-111111111111";
const b = "22222222-2222-2222-2222-222222222222";
const base = { id: "33333333-3333-3333-3333-333333333333", workspace_id: a, created_at: "2026-01-01T00:00:00Z", is_active: true };
function setup(t, initial = {}, control = {}) {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const data = structuredClone({ departments: [], faculty: [], courses: [], sections: [], ...initial });
  const requests = [];
  t.mock.method(globalThis, "fetch", async (url, options = {}) => {
    const path = new URL(url).pathname.split("/");
    const workspace = path[3], resource = path[4];
    const method = options.method ?? "GET";
    requests.push({ workspace, resource, method, body: options.body && JSON.parse(options.body) });
    if (control.fail || (control.failWrite && method !== "GET")) return Response.json({ detail: { message: "Unable to load this workspace." } }, { status: 503 });
    if (method === "PATCH" || path[6] === "deactivate") {
      const row = data[resource].find(row => row.id === path[5]);
      Object.assign(row, method === "PATCH" ? JSON.parse(options.body) : { is_active: false });
      return Response.json(row);
    }
    if (method === "POST" && path.length === 5) {
      const row = { ...base, id: crypto.randomUUID(), ...JSON.parse(options.body), workspace_id: workspace };
      data[resource].push(row); return Response.json(row, { status: 201 });
    }
    return Response.json(workspace === a ? data[resource] : []);
  });
  render(React.createElement(WorkspaceProvider, null, React.createElement(WorkspaceSelector), React.createElement(Academic)));
  selectWorkspace(a);
  return { requests, data, control };
}
function selectWorkspace(id) {
  fireEvent.change(screen.getByLabelText("Workspace UUID"), { target: { value: id } });
  fireEvent.click(screen.getByRole("button", { name: "Use workspace" }));
}
const department = { ...base, name: "Computing", code: "CS" };
const course = { ...base, id: "44444444-4444-4444-4444-444444444444", name: "Algorithms", code: "CS101", department_id: base.id };
const faculty = { ...base, id: "55555555-5555-5555-5555-555555555555", name: "Alex Reed", email: "alex@example.test", department_id: base.id };
const section = { ...base, id: "66666666-6666-6666-6666-666666666666", name: "Section A", course_id: course.id, student_count: 20 };
const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } });
const save = () => fireEvent.submit(screen.getByRole("button", { name: "Save changes" }).closest("form"));
function create(tab) {
  fireEvent.click(screen.getByRole("button", { name: tab }));
  fireEvent.click(screen.getByRole("button", { name: "Create new" }));
}

test("academic empty state, counts, and missing active parents", async t => {
  setup(t);
  await screen.findByText(/No departments yet/);
  for (const label of ["departments", "faculty", "courses", "sections"]) {
    assert.equal(screen.getByText(`Total ${label}`).parentElement.querySelector("strong").textContent, "0");
    assert.equal(screen.getByText(`Active ${label}`).parentElement.querySelector("strong").textContent, "0");
  }
  create("Faculty");
  assert.ok(screen.getByText("Create or reactivate departments first."));
  assert.equal(screen.getByRole("button", { name: "Save changes" }).disabled, true);
});

test("department rendering and creation refresh total and active counts", async t => {
  const { requests } = setup(t, { departments: [{ ...department, is_active: false }] });
  await screen.findByText("Computing");
  assert.ok(screen.getByText("CS"));
  assert.equal(screen.getByText("Active departments").parentElement.querySelector("strong").textContent, "0");
  create("Departments");
  fill("Name *", "Mathematics"); fill("Code *", "MATH"); save();
  await screen.findByText("Mathematics");
  assert.deepEqual(requests.find(row => row.method === "POST").body, { name: "Mathematics", code: "MATH" });
  assert.equal(screen.getByText("Total departments").parentElement.querySelector("strong").textContent, "2");
  assert.equal(screen.getByText("Active departments").parentElement.querySelector("strong").textContent, "1");
});

for (const [tab, resource, name, inputs, parentLabel, parentId, expectedLabel] of [
  ["Faculty", "faculty", "Alex", [["Email *", "alex@university.edu"]], "Department *", base.id, "Computing (CS)"],
  ["Courses", "courses", "Networks", [["Code *", "NET"]], "Department *", base.id, "Computing (CS)"],
  ["Sections", "sections", "Group B", [["Student count *", "35"]], "Course *", course.id, "Computing (CS) / Algorithms (CS101)"],
]) test(`${tab} creation uses named parents and backend field names`, async t => {
  const { requests } = setup(t, { departments: [department], courses: [course] });
  await screen.findByText("Computing");
  create(tab); fill("Name *", name);
  assert.ok(screen.getByRole("option", { name: expectedLabel }));
  for (const [label, value] of inputs) fill(label, value);
  fill(parentLabel, parentId); save();
  await screen.findByText(name);
  const request = requests.find(row => row.method === "POST");
  assert.equal(request.workspace, a); assert.equal(request.resource, resource);
  assert.equal(request.body[resource === "sections" ? "course_id" : "department_id"], parentId);
  assert.equal(Object.hasOwn(request.body, "workspace_id"), false);
  if (resource === "sections") assert.equal(request.body.student_count, 35);
});

test("invalid faculty emails preserve input and do not call API", async t => {
  const { requests } = setup(t, { departments: [department] });
  await screen.findByText("Computing"); create("Faculty");
  fill("Name *", "Alex"); fill("Department *", base.id);
  for (const value of ["invalid", "a@@university.edu", "a b@university.edu"]) {
    fill("Email *", value); save(); assert.match(screen.getByRole("alert").textContent, /valid email/);
  }
  assert.equal(screen.getByLabelText("Name *").value, "Alex");
  assert.equal(requests.filter(row => row.method !== "GET").length, 0);
});

test("sections reject zero, negative, fractional, missing and oversized student counts", async t => {
  const { requests } = setup(t, { departments: [department], courses: [course] });
  await screen.findByText("Computing"); create("Sections");
  fill("Name *", "Group"); fill("Course *", course.id);
  for (const value of ["0", "-1", "1.5", "", "2147483648"]) {
    fill("Student count *", value); save(); assert.match(screen.getByRole("alert").textContent, /Student count/);
  }
  assert.equal(requests.filter(row => row.method !== "GET").length, 0);
});

for (const [tab, resource, record] of [["Departments", "departments", department], ["Faculty", "faculty", faculty], ["Courses", "courses", course], ["Sections", "sections", section]]) {
  test(`${tab} edit and deactivate/reactivate preserve records`, async t => {
    const initial = { departments: [department], faculty: [faculty], courses: [course], sections: [section] };
    const { requests } = setup(t, initial);
    await screen.findByText("Computing");
    fireEvent.click(screen.getByRole("button", { name: tab }));
    fireEvent.click(screen.getByRole("button", { name: `Edit ${record.name}` }));
    fill("Name *", "Updated name"); save(); await screen.findByText("Updated name");
    assert.equal(requests.find(row => row.method === "PATCH").resource, resource);
    fireEvent.click(screen.getByRole("button", { name: "Deactivate" }));
    await screen.findByRole("button", { name: "Reactivate" });
    fireEvent.click(screen.getByRole("button", { name: "Reactivate" }));
    await screen.findByRole("button", { name: "Deactivate" });
    assert.equal(requests.filter(row => row.method === "DELETE").length, 0);
  });
}

test("inactive parents are omitted for creation but retained and labeled on edit", async t => {
  setup(t, { departments: [{ ...department, is_active: false }], faculty: [faculty], courses: [{ ...course, is_active: false }], sections: [section] });
  await screen.findByText("Computing"); create("Faculty");
  assert.equal(screen.queryByRole("option", { name: /Computing/ }), null);
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "Edit Alex Reed" }));
  assert.equal(screen.getByLabelText("Department *").value, base.id);
  assert.ok(screen.getByRole("option", { name: /Computing.*inactive/ }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "Sections" }));
  assert.ok(screen.getByText(/Computing.*Algorithms/));
  fireEvent.click(screen.getByRole("button", { name: "Edit Section A" }));
  assert.equal(screen.getByLabelText("Course *").value, course.id);
  assert.ok(screen.getByRole("option", { name: /Algorithms.*inactive/ }));
});

test("workspace change clears previous records and forms", async t => {
  const { requests } = setup(t, { departments: [department] });
  await screen.findByText("Computing");
  fireEvent.click(screen.getByRole("button", { name: "Edit Computing" }));
  selectWorkspace(b);
  assert.equal(screen.queryByLabelText("Name *"), null);
  assert.equal(screen.queryByText("Computing"), null);
  await screen.findByText(/No departments yet/);
  assert.equal(requests.at(-1).workspace, b);
});

test("API load and mutation errors allow retry without losing form values", async t => {
  const control = { fail: true, failWrite: false };
  setup(t, {}, control);
  await screen.findByRole("alert"); control.fail = false;
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await screen.findByText(/No departments yet/);
  create("Departments"); fill("Name *", "Math"); fill("Code *", "M");
  control.failWrite = true; save(); await screen.findByRole("alert");
  assert.equal(screen.getByLabelText("Name *").value, "Math");
  control.failWrite = false; save(); await screen.findByText("Math");
});
