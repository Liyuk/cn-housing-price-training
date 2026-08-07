"""Reports for city-level transaction sources."""

from __future__ import annotations

import argparse
import os

import pandas as pd


def _corr(frame: pd.DataFrame, left: str, right: str):
    values = frame[[left, right]].dropna()
    if len(values) < 2 or values[left].nunique() < 2 or values[right].nunique() < 2:
        return None
    return float(values[left].corr(values[right]))


def build_district_relationship_report(data) -> str:
    """Describe district-level relationships without inventing price data.

    The Beijing public source currently contains transaction counts and areas,
    not district sale prices. If future files add price columns, this report
    will calculate their cross-sectional correlations as well.
    """
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    required = {"month", "city", "district", "online_signing_count", "online_signing_area_m2"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError("missing district columns: " + ", ".join(sorted(missing)))
    for column in ("online_signing_count", "online_signing_area_m2"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce")
    frame = frame.dropna(subset=["district", "online_signing_count", "online_signing_area_m2"])
    frame["area_per_signing_m2"] = frame["online_signing_area_m2"] / frame["online_signing_count"]
    frame = frame[frame["online_signing_count"] > 0].copy()
    if frame.empty:
        return "# 区级关系分析\n\n没有可分析的区级交易记录。\n"

    months = ", ".join(sorted(frame["month"].astype(str).unique()))
    city = ", ".join(sorted(frame["city"].astype(str).unique()))
    count_area_corr = _corr(frame, "online_signing_count", "online_signing_area_m2")
    count_size_corr = _corr(frame, "online_signing_count", "area_per_signing_m2")
    total_count = frame["online_signing_count"].sum()
    frame["count_share"] = frame["online_signing_count"] / total_count
    top = frame.sort_values("online_signing_count", ascending=False).head(5)

    lines = [
        "# 区级房产关系分析",
        "",
        f"城市：{city}；月份：{months}；区/开发区记录数：{len(frame)}。",
        "",
        "## 当前能识别的关系",
        "",
    ]
    if count_area_corr is not None:
        lines.append(f"- 成交套数与成交面积相关系数：**{count_area_corr:.3f}**。该值越接近1，说明成交套数多的区域通常成交面积也大。")
    if count_size_corr is not None:
        lines.append(f"- 成交套数与平均签约面积相关系数：**{count_size_corr:.3f}**。它反映活跃区域是否同时存在更大户型成交。")
    lines.extend([
        "- 成交量集中度：前5个区域合计占全样本成交套数 "
        f"**{top['count_share'].sum():.1%}**。",
        "",
        "## 成交量最大的区域",
        "",
        "| 区域 | 网签套数 | 成交面积(m²) | 平均签约面积(m²/套) | 套数占比 |",
        "|---|---:|---:|---:|---:|",
    ])
    for row in top.itertuples():
        lines.append(
            f"| {row.district} | {row.online_signing_count:,.0f} | "
            f"{row.online_signing_area_m2:,.2f} | {row.area_per_signing_m2:.2f} | {row.count_share:.1%} |"
        )

    price_columns = [column for column in ("price", "unit_price", "price_yoy", "yoy") if column in frame.columns]
    lines.extend(["", "## 房价关系的限制", ""])
    if not price_columns:
        lines.append("当前数据没有区级成交单价或区级价格指数，只有网签套数和成交面积，因此不能得出“哪个区房价更高/成交量是否推动房价”的统计结论。")
        lines.append("需要补充至少连续6—12个月的区级成交单价、挂牌价或价格指数，才能分析区级价格趋势、滞后关系和因果模型。")
    else:
        price_column = price_columns[0]
        price_corr = _corr(frame, price_column, "online_signing_count")
        if price_corr is not None:
            lines.append(f"区级字段 `{price_column}` 与成交套数相关系数：**{price_corr:.3f}**。这是相关性，不代表因果关系。")
        else:
            lines.append(f"区级价格字段 `{price_column}` 的有效观测不足，暂不能计算相关性。")
    lines.extend([
        "",
        "## 建模建议",
        "",
        "1. 区级面板：以区-月份为一行，预测下月成交单价或价格涨跌。",
        "2. 解释变量：网签套数、成交面积、平均户型面积、挂牌量、库存、利率、就业和人口。",
        "3. 验证方式：按时间滚动验证，并控制区固定效应，避免把区域长期差异误当成短期价格影响。",
    ])
    return "\n".join(lines) + "\n"


def build_beijing_report(data_path: str, output_path: str) -> str:
    data = pd.read_csv(data_path)
    data["area_per_signing_m2"] = data["online_signing_area_m2"] / data["online_signing_count"]
    total_count = data["online_signing_count"].sum()
    total_area = data["online_signing_area_m2"].sum()
    data["count_share"] = data["online_signing_count"] / total_count
    lines = [
        "# 北京区级二手房网签分析",
        "",
        f"数据月份：{data['month'].min()}；区/开发区数量：{data['district'].nunique()}。",
        "",
        "| 区域 | 网签套数 | 成交面积(m²) | 套数占比 | 平均签约面积(m²/套) |",
        "|---|---:|---:|---:|---:|",
    ]
    for row in data.sort_values("online_signing_count", ascending=False).itertuples():
        lines.append(f"| {row.district} | {row.online_signing_count:,.0f} | {row.online_signing_area_m2:,.2f} | {row.count_share:.1%} | {row.area_per_signing_m2:.2f} |")
    lines.extend([
        "",
        f"全市纳入分区合计：{total_count:,.0f} 套、{total_area:,.2f} m²。",
        "",
        "注意：这是北京市住建委公开的存量房网签统计，不是成交价格；区级交易量与国家统计局 70 城价格指数的统计口径不同。",
    ])
    report = "\n".join(lines) + "\n"
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write(report)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/beijing_district_transactions.csv")
    parser.add_argument("--output", default="reports/beijing_district_analysis.md")
    parser.add_argument("--relationships", action="store_true")
    args = parser.parse_args()
    if args.relationships:
        report = build_district_relationship_report(args.data)
        os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
        with open(args.output, "w", encoding="utf-8") as handle:
            handle.write(report)
        print(report)
    else:
        print(build_beijing_report(args.data, args.output))
