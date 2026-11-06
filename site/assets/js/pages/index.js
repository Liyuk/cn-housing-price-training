import { boot } from "../core/boot.js";
import { Data } from "../core/data.js";
import { createTrendView } from "../domain/trend-view.js";
import { pct, cls, addMonths } from "../core/format.js";
import { icon } from "../core/icons.js";

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

  createTrendView(document.querySelector("#hero-view"), { data: { cum, fan }, region: "全国", zones: vintage.forecast, newHome: () => Data.load("cum_new"), urlSync: true });
  document.querySelector("#hero-foot").innerHTML =
    `指数为 70 城等权二手住宅（${cum.base.split("（")[0]}，环比链式累乘）。折线图：金色底纹为<b>上行阶段</b>（近 6 个月平均环比 &gt; 0），点线为口径断点，` +
    `深色带是 +${vintage.forecast.reliable_through} 个月内的 80% 区间（回测校准），中等色带到 +${vintage.forecast.caution_through} 个月（<b>谨慎参考</b>），最浅的是 +${vintage.forecast.horizon_months} 个月前的<b>情景区间</b>。K 线图的每个标注见图上方图例；K 线由月度指数合成，见“口径说明”。`;

  const last = br.up_mom.length - 1;
  const recent = br.months.slice(-12);
  let peakI = last;
  br.up_mom.forEach((v, i) => { if (br.months[i] >= recent[0] && v > br.up_mom[peakI]) peakI = i; });
  const hc = scorecard.hindcast, m3 = hc.city_mae_pct_points["3"], f3 = hc.flat_mae_pct_points["3"];
  const row = (k, v, note) => `<tr><th scope="row">${k}</th><td><b>${v}</b><span class="note">${note}</span></td></tr>`;
  document.querySelector("#kpis").innerHTML = [
    row(`+12 个月（${h12}）`, `<span class="${cls(nat.chg12)}">${pct(nat.chg12)}</span>`, `80% 区间 ${pct(nat.lo12)} ~ ${pct(nat.hi12)}，高于现价的概率约 ${Math.round(nat.p_up12 * 100)}%`),
    row(`${br.months[last]} 环比上涨的城市`, `${br.up_mom[last]} / ${br.n[last]} 城`, `近 12 个月最多：${br.months[peakI]}（${br.up_mom[peakI]} 城）`),
    row(`距 ${ph.peak.m} 高点`, `<span class="down">${pct(ph.from_peak_pct)}</span>`, `已过 ${ph.months_since_peak} 个月，价位回到 ${ph.back_to || "—"}`),
    row("预测的近期成绩", `${Math.round((1 - m3 / f3) * 100)}% 优于“不变”`, `${hc.origin} 起 ${hc.months_scored} 个月内，70 城平均误差 ${m3.toFixed(2)} 个百分点（不变：${f3.toFixed(2)}）`),
  ].join("");

  const wf = scorecard.walk_forward;
  const item = (href, title, body, meta) => `<li><a href="${href}"><span class="t1">${title}</span>${icon("chevron-right", 18).replace('class="icon"', 'class="icon chev"')}<span class="t2">${body}</span><span class="t3">${meta}</span></a></li>`;
  document.querySelector("#entries").innerHTML = [
    item("cities.html", "城市榜", `70 城按趋势强度排序，${counts["寒"] || 0} 座“寒”、${warmHot} 座“温/热”`, `${vintage.dataThrough} · 点城市看走势、预测与区县`),
    item("compare.html", "对比", "选 2–5 个地区叠加：统一基期、同比、距高点，自定义时间范围并看区间统计", "链接保留当前选择，可分享"),
    item("stats.html", "数据统计", "层级走势、上涨城市数、同比热力图、宏观、租金收益率", vintage.describe("cum.json", { basis: false })),
    item("forecast.html", "预测逻辑", `+${vintage.forecast.reliable_through} 个月比“不变”准 ${Math.round(wf.skill_vs_flat[wf.horizons.indexOf(vintage.forecast.reliable_through)] * 100)}%；+${wf.horizons[wf.horizons.length - 1]} 个月比“不变”${wf.skill_vs_flat[wf.skill_vs_flat.length - 1] < 0 ? "还差" : "仅好"} ${Math.abs(Math.round(wf.skill_vs_flat[wf.skill_vs_flat.length - 1] * 100))}%`, `回测起点 ${wf.scored_from} 起 · 账本 ${scorecard.ledger.length} 期`),
    item("data.html", "数据与方法", "来源、口径、缺口、对账结果与下载", `下一期预计 ${vintage.nextRelease}`),
  ].join("");
});
