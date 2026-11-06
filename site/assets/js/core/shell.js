/* Shell: header, navigation and footer, driven only by the page name.
   Change the navigation here once; every page follows.  The 口径说明 link goes to the data page
   (a section, not a modal: nothing here needs to interrupt the reader). */

import { initTheme } from "./theme.js";
import { icon } from "./icons.js";
import { range } from "./format.js";

export const PAGES = [
  { id: "home", href: "index.html", label: "总览" },
  { id: "cities", href: "cities.html", label: "城市榜" },
  { id: "compare", href: "compare.html", label: "对比" },
  { id: "stats", href: "stats.html", label: "数据统计" },
  { id: "forecast", href: "forecast.html", label: "预测逻辑" },
  { id: "data", href: "data.html", label: "数据与方法" },
  { id: "papers", href: "papers.html", label: "论文" },
];

export function mountShell(pageId, vintage) {
  const nav = PAGES.map((p) => `<a href="${p.href}"${p.id === pageId ? ' class="on" aria-current="page"' : ""}>${p.label}</a>`).join("");
  document.querySelector("#shell-header").innerHTML = `
    <header class="topbar"><div class="wrap">
      <a class="brand" href="index.html">趋势看板<b> · 70城</b></a>
      <nav class="nav" aria-label="页面">${nav}</nav>
      <div class="top-tools">
        <span class="badge asof" title="70 城指数最新月份；构建于 ${vintage.builtAt}">数据截至 ${vintage.dataThrough}</span>
        <a class="btn sm" href="data.html#definitions">口径说明</a>
        <button class="btn sm icon-only" id="theme-toggle" type="button"></button>
      </div>
    </div></header>`;
  document.querySelector("#shell-footer").innerHTML = `
    <footer class="site wrap">
      <span>cn-housing-price-training · 数据源：国家统计局、中国人民银行、北京市住建委、中房学、creprice · K 线：TradingView Lightweight Charts™（Apache-2.0）· 字体 Geist（OFL）· 图标 Lucide（ISC）</span>
      <span>构建于 ${vintage.builtAt} · 70 城数据 ${range(vintage.info("cum.json").start, vintage.dataThrough)} · 下一期预计 ${vintage.nextRelease}</span>
    </footer>`;
  initTheme(document.querySelector("#theme-toggle"));
}

export function showError(message) {
  let el = document.querySelector("#boot-error");
  if (!el) { el = document.createElement("div"); el.id = "boot-error"; el.setAttribute("role", "alert"); document.body.appendChild(el); }
  el.textContent = message;
  el.style.display = "block";
}
