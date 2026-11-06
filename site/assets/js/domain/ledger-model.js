/* Ledger model: the frozen path of a region next to what was published since.  No DOM, no chart library. */

export const HORIZON = 12;   // the months every region is frozen for in the page bundle, and the ones actuals arrive for first

/** The frozen path and the actuals of one region; `null` actual where the month is not yet published. */
export function regionPath(entry, region, horizon = HORIZON) {
  const f = region === "全国" ? entry.national : entry.cities[region];
  const a = region === "全国" ? entry.actual.national : entry.actual.cities[region] || [];
  const n = Math.min(horizon, f.q500.length);
  return Array.from({ length: n }, (_, i) => ({
    h: i + 1, month: entry.months[i], median: f.q500[i], lo: f.q100[i], hi: f.q900[i], actual: a[i] ?? null,
  }));
}

export const verdictOf = (row) => (row.actual == null ? "pending" : row.actual >= row.lo && row.actual <= row.hi ? "in" : "out");
