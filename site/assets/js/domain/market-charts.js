/* Option builders for the stats page: tier comparison, breadth, heatmap,
   new-vs-second-hand, macro and LPR.  Each takes its bundle and returns an
   ECharts option; colour comes from tokens. */

import { tok } from "../core/theme.js";
import { kit } from "../core/charts.js";
import { pct } from "../core/format.js";

export function tiersOption(cum) {
  const names = ["全国", "一线", "二线", "三线"];
  const colors = [tok("gold"), tok("orange"), tok("blue"), tok("ink-3")];
  const m = cum.months;
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 44, right: 12, top: 34, bottom: 28 },
    legend: kit.legend(names),
    tooltip: Object.assign(kit.tooltip(), {
      formatter: (p) => `<b>${m[p[0].dataIndex]}</b>` + p.map((x) => `<br/>${x.marker}${x.seriesName}：<b>${x.value.toFixed(1)}</b>`).join(""),
    }),
    xAxis: kit.yearAxis(m),
    yAxis: kit.valueAxis({ scale: true, axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: (v) => v.toFixed(0) } }),
    series: names.map((n, i) => ({
      name: n, type: "line", data: cum.series[n], showSymbol: false, lineStyle: { width: n === "全国" ? 2.4 : 1.6, color: colors[i] }, itemStyle: { color: colors[i] },
      markLine: i === 0 && cum.regime_break ? { symbol: "none", silent: true, data: [{ xAxis: cum.regime_break.month, lineStyle: { type: "dotted", color: tok("ink-3") },
        label: { color: tok("ink-3"), fontSize: 11, formatter: "口径断点 " + cum.regime_break.month, position: "insideStartTop" } }] } : undefined,
    })),
  };
}

export function breadthOption(b) {
  const lastI = b.months.length - 1;
  const recent = b.up_mom.reduce((best, v, i) => (b.months[i] >= b.months[lastI - 11] && v >= b.up_mom[best] ? i : best), lastI);
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 40, right: 16, top: 24, bottom: 28 },
    tooltip: Object.assign(kit.tooltip(), {
      formatter: (p) => `<b>${b.months[p[0].dataIndex]}</b><br/>环比上涨：<b>${p[0].value}</b> / ${b.n[p[0].dataIndex]} 城<br/>同比上涨：${b.up_yoy[p[0].dataIndex]} 城`,
    }),
    xAxis: kit.yearAxis(b.months, { boundaryGap: true }),
    yAxis: kit.valueAxis({ min: 0, max: 70, interval: 10 }),
    series: [{
      name: "环比上涨城市数", type: "bar", data: b.up_mom, barWidth: "72%", itemStyle: { color: tok("orange"), borderRadius: [2, 2, 0, 0] },
      markLine: { symbol: "none", silent: true, data: [{ yAxis: 35, lineStyle: { color: tok("ink-3"), type: "dashed", width: 1 }, label: { formatter: "半数城市", color: tok("ink-3"), fontSize: 11.5, position: "insideEndTop" } }] },
      markPoint: { symbol: "pin", symbolSize: 34, silent: true, itemStyle: { color: tok("gold") }, label: { color: "#fff", fontSize: 11 },
        data: [{ coord: [b.months[recent], b.up_mom[recent]], value: b.up_mom[recent] }, { coord: [b.months[lastI], b.up_mom[lastI]], value: b.up_mom[lastI] }] },
    }],
  };
}

export function heatOption(c) {
  const data = [];
  c.values.forEach((row, ri) => row.series.forEach((v, ci) => { if (v != null) data.push([ci, ri, v]); }));
  return {
    animation: false, textStyle: kit.text(),
    grid: { left: 62, right: 14, top: 8, bottom: 56 },
    tooltip: Object.assign(kit.tooltip("item"), { formatter: (p) => `<b>${c.cities[p.value[1]]}</b> · ${c.months[p.value[0]]}<br/>同比：<b>${p.value[2].toFixed(1)}</b>（${pct(p.value[2] - 100)}）` }),
    xAxis: Object.assign(kit.axis(), { type: "category", data: c.months, splitLine: { show: false },
      axisLabel: { color: tok("ink-3"), fontSize: 11, interval: (i, v) => v.endsWith("-01") && Number(v.slice(0, 4)) % 2 === 0, formatter: (v) => v.slice(0, 4) } }),
    yAxis: Object.assign(kit.axis(), { type: "category", data: c.cities, inverse: true, splitLine: { show: false }, axisLine: { show: false }, axisLabel: { color: tok("ink-2"), fontSize: 10, interval: 0 } }),
    visualMap: { min: 85, max: 115, calculable: false, orient: "horizontal", left: "center", bottom: 4, itemWidth: 12, itemHeight: 220,
      text: ["同比高", "低"], textStyle: { color: tok("ink-2"), fontSize: 11.5 }, inRange: { color: [tok("cold"), tok("cool"), tok("mid"), tok("warm"), tok("hot")] } },
    series: [{ type: "heatmap", data, progressive: 4000, itemStyle: { borderWidth: 0 }, emphasis: { itemStyle: { borderColor: tok("ink"), borderWidth: 1 } } }],
  };
}

export function compareOption(M) {
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 44, right: 14, top: 34, bottom: 26 },
    legend: kit.legend(["新建住宅", "二手住宅"]),
    tooltip: Object.assign(kit.tooltip(), { formatter: (p) => `<b>${M.months[p[0].dataIndex]}</b>` + p.filter((x) => x.value != null).map((x) => `<br/>${x.marker}${x.seriesName}：<b>${x.value.toFixed(1)}</b>`).join("") }),
    xAxis: kit.yearAxis(M.months),
    yAxis: kit.valueAxis({ scale: true }),
    series: [
      { name: "新建住宅", type: "line", data: M.new, showSymbol: false, lineStyle: { width: 1.6, color: tok("blue") }, itemStyle: { color: tok("blue") } },
      { name: "二手住宅", type: "line", data: M.secondhand, showSymbol: false, lineStyle: { width: 1.6, color: tok("gold") }, itemStyle: { color: tok("gold") } },
    ],
  };
}

export function macroOption(M, key) {
  const metric = M.metrics.find((x) => x.key === key) || M.metrics[0];
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 52, right: 18, top: 24, bottom: 28 },
    tooltip: Object.assign(kit.tooltip(), { formatter: (p) => {
      const i = p[0].dataIndex, v = M.series[metric.key][i];
      let s = `<b>${M.months[i]}</b>（1–${Number(M.months[i].slice(5))} 月累计）<br/>${metric.label}：<b>${v == null ? "—" : pct(v)}</b>`;
      if (metric.key === "inventory_area_yoy" && M.inventory_wan_m2[i] != null) s += `<br/>待售面积：<b>${M.inventory_wan_m2[i].toFixed(2)} 亿㎡</b>`;
      return s;
    } }),
    xAxis: kit.yearAxis(M.months),
    yAxis: kit.valueAxis({ scale: true, axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: "{value}%" } }),
    series: [{ type: "line", data: M.series[metric.key], showSymbol: false, lineStyle: { width: 2, color: tok("blue") }, itemStyle: { color: tok("blue") },
      markLine: { symbol: "none", silent: true, data: [{ yAxis: 0, lineStyle: { color: tok("ink-3"), type: "dashed" }, label: { show: false } }] } }],
  };
}

export function lprOption(L) {
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 44, right: 14, top: 34, bottom: 26 },
    legend: kit.legend(["1 年期 LPR", "5 年期以上 LPR"]),
    tooltip: kit.tooltip(),
    xAxis: Object.assign(kit.axis(), { type: "category", data: L.map((r) => r.m), boundaryGap: false, splitLine: { show: false }, axisLabel: { color: tok("ink-3"), fontSize: 11.5, interval: 11, formatter: (v) => v.slice(0, 4) } }),
    yAxis: kit.valueAxis({ scale: true, axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: "{value}%" } }),
    series: [
      { name: "1 年期 LPR", type: "line", step: "end", data: L.map((r) => r.lpr_1y), showSymbol: false, lineStyle: { width: 2, color: tok("gold") }, itemStyle: { color: tok("gold") } },
      { name: "5 年期以上 LPR", type: "line", step: "end", data: L.map((r) => r.lpr_5y), showSymbol: false, lineStyle: { width: 2, color: tok("blue") }, itemStyle: { color: tok("blue") } },
    ],
  };
}

/** Zoom a category-axis option to a window (months resolved against this chart's own `months`).  The slider is hidden:
 *  the window is controlled from outside.  A window that misses the series entirely draws a message, not stray points. */
export function withWindow(option, months, w) {
  if (w.outside) {
    return { ...option, series: (option.series || []).map((s) => ({ ...s, data: [], markLine: undefined, markPoint: undefined })), legend: undefined,
      graphic: [{ type: "text", left: "center", top: "middle", style: { text: `所选区间内没有数据（本图 ${months[0]} 至 ${months[months.length - 1]}）`, fill: tok("ink-3"), fontSize: 13 } }] };
  }
  return { ...option, dataZoom: [{ type: "slider", show: false, xAxisIndex: 0, startValue: months[w.i0], endValue: months[w.i1] }] };
}
