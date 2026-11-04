"""Frozen forecast ledger: predictions are written once, scored later.

A backtest can never prove a forecast was made before the outcome was known --
model design choices leak.  The ledger fixes that going forward: every run of
``probabilistic_forecast`` freezes its full forecast under
``reports/forecast_ledger/<origin>.csv`` (tracked in git, never overwritten),
and ``score_ledger`` compares each frozen file with whatever has been published
since.  The first entry (origin 2026-09) will be scored when 2026-10 data lands.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

LEDGER_DIR = Path("reports/forecast_ledger")


def freeze(frame: pd.DataFrame, origin: str, directory: Path = LEDGER_DIR) -> tuple[Path, bool]:
    """Write the forecast for `origin` unless a frozen copy already exists."""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{origin}.csv"
    if path.exists():
        return path, False
    frame.to_csv(path, index=False)
    return path, True


def score_ledger(panel_path: str, directory: Path = LEDGER_DIR) -> list[dict]:
    """Score every frozen forecast against the months published after its origin."""
    panel = pd.read_csv(panel_path)
    panel = panel[panel["market"].eq("secondhand")]
    mom = panel.pivot_table(index="month", columns="city", values="month_on_month", aggfunc="first")
    last = mom.index.max()
    results = []
    for path in sorted(directory.glob("*.csv")):
        origin = path.stem
        ledger = pd.read_csv(path)
        future = [m for m in mom.index if m > origin]
        entry = {"origin": origin, "frozen_file": f"{LEDGER_DIR.as_posix()}/{path.name}", "latest_data": last, "months_scored": len(future), "scored": []}
        if future:
            actual = mom.loc[future] / 100.0
            city_cum = actual.cumprod() * 100.0
            nat_cum = (actual.mean(axis=1)).cumprod() * 100.0
            for h, month in enumerate(future, start=1):
                sub = ledger[ledger["h"].eq(h)].set_index("region")
                cities = [c for c in city_cum.columns if c in sub.index]
                inside = [(sub.at[c, "q100"] <= city_cum.at[month, c] <= sub.at[c, "q900"]) for c in cities]
                err = np.abs(np.log(city_cum.loc[month, cities].to_numpy() / sub.loc[cities, "q500"].to_numpy()))
                flat = np.abs(np.log(city_cum.loc[month, cities].to_numpy() / 100.0))
                nat = sub.loc["全国"]
                entry["scored"].append({
                    "h": h, "month": month,
                    "national": {"actual": round(float(nat_cum[month]), 2), "median": float(nat["q500"]),
                                 "lo80": float(nat["q100"]), "hi80": float(nat["q900"])},
                    "city_inside80": round(float(np.mean(inside)), 3),
                    "city_mae_pct_points": round(float(err.mean()) * 100, 3),
                    "flat_mae_pct_points": round(float(flat.mean()) * 100, 3),
                })
        results.append(entry)
    return results


if __name__ == "__main__":
    print(json.dumps(score_ledger("data/processed/housing_indices_clean_v4.csv"), ensure_ascii=False, indent=1))
