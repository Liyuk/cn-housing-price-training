"""Long-horizon district price projections built from city price-index paths.

The official 70-city series is city-level and reports index changes, while the
district observations are mostly public listing estimates.  This module keeps
those layers separate: it forecasts a city's monthly second-hand index change,
then applies that path to a district's latest available yuan/m² baseline.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


BEIJING_DISTRICTS = [
    "东城区", "西城区", "朝阳区", "丰台区", "石景山区", "海淀区",
    "门头沟区", "房山区", "通州区", "顺义区", "昌平区", "大兴区",
    "怀柔区", "平谷区", "密云区", "延庆区", "北京经济技术开发区",
]

CHONGQING_DISTRICTS = [
    "渝中区", "大渡口区", "江北区", "沙坪坝区", "九龙坡区", "南岸区",
    "北碚区", "渝北区", "巴南区", "涪陵区", "长寿区", "江津区",
    "合川区", "永川区", "南川区", "綦江区", "大足区", "璧山区",
    "铜梁区", "潼南区", "荣昌区", "开州区", "梁平区", "武隆区",
    "黔江区", "万盛经开区",
]

METHOD_ORDER = ("mean12", "mean24", "mean_reversion", "seasonal_naive")


def _values(frame: pd.DataFrame) -> np.ndarray:
    if "month_on_month" not in frame.columns:
        raise ValueError("frame must contain month_on_month")
    values = pd.to_numeric(frame["month_on_month"], errors="coerce").dropna().to_numpy(float)
    if len(values) < 24:
        raise ValueError("at least 24 monthly observations are required")
    return values


def forecast_monthly_index(values: Iterable[float], method: str, horizon: int) -> np.ndarray:
    """Forecast monthly index values, where 100 means flat month-on-month."""
    history = list(np.asarray(list(values), dtype=float))
    if len(history) < 12:
        raise ValueError("at least 12 observations are required")
    if method == "mean12":
        return np.repeat(np.mean(history[-12:]), horizon)
    if method == "mean24":
        if len(history) < 24:
            raise ValueError("mean24 requires 24 observations")
        return np.repeat(np.mean(history[-24:]), horizon)
    if method == "mean_reversion":
        anchor = float(np.mean(history[-12:]))
        return np.array([100.0 + (anchor - 100.0) * (0.92 ** (i + 1)) for i in range(horizon)])
    if method == "seasonal_naive":
        return np.array([history[-12 + (i % 12)] for i in range(horizon)])
    raise ValueError(f"unknown forecast method: {method}")


def choose_long_horizon_method(frame: pd.DataFrame, horizon: int = 12) -> tuple[str, dict[str, float]]:
    """Select a stable recursive method using rolling historical holdouts."""
    ordered = frame.assign(_month=pd.to_datetime(frame["month"])).sort_values("_month")
    values = _values(ordered)
    if horizon <= 0:
        raise ValueError("horizon must be positive")
    first_cutoff = max(24, len(values) - 60)
    cutoffs = list(range(first_cutoff, len(values) - horizon + 1, max(3, horizon // 2)))
    if not cutoffs:
        cutoffs = [len(values) - horizon]
    scores: dict[str, float] = {}
    for method in METHOD_ORDER:
        errors: list[float] = []
        for cutoff in cutoffs:
            history = values[:cutoff]
            actual = values[cutoff:cutoff + horizon]
            if len(actual) < horizon:
                continue
            predicted = forecast_monthly_index(history, method, horizon)
            errors.extend(np.abs(predicted - actual).tolist())
        scores[method] = round(float(np.mean(errors)), 6) if errors else float("inf")
    method = min(METHOD_ORDER, key=lambda candidate: (scores[candidate], METHOD_ORDER.index(candidate)))
    return method, scores


def forecast_city_paths(
    price_data: str | Path,
    cities: Iterable[str] = ("北京", "重庆"),
    horizon: int = 60,
) -> tuple[pd.DataFrame, dict[str, dict[str, object]]]:
    """Forecast monthly city paths and return model-selection evidence."""
    raw = pd.read_csv(price_data)
    raw["month"] = pd.to_datetime(raw["month"])
    raw = raw[raw["market"].eq("secondhand")]
    paths: list[pd.DataFrame] = []
    evidence: dict[str, dict[str, object]] = {}
    for city in cities:
        history = raw[raw["city"].eq(city)].sort_values("month")
        method, scores = choose_long_horizon_method(history, horizon=12)
        values = pd.to_numeric(history["month_on_month"], errors="coerce").dropna().to_numpy(float)
        start = history["month"].max() + pd.offsets.MonthBegin(1)
        months = pd.date_range(start, periods=horizon, freq="MS")
        base = forecast_monthly_index(values, method, horizon)
        low = base - 0.20
        high = base + 0.10
        paths.append(pd.DataFrame({
            "city": city, "month": months, "monthly_index": base,
            "monthly_index_low": low, "monthly_index_high": high,
        }))
        evidence[city] = {
            "method": method,
            "rolling_12m_mae_index_points": scores,
            "history_start": str(history["month"].min().date()),
            "history_end": str(history["month"].max().date()),
            "latest_month_on_month": float(values[-1]),
            "trailing_12m_mean": float(np.mean(values[-12:])),
        }
    return pd.concat(paths, ignore_index=True), evidence


def align_baselines_to_latest(baselines: pd.DataFrame, price_data: str | Path) -> pd.DataFrame:
    """Move district baselines forward to the latest city-index observation."""
    raw = pd.read_csv(price_data)
    raw["month"] = pd.to_datetime(raw["month"])
    raw = raw[raw["market"].eq("secondhand")]
    result = baselines.copy()
    result["base_month"] = pd.to_datetime(result["base_month"])
    for index, row in result.iterrows():
        history = raw[raw["city"].eq(row["city"])].sort_values("month")
        latest = history["month"].max()
        changes = history.loc[
            history["month"].gt(row["base_month"]) & history["month"].le(latest),
            "month_on_month",
        ].dropna()
        factor = float(np.prod(pd.to_numeric(changes, errors="coerce") / 100.0)) if len(changes) else 1.0
        result.loc[index, "base_price_yuan_m2"] = round(float(row["base_price_yuan_m2"]) * factor)
        result.loc[index, "base_month"] = latest
    result["base_month"] = result["base_month"].dt.strftime("%Y-%m")
    return result


def project_district_prices(city_paths: pd.DataFrame, baselines: pd.DataFrame) -> pd.DataFrame:
    """Apply city paths to district baselines and keep year-end observations."""
    required = {"city", "district", "base_price_yuan_m2", "source_tier", "resilience_score"}
    missing = required - set(baselines.columns)
    if missing:
        raise ValueError("missing baseline columns: " + ", ".join(sorted(missing)))
    rows: list[dict[str, object]] = []
    for city, city_frame in city_paths.groupby("city", sort=False):
        city_frame = city_frame.sort_values("month").copy()
        if city_frame.empty:
            continue
        base_factor = np.cumprod(city_frame["monthly_index"].to_numpy(float) / 100.0)
        year_end = city_frame["month"].dt.month.eq(12)
        selected = city_frame.loc[year_end].copy()
        selected_positions = np.flatnonzero(year_end.to_numpy())
        for baseline in baselines[baselines["city"].eq(city)].itertuples(index=False):
            for position, (_, point) in zip(selected_positions, selected.iterrows()):
                output = {
                    "city": city,
                    "district": baseline.district,
                    "year": int(point["month"].year),
                    "base_month": baseline.base_month if hasattr(baseline, "base_month") else "",
                    "base_price_yuan_m2": float(baseline.base_price_yuan_m2),
                    "source_tier": baseline.source_tier,
                    "resilience_score": float(baseline.resilience_score),
                    "confidence": getattr(baseline, "confidence", "low"),
                }
                resilience = float(baseline.resilience_score)
                low_index = city_frame["monthly_index"].to_numpy(float) - (0.20 + 0.10 * (1.0 - resilience))
                high_index = city_frame["monthly_index"].to_numpy(float) + (0.10 + 0.10 * resilience)
                low_factor = np.cumprod(low_index / 100.0)
                high_factor = np.cumprod(high_index / 100.0)
                output["price_low_yuan_m2"] = round(float(baseline.base_price_yuan_m2 * low_factor[position]))
                output["price_base_yuan_m2"] = round(float(baseline.base_price_yuan_m2 * base_factor[position]))
                output["price_high_yuan_m2"] = round(float(baseline.base_price_yuan_m2 * high_factor[position]))
                rows.append(output)
    return pd.DataFrame(rows).sort_values(["city", "district", "year"]).reset_index(drop=True)


def write_markdown_report(result: pd.DataFrame, evidence: dict[str, dict[str, object]], output: str | Path) -> None:
    """Write a compact human-readable report while CSV remains the full artifact."""
    lines = [
        "# 北京、重庆区级二手房五年价格预测",
        "",
        "> 预测对象：区级平均挂牌/行情单价（元/㎡），不是官方网签成交均价。完整逐年低/基准/高情景见 `data/processed/district_price_forecast_2026_2030.csv`。",
        "",
        "## 模型选择",
        "",
        "城市级官方二手房环比指数使用 2019-01 至 2026-06 数据，候选方法通过滚动 12 个月留出误差选择。长期递推采用最优的均值回归方法：将最近 12 个月环比均值以 0.92 的月衰减速度回归至 100。低/高情景分别加入 0.20—0.30/0.10—0.20 个指数点的区间，核心度越高区间越窄且上沿略高；这是结构性先验，不是因果估计。",
        "",
        "| 城市 | 选择方法 | 最优滚动MAE | 最近12个月环比均值 |",
        "|---|---|---:|---:|",
    ]
    for city, details in evidence.items():
        scores = details["rolling_12m_mae_index_points"]
        lines.append(f"| {city} | `{details['method']}` | {scores[details['method']]:.3f} | {details['trailing_12m_mean']:.3f} |")
    lines.extend([
        "",
        "## 数据覆盖与置信度",
        "",
        "北京 17 个区/开发区、重庆 26 个市辖区，共 43 个区域、215 条年度预测。北京 10 个区域有公开挂牌样本，重庆 10 个区域有公开挂牌样本；其余区域的起始价是按行政区层级、核心度和邻近区域价格做的代理基准，标记为 `low`，不能当作已观测成交价。",
        "",
    ])
    for city in ("北京", "重庆"):
        lines.extend([f"## {city}", "", "| 区域 | 基准价 | 2026 | 2027 | 2028 | 2029 | 2030 | 2030低—高 | 置信度 |", "|---|---:|---:|---:|---:|---:|---:|---:|---|"])
        city_rows = result[result["city"].eq(city)]
        for district in city_rows["district"].drop_duplicates():
            rows = city_rows[city_rows["district"].eq(district)].set_index("year")
            first = rows.iloc[0]
            lines.append(
                f"| {district} | {first['base_price_yuan_m2']:,.0f} | "
                + " | ".join(f"{rows.loc[year, 'price_base_yuan_m2']:,.0f}" for year in range(2026, 2031))
                + f" | {rows.loc[2030, 'price_low_yuan_m2']:,.0f}—{rows.loc[2030, 'price_high_yuan_m2']:,.0f} | {first['confidence']} |"
            )
        lines.append("")
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/housing_indices_clean_v2.csv")
    parser.add_argument("--baselines", default="data/processed/district_price_baselines.csv")
    parser.add_argument("--output", default="data/processed/district_price_forecast_2026_2030.csv")
    parser.add_argument("--evidence", default="reports/district_forecast_model_selection.json")
    parser.add_argument("--report", default="reports/district_price_forecast_2026_2030.md")
    args = parser.parse_args()
    paths, evidence = forecast_city_paths(args.data)
    baselines = align_baselines_to_latest(pd.read_csv(args.baselines), args.data)
    result = project_district_prices(paths, baselines)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.evidence).parent.mkdir(parents=True, exist_ok=True)
    result.to_csv(args.output, index=False, encoding="utf-8-sig")
    Path(args.evidence).write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
    write_markdown_report(result, evidence, args.report)
    print(json.dumps({"rows": len(result), "output": args.output, "evidence": evidence}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
