import test from "node:test";
import assert from "node:assert/strict";
import { yoy, drawdown, rebase, metricValues, windowStats } from "../../site/assets/js/domain/series.js";

const months = Array.from({ length: 6 }, (_, i) => `2020-0${i + 1}`);

test("yoy: first 12 months are empty, then the change against a year earlier", () => {
  const levels = Array.from({ length: 14 }, (_, i) => 100 + i);
  const y = yoy(levels);
  assert.deepEqual(y.slice(0, 12), new Array(12).fill(null));
  assert.equal(y[12], 12);
  assert.equal(y[13], 11.9);
});

test("drawdown counts from the window start and never goes above zero", () => {
  const d = drawdown([100, 120, 90, 110, 130, 104], 1);
  assert.deepEqual(d, [null, 0, -25, -8.3, 0, -20]);
  assert.ok(drawdown([100, 99, 101]).every((v) => v <= 0));
});

test("rebase: the base month is exactly 100 and ratios are kept", () => {
  assert.deepEqual(rebase([50, 100, 150, 75], 1), [50, 100, 150, 75]);
  assert.deepEqual(rebase([50, 100, 150, 75], 3), [66.67, 133.33, 200, 100]);
  assert.deepEqual(rebase([null, 10, 20], 1), [null, 100, 200]);
});

test("metricValues: level is untouched", () => {
  const l = [1, 2, 3];
  assert.equal(metricValues(l, "level"), l);
});

test("window stats: change, drawdown, high/low, share of rising months", () => {
  const s = windowStats(months, [100, 110, 99, 105, 120, 108], 0, 5);
  assert.equal(s.months, 6);
  assert.equal(Math.round(s.change * 100) / 100, 8);
  assert.equal(s.annualised, null, "less than a year is not annualised");
  assert.equal(s.high.m, "2020-05");
  assert.equal(s.low.m, "2020-03");
  assert.deepEqual([s.maxDrawdown.from, s.maxDrawdown.to], ["2020-02", "2020-03"]);   // 110 -> 99 and 120 -> 108 tie at -10%: the first is kept
  assert.equal(Math.round(s.maxDrawdown.pct * 10) / 10, -10);
  assert.equal(s.upShare, 3 / 5);
  assert.equal(Math.round(s.fromHigh * 10) / 10, -10);
});

test("window stats: annualised over a full year equals the change", () => {
  const levels = Array.from({ length: 13 }, (_, i) => 100 * Math.pow(1.01, i));
  const s = windowStats(Array.from({ length: 13 }, (_, i) => `m${i}`), levels, 0, 12);
  assert.equal(Math.round(s.annualised * 100) / 100, Math.round(s.change * 100) / 100);
});

test("window stats flag a window that spans the regime break", () => {
  const m = ["2010-12", "2011-01", "2011-02", "2011-03"];
  assert.equal(windowStats(m, [1, 2, 3, 4], 0, 3, "2011-02").crossesBreak, true);
  assert.equal(windowStats(m, [1, 2, 3, 4], 2, 3, "2011-02").crossesBreak, false);
  assert.equal(windowStats(m, [1, 2, 3, 4], 0, 1, "2011-02").crossesBreak, false);
});
