/* Window statistics as an HTML table: one row per series, same columns on every page that shows a window
   (trend view, comparison page).  Pure: entries in, string out. */

import { esc, pct, cls } from "../core/format.js";

const dash = '<span class="dim">—</span>';
const num = (v) => v.toFixed(1);

/**
 * @param entries  [{ name, color?, stats }]  stats from series.windowStats
 * @param opts     { regimeBreak, notes: [string] }
 */
export function statsTable(entries, { regimeBreak = null, notes = [] } = {}) {
  if (!entries.length) return "";
  const first = entries[0].stats;
  const rows = entries.map(({ name, color, stats: s }) => `<tr>
    <th scope="row">${color ? `<i class="dot" style="background:${color}"></i>` : ""}${esc(name)}</th>
    <td class="num">${num(s.from.v)} → ${num(s.to.v)}</td>
    <td class="num ${cls(s.change)}"><b>${pct(s.change, 1)}</b></td>
    <td class="num">${s.annualised == null ? dash : pct(s.annualised, 1)}</td>
    <td class="num down">${pct(s.maxDrawdown.pct, 1)}<span class="dim"> ${s.maxDrawdown.from} → ${s.maxDrawdown.to}</span></td>
    <td class="num">${pct(s.fromHigh, 1)}<span class="dim"> 高点 ${s.high.m}</span></td>
    <td class="num">${s.upShare == null ? dash : Math.round(s.upShare * 100) + "%"}</td>
  </tr>`).join("");
  const warn = entries.some((e) => e.stats.crossesBreak)
    ? `<p class="callout">区间跨越口径断点 ${esc(regimeBreak)}：此前为旧口径（第三方镜像），此后为现行口径（官方页面），断点两侧的涨跌幅不宜直接比较。</p>`
    : "";
  const short = first.annualised == null ? "区间不足 12 个月，不折算年化。" : "";
  return `<div class="tv-stats-head"><b>区间统计</b><span class="dim">${first.from.m} → ${first.to.m} · ${first.months} 个月（基于指数水平，不随上方指标切换）</span></div>
    <div style="overflow-x:auto"><table class="plain stats"><thead><tr><th>序列</th><th>起点 → 终点</th><th>累计涨跌</th><th>年化</th><th>最大回撤</th><th>距区间高点</th><th>上涨月占比</th></tr></thead><tbody>${rows}</tbody></table></div>
    ${warn}${[short, ...notes].filter(Boolean).map((n) => `<p class="foot">${n}</p>`).join("")}`;
}
