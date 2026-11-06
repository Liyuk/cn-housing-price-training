"""Site data extras: per-city district files, rent-yield bundle, downloads, manifest.

The manifest is the seam between the Python build and the static pages.  Every
date, span, frequency and as-of the site shows is read from it
(``assets/js/core/vintage.js``), so no page hard-codes a date and a stale
bundle is visible rather than silently shown as current.

Interface: ``build_extras(payloads, ...)`` takes the already-built bundles
(name -> payload) and returns ``{filename: payload}`` for the extra bundles,
the downloads it wrote, and the manifest.  Everything about how coverage is
measured stays in here.
"""

from __future__ import annotations

import gzip
import io
import json
import shutil
from datetime import date
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from src.panel import CONSISTENT_FROM, quality_of

TIME_ZONE = "Asia/Shanghai"
RELEASE_DAY = 17  # NBS publishes the 70-city report around the 15th-17th of the following month


def next_release_estimate(last_month: str) -> str:
    """Estimated publication date of the report after `last_month` (an estimate, not a calendar)."""
    y, m = map(int, last_month.split("-"))
    m += 2
    y += (m - 1) // 12
    m = (m - 1) % 12 + 1
    return date(y, m, RELEASE_DAY).isoformat()


# ---------------------------------------------------------------- districts
def complete_cities(panel: pd.DataFrame, ratio: float = 0.8) -> pd.DataFrame:
    """Keep cities whose collected months cover >= `ratio` of the span any city reaches.

    A collection run can be partial (it takes hours); a city with a few months
    must not be published as if it were a series.
    """
    if panel.empty:
        return panel
    span = len(pd.period_range(panel["month"].min(), panel["month"].max(), freq="M"))
    counts = panel.groupby("city")["month"].nunique()
    return panel[panel["city"].isin(counts[counts >= ratio * span].index)]


def build_districts(panel: pd.DataFrame) -> dict[str, dict]:
    """One bundle per city: monthly price / rent / gross yield per district.

    Each report page lists only the top 10 districts per ranking, so a district
    can be absent in some months; absent months are null, never filled.
    """
    out: dict[str, dict] = {}
    for city, sub in panel.groupby("city"):
        months = sorted(sub["month"].unique())
        districts: dict[str, dict] = {}
        for district, d in sub.groupby("district"):
            d = d.set_index("month")

            def col(name: str, nd: int) -> list:
                return [None if m not in d.index or pd.isna(d.at[m, name]) else round(float(d.at[m, name]), nd) for m in months]

            districts[district] = {
                "price": col("price_yuan_m2", 0), "rent": col("rent_yuan_m2_month", 2), "yield": col("gross_yield_pct", 2),
            }
        latest = months[-1]
        order = sorted(districts, key=lambda k: -(next((v for v in reversed(districts[k]["price"]) if v is not None), 0)))
        out[city] = {
            "city": city, "months": months, "asof": latest, "n_months": len(months),
            "districts": {k: districts[k] for k in order},
            "note": "第三方（creprice）月报；每页只列价格榜/租金榜各前 10 名区，榜外月份为空。收益率 = 月租金 × 12 ÷ 单价，仅在同月两榜都有该区时计算。非成交价。",
        }
    return out


def build_yield(panel: pd.DataFrame) -> dict:
    """Cross-city view: gross rental yield of the listed districts, latest month and history."""
    cities = []
    for city, sub in panel.groupby("city"):
        sub = sub.dropna(subset=["gross_yield_pct"])
        if sub.empty:
            continue
        months = sorted(sub["month"].unique())
        latest = months[-1]
        now = sub[sub["month"].eq(latest)]
        series = sub.groupby("month")["gross_yield_pct"].median()
        cities.append({
            "city": city, "asof": latest, "n_districts": int(len(now)),
            "median_yield": round(float(now["gross_yield_pct"].median()), 2),
            "min_yield": round(float(now["gross_yield_pct"].min()), 2), "max_yield": round(float(now["gross_yield_pct"].max()), 2),
            "median_price": round(float(now["price_yuan_m2"].median()), 0),
            "series": {"months": list(series.index), "median": [round(float(v), 2) for v in series.values]},
        })
    cities.sort(key=lambda c: -c["median_yield"])
    return {"cities": cities, "note": "榜内区的租金收益率中位数；榜单成员逐月变化，序列只作趋势参考。"}


# ---------------------------------------------------------------- downloads
def write_downloads(out_dir: Path, panel_path: Path, paths_csv: Path, board: dict) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    files = []

    def gz(name: str, frame: pd.DataFrame, note: str) -> None:
        path = out_dir / name
        with open(path, "wb") as raw, gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as zipped, \
                io.TextIOWrapper(zipped, encoding="utf-8", newline="") as handle:   # mtime=0: rebuilds are byte-identical
            frame.to_csv(handle, index=False)
        files.append({"file": f"downloads/{name}", "bytes": path.stat().st_size, "note": note})

    panel = pd.read_csv(panel_path)[["month", "city", "market", "month_on_month", "yoy", "methodology"]]
    panel["quality"] = panel["month"].map(quality_of)
    gz("housing_index_70city.csv.gz", panel.sort_values(["month", "city", "market"]),
       "70 城新房/二手住宅价格指数（环比、同比），含来源口径 methodology 与数据质量 quality（low_consistency = 环比与同比不自洽，勿连乘）")
    if paths_csv.exists():
        gz("city_forecast_quantiles.csv.gz", pd.read_csv(paths_csv),
           "70 城 + 全国未来逐月预测分位数（指数，预测起点月 = 100）；+13 个月起为情景")
    board_csv = out_dir / "city_board.csv"
    pd.DataFrame(board["rows"]).drop(columns=["spark"]).to_csv(board_csv, index=False, encoding="utf-8-sig")
    files.append({"file": "downloads/city_board.csv", "bytes": board_csv.stat().st_size, "note": "城市榜单当期快照"})
    return files


# ---------------------------------------------------------------- manifest
def _span(months: list[str] | None) -> dict:
    return {} if not months else {"start": months[0], "end": months[-1], "n": len(months)}


def _bundle_info(name: str, payload, built_at: str) -> dict:
    """Coverage of one bundle, by the bundle's own shape."""
    info: dict = {"built_at": built_at}
    if name == "cum.json":
        info.update(_span(payload["months"]), freq="月度", basis=payload["base"], kind="official+legacy",
                    regime_break=payload["regime_break"]["month"])
    elif name == "cum_new.json":
        info.update(_span(payload["months"]), freq="月度", basis=payload["base"] + "；新建商品住宅", kind="official+legacy",
                    regime_break=payload["regime_break"]["month"], bridged=len(payload["bridged_months"]))
    elif name == "board.json":
        info.update(asof=payload["asof"], freq="月度", basis="近 6 个月平均环比（温度）", kind="derived")
    elif name == "fan.json":
        info.update(origin=payload["hist_months"][-1], start=payload["fc_months"][0], end=payload["fc_months"][-1],
                    n=len(payload["fc_months"]), freq="月度", basis="预测起点月 = 100", kind="model")
    elif name == "breadth.json":
        info.update(_span(payload["months"]), freq="月度", basis="环比上涨城市数", kind="derived")
    elif name == "cities_yoy.json":
        info.update(_span(payload["months"]), freq="月度", basis="同比指数（上年同月 = 100）", kind="official+legacy")
    elif name == "market_compare.json":
        info.update(_span(payload["months"]), freq="月度", basis="环比指数均值（上月 = 100）", kind="official+legacy")
    elif name == "macro.json":
        info.update(_span(payload["months"]), freq="月度（累计）", basis="年初至当月累计的同比", kind="official")
    elif name == "lpr.json":
        months = [r["m"] for r in payload]
        info.update(_span(months), freq="月度（每月 20 日公告）", basis="贷款市场报价利率", kind="official")
    elif name == "official.json":
        info.update(start=payload["month"], end=payload["month"], n=1, freq="快照", basis="北京存量房网签（单月）", kind="official")
    elif name == "district_scenarios.json":
        info.update(start="2026", end="2030", freq="年末", basis="v0.2 情景（数据至 2026-06）", kind="model")
    elif name == "scorecard.json":
        wf = payload["walk_forward"]
        info.update(start=wf["scored_from"], n=wf["n_origins"], freq="每 3 个月一个回测起点",
                    basis=f"回放起点 {payload['hindcast']['origin']}；账本 {len(payload['ledger'])} 期", kind="model")
    elif name == "ledger.json":
        entries = payload["entries"]
        scored = sum(len(e["actual"]["months"]) for e in entries)
        info.update(start=entries[0]["origin"] if entries else None, end=entries[-1]["origin"] if entries else None, n=len(entries),
                    freq="每次更新冻结一期", basis=f"起点 = 100；已评分 {scored} 个月", kind="model")
    elif name == "yield.json":
        info.update(asof=max(c["asof"] for c in payload["cities"]), freq="月度", basis="榜内区租金收益率", kind="third_party")
    elif name == "meta.json":
        info.update(asof=payload["coverage"]["end"], freq="月度", basis="覆盖范围与对账结果", kind="derived")
    return info


# Reliability zones are a *result*, computed from the walk-forward scorecard and never typed into a page.
ZONE_COVERAGE_TOL = 0.05   # 80% band must cover within 0.80 ± tol to count as reliable
ZONE_SKILL_RELIABLE = 0.20  # and beat "no change" by at least 20%
ZONE_SKILL_CAUTION = 0.15
ZONE_COVERAGE_CAUTION = 0.70
LEARN_HORIZON = 12         # beyond it the point forecast is a fixed rule, not learned


def forecast_zones(wf: dict) -> dict:
    """reliable_through: learned horizons whose band is calibrated and which clearly beat 'no change'.
    caution_through: further horizons that still have skill and acceptable coverage (a fixed rule
    chosen after seeing results, hence only 'caution').  Past it, scenarios only."""
    rows = list(zip(wf["horizons"], wf["coverage80"], wf["skill_vs_flat"]))
    reliable = max([h for h, c, s in rows if h <= LEARN_HORIZON and abs(c - 0.8) <= ZONE_COVERAGE_TOL and s >= ZONE_SKILL_RELIABLE], default=0)
    caution = max([h for h, c, s in rows if h > reliable and s >= ZONE_SKILL_CAUTION and c >= ZONE_COVERAGE_CAUTION], default=reliable)
    return {"reliable_through": reliable, "caution_through": caution}


def build_manifest(payloads: dict[str, object], district_files: dict[str, dict], downloads: list[dict],
                   sizes: dict[str, int], built_at: str, datasets: list[dict]) -> dict:
    meta, board, fan = payloads["meta.json"], payloads["board.json"], payloads["fan.json"]
    bundles = {name: {"file": f"data/{name}", "bytes": sizes.get(name, 0), **_bundle_info(name, payload, built_at)}
               for name, payload in payloads.items()}
    cities = {c: {"file": f"data/districts/{c}.json", "bytes": sizes.get(f"districts/{c}.json", 0),
                  "asof": d["asof"], "start": d["months"][0], "n": d["n_months"], "freq": "月度",
                  "basis": "第三方月报，前 10 名区", "kind": "third_party"} for c, d in district_files.items()}
    last = board["asof"]
    return {
        "built_at": built_at, "timezone": TIME_ZONE,
        "data_through": last,
        "next_release_estimate": next_release_estimate(last),
        "next_release_note": "国家统计局通常在次月 15–17 日发布；此为估计，不是日历",
        "forecast": {"origin": fan["hist_months"][-1], "end": fan["fc_months"][-1], "horizon_months": len(fan["fc_months"]),
                     **forecast_zones(payloads["scorecard.json"]["walk_forward"])},
        "regime_break": payloads["cum.json"]["regime_break"],
        "history_start": CONSISTENT_FROM,
        "bundles": bundles, "districts": cities, "downloads": downloads, "datasets": datasets,
    }


def dataset_matrix(panel_v4: pd.DataFrame, macro: pd.DataFrame, lpr: pd.DataFrame, creprice: pd.DataFrame | None) -> list[dict]:
    """Coverage matrix for the data page: what exists, from when to when, with which gaps."""
    rows = []
    for market, label in (("secondhand", "70 城二手住宅价格指数"), ("new", "70 城新建商品住宅价格指数")):
        sub = panel_v4[panel_v4["market"].eq(market)]
        months = sorted(sub["month"].unique())
        full = pd.period_range(months[0], months[-1], freq="M").strftime("%Y-%m")
        missing = sorted(set(full) - set(months))
        by = sub.groupby("methodology")["month"].nunique().to_dict()
        rows.append({
            "name": label, "source": "国家统计局（2011-02 起直接抓取官方页面；此前为第三方镜像）", "granularity": "城市 × 月",
            "freq": "月度", "start": months[0], "end": months[-1], "n": len(months), "missing": missing,
            "by_methodology": {k: int(v) for k, v in by.items()}, "kind": "official",
            "note": f"{CONSISTENT_FROM} 之前的环比与同比不自洽（环比连乘推不出同比），保留在下载文件中并标记 low_consistency，站内图表从 {CONSISTENT_FROM} 起",
        })
    rows.append({"name": "全国房地产开发与销售（含销售面积/额、待售面积）", "source": "国家统计局", "granularity": "全国 × 月（年初累计）",
                 "freq": "月度", "start": macro["month"].min(), "end": macro["month"].max(), "n": int(len(macro)), "missing": [], "kind": "official"})
    rows.append({"name": "贷款市场报价利率 LPR", "source": "中国人民银行", "granularity": "全国 × 月", "freq": "月度",
                 "start": lpr["month"].min(), "end": lpr["month"].max(), "n": int(len(lpr)), "missing": [], "kind": "official"})
    if creprice is not None and len(creprice):
        months = sorted(creprice["month"].unique())
        rows.append({"name": "区县价格、租金与租金收益率", "source": "creprice 月报（第三方，非成交价；每页仅前 10 名区）",
                     "granularity": f"{creprice['city'].nunique()} 城 × 区 × 月", "freq": "月度", "start": months[0], "end": months[-1],
                     "n": len(months), "missing": [], "kind": "third_party"})
    rows.append({"name": "北京区级网签（存量房）", "source": "北京市住建委", "granularity": "北京 × 区 × 月（仅 2025-10 快照）与年度",
                 "freq": "快照", "start": "2025-10", "end": "2025-10", "n": 1, "missing": [], "kind": "official"})
    rows.append({"name": "城市级月度销量", "source": "无统一官方来源", "granularity": "—", "freq": "—", "start": None, "end": None,
                 "n": 0, "missing": [], "kind": "unavailable"})
    rows.append({"name": "小区/楼盘价格与成交", "source": "无合规的批量来源，本站不提供", "granularity": "—", "freq": "—",
                 "start": None, "end": None, "n": 0, "missing": [], "kind": "unavailable"})
    return rows


def changelog(log_path: Path, limit: int = 8) -> list[dict]:
    """Human-readable update history from reports/data_update_log.json (newest first)."""
    if not log_path.exists():
        return []
    runs = json.loads(log_path.read_text(encoding="utf-8"))
    runs = [runs] if isinstance(runs, dict) else runs
    out = []
    for r in runs:
        parts = []
        fetched = r.get("city_months_fetched")
        n = fetched if isinstance(fetched, int) else len(fetched or [])
        if n:
            parts.append(f"抓取 70 城官方页面 {n} 个月")
        changed = r.get("replaced_cells_with_different_values") or []
        if changed:
            cities = sorted({c["city"] for c in changed})
            parts.append(f"{len(changed)} 个单元被官方页面纠正（{'、'.join(cities)}）")
        lm = r.get("legacy_mirror")
        if lm:
            parts.append(f"补入旧口径镜像 {lm.get('months_added', 0)} 个月；与官方页面逐格对照 {lm.get('identical_cells', 0)}/{lm.get('compared_cells', 0)} 一致")
        if r.get("mirror_filled_gaps"):
            parts.append(f"镜像补缺 {len({g.split(':')[1] for g in r['mirror_filled_gaps']})} 个月")
        if r.get("macro_months_added"):
            parts.append("宏观新增 " + "、".join(r["macro_months_added"]))
        if r.get("lpr_months_added"):
            parts.append("LPR 新增 " + "、".join(r["lpr_months_added"]))
        if parts:
            out.append({"run": str(r["run"])[:10], "text": "；".join(parts)})
    return out[::-1][:limit]


def write_json(path: Path, payload, default: Callable) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=default)
    path.write_text(text, encoding="utf-8")
    return len(text.encode("utf-8"))


def clean_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
