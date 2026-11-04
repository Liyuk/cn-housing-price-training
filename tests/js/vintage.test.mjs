import test from "node:test";
import assert from "node:assert/strict";
import { createVintage } from "../../site/assets/js/core/vintage.js";

const manifest = {
  built_at: "2026-11-04", data_through: "2026-09", next_release_estimate: "2026-11-17",
  forecast: { origin: "2026-09", end: "2029-09", horizon_months: 36 }, regime_break: { month: "2011-02" },
  bundles: {
    "cum.json": { start: "2006-01", end: "2026-09", n: 249, freq: "月度", basis: "2005-12 = 100（环比链式累乘）" },
    "official.json": { start: "2025-10", end: "2025-10", n: 1, freq: "快照", basis: "北京存量房网签（单月）" },
    "forecast_series.json": { asof: "2026-06", freq: "月度", basis: "v0.2 论文模型（对照用）" },
    "fan.json": { origin: "2026-09", start: "2026-10", end: "2029-09", n: 36, freq: "月度", basis: "预测起点月 = 100" },
  },
  districts: { 北京: { start: "2022-01", end: "2026-09", asof: "2026-09", n: 57, freq: "月度", basis: "第三方月报，前 10 名区" } },
};
const v = createVintage(manifest);

test("span: range, snapshot and as-of forms", () => {
  assert.equal(v.span("cum.json"), "2006-01 → 2026-09");
  assert.equal(v.span("official.json"), "2025-10");
  assert.equal(v.span("forecast_series.json"), "截至 2026-06");
});
test("describe: frequency, span, period count, basis", () => {
  assert.equal(v.describe("cum.json"), "月度 · 2006-01 → 2026-09 · 249 期 · 2005-12 = 100（环比链式累乘）");
  assert.equal(v.describe("official.json"), "快照 · 2025-10 · 北京存量房网签（单月）");   // one period: no count
  assert.equal(v.describe("cum.json", { basis: false }), "月度 · 2006-01 → 2026-09 · 249 期");
});
test("city district bundles resolve through the same interface", () => {
  assert.match(v.describe("北京"), /月度 · 2022-01 → 2026-09 · 57 期/);
});
test("unknown bundle yields an empty label, never 'undefined'", () => {
  assert.equal(v.describe("nope.json"), "");
  assert.equal(v.span("nope.json"), "");
});
test("headline dates come from the manifest", () => {
  assert.equal(v.dataThrough, "2026-09");
  assert.equal(v.nextRelease, "2026-11-17");
  assert.equal(v.forecast.end, "2029-09");
});
