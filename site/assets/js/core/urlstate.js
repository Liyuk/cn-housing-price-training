/* UrlState: chart and page state <-> the query string, so a link reproduces the view.
   parse/serialise are pure; `createUrlSync` is the only part that touches location/history.
   Parameters the schema does not know (the city page's ?c=…) are carried through untouched,
   and values equal to their default are left out so links stay short. */

export const oneOf = (values, def) => ({ def, parse: (raw) => (values.includes(raw) ? raw : undefined), format: String });
export const month = (def = null) => ({ def, parse: (raw) => (/^\d{4}-(0[1-9]|1[0-2])$/.test(raw) ? raw : undefined), format: String });
export const flag = (def = false) => ({ def, parse: (raw) => (raw === "1" ? true : raw === "0" ? false : undefined), format: (v) => (v ? "1" : "0") });
export const list = (def = [], { valid = () => true, max = Infinity } = {}) => ({
  def,
  parse: (raw) => { const items = raw.split(",").filter((x) => x && valid(x)); return items.length ? [...new Set(items)].slice(0, max) : undefined; },
  format: (v) => v.join(","),
});

const same = (a, b) => (Array.isArray(a) || Array.isArray(b) ? JSON.stringify(a) === JSON.stringify(b) : a === b);

/** Every key of the schema, from the query string where valid, else its default. */
export function parseState(search, schema) {
  const params = new URLSearchParams(search);
  const out = {};
  for (const [key, spec] of Object.entries(schema)) {
    const raw = params.get(key);
    const value = raw == null ? undefined : spec.parse(raw);
    out[key] = value === undefined ? spec.def : value;
  }
  return out;
}

/** A query string ("?a=1" or "") holding the non-default keys of `state` plus the foreign params already in `search`. */
export function serializeState(state, schema, search = "") {
  const params = new URLSearchParams(search);
  for (const [key, spec] of Object.entries(schema)) {
    const value = state[key];
    if (value === undefined || value === null || same(value, spec.def)) params.delete(key);
    else params.set(key, spec.format(value));
  }
  const text = params.toString();
  return text ? "?" + text : "";
}

/** Browser adapter.  `win` is injectable so tests can pass a fake window. */
export function createUrlSync(schema, win = window) {
  return {
    read: () => parseState(win.location.search, schema),
    write(state) {
      const next = serializeState(state, schema, win.location.search);
      if (next !== win.location.search) win.history.replaceState(null, "", win.location.pathname + next + win.location.hash);
    },
  };
}
