/* TimeWindow: the visible stretch of history, as one object that charts can share.
   A window is a preset ("last N years") or a custom from/to; each chart resolves it against its own
   months, so a series that starts later or ends earlier is clamped, never mis-aligned.
   Presets end at `bounds.last` (the data-through month), not at each series' own last month. */

import { addMonths } from "./format.js";
import { createUrlSync, month, oneOf } from "./urlstate.js";

export const RANGES = [["all", "全部"], ["20", "20 年"], ["10", "10 年"], ["5", "5 年"], ["3", "3 年"]];
export const WINDOW_SCHEMA = {
  r: oneOf([...RANGES.map(([v]) => v), "custom"], "all"),
  f: month(null),
  t: month(null),
};

/** First index whose month is >= m (or the last index), and last index whose month is <= m (or 0). */
const firstAtOrAfter = (months, m) => { const i = months.findIndex((x) => x >= m); return i < 0 ? months.length - 1 : i; };
const lastAtOrBefore = (months, m) => { let hit = 0; for (let i = 0; i < months.length && months[i] <= m; i++) hit = i; return hit; };

/** {range, from, to} -> {from, to, i0, i1} against `months` (sorted "YYYY-MM"); always at least two points. */
export function resolveWindow(months, { range = "all", from = null, to = null }, last = months[months.length - 1]) {
  let a, b;
  if (range === "custom") {
    let f = from || months[0], t = to || last;
    if (f > t) [f, t] = [t, f];
    a = firstAtOrAfter(months, f); b = lastAtOrBefore(months, t);
  } else {
    b = lastAtOrBefore(months, last);
    a = range === "all" ? 0 : firstAtOrAfter(months, addMonths(last, -12 * Number(range)));
  }
  const win = range === "custom" ? { from: from || months[0], to: to || last } : { from: months[0], to: last };
  const outside = range === "custom" && (win.to < months[0] || win.from > months[months.length - 1]) && win.from <= win.to;
  if (b <= a) { b = Math.min(months.length - 1, a + 1); a = Math.max(0, b - 1); }
  return { from: months[a], to: months[b], i0: a, i1: b, outside };
}

export function createTimeWindow({ bounds, state: initial = {} } = {}) {
  const state = { range: "all", from: null, to: null, ...initial };
  const subs = new Set();
  return {
    state,
    bounds,
    set(patch) {
      const next = { ...state, ...patch };
      if (next.range !== "custom") { next.from = null; next.to = null; }
      else { next.from = next.from || bounds.first; next.to = next.to || bounds.last; }
      Object.assign(state, next);
      subs.forEach((fn) => fn(state));
    },
    resolve: (months) => resolveWindow(months, state, bounds.last),
    subscribe(fn) { subs.add(fn); return () => subs.delete(fn); },
  };
}

/** A TimeWindow whose range/from/to live in the URL (?r=5, ?r=custom&f=2021-07&t=2024-01): read at creation, written on every change. */
export function windowFromUrl({ bounds, defaults = {}, win = window }) {
  const sync = createUrlSync(WINDOW_SCHEMA, win);
  const { r, f, t } = sync.read();
  const hasUrl = new URLSearchParams(win.location.search).has("r");
  const tw = createTimeWindow({ bounds, state: hasUrl ? { range: r, from: f, to: t } : defaults });
  tw.subscribe((s) => sync.write({ r: s.range, f: s.from, t: s.to }));
  return tw;
}
