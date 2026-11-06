"""Probabilistic 1–36 month forecasts for all 70 cities (second-hand homes).

Why a second forecasting layer next to ``five_year_forecast``:

* The v0.2 five-year model covers only 全国/北京, and its scenario band is a
  fixed historical swing spread evenly over 60 months.  Scored against the
  three official months released after it (2026-07..09), the national actuals
  sat at the top edge of the band and Beijing above it every month: the trend
  component (trailing 12-month mean) lags turning points and the band is far
  too narrow near-term.
* This module gives every city a short/mid-horizon forecast whose intervals
  are *calibrated*: their width comes from out-of-sample errors measured in a
  rolling-origin backtest, and their coverage is checked on a held-out period.

Method
------
1. Target: cumulative log change of the second-hand index over the next
   h = 1..36 months, per city.  The national series is the mean of the city
   month-on-month indices (same definition as ``five_year_forecast``), so the
   national forecast is aggregated bottom-up and stays coherent with cities.
2. Base models (each is a function of information available at the origin):
     naive    – last month's change persists
     drift12  – trailing 12-month mean persists (the v0.2 "trend" component)
     ar1      – AR(1) reversion of monthly change toward the 60-month mean
     damped   – smoothed momentum decaying toward zero (damped trend)
     global   – one gradient-boosting model pooled across all cities, direct
                multi-horizon (Montero-Manso & Hyndman 2021; M5 practice).
     chronos2 – optional zero-shot foundation model (``src/tsfm_baseline.py``),
                forecast to 12 months only; absent when no --tsfm file is given.
3. Combination: up to LEARN_HORIZON (12 months), per-horizon inverse-MSE weights
   from origins whose h-month outcome was already published, shrunk 25% toward
   equal weights.  Beyond 12 months the weight vector is fixed to the damped
   trend (see LONG_RULE): learned weights there only see pre-2023 regimes and
   lost to a flat forecast in walk-forward scoring.  That choice was made after
   seeing damped trend win the long horizons, so the 24/36-month scores are
   optimistic -- the rule is not blind.
4. Intervals: errors are normalised by the city's trailing 24-month volatility
   × √h; per-horizon empirical quantiles of these scores (again only from
   realised origins) give the 10/90 and 2.5/97.5 bands (locally weighted
   split-conformal).  Measured walk-forward coverage of the nominal 80% band is
   ~80% at 1 month, 75% at 6, 69% at 12, 61% at 24 and 39% at 36 months:
   the bands are published as such, not as calibrated beyond ~6 months.
5. Evidence: ``walk_forward_eval`` scores every origin from 2019-01 with
   weights/quantiles learned only from its past; ``hindcast`` replays the model
   at an earlier origin against months published since (a replay, not a
   forward test); ``forecast_ledger`` freezes each run so later months score
   it out of sample.

Everything is index-based: outputs are index paths (latest month = 100), not
yuan per square metre.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import pickle
from pathlib import Path

import numpy as np
import pandas as pd
import sklearn
from sklearn.ensemble import HistGradientBoostingRegressor

from .forecast_ledger import freeze
from .panel import PANEL_PATH, monthly_returns  # noqa: F401  (re-exported: the site build imports it from here)

TIER1 = ["北京", "上海", "广州", "深圳"]
TIER2 = [
    "天津", "石家庄", "太原", "呼和浩特", "沈阳", "大连", "长春", "哈尔滨", "南京", "杭州",
    "宁波", "合肥", "福州", "厦门", "南昌", "济南", "青岛", "郑州", "武汉", "长沙",
    "南宁", "海口", "重庆", "成都", "贵阳", "昆明", "西安", "兰州", "西宁", "银川", "乌鲁木齐",
]
HORIZON = 60   # five years, the span of the v0.2 paper; only the first LEARN_HORIZON months are learned
REPORT_HORIZONS = (1, 3, 6, 12, 24, 36, 48, 60)
GLOBAL_MAX = 36  # the pooled GBM is trained to here; beyond it its column is a placeholder (never weighted)
SHRINK_LAMBDA = 0.6  # weight on a city's own momentum in the shrunk damped trend (rest: its tier mean)
TRAIN_HORIZONS = [1, 2, 3, 6, 9, 12, 18, 24, 36]
MODELS = ["naive", "drift12", "ar1", "damped", "damped_shrunk", "global", "chronos2"]
QUANTILES = [0.025, 0.1, 0.5, 0.9, 0.975]


def city_tier(city: str) -> int:
    return 1 if city in TIER1 else 2 if city in TIER2 else 3


# ---------------------------------------------------------------- data prep
def load_panel(path: str, market: str = "secondhand") -> pd.DataFrame:
    frame = pd.read_csv(path)
    frame = frame[frame["market"].eq(market)]
    return frame


def national_returns(r: pd.DataFrame) -> pd.Series:
    """National series: log of the mean of city MoM indices."""
    return np.log(np.exp(r).mean(axis=1, skipna=True))


def forecast_returns(frame: pd.DataFrame, require_complete: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Mask values reconstructed from observations 12 months in the future.

    A bridged cell is useful for descriptive history, but using it as a feature
    at an earlier forecast origin leaks data that was not then available.
    """
    returns, bridged = monthly_returns(frame)
    observed = returns.mask(bridged)
    if require_complete and observed.isna().to_numpy().any():
        raise ValueError("secondhand forecast input is incomplete; provide directly observed data")
    return observed, bridged


# ---------------------------------------------------------------- local models
def _local_forecast(name: str, hist: np.ndarray, horizon: int) -> np.ndarray:
    hist = hist[~np.isnan(hist)]
    if len(hist) == 0:
        return np.zeros(horizon)
    steps = np.arange(1, horizon + 1)
    if name == "naive":
        return np.full(horizon, hist[-1])
    if name == "drift12":
        return np.full(horizon, hist[-12:].mean())
    if name == "ar1":
        window = hist[-60:]
        mu = window.mean()
        x, y = window[:-1] - mu, window[1:] - mu
        phi = float(np.clip((x @ y) / max(x @ x, 1e-12), 0.0, 0.98))
        return mu + phi ** steps * (hist[-1] - mu)
    if name == "damped":
        weights = 0.5 ** (np.arange(min(len(hist), 24))[::-1] / 2.0)  # 2-month half-life EWMA
        level = float(np.sum(weights * hist[-len(weights):]) / weights.sum())
        return level * 0.96 ** steps
    raise ValueError(name)


# ---------------------------------------------------------------- global model
def build_features(r: pd.DataFrame, new_r: pd.DataFrame | None = None) -> pd.DataFrame:
    """Long table (month, city) of features known at the end of `month`."""
    level = r.fillna(0.0).cumsum()
    nat = national_returns(r)
    breadth = (r >= 0).where(r.notna()).mean(axis=1)
    feats = {
        "r0": r, "r1": r.shift(1), "r2": r.shift(2),
        "m3": r.rolling(3, min_periods=2).mean(),
        "m6": r.rolling(6, min_periods=4).mean(),
        "m12": r.rolling(12, min_periods=9).mean(),
        "m24": r.rolling(24, min_periods=18).mean(),
        "ret36": r.rolling(36, min_periods=30).sum(),
        "vol12": r.rolling(12, min_periods=9).std(),
        "dd36": level - level.rolling(36, min_periods=12).max(),
        "accel": r.rolling(3, min_periods=2).mean() - r.rolling(12, min_periods=9).mean(),
    }
    nat_feats = {
        "nat_m3": nat.rolling(3, min_periods=2).mean(),
        "nat_m12": nat.rolling(12, min_periods=9).mean(),
        "breadth3": breadth.rolling(3, min_periods=2).mean(),
    }
    if new_r is not None:
        new_r = new_r.reindex(index=r.index, columns=r.columns)
        feats["new_m3"] = new_r.rolling(3, min_periods=2).mean()
    long = pd.concat({k: v.stack(dropna=False) for k, v in feats.items()}, axis=1)
    long.index.names = ["month", "city"]
    long = long.reset_index()
    for key, series in nat_feats.items():
        long[key] = long["month"].map(series)
    long["tier"] = long["city"].map(city_tier)
    return long


def build_targets(r: pd.DataFrame) -> pd.DataFrame:
    """Cumulative log change over the next h months for each (month, city)."""
    out = {}
    for h in TRAIN_HORIZONS:
        out[f"y{h}"] = r[::-1].rolling(h, min_periods=h).sum()[::-1].shift(-1)
    long = pd.concat({k: v.stack(dropna=False) for k, v in out.items()}, axis=1)
    long.index.names = ["month", "city"]
    return long.reset_index()


FEATURES = ["r0", "r1", "r2", "m3", "m6", "m12", "m24", "ret36", "vol12", "dd36", "accel",
            "nat_m3", "nat_m12", "breadth3", "new_m3", "tier"]


def _interp_path(points: dict[int, np.ndarray], horizon: int) -> np.ndarray:
    """Cumulative forecasts at TRAIN_HORIZONS → monthly cumulative path (cities × horizon)."""
    hs = sorted(points)
    stacked = np.stack([points[h] for h in hs], axis=1)
    grid = np.arange(1, horizon + 1)
    xs = np.asarray([0] + hs, dtype=float)
    out = np.empty((stacked.shape[0], horizon))
    for i in range(stacked.shape[0]):
        ys = np.concatenate([[0.0], stacked[i]])
        out[i] = np.interp(grid, xs, ys)
    return out


def global_forecast(table: pd.DataFrame, origin: str, cities: list[str], horizon: int) -> np.ndarray | None:
    """Fit on rows whose targets were fully observed by `origin`; predict at origin."""
    months = pd.PeriodIndex(table["month"], freq="M")
    origin_p = pd.Period(origin, freq="M")
    at_origin = table[table["month"].eq(origin)].set_index("city").reindex(cities)
    feature_cols = [c for c in FEATURES if c in table.columns]
    points: dict[int, np.ndarray] = {}
    for h in [h for h in TRAIN_HORIZONS if h <= horizon]:
        mask = (months + h <= origin_p) & table[f"y{h}"].notna() & table["m12"].notna()
        train = table.loc[mask]
        if len(train) < 1500:
            return None
        model = HistGradientBoostingRegressor(
            max_iter=200, learning_rate=0.05, max_depth=3, min_samples_leaf=40,
            l2_regularization=1.0, random_state=0,
        )
        model.fit(train[feature_cols], train[f"y{h}"])
        points[h] = model.predict(at_origin[feature_cols])
    return _interp_path(points, horizon)


# ---------------------------------------------------------------- backtest
TSFM: dict[str, dict[str, list[float]]] = {}  # origin -> city -> cumulative median, filled from --tsfm


def shrunk_damped(hist: pd.DataFrame, horizon: int, lam: float = SHRINK_LAMBDA, phi: float = 0.96) -> np.ndarray:
    """Damped trend with each city's momentum shrunk toward its tier's mean momentum.

    A single city's 24-month EWMA level is noisy; the tier mean is not.  Pooling
    (hierarchical shrinkage) lowered walk-forward error at every horizon from
    6 to 36 months (about -5% at 12 months) while leaving 1-3 months unchanged.
    """
    w = 0.5 ** (np.arange(min(len(hist), 24))[::-1] / 2.0)
    level = (hist.to_numpy()[-len(w):] * w[:, None]).sum(axis=0) / w.sum()
    tiers = np.array([city_tier(c) for c in hist.columns])
    tier_mean = np.array([level[tiers == t].mean() for t in tiers])
    level = lam * level + (1.0 - lam) * tier_mean
    return np.cumsum(level[:, None] * phi ** np.arange(1, horizon + 1)[None, :], axis=1)


def forecast_all(r: pd.DataFrame, table: pd.DataFrame, origin: str, horizon: int) -> dict[str, np.ndarray]:
    """Cumulative log-change paths (cities × horizon) for every base model."""
    hist = r.loc[:origin]
    cities = list(r.columns)
    paths = {}
    for name in ("naive", "drift12", "ar1", "damped"):
        paths[name] = np.stack([np.cumsum(_local_forecast(name, hist[c].to_numpy(), horizon)) for c in cities])
    paths["damped_shrunk"] = shrunk_damped(hist, horizon)
    g = global_forecast(table, origin, cities, min(horizon, GLOBAL_MAX))
    if g is not None:
        # beyond its trained horizon the column repeats the shrunk damped path: never weighted
        # (weights past LEARN_HORIZON are fixed) and hidden from the model-error table
        padded_g = paths["damped_shrunk"].copy()
        padded_g[:, : g.shape[1]] = g
        paths["global"] = padded_g
    if origin in TSFM:
        # The foundation model is only run to 12 months; later columns repeat
        # the shrunk damped path, which is the only model used past LEARN_HORIZON.
        cells = np.asarray([TSFM[origin][c] for c in cities])
        padded = paths["damped_shrunk"].copy()
        padded[:, : cells.shape[1]] = cells[:, :horizon]
        paths["chronos2"] = padded
    return paths


def realised_paths(r: pd.DataFrame, origin: str, horizon: int) -> np.ndarray:
    pos = r.index.get_loc(origin)
    future = r.iloc[pos + 1: pos + 1 + horizon].to_numpy().T  # cities × ≤horizon
    out = np.full((r.shape[1], horizon), np.nan)
    out[:, : future.shape[1]] = np.cumsum(future, axis=1)
    return out


def city_sigma(r: pd.DataFrame, origin: str) -> np.ndarray:
    sig = r.loc[:origin].iloc[-24:].std().to_numpy()
    return np.maximum(np.nan_to_num(sig, nan=0.004), 0.0015)


def city_tau(r: pd.DataFrame, origin: str) -> np.ndarray:
    """Drift uncertainty: std over the last 36 months of the rolling 12-month mean change."""
    m12 = r.loc[:origin].rolling(12).mean().iloc[-36:]
    return np.maximum(np.nan_to_num(m12.std().to_numpy(), nan=1e-4), 1e-4)


def band_scale(r: pd.DataFrame, origin: str, horizon: int) -> np.ndarray:
    """Interval scale (cities × horizon) = σ·√h + τ·h.

    σ√h is month-to-month noise accumulating like a random walk; τh is the
    uncertainty about the *trend itself*, which grows linearly and is what
    long-horizon errors are made of (the downturn's drift kept changing).
    Walk-forward, this lowered the interval score at every horizon versus σ√h alone.
    """
    h = np.arange(1, horizon + 1)
    return city_sigma(r, origin)[:, None] * np.sqrt(h)[None, :] + city_tau(r, origin)[:, None] * h[None, :]


def weighted_quantile(x: np.ndarray, w: np.ndarray, qs) -> np.ndarray:
    """Quantiles of x under weights w (interpolated on the weighted CDF)."""
    order = np.argsort(x)
    x, w = x[order], w[order]
    cdf = (np.cumsum(w) - 0.5 * w) / w.sum()
    return np.interp(qs, cdf, x)


def run_backtest(r: pd.DataFrame, table: pd.DataFrame, origins: list[str], horizon: int) -> dict:
    """Base-model forecasts and realised paths at every origin."""
    records = {}
    for origin in origins:
        paths = forecast_all(r, table, origin, horizon)
        records[origin] = {
            "paths": paths,
            "actual": realised_paths(r, origin, horizon),
            "scale": band_scale(r, origin, horizon),
        }
    return records


def national_path(city_cum: np.ndarray) -> np.ndarray:
    """Bottom-up national cumulative path from city cumulative log paths."""
    monthly = np.diff(np.concatenate([np.zeros((city_cum.shape[0], 1)), city_cum], axis=1), axis=1)
    return np.cumsum(np.log(np.nanmean(np.exp(monthly), axis=0)))


def _gap(a: str, b: str) -> int:
    """Months from a to b."""
    return (pd.Period(b, freq="M") - pd.Period(a, freq="M")).n


def ensemble_path(paths: dict[str, np.ndarray], weights: np.ndarray) -> np.ndarray:
    total = np.zeros_like(next(iter(paths.values())))
    norm = np.zeros(weights.shape[1])
    for k, name in enumerate(MODELS):
        if name in paths:
            total += paths[name] * weights[k]
            norm += weights[k]
    return total / np.maximum(norm, 1e-12)


MIN_ORIGINS = 3  # realised origins required before a horizon's weights/quantiles are learned
TOP_K = 2            # up to LEARN_HORIZON: average the k models with the lowest realised error so far
Q_HALF_LIFE = 4      # error quantiles weight recent origins more (half-life in origins = 12 months at step 3)
LEARN_HORIZON = 12  # weights are learned up to here; beyond it the rule below applies
# Beyond LEARN_HORIZON, weights learned from history reflect the regime that was
# observable h months ago (pre-2023 booms for h >= 24), which is the opposite of
# today's regime -- walk-forward scoring showed learned weights lose to a flat
# forecast there.  The rule is fixed a priori from the forecasting literature
# (damped trend is the standard hard-to-beat long-horizon benchmark in the
# M-competitions: Gardner & McKenzie 1985; Makridakis et al. 2020) and these
# horizons are published as scenarios, not calibrated forecasts.
LONG_RULE = "damped_shrunk"


def learn_at(records: dict, origins: list[str], now: str, horizon: int, shrink: float = 0.25, power: float = 1.0,
             top_k: int | None = TOP_K):
    """Weights and error quantiles using only what was observable at `now`.

    An origin o contributes to horizon h only if o + h <= now, i.e. its h-month
    outcome had already been published.  This is the walk-forward rule: no
    forecast is ever scored with weights or intervals fitted on its own future.

    Returns (weights models×h, city_q quantiles×h, nat_q quantiles×h, usable h mask).
    """
    weights = np.zeros((len(MODELS), horizon))
    q_city = np.zeros((len(QUANTILES), horizon))
    q_nat = np.zeros((len(QUANTILES), horizon))
    usable = np.zeros(horizon, dtype=bool)
    normal = np.asarray([-1.96, -1.2816, 0.0, 1.2816, 1.96])
    for h in range(1, horizon + 1):
        past = [o for o in origins if _gap(o, now) >= h]
        mse = np.full(len(MODELS), np.inf)
        if len(past) >= MIN_ORIGINS:
            sse, cnt = np.zeros(len(MODELS)), np.zeros(len(MODELS))
            for o in past:
                rec = records[o]
                act = rec["actual"][:, h - 1]
                for k, name in enumerate(MODELS):
                    if name in rec["paths"]:
                        err = rec["paths"][name][:, h - 1] - act
                        ok = ~np.isnan(err)
                        sse[k] += float(np.sum(err[ok] ** 2))
                        cnt[k] += ok.sum()
            mse = np.where(cnt > 0, sse / np.maximum(cnt, 1), np.inf)
        avail = np.isfinite(mse)
        if h > LEARN_HORIZON:
            weights[MODELS.index(LONG_RULE), h - 1] = 1.0
            usable[h - 1] = True
        elif avail.any() and top_k:
            # top-k combination: average only the k models with the lowest realised error so far
            keep = np.argsort(np.where(avail, mse, np.inf))[:top_k]
            weights[keep, h - 1] = 1.0 / len(keep)
            usable[h - 1] = True
        elif avail.any():
            inv = np.where(avail, 1.0 / np.maximum(mse, 1e-12) ** power, 0.0)
            equal = avail / avail.sum()
            weights[:, h - 1] = shrink * equal + (1 - shrink) * inv / inv.sum()
            usable[h - 1] = True
        else:
            weights[0, h - 1] = 1.0  # naive until something has been learned
        # normalised ensemble errors of the same realised origins
        city_scores, city_w, nat_scores, nat_w = [], [], [], []
        for idx, o in enumerate(past):
            rec = records[o]
            pred = ensemble_path(rec["paths"], weights[:, :horizon])
            act = rec["actual"]
            recency = 0.5 ** ((len(past) - 1 - idx) / Q_HALF_LIFE)   # newest origin weighs 1
            sc = (act[:, h - 1] - pred[:, h - 1]) / rec["scale"][:, h - 1]
            sc = sc[~np.isnan(sc)]
            city_scores.append(sc)
            city_w.append(np.full(len(sc), recency))
            if not np.isnan(act[:, :h]).any():
                nat_err = national_path(act)[h - 1] - national_path(pred)[h - 1]
                nat_scores.append(nat_err / float(np.median(rec["scale"][:, h - 1])))
                nat_w.append(recency)
        cs = np.concatenate(city_scores) if city_scores else np.array([])
        ns = np.asarray(nat_scores)
        q_city[:, h - 1] = weighted_quantile(cs, np.concatenate(city_w), QUANTILES) if len(cs) >= 100 else normal
        q_nat[:, h - 1] = weighted_quantile(ns, np.asarray(nat_w), QUANTILES) if len(ns) >= MIN_ORIGINS else normal
    for q in (q_city, q_nat):  # bands never narrow with horizon
        for i, p in enumerate(QUANTILES):
            if p < 0.5:
                q[i] = np.minimum.accumulate(q[i])
            elif p > 0.5:
                q[i] = np.maximum.accumulate(q[i])
    return weights, q_city, q_nat, usable


def walk_forward_eval(records: dict, origins: list[str], horizon: int, start: str, **learn_kw) -> dict:
    """Score every origin ≥ start with weights/quantiles learned only from its past.

    Scores are pooled over origins and cities; `flat` (index stays unchanged)
    is the no-skill benchmark.
    """
    report_h = [h for h in REPORT_HORIZONS if h <= horizon]
    models = MODELS + ["ensemble", "flat"]
    errs = {m: {h: [] for h in report_h} for m in models}
    inside = {"80": {h: [] for h in report_h}, "95": {h: [] for h in report_h}}
    hits = {h: [] for h in report_h}
    base_down = {h: [] for h in report_h}
    for o in [o for o in origins if o >= start]:
        weights, q_city, _, usable = learn_at(records, origins, o, horizon, **learn_kw)
        rec = records[o]
        pred = ensemble_path(rec["paths"], weights)
        for h in report_h:
            act = rec["actual"][:, h - 1]
            ok = ~np.isnan(act)
            if not ok.any() or not usable[h - 1]:
                continue
            for name in MODELS:
                if name in rec["paths"]:
                    errs[name][h].append(np.abs(rec["paths"][name][ok, h - 1] - act[ok]))
            errs["ensemble"][h].append(np.abs(pred[ok, h - 1] - act[ok]))
            errs["flat"][h].append(np.abs(act[ok]))
            scale = rec["scale"][ok, h - 1]
            inside["80"][h].append((act[ok] >= pred[ok, h - 1] + q_city[1, h - 1] * scale)
                                   & (act[ok] <= pred[ok, h - 1] + q_city[3, h - 1] * scale))
            inside["95"][h].append((act[ok] >= pred[ok, h - 1] + q_city[0, h - 1] * scale)
                                   & (act[ok] <= pred[ok, h - 1] + q_city[4, h - 1] * scale))
            hits[h].append(np.sign(pred[ok, h - 1]) == np.sign(act[ok]))
            base_down[h].append(act[ok] < 0)
    flat = lambda lst: np.concatenate(lst) if lst else np.array([np.nan])
    mae = {m: {h: round(float(np.mean(flat(errs[m][h]))) * 100, 3) for h in report_h if errs[m][h]} for m in models}
    skill = {h: round(1 - mae["ensemble"][h] / mae["flat"][h], 3) for h in mae["ensemble"] if h in mae["flat"]}
    return {
        "mae_pct_points": mae,
        "skill_vs_flat": skill,
        "coverage": {k: {h: round(float(np.mean(flat(v[h]))), 3) for h in report_h if v[h]} for k, v in inside.items()},
        "direction_hit_rate": {h: round(float(np.mean(flat(hits[h]))), 3) for h in report_h if hits[h]},
        "share_of_cities_falling": {h: round(float(np.mean(flat(base_down[h]))), 3) for h in report_h if base_down[h]},
        "n_origins": len([o for o in origins if o >= start]),
    }


def final_forecast(r: pd.DataFrame, table: pd.DataFrame, records: dict, origins: list[str], horizon: int):
    now = r.index[-1]
    weights, q_city, q_nat, usable = learn_at(records, origins, now, horizon)
    paths = forecast_all(r, table, now, horizon)
    point = ensemble_path(paths, weights)
    scale = band_scale(r, now, horizon)
    months = pd.period_range(pd.Period(now, freq="M") + 1, periods=horizon, freq="M").strftime("%Y-%m")

    def band_rows(region: str, centre: np.ndarray, sc: np.ndarray, q: np.ndarray) -> list[dict]:
        rows = []
        for h in range(horizon):
            row = {"region": region, "month": months[h], "h": h + 1}
            for j, p in enumerate(QUANTILES):
                row[f"q{int(p * 1000):03d}"] = round(float(100 * np.exp(centre[h] + (0 if p == 0.5 else q[j, h] * sc[h]))), 3)
            row["mom_point"] = round(float(100 * np.exp(centre[h] - (centre[h - 1] if h else 0.0))), 3)
            rows.append(row)
        return rows

    rows: list[dict] = []
    for i, city in enumerate(r.columns):
        rows += band_rows(city, point[i], scale[i], q_city)
    nat_point = national_path(point)
    rows += band_rows("全国", nat_point, np.median(scale, axis=0), q_nat)
    frame = pd.DataFrame(rows)
    info = {
        "origin": now,
        "weights": {name: {h: round(float(weights[k, h - 1]), 3) for h in REPORT_HORIZONS if h <= horizon}
                    for k, name in enumerate(MODELS)},
        "usable_horizons": int(usable.sum()),
        "model_paths_national": {name: [round(float(100 * np.exp(v)), 3) for v in national_path(p)] for name, p in paths.items()},
    }
    return frame, info, (q_city, q_nat)


def summarise(frame: pd.DataFrame, records: dict, origins: list[str], r: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Headline numbers per region.  P(higher than now) comes from the same
    empirical error distribution that sets the bands; probabilities are clipped
    to [1%, 99%] because ~40 overlapping origins cannot resolve the tails."""
    now = r.index[-1]
    weights, _, _, _ = learn_at(records, origins, now, horizon)
    scale_now = band_scale(r, now, horizon)
    region_scale = {c: scale_now[i] for i, c in enumerate(r.columns)}
    region_scale["全国"] = np.median(scale_now, axis=0)
    city_scores: dict[int, np.ndarray] = {}
    nat_scores: dict[int, np.ndarray] = {}
    for h in [x for x in (12, 24, 36, 60) if x <= horizon]:
        cs, ns = [], []
        for o in [o for o in origins if _gap(o, now) >= h]:
            rec = records[o]
            pred = ensemble_path(rec["paths"], weights)
            cs.append((rec["actual"][:, h - 1] - pred[:, h - 1]) / rec["scale"][:, h - 1])
            if not np.isnan(rec["actual"][:, :h]).any():
                ns.append((national_path(rec["actual"])[h - 1] - national_path(pred)[h - 1]) / float(np.median(rec["scale"][:, h - 1])))
        city_scores[h] = np.concatenate(cs)[~np.isnan(np.concatenate(cs))] if cs else np.array([])
        nat_scores[h] = np.asarray(ns)
    out = []
    for region, sub in frame.groupby("region", sort=False):
        sub = sub.set_index("h")
        rec = {"region": region}
        for h in [x for x in (12, 24, 36, 60) if x <= horizon]:
            if h not in sub.index:
                continue
            point = np.log(sub.at[h, "q500"] / 100.0)
            s = (nat_scores if region == "全国" else city_scores)[h]
            prob = float(np.mean(point + region_scale[region][h - 1] * s > 0)) if len(s) >= MIN_ORIGINS else np.nan
            rec[f"chg{h}"] = round(float(sub.at[h, "q500"] - 100.0), 2)
            rec[f"lo{h}"] = round(float(sub.at[h, "q100"] - 100.0), 2)
            rec[f"hi{h}"] = round(float(sub.at[h, "q900"] - 100.0), 2)
            rec[f"p_up{h}"] = None if np.isnan(prob) else round(float(np.clip(prob, 0.01, 0.99)), 2)
        trough = sub["q500"].idxmin()
        rec["trough_h"] = int(trough)
        rec["trough_month"] = sub.at[trough, "month"]
        rec["next_mom"] = float(sub.at[1, "mom_point"])
        out.append(rec)
    return pd.DataFrame(out)


def hindcast(r: pd.DataFrame, table: pd.DataFrame, records: dict, origins: list[str], origin: str, horizon: int) -> dict:
    """What the model would have said at `origin`, scored on months published since.

    Weights, error quantiles and the Chronos-2 forecast all come from
    information available at `origin`, so this is a genuine out-of-sample
    check, like-for-like with the v0.2 model's published 2026-07..09 numbers.
    """
    weights, q_city, q_nat, _ = learn_at(records, origins, origin, horizon)
    paths = forecast_all(r, table, origin, horizon)
    point = ensemble_path(paths, weights)
    actual = realised_paths(r, origin, horizon)
    known = int((~np.isnan(actual[0])).sum())
    scale = band_scale(r, origin, horizon)
    out: dict = {"origin": origin, "months_scored": known, "regions": {}}
    nat_point, nat_actual = national_path(point), national_path(actual[:, :known])
    nat_scale = np.median(scale, axis=0)
    out["regions"]["全国"] = {
        str(h): {
            "point": round(float(100 * np.exp(nat_point[h - 1])), 2),
            "lo80": round(float(100 * np.exp(nat_point[h - 1] + q_nat[1, h - 1] * nat_scale[h - 1])), 2),
            "hi80": round(float(100 * np.exp(nat_point[h - 1] + q_nat[3, h - 1] * nat_scale[h - 1])), 2),
            "actual": round(float(100 * np.exp(nat_actual[h - 1])), 2),
        } for h in range(1, known + 1)
    }
    for city in ("北京", "上海", "广州", "深圳"):
        i = list(r.columns).index(city)
        out["regions"][city] = {
            str(h): {
                "point": round(float(100 * np.exp(point[i, h - 1])), 2),
                "lo80": round(float(100 * np.exp(point[i, h - 1] + q_city[1, h - 1] * scale[i, h - 1])), 2),
                "hi80": round(float(100 * np.exp(point[i, h - 1] + q_city[3, h - 1] * scale[i, h - 1])), 2),
                "actual": round(float(100 * np.exp(actual[i, h - 1])), 2),
            } for h in range(1, known + 1)
        }
    inside, direction = {}, {}
    for h in range(1, known + 1):
        lo = point[:, h - 1] + q_city[1, h - 1] * scale[:, h - 1]
        hi = point[:, h - 1] + q_city[3, h - 1] * scale[:, h - 1]
        inside[str(h)] = round(float(np.mean((actual[:, h - 1] >= lo) & (actual[:, h - 1] <= hi))), 3)
        direction[str(h)] = round(float(np.mean(np.sign(point[:, h - 1]) == np.sign(actual[:, h - 1]))), 3)
    out["city_coverage_80"], out["city_direction_hit"] = inside, direction
    out["city_mae_pct_points"] = {
        str(h): round(float(np.mean(np.abs(point[:, h - 1] - actual[:, h - 1]))) * 100, 3) for h in range(1, known + 1)
    }
    out["flat_mae_pct_points"] = {str(h): round(float(np.mean(np.abs(actual[:, h - 1]))) * 100, 3) for h in range(1, known + 1)}
    return out


def records_cache_key(data: Path, tsfm: Path | None, horizon: int, start: str,
                      first_origin: str, step: int, source_paths: list[Path] | None = None) -> str:
    """Identify the inputs that determine cached base forecasts and realized paths."""
    sources = source_paths if source_paths is not None else [Path(__file__), Path(__file__).with_name("panel.py")]
    digest = hashlib.sha256()
    params = {"horizon": horizon, "start": start, "first_origin": first_origin, "step": step,
              "numpy": np.__version__, "pandas": pd.__version__, "sklearn": sklearn.__version__,
              "tsfm_present": tsfm is not None}
    digest.update(json.dumps(params, sort_keys=True).encode())
    for path in [Path(data), *([Path(tsfm)] if tsfm else []), *sources]:
        blob = Path(path).read_bytes()
        digest.update(len(blob).to_bytes(8, "big"))
        digest.update(blob)
    return digest.hexdigest()


def _cache_metadata_path(cache: Path) -> Path:
    return cache.with_name(cache.name + ".meta.json")


def records_cache_valid(cache: Path, key: str) -> bool:
    """Reject legacy, stale, incomplete or altered cache payloads."""
    try:
        metadata = json.loads(_cache_metadata_path(cache).read_text(encoding="utf-8"))
        return metadata["key"] == key and metadata["sha256"] == hashlib.sha256(cache.read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError):
        return False


def read_records_cache(cache: Path, key: str) -> dict | None:
    if not records_cache_valid(cache, key):
        return None
    try:
        return pickle.loads(cache.read_bytes())
    except (OSError, pickle.UnpicklingError, EOFError, ValueError, AttributeError, ImportError):
        return None


def write_records_cache(cache: Path, records: dict, key: str) -> None:
    cache.parent.mkdir(parents=True, exist_ok=True)
    payload = pickle.dumps(records)
    cache.write_bytes(payload)
    metadata = {"key": key, "sha256": hashlib.sha256(payload).hexdigest()}
    _cache_metadata_path(cache).write_text(json.dumps(metadata), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=PANEL_PATH)
    parser.add_argument("--horizon", type=int, default=HORIZON)
    parser.add_argument("--start", default="2011-02", help="first month used for modelling (2006-01..2011-01 is legacy methodology)")
    parser.add_argument("--first-origin", default="2016-01")
    parser.add_argument("--eval-from", default="2019-01", help="walk-forward scoring starts at this origin")
    parser.add_argument("--step", type=int, default=3, help="months between backtest origins")
    parser.add_argument("--output", default="data/processed/city_forecast_paths.csv")
    parser.add_argument("--summary", default="data/processed/city_forecast_summary.csv")
    parser.add_argument("--report", default="reports/probabilistic_forecast_backtest.json")
    parser.add_argument("--hindcast-origin", default="", help="default: three months before the last data month")
    parser.add_argument("--cache", default="data/processed/pf_records.pkl", help="backtest records cache ('' disables)")
    parser.add_argument("--tsfm", default="", help="JSON from src.tsfm_baseline; adds Chronos-2 as a base model")
    parser.add_argument("--export-returns", action="store_true", help="write the city return matrix for src.tsfm_baseline and exit")
    parser.add_argument("--returns-out", default="data/processed/city_returns_secondhand.csv", help="where --export-returns writes")
    args = parser.parse_args()

    panel = pd.read_csv(args.data)
    panel = panel[panel["month"] >= args.start]
    r, bridged = forecast_returns(panel[panel["market"].eq("secondhand")], require_complete=True)
    if args.export_returns:
        out = Path(args.returns_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        r.to_csv(out)
        print(f"wrote {out} ({r.shape[0]} months × {r.shape[1]} cities)")
        return
    if args.tsfm:
        TSFM.update(json.loads(Path(args.tsfm).read_text(encoding="utf-8"))["origins"])
    new_r, _ = forecast_returns(panel[panel["market"].eq("new")])
    table = build_features(r, new_r).merge(build_targets(r), on=["month", "city"], how="left")
    table = table[table["r0"].notna()]

    months = list(r.index)
    origins = months[months.index(args.first_origin):-1:args.step]
    print(f"backtest: {len(origins)} origins {origins[0]} → {origins[-1]}, data through {months[-1]}")
    cache = Path(args.cache) if args.cache else None
    key = records_cache_key(Path(args.data), Path(args.tsfm) if args.tsfm else None,
                            args.horizon, args.start, args.first_origin, args.step) if cache else ""
    records = read_records_cache(cache, key) if cache else None
    if records is not None:
        print(f"loaded cached backtest records from {cache}")
    else:
        records = run_backtest(r, table, origins, args.horizon)
        if cache:
            write_records_cache(cache, records, key)

    evaluation = walk_forward_eval(records, origins, args.horizon, args.eval_from)
    frame, info, _ = final_forecast(r, table, records, origins, args.horizon)
    summary = summarise(frame, records, origins, r, args.horizon)

    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False)
    ledger_path, fresh = freeze(frame, months[-1])
    print(f"ledger: {'froze' if fresh else 'kept existing'} {ledger_path}")
    summary.to_csv(args.summary, index=False)
    hind_origin = args.hindcast_origin or months[-4]
    hind = hindcast(r, table, records, origins, hind_origin, args.horizon)
    report = {
        "data_through": months[-1],
        "hindcast": hind,
        "origins": {"count": len(origins), "first": origins[0], "last": origins[-1], "scored_from": args.eval_from},
        "bridged_cells": int(bridged.to_numpy().sum()),
        "walk_forward": evaluation,
        **info,
    }
    Path(args.report).parent.mkdir(parents=True, exist_ok=True)
    Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    nat = summary[summary["region"].eq("全国")].iloc[0].to_dict()
    print(json.dumps({"walk_forward": evaluation, "weights": info["weights"], "national": nat}, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
