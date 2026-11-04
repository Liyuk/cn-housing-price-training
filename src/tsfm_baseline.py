"""Zero-shot time-series foundation model (Chronos-2) forecasts of city returns.

Optional add-on to ``probabilistic_forecast``.  Chronos-2 (Ansari et al. 2025)
is pretrained on large collections of unrelated series and forecasts a new
series with no training on housing data.  It needs torch and the
``chronos-forecasting`` package, so it runs in its own environment and hands
its output to the main pipeline as a JSON file -- the main pipeline stays
dependency-light and simply skips the model when the file is absent:

    .venv/bin/python -m src.probabilistic_forecast --export-returns
    python3 -m venv /tmp/tsfm
    /tmp/tsfm/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu
    /tmp/tsfm/bin/pip install "chronos-forecasting>=2.0" pandas numpy
    /tmp/tsfm/bin/python src/tsfm_baseline.py
    .venv/bin/python -m src.probabilistic_forecast --tsfm data/processed/chronos2_paths.json

Each origin is forecast using only returns up to that month (context = the
last 96 months of log month-on-month changes, per city, univariate), so the
output is a valid walk-forward input.  Values are cumulative log changes over
horizons 1..12, the median of the predictive distribution.
"""

from __future__ import annotations

import argparse
import json
import time

import numpy as np
import pandas as pd

HORIZON = 12  # default; --horizon 36 extends the foundation model to the full forecast span
CONTEXT = 96


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--returns", default="data/processed/city_returns_secondhand.csv")
    parser.add_argument("--output", default="data/processed/chronos2_paths.json")
    parser.add_argument("--first-origin", default="2016-01")
    parser.add_argument("--step", type=int, default=3)
    parser.add_argument("--extra", nargs="*", default=[], help="additional origins (YYYY-MM); the last data month is always included")
    parser.add_argument("--model", default="amazon/chronos-2")
    parser.add_argument("--horizon", type=int, default=HORIZON)
    args = parser.parse_args()

    from chronos import Chronos2Pipeline  # imported late: heavy, optional dependency

    returns = pd.read_csv(args.returns, index_col=0)
    months = list(returns.index)
    origins = sorted(set(months[months.index(args.first_origin):-1:args.step] + [months[-1]] + args.extra))
    pipeline = Chronos2Pipeline.from_pretrained(args.model, device_map="cpu")
    result: dict[str, dict[str, list[float]]] = {}
    started = time.time()
    for origin in origins:
        history = returns.loc[:origin].iloc[-CONTEXT:]
        long = history.reset_index(names="month").melt(id_vars="month", var_name="id", value_name="target")
        long["timestamp"] = pd.PeriodIndex(long["month"], freq="M").to_timestamp()
        out = pipeline.predict_df(long[["id", "timestamp", "target"]], prediction_length=args.horizon,
                                  quantile_levels=[0.5], id_column="id", timestamp_column="timestamp", target="target")
        out = out.sort_values(["id", "timestamp"])
        result[origin] = {city: np.cumsum(g["0.5"].to_numpy()).round(6).tolist() for city, g in out.groupby("id")}
        print(f"{origin}  {time.time() - started:.0f}s", flush=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        json.dump({"model": args.model, "context": CONTEXT, "horizon": args.horizon, "origins": result}, handle)


if __name__ == "__main__":
    main()
