"""Parse Beijing Housing Commission district-level online-signing statistics."""

from __future__ import annotations

import argparse
import csv
import os
import re
from typing import Dict, List

from .collector import TableParser, fetch


def parse_beijing_stats(html: str, source_url: str) -> List[Dict[str, object]]:
    month_match = re.search(r"(20\d{2})年\s*(\d{1,2})月存量房网上签约", html)
    if not month_match:
        raise ValueError("未找到北京存量房网签月份")
    month = f"{month_match.group(1)}-{int(month_match.group(2)):02d}"
    parser = TableParser()
    parser.feed(html)
    district_table = next((table for table in parser.tables if any("所在区" in cell for row in table for cell in row)), None)
    if not district_table:
        raise ValueError("未找到北京分区网签表")
    records: List[Dict[str, object]] = []
    for start in range(0, len(district_table), 3):
        block = district_table[start:start + 3]
        if len(block) < 3 or len(block[0]) != len(block[1]) or len(block[1]) != len(block[2]):
            continue
        for index in range(1, len(block[0])):
            district = re.sub(r"\s+", "", block[0][index])
            if not district or district == "全市":
                continue
            try:
                records.append({
                    "month": month,
                    "city": "北京",
                    "district": district,
                    "market": "secondhand",
                    "online_signing_count": float(block[1][index]),
                    "online_signing_area_m2": float(block[2][index]),
                    "source_url": source_url,
                })
            except ValueError:
                continue
    return records


def parse_annual_transactions(html: str, source_url: str) -> List[Dict[str, object]]:
    """Parse the 2020-2024 annual transaction tables (new and secondhand).

    The page's sub-tabs order is 新建商品房网签情况 then 存量房交易情况, so the
    two annual tables are assigned ``new`` then ``secondhand`` by DOM order.
    """
    parser = TableParser()
    parser.feed(html)
    records: List[Dict[str, object]] = []
    markets = iter(["new", "secondhand"])
    for table in parser.tables:
        if not table or not table[0]:
            continue
        header_row = "".join(table[0])
        if "住宅套数" not in header_row or "住宅面积" not in header_row:
            continue
        try:
            market = next(markets)
        except StopIteration:
            continue
        for row in table[1:]:
            if not row or len(row) < 4:
                continue
            year = re.sub(r"\D", "", row[0])
            try:
                housing_units = float(row[1])
            except ValueError:
                continue
            records.append({
                "year": year,
                "city": "北京",
                "market": market,
                "residential_units_wan": housing_units,
                "residential_area_wan_m2": float(row[2]),
                "non_residential_area_wan_m2": float(row[3]),
                "source_url": source_url,
            })
    return records


def collect(url: str, output: str, annual_output: str) -> int:
    records = parse_beijing_stats(fetch(url), url)
    annual = parse_annual_transactions(fetch(url), url)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    fields = ["month", "city", "district", "market", "online_signing_count", "online_signing_area_m2", "source_url"]
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    if annual_output and annual:
        os.makedirs(os.path.dirname(annual_output) or ".", exist_ok=True)
        annual_fields = ["year", "city", "market", "residential_units_wan", "residential_area_wan_m2", "non_residential_area_wan_m2", "source_url"]
        with open(annual_output, "w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=annual_fields)
            writer.writeheader()
            writer.writerows(annual)
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://zjw.beijing.gov.cn/bjjs/fdcjy/wqht/fcsjtj/index.shtml")
    parser.add_argument("--output", default="data/processed/beijing_district_transactions.csv")
    parser.add_argument("--annual-output", default="data/processed/beijing_annual_transactions.csv")
    args = parser.parse_args()
    print(collect(args.url, args.output, args.annual_output))
