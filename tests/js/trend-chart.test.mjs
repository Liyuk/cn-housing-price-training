import test from "node:test";
import assert from "node:assert/strict";
import { buildTrendOption, risingRuns, rangeStartIndex, scaledFan, fanTable } from "../../site/assets/js/domain/trend-chart.js";

const theme = { tok: (n) => `#${n}` };
const months = Array.from({ length: 40 }, (_, i) => `${2020 + Math.floor(i / 12)}-${String((i % 12) + 1).padStart(2, "0")}`);
const rising = months.map((_, i) => 100 + i);                       // monotone up
const cum = {
  months, base: "2019-12 = 100", regime_break: { month: "2020-06" },
  series: { 全国: rising, 一线: rising, 上海: rising },
  phases: Object.fromEntries(["全国", "一线", "上海"].map((r) => [r, { peak: { m: months[39], v: 139 }, back_to: "2020-01" }])),
};
const arr = (v) => Array.from({ length: 36 }, (_, i) => v - i * 0.05);
const fan = {
  fc_months: Array.from({ length: 36 }, (_, i) => `${2023 + Math.floor((i + 4) / 12)}-${String(((i + 4) % 12) + 1).padStart(2, "0")}`),
  regions: { 全国: { q025: arr(97), q100: arr(98), q500: arr(99.5), q900: arr(101), q975: arr(102) } },
};

test("a region with a fan gets history, median and three band pairs", () => {
  const o = buildTrendOption({ cum, fan }, "全国", {}, theme);
  const names = o.series.map((s) => s.name);
  assert.ok(names.includes("历史") && names.includes("预测中位数"));
  assert.equal(names.filter((n) => n === "80% 区间").length, 3);        // reliable + caution + scenario zones
  assert.equal(o.xAxis.data.length, 40 + 36);
});
test("zones come from the caller: the band split and the labels follow them", () => {
  const o = buildTrendOption({ cum, fan }, "全国", { zones: { reliable: 6, caution: 12 } }, theme);
  const area = o.series[0].markArea.data.at(-1)[0];
  assert.equal(area.xAxis, fan.fc_months[12]);                           // the scenario shading starts after `caution`
  const tip = o.tooltip.formatter([{ dataIndex: 40 + 8 }]);              // month +9: inside caution (7..12)
  assert.match(tip, /谨慎参考/);
  assert.match(o.tooltip.formatter([{ dataIndex: 40 + 20 }]), /情景/);
});
test("a tier has no fan: history only, no forecast labels", () => {
  const o = buildTrendOption({ cum, fan }, "一线", {}, theme);
  assert.deepEqual(o.series.map((s) => s.name), ["历史"]);
  assert.equal(o.xAxis.data.length, 40);
  assert.deepEqual(o.legend.data, ["历史"]);
});
test("the regime break is marked when it falls inside the history", () => {
  const o = buildTrendOption({ cum, fan }, "全国", {}, theme);
  const lines = o.series[0].markLine.data;
  assert.ok(lines.some((l) => l.xAxis === "2020-06"));
});
test("comparison line only for non-national regions and only when asked", () => {
  assert.ok(!buildTrendOption({ cum, fan }, "上海", { compare: false }, theme).series.some((s) => s.name === "全国"));
  assert.ok(buildTrendOption({ cum, fan }, "上海", { compare: true }, theme).series.some((s) => s.name === "全国"));
  assert.equal(buildTrendOption({ cum, fan }, "全国", { compare: true }, theme).series.filter((s) => s.name === "全国").length, 0);   // national is never compared with itself
});
test("forecast quantiles are rebased from origin = 100 to the chain level", () => {
  const sc = scaledFan({ q025: [100], q100: [100], q500: [100], q900: [100], q975: [100] }, 139);
  assert.equal(sc.q500[0], 139);
});
test("range keys map to a start index; 'all' is the first month", () => {
  assert.equal(rangeStartIndex("all", 249), 0);
  assert.equal(rangeStartIndex("10", 249), 249 - 1 - 120);
  assert.equal(rangeStartIndex("20", 100), 0);                          // never negative
});
test("rising runs need at least three months and a positive 6-month mean", () => {
  const flatThenUp = [100, 100, 100, 100, 100, 100, 101, 102, 103, 104, 105, 106];
  const runs = risingRuns(flatThenUp, months.slice(0, 12));
  assert.equal(runs.length, 1);
  assert.equal(runs[0][1], months[11]);
  assert.deepEqual(risingRuns([100, 99, 98, 97, 96, 95, 94, 93], months.slice(0, 8)), []);
});
test("fan table labels each row with relative and absolute months and a reliability zone", () => {
  const html = fanTable(fan, "全国", "2026-09", { reliable: 6, caution: 12 });
  assert.match(html, /\+1 个月/);
  assert.match(html, /可作预测/);
  assert.match(html, /谨慎参考/);
  assert.match(html, /仅作情景/);
  assert.equal(fanTable(fan, "一线", "2026-09"), "");
});
