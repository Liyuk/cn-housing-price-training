/* Comparison chart: several regions on one axis, rebased to a chosen month (level), or as year-on-year / drawdown.
   Everything here is pure (data in, option or array out) so it runs under node. */

import { rebase, metricValues, METRIC_NAME } from "./series.js";
import { pct } from "../core/format.js";

export const MAX_SERIES = 5;
export const COLOR_TOKENS = ["gold", "blue", "orange", "aqua", "violet"];   // fixed order, validated together (see scripts/design_check.py)
export const DASHES = ["solid", "solid", "solid", "dashed", "dashed"];

/** Colour slot per region.  A region keeps its slot while it stays selected; a new one takes the lowest free slot,
 *  so removing a line never repaints the others. */
export function assignColors(order, previous = {}) {
  const used = new Set(order.filter((r) => r in previous).map((r) => previous[r]));
  const slots = {};
  for (const r of order) {
    if (r in previous) { slots[r] = previous[r]; continue; }
    let k = 0;
    while (used.has(k)) k++;
    slots[r] = k; used.add(k);
  }
  return slots;
}

/** Index of the base month in `months` (the first month at or after it; null/absent -> the window start). */
export function baseIndex(months, base, i0) {
  if (!base) return i0;
  const i = months.findIndex((m) => m >= base);
  return i < 0 ? months.length - 1 : i;
}

/** The plotted values of one region under the metric. */
export function plotted(levels, metric, { ib, i0 }) {
  return metric === "level" ? rebase(levels, ib) : metricValues(levels, metric, i0);
}

/**
 * @param spec { months, regions:[{name, levels, slot}], metric, base (month|null), w:{i0,i1,outside}, breakMonth, narrow }
 */
export function buildCompareOption({ months, regions, metric, base, w, breakMonth = null, narrow = false }, theme) {
  const tok = theme.tok;
  const level = metric === "level";
  const ib = baseIndex(months, base, w.i0);
  const rows = regions.map((r) => ({ ...r, color: tok(COLOR_TOKENS[r.slot]), values: plotted(r.levels, metric, { ib, i0: w.i0 }) }));
  const fmt = level ? (v) => v.toFixed(1) : (v) => pct(v, 1);
  const marks = [{ yAxis: level ? 100 : 0, lineStyle: { type: "dashed", color: tok("ink-3"), opacity: 0.7, width: 1 }, label: { show: false } }];
  if (level) marks.push({ xAxis: months[ib], lineStyle: { type: "solid", color: tok("line-2"), width: 1 }, label: { show: !narrow, position: "insideEndTop", color: tok("ink-3"), fontSize: 11.5, formatter: `基期 ${months[ib]} = 100` } });
  if (breakMonth && months.includes(breakMonth)) marks.push({ xAxis: breakMonth, lineStyle: { type: "dotted", color: tok("ink-3"), width: 1 }, label: { show: !narrow, position: "insideStartTop", color: tok("ink-3"), fontSize: 11, formatter: "口径断点 " + breakMonth } });
  return {
    animationDuration: 300,
    grid: { left: 48, right: narrow ? 12 : 92, top: narrow ? 78 : 56, bottom: 30 },
    legend: { data: rows.map((r) => r.name), top: 0, left: 0, itemWidth: 14, itemHeight: 8, itemGap: 16, textStyle: { color: tok("ink-2"), fontSize: 12 } },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: tok("panel"), borderColor: tok("line-2"), borderWidth: 1, textStyle: { color: tok("ink"), fontSize: 12.5 },
      extraCssText: "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.25);",
      axisPointer: { type: "cross", lineStyle: { color: tok("ink-3"), width: 1 }, crossStyle: { color: tok("ink-3"), width: 1 },
        label: { backgroundColor: tok("foreground"), color: tok("background"), fontSize: 11, padding: [3, 6], borderRadius: 3 } },
      formatter(params) {
        const i = params[0].dataIndex;
        const lines = rows.map((r) => ({ r, v: r.values[i] })).filter((x) => x.v != null).sort((a, b) => b.v - a.v)
          .map(({ r, v }) => `<span style="color:${r.color}">●</span> ${r.name}：<b>${fmt(v)}</b>${level ? `（${pct(v - 100, 1)}）` : ""}`);
        return `<b>${months[i]}</b>${level ? `（基期 ${months[ib]} = 100）` : ""}<br/>${lines.join("<br/>")}`;
      },
    },
    xAxis: { type: "category", data: months, boundaryGap: false, axisLine: { lineStyle: { color: tok("line-2") } }, axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { color: tok("ink-3"), fontSize: 11.5, hideOverlap: true, interval: (i, v) => v.endsWith("-01"), formatter: (v) => v.slice(0, 4) },
      axisPointer: { label: { formatter: ({ value }) => value } } },
    yAxis: { type: "value", scale: true, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: tok("line") } },
      name: level ? `指数（基期 = 100）` : `${METRIC_NAME[metric]}（%）`, nameLocation: "end", nameGap: 12, nameTextStyle: { color: tok("ink-3"), fontSize: 11.5, align: "left", padding: [0, 0, 0, -44] },
      axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: level ? (v) => v.toFixed(0) : (v) => `${v.toFixed(0)}%` },
      axisPointer: { label: { formatter: ({ value }) => (level ? (+value).toFixed(1) : `${(+value).toFixed(1)}%`) } } },
    dataZoom: [{ type: "slider", show: false, startValue: months[w.i0], endValue: months[w.i1] }],
    brush: { xAxisIndex: 0, brushType: "lineX", brushMode: "single", throttleType: "debounce", throttleDelay: 120, removeOnClick: false, transformable: false,
      brushStyle: { color: tok("phase"), borderColor: tok("gold"), borderWidth: 1 } },
    toolbox: { show: false, feature: { brush: { type: ["lineX", "clear"] } } },
    series: rows.map((r, i) => ({
      name: r.name, type: "line", data: r.values, showSymbol: false, z: 5 - i * 0.1,
      lineStyle: { width: 2, color: r.color, type: DASHES[r.slot] }, itemStyle: { color: r.color },
      endLabel: { show: !narrow, formatter: "{a}", color: r.color, fontSize: 12, fontWeight: 500 },
      emphasis: { focus: "series" },
      ...(i === 0 ? { markLine: { symbol: "none", silent: true, animation: false, data: marks } } : {}),
    })),
  };
}

/** Presets for the picker.  `phases`: { region: { from_peak_pct } } of the chosen market; `cities`: the 70 city names. */
export function presets(phases, cities) {
  const byDrop = cities.filter((c) => phases[c]).sort((a, b) => phases[a].from_peak_pct - phases[b].from_peak_pct);
  return [
    { key: "tier1", label: "北上广深 + 全国", regions: ["全国", "北京", "上海", "广州", "深圳"] },
    { key: "tiers", label: "全国与三个层级", regions: ["全国", "一线", "二线", "三线"] },
    { key: "worst", label: "距高点跌得最多 5 城", regions: byDrop.slice(0, MAX_SERIES) },
    { key: "best", label: "距高点跌得最少 5 城", regions: byDrop.slice(-MAX_SERIES).reverse() },
  ];
}
