import test from "node:test";
import assert from "node:assert/strict";
import { assignColors, baseIndex, plotted, buildCompareOption, presets, COLOR_TOKENS, MAX_SERIES } from "../../site/assets/js/domain/compare-chart.js";

const theme = { tok: (n) => `tok(${n})` };
const months = Array.from({ length: 30 }, (_, i) => `${2020 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);
const levels = (start, g) => months.map((_, i) => +(start * Math.pow(1 + g, i)).toFixed(2));

test("colour slots: removing a line never repaints the others; a new line takes the lowest free slot", () => {
  const first = assignColors(["全国", "北京", "上海"]);
  assert.deepEqual(first, { 全国: 0, 北京: 1, 上海: 2 });
  const after = assignColors(["全国", "上海"], first);
  assert.deepEqual(after, { 全国: 0, 上海: 2 });
  assert.deepEqual(assignColors(["全国", "上海", "深圳"], after), { 全国: 0, 上海: 2, 深圳: 1 });
});

test("there is one validated colour token per selectable series", () => {
  assert.ok(COLOR_TOKENS.length >= MAX_SERIES);
});

test("base index: the first month at or after the base; absent base = window start", () => {
  assert.equal(baseIndex(months, "2021-03", 0), 14);
  assert.equal(baseIndex(months, null, 5), 5);
  assert.equal(baseIndex(months, "2030-01", 0), months.length - 1);
});

test("level metric: every series is exactly 100 at the base month", () => {
  const a = plotted(levels(100, 0.01), "level", { ib: 10, i0: 0 });
  const b = plotted(levels(50, -0.005), "level", { ib: 10, i0: 0 });
  assert.equal(a[10], 100);
  assert.equal(b[10], 100);
  assert.ok(a[11] > 100 && b[11] < 100);
});

test("yoy and drawdown ignore the base", () => {
  const l = levels(100, 0.01);
  assert.equal(plotted(l, "yoy", { ib: 10, i0: 0 })[11], null);
  assert.ok(plotted(l, "yoy", { ib: 10, i0: 0 })[12] > 12);
  assert.ok(plotted(levels(100, -0.01), "dd", { ib: 10, i0: 0 }).every((v) => v == null || v <= 0));
});

test("option: one line per region in its own colour, the base line, and a tooltip sorted high to low", () => {
  const regions = [{ name: "北京", levels: levels(100, 0.01), slot: 1 }, { name: "上海", levels: levels(100, -0.01), slot: 2 }];
  const opt = buildCompareOption({ months, regions, metric: "level", base: "2021-01", w: { i0: 0, i1: 29 }, breakMonth: "2020-06" }, theme);
  assert.deepEqual(opt.series.map((s) => s.name), ["北京", "上海"]);
  assert.equal(opt.series[0].lineStyle.color, "tok(blue)");
  assert.equal(opt.series[1].lineStyle.color, "tok(orange)");
  const marks = opt.series[0].markLine.data.map((m) => m.label.formatter || "");
  assert.ok(marks.includes("基期 2021-01 = 100") && marks.includes("口径断点 2020-06"));
  const html = opt.tooltip.formatter([{ dataIndex: 20 }]);
  assert.ok(html.indexOf("北京") < html.indexOf("上海"), "北京 is higher at month 20");
  assert.match(html, /基期 2021-01 = 100/);
  assert.equal(opt.dataZoom[0].startValue, "2020-01");
});

test("presets: worst/best are ordered by distance from peak and capped", () => {
  const cities = ["a", "b", "c", "d", "e", "f", "g"];
  const phases = Object.fromEntries(cities.map((c, i) => [c, { from_peak_pct: -10 * (i + 1) }]));
  const p = Object.fromEntries(presets(phases, cities).map((x) => [x.key, x.regions]));
  assert.deepEqual(p.worst, ["g", "f", "e", "d", "c"]);
  assert.deepEqual(p.best, ["a", "b", "c", "d", "e"]);
  assert.ok(p.worst.length <= MAX_SERIES);
});
