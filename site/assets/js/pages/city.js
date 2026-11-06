import { boot } from "../core/boot.js";
import { Data } from "../core/data.js";
import { createTrendView } from "../domain/trend-view.js";
import { fanTable } from "../domain/trend-chart.js";
import { mountDistrictExplorer } from "../domain/district-charts.js";
import { tChip } from "../domain/board.js";
import { icon } from "../core/icons.js";
import { pct, cls, probText, esc, addMonths, range } from "../core/format.js";

boot("cities", ["board", "cum", "fan"], async ({ data, vintage }) => {
  const { board, cum, fan } = data;
  const city = new URLSearchParams(location.search).get("c");
  const row = board.rows.find((r) => r.city === city);
  const head = document.querySelector("#city-head");
  document.querySelector("#back-link").innerHTML = icon("arrow-left", 14) + "城市榜";

  const picker = document.querySelector("#city-picker");
  picker.innerHTML = board.rows.slice().sort((a, b) => a.city.localeCompare(b.city, "zh")).map((r) => `<option value="${esc(r.city)}"${r.city === city ? " selected" : ""}>${esc(r.city)}</option>`).join("");
  if (!city) picker.insertAdjacentHTML("afterbegin", '<option value="" selected disabled>选择城市…</option>');
  picker.addEventListener("change", () => { location.search = "?c=" + encodeURIComponent(picker.value); });

  if (!row) {
    head.innerHTML = `<h1>${city ? `没有找到“${esc(city)}”` : "选择一个城市"}</h1><p class="lead">本站覆盖国家统计局 70 个大中城市。可以从上面的列表选择，或回到<a href="cities.html">城市榜</a>。</p>`;
    document.querySelectorAll(".city-only").forEach((el) => (el.hidden = true));
    return;
  }
  document.title = `${city} · 趋势看板`;
  const ph = cum.phases[city], f = fan.regions[city];
  head.innerHTML = `
    <div class="city-title"><h1>${esc(city)}</h1>${tChip(row.temp)}${row.turning ? '<span class="tag-turn">回暖</span>' : ""}<span class="dim">趋势强度 ${row.strength}</span></div>
    <p class="lead">${vintage.dataThrough} 同比 <b class="${cls(row.yoy - 100)}">${pct(row.yoy - 100)}</b>，环比 <b class="${cls(row.mom - 100)}">${pct(row.mom - 100)}</b>。` +
    `比 ${ph.peak.m} 的高点低 <b>${Math.abs(ph.from_peak_pct).toFixed(1)}%</b>，价位回到 ${ph.back_to || "更早"}。` +
    `模型预期 +12 个月（${addMonths(vintage.forecast.origin, 12)}）累计 <b class="${cls(row.f12)}">${pct(row.f12)}</b>，80% 区间 ${pct(row.lo12, 0)} ~ ${pct(row.hi12, 0)}。</p>`;

  const fact = (k, v, small) => `<div class="fact"><div class="k">${k}</div><div class="v">${v}${small ? `<small> ${small}</small>` : ""}</div></div>`;
  document.querySelector("#city-facts").innerHTML = [
    fact(`同比（${vintage.dataThrough}）`, `<span class="${cls(row.yoy - 100)}">${pct(row.yoy - 100)}</span>`),
    fact("环比", `<span class="${cls(row.mom - 100)}">${pct(row.mom - 100)}</span>`),
    fact("距高点", `<span class="${cls(ph.from_peak_pct)}">${pct(ph.from_peak_pct)}</span>`, `高点 ${ph.peak.m}`),
    fact("价位回到", ph.back_to || "—"),
    fact("最大回撤", `<span class="down">${pct(ph.max_drawdown.pct)}</span>`, range(ph.max_drawdown.from, ph.max_drawdown.to)),
    fact("最大涨幅", `<span class="up">${pct(ph.max_rally.pct)}</span>`, range(ph.max_rally.from, ph.max_rally.to)),
    fact("+12 个月预测", `<span class="${cls(row.f12)}">${pct(row.f12)}</span>`, `${pct(row.lo12, 0)} ~ ${pct(row.hi12, 0)}`),
    fact("高于现价概率", probText(row.p_up12), "+12 个月"),
  ].join("");

  createTrendView(document.querySelector("#city-view"), { data: { cum, fan }, region: city, allowCompare: true, zones: vintage.forecast });
  document.querySelector("#city-view-foot").innerHTML = `${city}与全国的链式指数均以 ${cum.base.split("（")[0]} 起算；${vintage.describe("cum.json", { basis: false })}。折线图中灰色竖线右侧为预测，K 线图中以“数据截止”标记为界。`;
  document.querySelector("#city-fan").innerHTML = fanTable(fan, city, vintage.forecast.origin, { reliable: vintage.forecast.reliable_through, caution: vintage.forecast.caution_through });
  document.querySelector("#city-fan-note").textContent = `预测起点 ${vintage.forecast.origin}，${vintage.describe("fan.json", { basis: false })}。+${vintage.forecast.reliable_through} 个月内可作预测，至 +${vintage.forecast.caution_through} 个月谨慎参考，其后仅作情景。`;

  const dist = await Data.tryLoad("districts/" + city).catch(() => null);
  const box = document.querySelector("#district-box");
  if (dist) {
    mountDistrictExplorer(box, dist);
  } else {
    const have = Object.keys(vintage.manifest.districts || {});
    box.innerHTML = `<p class="callout">暂无 ${esc(city)} 的区县数据。区县价格、租金目前只覆盖 ${have.length} 座城市（${have.map(esc).join("、") || "—"}），来自第三方月报，每页只列前 10 名区；其余城市没有可批量获取的区级月度数据。</p>`;
  }
});
