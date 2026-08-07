"""Quality checks and canonicalization for the housing-index panel."""

from __future__ import annotations

import argparse
import os

import pandas as pd


CITY_ALIASES = {
    "襄樊": "襄阳",
    "呼和浩特": "呼和浩特",
}
NUMERIC_COLUMNS = ["month_on_month", "yoy", "year_avg"]


def clean_price_data(input_path: str, output_path: str) -> pd.DataFrame:
    data = pd.read_csv(input_path)
    required = {"month", "city", "market", *NUMERIC_COLUMNS, "methodology", "source_url"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"缺少字段: {sorted(missing)}")
    data["month"] = pd.to_datetime(data["month"], errors="coerce").dt.strftime("%Y-%m")
    data["city"] = data["city"].astype(str).str.replace(r"\s+", "", regex=True).replace(CITY_ALIASES)
    data["market"] = data["market"].replace({"new_house": "new", "second_hand": "secondhand"})
    for column in NUMERIC_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")
    data["methodology"] = data["methodology"].fillna("current")
    data = data.dropna(subset=["month", "city", "market", "month_on_month", "yoy"])
    data = data[data["market"].isin(["new", "secondhand"])]
    data = data[data["month_on_month"].between(70, 130) & data["yoy"].between(50, 200)]
    priority = {"current": 0, "current_cirea": 1, "legacy": 2}
    data["_priority"] = data["methodology"].map(priority).fillna(9)
    data = data.sort_values(["month", "city", "market", "_priority"])
    data = data.drop_duplicates(["month", "city", "market"], keep="first").drop(columns="_priority")
    data = data.sort_values(["month", "city", "market"]).reset_index(drop=True)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    data.to_csv(output_path, index=False)
    return data


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/processed/housing_indices_enriched.csv")
    parser.add_argument("--output", default="data/processed/housing_indices_clean.csv")
    args = parser.parse_args()
    result = clean_price_data(args.input, args.output)
    print(f"清洗后 {len(result)} 条记录")
