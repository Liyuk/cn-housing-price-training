import { boot } from "../core/boot.js";
import { createTrendView } from "../domain/trend-view.js";
import { pct, cls, range, addMonths } from "../core/format.js";

boot("home", ["board", "cum", "fan", "breadth", "scorecard"], ({ data, vintage }) => {
  const { board, cum, fan, breadth: br, scorecard } = data;
  const nat = board.national, ph = cum.phases["全国"], counts = board.counts;
  const s = cum.series["全国"], n = s.length;
  const mean = (a, b) => { let t = 0; for (let i = a; i < b; i++) t += s[i] / s[i - 1] - 1; return (t / (b - a)) * 100; };
  const m6 = mean(n - 6, n), m6p = mean(n - 12, n - 6);

  const trend = m6 < -0.05 ? "仍在下行" : m6 > 0.05 ? "已经转升" : "基本持平";
  const d = m6 - m6p;
  const tail = d > 0.08 ? (m6 < 0 ? "，跌速在收窄" : "，涨势在加强") : d < -0.08 ? (m6 < 0 ? "，跌速在加快" : "，涨势在减弱") : "";
  document.querySelector("#headline").textContent = `全国二手住宅价格${trend}${tail}`;
  const warmHot = (counts["温"] || 0) + (counts["热"] || 0);
  const h12 = addMonths(vintage.forecast.origin, 12);
  document.querySelector("#lead").innerHTML =
    `截至 ${vintage.dataThrough}，70 城等权指数比 ${ph.peak.m} 的高点低 <b>${Math.abs(ph.from_peak_pct).toFixed(1)}%</b>，已回到 ${ph.back_to || "更早"} 的水平。` +
    `近 6 个月（${addMonths(vintage.dataThrough, -5)} → ${vintage.dataThrough}）平均每月${m6 < 0 ? "下跌" : "上涨"} <b>${Math.abs(m6).toFixed(2)}%</b>，此前 6 个月为 ${Math.abs(m6p).toFixed(2)}%。` +
    `${counts["寒"] || 0} 座城市处于“寒”，${warmHot} 座已进入“温”或“热”。` +
    `模型预期到 ${h12}（+12 个月）累计 <b>${pct(nat.chg12)}</b>，80% 区间 ${pct(nat.lo12)} ~ ${pct(nat.hi12)}，高于现价的概率约 ${Math.round(nat.p_up12 * 100)}%。`;

  createTrendView(document.querySelector("#hero-view"), { data: { cum, fan }, region: "全国", zones: vintage.forecast });
  document.querySelector("#hero-foot").innerHTML =
    `金色为 70 城等权二手住宅指数（${cum.base.split("（")[0]}，环比链式累乘）；金色底纹为<b>上行阶段</b>（近 6 个月平均环比 &gt; 0）；点线为口径断点。` +
    `深色带是 +${vintage.forecast.reliable_through} 个月内的 80% 区间（回测校准），中等色带到 +${vintage.forecast.caution_through} 个月（<b>谨慎参考</b>），最浅的是 +${vintage.forecast.horizon_months} 个月前的<b>情景区间</b>。K 线由月度指数合成，见“口径说明”。`;

  const last = br.up_mom.length - 1;
  const recent = br.months.slice(-12);
  let peakI = last;
  br.up_mom.forEach((v, i) => { if (br.months[i] >= recent[0] && v > br.up_mom[peakI]) peakI = i; });
  const hc = scorecard.hindcast, m3 = hc.city_mae_pct_points["3"], f3 = hc.flat_mae_pct_points["3"];
  const kpi = (k, v, dd) => `<div class="kpi"><div class="k">${k}</div><div class="v">${v}</div><div class="d">${dd}</div></div>`;
  document.querySelector("#kpis").innerHTML = [
    kpi(`+12 个月（${h12}）`, `<span class="${cls(nat.chg12)}">${pct(nat.chg12)}</span>`, `80% 区间 ${pct(nat.lo12)} ~ ${pct(nat.hi12)}<br/>高于现价的概率 ≈ ${Math.round(nat.p_up12 * 100)}%`),
    kpi(`${br.months[last]} 环比上涨的城市`, `${br.up_mom[last]}<small>/ ${br.n[last]} 城</small>`, `近 12 个月最多：${br.months[peakI]}（${br.up_mom[peakI]} 城）`),
    kpi(`距 ${ph.peak.m} 高点`, `<span class="down">${pct(ph.from_peak_pct)}</span>`, `已过 ${ph.months_since_peak} 个月<br/>价位回到 ${ph.back_to || "—"}`),
    kpi("预测的近期成绩", `${Math.round((1 - m3 / f3) * 100)}%<small>优于“不变”</small>`, `${hc.origin} 起 ${hc.months_scored} 个月内，70 城平均误差 ${m3.toFixed(2)} 个百分点（不变：${f3.toFixed(2)}）`),
  ].join("");

  const wf = scorecard.walk_forward;
  const card = (href, title, body, meta) => `<a class="card-link" href="${href}"><b>${title}</b><span>${body}</span><em>${meta}</em></a>`;
  document.querySelector("#entries").innerHTML = [
    card("cities.html", "城市榜", `70 城按趋势强度排序，${counts["寒"] || 0} 座“寒”、${warmHot} 座“温/热”`, `${vintage.dataThrough} · 点城市看区县`),
    card("stats.html", "数据统计", "层级走势、上涨城市数、同比热力图、宏观、租金收益率", vintage.describe("cum.json", { basis: false })),
    card("forecast.html", "预测逻辑", `+${vintage.forecast.reliable_through} 个月比“不变”准 ${Math.round(wf.skill_vs_flat[wf.horizons.indexOf(vintage.forecast.reliable_through)] * 100)}%；+${wf.horizons[wf.horizons.length - 1]} 个月仅 ${Math.round(wf.skill_vs_flat[wf.skill_vs_flat.length - 1] * 100)}%`, `回测起点 ${wf.scored_from} 起 · 账本 ${scorecard.ledger.length} 期`),
    card("data.html", "数据与方法", "来源、口径、缺口、对账结果与下载", `下一期预计 ${vintage.nextRelease}`),
  ].join("");
});
