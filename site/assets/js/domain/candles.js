/* Candles: synthetic OHLC from the monthly chain, and the Lightweight Charts
   backend.  An index has one value per month, no intramonth path, so candles are
   *constructed*, not observed: open = previous period's close, close = the
   period's last month, high/low = extremes of the period's monthly closes
   (and the open).  Monthly candles are therefore body-only. */

import { loadScript } from "../core/loader.js";
import { addMonths } from "../core/format.js";

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

export async function createCandleChart(el, theme) {
  await loadScript(LWC);
  const LW = window.LightweightCharts;
  const tok = theme.tok;
  const chart = LW.createChart(el, { autoSize: true, crosshair: { mode: LW.CrosshairMode.Normal } });
  const candle = chart.addCandlestickSeries({ priceLineVisible: false });
  const lineOpts = { priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
  const median = chart.addLineSeries({ ...lineOpts, lineWidth: 2, lineStyle: LW.LineStyle.Dashed });
  const lo = chart.addLineSeries({ ...lineOpts, lineWidth: 1, lineStyle: LW.LineStyle.Dotted });
  const hi = chart.addLineSeries({ ...lineOpts, lineWidth: 1, lineStyle: LW.LineStyle.Dotted });
  const nat = chart.addLineSeries({ ...lineOpts, lineWidth: 1 });
  const legend = document.createElement("div");
  legend.className = "lwc-legend";
  el.appendChild(legend);
  let lastCandles = [];

  function applyTheme() {
    const up = tok("orange"), down = tok("blue");   // 红涨蓝跌，与温度色一致
    chart.applyOptions({
      layout: { background: { type: "solid", color: "transparent" }, textColor: tok("ink-3"), fontFamily: getComputedStyle(document.body).fontFamily },
      grid: { vertLines: { color: tok("line") }, horzLines: { color: tok("line") } },
      rightPriceScale: { borderColor: tok("line-2") },
      timeScale: { borderColor: tok("line-2"), timeVisible: false, rightOffset: 2 },
    });
    candle.applyOptions({ upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down });
    median.applyOptions({ color: tok("gold") });
    lo.applyOptions({ color: tok("gold") });
    hi.applyOptions({ color: tok("gold") });
    nat.applyOptions({ color: tok("blue") });
  }
  applyTheme();

  chart.subscribeCrosshairMove((p) => {
    const c = p.seriesData && p.seriesData.get(candle);
    if (!c) { legend.textContent = ""; return; }
    legend.textContent = `${String(p.time).slice(0, 7)}  开 ${c.open.toFixed(1)}  高 ${c.high.toFixed(1)}  低 ${c.low.toFixed(1)}  收 ${c.close.toFixed(1)}`;
  });

  return {
    applyTheme,
    /** state: { candles, forecast|null, national|null, peak:{m,v}|null, breakMonth|null, rangeYears|"all", origin } */
    render(state) {
      lastCandles = state.candles;
      candle.setData(state.candles);
      const markers = [];
      if (state.peak) markers.push({ time: `${state.peak.m}-01`, position: "aboveBar", color: tok("gold"), shape: "arrowDown", text: `高点 ${state.peak.m}` });
      if (state.breakMonth) markers.push({ time: `${state.breakMonth}-01`, position: "belowBar", color: tok("ink-3"), shape: "square", text: "口径断点" });
      // markers must be sorted by time and attach to an existing candle time
      const times = new Set(state.candles.map((c) => c.time));
      candle.setMarkers(markers.map((m) => ({ ...m, time: nearest(state.candles, m.time) })).filter((m) => times.has(m.time)).sort((a, b) => (a.time < b.time ? -1 : 1)));
      const f = state.forecast;
      median.setData(f ? f.median : []); lo.setData(f ? f.lo : []); hi.setData(f ? f.hi : []);
      nat.setData(state.national || []);
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
