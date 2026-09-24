import { test } from "node:test";
import assert from "node:assert/strict";
import { listAll } from "../src/lib/api.ts";

const workspace = "11111111-1111-1111-1111-111111111111";
test("API client reads every page and scopes requests", async (t) => {
  t.mock.method(globalThis, "fetch", async (url, options) => {
    assert.equal(options.credentials, "omit");
    assert.equal(options.cache, "no-store");
    assert.match(url, new RegExp(`/api/workspaces/${workspace}/rooms`));
    const count = new URL(url).searchParams.get("offset") === "0" ? 200 : 1;
    return Response.json(Array.from({ length: count }, () => ({ workspace_id: workspace })));
  });
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const rows = await listAll(workspace, "rooms", new AbortController().signal);
  assert.equal(rows.length, 201);
});
test("API errors, foreign workspace data, and missing configuration are visible", async (t) => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const mock = t.mock.method(globalThis, "fetch", async () => Response.json({ detail: { message: "Workspace not found." } }, { status: 404 }));
  const load = () => listAll(workspace, "rooms", new AbortController().signal);
  await assert.rejects(load, /Workspace not found/);
  mock.mock.mockImplementation(async () => Response.json([{ workspace_id: "another-workspace" }]));
  await assert.rejects(load, /unexpected workspace/);
  mock.mock.mockImplementation(async () => { throw new Error("network"); });
  await assert.rejects(load, /Cannot reach the API/);
  delete process.env.NEXT_PUBLIC_API_BASE_URL;
  await assert.rejects(load, /NEXT_PUBLIC_API_BASE_URL/);
});
test("aborted requests cannot continue pagination", async (t) => {
  process.env.NEXT_PUBLIC_API_BASE_URL = "http://api.example.test";
  const controller = new AbortController();
  t.mock.method(globalThis, "fetch", async (_, options) => {
    controller.abort();
    options.signal.throwIfAborted();
  });
  await assert.rejects(() => listAll(workspace, "rooms", controller.signal), { name: "AbortError" });
});
