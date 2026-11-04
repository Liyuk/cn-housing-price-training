# 趋势看板（多页面静态站）

GitHub Pages 静态站：70 城二手住宅价格趋势、概率预测与回测成绩。架构与模块设计见 [`docs/site-architecture.md`](../docs/site-architecture.md)。

## 页面

`index.html` 总览 · `cities.html` 城市榜 · `city.html?c=上海` 城市页 · `stats.html` 数据统计 · `forecast.html` 预测逻辑 · `data.html` 数据与方法 · `papers.html` 论文

## 目录

```
assets/styles.css        设计令牌与样式（颜色只在这里定义；图表渲染时读取）
assets/js/core/          data（带缓存的 JSON 加载）· vintage（所有时间标注）· format · theme · charts · loader · shell · boot
assets/js/domain/        trend-chart（纯函数）· candles（合成 K 线）· trend-view（折线/K 线切换）· board · scorecard · market-charts · district-charts
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
python -m unittest discover -s tests      # Python，含 tests/test_site_contract.py（页面引用的数据块都已构建并在 manifest 中）
node --test tests/js/*.test.mjs           # 纯函数模块：format / data / vintage / candles / trend-chart / board
```

## 设计要点

- 温度（寒/凉/平/温/热）同时是发散色板：蓝 = 下跌，橙红 = 上涨，灰 = 持平；颜色从不单独承载信息，始终带文字标签。K 线同样红涨蓝跌。
- 金色 = 研究对象，蓝色 = 对照，橙色 = 提示。三色经 dataviz 校验器验证（深/浅两套）。
- **时间标注**：页面不写死日期，全部来自 manifest；月份 `YYYY-MM`，区间 `起 → 止`，预测同时写相对与绝对（`+12 个月（2027-09）`）；口径断点用竖线标出。
- **K 线**：Lightweight Charts v4.2.3（Apache-2.0，按需懒加载，页脚署名）。价格指数没有日内高低点，K 线由月度链式指数合成——月线只有实体，季线、年线才有影线。折线图仍是默认。
- 预测可信度分区（可作预测 / 谨慎参考 / 仅作情景）由回测**计算**并写入 manifest（`scripts/site_extras.py::forecast_zones`），图、表、文案都读它，不手写数字。

## 部署

推送到 `main` 且 `site/**` 有变化时，`.github/workflows/deploy-demo.yml` 会自动把 `site/` 部署到 GitHub Pages。站点根路径为 `/cn-housing-price-training/`，因此所有资源都使用相对路径。
