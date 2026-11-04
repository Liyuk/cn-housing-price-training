import test from "node:test";
import assert from "node:assert/strict";
import { createData, DataError } from "../../site/assets/js/core/data.js";

const ok = (body) => ({ ok: true, status: 200, json: async () => body });
const miss = (status) => ({ ok: false, status });

test("concurrent loads of one bundle share a single request", async () => {
  let calls = 0;
  const d = createData({ fetchImpl: async () => { calls++; return ok({ a: 1 }); } });
  const [x, y] = await Promise.all([d.load("board"), d.load("board")]);
  assert.deepEqual(x, y);
  assert.equal(calls, 1);
  await d.load("board");
  assert.equal(calls, 1);                           // cached
});
test("URLs are data/<name>.json, subpaths allowed", async () => {
  const seen = [];
  const d = createData({ fetchImpl: async (u) => { seen.push(u); return ok({}); } });
  await d.load("districts/北京");
  assert.deepEqual(seen, ["data/districts/北京.json"]);
});
test("HTTP failures raise one error type carrying bundle and status", async () => {
  const d = createData({ fetchImpl: async () => miss(500) });
  await assert.rejects(() => d.load("cum"), (e) => e instanceof DataError && e.bundle === "cum" && e.status === 500 && /cum: HTTP 500/.test(e.message));
});
test("network errors are wrapped too", async () => {
  const d = createData({ fetchImpl: async () => { throw new Error("offline"); } });
  await assert.rejects(() => d.load("cum"), (e) => e instanceof DataError && /offline/.test(e.message));
});
test("a failed load can be retried", async () => {
  let n = 0;
  const d = createData({ fetchImpl: async () => (++n === 1 ? miss(503) : ok({ v: 1 })) });
  await assert.rejects(() => d.load("fan"));
  assert.deepEqual(await d.load("fan"), { v: 1 });
});
test("tryLoad resolves null on 404 but still throws on other failures", async () => {
  const d404 = createData({ fetchImpl: async () => miss(404) });
  assert.equal(await d404.tryLoad("districts/苏州"), null);
  const d500 = createData({ fetchImpl: async () => miss(500) });
  await assert.rejects(() => d500.tryLoad("x"));
});
test("loadAll returns an object keyed by name", async () => {
  const d = createData({ fetchImpl: async (u) => ok({ u }) });
  const r = await d.loadAll(["a", "b"]);
  assert.deepEqual(Object.keys(r), ["a", "b"]);
  assert.equal(r.b.u, "data/b.json");
});
