import test from "node:test";
import assert from "node:assert/strict";
import { aggregateOhlc, forecastLines, shadeBlocks, legendModel, changeBars, periodLabel, candleKey } from "../../site/assets/js/domain/candles.js";

const months = ["2020-01", "2020-02", "2020-03", "2020-04", "2020-05", "2020-06"];
const values = [101, 103, 102, 100, 104, 105];

test("monthly candles chain: open = previous close, first open = base", () => {
  const c = aggregateOhlc(months, values, "M", 100);
  assert.equal(c.length, 6);
  assert.equal(c[0].open, 100);
  for (let i = 1; i < c.length; i++) assert.equal(c[i].open, c[i - 1].close);
  assert.equal(c[2].close, 102);
});
test("monthly candles are body-only: high/low are just open and close", () => {
  for (const k of aggregateOhlc(months, values, "M", 100)) {
    assert.equal(k.high, Math.max(k.open, k.close));
    assert.equal(k.low, Math.min(k.open, k.close));
  }
});
test("quarterly candles carry wicks from the months inside the quarter", () => {
  const q = aggregateOhlc(months, values, "Q", 100);
  assert.equal(q.length, 2);
  assert.deepEqual(q[0], { time: "2020-01-01", open: 100, high: 103, low: 100, close: 102 });
  assert.deepEqual(q[1], { time: "2020-04-01", open: 102, high: 105, low: 100, close: 105 });
});
test("yearly candle spans the year and starts on January 1", () => {
  const y = aggregateOhlc(months, values, "Y", 100);
  assert.equal(y.length, 1);
  assert.equal(y[0].time, "2020-01-01");
  assert.equal(y[0].close, 105);
  assert.equal(y[0].high, 105);
  assert.equal(y[0].low, 100);
});
test("periods crossing a year boundary are split, continuity is kept", () => {
  const c = aggregateOhlc(["2020-11", "2020-12", "2021-01", "2021-02"], [100, 102, 101, 104], "Y", 99);
  assert.equal(c.length, 2);
  assert.equal(c[1].open, c[0].close);
  assert.equal(c[1].time, "2021-01-01");
});
test("forecast lines start at the origin so they connect to the last candle", () => {
  const fanAll = { fc_months: ["2026-10", "2026-11"] };
  const fan = { q500: [99, 98], q100: [98, 96], q900: [100, 99] };
  const f = forecastLines(fanAll, fan, "2026-09", 150);
  assert.deepEqual(f.median[0], { time: "2026-09-01", value: 150 });
  assert.deepEqual(f.median[1], { time: "2026-10-01", value: 148.5 });   // 99 % of 150, rebased
  assert.equal(f.lo.length, 3);
});

test("period labels: month, quarter, year", () => {
  assert.equal(periodLabel("2026-07-01", "M"), "2026-07");
  assert.equal(periodLabel("2026-07-01", "Q"), "2026 Q3");
  assert.equal(periodLabel("2026-01-01", "Y"), "2026");
});

test("data bar on a candle: period label, OHLC, change coloured by direction, national close", () => {
  const m = legendModel({ title: "北京", period: "Q", bar: { time: "2026-07-01", open: 100, high: 101, low: 98, close: 99 }, national: 98.5, now: 99 });
  assert.equal(m.time, "2026 Q3");
  assert.equal(m.unit, "季 K");
  assert.deepEqual(m.ohlc.map((o) => `${o.k}${o.v}`), ["开100.0", "高101.0", "低98.0", "收99.0"]);
  assert.equal(m.tone, "down");
  assert.match(m.change, /1\.00（.*1\.00%）/);
  assert.deepEqual(m.rows, [{ name: "全国", value: "98.5", cls: "nat" }]);
  assert.equal(legendModel({ title: "x", period: "M", bar: { time: "2026-07-01", open: 100, high: 101, low: 100, close: 101 }, now: 101 }).tone, "up");
});

test("data bar in the forecast names the zone and gives changes relative to the current level", () => {
  const f = (h) => legendModel({ title: "全国", period: "Q", fc: { time: "2027-09-01", h, median: 97, lo: 94, hi: 99 }, now: 100, zones: { reliable: 12, caution: 24 } });
  assert.match(f(12).time, /^2027-09 · \+12 个月（可作预测）/);
  assert.equal(f(12).ohlc, null);
  assert.match(f(12).rows[0].value, /97\.0（.*3\.0%）/);
  assert.match(f(12).rows[1].value, /94\.0 ~ 99\.0/);
  assert.match(f(18).time, /谨慎参考/);
  assert.match(f(30).time, /仅作情景/);
  assert.equal(legendModel({ title: "x", period: "M" }).ohlc, null);
});

test("change bars are the period change in percent", () => {
  assert.deepEqual(changeBars([{ time: "2026-01-01", open: 100, close: 99 }, { time: "2026-04-01", open: 99, close: 99.99 }]).map((b) => b.value), [-1, 1]);
});

test("shade blocks: each rising run ends with a whitespace point; scenario zone starts at the caution horizon", () => {
  const months = [], series = [];
  let v = 100;
  for (let i = 0; i < 24; i++) { months.push(`${2020 + Math.floor(i / 12)}-${String(i % 12 + 1).padStart(2, "0")}`); v *= i < 14 ? 1.01 : 0.99; series.push(v); }
  const fc = Array.from({ length: 30 }, (_, i) => `2022-${String(i % 12 + 1).padStart(2, "0")}`);
  const { phase, scenario } = shadeBlocks(series, months, fc, { reliable: 12, caution: 24 });
  assert.ok(phase.length > 3);
  assert.ok(phase.some((p) => p.value === undefined), "run is closed by a whitespace point");
  const times = phase.map((p) => p.time);
  assert.deepEqual(times, [...times].sort(), "times ascend");
  assert.equal(new Set(times).size, times.length, "times unique");
  assert.equal(scenario.length, 6);
  assert.equal(scenario[0].time, `${fc[24]}-01`);
  assert.deepEqual(shadeBlocks(series, months, [], { reliable: 12, caution: 24 }).scenario, []);
});

test("key lists every mark the chart draws, and only those", () => {
  const all = candleKey({ compare: true, forecast: true, zones: { reliable: 12, caution: 24 }, period: "Q" });
  for (const t of ["上涨季", "下跌季", "上行阶段", "预测中位数", "80% 区间上/下沿", "情景区（+24 个月后", "全国", "每季涨跌幅"]) assert.ok(all.includes(t), t);
  const none = candleKey({ period: "M" });
  assert.ok(none.includes("上涨月") && !none.includes("预测中位数") && !none.includes("情景区"));
});
