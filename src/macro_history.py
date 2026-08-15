"""Build the full national macro panel from historical NBS releases.

The monthly "全国房地产市场基本情况" release carries cumulative-YTD real-estate
headline metrics.  This module walks the discovered URL map, parses each report
into the standard macro schema (value + YoY), and merges it with the already
present rows so the panel is complete for the covered range.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
from typing import Dict, List, Optional

from .collector import fetch
from .macro_sources import html_to_text, parse_real_estate_metrics

MACRO_FIELDS = [
    "month", "frequency", "methodology",
    "development_investment_value", "development_investment_yoy",
    "housing_investment_value", "housing_investment_yoy",
    "construction_area", "construction_area_yoy",
    "new_starts_area", "new_starts_area_yoy",
    "completions_area", "completions_area_yoy",
    "new_home_sales_area", "new_home_sales_area_yoy",
    "new_home_sales_value", "new_home_sales_value_yoy",
    "inventory_area", "inventory_area_yoy",
    "developer_funding", "developer_funding_yoy",
    "source_url_real_estate",
]


def _frequency(month: str) -> str:
    """YTD label from a month key like 2024-06 -> YTD_1_6."""
    end_month = int(month.split("-")[1])
    return f"YTD_1_{end_month}"


def collect_real_estate_history(urls: Dict[str, str], output: str) -> int:
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    rows: List[Dict[str, object]] = []
    for month, url in sorted(urls.items()):
        try:
            text = html_to_text(fetch(url))
        except Exception as error:
            print(f"  {month}: fetch failed ({str(error)[:40]})")
            continue
        parsed = parse_real_estate_metrics(text, month, url)
        # skip months where the headline investment figure did not parse
        if parsed.get("development_investment_value") is None:
            print(f"  {month}: no investment parsed, skipping")
            continue
        row = {
            "month": month,
            "frequency": _frequency(month),
            "methodology": "cumulative_ytd_official",
        }
        for field in MACRO_FIELDS[3:]:
            row[field] = parsed.get(field)
        rows.append(row)
        print(f"  {month}: OK (dev_inv={row['development_investment_value']})")
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=MACRO_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def merge_with_existing(new_path: str, existing_path: str, output_path: str, lpr_path: str = "") -> int:
    """Merge the newly collected rows with the existing macro panel and LPR."""
    existing: Dict[str, Dict[str, str]] = {}
    if os.path.exists(existing_path):
        with open(existing_path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                existing[row["month"]] = dict(row)
    with open(new_path, encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            existing[row["month"]] = dict(row)
    # attach LPR columns from the history file
    if lpr_path and os.path.exists(lpr_path):
        with open(lpr_path, encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                month = row["month"]
                if month in existing:
                    existing[month]["lpr_1y"] = row.get("lpr_1y", "")
                    existing[month]["lpr_5y"] = row.get("lpr_5y", "")
                    existing[month]["source_url_lpr"] = row.get("source_url_lpr", "")
    # union of columns
    fields: List[str] = []
    for row in existing.values():
        for key in row:
            if key not in fields:
                fields.append(key)
    with open(output_path, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for month in sorted(existing):
            writer.writerow({key: existing[month].get(key, "") for key in fields})
    return len(existing)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--urls", default="/tmp/nbs_real_estate_urls.json")
    parser.add_argument("--output", default="data/processed/macro_features_history.csv")
    parser.add_argument("--merge-output", default="data/processed/macro_features_full.csv")
    parser.add_argument("--existing", default="data/processed/macro_features.csv")
    parser.add_argument("--lpr", default="data/processed/lpr_history.csv")
    args = parser.parse_args()
    with open(args.urls, encoding="utf-8") as handle:
        url_map = json.load(handle)
    print(f"collected {collect_real_estate_history(url_map, args.output)} months")
    print(f"merged {merge_with_existing(args.output, args.existing, args.merge_output, args.lpr)} rows")
