"""Model explanation using time-held-out permutation importance."""

from __future__ import annotations

import argparse
import json
import os
from typing import List

import pandas as pd
from sklearn.inspection import permutation_importance

from .evaluate import _linear_model, split_time_holdout
from .train import build_model, feature_columns, load_features


def permutation_importance_report(data, test_months: int = 1, n_repeats: int = 10) -> List[dict]:
    frame = data.copy() if isinstance(data, pd.DataFrame) else pd.read_csv(data)
    if "market" in frame.columns:
        # Raw price panel input needs feature construction before splitting.
        frame = load_features(data) if not isinstance(data, pd.DataFrame) else load_features_from_frame(frame)
    train, test = split_time_holdout(frame, test_months=test_months)
    target = "yoy_secondhand"
    numeric, categorical = feature_columns(train)
    features = numeric + categorical
    model = build_model(numeric, categorical)
    model.fit(train[features], train[target])
    result = permutation_importance(
        model, test[features], test[target], scoring="neg_mean_absolute_error",
        n_repeats=n_repeats, random_state=42,
    )
    rows = [
        {"feature": feature, "importance_mean": round(float(mean), 6), "importance_std": round(float(std), 6)}
        for feature, mean, std in zip(features, result.importances_mean, result.importances_std)
    ]
    return sorted(rows, key=lambda row: row["importance_mean"], reverse=True)


def load_features_from_frame(frame: pd.DataFrame) -> pd.DataFrame:
    """Persist-free feature construction for tests and in-memory callers."""
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".csv") as handle:
        frame.to_csv(handle.name, index=False)
        return load_features(handle.name)


def write_importance(data_path: str, output_path: str, test_months: int = 1, n_repeats: int = 10) -> List[dict]:
    rows = permutation_importance_report(data_path, test_months, n_repeats)
    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as handle:
        json.dump(rows, handle, ensure_ascii=False, indent=2)
    return rows


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default="data/processed/housing_indices_clean_v3.csv")
    parser.add_argument("--output", default="reports/permutation_importance_v3.json")
    parser.add_argument("--test-months", type=int, default=1)
    parser.add_argument("--repeats", type=int, default=10)
    args = parser.parse_args()
    print(json.dumps(write_importance(args.data, args.output, args.test_months, args.repeats), ensure_ascii=False, indent=2))
