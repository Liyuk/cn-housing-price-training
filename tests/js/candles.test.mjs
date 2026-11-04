import test from "node:test";
import assert from "node:assert/strict";
import { aggregateOhlc, forecastLines } from "../../site/assets/js/domain/candles.js";

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
