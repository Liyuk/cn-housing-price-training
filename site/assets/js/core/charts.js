/* Charts: ECharts lifecycle.  Pages and domain modules hand in an option
   *builder* (a function), never an instance; this module owns loading the
   library, creating instances, resizing, and rebuilding on theme or breakpoint
   change.  `kit` holds the shared option fragments so every chart looks alike. */

import { tok, onThemeChange, onBreakpointChange } from "./theme.js";
import { debounce } from "./format.js";
import { loadScript } from "./loader.js";

export { loadScript };

const ECHARTS = [
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js",
  "https://unpkg.com/echarts@5.5.1/dist/echarts.min.js",
];

export const ensureEcharts = () => loadScript(ECHARTS);

const registry = new Map(); // element -> { inst, build }

/** Create or update the chart in `el`.  `build()` returns an ECharts option. */
export function mount(el, build) {
  const hit = registry.get(el);
  if (hit) { hit.build = build; hit.inst.setOption(build(), true); return hit.inst; }
  const inst = echarts.init(el, null, { renderer: "canvas" });
  registry.set(el, { inst, build });
  inst.setOption(build(), true);
  return inst;
}
export function instanceOf(el) { const h = registry.get(el); return h ? h.inst : null; }
export function dispose(el) { const h = registry.get(el); if (h) { h.inst.dispose(); registry.delete(el); } }

const rebuildAll = () => registry.forEach(({ inst, build }) => inst.setOption(build(), true));
onThemeChange(rebuildAll);
onBreakpointChange(rebuildAll);   // label and legend layout depend on the breakpoint
window.addEventListener("resize", debounce(() => registry.forEach(({ inst }) => inst.resize()), 120));

/** Run `fn` once when `el` approaches the viewport (below-the-fold sections load lazily). */
export function whenVisible(el, fn, margin = "500px") {
  if (!("IntersectionObserver" in window)) return fn();
  const io = new IntersectionObserver((entries) => {
    if (entries.some((e) => e.isIntersecting)) { io.disconnect(); fn(); }
  }, { rootMargin: margin });
  io.observe(el);
}

/* ---- shared option fragments ------------------------------------------- */
export const kit = {
  text: () => ({ fontFamily: getComputedStyle(document.body).fontFamily }),
  axis: () => ({
    axisLine: { lineStyle: { color: tok("line-2") } },
    axisTick: { show: false },
    axisLabel: { color: tok("ink-3"), fontSize: 11.5, hideOverlap: true },
    splitLine: { lineStyle: { color: tok("line") } },
  }),
  tooltip: (trigger = "axis") => ({
    trigger, confine: true,
    backgroundColor: tok("panel"), borderColor: tok("line-2"), borderWidth: 1,
    textStyle: { color: tok("ink"), fontSize: 12.5 },
    extraCssText: "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.25);",
    axisPointer: { type: "line", lineStyle: { color: tok("ink-3"), type: "solid", width: 1 } },
  }),
  legend: (data) => ({ data, top: 0, left: 0, itemWidth: 14, itemHeight: 8, itemGap: 16, textStyle: { color: tok("ink-2"), fontSize: 12 } }),
  /** Category axis labelled once per year. */
  yearAxis(data, extra = {}) {
    return Object.assign(kit.axis(), {
      type: "category", data, boundaryGap: false, splitLine: { show: false },
      axisLabel: { color: tok("ink-3"), fontSize: 11.5, hideOverlap: true, interval: (i, v) => v.endsWith("-01"), formatter: (v) => v.slice(0, 4) },
    }, extra);
  },
  valueAxis: (extra = {}) => Object.assign(kit.axis(), { type: "value", axisLine: { show: false } }, extra),
};
