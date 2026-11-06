/* Candles: synthetic OHLC from the monthly chain, and the Lightweight Charts
   backend.  An index has one value per month, no intramonth path, so candles are
   *constructed*, not observed: open = previous period's close, close = the
   period's last month, high/low = extremes of the period's monthly closes
   (and the open).  Monthly candles are therefore body-only. */

import { loadScript } from "../core/loader.js";
import { addMonths, pct } from "../core/format.js";
import { risingRuns, SCENARIO_SHADE, DEFAULT_ZONES } from "./trend-chart.js";

const LWC = ["https://cdn.jsdelivr.net/npm/lightweight-charts@4.2.3/dist/lightweight-charts.standalone.production.js"];

function periodStart(ym, period) {
  const [y, m] = ym.split("-").map(Number);
  if (period === "Y") return `${y}-01-01`;
  if (period === "Q") return `${y}-${String(Math.floor((m - 1) / 3) * 3 + 1).padStart(2, "0")}-01`;
  return `${ym}-01`;
}
const key = (ym, period) => (period === "Y" ? ym.slice(0, 4) : period === "Q" ? `${ym.slice(0, 4)}Q${Math.floor((+ym.slice(5, 7) - 1) / 3)}` : ym);
const r2 = (v) => Math.round(v * 100) / 100;

/** @param period "M" | "Q" | "Y" ; base: level before the first month (the chain base). */
export function aggregateOhlc(months, values, period = "M", base = 100) {
  const out = [];
  let prevClose = base, cur = null;
  const flush = () => { if (cur) { out.push({ time: periodStart(cur.first, period), open: r2(cur.open), high: r2(cur.high), low: r2(cur.low), close: r2(cur.close) }); prevClose = cur.close; } };
  months.forEach((m, i) => {
    const k = key(m, period), v = values[i];
    if (!cur || cur.k !== k) {
      flush();
      cur = { k, first: m, open: prevClose, high: Math.max(prevClose, v), low: Math.min(prevClose, v), close: v };
    } else {
      cur.high = Math.max(cur.high, v); cur.low = Math.min(cur.low, v); cur.close = v;
    }
  });
  flush();
  return out;
}

/** Forecast lines as {time,value} points, starting from the origin so they connect to the last candle. */
export function forecastLines(fanAll, fan, originMonth, now) {
  const k = now / 100, months = fanAll.fc_months;
  const mk = (arr) => [{ time: `${originMonth}-01`, value: r2(now) }].concat(arr.map((v, i) => ({ time: `${months[i]}-01`, value: r2(v * k) })));
  return { median: mk(fan.q500), lo: mk(fan.q100), hi: mk(fan.q900) };
}

/** Key for the K-line chart: every mark the chart draws, in one row (the line chart carries its own legend). */
export function candleKey({ compare = false, forecast = false, zones = DEFAULT_ZONES, period = "Q" } = {}) {
  const k = (cls, text) => `<span class="k"><i class="sw ${cls}"></i>${text}</span>`;
  const unit = { M: "月", Q: "季", Y: "年" }[period];
  return [
    k("up", `上涨${unit}（收盘高于开盘）`), k("down", `下跌${unit}`),
    k("phase", "上行阶段（近 6 个月平均环比 &gt; 0）"),
    ...(forecast ? [k("median", "预测中位数"), k("band", "80% 区间上/下沿"), k("scn", `情景区（+${zones.caution} 个月后，仅作情景）`)] : []),
    ...(compare ? [k("nat", "全国")] : []),
    `<span class="k note">开 = 上期收，收 = 期末，高/低 = 期内月度极值；预测线标注为相对现价位的变化</span>`,
  ].join("");
}

/** Label of the candle period starting at `time` ("2026-07-01" -> "2026 Q3" for quarters). */
export function periodLabel(time, period) {
  const [y, m] = time.split("-");
  if (period === "Y") return y;
  if (period === "Q") return `${y} Q${Math.floor((+m - 1) / 3) + 1}`;
  return `${y}-${m}`;
}

const ZONE_NAME = (h, zones) => (h > zones.caution ? "仅作情景" : h > zones.reliable ? "谨慎参考" : "可作预测");

/** Full-height background blocks as area points (value 1; a whitespace point ends each run):
 *  phase = rising runs of the history, scenario = the forecast months past the cautious zone. */
export function shadeBlocks(series, months, fcMonths, zones) {
  const phase = [];
  for (const [a, b] of risingRuns(series, months)) {
    for (let m = a; m <= b; m = addMonths(m, 1)) phase.push({ time: `${m}-01`, value: 1 });
    phase.push({ time: `${addMonths(b, 1)}-01` });
  }
  const scenario = fcMonths.length && zones && zones.caution < fcMonths.length
    ? fcMonths.slice(zones.caution).map((m) => ({ time: `${m}-01`, value: 1 }))
    : [];
  return { phase, scenario };
}

/** Hover read-out.  hist: {time, open, high, low, close}|null; fc: {h, median, lo, hi}|null; national: close|null. */
export function readout({ hist, fc, national, period, now, zones }) {
  if (hist) {
    const chg = (hist.close / hist.open - 1) * 100;
    let s = `${periodLabel(hist.time, period)}  开 ${hist.open.toFixed(1)}  高 ${hist.high.toFixed(1)}  低 ${hist.low.toFixed(1)}  收 ${hist.close.toFixed(1)}  涨跌 ${pct(chg, 2)}`;
    if (national != null) s += `  全国 ${national.toFixed(1)}`;
    return s;
  }
  if (fc) {
    const rel = (v) => pct((v / now - 1) * 100, 1);
    return `${fc.time.slice(0, 7)} · +${fc.h} 个月（${ZONE_NAME(fc.h, zones)}）  中位数 ${fc.median.toFixed(1)}（${rel(fc.median)}）  80% 区间 ${rel(fc.lo)} ~ ${rel(fc.hi)}`;
  }
  return "";
}

/** Lightweight Charts parses only rgb/hex/legacy hsl; the design tokens use `hsl(240 4% 46%)`, so resolve through the browser. */
function resolveColor(value) {
  const probe = document.createElement("span");
  probe.style.color = value;
  document.body.appendChild(probe);
  const rgb = getComputedStyle(probe).color;
  probe.remove();
  return rgb;
}

export async function createCandleChart(el, theme) {
  await loadScript(LWC);
  const LW = window.LightweightCharts;
  const tok = (name) => resolveColor(theme.tok(name));
  const ymd = (t) => (typeof t === "string" ? t : typeof t === "number" ? new Date(t * 1000).toISOString() : `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`).slice(0, 10);
  const chart = LW.createChart(el, {
    autoSize: true, crosshair: { mode: LW.CrosshairMode.Normal },
    localization: { timeFormatter: (t) => ymd(t).slice(0, 7) },
  });
  // background blocks first so everything else draws on top; value 1 on a fixed 0..1 scale = full pane height
  const shadeOpts = { priceScaleId: "shade", priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, lineVisible: false,
    autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 1 } }) };
  const phaseShade = chart.addAreaSeries(shadeOpts);
  const scenarioShade = chart.addAreaSeries(shadeOpts);
  chart.priceScale("shade").applyOptions({ scaleMargins: { top: 0, bottom: 0 }, visible: false });
  const candle = chart.addCandlestickSeries({ priceLineVisible: false, lastValueVisible: false });
  const lineOpts = { priceLineVisible: false, crosshairMarkerVisible: false };
  const median = chart.addLineSeries({ ...lineOpts, lineWidth: 2, lineStyle: LW.LineStyle.Dashed, title: "预测中位数" });
  const lo = chart.addLineSeries({ ...lineOpts, lineWidth: 1, lineStyle: LW.LineStyle.Dotted, title: "80% 下沿" });
  const hi = chart.addLineSeries({ ...lineOpts, lineWidth: 1, lineStyle: LW.LineStyle.Dotted, title: "80% 上沿" });
  const nat = chart.addLineSeries({ ...lineOpts, lineWidth: 1, title: "全国", lastValueVisible: true });
  const legend = document.createElement("div");
  legend.className = "lwc-legend";
  el.appendChild(legend);
  let ctx = null, nowLine = null;

  function applyTheme() {
    const up = tok("orange"), down = tok("blue");   // 红涨蓝跌，与温度色一致
    chart.applyOptions({
      layout: { background: { type: "solid", color: "transparent" }, textColor: tok("ink-3"), fontFamily: getComputedStyle(document.body).fontFamily },
      grid: { vertLines: { color: tok("line") }, horzLines: { color: tok("line") } },
      rightPriceScale: { borderColor: tok("line-2") },
      timeScale: { borderColor: tok("line-2"), timeVisible: false, rightOffset: 2, tickMarkFormatter: (t, type) => (type === 0 ? ymd(t).slice(0, 4) : ymd(t).slice(0, 7)) },
    });
    const tint = (c) => ({ topColor: c, bottomColor: c });
    phaseShade.applyOptions(tint(tok("phase")));
    scenarioShade.applyOptions(tint(SCENARIO_SHADE));
    candle.applyOptions({ upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down });
    median.applyOptions({ color: tok("gold") });
    lo.applyOptions({ color: tok("gold") });
    hi.applyOptions({ color: tok("gold") });
    nat.applyOptions({ color: tok("blue") });
    if (ctx) draw();
  }
  applyTheme();

  chart.subscribeCrosshairMove((p) => {
    if (!ctx || !p.time) { legend.textContent = ""; return; }
    const c = p.seriesData.get(candle);
    const t = String(p.time);
    if (c) {
      const n = p.seriesData.get(nat);
      legend.textContent = readout({ hist: { ...c, time: t }, national: n ? n.value : null, period: ctx.period, now: ctx.now, zones: ctx.zones });
      return;
    }
    const h = ctx.hOf.get(t), m = p.seriesData.get(median);
    legend.textContent = h && m ? readout({ fc: { time: t, h, median: m.value, lo: p.seriesData.get(lo).value, hi: p.seriesData.get(hi).value }, now: ctx.now, zones: ctx.zones }) : "";
  });

  function draw() {
    const { state } = ctx;
    const tokGold = tok("gold");
    candle.setData(state.candles);
    phaseShade.setData(state.shade.phase);
    scenarioShade.setData(state.shade.scenario);
    if (nowLine) candle.removePriceLine(nowLine);
    nowLine = candle.createPriceLine({ price: ctx.now, color: tokGold, lineWidth: 1, lineStyle: LW.LineStyle.Dashed, axisLabelVisible: true, title: "现价位" });
    // markers must be sorted by time and sit on an existing candle time
    const times = new Set(state.candles.map((c) => c.time));
    const last = state.candles[state.candles.length - 1].time;
    const markers = [];
    if (state.peak) markers.push({ time: nearest(state.candles, `${state.peak.m}-01`), position: "aboveBar", color: tokGold, shape: "arrowDown", text: `高点 ${state.peak.m}（${state.peak.v.toFixed(0)}）` });
    if (state.breakMonth) markers.push({ time: nearest(state.candles, `${state.breakMonth}-01`), position: "belowBar", color: tok("ink-3"), shape: "square", text: `口径断点 ${state.breakMonth}` });
    markers.push({ time: last, position: "belowBar", color: tok("ink-3"), shape: "circle", text: `数据截止 ${state.origin}` });
    candle.setMarkers(markers.filter((m) => times.has(m.time)).sort((a, b) => (a.time < b.time ? -1 : 1)));
    const f = state.forecast;
    median.setData(f ? f.median : []); lo.setData(f ? f.lo : []); hi.setData(f ? f.hi : []);
    for (const s of [median, lo, hi]) s.applyOptions({ lastValueVisible: !!f });
    nat.setData(state.national || []);
    nat.applyOptions({ lastValueVisible: !!state.national });
    if (f) {
      const z = ctx.zones, at = (h) => f.median[h] && { time: f.median[h].time, position: "aboveBar", color: tok("ink-3"), shape: "circle", text: `+${h} 个月` };
      median.setMarkers([z.reliable, z.caution].map(at).filter(Boolean));
    } else median.setMarkers([]);
  }

  return {
    applyTheme,
    /** state: { candles, shade, forecast|null, national|null, peak:{m,v}|null, breakMonth|null, rangeYears|"all", origin, period, zones } */
    render(state) {
      const f = state.forecast;
      ctx = {
        state, period: state.period, zones: state.zones || { reliable: 12, caution: 24 },
        now: state.candles[state.candles.length - 1].close,
        hOf: new Map((f ? f.median : []).map((p, i) => [p.time, i])),
      };
      draw();
      const first = state.candles[0].time;
      const end = f ? f.median[f.median.length - 1].time : state.candles[state.candles.length - 1].time;
      if (state.rangeYears === "all") chart.timeScale().fitContent();
      else {
        const from = `${addMonths(end.slice(0, 7), -12 * Number(state.rangeYears) - (f ? f.median.length - 1 : 0))}-01`;
        chart.timeScale().setVisibleRange({ from: from < first ? first : from, to: end });
      }
    },
    destroy() { chart.remove(); legend.remove(); },
  };
}

/** The candle whose period contains `time` (markers must sit on a candle time). */
function nearest(candles, time) {
  let hit = candles[0].time;
  for (const c of candles) { if (c.time <= time) hit = c.time; else break; }
  return hit;
}
