/* Board: the 70-city ranking table.  `filterSort` is pure (testable); `createBoard`
   renders the toolbar and table and links each city to its own page. */

import { esc, pct, cls, probText } from "../core/format.js";

export const TEMP_ORDER = ["寒", "凉", "平", "温", "热"];
export const TEMP_KEY = { 寒: "cold", 凉: "cool", 平: "flat", 温: "warm", 热: "hot" };

export function filterSort(rows, { key = "strength", dir = -1, temps = new Set(), tier = 0, q = "", turning = false } = {}) {
  const out = rows.filter((r) =>
    (!temps.size || temps.has(r.temp)) && (!tier || r.tier === tier) && (!q || r.city.includes(q)) && (!turning || r.turning));
  out.sort((a, b) => {
    const x = a[key], y = b[key];
    if (key === "city") return dir * String(x).localeCompare(String(y), "zh");
    return dir * ((x ?? -Infinity) - (y ?? -Infinity)) || a.city.localeCompare(b.city, "zh");
  });
  return out;
}

const COLS = [
  { k: "rank", label: "#", cls: "rank" },
  { k: "temp", label: "温度", cls: "l" },
  { k: "city", label: "城市", cls: "l", sortable: true },
  { k: "strength", label: "趋势强度", sortable: true },
  { k: "yoy", label: "同比", sortable: true },
  { k: "mom", label: "环比", sortable: true },
  { k: "spark", label: "近 24 个月" },
  { k: "from_peak_pct", label: "距高点", sortable: true },
  { k: "f12", label: "12 个月预测", sortable: true },
  { k: "range", label: "80% 区间（−12% ~ +12%）" },
  { k: "p_up12", label: "高于现价概率", sortable: true },
];

export const tChip = (label) => `<span class="t ${TEMP_KEY[label]}" title="温度：${label}">${label}</span>`;

export function sparkSvg(vals) {
  const W = 110, H = 28, n = vals.length;
  const mn = Math.min(...vals), mx = Math.max(...vals), span = Math.max(mx - mn, 0.01);
  const pts = vals.map((v, i) => [(i / (n - 1)) * W, H - 3 - ((v - mn) / span) * (H - 6)]);
  const color = vals[n - 1] >= vals[0] ? "var(--orange)" : "var(--blue)";
  const last = pts[n - 1];
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" aria-hidden="true"><polyline fill="none" style="stroke:${color}" stroke-width="1.6" stroke-linejoin="round" points="${pts.map((p) => p.map((x) => x.toFixed(1)).join(",")).join(" ")}"/><circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="2.3" style="fill:${color}"/></svg>`;
}
export function microSvg(lo, med, hi) {
  const W = 132, H = 22, R = 12;
  const x = (v) => ((Math.max(-R, Math.min(R, v)) + R) / (2 * R)) * W;
  return `<svg class="micro" viewBox="0 0 ${W} ${H}" aria-hidden="true"><line x1="${W / 2}" x2="${W / 2}" y1="2" y2="${H - 2}" style="stroke:var(--line-2)" stroke-width="1"/><rect x="${x(lo).toFixed(1)}" y="7" width="${Math.max(2, x(hi) - x(lo)).toFixed(1)}" height="8" rx="2" style="fill:var(--gold)" opacity="0.35"/><line x1="${x(med).toFixed(1)}" x2="${x(med).toFixed(1)}" y1="3" y2="${H - 3}" style="stroke:var(--gold-ink)" stroke-width="2.4" stroke-linecap="round"/></svg>`;
}

/**
 * @param root     element that receives the toolbar + table
 * @param board    board.json payload
 * @param opts     { cityHref(city) -> string, limit }  limit: show only the first n rows (home preview)
 */
export function createBoard(root, board, { cityHref = (c) => `city.html?c=${encodeURIComponent(c)}`, compact = false } = {}) {
  const state = { key: "strength", dir: -1, temps: new Set(), tier: 0, q: "", turning: false };
  root.innerHTML = `
    <div class="board-tools">
      <div class="chips" role="group" aria-label="按温度筛选">${TEMP_ORDER.map((t) =>
        `<button type="button" class="chip-btn" data-temp="${t}" aria-pressed="false">${tChip(t)}<span class="num">${board.counts[t] || 0}</span></button>`).join("")}</div>
      <select class="search" data-f="tier" aria-label="按城市层级筛选">
        <option value="0">全部城市</option><option value="1">一线（4）</option><option value="2">二线（31）</option><option value="3">三线（35）</option>
      </select>
      <input class="search" data-f="q" type="search" placeholder="搜索城市" aria-label="搜索城市" />
      <label class="check"><input type="checkbox" data-f="turning" /> 只看回暖</label>
      <span class="board-count"></span>
    </div>
    <div class="table-wrap"><table class="board"><thead></thead><tbody></tbody></table></div>`;
  const thead = root.querySelector("thead"), tbody = root.querySelector("tbody"), count = root.querySelector(".board-count");

  function render() {
    const rows = filterSort(board.rows, state);
    thead.innerHTML = "<tr>" + COLS.map((c) => {
      const sort = state.key === c.k ? (state.dir < 0 ? "descending" : "ascending") : "none";
      return `<th class="${c.cls || ""}" ${c.sortable ? `aria-sort="${sort}"` : ""}>${c.sortable ? `<button type="button" data-sort="${c.k}">${c.label}</button>` : c.label}</th>`;
    }).join("") + "</tr>";
    tbody.innerHTML = !rows.length ? `<tr class="empty"><td colspan="${COLS.length}">没有符合条件的城市。<br/><button type="button" class="btn sm outline" data-reset>清除筛选</button></td></tr>` : rows.map((r, i) => `
      <tr>
        <td class="rank">${i + 1}</td>
        <td class="l">${tChip(r.temp)}</td>
        <td class="l"><a class="city-btn" href="${cityHref(r.city)}">${esc(r.city)}</a>${r.turning ? '<span class="tag-turn" title="近 3 个月均值明显好于近 12 个月">回暖</span>' : ""}</td>
        <td><span class="strength"><span class="bar"><i style="width:${r.strength}%"></i></span><span class="num">${r.strength}</span></span></td>
        <td class="num ${cls(r.yoy - 100)}">${pct(r.yoy - 100)}</td>
        <td class="num ${cls(r.mom - 100)}">${pct(r.mom - 100)}</td>
        <td>${sparkSvg(r.spark)}</td>
        <td class="num ${cls(r.from_peak_pct)}">${pct(r.from_peak_pct)}</td>
        <td class="num ${cls(r.f12)}"><b>${pct(r.f12)}</b></td>
        <td>${microSvg(r.lo12, r.f12, r.hi12)}</td>
        <td class="num dim">${probText(r.p_up12)}</td>
      </tr>`).join("");
    count.textContent = `显示 ${rows.length} / ${board.rows.length} 城`;
  }

  root.addEventListener("click", (e) => {
    if (e.target.closest("[data-reset]")) {
      Object.assign(state, { temps: new Set(), tier: 0, q: "", turning: false });
      root.querySelectorAll("[data-temp]").forEach((b) => b.setAttribute("aria-pressed", "false"));
      root.querySelector('[data-f="tier"]').value = "0"; root.querySelector('[data-f="q"]').value = ""; root.querySelector('[data-f="turning"]').checked = false;
      return render();
    }
    const chip = e.target.closest("[data-temp]");
    if (chip) {
      const t = chip.dataset.temp, on = !state.temps.has(t);
      on ? state.temps.add(t) : state.temps.delete(t);
      chip.setAttribute("aria-pressed", String(on));
      return render();
    }
    const s = e.target.closest("[data-sort]");
    if (s) {
      const k = s.dataset.sort;
      if (state.key === k) state.dir *= -1; else { state.key = k; state.dir = k === "city" ? 1 : -1; }
      render();
    }
  });
  root.querySelector('[data-f="tier"]').addEventListener("change", (e) => { state.tier = Number(e.target.value); render(); });
  root.querySelector('[data-f="q"]').addEventListener("input", (e) => { state.q = e.target.value.trim(); render(); });
  root.querySelector('[data-f="turning"]').addEventListener("change", (e) => { state.turning = e.target.checked; render(); });
  render();
  return { state, render };
}
