/* Theme and design tokens.  styles.css is the single source of colour; charts read tokens
   through tok() at render time.  The theme follows the system until the visitor picks one. */

import { icon } from "./icons.js";

const listeners = new Set();
const narrowListeners = new Set();
let wasNarrow = typeof window !== "undefined" && window.innerWidth < 640;

export const tok = (name) => getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim();
export const isNarrow = () => window.innerWidth < 640;
export const onThemeChange = (fn) => listeners.add(fn);
export const onBreakpointChange = (fn) => narrowListeners.add(fn);

const stored = () => { try { return localStorage.getItem("theme"); } catch (e) { return null; } };
const system = () => (window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
const current = () => document.documentElement.dataset.theme || system();

function apply(theme, button) {
  document.documentElement.dataset.theme = theme;
  if (button) {
    button.innerHTML = icon(theme === "dark" ? "sun" : "moon", 16);
    button.setAttribute("aria-label", theme === "dark" ? "切换到浅色主题" : "切换到深色主题");
    button.title = theme === "dark" ? "浅色" : "深色";
  }
  listeners.forEach((fn) => fn(theme));
}

export function initTheme(button) {
  apply(current(), button);
  button.addEventListener("click", () => {
    const next = current() === "dark" ? "light" : "dark";
    try { localStorage.setItem("theme", next); } catch (e) { /* private mode */ }
    apply(next, button);
  });
  // follow the operating system until the visitor has chosen
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => { if (!stored()) apply(system(), button); });
}

window.addEventListener("resize", () => {
  const narrow = isNarrow();
  if (narrow !== wasNarrow) { wasNarrow = narrow; narrowListeners.forEach((fn) => fn(narrow)); }
});
