#!/usr/bin/env python3
"""Audit of the v0.2 five-year paper algorithm (src/five_year_forecast.py).

Reproduces the paper's headline numbers on the paper's own data vintage and then
measures, on the longer history now available, how the algorithm behaves:

  A. reproduction     headline cumulative changes, weights, AR(1) rho, half-lives
  B. selection        how many (overlapping) windows pick the weights, how clear the winner is,
                      and what changes if rho is estimated without the evaluation windows
  C. walk-forward     the paper's algorithm re-run at every origin 2016-06..2021-09 on the
                      2011+ national / Beijing series, scored at +12/24/36/60 months against
                      "no change" and a damped trend
  D. bands            coverage of the paper's low/high band in that walk-forward
  E. anchor           what the reversion anchor (sample mean) is, per data window

    .venv/bin/python scripts/paper_algorithm_audit.py [--output reports/paper_algorithm_audit.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.five_year_forecast import (  # noqa: E402
    _component_forecasts,
    _monthly_index,
    estimate_reversion,
    forecast_explainable,
)
from src.panel import PANEL_PATH, REGIME_BREAK  # noqa: E402

PAPER_DATA = "data/processed/housing_indices_clean_v3.csv"   # the vintage the paper was written on
HORIZONS = (12, 24, 36, 60)


def cum(series_mom: np.ndarray) -> float:
    """Cumulative change in percent of a MoM index path."""
    return (float(np.prod(np.asarray(series_mom) / 100.0)) - 1.0) * 100.0


# ---------------------------------------------------------------- A / B
def reproduce(path: str, ar1_fix: bool = False) -> dict:
    out = {}
    for name, city in (("全国", None), ("北京", "北京")):
        s = _monthly_index(path, city)
        frame, meta = forecast_explainable(s, 60, ar1_fix=ar1_fix)
        out[name] = {
            "months": int(len(s)), "span": [str(s.index[0].date())[:7], str(s.index[-1].date())[:7]],
            "weights": meta["weights"], "rho": meta["rho"], "half_life_months": meta["half_life_months"],
            "base_cum_5y": round(cum(frame["monthly_index"]), 1),
            "low_cum_5y": round(cum(frame["monthly_index_low"]), 1), "high_cum_5y": round(cum(frame["monthly_index_high"]), 1),
            "trailing12_mean_mom": round(float(s.iloc[-12:].mean()), 3), "sample_mean_mom": round(float(s.mean()), 3),
            "trend_only_5y": round(cum(np.full(60, s.iloc[-12:].mean())), 1),
        }
    return out


def selection_diagnostics(path: str) -> dict:
    """Replicates _grid_search_weights to expose its sample: windows, MAE table, margin, rho sensitivity."""
    out = {}
    for name, city in (("全国", None), ("北京", "北京")):
        s = _monthly_index(path, city)
        vals, idx = s.to_numpy(float), s.index
        horizon, train_end = 12, int(len(vals) * 0.75)
        cutoffs = list(range(36, train_end - horizon + 1, 3))

        def table(rho: float) -> list:
            rows = []
            for w1 in np.arange(0.0, 1.0001, 0.25):
                for w2 in np.arange(0.0, 1.0001 - w1 + 1e-9, 0.25):
                    w3 = 1.0 - w1 - w2
                    errs = []
                    for c in cutoffs:
                        t, r, se = _component_forecasts(pd.Series(vals[:c], index=idx[:c]), horizon, rho)
                        errs.extend(np.abs(w1 * t + w2 * r + w3 * se - vals[c:c + horizon]).tolist())
                    rows.append(((round(w1, 2), round(w2, 2), round(w3, 2)), float(np.mean(errs))))
            return sorted(rows, key=lambda x: x[1])

        rho_full = estimate_reversion(s)["rho"]
        rho_train = estimate_reversion(s.iloc[:train_end])["rho"]
        t_full, t_train = table(rho_full), table(rho_train)
        # windows are 12 months long every 3 months: how many independent 12-month blocks is that?
        first, last = idx[cutoffs[0]], idx[cutoffs[-1] + horizon - 1]
        out[name] = {
            "n_windows": len(cutoffs), "window_span": [str(first.date())[:7], str(last.date())[:7]],
            "independent_12m_blocks": round((cutoffs[-1] + horizon - cutoffs[0]) / 12, 1),
            "best": t_full[0][0], "best_mae": round(t_full[0][1], 4), "second": t_full[1][0], "second_mae": round(t_full[1][1], 4),
            "margin_pct": round((t_full[1][1] / t_full[0][1] - 1) * 100, 1),
            "top5": [(w, round(m, 4)) for w, m in t_full[:5]],
            "rho_full": rho_full, "rho_train_only": rho_train, "best_with_train_only_rho": t_train[0][0],
            "weights_change_with_train_only_rho": t_full[0][0] != t_train[0][0],
            "trend_only_mae": round(next(m for w, m in t_full if w == (1.0, 0.0, 0.0)), 4),
            "mae_unit": "index points of the monthly MoM index (100 = flat)",
        }
    return out


def headline_by_frac(path: str, fracs=(0.55, 0.6, 0.7, 0.75, 0.8, 0.9)) -> dict:
    """The paper's weight-sensitivity table lists weights only.  Re-run it and add what the weights do to the
    headline five-year number (selection function patched to take the training fraction)."""
    import src.five_year_forecast as ff

    original = ff._grid_search_weights
    out = {}
    try:
        for name, city in (("全国", None), ("北京", "北京")):
            s = _monthly_index(path, city)
            rows = []
            for frac in fracs:
                def select(series, horizon, rho, frac=frac):
                    vals, idx = series.to_numpy(float), series.index
                    train_end = int(len(vals) * frac)
                    best = None
                    for w1 in np.arange(0.0, 1.0001, 0.25):
                        for w2 in np.arange(0.0, 1.0001 - w1 + 1e-9, 0.25):
                            w3 = 1.0 - w1 - w2
                            errs = []
                            for cutoff in range(36, train_end - horizon + 1, 3):
                                t, r, se = _component_forecasts(pd.Series(vals[:cutoff], index=idx[:cutoff]), horizon, rho)
                                errs.extend(np.abs(w1 * t + w2 * r + w3 * se - vals[cutoff:cutoff + horizon]).tolist())
                            if errs and (best is None or np.mean(errs) < best[0]):
                                best = (float(np.mean(errs)), np.asarray([w1, w2, w3]))
                    return (best[1] if best else np.asarray([1.0, 0.0, 0.0])), (best[0] if best else float("inf"))
                ff._grid_search_weights = select
                frame, meta = forecast_explainable(s, 60)
                rows.append({"frac": frac, "weights": [meta["weights"]["trend"], meta["weights"]["mean_reversion"], meta["weights"]["seasonality"]],
                             "base_cum_5y": round(cum(frame["monthly_index"]), 1)})
            out[name] = rows
    finally:
        ff._grid_search_weights = original
    return out


# ---------------------------------------------------------------- C / D
def damped_path(hist: np.ndarray, horizon: int, phi: float = 0.96, half_life: float = 2.0) -> np.ndarray:
    """MoM path (index points) of an EWMA level decaying by phi per month, on the log scale."""
    r = np.log(hist / 100.0)
    w = 0.5 ** (np.arange(min(len(r), 24))[::-1] / half_life)
    level = float(np.sum(w * r[-len(w):]) / w.sum())
    return 100.0 * np.exp(level * phi ** np.arange(1, horizon + 1))


def walk_forward(series: pd.Series, first_origin: str = "2016-06", last_origin: str = "2021-09", step: int = 3) -> dict:
    vals, idx = series.to_numpy(float), series.index
    labels = [str(d.date())[:7] for d in idx]
    origins = [i for i, m in enumerate(labels) if first_origin <= m <= last_origin and (i - first_origin_pos(labels, first_origin)) % step == 0]
    rows = {h: {"paper": [], "flat": [], "damped": [], "actual": []} for h in HORIZONS}
    inside = {h: [] for h in HORIZONS}
    detail = []
    for o in origins:
        hist = series.iloc[: o + 1]
        frame, meta = forecast_explainable(hist, 60)
        paper = frame["monthly_index"].to_numpy()
        low, high = frame["monthly_index_low"].to_numpy(), frame["monthly_index_high"].to_numpy()
        dmp = damped_path(vals[: o + 1], 60)
        rec = {"origin": labels[o], "weights": meta["weights"]}
        for h in HORIZONS:
            if o + h >= len(vals):
                continue
            a = cum(vals[o + 1: o + 1 + h])
            p, f, d = cum(paper[:h]), 0.0, cum(dmp[:h])
            rows[h]["paper"].append(abs(p - a)); rows[h]["flat"].append(abs(f - a)); rows[h]["damped"].append(abs(d - a)); rows[h]["actual"].append(a)
            inside[h].append(cum(low[:h]) <= a <= cum(high[:h]))
            rec[f"p{h}"], rec[f"a{h}"] = round(p, 1), round(a, 1)
        detail.append(rec)
    summary = {}
    for h in HORIZONS:
        n = len(rows[h]["paper"])
        if not n:
            continue
        mae = {k: round(float(np.mean(v)), 2) for k, v in rows[h].items() if k != "actual"}
        summary[h] = {"n_origins": n, "mae_pct_points": mae, "paper_vs_flat": round(1 - mae["paper"] / mae["flat"], 3),
                      "damped_vs_flat": round(1 - mae["damped"] / mae["flat"], 3), "band_coverage": round(float(np.mean(inside[h])), 3)}
    return {"origins": [labels[o] for o in origins], "summary": summary, "detail": detail}


def first_origin_pos(labels: list, first: str) -> int:
    return next(i for i, m in enumerate(labels) if m >= first)


# ---------------------------------------------------------------- F
def compare_with_new_model(panel_path: str, records_path: str, first: str = "2019-01",
                           tsfm_path: str | None = None) -> dict:
    """Paper algorithm vs the current ensemble on identical origins (2019-01 on; the ensemble needs a
    realised past to learn weights, so earlier origins are not comparable)."""
    from src import probabilistic_forecast as pf

    cache = Path(records_path)
    key = pf.records_cache_key(Path(panel_path), Path(tsfm_path) if tsfm_path else None,
                               60, REGIME_BREAK, "2016-01", 3)
    rec = pf.read_records_cache(cache, key)
    if rec is None:
        raise ValueError("forecast cache is missing, stale, or lacks provenance; rebuild it with matching inputs")
    origins = [o for o in rec if o >= first]
    frame = pd.read_csv(panel_path)
    frame = frame[(frame["month"] >= REGIME_BREAK) & frame["market"].eq("secondhand")]
    nat = frame.groupby("month")["month_on_month"].mean()
    bj = frame[frame["city"].eq("北京")].set_index("month")["month_on_month"]
    cities = list(pd.read_csv(ROOT / "data/processed/city_returns_secondhand.csv", index_col=0, nrows=1).columns)
    out = {}
    for name, ser in (("全国", nat), ("北京", bj)):
        series = pd.Series(ser.to_numpy(float), index=pd.to_datetime(ser.index + "-01"))
        labels = list(ser.index)
        rows = {h: {"paper": [], "new": [], "flat": []} for h in HORIZONS}
        for o in origins:
            i = labels.index(o)
            paper = forecast_explainable(series.iloc[: i + 1], 60)[0]["monthly_index"].to_numpy()
            weights, *_ = pf.learn_at(rec, list(rec), o, 60)
            ens = pf.ensemble_path(rec[o]["paths"], weights)
            new = np.exp(pf.national_path(ens)) if name == "全国" else np.exp(ens[cities.index("北京")])
            for h in HORIZONS:
                if i + h >= len(labels):
                    continue
                a = cum(ser.to_numpy(float)[i + 1: i + 1 + h])
                rows[h]["paper"].append(abs(cum(paper[:h]) - a))
                rows[h]["new"].append(abs((new[h - 1] - 1.0) * 100.0 - a))
                rows[h]["flat"].append(abs(a))
        out[name] = {h: {"n_origins": len(v["paper"]), **{k: round(float(np.mean(x)), 2) for k, x in v.items()}} for h, v in rows.items() if v["paper"]}
    return out


# ---------------------------------------------------------------- E
def anchor_by_window(panel_path: str) -> dict:
    frame = pd.read_csv(panel_path)
    sh = frame[frame["market"].eq("secondhand")]
    out = {}
    for label, start in (("2019-01（论文窗口）", "2019-01"), ("2011-02（现行口径起点）", REGIME_BREAK), ("2008-01（自洽起点）", "2008-01")):
        s = sh[sh["month"] >= start].groupby("month")["month_on_month"].mean()
        out[label] = {"months": int(len(s)), "mean_mom": round(float(s.mean()), 3), "annualised_pct": round((float(np.prod(s.to_numpy() / 100)) ** (12 / len(s)) - 1) * 100, 2)}
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--paper-data", default=PAPER_DATA)
    parser.add_argument("--panel", default=PANEL_PATH)
    parser.add_argument("--output", default="reports/paper_algorithm_audit.json")
    parser.add_argument("--cache-tsfm", default="", help="TSFM JSON used when building the forecast cache, if any")
    args = parser.parse_args()

    result = {"reproduction": reproduce(args.paper_data), "reproduction_ar1_fixed": reproduce(args.paper_data, ar1_fix=True), "selection": selection_diagnostics(args.paper_data),
              "headline_by_frac": headline_by_frac(args.paper_data)}
    panel = pd.read_csv(args.panel)
    panel = panel[(panel["month"] >= REGIME_BREAK) & panel["market"].eq("secondhand")]
    nat = panel.groupby("month")["month_on_month"].mean()
    bj = panel[panel["city"].eq("北京")].set_index("month")["month_on_month"]
    to_series = lambda s: pd.Series(s.to_numpy(float), index=pd.to_datetime(s.index + "-01"))
    result["walk_forward"] = {"全国": walk_forward(to_series(nat)), "北京": walk_forward(to_series(bj))}
    result["anchor"] = anchor_by_window(args.panel)
    records = ROOT / "data/processed/pf_records.pkl"
    if records.exists():
        result["vs_new_model"] = compare_with_new_model(args.panel, str(records), tsfm_path=args.cache_tsfm or None)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k != "walk_forward"}, ensure_ascii=False, indent=1))
    for name, tab in result.get("vs_new_model", {}).items():
        print(f"\n== paper vs new model, identical origins ({name}, MAE in percentage points of cumulative change)")
        for h, v in tab.items():
            print(f"  +{h:>2}: n={v['n_origins']:>2} paper {v['paper']:>6}  new {v['new']:>6}  flat {v['flat']:>6}")
    for name, wf in result["walk_forward"].items():
        print(f"\n== walk-forward {name}: origins {wf['origins'][0]} → {wf['origins'][-1]} ({len(wf['origins'])})")
        for h, s in wf["summary"].items():
            print(f"  +{h:>2}: n={s['n_origins']:>2} MAE paper {s['mae_pct_points']['paper']:>6} flat {s['mae_pct_points']['flat']:>6} damped {s['mae_pct_points']['damped']:>6} | paper vs flat {s['paper_vs_flat']:+.0%} damped vs flat {s['damped_vs_flat']:+.0%} | band coverage {s['band_coverage']:.0%}")


if __name__ == "__main__":
    main()
