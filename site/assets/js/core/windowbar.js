/* WindowBar: the controls of a TimeWindow (range presets + custom from/to months).
   One implementation for the trend view, the comparison page and the stats page. */

import { RANGES } from "./timewindow.js";

/** Renders into `el`; `months` are the months the displayed from/to are resolved against. */
export function mountWindowBar(el, win, { months, label = "时间" }) {
  const { first, last } = win.bounds;
  el.innerHTML = `<span class="tv-lab">${label}</span>
    <div class="seg" data-g="range" role="group" aria-label="时间范围">${RANGES.map(([v, l]) => `<button type="button" data-v="${v}">${l}</button>`).join("")}</div>
    <span class="tv-custom" role="group" aria-label="自定义起止月"><input type="month" data-g="from" aria-label="起始月" min="${first}" max="${last}" /><span class="dim">至</span><input type="month" data-g="to" aria-label="截止月" min="${first}" max="${last}" /></span>`;
  const from = el.querySelector('input[data-g="from"]'), to = el.querySelector('input[data-g="to"]'), custom = el.querySelector(".tv-custom");
  function paint() {
    const w = win.resolve(months);
    el.querySelectorAll(".seg button").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.v === win.state.range)));
    from.value = w.from; to.value = w.to;
    custom.classList.toggle("on", win.state.range === "custom");
  }
  el.addEventListener("click", (e) => { const b = e.target.closest(".seg button"); if (b) win.set({ range: b.dataset.v }); });
  el.addEventListener("change", (e) => {
    if (!e.target.matches("input[type=month]")) return;
    const w = win.resolve(months);
    win.set({ range: "custom", from: from.value || w.from, to: to.value || w.to });
  });
  win.subscribe(paint);
  paint();
}
