import test from "node:test";
import assert from "node:assert/strict";
import { regionPath, verdictOf } from "../../site/assets/js/domain/ledger-model.js";

const months = Array.from({ length: 24 }, (_, i) => `2026-${String(i + 10).padStart(2, "0")}`.replace(/^2026-(1[3-9]|2\d)$/, (m, k) => `2027-${String(+k - 12).padStart(2, "0")}`));
const frozen = (c) => ({ q100: months.map((_, i) => c - 1 - i * 0.1), q500: months.map((_, i) => c - i * 0.05), q900: months.map((_, i) => c + 1 + i * 0.1) });
const entry = (actualNat, actualCity) => ({
  origin: "2026-09", months, national: frozen(100), cities: { 北京: frozen(100) },
  actual: { months: months.slice(0, actualNat.length), national: actualNat, cities: { 北京: actualCity } },
});

test("a path holds the frozen values and null for months not yet published", () => {
  const p = regionPath(entry([99.8], [99.9]), "全国");
  assert.equal(p.length, 12);
  assert.deepEqual([p[0].h, p[0].month], [1, "2026-10"]);
  assert.equal(p[0].actual, 99.8);
  assert.equal(p[1].actual, null);
  assert.equal(regionPath(entry([], []), "北京")[0].actual, null);
});

test("verdict: in / out of the frozen 80% band, pending until published", () => {
  const p = regionPath(entry([99.8, 90], []), "全国");
  assert.equal(verdictOf(p[0]), "in");
  assert.equal(verdictOf(p[1]), "out");
  assert.equal(verdictOf(p[2]), "pending");
});
