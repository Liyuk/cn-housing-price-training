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


def collect(url: str, output: str) -> int:
    records = parse_beijing_stats(fetch(url), url)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    fields = ["month", "city", "district", "market", "online_signing_count", "online_signing_area_m2", "source_url"]
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="https://zjw.beijing.gov.cn/bjjs/fdcjy/wqht/fcsjtj/index.shtml")
    parser.add_argument("--output", default="data/processed/beijing_district_transactions.csv")
    args = parser.parse_args()
    print(collect(args.url, args.output))
