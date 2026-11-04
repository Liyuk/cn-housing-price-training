import { boot } from "../core/boot.js";
import { createBoard } from "../domain/board.js";

boot("cities", ["board"], ({ data, vintage }) => {
  createBoard(document.querySelector("#board"), data.board);
  document.querySelector("#board-note").innerHTML =
    `温度按近 6 个月（${vintage.dataThrough} 往前）平均环比：寒 ≤ −0.30 · 凉 ≤ −0.10 · 平 ≤ +0.10 · 温 ≤ +0.30 · 热 &gt; +0.30（%/月）。` +
    `同比、环比 = 指数 − 100；距高点指该城市自 ${vintage.info("cum.json").start} 以来链式指数的最高点；12 个月预测为 ${vintage.forecast.origin} 起 +12 个月的中位数，微条为 80% 区间，金色竖线为中位数。`;
});
