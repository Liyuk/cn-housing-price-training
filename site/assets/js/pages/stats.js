import { boot } from "../core/boot.js";
import { Data } from "../core/data.js";
import { mount, whenVisible } from "../core/charts.js";
import { createTrendView } from "../domain/trend-view.js";
import { breadthOption, heatOption, compareOption, macroOption, lprOption, withWindow } from "../domain/market-charts.js";
import { windowFromUrl } from "../core/timewindow.js";
import { mountWindowBar } from "../core/windowbar.js";
import { yieldBarOption, officialOption } from "../domain/district-charts.js";
import { pct, grp, range } from "../core/format.js";

boot("stats", ["cum", "breadth"], ({ data, vintage }) => {
  const { cum, breadth } = data;
  const $ = (s) => document.querySelector(s);

  // one time window for every chart on the page (?r=5, ?r=custom&f=…&t=…); each chart resolves it against its own months
  const win = windowFromUrl({ bounds: { first: cum.months[0], last: vintage.dataThrough }, defaults: { range: "all" } });
  mountWindowBar($("#window-bar"), win, { months: cum.months, label: "共用时间范围" });
  $("#window-bar").insertAdjacentHTML("beforeend", '<span class="note">作用于下面所有按月的图；宏观与 LPR 只有近几年的数据，超出的部分不显示。</span>');
  const redraws = [];
  const windowed = (el, months, build) => { const draw = () => mount(el, () => withWindow(build(), months, win.resolve(months))); draw(); redraws.push(draw); };
  win.subscribe(() => redraws.forEach((draw) => draw()));

  // 1. tiers -- same TrendView as the home page, region switchable; tiers have no forecast fan
  createTrendView($("#tier-view"), { data: { cum, fan: { regions: {}, fc_months: [] } }, region: "全国", regions: ["全国", "一线", "二线", "三线"], allowCompare: true, newHome: () => Data.load("cum_new"), window: win, urlSync: true });
  $("#tier-foot").textContent = `等权链式指数（${cum.base.split("（")[0]}，环比链式累乘）。一线 4 城、二线 31 城、三线 35 城各自对环比取平均再连乘；折线图中点线为口径断点，K 线图中以“口径断点”标记。`;

  // 2. breadth
  windowed($("#chart-breadth"), breadth.months, () => breadthOption(breadth));
  const last = breadth.up_mom.length - 1;
  $("#breadth-foot").innerHTML = `${breadth.months[last]} 有 <b>${breadth.up_mom[last]}</b> / ${breadth.n[last]} 城环比上涨。${vintage.describe("breadth.json", { basis: false })}。`;

  // below the fold: load on approach
  whenVisible($("#heat-card"), async () => {
    const c = await Data.load("cities_yoy");
    windowed($("#chart-heat"), c.months, () => heatOption(c));
  });
  whenVisible($("#compare-card"), async () => {
    const m = await Data.load("market_compare");
    windowed($("#chart-compare"), m.months, () => compareOption(m));
  });
  whenVisible($("#macro-card"), async () => {
    const [macro, lpr] = await Promise.all([Data.load("macro"), Data.load("lpr")]);
    const sel = $("#macro-picker");
    sel.innerHTML = macro.metrics.map((m) => `<option value="${m.key}">${m.label}</option>`).join("");
    const lprMonths = lpr.map((r) => r.m);
    const drawMacro = () => mount($("#chart-macro"), () => withWindow(macroOption(macro, sel.value), macro.months, win.resolve(macro.months)));
    sel.addEventListener("change", drawMacro);
    drawMacro(); redraws.push(drawMacro);
    windowed($("#chart-lpr"), lprMonths, () => lprOption(lpr));
    const li = macro.months.length - 1, inv = macro.inventory_wan_m2[li], inv0 = macro.series.development_investment_yoy;
    $("#macro-lead").textContent = `开发投资同比（年初累计）${macro.months[0]} 为 ${pct(inv0[0])}，${macro.months[li]} 为 ${pct(inv0[li])}；商品房待售面积 ${inv.toFixed(2)} 亿㎡（${macro.months[li]}，累计口径）。`;
    const l = lpr[lpr.length - 1];
    $("#lpr-foot").textContent = `5 年期以上 LPR：${lpr[0].lpr_5y}%（${lpr[0].m}）→ ${l.lpr_5y}%（${l.m}）。LPR 每月 20 日公告，因此最新一期比 70 城指数更新。`;
  });
  whenVisible($("#yield-card"), async () => {
    const [y, official] = await Promise.all([Data.tryLoad("yield"), Data.load("official")]);
    if (y) {
      mount($("#chart-yield"), () => yieldBarOption(y));
      $("#yield-foot").innerHTML = `${y.note}<br/>${vintage.describe("yield.json", { basis: false })}。第三方月报，非成交价；柱右侧是该月两个榜单都列出的区数（1–10 个不等，区数少的城市中位数不稳）。点城市榜里的城市，可在城市页搜索区县。`;
    } else {
      $("#yield-card").innerHTML = '<p class="callout">租金收益率数据尚未生成。运行 <code>python -m src.creprice_panel</code> 采集后重新构建。</p>';
    }
    $("#official-total").textContent = grp(official.total_units);
    $("#official-month").textContent = official.month;
    mount($("#chart-official"), () => officialOption(official));
  });
});
