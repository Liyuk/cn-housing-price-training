#!/usr/bin/env python3
"""Build static JSON bundles for the GitHub Pages demo site.

The demo site (`site/`) is fully static: every chart is rendered client-side
from pre-baked JSON under `site/data/`. This script turns the processed CSVs
into those JSON bundles so the charts always agree with the repo's data.

The CSVs live under `data/processed/` and are git-ignored; the generated
`site/data/*.json` files ARE committed, which is what makes Pages deployment
self-contained.

Usage:
    .venv/bin/python scripts/build_demo_data.py

Outputs (all written to site/data/):
    meta.json                     headline numbers, weights, coverage, CIREA identity check
    cities_yoy.json               second-hand YoY matrix for the city heatmap
    district_scenarios.json       Beijing 17 / Chongqing 26 district 2026→2030 scenarios
    lpr.json                      LPR history
    macro.json                    national macro panel (investment, starts, sales, inventory)
    market_compare.json           new vs second-hand national MoM comparison
    official.json                 Beijing official 2025-10 district signings
    board.json                    70-city trend board (temperature, strength, 12m forecast)
    cum.json                      chained second-hand index since 2011 per city + phases
    fan.json                      probabilistic multi-year fans per city and national
    breadth.json                  number of cities with rising prices, per month
    scorecard.json                v0.2 vs actual, hindcast, walk-forward and model comparison

The panel is the v4 build (`python -m src.update_data`), the forecasts come from
`python -m src.probabilistic_forecast`.  The v0.2 paper model appears only inside scorecard.json (its published
scenarios scored against what happened) and district_scenarios.json.
"""

from __future__ import annotations

import json
from datetime import date
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import site_extras  # noqa: E402
from src.creprice_panel import CITY_CODES, collect as collect_creprice  # noqa: E402
from src.forecast_ledger import ledger_detail, score_ledger  # noqa: E402
from src.panel import CONSISTENT_FROM, PANEL_PATH, REGIME_BREAK, quality_of  # noqa: E402
from src.probabilistic_forecast import city_tier, monthly_returns  # noqa: E402

PROCESSED = ROOT / "data" / "processed"
OUT = ROOT / "site" / "data"
PANEL_V4 = Path(PANEL_PATH).name
HISTORY_START = CONSISTENT_FROM  # earlier months fail the YoY-chain identity (see src/panel.py)
ASOF_UPDATED = date.today().isoformat()  # build date

# The model's historical series is the monthly mean of the second-hand MoM
# index over available cities (see src/five_year_forecast.py:_monthly_index).
# The forecast month-on-month paths are read straight from the model output,
# so the fan chart and the hero numbers always agree with the reports.


def read(path: str) -> pd.DataFrame:
    """Read a processed CSV, tolerating a UTF-8 BOM on the first column."""
    frame = pd.read_csv(PROCESSED / path, encoding="utf-8-sig")
    if "month" in frame.columns:
        frame["month"] = pd.to_datetime(frame["month"])
    return frame


def build_meta() -> dict:
    """Coverage of the 70-city panel and the CIREA / mirror reconciliation (data page)."""
    v4 = read(PANEL_V4)
    months = v4[v4["market"].eq("secondhand")]["month"]
    return {
        "updated": ASOF_UPDATED,
        "coverage": {"cities": int(v4["city"].nunique()), "months": int(months.nunique()),
                     "start": months.min().strftime("%Y-%m"), "end": months.max().strftime("%Y-%m"),
                     "history_start": HISTORY_START},
        "cirea": _cirea_identity(),
    }


MIRROR_CSV = ROOT / "data" / "raw" / "mirror" / "70cityprice.csv"
SWAP_CITIES = ["徐州", "惠州", "扬州", "韶关"]  # swapped pairs in the mirror from 2021-01 (徐州↔扬州, 惠州↔韶关)


def _mirror_check(cirea: pd.DataFrame, official_months: set) -> dict | None:
    """Cross-check CIREA cells that have no official page against the third-party mirror."""
    if not MIRROR_CSV.exists():
        return None
    w = pd.read_csv(MIRROR_CSV, dtype=str)
    w["month"] = pd.to_datetime(w["DATE"])
    w["v"] = pd.to_numeric(w["SecondHandIDX"], errors="coerce")
    mom = w[w["FixedBase"].eq("环比")][["month", "CITY", "v"]].rename(columns={"CITY": "city", "v": "m_mom"})
    yoy = w[w["FixedBase"].eq("同比")][["month", "CITY", "v"]].rename(columns={"CITY": "city", "v": "m_yoy"})
    rest = cirea[~cirea["month"].isin(official_months)].merge(mom, on=["month", "city"]).merge(yoy, on=["month", "city"])
    same = (rest["month_on_month"] == rest["m_mom"]) & (rest["yoy"] == rest["m_yoy"])
    early = rest["month"] <= pd.Timestamp("2020-12-01")
    diff_cities = sorted(rest[~same]["city"].unique())
    return {
        "checked_cells": int(len(rest)), "identical_cells": int(same.sum()),
        "through_2020_identical": f"{int(same[early].sum())}/{int(early.sum())}",
        "differing_cells": int((~same).sum()), "differing_cities": diff_cities,
        "differing_only_at_swap_cities": bool(set(diff_cities) <= set(SWAP_CITIES)),
        "note": "镜像自 2021-01 起互换了四个城市的数据（用同比链式恒等式证明），这些差异来自镜像而非 CIREA",
    }


def _cirea_identity() -> dict:
    """Industry (CIREA) reposts vs official NBS pages fetched directly.

    Earlier versions compared panel cells *labeled* CIREA with the CIREA files,
    which is the same source against itself.  The v4 panel (src.update_data)
    holds cells parsed straight from stats.gov.cn pages, so the comparison is
    now independent -- but only for months whose official page could be
    located; the rest stay unverified and are reported as such.
    """
    panel = read(PANEL_V4)
    official = panel[panel["methodology"].eq("current") & panel["market"].eq("secondhand")]
    cirea = pd.concat([read("cirea_secondhand_2019_2022.csv"), read("cirea_secondhand_2023.csv")])
    merged = pd.merge(
        official[["month", "city", "yoy", "month_on_month"]],
        cirea[["month", "city", "yoy", "month_on_month"]],
        on=["month", "city"], suffixes=("_off", "_ci"),
    )
    mirror = _mirror_check(cirea, set(official["month"]))
    diff = (merged["yoy_off"] - merged["yoy_ci"]).abs().where(lambda d: d > 1e-9, 0.0)
    mom_diff = (merged["month_on_month_off"] - merged["month_on_month_ci"]).abs()
    bad = merged[(diff > 0) | (mom_diff > 1e-9)]
    return {
        "cirea_cells": int(len(cirea)),
        "overlap_cells": int(len(merged)),
        "unverified_cells": int(len(cirea) - len(merged)),
        "months_checked": int(merged["month"].nunique()),
        "mismatched_cells": int(len(bad)),
        "mismatch_months": sorted(bad["month"].dt.strftime("%Y-%m").unique().tolist()),
        "mismatch_cities": sorted(bad["city"].unique().tolist()),
        "r": round(float(merged["yoy_off"].corr(merged["yoy_ci"])), 4),
        "max_abs_diff": round(float(diff.max()), 1),
        "span": "2019-01 → 2023-12",
        "mirror": mirror,
    }


def _site_panel() -> pd.DataFrame:
    """Panel rows the site charts: the consistent era only (older rows stay in the download, flagged)."""
    frame = read(PANEL_V4)
    return frame[frame["month"] >= pd.Timestamp(HISTORY_START + "-01")]


def build_cities() -> dict:
    frame = _site_panel()
    frame = frame[frame["market"].eq("secondhand")]
    months_ts = sorted(frame["month"].unique())
    pivot = frame.pivot_table(index="city", columns="month", values="yoy", aggfunc="first")

    # Sort so the biggest recent decliners sit on top of the heatmap.
    order = pivot[months_ts[-1]].dropna().sort_values(ascending=False).index
    cities = list(order) + [c for c in pivot.index if c not in order]

    months = [m.strftime("%Y-%m") for m in months_ts]

    return {
        "months": months,
        "cities": cities,
        "values": [
            {
                "city": city,
                "series": [
                    None if pd.isna(pivot.at[city, m]) else round(float(pivot.at[city, m]), 1)
                    for m in months_ts
                ],
            }
            for city in cities
        ],
    }


def build_district_scenarios() -> dict:
    """Per-city district scenarios (北京 17 / 重庆 26) for the 2030 year-end."""
    frame = read("district_price_forecast_2026_2030.csv")
    result = {}
    for city in ("北京", "重庆"):
        city_frame = frame[frame["city"].eq(city)]
        base = city_frame[city_frame["year"].eq(2026)].set_index("district")["base_price_yuan_m2"]
        end = city_frame[city_frame["year"].eq(2030)].set_index("district")
        rows = []
        for district in base.index:
            rows.append(
                {
                    "district": district,
                    "base2026": int(round(float(base.at[district]))),
                    "base2030": int(round(float(end.at[district, "price_base_yuan_m2"]))),
                    "low2030": int(round(float(end.at[district, "price_low_yuan_m2"]))),
                    "high2030": int(round(float(end.at[district, "price_high_yuan_m2"]))),
                    "confidence": str(end.at[district, "confidence"]),
                }
            )
        rows.sort(key=lambda r: r["base2026"])
        result[city] = rows
    return result


def build_lpr() -> dict:
    frame = read("lpr_history.csv")
    frame["month"] = pd.to_datetime(frame["month"])
    frame = frame.sort_values("month")
    return [
        {
            "m": row.month.strftime("%Y-%m"),
            "lpr_1y": None if pd.isna(row.lpr_1y) else round(float(row.lpr_1y), 3),
            "lpr_5y": None if pd.isna(row.lpr_5y) else round(float(row.lpr_5y), 3),
        }
        for row in frame.itertuples()
    ]


def build_macro() -> dict:
    """National macro panel: YoY % series + inventory level, 2023-02 → 2026-06."""
    frame = read("macro_features_full.csv")
    frame["month"] = pd.to_datetime(frame["month"])
    frame = frame.sort_values("month")

    metrics = [
        ("development_investment_yoy", "房地产开发投资同比"),
        ("new_starts_area_yoy", "新开工面积同比"),
        ("completions_area_yoy", "竣工面积同比"),
        ("new_home_sales_area_yoy", "商品房销售面积同比"),
        ("new_home_sales_value_yoy", "商品房销售额同比"),
        ("inventory_area_yoy", "商品房待售面积同比"),
        ("developer_funding_yoy", "到位资金同比"),
    ]
    series = {
        field: [None if pd.isna(v) else round(float(v), 1) for v in frame[field]]
        for field, _ in metrics
    }
    months = [m.strftime("%Y-%m") for m in frame["month"]]
    inventory = [None if pd.isna(v) else round(float(v) / 10000.0, 2) for v in frame["inventory_area"]]
    return {
        "months": months,
        "metrics": [{"key": key, "label": label} for key, label in metrics],
        "series": series,
        "inventory_wan_m2": inventory,
    }


def build_market_compare() -> dict:
    """National monthly mean MoM index for new vs second-hand, for comparison."""
    frame = _site_panel()
    months = []
    new, secondhand = [], []
    for m, sub in frame.groupby("month"):
        months.append(m.strftime("%Y-%m"))
        def mean_for(mkt):
            vals = sub[sub["market"].eq(mkt)]["month_on_month"]
            return round(float(vals.mean()), 2) if len(vals) else None
        new.append(mean_for("new"))
        secondhand.append(mean_for("secondhand"))
    return {"months": months, "new": new, "secondhand": secondhand}


def build_official() -> dict:
    """Beijing official 2025-10 district second-hand signings."""
    frame = read("beijing_official_district_secondhand_2025_10.csv")
    frame = frame.sort_values("transaction_count", ascending=False)
    return {
        "month": "2025-10",
        "total_units": int(round(frame["transaction_count"].sum())),
        "districts": [
            {
                "district": row.district,
                "count": int(round(row.transaction_count)),
                "area_m2": round(float(row.transaction_area_m2), 0),
            }
            for row in frame.itertuples()
        ],
    }


# ---------------------------------------------------------------- trend board
TEMPERATURES = [  # (label, upper bound of mean monthly change in %, key)
    ("寒", -0.30, "cold"), ("凉", -0.10, "cool"), ("平", 0.10, "flat"), ("温", 0.30, "warm"), ("热", 99.0, "hot"),
]


def temperature(m6_pct: float) -> tuple[str, str]:
    for label, upper, key in TEMPERATURES:
        if m6_pct <= upper:
            return label, key
    return TEMPERATURES[-1][0], TEMPERATURES[-1][2]


def _market_returns(market: str = "secondhand") -> tuple[pd.DataFrame, pd.DataFrame]:
    panel = read(PANEL_V4)
    panel["month"] = panel["month"].dt.strftime("%Y-%m")
    panel = panel[panel["month"] >= HISTORY_START]
    return monthly_returns(panel[panel["market"].eq(market)])


def _secondhand_returns() -> tuple[pd.DataFrame, pd.DataFrame]:
    return _market_returns("secondhand")


def _chain(r: pd.DataFrame) -> pd.DataFrame:
    """Chained index (first month = its MoM), national = mean of city MoM indices."""
    chain = np.exp(r.cumsum()) * 100.0
    nat = np.exp(np.log(np.exp(r).mean(axis=1)).cumsum()) * 100.0
    tiers = {}
    for label, tier in (("一线", 1), ("二线", 2), ("三线", 3)):
        members = [c for c in r.columns if city_tier(c) == tier]
        tiers[label] = np.exp(np.log(np.exp(r[members]).mean(axis=1)).cumsum()) * 100.0
    chain.insert(0, "全国", nat)
    for i, (label, series) in enumerate(tiers.items(), start=1):
        chain.insert(i, label, series)
    return chain


def _phases(values: np.ndarray, months: list[str]) -> dict:
    """Peak, drawdown from peak, 'price back to' month, and the two phases the
    reference app annotates: B = largest rally, A = largest drawdown."""
    n = len(values)
    peak_i = int(np.argmax(values))
    # largest drawdown (peak-to-trough, trough after peak)
    run_max, dd_peak, best_dd, dd_pair = values[0], 0, 0.0, (0, 0)
    for i in range(n):
        if values[i] > run_max:
            run_max, dd_peak = values[i], i
        dd = values[i] / run_max - 1.0
        if dd < best_dd:
            best_dd, dd_pair = dd, (dd_peak, i)
    # largest rally (trough-to-peak, peak after trough)
    run_min, rl_low, best_rl, rl_pair = values[0], 0, 0.0, (0, 0)
    for i in range(n):
        if values[i] < run_min:
            run_min, rl_low = values[i], i
        rl = values[i] / run_min - 1.0
        if rl > best_rl:
            best_rl, rl_pair = rl, (rl_low, i)
    now = values[-1]
    back_to = None
    for i in range(peak_i - 1, -1, -1):  # latest month before the peak at/below today's level
        if values[i] <= now:
            back_to = months[i]
            break
    return {
        "peak": {"m": months[peak_i], "v": round(float(values[peak_i]), 1)},
        "now": round(float(now), 1),
        "from_peak_pct": round(float(now / values[peak_i] - 1.0) * 100.0, 1),
        "months_since_peak": n - 1 - peak_i,
        "back_to": back_to,
        "max_drawdown": {"from": months[dd_pair[0]], "to": months[dd_pair[1]], "pct": round(best_dd * 100.0, 1)},
        "max_rally": {"from": months[rl_pair[0]], "to": months[rl_pair[1]], "pct": round(best_rl * 100.0, 1)},
    }


def build_cum(market: str = "secondhand") -> dict:
    r, bridged = _market_returns(market)
    chain = _chain(r)
    months = list(chain.index)
    return {
        "months": months,
        "base": f"{(pd.Period(months[0], freq='M') - 1).strftime('%Y-%m')} = 100（环比链式累乘）",
        "regime_break": {"month": REGIME_BREAK, "note": "此前为旧口径（第三方镜像），此后为现行口径（官方页面）；断点两侧不应直接比较涨跌幅"},
        "bridged_months": sorted(set(bridged.index[bridged.any(axis=1)])),
        "series": {c: [round(float(v), 1) for v in chain[c]] for c in chain.columns},
        "phases": {c: _phases(chain[c].to_numpy(), months) for c in chain.columns},
    }


def build_breadth() -> dict:
    panel = _site_panel()
    sh = panel[panel["market"].eq("secondhand")]
    grouped = sh.groupby(sh["month"].dt.strftime("%Y-%m"))
    return {
        "months": list(grouped.groups.keys()),
        "n": [int(len(g)) for _, g in grouped],
        "up_mom": [int((g["month_on_month"] > 100).sum()) for _, g in grouped],
        "flat_mom": [int((g["month_on_month"] == 100).sum()) for _, g in grouped],
        "up_yoy": [int((g["yoy"] > 100).sum()) for _, g in grouped],
    }


def build_board() -> dict:
    r, _ = _secondhand_returns()
    chain = _chain(r)
    panel = read(PANEL_V4)
    last = panel["month"].max().strftime("%Y-%m")
    latest = panel[panel["market"].eq("secondhand") & panel["month"].eq(pd.Timestamp(last))].set_index("city")
    summary = pd.read_csv(PROCESSED / "city_forecast_summary.csv").set_index("region")
    pct = (np.exp(r) - 1.0) * 100.0
    m3, m6, m12 = pct.iloc[-3:].mean(), pct.iloc[-6:].mean(), pct.iloc[-12:].mean()
    strength = m3.rank(pct=True).mul(100).round().astype(int)
    months = list(chain.index)
    rows = []
    for city in r.columns:
        values = chain[city].to_numpy()
        ph = _phases(values, months)
        label, key = temperature(float(m6[city]))
        s = summary.loc[city]
        rows.append({
            "city": city,
            "tier": city_tier(city),
            "mom": float(latest.at[city, "month_on_month"]),
            "yoy": float(latest.at[city, "yoy"]),
            "m3": round(float(m3[city]), 2),
            "m6": round(float(m6[city]), 2),
            "m12": round(float(m12[city]), 2),
            "temp": label,
            "temp_key": key,
            "strength": int(strength[city]),
            "turning": bool(m3[city] - m12[city] >= 0.15 and pct[city].iloc[-1] >= 0),
            "spark": [round(float(v), 1) for v in values[-25:]],
            "from_peak_pct": ph["from_peak_pct"],
            "peak_m": ph["peak"]["m"],
            "back_to": ph["back_to"],
            "f12": float(s["chg12"]),
            "lo12": float(s["lo12"]),
            "hi12": float(s["hi12"]),
            "p_up12": None if pd.isna(s["p_up12"]) else float(s["p_up12"]),
            "chg36": float(s["chg36"]),
            **{k: (None if pd.isna(s.get(k)) else float(s[k])) for k in ("chg60", "lo60", "hi60", "p_up60") if k in s.index},
            "next_mom": float(s["next_mom"]),
        })
    rows.sort(key=lambda x: -x["strength"])
    temps = [x["temp"] for x in rows]
    nat = summary.loc["全国"]
    return {
        "asof": last,
        "updated": ASOF_UPDATED,
        "temperature_rule": {
            "metric": "近 6 个月平均环比涨跌（%/月）",
            "bands": [{"label": l, "upper": u if u < 90 else None} for l, u, _ in TEMPERATURES],
        },
        "counts": {label: temps.count(label) for label, _, _ in TEMPERATURES},
        "national": {k: (None if pd.isna(v) else v) for k, v in nat.items() if k != "region"},
        "rows": rows,
    }


def build_fan() -> dict:
    paths = pd.read_csv(PROCESSED / "city_forecast_paths.csv")
    r, _ = _secondhand_returns()
    chain = _chain(r)
    hist_months = list(chain.index[-37:])
    fc_months = list(paths[paths["region"].eq("全国")].sort_values("h")["month"])
    out = {"hist_months": hist_months, "fc_months": fc_months, "regions": {}}
    for region, sub in paths.groupby("region"):
        sub = sub.sort_values("h")
        hist = chain[region].iloc[-37:].to_numpy()
        out["regions"][region] = {
            "hist": [round(float(v / hist[-1] * 100.0), 2) for v in hist],
            "q025": [round(float(v), 2) for v in sub["q025"]],
            "q100": [round(float(v), 2) for v in sub["q100"]],
            "q500": [round(float(v), 2) for v in sub["q500"]],
            "q900": [round(float(v), 2) for v in sub["q900"]],
            "q975": [round(float(v), 2) for v in sub["q975"]],
        }
    return out


def build_ledger() -> dict:
    """Frozen forecasts and what has been published since, for the ledger section of the forecast page."""
    return ledger_detail(str(PROCESSED / PANEL_V4), ROOT / "reports" / "forecast_ledger")


def build_scorecard() -> dict:
    """v0.2 published scenarios vs the months published after it, plus the new model's evidence."""
    report = json.loads((ROOT / "reports" / "probabilistic_forecast_backtest.json").read_text(encoding="utf-8"))
    v4 = read(PANEL_V4)
    v3 = read("housing_indices_clean_v3.csv")
    new_months = sorted(m for m in set(v4["month"]) if m > v3["month"].max())
    paths = read("five_year_index_paths.csv")
    sh = v4[v4["market"].eq("secondhand")]
    legacy = {}
    for region, city in (("全国", None), ("北京", "北京")):
        sub = sh if city is None else sh[sh["city"].eq(city)]
        actual = sub.groupby("month")["month_on_month"].mean().loc[new_months]
        model = paths[paths["region"].eq(region)].set_index("month").loc[new_months]
        rows = []
        for i, m in enumerate(new_months, start=1):
            cum = lambda ser: float(np.prod(ser.iloc[:i].to_numpy() / 100.0) * 100.0)
            rows.append({
                "h": i, "m": m.strftime("%Y-%m"),
                "actual": round(cum(actual), 2),
                "base": round(cum(model["monthly_index"]), 2),
                "low": round(cum(model["monthly_index_low"]), 2),
                "high": round(cum(model["monthly_index_high"]), 2),
            })
        legacy[region] = rows
    wf = report["walk_forward"]
    return {
        "v02": {"origin": "2026-06", "released": "2026-08", "regions": legacy},
        "hindcast": report["hindcast"],
        "ledger": score_ledger(str(PROCESSED / PANEL_V4), ROOT / "reports" / "forecast_ledger"),
        "walk_forward": {
            "n_origins": wf["n_origins"],
            "scored_from": report["origins"]["scored_from"],
            "horizons": [int(h) for h in wf["skill_vs_flat"]],
            "skill_vs_flat": [wf["skill_vs_flat"][h] for h in wf["skill_vs_flat"]],
            "coverage80": [wf["coverage"]["80"][h] for h in wf["skill_vs_flat"]],
            "coverage95": [wf["coverage"]["95"][h] for h in wf["skill_vs_flat"]],
            "direction": [wf["direction_hit_rate"][h] for h in wf["skill_vs_flat"]],
            "mae": wf["mae_pct_points"],
        },
        "weights": report["weights"],
    }


def _creprice_panel() -> pd.DataFrame | None:
    """District panel for cities with cached reports (offline: never fetches)."""
    frame = site_extras.complete_cities(collect_creprice(list(CITY_CODES), "2022-01", "2026-12", offline=True))
    return frame if len(frame) else None


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    site_extras.clean_dir(OUT / "districts")  # stale city files must not outlive a rebuild

    bundles = {
        "meta.json": build_meta,
        "cities_yoy.json": build_cities,
        "district_scenarios.json": build_district_scenarios,
        "lpr.json": build_lpr,
        "macro.json": build_macro,
        "market_compare.json": build_market_compare,
        "official.json": build_official,
        "board.json": build_board,
        "cum.json": build_cum,
        "cum_new.json": lambda: build_cum("new"),
        "fan.json": build_fan,
        "breadth.json": build_breadth,
        "scorecard.json": build_scorecard,
        "ledger.json": build_ledger,
    }

    def default(value):  # numpy scalars from pandas aggregates
        if isinstance(value, np.integer):
            return int(value)
        if isinstance(value, np.floating):
            return None if np.isnan(value) else float(value)
        raise TypeError(type(value))

    payloads = {name: fn() for name, fn in bundles.items()}
    creprice = _creprice_panel()
    districts = site_extras.build_districts(creprice) if creprice is not None else {}
    if creprice is not None:
        payloads["yield.json"] = site_extras.build_yield(creprice)

    sizes: dict[str, int] = {}
    for name, payload in payloads.items():
        sizes[name] = site_extras.write_json(OUT / name, payload, default)
    for city, payload in districts.items():
        sizes[f"districts/{city}.json"] = site_extras.write_json(OUT / "districts" / f"{city}.json", payload, default)
    for name, size in sizes.items():
        print(f"wrote site/data/{name}  ({size / 1024:.0f} KB)")

    downloads = site_extras.write_downloads(ROOT / "site" / "downloads", PROCESSED / PANEL_V4,
                                            PROCESSED / "city_forecast_paths.csv", payloads["board.json"])
    datasets = site_extras.dataset_matrix(read(PANEL_V4).assign(month=lambda d: d["month"].dt.strftime("%Y-%m")),
                                          read("macro_features_full.csv").assign(month=lambda d: d["month"].dt.strftime("%Y-%m")),
                                          read("lpr_history.csv").assign(month=lambda d: d["month"].dt.strftime("%Y-%m")), creprice)
    manifest = site_extras.build_manifest(payloads, districts, downloads, sizes, ASOF_UPDATED, datasets)
    manifest["changelog"] = site_extras.changelog(ROOT / "reports" / "data_update_log.json")
    site_extras.write_json(OUT / "manifest.json", manifest, default)
    print(f"wrote site/data/manifest.json  ({len(payloads)} bundles, {len(districts)} city district files, {len(downloads)} downloads)")


if __name__ == "__main__":
    main()
