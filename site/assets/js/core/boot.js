/* Boot: the one place that knows the page start-up order.
   Loads the manifest, the page's bundles and the chart library in parallel,
   mounts the shell, binds [data-vintage] labels, then hands over to the page.
   Any failure becomes one visible message instead of a half-rendered page. */

import { Data } from "./data.js";
import { createVintage } from "./vintage.js";
import { mountShell, showError } from "./shell.js";
import { ensureEcharts } from "./charts.js";

/**
 * @param pageId   id from shell.PAGES
 * @param names    bundle names this page needs up front
 * @param run      async ({ data, vintage }) => void
 * @param opts     { echarts: false } for pages with no ECharts charts
 */
export async function boot(pageId, names, run, { echarts = true } = {}) {
  let ctx;
  try {
    const [manifest, data] = await Promise.all([
      Data.load("manifest"),
      Data.loadAll(names),
      echarts ? ensureEcharts() : null,
    ]);
    const vintage = createVintage(manifest);
    mountShell(pageId, vintage);
    ctx = { data, vintage, manifest };
  } catch (e) {
    showError(e.message && e.message.startsWith("script") ? "无法加载图表库（echarts），请检查网络后刷新。" : "数据加载失败：" + (e.message || e));
    return;
  }
  ctx.vintage.bind(document);
  try {
    await run(ctx);
  } catch (e) {
    console.error(e);
    showError("页面渲染失败：" + (e.message || e));
  }
  ctx.vintage.bind(document); // labels added by run()
}
