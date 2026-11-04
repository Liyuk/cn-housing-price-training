/* Script loader with CDN fallbacks.  Kept separate from charts.js so modules that
   only need to load a library do not pull in theme/DOM wiring at import time. */

const scripts = new Map();

export function loadScript(urls) {
  const key = urls[0];
  if (!scripts.has(key)) {
    scripts.set(key, new Promise((resolve, reject) => {
      const [first, ...rest] = urls;
      const s = document.createElement("script");
      s.src = first;
      s.onload = resolve;
      s.onerror = () => (rest.length ? loadScript(rest).then(resolve, reject) : reject(new Error("script: " + key)));
      document.head.appendChild(s);
    }));
  }
  return scripts.get(key);
}
