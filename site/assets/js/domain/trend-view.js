/* TrendView: one interface for "a region's index over time".
   Line mode is ECharts (annotations, rising-phase shading, probability fan, drag-to-select a window);
   K-line mode is Lightweight Charts (synthetic OHLC + forecast lines).  The page does not know which
   library draws what, nor how state reaches the address bar.

   State: region, mode (line|candle), metric (level|yoy|dd), time window (shared or own), K-line period,
   forecast horizon (0|12|24|60), overlays (national, new-home).

   const view = createTrendView(root, { data, region, regions, allowCompare, newHome, window, urlSync, zones });
   view.set({ region, mode, metric, period, fc, cmp, range, from, to })    // any subset
*/

import { mount, ensureEcharts } from "../core/charts.js";
import { tok, onThemeChange, isNarrow } from "../core/theme.js";
import { createTimeWindow, windowFromUrl } from "../core/timewindow.js";
import { mountWindowBar } from "../core/windowbar.js";
import { createUrlSync, oneOf, list } from "../core/urlstate.js";
import { buildTrendOption, regionLabel, baseLabel, DEFAULT_ZONES } from "./trend-chart.js";
import { aggregateOhlc, forecastLines, shadeBlocks, candleKey, createCandleChart } from "./candles.js";
import { METRICS, windowStats } from "./series.js";
import { statsTable } from "./window-stats.js";

const PERIODS = [["M", "月"], ["Q", "季"], ["Y", "年"]];
const FORECASTS = [["0", "不显示"], ["12", "+12 个月"], ["24", "+24 个月"], ["60", "+60 个月"]];
const seg = (g, label, items) => `<div class="seg" data-g="${g}" role="group" aria-label="${label}">${items.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join("")}</div>`;
const grp = (label, inner, attrs = "") => `<div class="tv-grp" ${attrs}><span class="tv-lab">${label}</span>${inner}</div>`;

export function createTrendView(root, { data, region, regions = null, allowCompare = false, newHome = null, mode, period = "Q", showToolbar = true, zones, range = "all", window: sharedWindow = null, urlSync = false }) {
  const { cum, fan } = data;
  const months = cum.months;
  let saved = null;
  try { saved = localStorage.getItem("trend-mode"); } catch (e) { /* ignore */ }
  const defaults = { g: region, m: mode || saved || "line", x: "level", p: period, fc: "60", cmp: allowCompare ? ["nat"] : [] };
  const schema = {
    g: oneOf(regions || [region], region),
    m: oneOf(["line", "candle"], defaults.m), x: oneOf(METRICS.map(([v]) => v), "level"), p: oneOf(PERIODS.map(([v]) => v), period),
    fc: oneOf(FORECASTS.map(([v]) => v), "60"), cmp: list(defaults.cmp, { valid: (v) => v === "nat" || v === "new" }),
  };
  const url = urlSync ? createUrlSync(schema) : null;
  const init = url ? url.read() : defaults;
  const state = { region: init.g, mode: init.m, metric: init.x, period: init.p, fc: init.fc, cmp: init.cmp };

  const bounds = { first: months[0], last: months[months.length - 1] };
  const win = sharedWindow || (urlSync ? windowFromUrl({ bounds, defaults: { range } }) : createTimeWindow({ bounds, state: { range } }));
  const ownWindow = !sharedWindow;
  const zoneSet = zones ? { reliable: zones.reliable_through, caution: zones.caution_through } : DEFAULT_ZONES;
  const theme = { tok };

  root.classList.add("tv");
  root.innerHTML = `
    ${showToolbar ? `<div class="tv-bar">
      ${regions ? seg("region", "范围", regions.map((r) => [r, r])) : ""}
      ${seg("mode", "图表类型", [["line", "折线"], ["candle", "K 线"]])}
      ${grp("指标", seg("metric", "指标", METRICS))}
      ${ownWindow ? '<div class="tv-grp" data-window></div>' : ""}
      ${seg("period", "K 线周期", PERIODS).replace('class="seg"', 'class="seg" hidden')}
      ${grp("预测", seg("fc", "预测期限", FORECASTS), 'data-grp="fc"')}
      ${allowCompare || newHome ? `<span class="tv-grp tv-checks" data-grp="cmp">
        ${allowCompare ? '<label class="check" data-cmp-label="nat"><input type="checkbox" data-cmp="nat" /> 对照全国</label>' : ""}
        ${newHome ? '<label class="check" data-cmp-label="new"><input type="checkbox" data-cmp="new" /> 对照新房</label>' : ""}
      </span>` : ""}
    </div>
    <p class="tv-hint" hidden></p>` : ""}
    <div class="tv-key" hidden></div>
    <div class="tv-stage">
      <div class="tv-line chart tall" role="img" aria-label="价格指数走势图"></div>
      <div class="tv-candle chart tall" role="img" aria-label="价格指数 K 线图" hidden></div>
    </div>
    <div class="tv-stats"></div>`;
  const lineEl = root.querySelector(".tv-line"), candleEl = root.querySelector(".tv-candle");
  const keyEl = root.querySelector(".tv-key"), statsEl = root.querySelector(".tv-stats");
  let candleChart = null, candleLoading = null, newCum = null, newLoading = null;

  const hasFan = () => !!(fan.regions[state.region] && fan.fc_months.length);
  const effMode = () => (state.metric === "level" ? state.mode : "line");
  const horizon = () => (state.metric === "level" && hasFan() ? Math.min(Number(state.fc), fan.fc_months.length) : 0);
  const compare = () => allowCompare && state.cmp.includes("nat") && state.region !== "全国";
  const compareNew = () => !!newCum && state.cmp.includes("new") && !!newCum.series[state.region];
  const breakMonth = cum.regime_break && cum.regime_break.month;

  /** The new-home bundle is loaded on first use; a failed load drops the overlay instead of breaking the chart. */
  async function ensureNew() {
    if (!state.cmp.includes("new") || !newHome || newCum) return;
    newLoading = newLoading || newHome().then((c) => (newCum = c), () => {});
    await newLoading;
    if (!newCum) state.cmp = state.cmp.filter((x) => x !== "new");
  }

  const closes = (levels) => aggregateOhlc(months, levels, state.period, 100).map((c) => ({ time: c.time, value: c.close }));

  async function renderCandle(w) {
    if (!candleChart) {
      candleLoading = candleLoading || createCandleChart(candleEl, theme).then((c) => (candleChart = c));
      await candleLoading;
    }
    const hist = cum.series[state.region];
    const h = horizon();
    const f = h > 0 ? fan.regions[state.region] : null;
    keyEl.innerHTML = candleKey({ compare: compare(), compareNew: compareNew(), forecast: !!f, zones: zoneSet, period: state.period });
    candleChart.render({
      title: regionLabel(state.region),
      base: baseLabel(cum),
      candles: aggregateOhlc(months, hist, state.period, 100),
      shade: shadeBlocks(hist, months, f ? fan.fc_months.slice(0, h) : [], zoneSet),
      forecast: f ? forecastLines(fan, f, months[months.length - 1], hist[hist.length - 1], h) : null,
      national: compare() ? closes(cum.series["全国"]) : null,
      newHome: compareNew() ? closes(newCum.series[state.region]) : null,
      peak: cum.phases[state.region].peak,
      breakMonth: breakMonth || null,
      window: { from: w.from, to: w.to, all: win.state.range === "all" },
      origin: months[months.length - 1],
      period: state.period,
      zones: zoneSet,
    });
  }

  const brushBound = new WeakSet();
  function renderLine(w) {
    const inst = mount(lineEl, () => buildTrendOption(data, state.region, {
      compare: compare(), compareNew: compareNew(), newHome: newCum, metric: state.metric,
      from: w.from, to: w.to, horizon: horizon(), brush: true, narrow: isNarrow(), zones: zoneSet,
    }, theme));
    inst.dispatchAction({ type: "takeGlobalCursor", key: "brush", brushOption: { brushType: "lineX", brushMode: "single" } });
    if (!brushBound.has(inst)) {
      brushBound.add(inst);
      inst.on("brushEnd", (p) => {
        const a = p.areas && p.areas[0];
        inst.dispatchAction({ type: "brush", areas: [] });
        if (!a || !a.coordRange) return;
        const [x0, x1] = a.coordRange.map((v) => Math.max(0, Math.min(months.length - 1, Math.round(v))));
        if (x1 - x0 >= 1) win.set({ range: "custom", from: months[x0], to: months[x1] });
      });
    }
  }

  function renderStats(w) {
    const entries = [{ name: regionLabel(state.region), color: tok("gold"), stats: windowStats(months, cum.series[state.region], w.i0, w.i1, breakMonth) }];
    const notes = [];
    if (compare()) entries.push({ name: "全国（70 城等权）", color: tok("blue"), stats: windowStats(months, cum.series["全国"], w.i0, w.i1, breakMonth) });
    if (compareNew()) {
      entries.push({ name: `新房（${state.region}）`, color: tok("aqua"), stats: windowStats(newCum.months, newCum.series[state.region], w.i0, w.i1, breakMonth) });
      const gap = (newCum.bridged_months || []).filter((m) => m >= w.from && m <= w.to);
      if (gap.length) notes.push(`新房 ${gap[0]} 至 ${gap[gap.length - 1]} 没有官方页面，由同比恒等式推算，已计入统计。`);
    }
    statsEl.innerHTML = statsTable(entries, { regimeBreak: breakMonth, notes });
  }

  const SEG_STATE = { region: () => state.region, mode: () => state.mode, metric: () => state.metric, period: () => state.period, fc: () => state.fc };
  function syncToolbar() {
    root.querySelectorAll(".seg").forEach((s) => {
      if (!SEG_STATE[s.dataset.g]) return;
      const value = SEG_STATE[s.dataset.g]();
      s.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === String(value))));
    });
    const candle = effMode() === "candle", level = state.metric === "level";
    const on = (sel, fn) => { const el = root.querySelector(sel); if (el) fn(el); };
    on('.seg[data-g="period"]', (el) => { el.hidden = !candle; });
    on('[data-grp="fc"]', (el) => { el.hidden = !(level && hasFan()); });
    on('.seg[data-g="mode"] button[data-v="candle"]', (b) => { b.disabled = !level; b.title = level ? "" : "K 线只用于指数水平"; });
    on('[data-cmp-label="nat"]', (el) => { el.hidden = state.region === "全国"; });
    root.querySelectorAll("input[data-cmp]").forEach((i) => { i.checked = state.cmp.includes(i.dataset.cmp); });
    on(".tv-hint", (el) => {
      el.hidden = false;
      el.textContent = candle ? "K 线：滚轮缩放、拖动平移；区间统计跟随上方的时间范围。" : "折线图：在图上横向拖选一段，即可缩放并统计该区间；点“全部”恢复。";
    });
  }

  function writeUrl() {
    if (url) url.write({ g: state.region, m: state.mode, x: state.metric, p: state.period, fc: state.fc, cmp: state.cmp });
  }

  async function render() {
    syncToolbar();
    await ensureNew();
    const w = win.resolve(months);
    syncToolbar();
    renderStats(w);
    writeUrl();
    const candle = effMode() === "candle";
    lineEl.hidden = candle; candleEl.hidden = !candle; keyEl.hidden = !candle;
    if (candle) {
      try { await renderCandle(w); } catch (e) { console.error(e); state.mode = "line"; render(); }   // library failed to load: stay on the line chart
      return;
    }
    await ensureEcharts();
    renderLine(w);
  }
  let pending = null;
  const schedule = () => (pending = pending || Promise.resolve().then(() => { pending = null; return render(); }));

  root.addEventListener("click", (e) => {
    const b = e.target.closest(".seg button");
    if (!b || b.disabled) return;
    if (SEG_STATE[b.closest(".seg").dataset.g]) set({ [b.closest(".seg").dataset.g]: b.dataset.v });
  });
  root.addEventListener("change", (e) => {
    const t = e.target;
    if (t.matches("input[data-cmp]")) {
      const picked = new Set(state.cmp);
      t.checked ? picked.add(t.dataset.cmp) : picked.delete(t.dataset.cmp);
      set({ cmp: [...picked] });
    }
  });
  const windowEl = root.querySelector("[data-window]");
  if (windowEl) mountWindowBar(windowEl, win, { months });
  onThemeChange(() => candleChart && candleChart.applyTheme());
  win.subscribe(schedule);

  function set(patch) {
    for (const k of ["region", "mode", "metric", "period", "fc", "cmp"]) if (k in patch) state[k] = patch[k];
    if ("mode" in patch) { try { localStorage.setItem("trend-mode", state.mode); } catch (e) { /* ignore */ } }
    if ("range" in patch || "from" in patch || "to" in patch) { win.set({ range: patch.range || "custom", from: patch.from, to: patch.to }); return pending; }
    return schedule();
  }
  render();
  return { set, state, window: win };
}
