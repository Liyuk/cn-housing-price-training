/* Candles: synthetic OHLC from the monthly chain, and the Lightweight Charts
   backend.  An index has one value per month, no intramonth path, so candles are
   *constructed*, not observed: open = previous period's close, close = the
   period's last month, high/low = extremes of the period's monthly closes
   (and the open).  Monthly candles are therefore body-only. */

import { loadScript } from "../core/loader.js";
import { addMonths, pct, sgn, esc } from "../core/format.js";
import { risingRuns, SCENARIO_SHADE, DEFAULT_ZONES } from "./trend-chart.js";

const LWC = ["https://cdn.jsdelivr.net/npm/lightweight-charts@5.2.1/dist/lightweight-charts.standalone.production.js"];

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
export function forecastLines(fanAll, fan, originMonth, now, horizon = fanAll.fc_months.length) {
  const k = now / 100, months = fanAll.fc_months.slice(0, horizon);
  const mk = (arr) => [{ time: `${originMonth}-01`, value: r2(now) }].concat(arr.slice(0, horizon).map((v, i) => ({ time: `${months[i]}-01`, value: r2(v * k) })));
  return { median: mk(fan.q500), lo: mk(fan.q100), hi: mk(fan.q900) };
}

/** Key for the K-line chart: every mark the chart draws, in one row (the line chart carries its own legend). */
export function candleKey({ compare = false, compareNew = false, forecast = false, zones = DEFAULT_ZONES, period = "Q" } = {}) {
  const k = (cls, text) => `<span class="k"><i class="sw ${cls}"></i>${text}</span>`;
  const unit = { M: "月", Q: "季", Y: "年" }[period];
  return [
    k("up", `上涨${unit}（收盘高于开盘）`), k("down", `下跌${unit}`),
    k("phase", "上行阶段（近 6 个月平均环比 &gt; 0）"),
    ...(forecast ? [k("median", "预测中位数"), k("band", "80% 区间上/下沿"), k("scn", `情景区（+${zones.caution} 个月后，仅作情景）`)] : []),
    ...(compare ? [k("nat", "全国")] : []),
    ...(compareNew ? [k("new", "新房（同地区）")] : []),
    k("chg", `下方柱：每${unit}涨跌幅`),
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

/** What the top-left data bar shows (TradingView-style): the bar under the crosshair, or the last bar when the
 *  crosshair is off the chart; in the forecast the zone and the forecast values instead of OHLC.
 *  bar: {time, open, high, low, close}|null; fc: {time, h, median, lo, hi}|null; national: close|null. */
export function legendModel({ title, period, bar, fc, national, newHome, now, zones = DEFAULT_ZONES }) {
  const unit = { M: "月 K", Q: "季 K", Y: "年 K" }[period];
  const out = { title, unit, time: "", ohlc: null, change: null, tone: "flatc", rows: [] };
  if (fc) {
    const rel = (v) => pct((v / now - 1) * 100, 1);
    out.time = `${fc.time.slice(0, 7)} · +${fc.h} 个月（${ZONE_NAME(fc.h, zones)}）`;
    out.rows.push({ name: "预测中位数", value: `${fc.median.toFixed(1)}（${rel(fc.median)}）`, cls: "median" });
    out.rows.push({ name: "80% 区间", value: `${fc.lo.toFixed(1)} ~ ${fc.hi.toFixed(1)}（${rel(fc.lo)} ~ ${rel(fc.hi)}）`, cls: "band" });
    return out;
  }
  if (!bar) return out;
  const d = bar.close - bar.open;
  out.time = periodLabel(bar.time, period);
  out.tone = d > 0 ? "up" : d < 0 ? "down" : "flatc";
  out.ohlc = [["开", bar.open], ["高", bar.high], ["低", bar.low], ["收", bar.close]].map(([k, v]) => ({ k, v: v.toFixed(1) }));
  out.change = `${sgn(d, 2)}（${pct((bar.close / bar.open - 1) * 100, 2)}）`;
  if (national != null) out.rows.push({ name: "全国", value: national.toFixed(1), cls: "nat" });
  if (newHome != null) out.rows.push({ name: "新房", value: newHome.toFixed(1), cls: "new" });
  return out;
}

/** Period change in percent per candle (the lower pane, where TradingView puts volume). */
export function changeBars(candles) {
  return candles.map((c) => ({ time: c.time, value: r2((c.close / c.open - 1) * 100) }));
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

const PANE_SHARE = 0.2;   // the change pane takes a fifth of the plot height, like TradingView's volume pane

export async function createCandleChart(el, theme) {
  await loadScript(LWC);
  const LW = window.LightweightCharts;
  const tok = (name) => resolveColor(theme.tok(name));
  const alpha = (rgb, a) => rgb.replace(/^rgb\((.*)\)$/, `rgba($1, ${a})`);
  const ymd = (t) => (typeof t === "string" ? t : typeof t === "number" ? new Date(t * 1000).toISOString() : `${t.year}-${String(t.month).padStart(2, "0")}-${String(t.day).padStart(2, "0")}`).slice(0, 10);
  let ctx = null;
  /** The candle whose period contains a date (months between quarterly/yearly candles map to their candle). */
  const barAt = (s) => {
    const cs = ctx.state.candles;
    return s >= cs[0].time && s <= ctx.lastBarEnd ? ctx.byTime.get(nearest(cs, s)) : null;
  };
  const crossLabel = (t) => {
    const s = ymd(t);
    if (!ctx) return s.slice(0, 7);
    const bar = barAt(s);
    return bar ? periodLabel(bar.time, ctx.period) : s.slice(0, 7);
  };
  const chart = LW.createChart(el, {
    autoSize: true,
    crosshair: { mode: LW.CrosshairMode.Normal },
    localization: { locale: "zh-CN", timeFormatter: crossLabel, priceFormatter: (v) => v.toFixed(1) },
    rightPriceScale: { scaleMargins: { top: 0.16, bottom: 0.06 }, minimumWidth: 64 },
    timeScale: { rightOffset: 3, timeVisible: false,
      tickMarkFormatter: (t, type) => { const s = ymd(t); return type === 0 ? s.slice(0, 4) : `${+s.slice(5, 7)}月`; } },
  });
  // pane 0: price.  Background blocks first so everything else draws on top; value 1 on a fixed 0..1 scale = full pane height
  const shadeOpts = { priceScaleId: "shade", priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false, lineVisible: false,
    autoscaleInfoProvider: () => ({ priceRange: { minValue: 0, maxValue: 1 } }) };
  const phaseShade = chart.addSeries(LW.AreaSeries, shadeOpts, 0);
  const scenarioShade = chart.addSeries(LW.AreaSeries, shadeOpts, 0);
  chart.priceScale("shade", 0).applyOptions({ scaleMargins: { top: 0, bottom: 0 } });
  const candle = chart.addSeries(LW.CandlestickSeries, { title: "现价位", priceLineStyle: LW.LineStyle.Dashed, priceLineWidth: 1 }, 0);
  const lineOpts = { priceLineVisible: false, crosshairMarkerVisible: false };
  const median = chart.addSeries(LW.LineSeries, { ...lineOpts, lineWidth: 2, lineStyle: LW.LineStyle.Dashed, title: "中位数", crosshairMarkerVisible: true, crosshairMarkerRadius: 3 }, 0);
  const lo = chart.addSeries(LW.LineSeries, { ...lineOpts, lineWidth: 1, lineStyle: LW.LineStyle.Dotted, title: "80% 下沿" }, 0);
  const hi = chart.addSeries(LW.LineSeries, { ...lineOpts, lineWidth: 1, lineStyle: LW.LineStyle.Dotted, title: "80% 上沿" }, 0);
  const nat = chart.addSeries(LW.LineSeries, { ...lineOpts, lineWidth: 1, title: "全国" }, 0);
  const newS = chart.addSeries(LW.LineSeries, { ...lineOpts, lineWidth: 1, lineStyle: LW.LineStyle.Dashed, title: "新房" }, 0);
  const candleMarks = LW.createSeriesMarkers(candle, []);
  const medianMarks = LW.createSeriesMarkers(median, []);
  // pane 1: period change in percent, on its own axis
  const change = chart.addSeries(LW.HistogramSeries, { priceLineVisible: false, lastValueVisible: false, base: 0,
    priceFormat: { type: "custom", formatter: (v) => `${v.toFixed(1)}%`, minMove: 0.01 } }, 1);
  chart.priceScale("right", 1).applyOptions({ scaleMargins: { top: 0.18, bottom: 0.04 }, minimumWidth: 64 });
  const [pricePane, changePane] = chart.panes();
  pricePane.setStretchFactor(1 - PANE_SHARE);
  changePane.setStretchFactor(PANE_SHARE);

  const legend = Object.assign(document.createElement("div"), { className: "lwc-legend" });
  const paneLabel = Object.assign(document.createElement("div"), { className: "lwc-pane" });
  el.append(legend, paneLabel);

  function applyTheme() {
    const up = tok("orange"), down = tok("blue");   // 红涨蓝跌，与温度色一致
    const cross = { color: tok("ink-3"), labelBackgroundColor: tok("foreground") };
    chart.applyOptions({
      layout: { background: { type: "solid", color: "transparent" }, textColor: tok("ink-3"), fontFamily: getComputedStyle(document.body).fontFamily, fontSize: 11,
        panes: { separatorColor: tok("line-2"), separatorHoverColor: tok("line"), enableResize: true } },
      grid: { vertLines: { color: tok("line") }, horzLines: { color: tok("line") } },
      crosshair: { vertLine: cross, horzLine: cross },
      rightPriceScale: { borderColor: tok("line-2") },
      timeScale: { borderColor: tok("line-2") },
    });
    chart.priceScale("right", 1).applyOptions({ borderColor: tok("line-2") });
    const tint = (c) => ({ topColor: c, bottomColor: c });
    phaseShade.applyOptions(tint(tok("phase")));
    scenarioShade.applyOptions(tint(SCENARIO_SHADE));
    candle.applyOptions({ upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down });
    for (const s of [median, lo, hi]) s.applyOptions({ color: tok("gold") });
    nat.applyOptions({ color: tok("blue") });
    newS.applyOptions({ color: tok("aqua") });
    if (ctx) { ctx.up = up; ctx.down = down; draw(); }
  }

  function showLegend(m, pctValue) {
    const v = (x) => `<b class="${m.tone}">${x}</b>`;
    const head = `<span class="lg-title">${esc(m.title)}</span><span class="lg-unit">${m.unit} · 指数（${esc(ctx.state.base)}）</span><span class="lg-time">${esc(m.time)}</span>`;
    const ohlc = m.ohlc ? m.ohlc.map((o) => `<span>${o.k} ${v(o.v)}</span>`).join("") + `<span>${v(m.change)}</span>` : "";
    const rows = m.rows.map((r) => `<div class="row"><i class="sw ${r.cls}"></i>${r.name} <b>${esc(r.value)}</b></div>`).join("");
    legend.innerHTML = `<div class="row">${head}${ohlc}</div>${rows}`;
    const tone = pctValue > 0 ? "up" : pctValue < 0 ? "down" : "flatc";
    paneLabel.innerHTML = `期间涨跌幅（%，每${{ M: "月", Q: "季", Y: "年" }[ctx.period]}）${pctValue == null ? "" : ` <b class="${tone}">${pct(pctValue, 2)}</b>`}`;
  }

  const changeOf = (c) => r2((c.close / c.open - 1) * 100);
  function idle() {
    const { state } = ctx, last = state.candles[state.candles.length - 1];
    showLegend(legendModel({ title: state.title, period: ctx.period, bar: last, national: ctx.natLast, newHome: ctx.newLast, now: ctx.now, zones: ctx.zones }), changeOf(last));
  }

  chart.subscribeCrosshairMove((p) => {
    if (!ctx) return;
    if (!p.time || !p.point || p.point.x < 0) { idle(); return; }
    const { state } = ctx;
    const t = ymd(p.time), c = barAt(t);
    if (c) {
      const n = ctx.natBy.get(c.time), w = ctx.newBy.get(c.time);
      showLegend(legendModel({ title: state.title, period: ctx.period, bar: c, national: n == null ? null : n, newHome: w == null ? null : w, now: ctx.now, zones: ctx.zones }), changeOf(c));
      return;
    }
    const h = ctx.hOf.get(t), m = p.seriesData.get(median);
    if (h && m) showLegend(legendModel({ title: state.title, period: ctx.period, fc: { time: t, h, median: m.value, lo: p.seriesData.get(lo).value, hi: p.seriesData.get(hi).value }, now: ctx.now, zones: ctx.zones }), null);
    else idle();
  });

  function placeOverlays() {
    paneLabel.style.top = `${Math.round(chart.paneSize(0).height) + 4}px`;   // just below the pane separator
  }

  function draw() {
    const { state } = ctx;
    const tokGold = tok("gold"), ink3 = tok("ink-3");
    // two empty periods on the left so the first tick label is not clipped at the edge
    const step = { M: 1, Q: 3, Y: 12 }[ctx.period];
    const first = state.candles[0].time.slice(0, 7);
    const lead = [2, 1].map((k) => ({ time: `${addMonths(first, -k * step)}-01` }));
    candle.setData(lead.concat(state.candles));
    change.setData(changeBars(state.candles).map((b) => ({ ...b, color: alpha(b.value >= 0 ? ctx.up : ctx.down, 0.6) })));
    phaseShade.setData(state.shade.phase);
    scenarioShade.setData(state.shade.scenario);
    const times = new Set(state.candles.map((c) => c.time));
    const last = state.candles[state.candles.length - 1].time;
    const markers = [];
    if (state.peak) markers.push({ time: nearest(state.candles, `${state.peak.m}-01`), position: "aboveBar", color: tokGold, shape: "arrowDown", text: `高点 ${state.peak.m}（${state.peak.v.toFixed(0)}）` });
    if (state.breakMonth) markers.push({ time: nearest(state.candles, `${state.breakMonth}-01`), position: "belowBar", color: ink3, shape: "square", text: `口径断点 ${state.breakMonth}` });
    markers.push({ time: last, position: "belowBar", color: ink3, shape: "circle", text: `数据截止 ${state.origin}` });
    candleMarks.setMarkers(markers.filter((m) => times.has(m.time)).sort((a, b) => (a.time < b.time ? -1 : 1)));
    const f = state.forecast;
    median.setData(f ? f.median : []); lo.setData(f ? f.lo : []); hi.setData(f ? f.hi : []);
    for (const s of [median, lo, hi]) s.applyOptions({ lastValueVisible: !!f });
    nat.setData(state.national || []);
    nat.applyOptions({ lastValueVisible: !!state.national });
    newS.setData(state.newHome || []);
    newS.applyOptions({ lastValueVisible: !!state.newHome });
    const z = ctx.zones, at = (h) => f && f.median[h] && { time: f.median[h].time, position: "aboveBar", color: ink3, shape: "circle", text: `+${h} 个月` };
    medianMarks.setMarkers([z.reliable, z.caution].map(at).filter(Boolean));
    placeOverlays();
    idle();
  }

  const ro = new ResizeObserver(() => ctx && placeOverlays());
  ro.observe(el);
  applyTheme();

  return {
    applyTheme,
    /** state: { title, base, candles, shade, forecast|null, national|null, newHome|null, peak, breakMonth, window:{from,to,all}, origin, period, zones } */
    render(state) {
      const f = state.forecast;
      ctx = {
        state, period: state.period, zones: state.zones || DEFAULT_ZONES,
        now: state.candles[state.candles.length - 1].close,
        natLast: state.national ? state.national[state.national.length - 1].value : null,
        newLast: state.newHome ? state.newHome[state.newHome.length - 1].value : null,
        newBy: new Map((state.newHome || []).map((p) => [p.time, p.value])),
        byTime: new Map(state.candles.map((c) => [c.time, c])),
        lastBarEnd: state.origin + "-01",
        natBy: new Map((state.national || []).map((p) => [p.time, p.value])),
        hOf: new Map((f ? f.median : []).map((p, i) => [p.time, i])),
        up: tok("orange"), down: tok("blue"),
      };
      draw();
      const first = state.candles[0].time;
      if (state.window.all) chart.timeScale().fitContent();
      else {
        const to = f && state.window.to >= state.origin ? f.median[f.median.length - 1].time : `${state.window.to}-01`;
        const from = `${state.window.from}-01`;
        chart.timeScale().setVisibleRange({ from: from < first ? first : from, to });
      }
    },
    destroy() { ro.disconnect(); chart.remove(); legend.remove(); paneLabel.remove(); },
  };
}

/** The candle whose period contains `time` (markers must sit on a candle time). */
function nearest(candles, time) {
  let hit = candles[0].time;
  for (const c of candles) { if (c.time <= time) hit = c.time; else break; }
  return hit;
}
