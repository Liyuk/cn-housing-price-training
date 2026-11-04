import { boot } from "../core/boot.js";
import { Data } from "../core/data.js";
import { esc, grp, range } from "../core/format.js";

const KIND = { official: "官方", "official+legacy": "官方 + 旧口径镜像", third_party: "第三方", model: "模型", derived: "派生", unavailable: "无" };
const METHOD = { current: "官方页面", current_cirea: "CIREA 转载", current_cirea_legacy_doc: "CIREA 旧文档", legacy_mirror: "旧口径镜像", mirror_filled: "镜像补缺" };
const kb = (b) => (b >= 1048576 ? (b / 1048576).toFixed(1) + " MB" : Math.max(1, Math.round(b / 1024)) + " KB");

boot("data", ["meta"], ({ data, vintage, manifest }) => {
  const $ = (s) => document.querySelector(s);
  const c = data.meta.cirea, mi = c.mirror;

  $("#coverage").innerHTML = `<div style="overflow-x:auto"><table class="plain"><thead><tr><th class="l">数据集</th><th class="l">来源</th><th class="l">粒度</th><th class="l">频率</th><th>起止</th><th>期数</th><th class="l">缺口</th></tr></thead><tbody>` +
    manifest.datasets.map((d) => {
      const gaps = d.kind === "unavailable" ? "—" : d.missing.length ? `${d.missing.length} 个月（${d.missing.join("、")}）` : "无";
      return `<tr class="${d.kind === "unavailable" ? "dim" : ""}"><td class="l"><b>${esc(d.name)}</b></td><td class="l">${esc(d.source)}</td><td class="l">${esc(d.granularity)}</td><td class="l">${esc(d.freq)}</td><td class="num">${d.start ? range(d.start, d.end) : "—"}</td><td class="num">${d.n || "—"}</td><td class="l">${gaps}</td></tr>`;
    }).join("") + "</tbody></table></div>";
  const sh = manifest.datasets[0].by_methodology || {};
  const notes = manifest.datasets.filter((d) => d.note).map((d) => `${esc(d.name)}：${esc(d.note)}`).join("；");
  $("#coverage-foot").innerHTML = `${notes}。<br/>` +
    `二手住宅 ${Object.entries(sh).map(([k, v]) => `${METHOD[k] || k} ${v} 个月`).join("，")}。` +
    `${vintage.regimeBreak.month} 以前是旧口径（第三方镜像），之后是现行口径；“镜像补缺”指官方页面缺失、但镜像在可对照月份与官方逐格一致的月份。`;

  $("#cirea").innerHTML = [
    ["可直接核对官方页面", grp(c.overlap_cells), `${c.months_checked} 个月；${grp(c.cirea_cells)} 个单元中其余 ${grp(c.unverified_cells)} 个无官方页面`],
    ["与官方页面一致", grp(c.overlap_cells - c.mismatched_cells), `${((c.overlap_cells - c.mismatched_cells) / c.overlap_cells * 100).toFixed(2)}%`],
    ["不一致", String(c.mismatched_cells), `${c.mismatch_months.join("、")} · ${c.mismatch_cities.join("、")}`],
    ["无官方页面的月份，对照镜像", grp(mi.checked_cells), `${grp(mi.identical_cells)} 个一致；${mi.differing_cells} 个不同，仅出现在 ${mi.differing_cities.join("、")}（镜像自身的互换）`],
  ].map(([k, v, cap]) => `<div class="c"><span class="big">${v}</span><b style="font-size:13.5px">${k}</b><div class="cap">${cap}</div></div>`).join("");
  $("#cirea-callout").innerHTML = `对账区间 ${c.span}。行业转载<b>几乎</b>等同官方，但不是逐格相同：CIREA 文档在 ${c.mismatch_months[0]} 把 徐州↔扬州、惠州↔韶关 两对城市的数据行互换了，最大偏差 ${c.max_abs_diff.toFixed(1)} 个指数点（相关系数 ${c.r.toFixed(4)}）。` +
    `第三方镜像在 2021 年起也互换了同样四个城市，用“12 个月环比连乘 = 同比”可以证明官方页面是对的。本站面板用官方页面的值。结论：转载与镜像可以当线索，<b>不能代替</b>独立核验。`;

  const b = manifest.bundles;
  $("#bundles").innerHTML = `<div style="overflow-x:auto"><table class="plain"><thead><tr><th class="l">数据块</th><th class="l">性质</th><th class="l">频率 · 范围 · 期数 · 口径</th><th>大小</th></tr></thead><tbody>` +
    Object.entries(b).map(([name, info]) => `<tr><td class="l"><code>${name}</code></td><td class="l">${KIND[info.kind] || ""}</td><td class="l">${esc(vintage.describe(name))}</td><td class="num">${kb(info.bytes)}</td></tr>`).join("") +
    Object.entries(manifest.districts).map(([city, info]) => `<tr><td class="l"><code>districts/${esc(city)}.json</code></td><td class="l">${KIND[info.kind]}</td><td class="l">${esc(vintage.describe(city))}</td><td class="num">${kb(info.bytes)}</td></tr>`).join("") +
    "</tbody></table></div>";
  $("#downloads").innerHTML = manifest.downloads.map((d) => `<li><a href="${d.file}" download>${d.file.split("/").pop()}</a> <span class="dim">${kb(d.bytes)} · ${esc(d.note)}</span></li>`).join("");
  $("#next-release").textContent = `${vintage.nextRelease}（估计）`;
  $("#changelog").innerHTML = (manifest.changelog || []).map((e) => `<li><b>${e.run}</b> ${esc(e.text)}</li>`).join("") || '<li class="dim">暂无记录</li>';
});

