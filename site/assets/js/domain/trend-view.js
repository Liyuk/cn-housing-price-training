/* TrendView: one interface for "a region's index over time", with line and K-line
   modes.  The page does not know which chart library draws what: line mode is
   ECharts (annotations, rising-phase shading, probability fan), candle mode is
   Lightweight Charts (synthetic OHLC + the forecast median/80% lines).

   const view = createTrendView(root, { data, region, allowCompare });
   view.set({ region, mode, range, period, compare })    // any subset
*/

import { mount, ensureEcharts } from "../core/charts.js";
import { tok, onThemeChange, isNarrow } from "../core/theme.js";
import { buildTrendOption, DEFAULT_ZONES } from "./trend-chart.js";
import { aggregateOhlc, forecastLines, shadeBlocks, candleKey, createCandleChart } from "./candles.js";

const RANGES = [["all", "全部"], ["20", "20 年"], ["10", "10 年"], ["5", "5 年"], ["3", "3 年"]];
const PERIODS = [["M", "月"], ["Q", "季"], ["Y", "年"]];

export function createTrendView(root, { data, region, regions = null, allowCompare = false, mode, range = "all", period = "Q", showToolbar = true, zones }) {
  let saved = null;
  try { saved = localStorage.getItem("trend-mode"); } catch (e) { /* ignore */ }
  const state = { region, mode: mode || saved || "line", range, period, compare: allowCompare };
  const theme = { tok };

  root.classList.add("tv");
  root.innerHTML = `
    ${showToolbar ? `<div class="tv-bar">
      ${regions ? `<div class="seg" data-g="region" role="group" aria-label="范围">${regions.map((r) => `<button type="button" data-v="${r}">${r}</button>`).join("")}</div>` : ""}
      <div class="seg" data-g="mode" role="group" aria-label="图表类型">
        <button type="button" data-v="line">折线</button><button type="button" data-v="candle">K 线</button>
      </div>
      <div class="seg" data-g="range" role="group" aria-label="时间范围">${RANGES.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join("")}</div>
      <div class="seg" data-g="period" role="group" aria-label="K 线周期" hidden>${PERIODS.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join("")}</div>
      ${allowCompare ? '<label class="check"><input type="checkbox" data-g="compare" checked /> 对照全国</label>' : ""}
    </div>` : ""}
    <div class="tv-key" hidden></div>
    <div class="tv-stage">
      <div class="tv-line chart tall" role="img" aria-label="价格指数走势图"></div>
      <div class="tv-candle chart tall" role="img" aria-label="价格指数 K 线图" hidden></div>
    </div>`;
  const lineEl = root.querySelector(".tv-line");
  const candleEl = root.querySelector(".tv-candle");
  const keyEl = root.querySelector(".tv-key");
  const zoneSet = zones ? { reliable: zones.reliable_through, caution: zones.caution_through } : DEFAULT_ZONES;
  let candleChart = null, candleLoading = null;

  const nationalCloses = () => aggregateOhlc(data.cum.months, data.cum.series["全国"], state.period, 100).map((c) => ({ time: c.time, value: c.close }));

  async function renderCandle() {
    if (!candleChart) {
      candleLoading = candleLoading || createCandleChart(candleEl, theme).then((c) => (candleChart = c));
      await candleLoading;
    }
    const { cum, fan } = data;
    const hist = cum.series[state.region], months = cum.months;
    const f = fan.regions[state.region];
    const base = 100; // chain base (period before the first month = 100)
    const compare = state.compare && state.region !== "全国";
    keyEl.innerHTML = candleKey({ compare, forecast: !!f, zones: zoneSet, period: state.period });
    candleChart.render({
      candles: aggregateOhlc(months, hist, state.period, base),
      shade: shadeBlocks(hist, months, f ? fan.fc_months : [], zoneSet),
      forecast: f ? forecastLines(fan, f, months[months.length - 1], hist[hist.length - 1]) : null,
      national: compare ? nationalCloses() : null,
      peak: cum.phases[state.region].peak,
      breakMonth: cum.regime_break ? cum.regime_break.month : null,
      rangeYears: state.range,
      origin: months[months.length - 1],
      period: state.period,
      zones: zoneSet,
    });
  }

  function syncToolbar() {
    root.querySelectorAll(".seg").forEach((seg) => {
      const g = seg.dataset.g;
      seg.querySelectorAll("button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === state[g])));
    });
    const periodSeg = root.querySelector('.seg[data-g="period"]');
    if (periodSeg) periodSeg.hidden = state.mode !== "candle";
    const cmp = root.querySelector('input[data-g="compare"]');
    if (cmp) { cmp.checked = state.compare; cmp.closest("label").hidden = state.region === "全国"; }
  }

  async function render() {
    syncToolbar();
    const candle = state.mode === "candle";
    lineEl.hidden = candle;
    candleEl.hidden = !candle;
    keyEl.hidden = !candle;
    if (candle) {
      try { await renderCandle(); } catch (e) { state.mode = "line"; render(); }  // library failed to load: stay on the line chart
      return;
    }
    await ensureEcharts();
    mount(lineEl, () => buildTrendOption(data, state.region, { compare: state.compare && allowCompare, range: state.range, narrow: isNarrow(), ...(zones ? { zones: { reliable: zones.reliable_through, caution: zones.caution_through } } : {}) }, theme));
  }

  root.addEventListener("click", (e) => {
    const b = e.target.closest(".seg button");
    if (!b) return;
    const g = b.closest(".seg").dataset.g;
    set({ [g]: b.dataset.v });
  });
  const cmp = root.querySelector('input[data-g="compare"]');
  if (cmp) cmp.addEventListener("change", () => set({ compare: cmp.checked }));
  onThemeChange(() => candleChart && candleChart.applyTheme());

  function set(patch) {
    Object.assign(state, patch);
    if (patch.mode) { try { localStorage.setItem("trend-mode", state.mode); } catch (e) { /* ignore */ } }
    return render();
  }
  render();
  return { set, state };
}
