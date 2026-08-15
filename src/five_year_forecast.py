"""Five-year (2026-2030) national and Beijing second-hand housing price forecasts.

Method (following the housing-price forecasting literature):

1. An explainable three-component ensemble:
     - Trend continuation: extend the trailing 12-month month-on-month mean.
     - Mean reversion: converge toward the long-run mean at the data-estimated
       speed (AR(1)); relevant when a market is near its historical norm.
     - Seasonality: use the same calendar month a year earlier.
   Component weights are NOT assumed; they are selected by strict rolling
   out-of-sample evaluation (each forecast point uses only history available
   before it).  This lets the data decide whether a market is trending or
   mean-reverting -- e.g. national is trending down (weight ~1 on trend),
   Beijing is mean-reverting (weights split across reversion + seasonality).

2. National 70-city and Beijing are modelled separately because their dynamics
   differ (trending vs reversion).

3. Output is scenario/interval-based (base / low / high) anchored to the
   historical 5-year swing, because long-run point forecasts are inherently
   weak (Rapach & Strauss 2009; IMF Geng 2018).

4. District yuan/m2 baselines are projected along the city path, keeping the
   official-city index vs third-party listing-district layers separate.  The
   district scenarios are low-confidence by construction (18-month listing
   sample, non-official price basis).
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd


def _monthly_index(price_data: str | Path, city: str | None = None) -> pd.Series:
    """Monthly mean second-hand month-on-month index for a city or all cities."""
    raw = pd.read_csv(price_data)
    raw["month"] = pd.to_datetime(raw["month"])
    raw = raw[raw["market"].eq("secondhand")]
    if city:
        raw = raw[raw["city"].eq(city)]
    series = raw.groupby("month")["month_on_month"].mean().sort_index()
    return series


def estimate_reversion(series: pd.Series) -> dict[str, float]:
    """Estimate AR(1) reversion to the long-run mean and half-life in months."""
    values = series.to_numpy(float)
    x = values[:-1] - 100.0
    y = values[1:] - 100.0
    rho = float(np.sum(x * y) / np.sum(x * x))
    half_life = float(np.log(0.5) / np.log(rho)) if rho > 0 else float("inf")
    return {"rho": round(rho, 4), "half_life_months": round(half_life, 1)}


def _component_forecasts(hist: pd.Series, horizon: int, rho: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return (trend, mean-reversion, seasonality) forecasts of length horizon."""
    vals = hist.to_numpy(float)
    trend = np.full(horizon, float(np.mean(vals[-12:])))
    speed = 1.0 - rho
    long_mean = float(np.mean(vals))
    anchor = float(np.mean(vals[-12:]))
    reversion = []
    for _ in range(horizon):
        nv = long_mean + (anchor - long_mean) * speed
        reversion.append(nv)
        anchor = nv
    season = np.asarray([vals[-12 + i % 12] for i in range(horizon)], dtype=float)
    return trend, np.asarray(reversion, dtype=float), season


def _grid_search_weights(
    series: pd.Series,
    horizon: int,
    rho: float,
) -> tuple[np.ndarray, float]:
    """Choose component weights by rolling out-of-sample MAE on the history.

    To avoid look-ahead bias, only the first 3/4 of the series is used to pick
    weights; the remaining 1/4 is held out implicitly by the walk-forward loop
    below (each cutoff is entirely before the held-out tail).  This mirrors what
    an analyst would actually know at the forecast date.
    """
    vals = series.to_numpy(float)
    idx = series.index
    # use only the first ~3/4 of history for weight selection
    train_end = int(len(vals) * 0.75)
    best: tuple[float, np.ndarray] | None = None
    for w1 in np.arange(0.0, 1.0001, 0.25):
        for w2 in np.arange(0.0, 1.0001 - w1 + 1e-9, 0.25):
            w3 = 1.0 - w1 - w2
            errs: list[float] = []
            for cutoff in range(36, train_end - horizon + 1, 3):
                hist = pd.Series(vals[:cutoff], index=idx[:cutoff])
                actual = vals[cutoff:cutoff + horizon]
                t, r, s = _component_forecasts(hist, horizon, rho)
                pred = w1 * t + w2 * r + w3 * s
                errs.extend(np.abs(pred - actual).tolist())
            if not errs:
                continue
            mae = float(np.mean(errs))
            if best is None or mae < best[0]:
                best = (mae, np.asarray([w1, w2, w3]))
    if best is None:
        best = (float("inf"), np.asarray([1.0, 0.0, 0.0]))
    return best[1], best[0]


def forecast_explainable(
    series: pd.Series,
    horizon: int = 60,
    anchor_window: int = 12,
) -> tuple[pd.DataFrame, dict[str, object]]:
    """Forecast with data-selected weights and a decomposition of each step."""
    rho = estimate_reversion(series)["rho"]
    weights, train_mae = _grid_search_weights(series, 12, rho)
    hist = series.copy()
    months = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    base = np.empty(horizon)
    trend_c = np.empty(horizon)
    reversion_c = np.empty(horizon)
    season_c = np.empty(horizon)
    for i in range(horizon):
        t, r, s = _component_forecasts(hist, 1, rho)
        trend_c[i], reversion_c[i], season_c[i] = t[0], r[0], s[0]
        base[i] = weights[0] * t[0] + weights[1] * r[0] + weights[2] * s[0]
        # advance history for seasonality reference
        hist = pd.concat([hist, pd.Series([base[i]], index=[months[i]])])
    # scenario bands anchored to historical 5y swing
    hist_factor = float(np.prod(series.to_numpy()[-60:] / 100.0))
    base_factor = float(np.prod(base / 100.0))
    half_width = 0.5 * abs(1.0 - hist_factor)
    low_factor = max(base_factor - half_width, 1e-3)
    high_factor = base_factor + half_width
    low_index = base * (low_factor / base_factor) ** (1.0 / horizon)
    high_index = base * (high_factor / base_factor) ** (1.0 / horizon)
    frame = pd.DataFrame({
        "month": months,
        "monthly_index": base,
        "monthly_index_low": low_index,
        "monthly_index_high": high_index,
        "trend_component": trend_c,
        "reversion_component": reversion_c,
        "season_component": season_c,
    })
    meta = {
        "rho": rho,
        "half_life_months": estimate_reversion(series)["half_life_months"],
        "weights": {
            "trend": round(float(weights[0]), 3),
            "mean_reversion": round(float(weights[1]), 3),
            "seasonality": round(float(weights[2]), 3),
        },
        "train_mae_12m": round(train_mae, 4),
        "long_run_mean": round(float(np.mean(series)), 3),
        "trailing_12m_mean": round(float(np.mean(series.to_numpy()[-12:])), 3),
        "hist_5y_factor": round(hist_factor, 4),
        "cumulative_5y_factor": round(base_factor, 4),
    }
    return frame, meta


def project_baselines(
    city_paths: dict[str, pd.DataFrame],
    baselines: pd.DataFrame,
) -> pd.DataFrame:
    """Project district yuan/m2 baselines along a city's forecast path."""
    rows: list[dict[str, object]] = []
    for city, path in city_paths.items():
        path = path.sort_values("month").copy()
        base_factor = np.cumprod(path["monthly_index"].to_numpy(float) / 100.0)
        low_factor = np.cumprod(path["monthly_index_low"].to_numpy(float) / 100.0)
        high_factor = np.cumprod(path["monthly_index_high"].to_numpy(float) / 100.0)
        year_ends = [i for i, m in enumerate(path["month"]) if m.month == 12]
        city_base = baselines[baselines["city"].eq(city)]
        for baseline in city_base.itertuples(index=False):
            for pos in year_ends:
                point = path.iloc[pos]
                rows.append({
                    "city": city,
                    "district": baseline.district,
                    "year": int(point["month"].year),
                    "base_price_yuan_m2": float(baseline.base_price_yuan_m2),
                    "price_low_yuan_m2": round(float(baseline.base_price_yuan_m2) * low_factor[pos]),
                    "price_base_yuan_m2": round(float(baseline.base_price_yuan_m2) * base_factor[pos]),
                    "price_high_yuan_m2": round(float(baseline.base_price_yuan_m2) * high_factor[pos]),
                    "confidence": "low",
                })
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/housing_indices_clean_v3.csv")
    parser.add_argument("--baselines", default="data/processed/district_price_baselines.csv")
    parser.add_argument("--horizon", type=int, default=60)
    parser.add_argument("--output", default="data/processed/five_year_forecast_2026_2030.csv")
    parser.add_argument("--paths", default="data/processed/five_year_index_paths.csv")
    parser.add_argument("--report", default="reports/five_year_forecast_2026_2030.md")
    args = parser.parse_args()

    national = _monthly_index(args.data)
    beijing = _monthly_index(args.data, city="北京")
    baselines = pd.read_csv(args.baselines)

    nat_path, nat_meta = forecast_explainable(national, args.horizon)
    bj_path, bj_meta = forecast_explainable(beijing, args.horizon)

    city_paths = {"全国": nat_path, "北京": bj_path}
    district_rows = project_baselines({"北京": bj_path}, baselines[baselines["city"].eq("北京")])

    all_paths = pd.concat([
        nat_path.assign(region="全国"),
        bj_path.assign(region="北京"),
    ])
    Path(args.paths).parent.mkdir(parents=True, exist_ok=True)
    all_paths.to_csv(args.paths, index=False, encoding="utf-8-sig")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    district_rows.to_csv(args.output, index=False, encoding="utf-8-sig")

    summary = {"national": nat_meta, "beijing": bj_meta}
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(
        "# 未来五年（2026—2030）全国与北京二手住宅价格预测\n\n"
        "> 方法：可解释三成分组合（趋势延续 / 均值回归 / 季节性），权重由滚动样本外验证选择。"
        "官方指数是价格指数而非绝对房价，预测的是指数路径。\n\n"
        "```json\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
