"""Compare simple regressors with a time-based holdout."""

from __future__ import annotations

import argparse
import json
import os
from typing import Optional

import pandas as pd
from sklearn.dummy import DummyRegressor
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline

from .train import build_model, feature_columns, load_features


def split_time_holdout(data: pd.DataFrame, test_months: int = 1):
    ordered = data.assign(_month=pd.to_datetime(data["month"])).sort_values("_month")
    cutoff = ordered["_month"].drop_duplicates().iloc[-test_months]
    return ordered[ordered["_month"] < cutoff].drop(columns="_month"), ordered[ordered["_month"] >= cutoff].drop(columns="_month")


def _linear_model(numeric: list[str], categorical: list[str]) -> Pipeline:
    from sklearn.compose import ColumnTransformer
    from sklearn.impute import SimpleImputer
    from sklearn.preprocessing import OneHotEncoder

    preprocess = ColumnTransformer([
        ("categorical", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("numeric", SimpleImputer(strategy="median"), numeric),
    ])
    return Pipeline([( "preprocess", preprocess), ("regressor", Ridge(alpha=10.0))])


def evaluate(data_path: str, output_path: str, macro_path: Optional[str] = None) -> dict:
    data = load_features(data_path, macro_path)
    train, test = split_time_holdout(data, test_months=1)
    target = "yoy_secondhand"
    numeric, categorical = feature_columns(train)
    features = numeric + categorical
    models = {
        "mean_baseline": DummyRegressor(strategy="mean"),
        "ridge": _linear_model(numeric, categorical),
        "random_forest": build_model(numeric, categorical),
    }
    results = {}
    for name, model in models.items():
        model.fit(train[features], train[target])
        prediction = model.predict(test[features])
        results[name] = {
            "mae": round(float(mean_absolute_error(test[target], prediction)), 4),
            "rmse": round(float(mean_squared_error(test[target], prediction) ** 0.5), 4),
            "r2": round(float(r2_score(test[target], prediction)), 4),
        }
    result = {"train_rows": len(train), "test_rows": len(test), "test_month": str(test["month"].max()), "models": results}
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(result, handle, ensure_ascii=False, indent=2)
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/housing_indices_clean.csv")
    parser.add_argument("--output", default="reports/model_comparison.json")
    parser.add_argument("--macro", default=None)
    args = parser.parse_args()
    print(json.dumps(evaluate(args.data, args.output, args.macro), ensure_ascii=False, indent=2))
