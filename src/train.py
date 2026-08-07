"""Train a baseline model for second-hand housing price-index changes."""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import Pipeline
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import OneHotEncoder


TIER_1 = {"北京", "上海", "广州", "深圳"}
TIER_2 = {
    "天津", "重庆", "杭州", "南京", "武汉", "成都", "西安", "郑州", "济南",
    "青岛", "宁波", "厦门", "合肥", "福州", "长沙", "昆明", "沈阳", "大连",
    "哈尔滨", "长春", "南昌", "南宁", "贵阳", "太原", "石家庄", "兰州",
}


def add_temporal_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Add city-wise lag, first-difference and 3-period rolling features."""
    result = frame.copy()
    result["_month_sort"] = pd.to_datetime(result["month"])
    result = result.sort_values(["city", "_month_sort"]).drop(columns="_month_sort").reset_index(drop=True)
    grouped = result.groupby("city", sort=False)
    source_columns = [
        "yoy_new", "month_on_month_new", "yoy_secondhand", "month_on_month_secondhand",
    ]
    for column in source_columns:
        lag = grouped[column].shift(1)
        result[f"{column}_lag1"] = lag
        result[f"{column}_delta1"] = result[column] - lag
        result[f"{column}_roll3"] = grouped[column].transform(lambda values: values.rolling(3, min_periods=1).mean())
    return result


def load_features(path: str, macro_path: Optional[str] = None) -> pd.DataFrame:
    raw = pd.read_csv(path)
    value_columns = ["month_on_month", "yoy", "year_avg"]
    wide = raw.pivot_table(index=["month", "city"], columns="market", values=value_columns)
    wide.columns = [f"{metric}_{market}" for metric, market in wide.columns]
    wide = wide.reset_index()
    wide["month_num"] = pd.to_datetime(wide["month"]).dt.month
    wide["month_sin"] = np.sin(2 * np.pi * wide["month_num"] / 12)
    wide["month_cos"] = np.cos(2 * np.pi * wide["month_num"] / 12)
    wide["city_tier"] = wide["city"].map(lambda city: 1 if city in TIER_1 else 2 if city in TIER_2 else 3)
    if macro_path:
        macro = pd.read_csv(macro_path)
        wide = wide.merge(macro, on="month", how="left", suffixes=("", "_macro"))
    wide = add_temporal_features(wide)
    return wide.dropna(subset=["yoy_secondhand"])


def feature_columns(data: pd.DataFrame) -> tuple[list[str], list[str]]:
    """Return one-step-ahead features only.

    Current-month secondhand values are excluded because they are unavailable
    when the forecast is made and can leak information about the target.
    """
    numeric = [
        "month_num", "month_sin", "month_cos", "city_tier",
        "yoy_new_lag1", "month_on_month_new_lag1",
        "yoy_secondhand_lag1", "month_on_month_secondhand_lag1",
    ]
    numeric = [column for column in numeric if column in data.columns and data[column].notna().any()]
    numeric.extend(column for column in (
        "lpr_1y", "lpr_5y", "development_investment_value", "development_investment_yoy",
        "housing_investment_value", "housing_investment_yoy", "construction_area", "construction_area_yoy",
        "new_starts_area", "new_starts_area_yoy", "completions_area", "completions_area_yoy",
        "new_home_sales_area", "new_home_sales_area_yoy", "new_home_sales_value", "new_home_sales_value_yoy",
        "inventory_area", "inventory_area_yoy", "developer_funding", "developer_funding_yoy",
    ) if column in data.columns and data[column].notna().any())
    return numeric, ["city"]


def build_model(numeric: list[str], categorical: list[str]) -> Pipeline:
    preprocess = ColumnTransformer(
        [
            ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
            ("numeric", SimpleImputer(strategy="median"), numeric),
        ],
    )
    return Pipeline([
        ("preprocess", preprocess),
        ("regressor", RandomForestRegressor(n_estimators=300, random_state=42, min_samples_leaf=2, n_jobs=-1)),
    ])


def train(data_path: str, model_path: str, metrics_path: str, macro_path: Optional[str] = None) -> dict:
    data = load_features(data_path, macro_path)
    target = "yoy_secondhand"
    numeric, categorical = feature_columns(data)
    features = numeric + categorical
    splitter = GroupShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
    train_idx, test_idx = next(splitter.split(data[features], data[target], groups=data["city"]))
    model = build_model(numeric, categorical)
    model.fit(data.iloc[train_idx][features], data.iloc[train_idx][target])
    predicted = model.predict(data.iloc[test_idx][features])
    metrics = {
        "rows": int(len(data)),
        "train_rows": int(len(train_idx)),
        "test_rows": int(len(test_idx)),
        "test_cities": int(data.iloc[test_idx]["city"].nunique()),
        "mae_index_points": round(float(mean_absolute_error(data.iloc[test_idx][target], predicted)), 4),
        "rmse_index_points": round(float(mean_squared_error(data.iloc[test_idx][target], predicted) ** 0.5), 4),
        "r2": round(float(r2_score(data.iloc[test_idx][target], predicted)), 4),
        "target": target,
        "features": features,
        "split": "GroupShuffleSplit by city, test_size=20%, random_state=42",
    }
    os.makedirs(os.path.dirname(model_path) or ".", exist_ok=True)
    os.makedirs(os.path.dirname(metrics_path) or ".", exist_ok=True)
    joblib.dump(model, model_path)
    with open(metrics_path, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
    return metrics


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/housing_indices.csv")
    parser.add_argument("--model", default="models/secondhand_yoy_random_forest.joblib")
    parser.add_argument("--metrics", default="reports/metrics.json")
    parser.add_argument("--macro", default="data/processed/macro_features.csv")
    args = parser.parse_args()
    macro_path = args.macro if os.path.exists(args.macro) else None
    print(json.dumps(train(args.data, args.model, args.metrics, macro_path), ensure_ascii=False, indent=2))
