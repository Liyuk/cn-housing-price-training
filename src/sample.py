"""Create reproducible, stratified samples for fast model experiments."""

from __future__ import annotations

import argparse
import os
from typing import Iterable, Optional

import pandas as pd


def sample_panel(data, cities: Optional[Iterable[str]] = None, markets: Optional[Iterable[str]] = None,
                 start_month: Optional[str] = None, end_month: Optional[str] = None,
                 max_cities: Optional[int] = None, random_state: int = 42) -> pd.DataFrame:
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    if "month" not in frame or "city" not in frame or "market" not in frame:
        raise ValueError("sample panel requires month, city and market columns")
    frame["month"] = pd.to_datetime(frame["month"], errors="coerce").dt.strftime("%Y-%m")
    if start_month:
        frame = frame[frame["month"] >= start_month]
    if end_month:
        frame = frame[frame["month"] <= end_month]
    if cities is not None:
        frame = frame[frame["city"].isin(list(cities))]
    elif max_cities is not None:
        available = sorted(frame["city"].dropna().unique())
        if len(available) > max_cities:
            selected = pd.Series(available).sample(n=max_cities, random_state=random_state).sort_values().tolist()
            frame = frame[frame["city"].isin(selected)]
    if markets is not None:
        frame = frame[frame["market"].isin(list(markets))]
    return frame.sort_values(["month", "city", "market"]).reset_index(drop=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/housing_indices_clean_v2.csv")
    parser.add_argument("--output", default="data/samples/housing_panel_sample.csv")
    parser.add_argument("--cities", nargs="*", default=["北京", "上海", "重庆", "深圳"])
    parser.add_argument("--markets", nargs="*", default=["new", "secondhand"])
    parser.add_argument("--start-month", default="2019-01")
    parser.add_argument("--end-month", default="2026-06")
    args = parser.parse_args()
    result = sample_panel(args.input, args.cities, args.markets, args.start_month, args.end_month)
    os.makedirs(os.path.dirname(args.output) or ".", exist_ok=True)
    result.to_csv(args.output, index=False)
    print(f"写入 {len(result)} 条样本到 {args.output}")
