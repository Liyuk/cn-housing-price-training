/* Icons: lucide (ISC license, https://lucide.dev), generated from lucide-static by the design pass.
   One stroke weight (2), 24px grid, currentColor -- the same set shadcn/ui uses.  icon(name, size) -> SVG string. */

const PATHS = {
  "check": '<path d="M20 6 9 17l-5-5" />',
  "x": '<path d="M18 6 6 18" /> <path d="m6 6 12 12" />',
  "arrow-left": '<path d="m12 19-7-7 7-7" /> <path d="M19 12H5" />',
  "chevron-right": '<path d="m9 18 6-6-6-6" />',
  "chevron-down": '<path d="m6 9 6 6 6-6" />',
  "sun": '<circle cx="12" cy="12" r="4" /> <path d="M12 2v2" /> <path d="M12 20v2" /> <path d="m4.93 4.93 1.41 1.41" /> <path d="m17.66 17.66 1.41 1.41" /> <path d="M2 12h2" /> <path d="M20 12h2" /> <path d="m6.34 17.66-1.41 1.41" /> <path d="m19.07 4.93-1.41 1.41" />',
  "moon": '<path d="M20.985 12.486a9 9 0 1 1-9.473-9.472c.405-.022.617.46.402.803a6 6 0 0 0 8.268 8.268c.344-.215.825-.004.803.401" />',
  "download": '<path d="M12 15V3" /> <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" /> <path d="m7 10 5 5 5-5" />',
  "external-link": '<path d="M15 3h6v6" /> <path d="M10 14 21 3" /> <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />',
  "info": '<circle cx="12" cy="12" r="10" /> <path d="M12 16v-4" /> <path d="M12 8h.01" />',
  "search": '<path d="m21 21-4.34-4.34" /> <circle cx="11" cy="11" r="8" />',
  "trending-down": '<path d="M16 17h6v-6" /> <path d="m22 17-8.5-8.5-5 5L2 7" />',
  "menu": '<path d="M4 5h16" /> <path d="M4 12h16" /> <path d="M4 19h16" />',
  "circle-alert": '<circle cx="12" cy="12" r="10" /> <line x1="12" x2="12" y1="8" y2="12" /> <line x1="12" x2="12.01" y1="16" y2="16" />',
};

export function icon(name, size = 16, label = "") {
  const body = PATHS[name];
  if (!body) throw new Error("unknown icon: " + name);
  const a11y = label ? `role="img" aria-label="${label}"` : 'aria-hidden="true"';
  return `<svg class="icon" ${a11y} width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${body}</svg>`;
}
