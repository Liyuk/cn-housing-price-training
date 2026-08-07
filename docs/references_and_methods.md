# 论文、开源项目与本项目方法路线

## 优先参考论文

### 1. 空间异质性：GNNWR（深圳）

Wang、Wang、Wu 的深圳研究将地理神经网络加权回归（GNNWR）用于住宅估价，核心启发是：同一个因素在不同区域的作用不应被假设为完全相同。适合未来有小区/区级成交价格和空间坐标后使用。

本项目借鉴：先做区级固定效应和空间滞后，再评估GWR/MGWR，最后才考虑GNNWR，避免数据不足时过度复杂化。

论文：[House Price Valuation Model Based on Geographically Neural Network Weighted Regression](https://arxiv.org/abs/2202.04358)

### 2. 北京空间因素：空间误差模型与GWR

北京绿地可达性研究同时使用空间误差模型（SEM）和GWR，说明交通、公共服务等因素可能存在空间溢出，而且影响强度随区域变化。

本项目借鉴：加入轨道交通、教育、绿地、就业和中心距离等区级特征，并区分“全局影响”和“区域局部影响”。

论文：[The Relationship between Multiple Travel Modes Green Space Accessibility and Housing Price](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4327400)

### 3. 机器学习解释：Random Forest + SHAP

该研究将随机森林与SHAP结合，用位置、环境和基础设施变量解释房价预测，适合本项目的“预测 + 影响因素报告”目标。

本项目借鉴：不仅输出预测值，还输出每个城市/区的主要正负贡献因素，并将SHAP解释明确标注为模型关联，不表述为因果。

论文：[Exploring Housing Price Dynamics in Sustainable Cities Through a Cooperated Big Data Driven Machine Learning Method](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=5257282)

### 4. 空间与时间联动

关于中国城市房价的空间研究表明，邻近城市和基础设施变化可能影响本地价格。对本项目而言，最值得实现的是“邻近城市价格滞后 + 本城市自身滞后”的动态空间面板，而不是直接训练黑箱深度网络。

## 开源项目

### 链家/贝壳挂牌数据分析

[linpingta/lianjia-eroom-analysis](https://github.com/linpingta/lianjia-eroom-analysis) 提供北京、杭州、上海、深圳、广州等城市的挂牌数据分析脚本和历史CSV结构，可参考字段设计：小区、区域、户型、面积、挂牌价、采集时间和价格调整轨迹。

注意：仓库自身声明仅适度访问公开数据、尊重网站规则，不能访问非公开数据。因此本项目只参考其数据字典和分析方法，不直接复制高频爬取行为。

### 空间统计实现

- `PySAL` / `mgwr`：空间权重、空间回归、GWR/MGWR；
- `scikit-learn`：基准回归、随机森林、时间切分和管线；
- `xgboost` / `lightgbm`：梯度提升模型；
- `shap`：模型解释和特征贡献；
- `geopandas`：行政区边界、空间连接和距离特征。

## 对当前项目的实施顺序

1. 先补齐连续城市级月度面板；
2. 加入严格滞后特征和宏观变量；
3. 建立季节性基线、Ridge、Random Forest、Gradient Boosting四组基准；
4. 加入城市固定效应和城市邻接价格滞后；
5. 有连续区级价格后，再做区级面板固定效应；
6. 有空间坐标后，再做Moran's I、SEM、GWR/MGWR；
7. 最后使用SHAP和局部模型解释区域差异；
8. 所有模型按时间滚动回测，不使用随机切分作为主要结论。

## 不建议现在做的事情

- 直接上LSTM/Transformer：当前月度面板缺口太多，容易记忆缺失模式而不是学习市场规律。
- 把挂牌价当成交价：挂牌价存在选择偏差和议价空间，必须单独命名为挂牌市场指标。
- 用城市级70城指数推断区级价格：空间粒度不匹配。
- 只看R²：必须同时报告MAE、RMSE、方向准确率、滚动窗口稳定性和数据覆盖率。

