/* Data: cached JSON loading with one failure mode.
   The seam is `fetch`: the browser adapter is the default; tests pass an
   in-memory one.  Concurrent loads of the same bundle share one request. */

export class DataError extends Error {
  constructor(name, status, cause) {
    super(status ? `${name}: HTTP ${status}` : `${name}: ${cause || "network error"}`);
    this.name = "DataError";
    this.bundle = name;
    this.status = status;
  }
}

export function createData({ fetchImpl = (...a) => fetch(...a), root = "data" } = {}) {
  const pending = new Map();

  function load(name) {
    if (!pending.has(name)) {
      const p = Promise.resolve()
        .then(() => fetchImpl(`${root}/${name}.json`))
        .catch((e) => { throw new DataError(name, 0, e && e.message); })
        .then((resp) => {
          if (!resp.ok) throw new DataError(name, resp.status);
          return resp.json();
        });
      pending.set(name, p);
      p.catch(() => pending.delete(name)); // a failed load may be retried
    }
    return pending.get(name);
  }

  return {
    load,
    /** Load several bundles; resolves to an object keyed by name. */
    async loadAll(names) {
      const out = await Promise.all(names.map(load));
      return Object.fromEntries(names.map((n, i) => [n, out[i]]));
    },
    /** Like load, but resolves to null when the bundle does not exist (404). */
    async tryLoad(name) {
      try { return await load(name); } catch (e) { if (e.status === 404) return null; throw e; }
    },
  };
}

export const Data = createData();
