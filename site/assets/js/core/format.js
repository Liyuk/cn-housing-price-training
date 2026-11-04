/* Pure formatting helpers.  No DOM, no globals: importable from node tests.
   Time conventions (site-wide): months are "YYYY-MM"; a span is "起 → 止";
   a horizon is "+12 个月（2027-09）" -- relative and absolute together. */

export const esc = (s) => String(s).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

/** Signed fixed-point; a value that rounds to zero carries no sign ("0.0", not "+0.0"). */
export function sgn(v, d = 1) {
  const a = Number(Math.abs(v).toFixed(d));
  return (a === 0 ? "" : v > 0 ? "+" : "−") + a.toFixed(d);
}
export const pct = (v, d = 1) => sgn(v, d) + "%";
export const cls = (v) => (v >= 0.05 ? "up" : v <= -0.05 ? "down" : "flatc");
export const probText = (p) => (p == null ? "—" : p <= 0.01 ? "≤1%" : p >= 0.99 ? "≥99%" : Math.round(p * 100) + "%");
export const grp = (n) => Number(n).toLocaleString("zh-CN");

/** "2026-09" + n months -> "2027-09" (n may be negative). */
export function addMonths(ym, n) {
  const [y, m] = ym.split("-").map(Number);
  const t = y * 12 + (m - 1) + n;
  return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`;
}
/** Whole months from a to b ("2026-09" - "2026-06" = 3). */
export function monthsBetween(a, b) {
  const [ya, ma] = a.split("-").map(Number);
  const [yb, mb] = b.split("-").map(Number);
  return (yb - ya) * 12 + (mb - ma);
}
export const range = (a, b) => (a === b ? a : `${a} → ${b}`);
export const horizon = (h, origin) => `+${h} 个月（${addMonths(origin, h)}）`;
export const periods = (n) => `${n} 期`;

export function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}
