"""Five-year (2026-2030) national and Beijing second-hand housing price forecasts.

Method (following the housing-price forecasting literature):

1. Short-term momentum, long-term mean reversion (Capozza et al. 2002; Case & Shiller 1989).
   Monthly month-on-month index changes are modelled as an error-correction
   process toward a long-run anchor.  The anchor is estimated from the index's
   own history (a rolling mean of month-on-month, mean-reverting toward 100),
   which is the honest choice given that the national macro panel only spans
   ~3.5 years and cannot separately identify long-run fundamentals.

2. National and Beijing are modelled separately because their reversion speeds
   differ (Beijing half-life ~2 months vs national ~16 months, estimated from
   the 2019-2026 panel).

3. Output is scenario/interval-based (base / low / high), not point-only,
   because the literature (Rapach & Strauss 2009; IMF Geng 2018) shows long-run
   point forecasts of house prices are inherently weak.

4. The national "index" is the mean of the 70-city month-on-month series; the
   Beijing path is Beijing's own series.  District yuan/m2 baselines are then
   projected along the city path, keeping the official-city vs listing-district
   layers separate.
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
    """Estimate AR(1) reversion to 100 and half-life in months.

    Regress (mom_t - 100) on (mom_{t-1} - 100).  Half-life = ln(0.5)/ln(rho).
    """
    values = series.to_numpy(float)
    x = values[:-1] - 100.0
    y = values[1:] - 100.0
    rho = float(np.sum(x * y) / np.sum(x * x))
    half_life = float(np.log(0.5) / np.log(rho)) if rho > 0 else float("inf")
    return {"rho": round(rho, 4), "half_life_months": round(half_life, 1)}


def forecast_error_correction(
    series: pd.Series,
    horizon: int = 60,
    anchor_window: int = 12,
) -> np.ndarray:
    """Error-correction forecast of month-on-month index values.

    Each step: predicted_mom = long_mean + (anchor - long_mean) * (1 - rho).
    ``rho`` is the AR(1) reversion coefficient; the path converges to the
    historical long-run mean (not to 100), so a market currently below its
    long-run norm recovers gradually, while one above it cools.
    """
    values = series.to_numpy(float)
    reversion = estimate_reversion(series)
    speed = 1.0 - reversion["rho"]
    long_mean = float(np.mean(values))
    anchor = float(np.mean(values[-anchor_window:]))
    out: list[float] = []
    for _ in range(horizon):
        next_val = long_mean + (anchor - long_mean) * speed
        out.append(next_val)
        anchor = next_val
    return np.asarray(out, dtype=float)


def _historical_5y_factor(series: pd.Series) -> float:
    """Cumulative factor of the trailing 60 months (a realistic 5y band anchor)."""
    s = series.sort_index().tail(60)
    return float(np.prod(s.to_numpy(float) / 100.0))


def forecast_series(
    series: pd.Series,
    horizon: int = 60,
    anchor_window: int = 12,
    band_frac: float = 0.5,
) -> pd.DataFrame:
    """Forecast a month-on-month index series and build base/low/high bands.

    The base path is an error-correction forecast converging to the long-run
    mean.  Low/high bands scale the base path by a fraction of the *historical*
    5-year cumulative change (e.g. national -22.9%, Beijing -8.9% over the past
    60 months), which anchors the uncertainty interval in observed reality
    rather than compounding an arbitrary monthly offset.
    """
    values = series.to_numpy(float)
    reversion = estimate_reversion(series)
    base = forecast_error_correction(series, horizon, anchor_window)
    base_factor = float(np.prod(base / 100.0))
    hist_factor = _historical_5y_factor(series)
    # half-width of the interval as a fraction of the historical swing
    half_width = band_frac * abs(1.0 - hist_factor)
    low_factor = base_factor - half_width
    high_factor = base_factor + half_width
    low_factor = max(low_factor, 1e-3)
    months = pd.date_range(series.index[-1] + pd.offsets.MonthBegin(1), periods=horizon, freq="MS")
    # a flat monthly adjustment that yields the target cumulative factors
    low_index = base * (low_factor / base_factor) ** (1.0 / horizon)
    high_index = base * (high_factor / base_factor) ** (1.0 / horizon)
    return pd.DataFrame({
        "month": months,
        "monthly_index": base,
        "monthly_index_low": low_index,
        "monthly_index_high": high_index,
    }), reversion, float(np.std(values))


def cumulative_factor(monthly_index: np.ndarray) -> float:
    """Cumulative multiplier from a sequence of month-on-month index values."""
    return float(np.prod(monthly_index / 100.0))


def project_baselines(
    city_paths: dict[str, pd.DataFrame],
    baselines: pd.DataFrame,
    base_month: str = "2026-05",
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
                    "confidence": getattr(baseline, "confidence", "low"),
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

    national_path, national_rev, national_sigma = forecast_series(national, args.horizon)
    beijing_path, beijing_rev, beijing_sigma = forecast_series(beijing, args.horizon)

    city_paths = {"全国": national_path, "北京": beijing_path}

    # cumulative multipliers
    national_factor = cumulative_factor(national_path["monthly_index"].to_numpy(float))
    beijing_factor = cumulative_factor(beijing_path["monthly_index"].to_numpy(float))

    # project Beijing districts
    district_rows = project_baselines({"北京": beijing_path}, baselines[baselines["city"].eq("北京")])

    # save paths
    all_paths = pd.concat([
        national_path.assign(region="全国"),
        beijing_path.assign(region="北京"),
    ])
    Path(args.paths).parent.mkdir(parents=True, exist_ok=True)
    all_paths.to_csv(args.paths, index=False, encoding="utf-8-sig")
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    district_rows.to_csv(args.output, index=False, encoding="utf-8-sig")

    summary = {
        "national": {
            "reversion": national_rev,
            "resid_sigma": round(national_sigma, 4),
            "latest_monthly_index": round(float(national.iloc[-1]), 3),
            "cumulative_5y_factor": round(national_factor, 4),
        },
        "beijing": {
            "reversion": beijing_rev,
            "resid_sigma": round(beijing_sigma, 4),
            "latest_monthly_index": round(float(beijing.iloc[-1]), 3),
            "cumulative_5y_factor": round(beijing_factor, 4),
        },
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(
        "# 未来五年（2026—2030）全国与北京二手住宅价格预测\n\n"
        + "> 方法：误差修正/均值回归（短期动量 + 长期向均值收敛），分情景输出；全国与北京分别建模。"
        + "官方指数是价格指数而非绝对房价，预测的是指数路径。\n\n"
        + "```json\n" + json.dumps(summary, ensure_ascii=False, indent=2) + "\n```\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
