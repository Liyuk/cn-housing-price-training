#!/usr/bin/env python3
"""Build static JSON bundles for the GitHub Pages demo site.

The demo site (`site/`) is fully static: every chart is rendered client-side
from pre-baked JSON under `site/data/`. This script turns the processed CSVs
into those JSON bundles so the charts always agree with the repo's data.

The CSVs live under `data/processed/` and are git-ignored; the generated
`site/data/*.json` files ARE committed, which is what makes Pages deployment
self-contained.

Usage:
    .venv/bin/python scripts/build_demo_data.py

Outputs (all written to site/data/):
    meta.json                     headline numbers, weights, coverage, CIREA identity check
    forecast_series.json          historical + forecast fan for 全国 / 北京
    components.json               trend/reversion/season per region per month
    cities_yoy.json               second-hand YoY matrix for the city heatmap
    district_scenarios.json       Beijing 17 / Chongqing 26 district 2026→2030 scenarios
    district_listing.json         Beijing 10-district listing price panel
    lpr.json                      LPR history
    macro.json                    national macro panel (investment, starts, sales, inventory)
    market_compare.json           new vs second-hand national MoM comparison
    official.json                 Beijing official 2025-10 district signings
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "site" / "data"

# The model's historical series is the monthly mean of the second-hand MoM
# index over available cities (see src/five_year_forecast.py:_monthly_index).
# The forecast month-on-month paths are read straight from the model output,
# so the fan chart and the hero numbers always agree with the reports.


def read(path: str) -> pd.DataFrame:
    """Read a processed CSV, tolerating a UTF-8 BOM on the first column."""
    frame = pd.read_csv(PROCESSED / path, encoding="utf-8-sig")
    if "month" in frame.columns:
        frame["month"] = pd.to_datetime(frame["month"])
    return frame


def monthly_secondhand(city: str | None = None) -> pd.Series:
    frame = read("housing_indices_clean_v3.csv")
    frame = frame[frame["market"].eq("secondhand")]
    if city:
        frame = frame[frame["city"].eq(city)]
    return frame.groupby("month")["month_on_month"].mean().sort_index()


def cumulative(series: pd.Series, anchor: str) -> pd.Series:
    """Chain MoM index into a cumulative series, re-anchored to 100 at `anchor`."""
    cum = (series / 100.0).cumprod() * 100.0
    return cum / float(cum.loc[pd.Timestamp(anchor)]) * 100.0


def cumulative_from(series: pd.Series, reference_value: float) -> pd.Series:
    """Cumulative series continuing from `reference_value`.

    The forecast paths start the month after the historical series ends and are
    expressed as MoM indices. Chained from `reference_value` (= 100 when history
    is re-anchored to 100 at the anchor month), this reproduces the report's
    scenario numbers exactly: e.g. national base −22.1% over 2026-07 → 2031-06.
    """
    return (series / 100.0).cumprod() * reference_value


def build_meta() -> dict:
    paths = read("five_year_index_paths.csv")
    last_hist = monthly_secondhand().index.max()
    n_cities = read("housing_indices_clean_v3.csv")["city"].nunique()

    def scenarios(region: str) -> dict:
        sub = paths[paths["region"].eq(region)]
        # The forecast paths start the month after history ends, so anchor the
        # cumulative fan to the last historical value (≈100).
        ref = float(cumulative(monthly_secondhand(), "2026-06").iloc[-1])
        base = cumulative_from(sub.set_index("month")["monthly_index"], ref)
        low = cumulative_from(sub.set_index("month")["monthly_index_low"], ref)
        high = cumulative_from(sub.set_index("month")["monthly_index_high"], ref)
        end = sub["month"].max()
        return {
            "base_cum": round(float(base.loc[end]) - 100.0, 1),
            "low_cum": round(float(low.loc[end]) - 100.0, 1),
            "high_cum": round(float(high.loc[end]) - 100.0, 1),
        }

    # Weights and reversion half-lives are verified model constants from the
    # five-year forecast report (reports/five_year_forecast_2026_2030.md).
    return {
        "updated": "2026-08-15",
        "anchor": str(last_hist.date()),
        "horizon_end": str(paths["month"].max().date()),
        "coverage": {
            "cities": n_cities,
            "months": int(monthly_secondhand().shape[0]),
            "start": "2019-01",
            "end": "2026-06",
        },
        "national": scenarios("全国"),
        "beijing": scenarios("北京"),
        "weights": {
            "national": {"trend": 1.00, "reversion": 0.00, "season": 0.00},
            "beijing": {"trend": 0.25, "reversion": 0.50, "season": 0.25},
        },
        "reversion": {
            "national": {"rho": 0.958, "half_life_months": 16.1},
            "beijing": {"rho": 0.695, "half_life_months": 1.9},
        },
        "cum60m": {
            "national": round(float(np.prod(monthly_secondhand().to_numpy()[-60:] / 100.0) - 1.0) * 100.0, 1),
            "beijing": round(float(np.prod(monthly_secondhand(city="北京").to_numpy()[-60:] / 100.0) - 1.0) * 100.0, 1),
        },
        "cirea": _cirea_identity(),
    }


def _cirea_identity() -> dict:
    """Industry (CIREA) vs official (NBS) second-hand index identity check.

    Both index series come from the same NBS source; CIREA's public historical
    documents are a repost of the official numbers. The comparison quantifies
    that claim over every overlapping cell.
    """
    nbs = read("housing_indices_clean_v3.csv")
    cirea = pd.concat(
        [read("cirea_secondhand_2019_2022.csv"), read("cirea_secondhand_2023.csv")]
    )
    nbs = nbs[nbs["methodology"].eq("current_cirea_legacy_doc")]
    merged = pd.merge(
        nbs[["month", "city", "market", "yoy"]],
        cirea[["month", "city", "market", "yoy"]],
        on=["month", "city", "market"],
        suffixes=("_nbs", "_cirea"),
    )
    overlap = int(len(merged))
    if overlap:
        r = float(merged["yoy_nbs"].corr(merged["yoy_cirea"]))
        max_diff = float((merged["yoy_nbs"] - merged["yoy_cirea"]).abs().max())
    else:
        r, max_diff = float("nan"), float("nan")
    return {
        "overlap_cells": overlap,
        "r": round(r, 4),
        "max_abs_diff": round(max_diff, 4),
        "span": "2019-01 → 2023-12",
    }


def build_forecast() -> dict:
    paths = read("five_year_index_paths.csv")
    series = {}

    for region in ("全国", "北京"):
        hist = cumulative(monthly_secondhand(city=None if region == "全国" else "北京"), "2026-06")
        hist = hist[hist.index <= "2026-06"]
        ref = float(hist.iloc[-1])
        sub = paths[paths["region"].eq(region)].set_index("month")
        base = cumulative_from(sub["monthly_index"], ref)
        low = cumulative_from(sub["monthly_index_low"], ref)
        high = cumulative_from(sub["monthly_index_high"], ref)
        series[region] = {
            "history": [
                {"m": m.strftime("%Y-%m"), "v": round(float(v), 2)}
                for m, v in hist.items()
            ],
            "forecast": [
                {
                    "m": m.strftime("%Y-%m"),
                    "base": round(float(base.loc[m]), 2),
                    "low": round(float(low.loc[m]), 2),
                    "high": round(float(high.loc[m]), 2),
                }
                for m in sub.index
            ],
        }
    return series


def build_components() -> dict:
    paths = read("five_year_index_paths.csv")
    result = {}
    for region in ("全国", "北京"):
        sub = paths[paths["region"].eq(region)]
        result[region] = [
            {
                "m": row.month.strftime("%Y-%m"),
                "trend": round(float(row.trend_component), 3),
                "reversion": round(float(row.reversion_component), 3),
                "season": round(float(row.season_component), 3),
                "base": round(float(row.monthly_index), 3),
            }
            for row in sub.itertuples()
        ]
    return result


def build_cities() -> dict:
    frame = read("housing_indices_clean_v3.csv")
    frame = frame[frame["market"].eq("secondhand")]
    months_ts = sorted(frame["month"].unique())
    pivot = frame.pivot_table(index="city", columns="month", values="yoy", aggfunc="first")

    # Sort so the biggest recent decliners sit on top of the heatmap.
    order = pivot[months_ts[-1]].dropna().sort_values(ascending=False).index
    cities = list(order) + [c for c in pivot.index if c not in order]

    months = [m.strftime("%Y-%m") for m in months_ts]

    return {
        "months": months,
        "cities": cities,
        "values": [
            {
                "city": city,
                "series": [
                    None if pd.isna(pivot.at[city, m]) else round(float(pivot.at[city, m]), 1)
                    for m in months_ts
                ],
            }
            for city in cities
        ],
    }


def build_district_scenarios() -> dict:
    """Per-city district scenarios (北京 17 / 重庆 26) for the 2030 year-end."""
    frame = read("district_price_forecast_2026_2030.csv")
    result = {}
    for city in ("北京", "重庆"):
        city_frame = frame[frame["city"].eq(city)]
        base = city_frame[city_frame["year"].eq(2026)].set_index("district")["base_price_yuan_m2"]
        end = city_frame[city_frame["year"].eq(2030)].set_index("district")
        rows = []
        for district in base.index:
            rows.append(
                {
                    "district": district,
                    "base2026": int(round(float(base.at[district]))),
                    "base2030": int(round(float(end.at[district, "price_base_yuan_m2"]))),
                    "low2030": int(round(float(end.at[district, "price_low_yuan_m2"]))),
                    "high2030": int(round(float(end.at[district, "price_high_yuan_m2"]))),
                    "confidence": str(end.at[district, "confidence"]),
                }
            )
        rows.sort(key=lambda r: r["base2026"])
        result[city] = rows
    return result


def build_district_listing() -> dict:
    frame = read("creprice_beijing_district_prices.csv")
    frame["month"] = pd.to_datetime(frame["month"])
    months = sorted(frame["month"].dt.strftime("%Y-%m").unique())
    series = []
    for district, sub in frame.groupby("district"):
        sub = sub.set_index("month")["price_yuan_m2"]
        series.append(
            {
                "district": district,
                "series": [
                    round(float(sub.loc[pd.Timestamp(m)]), 0) if pd.Timestamp(m) in sub.index else None
                    for m in months
                ],
            }
        )
    series.sort(key=lambda s: next(v for v in reversed(s["series"]) if v is not None), reverse=True)
    return {"months": months, "districts": series}


def build_lpr() -> dict:
    frame = read("lpr_history.csv")
    frame["month"] = pd.to_datetime(frame["month"])
    frame = frame.sort_values("month")
    return [
        {
            "m": row.month.strftime("%Y-%m"),
            "lpr_1y": None if pd.isna(row.lpr_1y) else round(float(row.lpr_1y), 3),
            "lpr_5y": None if pd.isna(row.lpr_5y) else round(float(row.lpr_5y), 3),
        }
        for row in frame.itertuples()
    ]


def build_macro() -> dict:
    """National macro panel: YoY % series + inventory level, 2023-02 → 2026-06."""
    frame = read("macro_features_full.csv")
    frame["month"] = pd.to_datetime(frame["month"])
    frame = frame.sort_values("month")

    metrics = [
        ("development_investment_yoy", "房地产开发投资同比"),
        ("new_starts_area_yoy", "新开工面积同比"),
        ("completions_area_yoy", "竣工面积同比"),
        ("new_home_sales_area_yoy", "商品房销售面积同比"),
        ("new_home_sales_value_yoy", "商品房销售额同比"),
        ("inventory_area_yoy", "商品房待售面积同比"),
        ("developer_funding_yoy", "到位资金同比"),
    ]
    series = {
        field: [None if pd.isna(v) else round(float(v), 1) for v in frame[field]]
        for field, _ in metrics
    }
    months = [m.strftime("%Y-%m") for m in frame["month"]]
    inventory = [None if pd.isna(v) else round(float(v) / 10000.0, 2) for v in frame["inventory_area"]]
    return {
        "months": months,
        "metrics": [{"key": key, "label": label} for key, label in metrics],
        "series": series,
        "inventory_wan_m2": inventory,
    }


def build_market_compare() -> dict:
    """National monthly mean MoM index for new vs second-hand, for comparison."""
    frame = read("housing_indices_clean_v3.csv")
    frame["month"] = pd.to_datetime(frame["month"])
    months = []
    new, secondhand = [], []
    for m, sub in frame.groupby("month"):
        months.append(m.strftime("%Y-%m"))
        def mean_for(mkt):
            vals = sub[sub["market"].eq(mkt)]["month_on_month"]
            return round(float(vals.mean()), 2) if len(vals) else None
        new.append(mean_for("new"))
        secondhand.append(mean_for("secondhand"))
    return {"months": months, "new": new, "secondhand": secondhand}


def build_official() -> dict:
    """Beijing official 2025-10 district second-hand signings."""
    frame = read("beijing_official_district_secondhand_2025_10.csv")
    frame = frame.sort_values("transaction_count", ascending=False)
    return {
        "month": "2025-10",
        "total_units": int(round(frame["transaction_count"].sum())),
        "districts": [
            {
                "district": row.district,
                "count": int(round(row.transaction_count)),
                "area_m2": round(float(row.transaction_area_m2), 0),
            }
            for row in frame.itertuples()
        ],
    }


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)

    bundles = {
        "meta.json": build_meta,
        "forecast_series.json": build_forecast,
        "components.json": build_components,
        "cities_yoy.json": build_cities,
        "district_scenarios.json": build_district_scenarios,
        "district_listing.json": build_district_listing,
        "lpr.json": build_lpr,
        "macro.json": build_macro,
        "market_compare.json": build_market_compare,
        "official.json": build_official,
    }

    for name, fn in bundles.items():
        payload = fn()
        (OUT / name).write_text(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        size = len(json.dumps(payload, ensure_ascii=False)) / 1024
        print(f"wrote site/data/{name}  ({size:.0f} KB)")


if __name__ == "__main__":
    main()
