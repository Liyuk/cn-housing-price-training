"""Collect Beijing/Chongqing district-level residential price reports from creprice.cn.

creprice.cn publishes monthly district reports per city, e.g.
https://www.creprice.cn/report/bj/2025-04.html.  Each page carries two tables:
district average residential unit price (yuan/m², sometimes in 万 units) and
district average rent.  This module parses the price table into a tidy
monthly panel keyed by (city, district, month), keeping the reported MoM
change and a stable source URL so downstream labeling can flag the rows as
public third-party listing/market estimates rather than official transaction
prices.
"""

from __future__ import annotations

import argparse
import csv
import os
import re
import urllib.request
from typing import Dict, List

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36"
    ),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
}

# 万-units: "11.9万" -> 119000
_WAN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)万$")


def _city_code(city: str) -> str:
    return {"北京": "bj", "重庆": "cq"}[city]


def _fetch(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = bytearray()
        while True:
            chunk = response.read(4096)
            if not chunk:
                break
            raw.extend(chunk)
        for encoding in ("utf-8", "gb18030"):
            try:
                return bytes(raw).decode(encoding)
            except UnicodeDecodeError:
                continue
        return bytes(raw).decode("utf-8", errors="replace")


def _parse_price_rows(html: str) -> List[Dict[str, object]]:
    """Return district price rows from a creprice city report page."""
    rows: List[Dict[str, object]] = []
    for table in re.findall(r"<table.*?</table>", html, re.S):
        header = re.sub(r"\s+", "", re.sub(r"<[^>]+>", " ", table))
        if "平均单价" not in header:
            continue
        # Keep the residential unit-price table and exclude the rent table,
        # whose column is labelled 平均单价（元/月/㎡）.
        if "元/月/㎡" in header:
            continue
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            cells = [
                re.sub(r"\s+", "", re.sub(r"<[^>]+>", "", cell))
                for cell in re.findall(r"<t[dh].*?</t[dh]>", row, re.S)
            ]
            if len(cells) < 5 or cells[0].isdigit() is False:
                continue
            district = re.sub(r"区$", "", cells[1])
            price_text = cells[3]
            mom_text = cells[4]
            price = None
            wan = _WAN.match(price_text)
            if wan:
                price = float(wan.group(1)) * 10_000
            else:
                try:
                    price = float(price_text)
                except ValueError:
                    price = None
            if price is None:
                continue
            mom = None
            mom_match = re.search(r"([+\-])?([0-9]+(?:\.[0-9]+)?)%", mom_text)
            if mom_match:
                sign = -1.0 if mom_match.group(1) == "-" else 1.0
                mom = round(sign * float(mom_match.group(2)), 2)
            rows.append({
                "district": district,
                "price_yuan_m2": price,
                "price_mom_pct": mom,
            })
    return rows


def collect(city: str, months: List[str], output: str) -> int:
    code = _city_code(city)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    fields = [
        "city", "district", "month", "market",
        "price_yuan_m2", "price_mom_pct", "source_url",
        "source_type", "methodology",
    ]
    total = 0
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for month in months:
            url = f"https://www.creprice.cn/report/{code}/{month}.html"
            html = _fetch(url)
            for row in _parse_price_rows(html):
                writer.writerow({
                    "city": city,
                    "district": row["district"],
                    "month": month,
                    "market": "residential",
                    "price_yuan_m2": row["price_yuan_m2"],
                    "price_mom_pct": row["price_mom_pct"],
                    "source_url": url,
                    "source_type": "third_party_report",
                    "methodology": "reported_avg_listing_price_top10",
                })
                total += 1
    return total


def _month_range(start: str, end: str) -> List[str]:
    """Inclusive YYYY-MM range, e.g. 2025-04..2026-06."""
    from datetime import date
    months: List[str] = []
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    cursor = date(y, m, 1)
    end_date = date(ey, em, 1)
    while cursor <= end_date:
        months.append(cursor.strftime("%Y-%m"))
        if cursor.month == 12:
            cursor = cursor.replace(year=cursor.year + 1, month=1)
        else:
            cursor = cursor.replace(month=cursor.month + 1)
    return months


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--city", default="北京")
    parser.add_argument("--start", default="2025-01")
    parser.add_argument("--end", default="2026-06")
    parser.add_argument("--months", default="", help="comma separated YYYY-MM list, overrides start/end")
    parser.add_argument("--output", default="data/processed/creprice_beijing_district_prices.csv")
    args = parser.parse_args()
    months = [m.strip() for m in args.months.split(",") if m.strip()] if args.months else _month_range(args.start, args.end)
    print(collect(args.city, months, args.output))
