/* cn-housing-price-training demo — chart rendering.
   Loads pre-baked JSON from ./data/, renders ECharts. Palette follows the
   validated dataviz reference (blue/orange/aqua/yellow; blue↔red diverging
   with gray midpoint; sequential blue ramp). Dark values are the dark-surface
   steps of the same ramps, not an inverted flip. */

const ROOT = "data";
const JS_URL =
  "https://cdn.jsdelivr.net/npm/echarts@5.5.1/dist/echarts.min.js";
const ALT_URL =
  "https://unpkg.com/echarts@5.5.1/dist/echarts.min.js";

// Palette slots — kept in sync with styles.css.
const PALETTE = {
  light: {
    surface: "#fcfcfb", plane: "#f9f9f7", primary: "#0b0b0b",
    secondary: "#52514e", muted: "#898781", grid: "#e1e0d9",
    axis: "#c3c2b7", blue: "#2a78d6", orange: "#eb6834",
    aqua: "#1baf7a", yellow: "#eda100", de: "#a8a69e",
    good: "#006300", divergingMid: "#f0efec",
  },
  dark: {
    surface: "#1a1a19", plane: "#0d0d0d", primary: "#ffffff",
    secondary: "#c3c2b7", muted: "#898781", grid: "#2c2c2a",
    axis: "#383835", blue: "#3987e5", orange: "#d95926",
    aqua: "#199e70", yellow: "#c98500", de: "#6b6a64",
    good: "#0ca30c", divergingMid: "#383835",
  },
};

let C = PALETTE.light; // current colors (swapped on theme change)
let META = null;
let FC = null; // forecast_series
let COMP = null; // components
let CITIES = null; // cities_yoy
let DIST_SCEN = null; // district_scenarios (per-city)
let DIST_LIST = null; // district_listing
let LPR = null; // lpr
let MACRO = null; // macro panel
let MCMP = null; // market_compare
let OFFICIAL = null; // official signings
let charts = [];

function isDark() {
  const stamped = document.documentElement.dataset.theme;
  if (stamped === "dark" || stamped === "light") return stamped === "dark";
  return window.matchMedia("(prefers-color-scheme: dark)").matches;
}

function setTheme(dark) {
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  C = dark ? PALETTE.dark : PALETTE.light;
  document.getElementById("theme-label").textContent = dark ? "浅色" : "深色";
  charts.forEach((ch) => {
    const opt = ch.option();
    ch.instance.setOption(opt, true);
  });
}

function baseGrid() {
  return {
    left: 56, right: 24, top: 40, bottom: 44,
    containLabel: false,
  };
}

function baseTextStyle() {
  return { fontFamily: 'system-ui, -apple-system, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif' };
}

function baseTooltip(axis) {
  return {
    trigger: axis ? "axis" : "item",
    backgroundColor: C.surface,
    borderColor: C.axis,
    borderWidth: 1,
    textStyle: { color: C.primary, fontSize: 12.5 },
    axisPointer: axis ? { type: "line", lineStyle: { color: C.axis, type: "dashed" } } : undefined,
    confine: true,
  };
}

function baseAxis(extra) {
  return Object.assign(
    {
      axisLine: { lineStyle: { color: C.axis } },
      axisTick: { lineStyle: { color: C.axis } },
      axisLabel: { color: C.secondary, fontSize: 11.5 },
      splitLine: { lineStyle: { color: C.grid } },
    },
    extra || {}
  );
}

/* ---------- chart registry ---------- */
function register(el, name, optionBuilder) {
  const inst = echarts.init(el, null, { renderer: "canvas" });
  charts.push({ name, instance: inst, option: optionBuilder });
  inst.setOption(optionBuilder());
  return inst;
}

window.addEventListener("resize", () => {
  charts.forEach((ch) => ch.instance.resize());
});

/* ---------- load data ---------- */
async function loadJson(name) {
  const resp = await fetch(`${ROOT}/${name}`);
  if (!resp.ok) throw new Error(`${name}: HTTP ${resp.status}`);
  return resp.json();
}

/* ---------- section 1: hero ---------- */
function fmtCum(v) {
  return (v > 0 ? "+" : "") + v.toFixed(1) + "%";
}

function renderHero() {
  const setValue = (id, v, band) => {
    const el = document.getElementById(id);
    const val = el.querySelector(".value");
    const sub = el.querySelector(".sub");
    val.textContent = fmtCum(v);
    if (band) sub.innerHTML = `<span class="band">区间</span>&nbsp;${fmtCum(band[0])} ~ ${fmtCum(band[1])}`;
  };

  setValue("stat-nat-base", META.national.base_cum, [META.national.low_cum, META.national.high_cum]);
  setValue("stat-bj-base", META.beijing.base_cum, [META.beijing.low_cum, META.beijing.high_cum]);
  setValue("stat-nat-hist", META.cum60m.national);
  setValue("stat-bj-hist", META.cum60m.beijing);

  document.getElementById("coverage-note").textContent =
    `数据覆盖 ${META.coverage.cities} 个城市 · ${META.coverage.months} 个月（${META.coverage.start} – ${META.coverage.end}）· 锚点 ${META.anchor.slice(0, 7)} = 100`;
  document.getElementById("anchor-label").textContent = META.anchor.slice(0, 7);
}

/* ---------- section 2: forecast fan ---------- */
function fanChart(region) {
  const data = FC[region];
  const months = data.history.map((d) => d.m);
  const histVals = data.history.map((d) => d.v);
  const fcMonths = data.forecast.map((d) => d.m);
  const allMonths = months.concat(fcMonths);
  const gap = months.length; // history occupies [0, gap)

  // The uncertainty band is drawn as a stacked band on top of the LOW line:
  //   series "低情景" (transparent)  = low        → anchors the band base
  //   series "高情景" (filled)       = high - low → fills from low up to high
  //   series "基准情景" (line)       = base       → the base scenario path
  // Both band series share one stack id, in this order, so ECharts cumulates
  // from the axis: the fill spans [low, high] and the base line crosses it.
  const low = new Array(gap).fill(null).concat(data.forecast.map((d) => d.low));
  const band = new Array(gap).fill(null).concat(data.forecast.map((d) => d.high - d.low));
  const base = new Array(gap).fill(null).concat(data.forecast.map((d) => d.base));
  // History line: numeric index values for the history window, null in the
  // forecast window so the line ends at the anchor (2026-06).
  const histPad = histVals.concat(new Array(fcMonths.length).fill(null));

  // Y-domain must span BOTH the history (higher levels) and the forecast fan
  // (lower levels). With no explicit domain ECharts auto-zooms to the forecast
  // band and clips the history line off the top of the plot.
  const allVals = data.history.map((d) => d.v).concat(
    data.forecast.flatMap((d) => [d.base, d.low, d.high])
  );
  const yMin = Math.min(...allVals);
  const yMax = Math.max(...allVals);
  const yPad = (yMax - yMin) * 0.08;

  return {
    grid: baseGrid(),
    tooltip: Object.assign(baseTooltip(true), {
      formatter(params) {
        const idx = params[0].dataIndex;
        const m = allMonths[idx];
        const isFc = idx >= gap;
        let lines = `<b>${m}</b>`;
        params.forEach((p) => {
          if (p.value == null) return;
          lines += `<br/>${p.marker}${p.seriesName}: <b>${Number(p.value).toFixed(1)}</b>`;
        });
        return lines;
      },
    }),
    legend: {
      data: ["历史", "基准情景", "低情景", "高情景"],
      top: 6, left: 0,
      textStyle: { color: C.secondary, fontSize: 12 },
      itemWidth: 14, itemHeight: 8,
    },
    xAxis: baseAxis({
      type: "category",
      data: allMonths,
      boundaryGap: false,
      axisLabel: {
        color: C.secondary, fontSize: 11,
        // Label only each January, so each year appears once.
        interval: (idx, value) => value.endsWith("-01"),
        formatter: (v) => v.slice(0, 4),
      },
    }),
    yAxis: baseAxis({
      type: "value",
      min: yMin - yPad,
      max: yMax + yPad,
      axisLabel: { color: C.secondary, fontSize: 11 },
    }),
    series: [
      {
        name: "历史", type: "line", data: histPad, smooth: 0.15,
        showSymbol: false, lineStyle: { width: 2, color: C.blue },
        itemStyle: { color: C.blue },
      },
      {
        name: "低情景", type: "line", data: low, stack: "fan", smooth: 0.15,
        showSymbol: false, lineStyle: { width: 0 },
        itemStyle: { color: "transparent" }, silent: true,
        tooltip: { show: false }, z: 2,
      },
      {
        name: "高情景", type: "line", data: band, stack: "fan", smooth: 0.15,
        showSymbol: false, lineStyle: { width: 0 },
        areaStyle: { color: C.orange, opacity: 0.16 },
        itemStyle: { color: "transparent" }, silent: true,
        tooltip: { show: false }, z: 2,
      },
      {
        name: "基准情景", type: "line", data: base, smooth: 0.15,
        showSymbol: false, lineStyle: { width: 2.5, color: C.orange },
        itemStyle: { color: C.orange },
      },
    ],
  };
}

/* ---------- section 3: city heatmap ---------- */
function heatmapChart() {
  const colors = ["#cde2fb", "#86b6ef", "#2a78d6", "#1c5cab", "#104281"];
  return {
    grid: { left: 74, right: 16, top: 34, bottom: 44 },
    tooltip: Object.assign(baseTooltip(false), {
      formatter(p) {
        const v = p.value[2];
        return `${p.value[0]} · ${CITIES.months[p.value[1]]}<br/>同比：<b>${v == null ? "—" : v.toFixed(1)}</b>`;
      },
    }),
    xAxis: {
      type: "category",
      data: CITIES.months,
      axisLine: { lineStyle: { color: C.axis } },
      axisTick: { show: false },
      axisLabel: {
        color: C.secondary, fontSize: 10.5,
        interval: (idx, v) => v.endsWith("-01"),
        formatter: (v) => v.slice(0, 4),
      },
    },
    yAxis: {
      type: "category",
      data: CITIES.cities,
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: C.secondary, fontSize: 11 },
    },
    visualMap: {
      min: 85, max: 115, calculable: false,
      orient: "horizontal", left: "center", bottom: 0,
      inRange: { color: colors },
      text: ["高", "低"],
      textStyle: { color: C.secondary, fontSize: 11 },
    },
    series: [
      {
        type: "heatmap",
        data: [],
        label: { show: false },
        itemStyle: { borderWidth: 0, borderRadius: 1 },
        emphasis: { itemStyle: { shadowBlur: 6, shadowColor: "rgba(0,0,0,0.3)" } },
      },
    ],
  };
}

function heatmapData() {
  const out = [];
  CITIES.values.forEach((row, ri) => {
    row.series.forEach((v, ci) => {
      if (v != null) out.push([ri, ci, v]);
    });
  });
  return out;
}

/* ---------- section 3: city line (selected city) ---------- */
function cityLineChart(city) {
  const selected = city || CITIES.cities[0];
  const lineSeries = reorderCitySeries(selected);

  return {
    grid: baseGrid(),
    tooltip: Object.assign(baseTooltip(true), {
      formatter(params) {
        const m = CITIES.months[params[0].dataIndex];
        let lines = `<b>${m}</b>`;
        params.forEach((p) => {
          if (p.value == null) return;
          lines += `<br/>${p.marker}${p.seriesName}: <b>${Number(p.value).toFixed(1)}</b>`;
        });
        return lines;
      },
    }),
    legend: {
      type: "scroll", top: 0, left: 0, width: "82%",
      textStyle: { color: C.secondary, fontSize: 11 },
    },
    xAxis: baseAxis({
      type: "category",
      data: CITIES.months,
      boundaryGap: false,
      axisLabel: {
        color: C.secondary, fontSize: 11,
        interval: (idx, v) => v.endsWith("-01"),
        formatter: (v) => v.slice(0, 4),
      },
    }),
    yAxis: baseAxis({
      type: "value",
      scale: true,
      axisLabel: { color: C.secondary, fontSize: 11, formatter: "{value}" },
    }),
    series: lineSeries,
  };
}

/* ---------- section 4: component decomposition ---------- */
function componentChart(region) {
  const rows = COMP[region];
  const months = rows.map((r) => r.m);

  // The three components share the same ~100 MoM-index scale, so they are
  // drawn as separate lines, NOT stacked (stacking would sum them to ~298 on
  // the y-axis). The "加权和" is the true weighted forecast = r.base.
  const allVals = rows.flatMap((r) => [r.trend, r.reversion, r.season, r.base]);
  const yMin = Math.min(...allVals);
  const yMax = Math.max(...allVals);
  const yPad = Math.max((yMax - yMin) * 0.15, 0.1);

  return {
    grid: baseGrid(),
    tooltip: Object.assign(baseTooltip(true), {
      formatter(params) {
        const r = rows[params[0].dataIndex];
        let lines = `<b>${r.m}</b>`;
        params.forEach((p) => {
          if (p.value == null) return;
          lines += `<br/>${p.marker}${p.seriesName}: <b>${Number(p.value).toFixed(2)}</b>`;
        });
        lines += `<br/>加权和 = 预测环比：<b>${r.base.toFixed(2)}</b>`;
        return lines;
      },
    }),
    legend: {
      data: ["趋势延续", "均值回归", "季节性", "加权和"],
      top: 0, left: 0,
      textStyle: { color: C.secondary, fontSize: 12 },
      itemWidth: 14, itemHeight: 8,
    },
    xAxis: baseAxis({
      type: "category", data: months, boundaryGap: false,
      axisLabel: {
        color: C.secondary, fontSize: 11,
        interval: (idx, v) => v.endsWith("-01"),
        formatter: (v) => v.slice(0, 4),
      },
    }),
    yAxis: baseAxis({
      type: "value",
      min: yMin - yPad,
      max: yMax + yPad,
      axisLabel: { color: C.secondary, fontSize: 11 },
    }),
    series: [
      {
        name: "趋势延续", type: "line",
        data: rows.map((r) => r.trend), showSymbol: false,
        lineStyle: { width: 1.5, color: C.blue }, itemStyle: { color: C.blue },
      },
      {
        name: "均值回归", type: "line",
        data: rows.map((r) => r.reversion), showSymbol: false,
        lineStyle: { width: 1.5, color: C.orange }, itemStyle: { color: C.orange },
      },
      {
        name: "季节性", type: "line",
        data: rows.map((r) => r.season), showSymbol: false,
        lineStyle: { width: 1.5, color: C.aqua }, itemStyle: { color: C.aqua },
      },
      {
        name: "加权和", type: "line",
        data: rows.map((r) => r.base), showSymbol: false,
        lineStyle: { width: 2, color: C.primary, type: "dashed" },
        itemStyle: { color: C.primary },
      },
    ],
  };
}

/* ---------- section 5: district scenarios (北京 / 重庆) ---------- */
function districtChart(city) {
  const rows = (DIST_SCEN[city] || []).slice();
  const labels = rows.map((r) => r.district);
  return {
    grid: { left: 74, right: 30, top: 12, bottom: 36 },
    tooltip: Object.assign(baseTooltip(true), {
      formatter(params) {
        const r = rows[params[0].dataIndex];
        let lines = `<b>${r.district}</b>`;
        params.forEach((p) => {
          if (p.value == null) return;
          lines += `<br/>${p.marker}${p.seriesName}: <b>${Number(p.value).toLocaleString("zh-CN")} 元/㎡</b>`;
        });
        return lines;
      },
    }),
    legend: {
      data: ["2026 基准", "2030 基准", "2030 区间"],
      top: 0, right: 0,
      textStyle: { color: C.secondary, fontSize: 12 },
    },
    xAxis: {
      type: "category",
      data: labels,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: C.axis } },
      axisLabel: { color: C.secondary, fontSize: 11, interval: 0, rotate: 35 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: C.secondary, fontSize: 11, formatter: (v) => `${v / 10000} 万` },
      axisLine: { lineStyle: { color: C.axis } },
      splitLine: { lineStyle: { color: C.grid } },
    },
    series: [
      {
        name: "2030 区间", type: "custom",
        renderItem(params, api) {
          const idx = api.value(0);
          const low = api.coord([idx, rows[idx].low2030]);
          const high = api.coord([idx, rows[idx].high2030]);
          const width = Math.min(28, api.size([1, 0])[0] * 0.55);
          return {
            type: "rect",
            shape: { x: low[0] - width / 2, y: high[1], width, height: low[1] - high[1] },
            style: api.style({ fill: C.orange, opacity: 0.22 }),
          };
        },
        data: rows.map((_, i) => i),
        z: 1,
      },
      {
        name: "2026 基准", type: "bar",
        data: rows.map((r) => r.base2026),
        barGap: "-100%",
        itemStyle: { color: C.de },
        emphasis: { itemStyle: { color: C.de } },
      },
      {
        name: "2030 基准", type: "bar",
        data: rows.map((r) => r.base2030),
        itemStyle: { color: C.blue },
        emphasis: { itemStyle: { color: C.blue } },
      },
    ],
  };
}

/* ---------- section 5: district sparkline cards ---------- */
function sparkData(district) {
  const row = DIST_LIST.districts.find((d) => d.district === district);
  if (!row) return null;
  const pts = row.series.map((v, i) => (v == null ? null : [i, v])).filter((p) => p);
  const first = row.series.find((v) => v != null);
  const last = [...row.series].reverse().find((v) => v != null);
  return { row, pts, first, last, delta: last - first };
}

function renderSparks() {
  const grid = document.getElementById("district-sparks");
  grid.innerHTML = "";
  DIST_LIST.districts.forEach((d) => {
    const card = document.createElement("div");
    card.className = "spark-card";
    const { pts, last, delta } = sparkData(d.district);
    const down = delta <= 0;
    card.innerHTML = `
      <div class="spark-head">
        <span class="district">${d.district}区</span>
        <span class="price">${Number(last).toLocaleString("zh-CN")} 元/㎡</span>
      </div>
      <svg viewBox="0 0 300 52" preserveAspectRatio="none" aria-hidden="true"></svg>
      <div class="delta ${down ? "down" : "up"}">${delta >= 0 ? "+" : ""}${delta.toFixed(1)} 元/㎡（样本期）</div>
    `;
    grid.appendChild(card);

    const svg = card.querySelector("svg");
    const pad = 2;
    const min = Math.min(...pts.map((p) => p[1]));
    const max = Math.max(...pts.map((p) => p[1]));
    const span = Math.max(max - min, 1);
    const W = 300, H = 52;
    const x = (i) => (i / (DIST_LIST.months.length - 1)) * (W - pad * 2) + pad;
    const y = (v) => H - pad - ((v - min) / span) * (H - pad * 2);
    const pathD = pts.map((p, i) => `${i === 0 ? "M" : "L"}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join(" ");
    svg.innerHTML = `<path d="${pathD}" fill="none" stroke="${down ? C.orange : C.good}" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>`;
  });
}

/* ---------- section 6: macro ---------- */
function lprChart() {
  return {
    grid: baseGrid(),
    tooltip: baseTooltip(true),
    legend: {
      data: ["1 年期 LPR", "5 年期以上 LPR"],
      top: 0, left: 0,
      textStyle: { color: C.secondary, fontSize: 12 },
    },
    xAxis: baseAxis({
      type: "category", data: LPR.map((r) => r.m), boundaryGap: false,
      axisLabel: { color: C.secondary, fontSize: 11, interval: 11 },
    }),
    yAxis: baseAxis({
      type: "value", scale: true,
      axisLabel: { color: C.secondary, fontSize: 11, formatter: "{value}%" },
    }),
    series: [
      {
        name: "1 年期 LPR", type: "line",
        data: LPR.map((r) => r.lpr_1y), showSymbol: false,
        lineStyle: { width: 2, color: C.aqua }, itemStyle: { color: C.aqua },
      },
      {
        name: "5 年期以上 LPR", type: "line",
        data: LPR.map((r) => r.lpr_5y), showSymbol: false,
        lineStyle: { width: 2, color: C.blue }, itemStyle: { color: C.blue },
      },
    ],
  };
}

/* ---------- section 6b: macro panel with metric selector ---------- */
function macroChart(metricKey) {
  const months = MACRO.months;
  const metric = MACRO.metrics.find((m) => m.key === metricKey) || MACRO.metrics[0];
  const seriesData = MACRO.series[metric.key].map((v, i) => (v == null ? null : [months[i], v]));
  return {
    grid: Object.assign(baseGrid(), { right: 40 }),
    tooltip: Object.assign(baseTooltip(true), {
      formatter(params) {
        const idx = params[0].dataIndex;
        const m = months[idx];
        const yoy = MACRO.series[metric.key][idx];
        let lines = `<b>${m}</b><br/>${metric.label}：<b>${yoy == null ? "—" : yoy.toFixed(1) + "%"}</b>`;
        const inv = MACRO.inventory_wan_m2[idx];
        if (metric.key === "inventory_area_yoy" && inv != null) {
          lines += `<br/>待售面积（累计口径）：<b>${inv.toFixed(2)} 亿㎡</b>`;
        }
        return lines;
      },
    }),
    xAxis: baseAxis({
      type: "category", data: months, boundaryGap: false,
      axisLabel: { color: C.secondary, fontSize: 11, interval: 4 },
    }),
    yAxis: baseAxis({
      type: "value", scale: true,
      axisLabel: { color: C.secondary, fontSize: 11, formatter: "{value}%" },
      name: "%（同比）", nameTextStyle: { color: C.muted, fontSize: 11 },
    }),
    series: [
      {
        name: metric.label, type: "line",
        data: seriesData, showSymbol: false,
        lineStyle: { width: 2, color: C.blue }, itemStyle: { color: C.blue },
        markLine: {
          symbol: "none",
          lineStyle: { color: C.axis, type: "dashed" },
          data: [{ yAxis: 0 }],
          label: { show: false },
        },
      },
    ],
  };
}

/* ---------- section 6c: new vs second-hand comparison ---------- */
function marketCompareChart() {
  return {
    grid: baseGrid(),
    tooltip: Object.assign(baseTooltip(true), {
      formatter(params) {
        const idx = params[0].dataIndex;
        const m = MCMP.months[idx];
        let lines = `<b>${m}</b>`;
        params.forEach((p) => {
          if (p.value == null) return;
          lines += `<br/>${p.marker}${p.seriesName}: <b>${Number(p.value).toFixed(1)}</b>`;
        });
        return lines;
      },
    }),
    legend: {
      data: ["新建住宅", "二手住宅"],
      top: 0, left: 0,
      textStyle: { color: C.secondary, fontSize: 12 },
    },
    xAxis: baseAxis({
      type: "category", data: MCMP.months, boundaryGap: false,
      axisLabel: {
        color: C.secondary, fontSize: 11,
        interval: (idx, v) => v.endsWith("-01"),
        formatter: (v) => v.slice(0, 4),
      },
    }),
    yAxis: baseAxis({
      type: "value", scale: true,
      axisLabel: { color: C.secondary, fontSize: 11 },
    }),
    series: [
      {
        name: "新建住宅", type: "line",
        data: MCMP.new, showSymbol: false,
        lineStyle: { width: 2, color: C.aqua }, itemStyle: { color: C.aqua },
      },
      {
        name: "二手住宅", type: "line",
        data: MCMP.secondhand, showSymbol: false,
        lineStyle: { width: 2, color: C.blue }, itemStyle: { color: C.blue },
      },
    ],
  };
}

/* ---------- section 6d: official Beijing signings ---------- */
function officialChart() {
  const rows = OFFICIAL.districts;
  return {
    grid: { left: 60, right: 24, top: 30, bottom: 36 },
    tooltip: Object.assign(baseTooltip(true), {
      formatter(params) {
        const r = rows[params[0].dataIndex];
        return `<b>${r.district}</b><br/>网签套数：<b>${r.count.toLocaleString("zh-CN")}</b><br/>面积：${r.area_m2.toLocaleString("zh-CN")} ㎡`;
      },
    }),
    xAxis: baseAxis({
      type: "category", data: rows.map((r) => r.district),
      axisLabel: { color: C.secondary, fontSize: 11, interval: 0, rotate: 35 },
    }),
    yAxis: baseAxis({
      type: "value",
      axisLabel: { color: C.secondary, fontSize: 11 },
    }),
    series: [
      {
        name: "网签套数", type: "bar",
        data: rows.map((r) => r.count),
        barWidth: "55%",
        itemStyle: { color: C.blue, borderRadius: [3, 3, 0, 0] },
        label: { show: true, position: "top", fontSize: 10, color: C.secondary },
      },
    ],
  };
}

/* ---------- CIREA identity callout ---------- */
function renderCirea() {
  const el = document.getElementById("cirea-callout");
  if (!el) return;
  const c = META.cirea;
  el.innerHTML = `
    <div class="cirea-stat"><span class="big">${c.overlap_cells.toLocaleString("zh-CN")}</span> 个重叠单元</div>
    <div class="cirea-stat"><span class="big">r = ${c.r.toFixed(4)}</span> 相关系数</div>
    <div class="cirea-stat"><span class="big">${c.max_abs_diff === 0 ? "0.0" : c.max_abs_diff}</span> 最大绝对差（指数点）</div>
    <p class="cirea-note">${c.span} · 行业指数（CIREA 公开文档）与官方（国家统计局）二手住宅指数逐格一致 —— 行业指数是官方数据的转载，不是独立来源。这是论文"来源—口径感知构建"的核心发现。</p>
  `;
}

function renderOfficialTotal() {
  const el = document.getElementById("official-total");
  if (el && OFFICIAL) el.textContent = OFFICIAL.total_units.toLocaleString("zh-CN");
}

/* ---------- weights panel ---------- */
function renderWeights() {
  const weights = META.weights;
  const mk = (id, w, labels) => {
    const el = document.getElementById(id);
    const items = [
      ["趋势延续", w.trend, "fill-trend"],
      ["均值回归", w.reversion, "fill-reversion"],
      ["季节性", w.season, "fill-season"],
    ];
    el.innerHTML = "";
    items.forEach(([name, v, cls]) => {
      const row = document.createElement("div");
      row.className = "weight-bar";
      row.innerHTML = `
        <div class="row"><span>${name}</span><span class="pct">${(v * 100).toFixed(0)}%</span></div>
        <div class="track"><div class="fill ${cls}" style="width:${v * 100}%"></div></div>
      `;
      el.appendChild(row);
    });
    const note = el.parentElement.querySelector(".model-note");
    const r = META.reversion[id.includes("nat") ? "national" : "beijing"];
    note.innerHTML = `环比 AR(1) ρ = ${r.rho} · 回归半衰期 <b>${r.half_life_months} 个月</b> · 市场判断：<b>${id.includes("nat") ? "下行趋势市" : "均值回归市"}</b>`;
  };
  mk("weights-nat", weights.national, null);
  mk("weights-bj", weights.beijing, null);
}

/* ---------- filters ---------- */
function bindCityPicker() {
  const select = document.getElementById("city-picker");
  CITIES.cities.forEach((c) => {
    const opt = document.createElement("option");
    opt.value = c;
    opt.textContent = c;
    select.appendChild(opt);
  });
  select.addEventListener("change", () => {
    const ch = charts.find((c) => c.name === "city-line");
    if (ch) ch.instance.setOption(cityLineChart(select.value), true);
  });
}

function reorderCitySeries(city) {
  return CITIES.values
    .map((row) => {
      const isSel = row.city === city;
      return {
        name: row.city,
        type: "line",
        data: row.series,
        showSymbol: false,
        lineStyle: { width: isSel ? 2.5 : 1.1, color: isSel ? C.blue : C.de },
        itemStyle: { color: isSel ? C.blue : C.de },
        emphasis: { lineStyle: { width: 2.5 } },
        z: isSel ? 3 : 1,
      };
    })
    .sort((a, b) => (a.lineStyle.width === b.lineStyle.width ? 0 : a.lineStyle.width > b.lineStyle.width ? 1 : -1));
}

function bindSegButtons() {
  document.querySelectorAll(".seg[data-region]").forEach((seg) => {
    seg.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn || btn.classList.contains("active")) return;
      seg.querySelectorAll("button").forEach((b) => b.classList.remove("active", "alt"));
      btn.classList.add("active");
      if (btn.dataset.v === "北京") btn.classList.add("alt");
      const region = btn.dataset.v;
      const fan = charts.find((c) => c.name === "fan");
      if (fan) fan.instance.setOption(fanChart(region), true);
      const comp = charts.find((c) => c.name === "component");
      if (comp) comp.instance.setOption(componentChart(region), true);
    });
  });
}

function bindMacroPicker() {
  const select = document.getElementById("macro-picker");
  if (!select) return;
  MACRO.metrics.forEach((m) => {
    const opt = document.createElement("option");
    opt.value = m.key;
    opt.textContent = m.label;
    select.appendChild(opt);
  });
  select.addEventListener("change", () => {
    const ch = charts.find((c) => c.name === "macro");
    if (ch) ch.instance.setOption(macroChart(select.value), true);
  });
}

function bindDistrictPicker() {
  document.querySelectorAll(".seg[data-district-city]").forEach((seg) => {
    seg.addEventListener("click", (e) => {
      const btn = e.target.closest("button");
      if (!btn || btn.classList.contains("active")) return;
      seg.querySelectorAll("button").forEach((b) => b.classList.remove("active", "alt"));
      btn.classList.add("active");
      const city = btn.dataset.v;
      const ch = charts.find((c) => c.name === "district");
      if (ch) ch.instance.setOption(districtChart(city), true);
    });
  });
}

function bindThemeToggle() {
  const btn = document.getElementById("theme-toggle");
  btn.addEventListener("click", () => setTheme(!isDark()));
}

/* ---------- 口径说明 modal ---------- */
function bindDefsModal() {
  const backdrop = document.getElementById("defs-backdrop");
  const openBtn = document.getElementById("defs-open");
  const closeBtn = document.getElementById("defs-close");
  const okBtn = document.getElementById("defs-ok");
  if (!backdrop || !openBtn) return;

  function show() {
    backdrop.hidden = false;
    document.body.style.overflow = "hidden";
    const focusTarget = closeBtn || openBtn;
    if (focusTarget) focusTarget.focus();
  }
  function hide() {
    backdrop.hidden = true;
    document.body.style.overflow = "";
    openBtn.focus();
  }

  openBtn.addEventListener("click", show);
  closeBtn.addEventListener("click", hide);
  okBtn.addEventListener("click", hide);
  backdrop.addEventListener("click", (e) => {
    if (e.target === backdrop) hide();
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !backdrop.hidden) hide();
  });
}

/* ---------- boot ---------- */
async function boot() {
  try {
    const script = document.createElement("script");
    script.src = JS_URL;
    await new Promise((resolve, reject) => {
      script.onload = resolve;
      script.onerror = () => {
        const alt = document.createElement("script");
        alt.src = ALT_URL;
        alt.onload = resolve;
        alt.onerror = () => reject(new Error("ECharts 加载失败"));
        document.head.appendChild(alt);
      };
      document.head.appendChild(script);
    });
  } catch (e) {
    document.getElementById("boot-error").textContent =
      "无法加载图表库（echarts）——请检查网络连接后刷新。";
    document.getElementById("boot-error").style.display = "block";
    return;
  }

  try {
    [META, FC, COMP, CITIES, DIST_SCEN, DIST_LIST, LPR, MACRO, MCMP, OFFICIAL] = await Promise.all([
      loadJson("meta.json"),
      loadJson("forecast_series.json"),
      loadJson("components.json"),
      loadJson("cities_yoy.json"),
      loadJson("district_scenarios.json"),
      loadJson("district_listing.json"),
      loadJson("lpr.json"),
      loadJson("macro.json"),
      loadJson("market_compare.json"),
      loadJson("official.json"),
    ]);
  } catch (e) {
    document.getElementById("boot-error").textContent =
      "数据加载失败：" + e.message;
    document.getElementById("boot-error").style.display = "block";
    return;
  }

  setTheme(isDark());

  renderHero();
  renderWeights();
  renderSparks();
  renderCirea();
  renderOfficialTotal();
  bindThemeToggle();
  bindDefsModal();
  bindCityPicker();
  bindSegButtons();
  bindMacroPicker();
  bindDistrictPicker();

  // charts (named so filters can target them)
  register(document.getElementById("chart-fan"), "fan", () => fanChart("全国"));
  register(document.getElementById("chart-heat"), "heatmap", () => {
    const opt = heatmapChart();
    opt.series[0].data = heatmapData();
    return opt;
  });
  register(document.getElementById("chart-city"), "city-line", () =>
    cityLineChart(document.getElementById("city-picker").value || CITIES.cities[0])
  );
  register(document.getElementById("chart-component"), "component", () => componentChart("全国"));
  register(document.getElementById("chart-district"), "district", () => districtChart("北京"));
  register(document.getElementById("chart-lpr"), "lpr", lprChart);
  register(document.getElementById("chart-macro"), "macro", () => {
    const sel = document.getElementById("macro-picker");
    return macroChart(sel ? sel.value : "development_investment_yoy");
  });
  register(document.getElementById("chart-compare"), "compare", marketCompareChart);
  register(document.getElementById("chart-official"), "official", officialChart);
}

document.addEventListener("DOMContentLoaded", boot);
