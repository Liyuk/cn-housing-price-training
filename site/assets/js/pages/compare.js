import { boot } from "../core/boot.js";
import { Data } from "../core/data.js";
import { mount } from "../core/charts.js";
import { tok, isNarrow, onBreakpointChange } from "../core/theme.js";
import { esc, addMonths } from "../core/format.js";
import { createUrlSync, oneOf, month, list } from "../core/urlstate.js";
import { windowFromUrl } from "../core/timewindow.js";
import { mountWindowBar } from "../core/windowbar.js";
import { windowStats, METRICS } from "../domain/series.js";
import { statsTable } from "../domain/window-stats.js";
import { assignColors, baseIndex, buildCompareOption, presets, COLOR_TOKENS, MAX_SERIES } from "../domain/compare-chart.js";

const TIERS = ["全国", "一线", "二线", "三线"];

boot("compare", ["cum", "board"], ({ data, vintage }) => {
  const { cum, board } = data;
  const $ = (s) => document.querySelector(s);
  const months = cum.months;
  const cities = board.rows.map((r) => r.city).sort((a, b) => a.localeCompare(b, "zh"));
  const known = new Set([...TIERS, ...cities]);
  const MARKETS = [["secondhand", "二手住宅"], ["new", "新建商品住宅"]];

  const schema = {
    s: list(["全国", "北京", "上海", "广州", "深圳"], { valid: (r) => known.has(r), max: MAX_SERIES }),
    x: oneOf(METRICS.map(([v]) => v), "level"),
    b: month(null),
    k: oneOf(MARKETS.map(([v]) => v), "secondhand"),
  };
  const sync = createUrlSync(schema);
  const state = sync.read();
  let colors = assignColors(state.s);
  const bundles = { secondhand: cum, new: null };
  const win = windowFromUrl({ bounds: { first: months[0], last: vintage.dataThrough }, defaults: { range: "10" } });

  const marketCum = () => bundles[state.k];
  const phases = () => (marketCum() || cum).phases;

  // ---- picker
  const pick = $("#cmp-pick");
  pick.innerHTML = `<div class="tv-grp"><span class="tv-lab">已选</span><span class="chips" id="cmp-chips"></span></div>
    <div class="tv-grp"><span class="tv-lab">添加</span><select class="search" id="cmp-add" aria-label="添加地区"></select></div>
    <div class="tv-grp"><span class="tv-lab">预设</span><span id="cmp-presets" class="chips"></span></div>`;
  const chips = $("#cmp-chips"), addSel = $("#cmp-add");

  function paintPicker() {
    chips.innerHTML = state.s.map((r) => `<button type="button" class="chip-btn" data-rm="${esc(r)}" aria-label="移除 ${esc(r)}"><i class="dot" style="background:${tok(COLOR_TOKENS[colors[r]])}"></i>${esc(r)}<span class="x" aria-hidden="true">×</span></button>`).join("") || '<span class="dim">至少选 1 个</span>';
    const rest = [...TIERS, ...cities].filter((r) => !state.s.includes(r));
    addSel.innerHTML = `<option value="" selected disabled>${state.s.length >= MAX_SERIES ? `最多 ${MAX_SERIES} 个` : "选择地区…"}</option>` +
      `<optgroup label="全国与层级">${rest.filter((r) => TIERS.includes(r)).map((r) => `<option>${esc(r)}</option>`).join("")}</optgroup>` +
      `<optgroup label="城市">${rest.filter((r) => !TIERS.includes(r)).map((r) => `<option>${esc(r)}</option>`).join("")}</optgroup>`;
    addSel.disabled = state.s.length >= MAX_SERIES;
    $("#cmp-presets").innerHTML = presets(phases(), cities).map((p) => `<button type="button" class="chip-btn" data-preset="${p.key}">${esc(p.label)}</button>`).join("");
  }
  chips.addEventListener("click", (e) => { const b = e.target.closest("[data-rm]"); if (b && state.s.length > 1) { state.s = state.s.filter((r) => r !== b.dataset.rm); update(); } });
  addSel.addEventListener("change", () => { if (addSel.value && state.s.length < MAX_SERIES) { state.s = [...state.s, addSel.value]; update(); } });
  $("#cmp-presets").addEventListener("click", (e) => {
    const b = e.target.closest("[data-preset]");
    if (!b) return;
    state.s = presets(phases(), cities).find((p) => p.key === b.dataset.preset).regions;
    colors = {};
    update();
  });

  // ---- controls
  const bar = $("#cmp-bar");
  bar.innerHTML = `<div class="tv-grp"><span class="tv-lab">指标</span><div class="seg" data-g="x" role="group" aria-label="指标">${METRICS.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join("")}</div></div>
    <div class="tv-grp"><span class="tv-lab">市场</span><div class="seg" data-g="k" role="group" aria-label="市场">${MARKETS.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join("")}</div></div>
    <div class="tv-grp" data-window></div>
    <div class="tv-grp" data-base><span class="tv-lab">基期 = 100</span><input type="month" id="cmp-base" aria-label="基期月" min="${months[0]}" max="${vintage.dataThrough}" />
      <button type="button" class="btn sm" id="cmp-peak" title="以全国二手住宅指数的最高点为基期">全国高点</button>
      <button type="button" class="btn sm" id="cmp-base-reset">窗口起点</button></div>`;
  mountWindowBar(bar.querySelector("[data-window]"), win, { months });
  bar.addEventListener("click", (e) => {
    const b = e.target.closest(".seg button");
    if (!b) return;
    state[b.closest(".seg").dataset.g] = b.dataset.v;
    update();
  });
  $("#cmp-base").addEventListener("change", (e) => { state.b = e.target.value || null; update(); });
  $("#cmp-peak").addEventListener("click", () => { state.b = cum.phases["全国"].peak.m; update(); });
  $("#cmp-base-reset").addEventListener("click", () => { state.b = null; update(); });
  win.subscribe(() => update());
  onBreakpointChange(() => draw());

  // ---- rendering
  async function ensureMarket() {
    if (bundles[state.k]) return true;
    try { bundles[state.k] = await Data.load("cum_new"); return true; } catch (e) { state.k = "secondhand"; return false; }
  }

  function selection() {
    const c = marketCum();
    return state.s.filter((r) => c.series[r]).map((r) => ({ name: r, levels: c.series[r], slot: colors[r] }));
  }

  function draw() {
    const c = marketCum();
    if (!c) return;
    const w = win.resolve(months);
    const regions = selection();
    mount($("#cmp-chart"), () => buildCompareOption({ months, regions, metric: state.x, base: state.b, w, breakMonth: cum.regime_break.month, narrow: isNarrow() }, { tok }));
    const ib = baseIndex(months, state.b, w.i0);
    const level = state.x === "level";
    const label = MARKETS.find(([v]) => v === state.k)[1];
    $("#cmp-foot").innerHTML = `${label}，${vintage.describe("cum.json", { basis: false })}。` + (level
      ? `所有线在 <b>${months[ib]}</b> 都等于 100，读数就是“相对那个月涨了多少”。` : `指标：${METRICS.find(([v]) => v === state.x)[1]}。`) +
      (state.k === "new" && (c.bridged_months || []).length ? ` 新房 ${c.bridged_months[0]} 至 ${c.bridged_months[c.bridged_months.length - 1]} 没有官方页面，由同比恒等式推算。` : "");
    $("#cmp-stats").innerHTML = statsTable(regions.map((r) => ({ name: r.name, color: tok(COLOR_TOKENS[r.slot]), stats: windowStats(months, r.levels, w.i0, w.i1, cum.regime_break.month) })), { regimeBreak: cum.regime_break.month,
      notes: level ? [`统计以窗口起点（${w.from}）为起点，与基期无关；基期只决定上方曲线的起算位置。`] : [] });
  }

  function paintControls() {
    bar.querySelectorAll(".seg[data-g='x'] button, .seg[data-g='k'] button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === state[b.closest(".seg").dataset.g])));
    const w = win.resolve(months);
    $("#cmp-base").value = state.b || w.from;
    bar.querySelector("[data-base]").classList.toggle("off", state.x !== "level");
    $("#cmp-base").disabled = $("#cmp-peak").disabled = $("#cmp-base-reset").disabled = state.x !== "level";
  }

  async function update() {
    await ensureMarket();
    colors = assignColors(state.s, colors);
    sync.write(state);
    paintPicker(); paintControls(); draw();
    document.title = `${state.s.join(" vs ")} · 对比 · 趋势看板`;
  }
  update().then(() => {
    const el = $("#cmp-chart");
    const inst = window.echarts.getInstanceByDom(el);
    if (!inst) return;
    inst.dispatchAction({ type: "takeGlobalCursor", key: "brush", brushOption: { brushType: "lineX", brushMode: "single" } });
    inst.on("brushEnd", (p) => {
      const a = p.areas && p.areas[0];
      inst.dispatchAction({ type: "brush", areas: [] });
      if (!a || !a.coordRange) return;
      const [x0, x1] = a.coordRange.map((v) => Math.max(0, Math.min(months.length - 1, Math.round(v))));
      if (x1 - x0 >= 1) win.set({ range: "custom", from: months[x0], to: months[x1] });
    });
  });
});
