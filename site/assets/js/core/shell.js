/* Shell: header, navigation, footer and the 口径 dialog, driven only by the
   page name.  Change the navigation here once; every page follows. */

import { initTheme } from "./theme.js";
import { range, addMonths } from "./format.js";

export const PAGES = [
  { id: "home", href: "index.html", label: "总览" },
  { id: "cities", href: "cities.html", label: "城市榜" },
  { id: "stats", href: "stats.html", label: "数据统计" },
  { id: "forecast", href: "forecast.html", label: "预测逻辑" },
  { id: "data", href: "data.html", label: "数据与方法" },
  { id: "papers", href: "papers.html", label: "论文" },
];

const DEFS = (v) => `
  <h3>价格指数 ≠ 房价</h3>
  <p>城市级数据是<b>价格指数</b>：环比 = 上月 100，同比 = 上年同月 100。指数低于 100 表示下跌，不能把“指数跌 10%”读成“每平方米房价跌 10 个百分点”。图中“${v.info("cum.json").basis.split(" ")[0]} = 100”的曲线，是把每月环比连乘得到的链式指数。</p>
  <h3>全国曲线是 70 城的等权平均</h3>
  <p>全国线 = 70 座城市环比指数的简单平均再连乘，不是官方的全国房价指数，也没有按城市规模加权。一线、二线、三线同理（4 / 31 / 35 座城市）。</p>
  <h3>口径断点</h3>
  <p>${v.regimeBreak.month} 以前是旧口径（来自第三方镜像，与官方页面在可对照的月份逐格一致），${v.regimeBreak.month} 起是现行口径（直接抓取官方页面）。图上用竖线标出，<b>不要把跨过断点的涨跌幅当作同一口径</b>；预测模型只用断点之后的数据。</p>
  <h3>温度与趋势强度</h3>
  <p>温度按近 6 个月平均环比（%/月）划分：寒 ≤ −0.30，凉 −0.30 ~ −0.10，平 −0.10 ~ +0.10，温 +0.10 ~ +0.30，热 &gt; +0.30。趋势强度是近 3 个月平均环比在 70 城中的百分位。<code>回暖</code>：近 3 个月均值比近 12 个月均值高 0.15 个百分点以上，且最新一月环比不为负。</p>
  <h3>K 线是怎么来的</h3>
  <p>价格指数每月只有一个收盘值，没有日内高低点。K 线图由月度链式指数<b>合成</b>：开盘 = 上一期收盘，收盘 = 本期最后一个月，最高/最低 = 本期内各月收盘的极值。月线 K 线只有实体、没有影线；季线、年线才有影线。它是同一份数据的另一种看法，没有额外信息。</p>
  <h3>时间标注</h3>
  <p>月份写作 YYYY-MM。每张图和每个数据块标注自己的“数据截至”和起止范围，因为各来源的最新月份不同：70 城指数截至 ${v.dataThrough}，LPR 截至 ${v.asof("lpr.json")}，宏观为 ${v.asof("macro.json")} 年初累计。预测期限同时写相对和绝对，如“+12 个月（${addMonths(v.forecast.origin, 12)}）”。</p>
  <h3>预测的性质</h3>
  <p>预测只用价格自身的历史（加一个跨城市的基础模型），不含政策、利率等外生变量。各期限的实际覆盖率与相对“不变”的优势见<a href="forecast.html">预测逻辑</a>页的回测；远期只应当作情景。概率只代表模型自己的不确定性，不是对政策转向的判断。</p>
  <h3>区级与小区级数据</h3>
  <p>区县价格、租金来自<b>第三方月报</b>（每页只列前 10 名区），不是成交价；官方区级数据只有北京网签套数/面积。小区、楼盘级数据没有合规的批量来源，本站不提供。</p>`;

export function mountShell(pageId, vintage) {
  const nav = PAGES.map((p) => `<a href="${p.href}"${p.id === pageId ? ' class="on" aria-current="page"' : ""}>${p.label}</a>`).join("");
  document.querySelector("#shell-header").innerHTML = `
    <header class="topbar"><div class="wrap">
      <a class="brand" href="index.html">趋势看板<b> · 70城</b></a>
      <nav class="nav" aria-label="页面">${nav}</nav>
      <div class="top-tools">
        <span class="asof" title="70 城指数最新月份；构建于 ${vintage.builtAt}">数据截至 ${vintage.dataThrough}</span>
        <button class="ghost" id="defs-open" type="button">口径说明</button>
        <button class="ghost" id="theme-toggle" type="button" aria-label="切换深色或浅色主题">浅色</button>
      </div>
    </div></header>`;
  document.querySelector("#shell-footer").innerHTML = `
    <footer class="site wrap">
      <span>cn-housing-price-training · 数据源：国家统计局、中国人民银行、北京市住建委、中房学、creprice · K 线：TradingView Lightweight Charts™（Apache-2.0）</span>
      <span>构建于 ${vintage.builtAt} · 70 城数据 ${range(vintage.info("cum.json").start, vintage.dataThrough)} · 下一期预计 ${vintage.nextRelease}</span>
    </footer>
    <div class="modal-back" id="defs-backdrop" hidden>
      <div class="modal" role="dialog" aria-modal="true" aria-labelledby="defs-title">
        <div class="modal-head"><h2 id="defs-title">口径说明</h2><button class="ghost x" id="defs-close" type="button" aria-label="关闭">×</button></div>
        <div class="modal-body">${DEFS(vintage)}</div>
      </div>
    </div>`;
  initTheme(document.querySelector("#theme-toggle"));
  const back = document.querySelector("#defs-backdrop");
  const open = document.querySelector("#defs-open");
  const show = () => { back.hidden = false; document.body.style.overflow = "hidden"; document.querySelector("#defs-close").focus(); };
  const hide = () => { back.hidden = true; document.body.style.overflow = ""; open.focus(); };
  open.addEventListener("click", show);
  document.querySelector("#defs-close").addEventListener("click", hide);
  back.addEventListener("click", (e) => { if (e.target === back) hide(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !back.hidden) hide(); });
}

export function showError(message) {
  let el = document.querySelector("#boot-error");
  if (!el) { el = document.createElement("div"); el.id = "boot-error"; el.setAttribute("role", "alert"); document.body.appendChild(el); }
  el.textContent = message;
  el.style.display = "block";
}
