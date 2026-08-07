"""Automated completeness and quality checks for the housing price panel."""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

import pandas as pd


def audit_price_panel(data, start_month: Optional[str] = None, end_month: Optional[str] = None, expected_cities: int = 70) -> dict:
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    required = {"month", "city", "market"}
    missing_columns = sorted(required.difference(frame.columns))
    if missing_columns:
        raise ValueError("missing required columns: " + ", ".join(missing_columns))
    frame["month"] = pd.to_datetime(frame["month"], errors="coerce").dt.strftime("%Y-%m")
    frame = frame.dropna(subset=["month", "city", "market"])
    key = ["month", "city", "market"]
    observed_months = sorted(frame["month"].unique())
    if start_month is None:
        start_month = observed_months[0] if observed_months else None
    if end_month is None:
        end_month = observed_months[-1] if observed_months else None
    expected_months = []
    if start_month and end_month:
        expected_months = pd.period_range(start_month, end_month, freq="M").astype(str).tolist()
    market_summary = {}
    for market, subset in frame.groupby("market"):
        market_months = sorted(subset["month"].unique())
        market_summary[market] = {
            "rows": int(len(subset)),
            "cities": int(subset["city"].nunique()),
            "months": len(market_months),
            "min_month": market_months[0] if market_months else None,
            "max_month": market_months[-1] if market_months else None,
            "missing_months": sorted(set(expected_months) - set(market_months)),
        }
    numeric_nulls = {column: int(value) for column, value in frame.isna().sum().items() if value}
    return {
        "rows": int(len(frame)),
        "cities": int(frame["city"].nunique()),
        "markets": sorted(frame["market"].unique().tolist()),
        "min_month": observed_months[0] if observed_months else None,
        "max_month": observed_months[-1] if observed_months else None,
        "observed_months": len(observed_months),
        "expected_months": len(expected_months),
        "missing_months": sorted(set(expected_months) - set(observed_months)),
        "duplicate_keys": int(frame.duplicated(key).sum()),
        "nulls": numeric_nulls,
        "expected_cities": expected_cities,
        "city_coverage": round(frame["city"].nunique() / expected_cities, 4) if expected_cities else None,
        "market_summary": market_summary,
    }


def write_audit(data_path: str, output_path: str, start_month: Optional[str] = None, end_month: Optional[str] = None) -> dict:
    result = audit_price_panel(data_path, start_month=start_month, end_month=end_month)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/housing_indices_clean_v2.csv")
    parser.add_argument("--output", default="reports/data_quality_v2.json")
    parser.add_argument("--start-month")
    parser.add_argument("--end-month")
    args = parser.parse_args()
    print(json.dumps(write_audit(args.data, args.output, args.start_month, args.end_month), ensure_ascii=False, indent=2))
