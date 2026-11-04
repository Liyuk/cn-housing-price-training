import test from "node:test";
import assert from "node:assert/strict";
import { sgn, pct, cls, addMonths, monthsBetween, range, horizon, probText, esc } from "../../site/assets/js/core/format.js";

test("a value that rounds to zero carries no sign", () => {
  assert.equal(sgn(0.04), "0.0");
  assert.equal(sgn(-0.04), "0.0");
  assert.equal(sgn(0.06), "+0.1");
  assert.equal(sgn(-2.25, 1), "−2.3");
  assert.equal(pct(-3.22), "−3.2%");
});
test("cls treats near-zero as flat", () => {
  assert.equal(cls(0.01), "flatc");
  assert.equal(cls(0.5), "up");
  assert.equal(cls(-0.5), "down");
});
test("addMonths crosses year boundaries both ways", () => {
  assert.equal(addMonths("2026-09", 12), "2027-09");
  assert.equal(addMonths("2026-11", 3), "2027-02");
  assert.equal(addMonths("2026-01", -1), "2025-12");
  assert.equal(addMonths("2026-09", -61), "2021-08");
});
test("monthsBetween is signed", () => {
  assert.equal(monthsBetween("2026-06", "2026-09"), 3);
  assert.equal(monthsBetween("2026-09", "2025-09"), -12);
});
test("time labels: span and horizon give relative and absolute together", () => {
  assert.equal(range("2006-01", "2026-09"), "2006-01 → 2026-09");
  assert.equal(range("2025-10", "2025-10"), "2025-10");
  assert.equal(horizon(12, "2026-09"), "+12 个月（2027-09）");
});
test("probability text clips the tails the data cannot resolve", () => {
  assert.equal(probText(0.004), "≤1%");
  assert.equal(probText(0.999), "≥99%");
  assert.equal(probText(0.564), "56%");
  assert.equal(probText(null), "—");
});
test("esc neutralises markup", () => assert.equal(esc('<a href="x">&'), "&lt;a href=&quot;x&quot;&gt;&amp;"));
