/* Ledger view: what was predicted (frozen), when it was frozen, and what happened since.
   The chart option and the render function; the data side is ledger-model.js.  Levels are "origin month = 100". */

import { kit, mount } from "../core/charts.js";
import { tok } from "../core/theme.js";
import { esc, pct, addMonths } from "../core/format.js";
import { icon } from "../core/icons.js";
import { regionPath, verdictOf } from "./ledger-model.js";

export const REPO_URL = "https://github.com/Liyuk/cn-housing-price-training";

export function ledgerOption(path, theme = { tok }) {
  const t = theme.tok;
  const gold = t("gold");
  const months = path.map((p) => p.month);
  const x = ["起点", ...months];
  const base = [100];
  const lo = base.concat(path.map((p) => p.lo)), hi = base.concat(path.map((p) => p.hi));
  return {
    animationDuration: 300, textStyle: kit.text(),
    grid: { left: 48, right: 14, top: 44, bottom: 28 },
    legend: { ...kit.legend(["冻结的中位数", "80% 区间", "实际"]), data: ["冻结的中位数", "80% 区间", "实际"] },
    tooltip: Object.assign(kit.tooltip(), { formatter: (p) => {
      const i = p[0].dataIndex;
      if (i === 0) return "<b>预测起点</b>：100";
      const r = path[i - 1];
      return `<b>${r.month}（+${r.h}）</b><br/>冻结的中位数：<b>${r.median.toFixed(2)}</b><br/>80% 区间：${r.lo.toFixed(2)} ~ ${r.hi.toFixed(2)}<br/>实际：<b>${r.actual == null ? "尚未公布" : r.actual.toFixed(2)}</b>`;
    } }),
    xAxis: Object.assign(kit.axis(), { type: "category", data: x, boundaryGap: false, splitLine: { show: false }, axisLabel: { color: t("ink-3"), fontSize: 11.5, hideOverlap: true, formatter: (v) => (v === "起点" ? v : v.slice(2)) } }),
    yAxis: kit.valueAxis({ scale: true, name: "指数（起点月 = 100）", nameLocation: "end", nameGap: 12, nameTextStyle: { color: t("ink-3"), fontSize: 11.5, align: "left", padding: [0, 0, 0, -40] } }),
    series: [
      { name: "_lo", type: "line", data: lo, stack: "band", symbol: "none", lineStyle: { width: 0 }, silent: true, tooltip: { show: false } },
      { name: "80% 区间", type: "line", data: hi.map((v, i) => +(v - lo[i]).toFixed(2)), stack: "band", symbol: "none", lineStyle: { width: 0 }, areaStyle: { color: gold, opacity: 0.22 }, itemStyle: { color: gold }, silent: true, tooltip: { show: false } },
      { name: "冻结的中位数", type: "line", data: base.concat(path.map((p) => p.median)), showSymbol: false, lineStyle: { width: 2, color: gold, type: "dashed" }, itemStyle: { color: gold } },
      { name: "实际", type: "line", data: [100, ...path.map((p) => p.actual)], connectNulls: false, symbolSize: 8, lineStyle: { width: 2, color: t("blue") }, itemStyle: { color: t("blue"), borderColor: t("panel"), borderWidth: 2 } },
    ],
  };
}

const short = (sha) => sha.slice(0, 7);

function provenanceHtml(e) {
  const f = e.frozen;
  if (!f) return "";
  const when = f.committed_at ? f.committed_at.replace("T", " ").slice(0, 16) + " " + f.committed_at.slice(-6) : null;
  const commit = f.commit ? `<a href="${REPO_URL}/commit/${f.commit}" rel="noopener">${short(f.commit)}</a>（${when}）` : "尚未提交到仓库";
  const state = f.clean === false ? "，<b>文件在提交后被改动过</b>" : f.clean ? "，提交后未改动" : "";
  return `<div class="ledger-prov"><b>怎么核对：</b>冻结文件 <code>${esc(f.file)}</code>（${f.rows.toLocaleString("zh-CN")} 行），SHA-256 <code title="${f.sha256}">${f.sha256.slice(0, 12)}…${f.sha256.slice(-6)}</code>；公开于提交 ${commit}${state}。
    <details><summary>怎么自己验证</summary><p class="foot">下载仓库后运行 <code>shasum -a 256 ${esc(f.file)}</code>，与上面的哈希比对；再看该提交的日期。提交日期是 git 里提交者自报的时间，不是第三方时间戳；更硬的证明是 GitHub 页面上该提交的时间，以及国家统计局下一期数据的发布时间晚于它。</p></details></div>`;
}

/**
 * @param el        container
 * @param ledger    ledger.json
 * @param scorecard scorecard.json (per-origin scoring summary)
 * @param ctx       { nextRelease }
 */
export function renderLedger(el, ledger, scorecard, { nextRelease }) {
  const entries = ledger.entries.slice().reverse();
  if (!entries.length) { el.innerHTML = '<p class="dim">暂无冻结的预测。</p>'; return; }
  const regions = (e) => ["全国", ...Object.keys(e.cities).sort((a, b) => a.localeCompare(b, "zh"))];
  el.innerHTML = entries.map((e, k) => {
    const scored = (scorecard.ledger || []).find((s) => s.origin === e.origin);
    const n = e.actual.months.length;
    const status = n
      ? `已评分 <b>${n}</b> 个月（${e.actual.months[0]} → ${e.actual.months[n - 1]}）。`
      : `<b>等待评分</b>：最新数据仍是 ${scorecard.ledger.find((s) => s.origin === e.origin)?.latest_data || e.origin}，下一期（${addMonths(e.origin, 1)}）预计 ${esc(nextRelease)} 公布（估计值），公布后重新构建即自动评分。`;
    const summary = scored && scored.scored.length
      ? `<p class="foot">70 城平均误差（累计变化，百分点）：` + scored.scored.map((x) => `${x.month} <b>${x.city_mae_pct_points.toFixed(2)}</b>（不变 ${x.flat_mae_pct_points.toFixed(2)}）`).join("；") + "。</p>" : "";
    return `<div class="ledger-entry" data-origin="${e.origin}">
      <div class="hero-head"><h3>${e.origin} 起点的预测</h3><span class="sub">冻结 ${e.months.length} 个月 × 70 城 + 全国</span></div>
      <p style="margin:0 0 8px">${status}</p>
      ${provenanceHtml(e)}
      <div class="tv-bar"><div class="tv-grp"><span class="tv-lab">看哪里</span><select class="search" data-region aria-label="选择地区">${regions(e).map((r) => `<option>${esc(r)}</option>`).join("")}</select></div></div>
      <p class="foot">评分对象永远是冻结文件：即使模型在冻结之后被修订（修复回测问题等），也不改写已冻结的预测；修订后的预测只用于之后的新一期。</p>
      <div class="chart mid" data-chart role="img" aria-label="冻结的预测与实际"></div>
      <div data-table style="overflow-x:auto"></div>${summary}
    </div>`;
  }).join("");

  const draw = (box, e, region) => {
    const path = regionPath(e, region);
    mount(box.querySelector("[data-chart]"), () => ledgerOption(path));
    const verdict = (r) => ({ pending: '<span class="dim">待公布</span>', in: `<span class="verdict in">${icon("check", 14)}区间内</span>`, out: `<span class="verdict out">${icon("x", 14)}区间外</span>` }[verdictOf(r)]);
    box.querySelector("[data-table]").innerHTML = `<table class="plain"><thead><tr><th>月份</th><th>冻结的中位数</th><th>80% 区间</th><th>实际</th><th>结果</th></tr></thead><tbody>${path.map((r) =>
      `<tr><td>${r.month}（+${r.h}）</td><td class="num">${r.median.toFixed(2)}<span class="dim"> （${pct(r.median - 100, 1)}）</span></td><td class="num">${r.lo.toFixed(2)} ~ ${r.hi.toFixed(2)}</td><td class="num">${r.actual == null ? "—" : `<b>${r.actual.toFixed(2)}</b>`}</td><td>${verdict(r)}</td></tr>`).join("")}</tbody></table>`;
  };
  el.querySelectorAll(".ledger-entry").forEach((box) => {
    const e = ledger.entries.find((x) => x.origin === box.dataset.origin);
    draw(box, e, "全国");
    box.querySelector("[data-region]").addEventListener("change", (ev) => draw(box, e, ev.target.value));
  });
}
