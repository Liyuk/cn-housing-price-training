/* Scorecard: how good the forecasts have been.  Renders the replay table,
   the frozen-forecast ledger, the per-model error table, and the skill /
   coverage option builders.  All dates come from the scorecard data itself. */

import { tok } from "../core/theme.js";
import { kit } from "../core/charts.js";
import { pct } from "../core/format.js";
import { icon } from "../core/icons.js";

export const MODEL_LABEL = {
  naive: "上月持续", drift12: "12 月均值", ar1: "AR(1) 回归", damped: "阻尼趋势", global: "跨城市 GBM",
  damped_shrunk: "收缩阻尼趋势", chronos2: "Chronos-2（零样本）", ensemble: "组合（本站预测）", flat: "价格不变（基准）",
};
const verdict = (ok) => `<span class="verdict ${ok ? "in" : "out"}">${icon(ok ? "check" : "x", 14)}${ok ? "区间内" : "区间外"}</span>`;
const inside = (a, lo, hi) => a >= lo && a <= hi;

export function renderHindcast(sc, tableEl, calloutEl) {
  const hc = sc.hindcast, v02 = sc.v02.regions;
  const regions = ["全国", "北京", "上海", "广州", "深圳"];
  let newIn = 0, newN = 0;
  const body = regions.flatMap((r) => Object.entries(hc.regions[r]).map(([h, x], i) => {
    const old = v02[r] && v02[r][Number(h) - 1];
    const ni = inside(x.actual, x.lo80, x.hi80); newN++; newIn += ni;
    let oldCell = '<td class="dim">—</td><td></td>';
    if (old) oldCell = `<td class="num">${old.base.toFixed(2)}<span class="dim"> （${old.low.toFixed(2)} ~ ${old.high.toFixed(2)}）</span></td><td>${verdict(inside(old.actual, old.low, old.high))}</td>`;
    return `<tr><td>${i === 0 ? `<b>${r}</b>` : ""}</td><td>${hc.origin} +${h}</td><td class="num"><b>${x.actual.toFixed(2)}</b></td>${oldCell}<td class="num">${x.point.toFixed(2)}<span class="dim"> （${x.lo80.toFixed(2)} ~ ${x.hi80.toFixed(2)}）</span></td><td>${verdict(ni)}</td></tr>`;
  })).join("");
  tableEl.innerHTML = `<div style="overflow-x:auto"><table class="plain"><thead><tr><th>地区</th><th>预测起点 +月数</th><th>实际</th><th>v0.2 基准（区间）</th><th>v0.2</th><th>新模型中位（80% 区间）</th><th>新模型</th></tr></thead><tbody>${body}</tbody></table></div>`;
  const bj = v02["北京"], nat = v02["全国"], bjOut = bj.filter((x) => x.actual > x.high).length;
  const m3 = hc.city_mae_pct_points["3"], f3 = hc.flat_mae_pct_points["3"];
  calloutEl.innerHTML =
    `数值为“预测起点月 = 100”的累计指数。<b>这是事后回放，不是事前预测</b>：新模型是在这 ${hc.months_scored} 个月公布之后才定型的，只是权重、区间和 Chronos-2 预测都严格只用 ${hc.origin} 及以前的数据。真正的事前检验见下方的预测账本。` +
    `<br/><b>新模型</b>：${newN} 个检验点中 ${newIn} 个落在 80% 区间内；70 城 3 个月内平均误差 ${m3.toFixed(2)} 个百分点，“价格不变”为 ${f3.toFixed(2)}。` +
    `<b>v0.2 论文模型</b>：北京有 ${bjOut} / ${bj.length} 个月高于其区间上沿，全国 ${nat[nat.length - 1].actual > nat[nat.length - 1].high ? "最后一个月也高于区间上沿" : "仍在区间内，但贴近上沿"}——其趋势成分滞后于拐点，区间也偏窄。`;
}

export function renderLedger(sc, el, nextRelease, horizon) {
  const entries = (sc.ledger || []).slice().reverse();
  el.innerHTML = entries.map((e) => {
    const head = `<p style="margin:0 0 6px"><b>${e.origin}</b> 的预测已冻结于 <code>${e.frozen_file}</code>（含 70 城 × ${horizon} 个月的全部分位数）。`;
    if (!e.months_scored) return head + `最新数据仍是 ${e.latest_data}，<b>等待下一期官方数据公布后自动评分</b>（预计 ${nextRelease}，估计值）。</p>`;
    const rows = e.scored.map((x) => {
      const n = x.national;
      return `<tr><td>${x.month}（+${x.h}）</td><td class="num"><b>${n.actual.toFixed(2)}</b></td><td class="num">${n.median.toFixed(2)}<span class="dim"> （${n.lo80.toFixed(2)} ~ ${n.hi80.toFixed(2)}）</span></td><td>${verdict(inside(n.actual, n.lo80, n.hi80))}</td><td class="num">${Math.round(x.city_inside80 * 100)}%</td><td class="num">${x.city_mae_pct_points.toFixed(2)} / ${x.flat_mae_pct_points.toFixed(2)}</td></tr>`;
    }).join("");
    return head + `</p><table class="plain"><thead><tr><th>月份</th><th>全国实际</th><th>预测中位（80% 区间）</th><th>全国</th><th>70 城落入区间</th><th>70 城误差 / 不变</th></tr></thead><tbody>${rows}</tbody></table>`;
  }).join("") || '<p class="dim">暂无冻结的预测。</p>';
}

export function renderModelTable(sc, tableEl, footEl, nOriginsEl) {
  const w = sc.walk_forward, hs = w.horizons;
  const order = ["flat", "naive", "drift12", "ar1", "damped", "damped_shrunk", "global", "chronos2", "ensemble"];
  const horizonOf = (m) => (m === "chronos2" ? 12 : m === "global" ? 36 : Infinity);   // models that are not run past their trained horizon
  const best = hs.map((h) => Math.min(...order.filter((m) => m !== "flat" && h <= horizonOf(m)).map((m) => w.mae[m][h]).filter((v) => v != null)));
  const rows = order.map((m) => `<tr><td>${m === "ensemble" ? "<b>" : ""}${MODEL_LABEL[m]}${m === "ensemble" ? "</b>" : ""}</td>` + hs.map((h, i) => {
    const v = w.mae[m] && w.mae[m][h];
    if (v == null || h > horizonOf(m)) return '<td class="dim">—</td>';
    return `<td class="num ${m !== "flat" && v === best[i] ? "best" : ""}">${v.toFixed(2)}</td>`;
  }).join("") + "</tr>").join("");
  tableEl.innerHTML = `<table class="plain"><thead><tr><th>模型</th>${hs.map((h) => `<th>+${h} 个月</th>`).join("")}</tr></thead><tbody>${rows}</tbody></table>`;
  nOriginsEl.textContent = w.n_origins;
  const last = hs[hs.length - 1], skillLast = Math.round(w.skill_vs_flat[hs.indexOf(last)] * 100);
  footEl.innerHTML = `金色为每列最小误差。回测起点为 ${w.scored_from} 起每 3 个月一次（${w.n_origins} 个），每个起点的权重与区间只用当时已公布的数据。` +
    `13 个月以后组合固定使用收缩阻尼趋势（所以与其数值相同）；Chronos-2 只预测到 12 个月，跨城市 GBM 到 36 个月。` +
    `<b>这条长期规则不是盲选</b>：阻尼系数在 0.90–0.96 之间结果几乎不变，不阻尼（系数 1）则明显更差；但“收缩 40%”是在同一回测里从三个取值中选的，所以 +24 个月的成绩略偏乐观。` +
    `<b>+${last} 个月比“价格不变”${skillLast >= 0 ? "好" : "还差"} ${Math.abs(skillLast)}%</b>：只有 2019–2021 年上涨期的起点能检验到这么远，动量外推在转折点上失效——五年期只能当情景。`;
}

export function skillOption(sc) {
  const w = sc.walk_forward, labels = w.horizons.map((h) => `+${h} 个月`);
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 44, right: 12, top: 18, bottom: 26 },
    tooltip: Object.assign(kit.tooltip(), { formatter: (p) => `${p[0].name}：误差比“不变”${p[0].value >= 0 ? "低" : "高"} <b>${Math.abs(p[0].value).toFixed(0)}%</b>` }),
    xAxis: Object.assign(kit.axis(), { type: "category", data: labels, splitLine: { show: false } }),
    yAxis: kit.valueAxis({ axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: "{value}%" } }),
    series: [{ type: "bar", barWidth: "52%",
      data: w.skill_vs_flat.map((v, i) => ({ value: +(v * 100).toFixed(1), itemStyle: { color: w.horizons[i] <= 12 ? tok("gold") : tok("ink-3"), borderRadius: v >= 0 ? [3, 3, 0, 0] : [0, 0, 3, 3] } })),
      label: { show: true, position: "top", color: tok("ink-2"), fontSize: 11.5, formatter: (p) => p.value.toFixed(0) + "%" } }],
  };
}

export function coverOption(sc) {
  const w = sc.walk_forward, labels = w.horizons.map((h) => `+${h} 个月`);
  return {
    animationDuration: 400, textStyle: kit.text(),
    grid: { left: 44, right: 26, top: 18, bottom: 26 },
    tooltip: Object.assign(kit.tooltip(), { formatter: (p) => `${p[0].name}：标称 80% 区间实际覆盖 <b>${p[0].value.toFixed(0)}%</b>` }),
    xAxis: Object.assign(kit.axis(), { type: "category", data: labels, splitLine: { show: false }, boundaryGap: false }),
    yAxis: kit.valueAxis({ min: 0, max: 100, axisLabel: { color: tok("ink-3"), fontSize: 11.5, formatter: "{value}%" } }),
    series: [{ type: "line", data: w.coverage80.map((v) => +(v * 100).toFixed(1)), symbolSize: 8,
      lineStyle: { color: tok("gold"), width: 2 }, itemStyle: { color: tok("gold"), borderColor: tok("panel"), borderWidth: 2 },
      label: { show: true, position: "top", color: tok("ink-2"), fontSize: 11.5, formatter: (p) => p.value.toFixed(0) + "%" },
      markLine: { symbol: "none", silent: true, data: [{ yAxis: 80, lineStyle: { color: tok("blue"), type: "dashed", width: 1 }, label: { formatter: "理想 80%", color: tok("blue"), fontSize: 11.5, position: "insideEndTop" } }] } }],
  };
}
