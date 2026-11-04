"""Script-driven, incremental data update from official sources.

One command keeps the canonical panels current without manual URL lists:

    .venv/bin/python -m src.update_data                 # latest months only
    .venv/bin/python -m src.update_data --backfill-index <long-table.csv.gz>

What it does:

1. 70-city price indices: scans the first pages of the NBS release directory
   for "N月份70个大中城市商品住宅销售价格变动情况" and fetches every month not yet
   in the panel.  ``--backfill-index`` additionally reads a third-party long
   table (e.g. taifuer/house_price_index) **only as a URL index**: every month
   is re-fetched from the official stats.gov.cn page it cites, so no
   third-party number enters the panel.
2. Merge priority: a directly fetched official page (``current``) always
   replaces a CIREA-reposted cell (``current_cirea*``).  Replacements are
   logged cell by cell, so a disagreement between the repost and the official
   page is visible instead of silently overwritten.
3. National real-estate macro panel ("1—N月份全国房地产市场基本情况") and the
   PBOC LPR series are extended the same way.

Raw HTML is cached under ``data/raw/nbs/`` so reruns are offline and the
panel is reproducible from the cache.
"""

from __future__ import annotations

import argparse
import hashlib
import html as html_lib
import json
import os
import re
from pathlib import Path
from typing import Dict, List
from urllib.parse import urljoin

import pandas as pd

from .clean import clean_price_data
from .collector import INDEX_URL, REAL_ESTATE_TITLE, REPORT_TITLE, fetch, parse_index_tables
from .macro_history import MACRO_FIELDS, _frequency
from .macro_sources import collect_lpr_history, html_to_text, parse_real_estate_metrics

from .panel import MIRROR_TRUSTED_THROUGH, PANEL_PATH  # noqa: E402

PANEL = PANEL_PATH
MACRO = "data/processed/macro_features_full.csv"
LPR = "data/processed/lpr_history.csv"
CACHE = "data/raw/nbs"
LOG = "reports/data_update_log.json"


def cached_fetch(url: str, cache_dir: str = CACHE) -> str:
    """Fetch a page once and serve later calls from the on-disk cache."""
    os.makedirs(cache_dir, exist_ok=True)
    name = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16] + ".html"
    path = Path(cache_dir) / name
    if path.exists():
        return path.read_text(encoding="utf-8")
    content = fetch(url)
    path.write_text(content, encoding="utf-8")
    return content


def discover_recent(max_pages: int = 6) -> tuple[Dict[str, str], Dict[str, str]]:
    """Scan the newest release-directory pages for 70-city and macro reports.

    Unlike ``collector.discover_urls`` there is no early exit: a monthly update
    only needs the first few pages, and both report types are collected in the
    same pass.
    """
    city: Dict[str, str] = {}
    macro: Dict[str, str] = {}
    for page in range(max_pages):
        page_url = INDEX_URL if page == 0 else INDEX_URL.replace(".html", f"_{page}.html")
        try:
            content = fetch(page_url)
        except Exception:
            continue
        for href, text in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]*>(.*?)</a>", content, re.S):
            text = html_lib.unescape(re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", text)))
            match = re.search(r"(20\d{2})年(\d{1,2})月份" + re.escape(REPORT_TITLE), text)
            if match:
                city[f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"] = urljoin(page_url, href)
                continue
            match = re.search(r"(20\d{2})年1?—?(\d{1,2})月份" + re.escape(REAL_ESTATE_TITLE), text)
            if match:
                macro[f"{int(match.group(1)):04d}-{int(match.group(2)):02d}"] = urljoin(page_url, href)
                continue
            match = re.search(r"(20\d{2})年上半年" + re.escape(REAL_ESTATE_TITLE), text)
            if match:
                macro[f"{int(match.group(1)):04d}-06"] = urljoin(page_url, href)
    return dict(sorted(city.items())), dict(sorted(macro.items()))


def mirror_url_index(path: str) -> Dict[str, str]:
    """Official report URL per month, read from a third-party long table.

    Only the ``period`` and ``source_url`` columns are used, and only URLs on
    the official stats.gov.cn domain are kept.
    """
    frame = pd.read_csv(path, encoding="utf-8-sig", usecols=["period", "source_url"])
    frame = frame[frame["source_url"].astype(str).str.contains(r"^https?://www\.stats\.gov\.cn/", regex=True)]
    return frame.drop_duplicates("period").set_index("period")["source_url"].sort_index().to_dict()


def collect_months(urls: Dict[str, str], cache_dir: str = CACHE) -> pd.DataFrame:
    """Fetch and parse official 70-city pages; months that fail are reported, not fatal."""
    records: List[dict] = []
    for month, url in sorted(urls.items()):
        try:
            content = cached_fetch(url, cache_dir)
            rows = parse_index_tables(content, month, url)
        except Exception as error:  # a malformed archive page must not abort a batch
            print(f"  {month}: failed ({str(error)[:60]})")
            continue
        if len(rows) < 100:
            print(f"  {month}: only {len(rows)} rows parsed, skipped")
            continue
        records.extend(rows)
    return pd.DataFrame(records)


def merge_panel(existing_path: str, new_rows: pd.DataFrame, output_path: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Merge new official rows into the panel and log value changes.

    Returns (merged panel, replaced cells whose values differ).
    """
    existing = pd.read_csv(existing_path) if os.path.exists(existing_path) else pd.DataFrame()
    key = ["month", "city", "market"]
    changed = pd.DataFrame()
    if len(existing) and len(new_rows):
        joined = existing.merge(new_rows, on=key, suffixes=("_old", "_new"))
        diff = (joined["month_on_month_old"] - joined["month_on_month_new"]).abs().gt(1e-9) | (
            joined["yoy_old"] - joined["yoy_new"]
        ).abs().gt(1e-9)
        changed = joined.loc[diff, key + ["month_on_month_old", "month_on_month_new", "yoy_old", "yoy_new", "methodology_old"]]
    tmp = Path(output_path).with_suffix(".tmp.csv")
    pd.concat([new_rows, existing], ignore_index=True).to_csv(tmp, index=False)
    merged = clean_price_data(str(tmp), output_path)
    tmp.unlink()
    return merged, changed


MIRROR_SOURCE = "https://github.com/wofeiwo/70city-price-skill (data/70cityprice.csv; derived from the NBS database)"
MIRROR_COLUMNS = {"new": "CommodityHouseIDX", "secondhand": "SecondHandIDX"}


def legacy_mirror_rows(path: str, before: str, official: pd.DataFrame | None = None) -> tuple[pd.DataFrame, dict]:
    """2006-2010 history from a third-party dump of the NBS database.

    Official pages for these months are not in the release directory, so the
    dump is the only source.  It is used *only* for months before `before`
    (the first month with directly fetched official pages), tagged
    ``legacy_mirror`` and never mixed into the official months.  Trust comes
    from an agreement check on the months where both exist: if `official` is
    given, the dump is compared with it for every month that predates 2021
    (from 2021 on the dump swaps four city pairs, which is why those months are
    never taken from it) and the result is returned for the update log.
    """
    raw = pd.read_csv(path, dtype=str)
    raw["month"] = pd.to_datetime(raw["DATE"]).dt.strftime("%Y-%m")
    rows = []
    for market, column in MIRROR_COLUMNS.items():
        raw[column] = pd.to_numeric(raw[column], errors="coerce")
        wide = raw.pivot_table(index=["month", "CITY"], columns="FixedBase", values=column, aggfunc="first")
        wide = wide.rename(columns={"环比": "month_on_month", "同比": "yoy"})[["month_on_month", "yoy"]].dropna().reset_index()
        wide["market"], wide["city"] = market, wide["CITY"]
        rows.append(wide.drop(columns="CITY"))
    frame = pd.concat(rows, ignore_index=True)
    frame["year_avg"], frame["methodology"], frame["source_url"] = None, "legacy_mirror", MIRROR_SOURCE
    check: dict = {"source": MIRROR_SOURCE}
    if official is not None and len(official):
        both = frame[frame["month"].between(official["month"].min(), "2020-12")].merge(
            official, on=["month", "city", "market"], suffixes=("_mirror", "_official"))
        check.update({
            "compared_cells": int(len(both)),
            "identical_cells": int(((both["month_on_month_mirror"] == both["month_on_month_official"])
                                    & (both["yoy_mirror"] == both["yoy_official"])).sum()),
            "months": [both["month"].min(), both["month"].max()] if len(both) else None,
        })
    return frame[frame["month"] < before].copy(), check




def mirror_gap_rows(path: str, panel: pd.DataFrame, first: str = "2011-02") -> pd.DataFrame:
    """Rows for (market, month) combinations absent from the panel, taken from the mirror.

    Only months up to MIRROR_TRUSTED_THROUGH are used: the dump agrees with the
    directly fetched official pages in every comparable cell up to there.
    """
    full, _ = legacy_mirror_rows(path, before="9999-12")
    full = full[full["month"].between(first, MIRROR_TRUSTED_THROUGH)]
    have = set(zip(panel["market"], panel["month"]))
    keep = [(m, mo) not in have for m, mo in zip(full["market"], full["month"])]
    out = full[keep].copy()
    out["methodology"] = "mirror_filled"
    return out


def update_macro(urls: Dict[str, str], macro_path: str = MACRO, lpr_path: str = LPR) -> List[str]:
    """Append macro months newer than the panel's last month."""
    frame = pd.read_csv(macro_path) if os.path.exists(macro_path) else pd.DataFrame(columns=MACRO_FIELDS)
    have = set(frame["month"].astype(str))
    added: List[str] = []
    rows = []
    for month, url in urls.items():
        if month in have:
            continue
        parsed = parse_real_estate_metrics(html_to_text(cached_fetch(url)), month, url)
        if parsed.get("development_investment_value") is None:
            print(f"  macro {month}: no investment figure parsed, skipped")
            continue
        row = {"month": month, "frequency": _frequency(month), "methodology": "cumulative_ytd_official"}
        row.update({field: parsed.get(field) for field in MACRO_FIELDS[3:]})
        rows.append(row)
        added.append(month)
    if rows:
        frame = pd.concat([frame, pd.DataFrame(rows)], ignore_index=True)
    if os.path.exists(lpr_path):
        lpr = pd.read_csv(lpr_path).set_index("month")
        for column in ("lpr_1y", "lpr_5y", "source_url_lpr"):
            if column in lpr.columns:
                frame[column] = frame["month"].map(lpr[column]).combine_first(frame.get(column, pd.Series(index=frame.index, dtype=object)))
    frame.sort_values("month").to_csv(macro_path, index=False)
    return added


def update_lpr(lpr_path: str = LPR, year: int | None = None) -> List[str]:
    """Re-collect the current year's LPR announcements and merge them in."""
    year = year or pd.Timestamp.today().year
    tmp = "/tmp/lpr_update.csv"
    collect_lpr_history(tmp, start_year=year, end_year=year)
    new = pd.read_csv(tmp)
    old = pd.read_csv(lpr_path) if os.path.exists(lpr_path) else pd.DataFrame(columns=new.columns)
    added = sorted(set(new["month"]) - set(old["month"]))
    merged = pd.concat([new, old]).drop_duplicates("month", keep="first").sort_values("month")
    merged.to_csv(lpr_path, index=False)
    return added


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--panel", default=PANEL)
    parser.add_argument("--base", default="", help="seed panel when --panel does not exist yet (e.g. clean_v3)")
    parser.add_argument("--pages", type=int, default=6, help="release-directory pages to scan")
    parser.add_argument("--backfill-index", default="", help="third-party long table used only as an official-URL index")
    parser.add_argument("--start-month", default="2011-01")
    parser.add_argument("--legacy-mirror", default="", help="third-party 2006+ dump; used only for months before --legacy-before")
    parser.add_argument("--legacy-before", default="2011-02")
    parser.add_argument("--skip-macro", action="store_true")
    parser.add_argument("--skip-lpr", action="store_true")
    parser.add_argument("--log", default=LOG)
    args = parser.parse_args()

    if not os.path.exists(args.panel) and args.base:
        pd.read_csv(args.base).to_csv(args.panel, index=False)
    existing = pd.read_csv(args.panel) if os.path.exists(args.panel) else pd.DataFrame(columns=["month", "methodology"])
    official_months = set(existing.loc[existing["methodology"].eq("current"), "month"])

    city_urls, macro_urls = discover_recent(args.pages)
    targets = {m: u for m, u in city_urls.items() if m not in official_months}
    if args.backfill_index:
        for month, url in mirror_url_index(args.backfill_index).items():
            if month >= args.start_month and month not in official_months:
                targets.setdefault(month, url)
    print(f"70-city: {len(targets)} months to fetch")
    new_rows = collect_months(targets)
    log: Dict[str, object] = {"run": pd.Timestamp.now().isoformat(timespec="seconds")}
    if len(new_rows):
        merged, changed = merge_panel(args.panel, new_rows, args.panel)
        log["city_months_fetched"] = sorted(new_rows["month"].unique().tolist())
        log["panel_rows"] = int(len(merged))
        log["panel_range"] = [merged["month"].min(), merged["month"].max()]
        log["replaced_cells_with_different_values"] = changed.to_dict("records")
        print(f"panel: {len(merged)} rows, {merged['month'].min()} → {merged['month'].max()}; "
              f"{len(changed)} reposted cells corrected by official pages")
    if args.legacy_mirror:
        current = pd.read_csv(args.panel)
        old_rows, check = legacy_mirror_rows(args.legacy_mirror, args.legacy_before,
                                             current[current["methodology"].eq("current")])
        have = set(current.loc[current["methodology"].eq("legacy_mirror"), "month"])
        old_rows = old_rows[~old_rows["month"].isin(have)]
        gaps = mirror_gap_rows(args.legacy_mirror, current)
        if len(gaps):
            log["mirror_filled_gaps"] = sorted({f"{m}:{mo}" for m, mo in zip(gaps["market"], gaps["month"])})
            print(f"mirror gap fill: {gaps['month'].nunique()} months, {len(gaps)} cells")
            old_rows = pd.concat([old_rows, gaps], ignore_index=True)
        if len(old_rows):
            merged, _ = merge_panel(args.panel, old_rows, args.panel)
            log["legacy_mirror"] = {**check, "months_added": int(old_rows["month"].nunique()), "panel_range": [merged["month"].min(), merged["month"].max()]}
            print(f"legacy mirror: +{old_rows['month'].nunique()} months, panel now {merged['month'].min()} → {merged['month'].max()}; check {check}")
    if not args.skip_lpr:
        log["lpr_months_added"] = update_lpr()
    if not args.skip_macro:
        log["macro_months_added"] = update_macro(macro_urls)
    # append-only: later runs must not erase the record of earlier corrections
    log_path = Path(args.log)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    history = json.loads(log_path.read_text(encoding="utf-8")) if log_path.exists() else []
    history = [history] if isinstance(history, dict) else history
    history.append(log)
    log_path.write_text(json.dumps(history, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in log.items() if k != "replaced_cells_with_different_values"}, ensure_ascii=False, default=str))


if __name__ == "__main__":
    main()
