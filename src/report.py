"""Generate a compact, reproducible analysis report from the processed panel."""

from __future__ import annotations

import argparse
import os

import pandas as pd


def build_report(data_path: str, output_path: str) -> str:
    data = pd.read_csv(data_path)
    data["month"] = pd.to_datetime(data["month"])
    lines = [
        "# 中国住宅价格指数 ML 项目分析报告",
        "",
        "> 本报告由 `src/report.py` 自动生成。价格字段是指数，不是每平方米成交价。",
        "> 本报告只对当前已落地数据做统计；月份缺口和口径差异见数据质量审计，不代表完整全国历史面板。",
        "",
        "## 数据概览",
        "",
        f"- 记录数：{len(data):,}",
        f"- 月份：{data['month'].min():%Y-%m} 至 {data['month'].max():%Y-%m}（{data['month'].nunique()} 个观测月）",
        f"- 城市数：{data['city'].nunique()}",
        f"- 市场：{', '.join(sorted(data['market'].dropna().unique()))}",
    ]
    if "methodology" in data:
        methodology = data["methodology"].value_counts().to_dict()
        lines.append(f"- 统计口径：{methodology}")
    lines.extend(["", "## 新房/二手房指数概览", "", "| 市场 | 平均环比指数 | 平均同比指数 | 记录数 |", "|---|---:|---:|---:|"])
    summary = data.groupby("market").agg(month_on_month=("month_on_month", "mean"), yoy=("yoy", "mean"), rows=("city", "size"))
    for market, row in summary.iterrows():
        lines.append(f"| {market} | {row['month_on_month']:.2f} | {row['yoy']:.2f} | {int(row['rows']):,} |")
    lines.extend(["", "## 市场状态统计", ""])
    for market, subset in data.groupby("market"):
        mom_down = (subset["month_on_month"] < 100).mean() * 100
        yoy_down = (subset["yoy"] < 100).mean() * 100
        volatility = subset.groupby("city")["month_on_month"].std().mean()
        lines.append(f"- **{market}**：环比低于 100 的比例 {mom_down:.1f}%；同比低于 100 的比例 {yoy_down:.1f}%；城市平均环比波动 {volatility:.2f} 个指数点。")
    yearly = data.assign(year=data["month"].dt.year).groupby(["year", "market"])["yoy"].mean().unstack()
    lines.extend(["", "## 年度同比指数均值", "", "| 年份 | 新房 | 二手房 |", "|---:|---:|---:|"])
    for year, row in yearly.iterrows():
        lines.append(f"| {year} | {row.get('new', float('nan')):.2f} | {row.get('secondhand', float('nan')):.2f} |")
    wide = data.pivot_table(index=["month", "city"], columns="market", values="yoy").dropna()
    if {"new", "secondhand"}.issubset(wide.columns):
        lines.extend(["", "## 新房与二手房关系", "", f"- 同一城市同一月份的新房与二手房同比指数相关系数：{wide['new'].corr(wide['secondhand']):.3f}。", "- 该相关性是描述性统计，不代表因果关系；后续需要加入交易量、利率和供给变量。"])
    city_summary = data[data["city"].isin(["北京", "重庆"])].groupby(["city", "market"]).agg(avg_yoy=("yoy", "mean"), avg_mom=("month_on_month", "mean"), rows=("city", "size"))
    if not city_summary.empty:
        lines.extend(["", "## 北京/重庆专项摘要", "", "| 城市 | 市场 | 平均同比 | 平均环比 | 记录数 |", "|---|---|---:|---:|---:|"])
        for (city, market), row in city_summary.iterrows():
            lines.append(f"| {city} | {market} | {row['avg_yoy']:.2f} | {row['avg_mom']:.2f} | {int(row['rows'])} |")
    latest_month = data["month"].max()
    latest = data[data["month"] == latest_month]
    lines.extend(["", f"## 最新月份（{latest_month:%Y-%m}）城市分化", ""])
    for market in sorted(latest["market"].unique()):
        subset = latest[latest["market"] == market].sort_values("yoy")
        low = "、".join(f"{r.city}({r.yoy:.1f})" for r in subset.head(5).itertuples())
        high = "、".join(f"{r.city}({r.yoy:.1f})" for r in subset.tail(5).sort_values("yoy", ascending=False).itertuples())
        lines.extend([f"- **{market}**：同比较低：{low}；同比较高：{high}"])
    lines.extend([
        "",
        "## 建模解释",
        "",
        "当前基线模型预测二手住宅同比指数。后续加入国家房地产开发/销售指标、LPR、土地成交和北京/重庆网签数据后，应采用按时间滚动的验证集，并将 2008—2010 旧口径与 2011 年后现行口径分开评估。",
        "",
        "## 数据局限",
        "",
        "1. 70 城价格是统计指数，不提供完整城市/区县成交单价。",
        "2. 全国房地产月报多数是累计口径，直接转月度时必须做差分并处理 1—2 月合并发布。",
        "3. 北京和重庆区级交易量需要地方住建部门数据，不能从 70 城表格反推。",
    ])
    report = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/housing_indices.csv")
    parser.add_argument("--output", default="reports/analysis.md")
    args = parser.parse_args()
    print(build_report(args.data, args.output))
