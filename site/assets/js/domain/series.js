/* Series arithmetic for the charts: metrics (level / year-on-year / drawdown), rebasing, and the statistics of a window.
   Pure functions over arrays; no DOM.  Levels are the chained index (month 0 = base 100). */

export const METRICS = [["level", "指数"], ["yoy", "同比"], ["dd", "距高点"]];
export const METRIC_NAME = { level: "指数", yoy: "同比（环比连乘）", dd: "距窗口内高点" };

const r1 = (v) => Math.round(v * 10) / 10;

/** Year-on-year change in percent; the first `lag` months have no value. */
export function yoy(levels, lag = 12) {
  return levels.map((v, i) => (i < lag || levels[i - lag] == null || v == null ? null : r1((v / levels[i - lag] - 1) * 100)));
}

/** Percent below the running high, counted from index i0 (earlier points are null). */
export function drawdown(levels, i0 = 0) {
  let high = -Infinity;
  return levels.map((v, i) => {
    if (i < i0 || v == null) return null;
    high = Math.max(high, v);
    return r1((v / high - 1) * 100);
  });
}

/** A series under the chosen metric.  `i0` is where the window starts (drawdown counts from it). */
export function metricValues(levels, metric, i0 = 0) {
  if (metric === "yoy") return yoy(levels);
  if (metric === "dd") return drawdown(levels, i0);
  return levels;
}

/** Levels scaled so the value at index `ib` is 100. */
export function rebase(levels, ib) {
  const base = levels[ib];
  return levels.map((v) => (v == null || !base ? null : Math.round((v / base) * 10000) / 100));
}

/** Statistics of levels[i0..i1].  `crossesBreak`: the window spans the series' regime break (changes there are not comparable). */
export function windowStats(months, levels, i0, i1, regimeBreak = null) {
  const steps = i1 - i0;
  const start = levels[i0], end = levels[i1];
  let high = { i: i0, v: start }, low = { i: i0, v: start }, peak = i0, dd = { pct: 0, from: i0, to: i0 }, up = 0;
  for (let i = i0 + 1; i <= i1; i++) {
    if (levels[i] > high.v) high = { i, v: levels[i] };
    if (levels[i] < low.v) low = { i, v: levels[i] };
    if (levels[i] > levels[peak]) peak = i;
    const d = levels[i] / levels[peak] - 1;
    if (d < dd.pct) dd = { pct: d, from: peak, to: i };
    if (levels[i] > levels[i - 1]) up++;
  }
  return {
    from: { m: months[i0], v: start }, to: { m: months[i1], v: end },
    months: steps + 1,
    change: (end / start - 1) * 100,
    annualised: steps >= 12 ? (Math.pow(end / start, 12 / steps) - 1) * 100 : null,
    maxDrawdown: { pct: dd.pct * 100, from: months[dd.from], to: months[dd.to] },
    high: { m: months[high.i], v: high.v }, low: { m: months[low.i], v: low.v },
    fromHigh: (end / high.v - 1) * 100,
    upShare: steps ? up / steps : null,
    crossesBreak: !!regimeBreak && months[i0] < regimeBreak && regimeBreak <= months[i1],
  };
}
