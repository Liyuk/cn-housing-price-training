/* Trend chart (line mode): a pure function from data to an ECharts option.
   No DOM and no globals -- the theme is passed in -- so it runs under node tests. */

import { pct, cls, addMonths } from "../core/format.js";
import { metricValues, METRIC_NAME } from "./series.js";

/** "2007-12 = 100" from cum.base ("2007-12 = 100（…）"). */
export const baseLabel = (cum) => (cum.base || "").split("（")[0] || "起点 = 100";

/** Display name of a region in chart titles, legends and tooltips. */
export const regionLabel = (region) => (region === "全国" ? "全国（70 城等权）" : ["一线", "二线", "三线"].includes(region) ? `${region}城市（等权）` : region);

export const SCENARIO_SHADE = "rgba(128,128,120,0.07)";
export const DEFAULT_ZONES = { reliable: 12, caution: 24 }; // overridden by the manifest (computed from the scorecard)

/** Runs of months where the trailing 6-month mean MoM change is positive (>= 3 months long). */
export function risingRuns(series, months) {
  const runs = [];
  let start = null;
  for (let i = 6; i < series.length; i++) {
    let s = 0;
    for (let k = i - 5; k <= i; k++) s += series[k] / series[k - 1] - 1;
    const rising = s / 6 > 0;
    if (rising && start === null) start = i;
    if ((!rising || i === series.length - 1) && start !== null) {
      const end = rising ? i : i - 1;
      if (end - start >= 2) runs.push([months[start], months[end]]);
      start = null;
    }
  }
  return runs;
}

/** Index of the first visible month for a range key ("all" or years). */
export function rangeStartIndex(range, histLen) {
  if (range === "all") return 0;
  return Math.max(0, histLen - 1 - Number(range) * 12);
}

/** Forecast quantile arrays rebased from "origin = 100" to the chain level at the origin. */
export function scaledFan(fan, now, horizon = fan.q500.length) {
  const k = now / 100;
  return Object.fromEntries(["q025", "q100", "q500", "q900", "q975"].map((q) => [q, fan[q].slice(0, horizon).map((v) => +(v * k).toFixed(2))]));
}

/**
 * @param data   { cum, fan }  as loaded from cum.json / fan.json
 * @param region 全国 | 一线 | 二线 | 三线 | city name (tiers have no fan: history only)
 * @param opts   { compare, compareNew, newHome, metric, range, from, to, horizon, brush, narrow, zones:{reliable,caution} }
 *               compare: add the national line; compareNew + newHome (cum_new.json): add the new-home line of the same region;
 *               metric: level | yoy | dd (forecast only under level); from/to: window in months (else `range`, last N years);
 *               horizon: forecast months to draw (0 = none, default all); brush: drag-select a window on the chart
 * @param theme  { tok(name) }
 */
export function buildTrendOption(data, region, { compare = false, compareNew = false, newHome = null, metric = "level", range = "all", from = null, to = null, horizon = null, brush = false, narrow = false, zones = DEFAULT_ZONES } = {}, theme) {
  const { cum, fan: fanAll } = data;
  const tok = theme.tok;
  const hm = cum.months, H = hm.length;
  const level = metric === "level";
  const levels = cum.series[region];
  const ph = cum.phases[region];
  const fanRaw = level ? fanAll.regions[region] || null : null;
  const F = fanRaw ? Math.min(horizon == null ? fanAll.fc_months.length : horizon, fanAll.fc_months.length) : 0;
  const fan = F > 0 ? fanRaw : null;
  const fm = fan ? fanAll.fc_months.slice(0, F) : [];
  const all = hm.concat(fm);
  const now = levels[H - 1];
  const pad = (n) => new Array(n).fill(null);
  const gold = tok("gold");
  const label = regionLabel(region);
  const i0 = from ? Math.max(0, hm.findIndex((m) => m >= from)) : rangeStartIndex(range, H);
  const iEnd = to && to < hm[H - 1] ? hm.findLastIndex((m) => m <= to) : all.length - 1;
  const show = (arr) => metricValues(arr, metric, i0);
  const histV = show(levels);
  const natV = show(cum.series["全国"]);
  const newLevels = newHome && newHome.series[region] && newHome.months.length === H ? newHome.series[region] : null;
  const newV = newLevels ? show(newLevels) : null;
  const fmt = level ? (v) => v.toFixed(1) : (v) => pct(v, 1);

  let q = null;
  const series = [];
  if (fan) {
    const sc = scaledFan(fan, now, F);
    q = Object.fromEntries(Object.entries(sc).map(([k, arr]) => { const a = pad(H).concat(arr); a[H - 1] = +now.toFixed(2); return [k, a]; }));
  }
  const slice = (arr, a, b) => arr.map((v, i) => (i >= a && i <= b ? v : null));
  const diff = (hi, lo) => hi.map((v, i) => (v == null ? null : +(v - lo[i]).toFixed(2)));
  const areaPair = (name, lo, hi, stack, opacity) => ([
    { name: "_" + stack, type: "line", data: lo, stack, symbol: "none", lineStyle: { width: 0 }, silent: true, tooltip: { show: false }, z: 1 },
    { name, type: "line", data: diff(hi, lo), stack, symbol: "none", lineStyle: { width: 0 }, areaStyle: { color: gold, opacity },
      itemStyle: { color: gold }, silent: true, tooltip: { show: false }, z: 1 },
  ]);

  const runs = risingRuns(levels, hm);
  const areas = runs.map(([a, b]) => [{ xAxis: a, itemStyle: { color: tok("phase") } }, { xAxis: b }]);
  if (fan && zones.caution < F) {
    areas.push([{ xAxis: fm[zones.caution], name: "情景区", label: { show: true, position: "insideTop", color: tok("ink-3"), fontSize: 11.5,
      formatter: "情景区" }, itemStyle: { color: SCENARIO_SHADE } }, { xAxis: fm[F - 1] }]);
  }
  const rb = cum.regime_break && hm.includes(cum.regime_break.month) ? cum.regime_break.month : null;
  const markLines = level
    ? [{ yAxis: now, lineStyle: { type: "dashed", color: gold, opacity: 0.55, width: 1 },
        label: { show: true, position: "insideStartTop", color: tok("gold-ink"), fontSize: 11.5,
          formatter: narrow ? `现价位 ${now.toFixed(0)}` : ph.back_to ? `现价位 ${now.toFixed(1)} = ${ph.back_to} 的水平` : `现价位 ${now.toFixed(1)}` } }]
    : [{ yAxis: 0, lineStyle: { type: "dashed", color: tok("ink-3"), opacity: 0.7, width: 1 }, label: { show: false } }];
  if (fan) {
    markLines.push({ xAxis: hm[H - 1], lineStyle: { type: "solid", color: tok("line-2"), width: 1 },
      label: { show: !narrow, position: "insideEndTop", color: tok("ink-3"), fontSize: 11.5, formatter: "数据截止 " + hm[H - 1] } });
  }
  if (rb) {
    markLines.push({ xAxis: rb, lineStyle: { type: "dotted", color: tok("ink-3"), width: 1 },
      label: { show: !narrow, position: "insideStartTop", color: tok("ink-3"), fontSize: 11, formatter: "口径断点 " + rb } });
  }

  series.push({
    name: "历史", type: "line", data: histV.concat(pad(F)), showSymbol: false, z: 5,
    lineStyle: { width: 2.2, color: gold }, itemStyle: { color: gold },
    markArea: { silent: true, data: areas },
    markLine: { symbol: "none", silent: true, animation: false, data: markLines },
    ...(level ? { markPoint: { symbol: "circle", symbolSize: 8, silent: true, itemStyle: { color: gold, borderColor: tok("panel"), borderWidth: 2 },
      label: { show: true, position: "top", color: tok("ink-2"), fontSize: 11.5, formatter: () => `高点 ${ph.peak.m}（${ph.peak.v.toFixed(0)}）` },
      data: [{ coord: [ph.peak.m, ph.peak.v] }] } } : {}),
  });
  const showCompare = compare && region !== "全国";
  if (showCompare) {
    series.push({ name: "全国", type: "line", data: natV.concat(pad(F)), showSymbol: false, z: 4,
      lineStyle: { width: 1.6, color: tok("blue") }, itemStyle: { color: tok("blue") } });
  }
  const showNew = compareNew && !!newV;
  if (showNew) {
    series.push({ name: "新房", type: "line", data: newV.concat(pad(F)), showSymbol: false, z: 4,
      lineStyle: { width: 1.6, color: tok("aqua"), type: "dashed" }, itemStyle: { color: tok("aqua") } });
  }
  if (fan) {
    const a0 = H - 1, aRel = H - 1 + zones.reliable, aCau = H - 1 + zones.caution, aEnd = H + F - 1;
    series.push(
      ...areaPair("95% 区间", q.q025, q.q975, "b95", 0.1),
      ...areaPair("80% 区间", slice(q.q100, a0, aRel), slice(q.q900, a0, aRel), "b80c", 0.3),
      ...areaPair("80% 区间", slice(q.q100, aRel, aCau), slice(q.q900, aRel, aCau), "b80m", 0.2),
      ...areaPair("80% 区间", slice(q.q100, aCau, aEnd), slice(q.q900, aCau, aEnd), "b80s", 0.1),
      { name: "预测中位数", type: "line", data: q.q500, showSymbol: false, z: 6, lineStyle: { width: 2, color: gold, type: "dashed" }, itemStyle: { color: gold } },
    );
  }
  const legend = fan ? ["历史", "预测中位数", "80% 区间", "95% 区间"] : ["历史"];
  if (showCompare) legend.splice(1, 0, "全国");
  if (showNew) legend.splice(showCompare ? 2 : 1, 0, "新房");
  const yName = level ? `指数（${baseLabel(cum)}）` : metric === "yoy" ? "同比（%）" : "距窗口内高点（%）";
  const histName = level ? label : `${label}（${METRIC_NAME[metric]}）`;

  return {
    animationDuration: 400,
    grid: { left: 44, right: 12, top: narrow ? 78 : 56, bottom: 30 },
    legend: { data: legend, top: 0, left: 0, itemWidth: 14, itemHeight: 8, itemGap: 16, textStyle: { color: tok("ink-2"), fontSize: 12 } },
    tooltip: {
      trigger: "axis", confine: true, backgroundColor: tok("panel"), borderColor: tok("line-2"), borderWidth: 1,
      textStyle: { color: tok("ink"), fontSize: 12.5 }, extraCssText: "border-radius:8px;box-shadow:0 8px 24px rgba(0,0,0,.25);",
      axisPointer: { type: "cross", lineStyle: { color: tok("ink-3"), width: 1 }, crossStyle: { color: tok("ink-3"), width: 1 },
        label: { backgroundColor: tok("foreground"), color: tok("background"), fontSize: 11, padding: [3, 6], borderRadius: 3 } },
      formatter(params) {
        const i = params[0].dataIndex, m = all[i];
        if (i < H) {
          const v = histV[i];
          let s = `<b>${m}</b><br/>${histName}：<b>${v == null ? "—" : fmt(v)}</b>`;
          if (level && i > 0) s += `（环比 ${pct((levels[i] / levels[i - 1] - 1) * 100, 2)}）`;
          if (showCompare) s += `<br/><span style="color:${tok("blue")}">●</span> 全国：<b>${natV[i] == null ? "—" : fmt(natV[i])}</b>`;
          if (showNew) s += `<br/><span style="color:${tok("aqua")}">●</span> 新房：<b>${newV[i] == null ? "—" : fmt(newV[i])}</b>`;
          return s;
        }
        const h = i - H + 1, c = (k) => pct(fan[k][h - 1] - 100, 1);
        return `<b>${m}</b> · +${h} 个月${h > zones.caution ? "（情景）" : h > zones.reliable ? "（谨慎参考）" : ""}<br/>中位数：<b>${q.q500[i].toFixed(1)}</b>（${c("q500")}）<br/>80% 区间：${c("q100")} ~ ${c("q900")}<br/>95% 区间：${c("q025")} ~ ${c("q975")}`;
      },
    },
    xAxis: {
      type: "category", data: all, boundaryGap: false, axisLine: { lineStyle: { color: tok("line-2") } }, axisTick: { show: false }, splitLine: { show: false },
      axisLabel: { color: tok("ink-3"), fontSize: 11.5, hideOverlap: true, interval: (i, v) => v.endsWith("-01"), formatter: (v) => v.slice(0, 4) },
      axisPointer: { label: { formatter: ({ value }) => value } },
    },
    yAxis: { type: "value", scale: true, axisLine: { show: false }, axisTick: { show: false }, splitLine: { lineStyle: { color: tok("line") } },
      name: yName, nameLocation: "end", nameGap: 12, nameTextStyle: { color: tok("ink-3"), fontSize: 11.5, align: "left", padding: [0, 0, 0, -40] },
      axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: level ? (v) => v.toFixed(0) : (v) => `${v.toFixed(0)}%` },
      axisPointer: { label: { formatter: ({ value }) => (level ? (+value).toFixed(1) : `${(+value).toFixed(1)}%`) } } },
    dataZoom: [{ type: "slider", show: false, startValue: all[i0], endValue: all[Math.min(iEnd, all.length - 1)] }],
    ...(brush ? {
      brush: { xAxisIndex: 0, brushType: "lineX", brushMode: "single", throttleType: "debounce", throttleDelay: 120, removeOnClick: false, transformable: false,
        brushStyle: { color: tok("phase"), borderColor: gold, borderWidth: 1 } },
      toolbox: { show: false, feature: { brush: { type: ["lineX", "clear"] } } },
    } : {}),
    series,
  };
}

/** Forecast data table (HTML string) for a region; empty string when the region has no fan. */
export function fanTable(fanAll, region, origin, zones = DEFAULT_ZONES) {
  const fan = fanAll.regions[region];
  if (!fan) return "";
  const rows = [1, 3, 6, 12, 24, 36, 48, 60].filter((h) => h <= fanAll.fc_months.length).map((h) => {
    const c = (k) => pct(fan[k][h - 1] - 100, 1);
    const zone = h <= zones.reliable ? "可作预测" : h <= zones.caution ? "谨慎参考" : "仅作情景";
    return `<tr><td>${fanAll.fc_months[h - 1]}（+${h} 个月）</td><td class="${cls(fan.q500[h - 1] - 100)}"><b>${c("q500")}</b></td><td>${c("q100")} ~ ${c("q900")}</td><td>${c("q025")} ~ ${c("q975")}</td><td>${zone}</td></tr>`;
  }).join("");
  return `<table class="plain"><thead><tr><th>月份（相对 ${origin} 的变化）</th><th>中位数</th><th>80% 区间</th><th>95% 区间</th><th>可信度</th></tr></thead><tbody>${rows}</tbody></table>`;
}
