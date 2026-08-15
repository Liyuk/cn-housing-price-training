"""Small, dependency-light parsers for national housing and financing indicators."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import sys
from html.parser import HTMLParser
from typing import Dict, Optional

from .collector import fetch


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts = []

    def handle_data(self, data: str) -> None:
        self.parts.append(data)

    def text(self) -> str:
        return re.sub(r"\s+", " ", " ".join(self.parts)).strip()


def html_to_text(content: str) -> str:
    parser = TextParser()
    parser.feed(content)
    return parser.text()


def _first_number(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text)
    return float(match.group(1).replace(",", "")) if match else None


def parse_lpr(text: str, month: str, source_url: str) -> Dict[str, object]:
    """Parse a PBOC LPR announcement into one monthly observation.

    Older announcements (pre-2024) insert spaces inside labels, e.g.
    "1 年期 LPR 为 3.65%", so the label is matched space-tolerantly.
    """
    compact = re.sub(r"\s+", "", text)
    return {
        "month": month,
        "lpr_1y": _first_number(r"1年期LPR为\s*([0-9.]+)%", compact),
        "lpr_5y": _first_number(r"5年期以上LPR为\s*([0-9.]+)%", compact),
        "source_url": source_url,
        "source_url_lpr": source_url,
    }


def _yoy(pattern: str, text: str) -> Optional[float]:
    """Extract a signed YoY percentage like -18.0 (下降) or +3.2 (增长)."""
    match = re.search(pattern, text)
    if not match:
        return None
    direction = match.group(1)
    value = float(match.group(2).replace(",", ""))
    return -value if direction == "下降" else value


def parse_real_estate_metrics(text: str, month: str, source_url: str) -> Dict[str, object]:
    """Parse headline national real-estate metrics from an NBS release."""
    normalized = re.sub(r"\s+", " ", text)
    return {
        "month": month,
        "development_investment_value": _first_number(r"房地产开发投资(?:完成额)?\s*([0-9,.]+)\s*亿元", normalized),
        "development_investment_yoy": _yoy(r"房地产开发投资(?:完成额)?\s*[0-9,.]+\s*亿元[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "housing_investment_value": _first_number(r"其中[，,:：]住宅投资\s*([0-9,.]+)\s*亿元", normalized),
        "housing_investment_yoy": _yoy(r"住宅投资\s*[0-9,.]+\s*亿元[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "construction_area": _first_number(r"房屋施工面积\s*([0-9,.]+)\s*万平方米", normalized),
        "construction_area_yoy": _yoy(r"房屋施工面积\s*[0-9,.]+\s*万平方米[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "new_starts_area": _first_number(r"房屋新开工面积\s*([0-9,.]+)\s*万平方米", normalized),
        "new_starts_area_yoy": _yoy(r"房屋新开工面积\s*[0-9,.]+\s*万平方米[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "completions_area": _first_number(r"房屋竣工面积\s*([0-9,.]+)\s*万平方米", normalized),
        "completions_area_yoy": _yoy(r"房屋竣工面积\s*[0-9,.]+\s*万平方米[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "new_home_sales_area": _first_number(r"(?:新建)?商品房销售面积\s*([0-9,.]+)\s*万平方米", normalized),
        "new_home_sales_area_yoy": _yoy(r"(?:新建)?商品房销售面积\s*[0-9,.]+\s*万平方米[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "new_home_sales_value": _first_number(r"(?:新建)?商品房销售额\s*([0-9,.]+)\s*亿元", normalized),
        "new_home_sales_value_yoy": _yoy(r"(?:新建)?商品房销售额\s*[0-9,.]+\s*亿元[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "inventory_area": _first_number(r"商品房待售面积\s*([0-9,.]+)\s*万平方米", normalized),
        "inventory_area_yoy": _yoy(r"商品房待售面积\s*[0-9,.]+\s*万平方米[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "developer_funding": _first_number(r"房地产开发企业到位资金\s*([0-9,.]+)\s*亿元", normalized),
        "developer_funding_yoy": _yoy(r"房地产开发企业到位资金\s*[0-9,.]+\s*亿元[，,]?(?:同比)?(下降|增长)\s*([0-9.]+)%", normalized),
        "source_url": source_url,
        "source_url_real_estate": source_url,
    }


def collect(output: str, lpr_month: str, lpr_url: str, real_estate_month: str, real_estate_url: str) -> None:
    lpr = parse_lpr(html_to_text(fetch(lpr_url)), lpr_month, lpr_url)
    real_estate = parse_real_estate_metrics(html_to_text(fetch(real_estate_url)), real_estate_month, real_estate_url)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=sorted(set(lpr) | set(real_estate)))
        writer.writeheader()
        writer.writerow({**real_estate, **lpr})


LPR_LIST_URL = "https://www.pbc.gov.cn/zhengcehuobisi/125207/125213/125440/3876551/index.html"


def collect_lpr_history(output: str, start_year: int = 2019, end_year: int = 2026, max_pages: int = 8) -> int:
    """Collect the monthly LPR series from the PBOC announcement archive.

    Each listing page carries ~19 monthly announcements, newest first.  We walk
    the paginated archive, parse each announcement for the 1y and 5y LPR, and
    keep the newest observation per calendar month (announcements are issued on
    the 20th; only the month matters for the macro panel).
    """
    import time
    from urllib.parse import urljoin

    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    monthly: Dict[str, Dict[str, object]] = {}
    for page in range(1, max_pages + 1):
        page_url = LPR_LIST_URL if page == 1 else urljoin(LPR_LIST_URL, f"de24575c-{page}.html")
        try:
            html = fetch(page_url)
        except Exception:
            break
        links = re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, re.S)
        for href, text in links:
            text = re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", text))
            if "全国银行间同业拆借中心受权公布" not in text:
                continue
            match = re.search(r"(20\d{2})年(\d{1,2})月(\d{1,2})日", text)
            if not match:
                continue
            year, month = int(match.group(1)), int(match.group(2))
            if not (start_year <= year <= end_year):
                continue
            key = f"{year:04d}-{month:02d}"
            full_url = urljoin(page_url, href)
            try:
                announcement = html_to_text(fetch(full_url))
                parsed = parse_lpr(announcement, key, full_url)
            except Exception:
                continue
            if parsed.get("lpr_1y") is None or parsed.get("lpr_5y") is None:
                continue
            # keep the newest announcement for the month
            monthly[key] = parsed
            time.sleep(0.5)  # politeness delay; PBOC rate-limits bursts
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["month", "lpr_1y", "lpr_5y", "source_url", "source_url_lpr"])
        writer.writeheader()
        for key in sorted(monthly):
            row = monthly[key]
            writer.writerow({
                "month": key,
                "lpr_1y": row["lpr_1y"],
                "lpr_5y": row["lpr_5y"],
                "source_url": row["source_url"],
                "source_url_lpr": row["source_url_lpr"],
            })
    return len(monthly)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/processed/macro_features.csv")
    parser.add_argument("--lpr-history", action="store_true", help="collect the full LPR series from the PBOC archive")
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--lpr-month", required="--lpr-history" not in sys.argv)
    parser.add_argument("--lpr-url", required="--lpr-history" not in sys.argv)
    parser.add_argument("--real-estate-month", required="--lpr-history" not in sys.argv)
    parser.add_argument("--real-estate-url", required="--lpr-history" not in sys.argv)
    args = parser.parse_args()
    if args.lpr_history:
        count = collect_lpr_history(args.output, args.start_year, args.end_year)
        print(json.dumps({"output": args.output, "months": count}, ensure_ascii=False))
    else:
        collect(args.output, args.lpr_month, args.lpr_url, args.real_estate_month, args.real_estate_url)
        print(json.dumps({"output": args.output}, ensure_ascii=False))
