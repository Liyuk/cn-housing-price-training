/* Theme and design tokens.  styles.css is the single source of colour; charts
   read tokens through tok() at render time. */

const listeners = new Set();
const narrowListeners = new Set();
let wasNarrow = typeof window !== "undefined" && window.innerWidth < 640;

export const tok = (name) => getComputedStyle(document.documentElement).getPropertyValue("--" + name).trim();
export const isNarrow = () => window.innerWidth < 640;
export const onThemeChange = (fn) => listeners.add(fn);
export const onBreakpointChange = (fn) => narrowListeners.add(fn);

export function initTheme(button) {
  const sync = () => (button.textContent = document.documentElement.dataset.theme === "dark" ? "浅色" : "深色");
  sync();
  button.addEventListener("click", () => {
    const next = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
    document.documentElement.dataset.theme = next;
    try { localStorage.setItem("theme", next); } catch (e) { /* private mode */ }
    sync();
    listeners.forEach((fn) => fn(next));
  });
}

window.addEventListener("resize", () => {
  const narrow = isNarrow();
  if (narrow !== wasNarrow) { wasNarrow = narrow; narrowListeners.forEach((fn) => fn(narrow)); }
});
