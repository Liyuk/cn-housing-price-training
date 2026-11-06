# 站点架构（多页面）

> 按 codebase-design 的词汇设计：**深模块**（小接口、大实现）、**接缝**（可在不改调用方的前提下替换行为的位置）、**删除测试**（删掉模块后复杂度是消失，还是散落到 N 个调用方）。
> 站点是纯静态：无构建步骤，浏览器原生 ES 模块，数据是预生成的 JSON。

## 页面与内容归属

每个事实只在一个页面里出现，其他页面用链接指向它。

| 页面 | 回答的问题 | 内容 |
|---|---|---|
| `index.html` 总览 | 现在是什么状况？ | 一句结论、全国走势大图（折线/K 线、指标、时间范围、预测期限、对照新房）、4 个数字、各页入口 |
| `cities.html` 城市榜 | 我的城市在哪个位置？ | 70 城榜单：温度、趋势强度、同比环比、走势、12 个月预测与概率；筛选/排序/搜索 |
| `city.html?c=上海` 城市页 | 这个城市的全部信息 | 走势（折线/K 线，对照全国）、阶段信息、36 个月预测区间与数据表、**区县搜索**（价格/租金/租金收益率，仅有数据的城市）、小区说明 |
| `compare.html` 对比 | 谁涨得多、谁跌得多？ | 2–5 个地区（城市/全国/层级，二手或新房）叠加；指数（统一基期）/ 同比 / 距高点；自定义时间范围与区间统计；链接保留选择 |
| `stats.html` 数据统计 | 发生了什么？ | 层级走势、上涨城市数、同比热力图、新房 vs 二手、宏观与 LPR、租金收益率、北京官方网签；**一个共用时间范围控制所有按月的图** |
| `forecast.html` 预测逻辑 | 怎么预测、靠不靠谱？ | 模型与组合规则、区间怎么来、实战回放、回测优势与覆盖率、各模型误差、**预测账本（冻结文件的哈希与提交、冻结的预测 vs 实际、逐城查看）**、v0.2 区县情景 |
| `data.html` 数据与方法 | 数据怎么来的？ | 来源分级、口径、覆盖矩阵与缺口、对账结果、更新流程、更新记录、下载 |
| `papers.html` 论文 | 论文说了什么？ | 两篇论文摘要与版本、与网站数字的对应、待修订项 |

城市页替代了原来的详情抽屉（删除测试：抽屉与城市页做同一件事，保留页面，抽屉的焦点陷阱、hash 同步等复杂度整体消失）。

## 深模块清单

```
assets/js/core/
  data.js       Data.load(name…)           缓存、重复请求合并、统一报错；fetch 可注入（真实 / 测试替身 = 两个适配器，接缝成立）
  vintage.js    Vintage.describe(name)     所有"数据截至 / 起止 / 频率 / 期数"文字的唯一来源（读 manifest.json）
  format.js     纯函数：pct sgn ym range horizon esc probText
  theme.js      主题与设计令牌 tok(name)；onChange 回调
  charts.js     ECharts 生命周期：加载、挂载、主题/断点变化时重建、懒加载
  shell.js      页眉/导航/页脚/口径弹层，只由页面名驱动
  urlstate.js   页面状态 ⇄ 查询字符串：parseState / serializeState 是纯函数，createUrlSync 是唯一碰 location 的地方；默认值不写进链接，未知参数（?c=上海）原样保留
  timewindow.js 时间窗口对象：预设（近 N 年）或自定义起止月；各图用自己的月份序列 resolve，所以起点更晚/终点更早的序列被截断而不是错位；windowFromUrl 把窗口放进链接（?r=5 / ?r=custom&f=&t=）
  windowbar.js  时间窗口的控件（范围预设 + 起止月），趋势视图、对比页、数据统计页共用
assets/js/domain/
  trend-chart.js   纯函数 buildTrendOption(data, region, opts, theme) → ECharts option；fanTable()
  candles.js       纯函数 aggregateOhlc(months, values, period)；Lightweight Charts 的懒加载与渲染
  trend-view.js    createTrendView(el, opts) — 折线/K 线、指标（指数/同比/距高点）、时间窗口（自有或共用）、预测期限（不显示/+12/+24/+60）、对照（全国/新房）、折线图拖选区间、区间统计；状态可进链接；隐藏两套图表库的差异
  series.js        纯函数：yoy / drawdown / rebase / metricValues / windowStats（累计涨跌、年化、最大回撤、距高点、上涨月占比、是否跨口径断点）
  window-stats.js  纯函数：区间统计表（每页同一套列），跨断点与新房推算月份的提示
  compare-chart.js 纯函数：buildCompareOption（统一基期、同比、回撤）、assignColors（线被移除时其他线不换色）、presets
  ledger-model.js  纯函数：冻结路径与实际的对齐、区间内/外/待公布
  ledger.js        账本视图：冻结文件的哈希与提交、冻结预测 vs 实际的图与逐月表
  board.js         纯函数 filterSort(rows, state)；createBoard(root, rows)
  scorecard.js     实战回放 / 账本 / 模型误差表 / 技能与覆盖图
assets/js/pages/   index.js cities.js city.js compare.js stats.js forecast.js data.js papers.js   ← 薄：只接线
```

**接口即测试面。** `format / vintage / candles.aggregateOhlc / board.filterSort / trend-chart.buildTrendOption / data.load` 全是可在 node 里直接测试的纯函数或带注入的模块，`tests/js/*.test.mjs`。

**接缝与适配器**
- `Data` 的接缝在 `fetch`：浏览器适配器 + 内存适配器（测试）。
- `TrendView` 的接缝在"渲染后端"：ECharts（折线）与 Lightweight Charts（K 线）两个适配器，页面不知道后端是谁。
- Python 侧：`scripts/build_demo_data.py` ↔ 站点之间的接缝是 `data/manifest.json`；`tests/test_site_contract.py` 检查页面里 `Data.load('x')` 引用的每个包都在 manifest 里。

## 状态进链接

| 参数 | 含义 | 出现在 |
|---|---|---|
| `m` `x` `p` `fc` `cmp` `g` | 图表类型（line/candle）· 指标（level/yoy/dd）· K 线周期（M/Q/Y）· 预测期限（0/12/24/60）· 对照（nat,new）· 范围（数据统计页的层级） | 总览、城市页、数据统计页的趋势图 |
| `r` `f` `t` | 时间范围（all/20/10/5/3/custom）与自定义起止月 | 同上；数据统计页由所有图共用；对比页 |
| `s` `k` `b` | 对比的地区（逗号分隔，最多 5 个）· 市场（secondhand/new）· 基期月 | 对比页 |

无效值回落到默认；等于默认的不写进链接。

**预测只在“指数”口径下显示**：同比与回撤需要把预测路径接到历史上，区间的分位数不能直接换算，所以这两个口径不画预测，预测期限控件随之隐藏；K 线也只用于指数水平。

## 时间标注规则（全站一致）

1. **页面里不写死日期。** 起止、截至、期数全部来自 `manifest.json`，由 `Vintage` 输出。
2. 月份一律 `YYYY-MM`；区间 `起 → 止`；时长"N 个月"；预测期限写成 `+12 个月（2027-09）`，同时给相对和绝对。
3. 每个卡片标出自己的数据截至时间——各来源的最新月份不同（70 城 2026-09，LPR 2026-10，宏观 1–9 月累计，北京挂牌/租金按采集结果）。
4. 周期与口径随数据标注：月度 / 累计（年初至当月）/ 快照；链式指数写明基期（`2005-12 = 100`）。
5. 历史从 **2008-01** 起（`src/panel.py::CONSISTENT_FROM`）：更早的环比与同比不自洽，保留在下载文件并标记 `low_consistency`；2011-02 前为旧口径，图上以竖线标出口径断点。
6. 下一期预计发布日：按国家统计局历史规律给出估计（每月 15–17 日），明确写"预计"。

## 数据层级与可得性（诚实边界）

| 层级 | 状态 |
|---|---|
| 城市 · 月度指数 | 2006-01 → 最新；站内 2008-01 起（2006–2010 来自第三方镜像，2011 起官方页面直抓并与镜像逐格对照；2006–2007 未通过自洽检验） |
| 城市 · 销量 | 国家统计局无城市级月度销量；仅全国累计 |
| 区县 · 月度价格/租金/收益率 | creprice 月报，每页仅前 10 名区，第三方口径；首批 12 个大城市 |
| 区县 · 成交量 | 仅北京网签（快照/年度） |
| 小区/楼盘 | 无合规的批量来源，**不做**（城市页明确说明，不放空壳） |

## 设计系统（2026-11-05 重做）

| 层 | 内容 |
|---|---|
| 底座 | shadcn/ui zinc 主题的 token 与组件规格（`site/assets/styles.css` 顶部注释写明来源） |
| 规则 | Impeccable 的 Operate 模式：界面单色、颜色只表示数据、一个字体族、固定字号、边框做层级、无装饰动效、不用弹窗 |
| 数据色 | 金（研究对象）/ 蓝（对照）/ 橙（提示），经 dataviz 校验器在 `#09090b` 与 `#ffffff` 上验证；温度色阶是蓝↔橙红发散色，始终带文字 |
| 图标 | Lucide，`core/icons.js` |
| 自动检查 | `scripts/design_check.py`（对比度实算 + 10 项禁用模式），`tests/test_design_check.py` 含“坏样本必须被抓住”的负面测试 |

删除测试的结果：`口径说明` 弹窗与数据页的"口径要点"重复，已删弹窗，内容并入 `data.html#definitions`，由 `domain/definitions.js` 渲染（日期来自 manifest）；shell 因此不再包含任何页面内容，只负责页眉导航与页脚。
