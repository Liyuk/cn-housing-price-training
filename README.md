# 中国 70 城住宅价格指数机器学习项目

这是一个可重复运行的基线项目：从国家统计局公开月报采集 70 个大中城市的新建住宅和二手住宅价格指数，整理为训练数据，并用随机森林预测二手住宅同比指数。

## 数据口径

- 数据源：国家统计局“70 个大中城市商品住宅销售价格变动情况”官方月报。
- 默认采集范围：2008-01 至最新可用月份。采集器会先抓取国家统计局“数据发布”目录，自动发现月报链接，因此不需要手工维护 URL。
- 2008-2010 使用国家统计局旧口径“房屋销售价格指数”；2011-01 起使用现行《住宅销售价格统计调查方案》。两段数据会保留 `methodology` 标记（后续补充），建模时应分别评估，不能把口径变化误判为市场变化。
- 每月约 140 条长表记录（70 城 × 新房/二手房），字段为环比、同比、当年平均指数；早期月报没有“当年平均”字段时保留为空并在训练时填补。
- 目标变量：`yoy_secondhand`，即二手住宅销售价格同比指数（上年同月=100）。这不是实际成交单价，不能直接解读为每平方米价格。

## 运行

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m src.collector --start-year 2008 --end-year 2026
.venv/bin/python -m src.macro_sources --lpr-month 2024-04 --lpr-url '<PBOC-LPR-URL>' --real-estate-month 2025-11 --real-estate-url '<NBS-REAL-ESTATE-URL>'
.venv/bin/python -m src.cirea_sources --input data/raw/cirea/secondhand_2023.docx --year 2023 --output data/processed/cirea_secondhand_2023.csv --source-url 'https://www.cirea.org.cn/content/4773'
.venv/bin/python -m src.clean
.venv/bin/python -m src.train
.venv/bin/python -m src.evaluate
.venv/bin/python -m src.audit --data data/processed/housing_indices_clean_v2.csv --output reports/data_quality_v2.json --start-month 2019-01 --end-month 2026-06
.venv/bin/python -m src.sample --input data/processed/housing_indices_clean_v2.csv --output data/samples/housing_panel_sample.csv --cities 北京 上海 重庆 深圳
.venv/bin/python -m src.report
.venv/bin/python -m src.beijing_sources
.venv/bin/python -m src.local_report
```

输出：清洗后的价格面板、模型比较、全国分析报告和北京区级网签分析报告。当前已实际落地的验证数据包括 2023 年二手房历史附件与 2025 年官方月报样本；2008 年起完整历史采集仍需继续处理国家统计局历史目录和旧格式附件。

## 北京/重庆区级五年预测

运行 `.venv/bin/python -m src.district_forecast` 可生成北京 17 个区/开发区和重庆 26 个市辖区 2026—2030 年二手房单价情景预测。完整逐区逐年 CSV 为 `data/processed/district_price_forecast_2026_2030.csv`，说明报告为 `reports/district_price_forecast_2026_2030.md`。

该预测将城市级官方二手房环比指数与区级挂牌/行情单价分开处理：城市路径使用滚动 12 个月回测选择长期方法，区级价格使用公开样本或明确标记的代理基准。`low` 置信度区域没有连续区级成交价格，不能解读为官方成交均价。

可接入的数据源、字段和口径边界见 [docs/data_sources.md](docs/data_sources.md)。

训练集/测试集按城市分组切分，测试城市不会出现在训练集，以减少空间泄漏。当前样本量适合做教学和流程演示；如果要用于研究或投资决策，应继续补充完整月度历史、城市宏观变量和真实成交单价，并做时间滚动验证。

当前特征工程还包括按城市计算的 1 期滞后、同比变化、3 期滚动均值。模型只使用二手房的滞后同比，不使用当期二手房同比本身，避免目标泄漏；新房当期价格变化可作为同期解释变量。

当前严格预测模型的特征只使用月份季节性、城市层级以及新房/二手房上一期指标，避免把目标月份的二手房数据作为预测输入。数据质量审计会检查月份缺口、城市覆盖、重复键和缺失值，并输出 `reports/data_quality_v2.json`。

快速实验样本见 `data/samples/housing_panel_sample.csv`，默认包含北京、上海、重庆、深圳，固定按月份、城市、市场排序；采样脚本使用固定随机种子，便于复现实验。
