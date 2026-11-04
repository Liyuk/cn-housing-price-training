/* District-level views: the v0.2 scenario range plot, official signings,
   cross-city rental yield, and the city page's district explorer. */

import { tok } from "../core/theme.js";
import { kit, mount } from "../core/charts.js";
import { esc, pct, grp, range } from "../core/format.js";

export function scenarioOption(rows) {
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 64, right: 24, top: 16, bottom: 44 },
    tooltip: Object.assign(kit.tooltip("item"), { formatter(p) {
      const r = rows[p.dataIndex], chg = (r.base2030 / r.base2026 - 1) * 100;
      return `<b>${r.district}</b><br/>2026 基准：${grp(r.base2026)}<br/>2030 基准：<b>${grp(r.base2030)}</b>（${pct(chg)}）<br/>2030 区间：${grp(r.low2030)} ~ ${grp(r.high2030)} 元/㎡`;
    } }),
    xAxis: Object.assign(kit.axis(), { type: "category", data: rows.map((r) => r.district), splitLine: { show: false }, axisLabel: { color: tok("ink-2"), fontSize: 11, interval: 0, rotate: 35 } }),
    yAxis: kit.valueAxis({ axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: (v) => `${v / 10000} 万` } }),
    series: [{
      type: "custom", z: 3, data: rows.map((r, i) => [i, r.base2026, r.base2030, r.low2030, r.high2030]), encode: { x: 0, y: [1, 2, 3, 4] },
      renderItem(params, api) {
        const i = api.value(0), r = rows[i], x = api.coord([i, r.base2030])[0];
        const yLo = api.coord([i, r.low2030])[1], yHi = api.coord([i, r.high2030])[1], y26 = api.coord([i, r.base2026])[1], y30 = api.coord([i, r.base2030])[1];
        return { type: "group", children: [
          { type: "rect", shape: { x: x - 6, y: yHi, width: 12, height: Math.max(2, yLo - yHi), r: 3 }, style: { fill: tok("gold"), opacity: 0.4 } },
          { type: "line", shape: { x1: x - 11, x2: x + 11, y1: y26, y2: y26 }, style: { stroke: tok("ink-2"), lineWidth: 2.4 } },
          { type: "circle", shape: { cx: x, cy: y30, r: 4.6 }, style: { fill: tok("blue"), stroke: tok("panel"), lineWidth: 2 } },
        ] };
      },
    }],
  };
}

export function officialOption(O) {
  const rows = O.districts;
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 52, right: 14, top: 22, bottom: 40 },
    tooltip: Object.assign(kit.tooltip(), { formatter: (p) => { const r = rows[p[0].dataIndex]; return `<b>${r.district}</b><br/>网签 <b>${grp(r.count)}</b> 套<br/>面积 ${grp(r.area_m2)} ㎡`; } }),
    xAxis: Object.assign(kit.axis(), { type: "category", data: rows.map((r) => r.district), splitLine: { show: false }, axisLabel: { color: tok("ink-2"), fontSize: 11, interval: 0, rotate: 40 } }),
    yAxis: kit.valueAxis(),
    series: [{ type: "bar", data: rows.map((r) => r.count), barWidth: "58%", itemStyle: { color: tok("blue"), borderRadius: [3, 3, 0, 0] } }],
  };
}

/** Cross-city gross rental yield (latest month), horizontal bars sorted high to low. */
export function yieldBarOption(Y) {
  const rows = Y.cities;
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 56, right: 96, top: 8, bottom: 24 },
    tooltip: Object.assign(kit.tooltip("item"), { formatter: (p) => { const r = rows[p.dataIndex];
      return `<b>${r.city}</b>（${r.asof}，榜内 ${r.n_districts} 个区）<br/>租金收益率中位数：<b>${r.median_yield.toFixed(2)}%</b><br/>区间：${r.min_yield.toFixed(2)}% ~ ${r.max_yield.toFixed(2)}%<br/>单价中位数：${grp(r.median_price)} 元/㎡`; } }),
    xAxis: kit.valueAxis({ axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: "{value}%" } }),
    yAxis: Object.assign(kit.axis(), { type: "category", data: rows.map((r) => r.city), inverse: true, splitLine: { show: false }, axisLabel: { color: tok("ink-2"), fontSize: 12 } }),
    series: [{
      type: "bar", barWidth: 12, data: rows.map((r) => r.median_yield), itemStyle: { color: tok("gold"), borderRadius: [0, 3, 3, 0] },
      label: { show: true, position: "right", color: tok("ink-2"), fontSize: 11.5, formatter: (p) => `${p.value.toFixed(2)}%  · ${rows[p.dataIndex].n_districts} 区` },
    }],
  };
}

/* ------------------------------------------------------------------------
   District explorer (city page).  Search a district, pick a measure, see the
   monthly path.  Top-10 rankings mean a district can be missing in a month;
   gaps are shown as gaps, never interpolated. */
const MEASURES = { price: ["单价", "元/㎡", 0], rent: ["月租金", "元/月/㎡", 1], yield: ["租金收益率", "%", 2] };

export function mountDistrictExplorer(root, payload) {
  const names = Object.keys(payload.districts);
  const state = { measure: "price", q: "", selected: new Set(names.slice(0, 3)) };
  root.innerHTML = `
    <div class="tv-bar">
      <input class="search" type="search" placeholder="搜索区县" aria-label="搜索区县" />
      <div class="seg" role="group" aria-label="指标">${Object.entries(MEASURES).map(([k, [l]]) => `<button type="button" data-m="${k}">${l}</button>`).join("")}</div>
      <span class="board-count">${range(payload.months[0], payload.months[payload.months.length - 1])} · ${payload.n_months} 期 · 截至 ${payload.asof}</span>
    </div>
    <div class="dist-grid">
      <div class="dist-list" role="group" aria-label="区县列表"></div>
      <div class="chart mid dist-chart" role="img" aria-label="区县价格、租金与租金收益率走势"></div>
    </div>
    <p class="foot">${esc(payload.note)}</p>`;
  const list = root.querySelector(".dist-list"), chartEl = root.querySelector(".dist-chart");
  const palette = () => [tok("gold"), tok("blue"), tok("orange"), tok("aqua") || tok("ink-2"), tok("ink-2")];

  function latest(name) {
    const a = payload.districts[name][state.measure];
    for (let i = a.length - 1; i >= 0; i--) if (a[i] != null) return a[i];
    return null;
  }
  function renderList() {
    const q = state.q;
    list.innerHTML = names.filter((n) => !q || n.includes(q)).map((n) => {
      const v = latest(n), [, unit, d] = MEASURES[state.measure];
      return `<label class="dist-item"><input type="checkbox" data-d="${esc(n)}" ${state.selected.has(n) ? "checked" : ""}/><span>${esc(n)}</span><span class="num dim">${v == null ? "—" : (d ? v.toFixed(d) : grp(v)) + (state.measure === "yield" ? "%" : "")}</span></label>`;
    }).join("") || '<p class="dim">没有匹配的区县</p>';
  }
  function option() {
    const [label, unit, d] = MEASURES[state.measure];
    const colors = palette(), sel = [...state.selected].slice(0, 5);
    return {
      animationDuration: 300, textStyle: kit.text(),
      grid: { left: 52, right: 16, top: 34, bottom: 26 },
      legend: kit.legend(sel),
      tooltip: Object.assign(kit.tooltip(), { formatter: (p) => `<b>${payload.months[p[0].dataIndex]}</b>` + p.filter((x) => x.value != null).map((x) => `<br/>${x.marker}${x.seriesName}：<b>${d ? Number(x.value).toFixed(d) : grp(x.value)}</b> ${unit}`).join("") }),
      xAxis: Object.assign(kit.axis(), { type: "category", data: payload.months, boundaryGap: false, splitLine: { show: false }, axisLabel: { color: tok("ink-3"), fontSize: 11.5, hideOverlap: true, interval: (i, v) => v.endsWith("-01") || v.endsWith("-07"), formatter: (v) => v.slice(0, 7) } }),
      yAxis: kit.valueAxis({ scale: true, axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: (v) => (state.measure === "yield" ? `${v}%` : state.measure === "price" ? `${v / 10000} 万` : String(v)) } }),
      series: sel.map((n, i) => ({ name: n, type: "line", data: payload.districts[n][state.measure], connectNulls: false, showSymbol: true, symbolSize: 4,
        lineStyle: { width: 1.8, color: colors[i % colors.length] }, itemStyle: { color: colors[i % colors.length] } })),
    };
  }
  function render() {
    root.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.m === state.measure)));
    renderList();
    mount(chartEl, option);
  }
  root.querySelector(".seg").addEventListener("click", (e) => { const b = e.target.closest("button[data-m]"); if (b) { state.measure = b.dataset.m; render(); } });
  root.querySelector('input[type="search"]').addEventListener("input", (e) => { state.q = e.target.value.trim(); renderList(); });
  list.addEventListener("change", (e) => {
    const c = e.target.closest("input[data-d]");
    if (!c) return;
    c.checked ? state.selected.add(c.dataset.d) : state.selected.delete(c.dataset.d);
    if (!state.selected.size) { state.selected.add(c.dataset.d); c.checked = true; }
    mount(chartEl, option);
  });
  render();
}
