/* 口径说明: what every number on the site means.  Rendered into the data page (it used to be a modal
   that duplicated the data page; the header now links here).  Dates come from the manifest. */

import { addMonths } from "../core/format.js";

export function renderDefinitions(el, v) {
  const base = v.info("cum.json").basis.split(" ")[0];
  const f = v.forecast;
  el.innerHTML = `
    <dl class="defs">
      <div><dt>价格指数 ≠ 房价</dt>
        <dd>城市级数据是<b>价格指数</b>：环比 = 上月 100，同比 = 上年同月 100。指数低于 100 表示下跌，不能把“指数跌 10%”读成“每平方米房价跌 10 个百分点”。图中“${base} = 100”的曲线，是把每月环比连乘得到的链式指数。</dd></div>
      <div><dt>全国线是 70 城的等权平均</dt>
        <dd>全国线 = 70 座城市环比指数的简单平均再连乘，不是官方的全国房价指数，也没有按城市规模加权。一线、二线、三线同理（4 / 31 / 35 座城市）。</dd></div>
      <div><dt>口径断点与起点</dt>
        <dd>${v.regimeBreak.month} 以前是旧口径（第三方镜像，与官方页面在可对照的月份逐格一致），${v.regimeBreak.month} 起是现行口径（直接抓取官方页面）。图上用竖线标出，<b>不要把跨过断点的涨跌幅当作同一口径</b>。站内图表从 ${v.manifest.history_start} 起：更早的环比与同比不自洽，保留在下载文件里并标记 <code>low_consistency</code>。预测模型只用断点之后的数据。</dd></div>
      <div><dt>温度与趋势强度</dt>
        <dd>温度按近 6 个月平均环比（%/月）划分：寒 ≤ −0.30，凉 −0.30 ~ −0.10，平 −0.10 ~ +0.10，温 +0.10 ~ +0.30，热 &gt; +0.30。趋势强度是近 3 个月平均环比在 70 城中的百分位。<code>回暖</code>：近 3 个月均值比近 12 个月均值高 0.15 个百分点以上，且最新一月环比不为负。</dd></div>
      <div><dt>K 线是怎么来的</dt>
        <dd>价格指数每月只有一个收盘值，没有日内高低点。K 线由月度链式指数<b>合成</b>：开盘 = 上一期收盘，收盘 = 本期最后一个月，最高/最低 = 本期内各月收盘的极值。月线只有实体、没有影线；季线、年线才有影线。它是同一份数据的另一种看法，没有额外信息。红涨蓝跌，与温度色一致。</dd></div>
      <div><dt>时间标注</dt>
        <dd>月份写作 YYYY-MM。每张图和每个数据块标注自己的“数据截至”和起止范围，因为各来源的最新月份不同：70 城指数截至 ${v.dataThrough}，LPR 截至 ${v.asof("lpr.json")}，宏观为 ${v.asof("macro.json")} 年初累计。预测期限同时写相对和绝对，如“+12 个月（${addMonths(f.origin, 12)}）”。</dd></div>
      <div><dt>预测的性质</dt>
        <dd>预测只用价格自身的历史（加一个跨城市的基础模型），不含政策、利率等外生变量。可信度分为三档，由回测计算：+1 至 +${f.reliable_through} 个月<b>可作预测</b>，至 +${f.caution_through} 个月<b>谨慎参考</b>，其后<b>仅作情景</b>——具体数字见<a href="forecast.html">预测逻辑</a>页。概率只代表模型自己的不确定性，不是对政策转向的判断。</dd></div>
      <div><dt>区级与小区级数据</dt>
        <dd>区县价格、租金来自<b>第三方月报</b>（每页只列前 10 名区），不是成交价；官方区级数据只有北京网签套数/面积。小区、楼盘级数据没有合规的批量来源，本站不提供。</dd></div>
    </dl>`;
}
