# 趋势看板（多页面静态站）

GitHub Pages 静态站：70 城二手住宅价格趋势、概率预测与回测成绩。架构与模块设计见 [`docs/site-architecture.md`](../docs/site-architecture.md)。

## 页面

`index.html` 总览 · `cities.html` 城市榜 · `city.html?c=上海` 城市页 · `stats.html` 数据统计 · `forecast.html` 预测逻辑 · `data.html` 数据与方法 · `papers.html` 论文

## 目录

```
assets/styles.css        设计令牌与样式（shadcn zinc + 数据色；颜色只在这里定义，图表渲染时读取）
assets/fonts/            Geist（OFL）
assets/js/core/          data（带缓存的 JSON 加载）· vintage（所有时间标注）· format · theme · icons（Lucide）· charts · loader · shell · boot
assets/js/domain/        trend-chart（纯函数）· candles（合成 K 线）· trend-view（折线/K 线切换）· board · scorecard · definitions · market-charts · district-charts
assets/js/pages/         每页一个薄脚本，只做接线
data/                    scripts/build_demo_data.py 生成的 JSON；manifest.json 是页面与构建之间的接缝
data/districts/<城市>.json  各城市区县价格/租金/收益率（只有采集过的城市）
downloads/               指数面板、预测分位数、榜单快照
```

## 本地预览

```bash
python3 -m http.server 8080 --directory site
# 访问 http://localhost:8080
```

必须用 HTTP 服务器（ES 模块与 `fetch` 都不支持 `file://`）。

## 重新生成数据

完整的每月流程是 `bash scripts/monthly_update.sh`；只重生成站点 JSON：

```bash
.venv/bin/python scripts/build_demo_data.py
```

## 测试

```bash
python -m unittest discover -s tests      # Python，含 test_site_contract（数据块都在 manifest 中）与 test_design_check（设计规范）
node --test tests/js/*.test.mjs           # 纯函数模块：format / data / vintage / candles / trend-chart / board
```

## 设计系统

底座是 **shadcn/ui 的 zinc 主题**（token 与组件规格取自 `ui.shadcn.com/r/themes.css` 和组件注册表：button h-9、badge、tabs/toggle-group 分段控件、input、table、card、alert），再按 **Impeccable 的 Operate 规则**落地：

- **界面单色，颜色只表示数据。** 主色就是前景色（shadcn neutral 的做法）；金色 = 研究对象，蓝色 = 对照，橙色 = 提示，三色经 dataviz 校验器验证（深/浅两套，色盲分离 ΔE ≥ 22，对比度 ≥ 3:1）。温度 寒/凉/平/温/热 是蓝↔橙红的发散色板，始终带文字，K 线同样红涨蓝跌。需要正文级对比度的地方（涨跌文字、金色文字）用更深的色阶，见 `styles.css` 里的 `--up / --down / --gold-text`。
- **一个字体族**：Geist（自托管，OFL），中文回退系统字体；固定 rem 字号，标题 28/20/15，正文 14；没有展示字体。
- **只用边框做层级**（卡片不加阴影），没有侧边竖条、没有玻璃拟态、没有入场动画；动效只用于状态（150ms 的悬停/聚焦），加载用骨架。
- **图标**：Lucide（ISC），统一 2px 描边，由 `core/icons.js` 提供；不用字符冒充图标。
- **主题跟随系统**，可手动切换并记住；浏览器默认元素（选中色、光标、勾选框、滚动条、焦点环）都用色板主题化。
- **不用弹窗**：口径说明是数据页的章节（`data.html#definitions`），导航在手机上保留（横向滑动）。
- 关键数字用表格而不是大数字卡片，首页入口用链接列表而不是等大卡片。

这些约束由 `scripts/design_check.py` 自动检查（对比度从 `styles.css` 的 token 实算，加 10 项禁用模式扫描），`tests/test_design_check.py` 用故意写坏的样本确认检查真的会失败。

## 其他约定

- **时间标注**：页面不写死日期，全部来自 manifest；月份 `YYYY-MM`，区间 `起 → 止`，预测同时写相对与绝对（`+12 个月（2027-09）`）；口径断点用竖线标出。
- **K 线**：Lightweight Charts v4.2.3（Apache-2.0，按需懒加载，页脚署名）。价格指数没有日内高低点，K 线由月度链式指数合成——月线只有实体，季线、年线才有影线。折线图仍是默认。
- 预测可信度分区（可作预测 / 谨慎参考 / 仅作情景）由回测**计算**并写入 manifest（`scripts/site_extras.py::forecast_zones`），图、表、文案都读它，不手写数字。

## 部署

推送到 `main` 且 `site/**` 有变化时，`.github/workflows/deploy-demo.yml` 会自动把 `site/` 部署到 GitHub Pages。站点根路径为 `/cn-housing-price-training/`，因此所有资源都使用相对路径。
