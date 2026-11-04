import test from "node:test";
import assert from "node:assert/strict";
import { filterSort } from "../../site/assets/js/domain/board.js";

const rows = [
  { city: "北京", tier: 1, temp: "平", strength: 91, yoy: 97.5, turning: true, f12: 0.1, p_up12: 0.38 },
  { city: "上海", tier: 1, temp: "热", strength: 100, yoy: 100.8, turning: true, f12: 2.7, p_up12: 0.56 },
  { city: "唐山", tier: 3, temp: "寒", strength: 5, yoy: 94.0, turning: false, f12: -5.4, p_up12: 0.01 },
  { city: "成都", tier: 2, temp: "凉", strength: 60, yoy: 96, turning: false, f12: -2.0, p_up12: null },
];
const names = (r) => r.map((x) => x.city);

test("default order is strongest first", () => assert.deepEqual(names(filterSort(rows)), ["上海", "北京", "成都", "唐山"]));
test("ascending flips the order", () => assert.deepEqual(names(filterSort(rows, { key: "yoy", dir: 1 })), ["唐山", "成都", "北京", "上海"]));
test("null values sort last when descending", () => assert.equal(names(filterSort(rows, { key: "p_up12", dir: -1 })).at(-1), "成都"));   // 成都 has no probability
test("temperature chips combine as OR", () => assert.deepEqual(names(filterSort(rows, { temps: new Set(["寒", "热"]) })).sort(), ["上海", "唐山"].sort()));
test("tier, search and turning filters combine as AND", () => {
  assert.deepEqual(names(filterSort(rows, { tier: 1, turning: true, q: "京" })), ["北京"]);
  assert.deepEqual(names(filterSort(rows, { tier: 3, turning: true })), []);
});
test("city sort uses Chinese collation and does not mutate the input", () => {
  const copy = rows.slice();
  filterSort(rows, { key: "city", dir: 1 });
  assert.deepEqual(rows, copy);
});
