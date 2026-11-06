import test from "node:test";
import assert from "node:assert/strict";
import { oneOf, month, flag, list, parseState, serializeState, createUrlSync } from "../../site/assets/js/core/urlstate.js";

const schema = { m: oneOf(["line", "candle"], "line"), f: month(null), on: flag(false), s: list(["全国"], { max: 3 }) };

test("parse: valid values are read, invalid ones fall back to the default", () => {
  assert.deepEqual(parseState("?m=candle&f=2021-07&on=1&s=北京,上海", schema), { m: "candle", f: "2021-07", on: true, s: ["北京", "上海"] });
  assert.deepEqual(parseState("?m=bar&f=2021-13&on=2&s=", schema), { m: "line", f: null, on: false, s: ["全国"] });
});

test("lists are de-duplicated and capped", () => {
  assert.deepEqual(parseState("?s=a,b,a,c,d", schema).s, ["a", "b", "c"]);
});

test("serialise: defaults are left out, foreign params survive", () => {
  assert.equal(serializeState({ m: "line", f: null, on: false, s: ["全国"] }, schema, "?c=%E4%B8%8A%E6%B5%B7"), "?c=%E4%B8%8A%E6%B5%B7");
  const q = serializeState({ m: "candle", f: "2021-07", on: true, s: ["北京", "上海"] }, schema, "?c=x");
  assert.deepEqual(Object.fromEntries(new URLSearchParams(q)), { c: "x", m: "candle", f: "2021-07", on: "1", s: "北京,上海" });
  assert.equal(serializeState({ m: "line", f: null, on: false, s: ["全国"] }, schema, "?m=candle"), "");
});

test("round trip", () => {
  const state = { m: "candle", f: "2019-01", on: true, s: ["深圳"] };
  assert.deepEqual(parseState(serializeState(state, schema), schema), state);
});

test("sync adapter reads the location and rewrites it without adding history entries", () => {
  const calls = [];
  const win = { location: { search: "?m=candle", pathname: "/city.html", hash: "#x" }, history: { replaceState: (...a) => calls.push(a) } };
  const sync = createUrlSync(schema, win);
  assert.equal(sync.read().m, "candle");
  sync.write({ m: "candle", f: null, on: false, s: ["全国"] });
  assert.equal(calls.length, 0, "unchanged state does not touch history");
  sync.write({ m: "line", f: "2021-07", on: false, s: ["全国"] });
  assert.deepEqual(calls[0].slice(1), ["", "/city.html?f=2021-07#x"]);
});
