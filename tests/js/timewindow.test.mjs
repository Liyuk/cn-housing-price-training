import test from "node:test";
import assert from "node:assert/strict";
import { resolveWindow, createTimeWindow } from "../../site/assets/js/core/timewindow.js";

const months = Array.from({ length: 36 }, (_, i) => `${2020 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);   // 2020-01 .. 2022-12

test("presets end at the bounds' last month and count back whole years", () => {
  assert.deepEqual(resolveWindow(months, { range: "all" }), { from: "2020-01", to: "2022-12", i0: 0, i1: 35, outside: false });
  const w = resolveWindow(months, { range: "1" });
  assert.deepEqual([w.from, w.to], ["2021-12", "2022-12"]);
  assert.equal(resolveWindow(months, { range: "20" }).from, "2020-01", "clamped to the series start");
});

test("a series that ends earlier is clamped, not mis-aligned", () => {
  const short = months.slice(0, 30);                                         // ends 2022-06
  const w = resolveWindow(short, { range: "1" }, "2022-12");
  assert.equal(w.to, "2022-06");
  assert.equal(w.from, "2021-12");
});

test("custom windows are clamped, swapped when reversed, and never shorter than two points", () => {
  assert.deepEqual(resolveWindow(months, { range: "custom", from: "2019-01", to: "2030-01" }).from, "2020-01");
  const w = resolveWindow(months, { range: "custom", from: "2022-06", to: "2021-03" });
  assert.deepEqual([w.from, w.to], ["2021-03", "2022-06"]);
  const tiny = resolveWindow(months, { range: "custom", from: "2021-05", to: "2021-05" });
  assert.equal(tiny.i1 - tiny.i0, 1);
});

test("shared window: set() notifies subscribers; leaving custom drops from/to", () => {
  const win = createTimeWindow({ bounds: { first: "2020-01", last: "2022-12" } });
  const seen = [];
  win.subscribe((s) => seen.push({ ...s }));
  win.set({ range: "custom", from: "2021-01" });
  assert.deepEqual(seen[0], { range: "custom", from: "2021-01", to: "2022-12" });
  win.set({ range: "5" });
  assert.deepEqual(seen[1], { range: "5", from: null, to: null });
  assert.equal(win.resolve(months).from, "2020-01");
});

test("a custom window wholly outside a series is flagged, so the chart can say so instead of showing its first points", () => {
  assert.equal(resolveWindow(months, { range: "custom", from: "2010-01", to: "2015-12" }).outside, true);
  assert.equal(resolveWindow(months, { range: "custom", from: "2024-01", to: "2025-12" }).outside, true);
  assert.equal(resolveWindow(months, { range: "custom", from: "2019-01", to: "2020-06" }).outside, false);
});
