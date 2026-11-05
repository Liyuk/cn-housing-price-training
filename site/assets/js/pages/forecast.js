import { boot } from "../core/boot.js";
import { Data } from "../core/data.js";
import { mount, whenVisible } from "../core/charts.js";
import { renderHindcast, renderLedger, renderModelTable, skillOption, coverOption } from "../domain/scorecard.js";
import { scenarioOption } from "../domain/district-charts.js";
import { addMonths } from "../core/format.js";

boot("forecast", ["scorecard"], ({ data, vintage }) => {
  const sc = data.scorecard, $ = (s) => document.querySelector(s);
  const f = vintage.forecast, wf = sc.walk_forward;

  $("#fc-origin").textContent = f.origin;
  $("#fc-end").textContent = f.end;
  $("#hindcast-title").textContent = `先做一次实战检验：${sc.hindcast.origin} 的预测 vs 之后公布的 ${sc.hindcast.months_scored} 个月`;
  renderHindcast(sc, $("#hindcast-table"), $("#hindcast-callout"));
  renderLedger(sc, $("#ledger"), vintage.nextRelease, vintage.forecast.horizon_months);
  renderModelTable(sc, $("#model-table"), $("#model-foot"), $("#n-origins"));
  mount($("#chart-skill"), () => skillOption(sc));
  mount($("#chart-cover"), () => coverOption(sc));

  const h = (n) => `${addMonths(f.origin, n)}`;
  const at = (arr, k) => Math.round(arr[wf.horizons.indexOf(k)] * 100);
  $("#zone-reliable").textContent = `+1 至 +${f.reliable_through} 个月（${h(1)} → ${h(f.reliable_through)}）`;
  $("#zone-caution").textContent = `+${f.reliable_through + 1} 至 +${f.caution_through} 个月（→ ${h(f.caution_through)}）`;
  $("#zone-scenario").textContent = `+${f.caution_through + 1} 至 +${f.horizon_months} 个月（→ ${h(f.horizon_months)}）`;
  $("#rel-h").textContent = f.reliable_through; $("#rel-cov").textContent = at(wf.coverage80, f.reliable_through);
  $("#rel-skill").textContent = at(wf.skill_vs_flat, f.reliable_through); $("#rel-dir").textContent = at(wf.direction, f.reliable_through);
  $("#cau-h").textContent = f.caution_through; $("#cau-cov").textContent = at(wf.coverage80, f.caution_through); $("#cau-skill").textContent = at(wf.skill_vs_flat, f.caution_through);
  const skillEnd = at(wf.skill_vs_flat, f.horizon_months);
  $("#sce-h").textContent = f.horizon_months; $("#sce-cov").textContent = at(wf.coverage80, f.horizon_months);
  $("#sce-skill").textContent = skillEnd >= 0 ? `比“不变”准 ${skillEnd}%` : `比“不变”还差 ${Math.abs(skillEnd)}%`;

  whenVisible($("#scen-card"), async () => {
    const d = await Data.load("district_scenarios");
    const seg = $("#district-seg");
    let city = "北京";
    mount($("#chart-district"), () => scenarioOption(d[city]));
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-v]");
      if (!b) return;
      seg.querySelectorAll("button").forEach((x) => x.setAttribute("aria-pressed", String(x === b)));
      city = b.dataset.v;
      mount($("#chart-district"), () => scenarioOption(d[city]));
    });
  });
}, { echarts: true });
