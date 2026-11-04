/* Vintage: the single source of every "data through / span / frequency" label.
   Reads manifest.json (written by scripts/site_extras.py).  Pages never hard-code
   a date; they ask here, so a stale bundle is visible instead of passing as current. */

import { range, periods } from "./format.js";

export function createVintage(manifest) {
  const info = (name) => manifest.bundles[name] || (manifest.districts && manifest.districts[name]) || null;

  /** "2006-01 → 2026-09", "截至 2026-06", or a single month. */
  function span(name) {
    const b = info(name);
    if (!b) return "";
    if (b.start && b.end) return range(b.start, b.end);
    if (b.asof) return `截至 ${b.asof}`;
    if (b.origin) return `起点 ${b.origin}`;
    return "";
  }

  /** "月度 · 2006-01 → 2026-09 · 249 期 · 基期 2005-12 = 100（环比链式累乘）" */
  function describe(name, { basis = true } = {}) {
    const b = info(name);
    if (!b) return "";
    const parts = [];
    if (b.freq) parts.push(b.freq);
    const s = span(name);
    if (s) parts.push(s);
    if (b.n && b.start !== b.end && !/年末|回测/.test(b.freq || "")) parts.push(periods(b.n));
    if (basis && b.basis) parts.push(b.basis);
    return parts.join(" · ");
  }

  return {
    manifest,
    info, span, describe,
    asof: (name) => { const b = info(name); return b ? b.asof || b.end || b.origin || "" : ""; },
    dataThrough: manifest.data_through,
    builtAt: manifest.built_at,
    nextRelease: manifest.next_release_estimate,
    forecast: manifest.forecast,
    regimeBreak: manifest.regime_break,
    /** Fill every [data-vintage="bundle.json"] (describe) and [data-span="bundle.json"] (span) in `root`. */
    bind(root) {
      root.querySelectorAll("[data-vintage]").forEach((el) => { el.textContent = describe(el.dataset.vintage); });
      root.querySelectorAll("[data-span]").forEach((el) => { el.textContent = span(el.dataset.span); });
      root.querySelectorAll("[data-fill]").forEach((el) => {
        const key = el.dataset.fill;
        const map = { dataThrough: manifest.data_through, builtAt: manifest.built_at, nextRelease: manifest.next_release_estimate,
          forecastOrigin: manifest.forecast.origin, forecastEnd: manifest.forecast.end };
        if (key in map) el.textContent = map[key];
      });
    },
  };
}
