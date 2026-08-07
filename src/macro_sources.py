"""Small, dependency-light parsers for national housing and financing indicators."""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
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
    """Parse a PBOC LPR announcement into one monthly observation."""
    return {
        "month": month,
        "lpr_1y": _first_number(r"1年期LPR为\s*([0-9.]+)%", text),
        "lpr_5y": _first_number(r"5年期以上LPR为\s*([0-9.]+)%", text),
        "source_url": source_url,
        "source_url_lpr": source_url,
    }


def parse_real_estate_metrics(text: str, month: str, source_url: str) -> Dict[str, object]:
    """Parse headline national real-estate metrics from an NBS release."""
    normalized = re.sub(r"\s+", " ", text)
    return {
        "month": month,
        "development_investment_value": _first_number(r"房地产开发投资(?:完成额)?\s*([0-9,.]+)\s*亿元", normalized),
        "housing_investment_value": _first_number(r"其中：住宅投资\s*([0-9,.]+)\s*亿元", normalized),
        "construction_area": _first_number(r"房屋施工面积\s*([0-9,.]+)\s*万平方米", normalized),
        "new_starts_area": _first_number(r"房屋新开工面积\s*([0-9,.]+)\s*万平方米", normalized),
        "completions_area": _first_number(r"房屋竣工面积\s*([0-9,.]+)\s*万平方米", normalized),
        "new_home_sales_area": _first_number(r"新建商品房销售面积\s*([0-9,.]+)\s*万平方米", normalized),
        "new_home_sales_value": _first_number(r"新建商品房销售额\s*([0-9,.]+)\s*亿元", normalized),
        "inventory_area": _first_number(r"商品房待售面积\s*([0-9,.]+)\s*万平方米", normalized),
        "developer_funding": _first_number(r"房地产开发企业到位资金\s*([0-9,.]+)\s*亿元", normalized),
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


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/processed/macro_features.csv")
    parser.add_argument("--lpr-month", required=True)
    parser.add_argument("--lpr-url", required=True)
    parser.add_argument("--real-estate-month", required=True)
    parser.add_argument("--real-estate-url", required=True)
    args = parser.parse_args()
    collect(args.output, args.lpr_month, args.lpr_url, args.real_estate_month, args.real_estate_url)
    print(json.dumps({"output": args.output}, ensure_ascii=False))
