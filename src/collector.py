"""Collect and parse National Bureau of Statistics 70-city housing indices."""

from __future__ import annotations

import argparse
import csv
import html as html_lib
import os
import re
import time
import urllib.request
from urllib.parse import urljoin
from html.parser import HTMLParser
from typing import Dict, Iterable, List, Optional


URLS = {
    "2025-01": "https://www.stats.gov.cn/sj/zxfb/202502/t20250219_1958761.html",
    "2025-03": "https://www.stats.gov.cn/sj/zxfb/202504/t20250416_1959311.html",
    "2025-04": "https://www.stats.gov.cn/sj/zxfb/202505/t20250519_1959852.html",
    "2025-06": "https://www.stats.gov.cn/sj/zxfb/202507/t20250715_1960403.html",
    "2025-09": "https://www.stats.gov.cn/sj/zxfb/202510/t20251020_1961597.html",
    "2025-12": "https://www.stats.gov.cn/sj/zxfbhjd/202601/t20260119_1962319.html",
    "2026-05": "https://www.stats.gov.cn/sj/zxfb/202606/t20260616_1963946.html",
    "2026-06": "https://www.stats.gov.cn/sj/zxfbhjd/202607/t20260715_1964115.html",
}

INDEX_URL = "https://www.stats.gov.cn/sj/zxfb/index.html"
REPORT_TITLE = "70个大中城市商品住宅销售价格变动情况"


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tables: List[List[List[str]]] = []
        self._table_depth = 0
        self._rows: List[List[str]] = []
        self._row: Optional[List[str]] = None
        self._cell: Optional[List[str]] = None

    def handle_starttag(self, tag: str, attrs: object) -> None:
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._rows = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"}:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell is not None:
            self._row.append("".join(self._cell).strip())
            self._cell = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            self._rows.append(self._row)
            self._row = None
        elif tag == "table":
            if self._table_depth == 1:
                self.tables.append(self._rows)
            self._table_depth -= 1


def normalize_city(value: str) -> str:
    return re.sub(r"\s+", "", value).replace("\u3000", "")


def _number(value: str) -> float:
    return float(value.replace("—", "100").replace("-", "100"))


def _rows_to_records(table: List[List[str]], month: str, market: str, source_url: str) -> Iterable[Dict[str, object]]:
    for row in table[2:]:
        if len(row) < 6:
            continue
        width = 4 if len(row) >= 8 else 3
        for offset in range(0, len(row), width):
            if offset + 2 >= len(row):
                continue
            city = normalize_city(row[offset])
            if not city or not re.search(r"[\u4e00-\u9fff]", city):
                continue
            try:
                yield {
                    "month": month,
                    "city": city,
                    "market": market,
                    "month_on_month": _number(row[offset + 1]),
                    "yoy": _number(row[offset + 2]),
                    "year_avg": _number(row[offset + 3]) if width == 4 else None,
                    "methodology": "current",
                    "source_url": source_url,
                }
            except ValueError:
                continue


def _legacy_rows_to_records(table: List[List[str]], month: str, source_url: str) -> Iterable[Dict[str, object]]:
    """Parse 2008-2010 reports: city + overall/new/secondhand (yoy, mom)."""
    for row in table[3:]:
        if len(row) < 7 or not re.search(r"[\u4e00-\u9fff]", row[0]):
            continue
        city = normalize_city(row[0])
        if city == "全国":
            continue
        for market, yoy_index, mom_index in (("new", 3, 4), ("secondhand", 5, 6)):
            try:
                yield {
                    "month": month,
                    "city": city,
                    "market": market,
                    "month_on_month": _number(row[mom_index]),
                    "yoy": _number(row[yoy_index]),
                    "year_avg": None,
                    "methodology": "legacy",
                    "source_url": source_url,
                }
            except (IndexError, ValueError):
                continue


def parse_index_tables(html: str, month: str, source_url: str) -> List[Dict[str, object]]:
    parser = TableParser()
    parser.feed(html)
    legacy_tables = [table for table in parser.tables if any("房屋销售价格指数" in cell for row in table[:3] for cell in row)]
    if legacy_tables:
        records: List[Dict[str, object]] = []
        for table in legacy_tables[:2]:
            records.extend(_legacy_rows_to_records(table, month, source_url))
        if len(records) >= 100:
            return records
    if len(parser.tables) < 2:
        raise ValueError("页面中未找到新房和二手房指数表")
    records = list(_rows_to_records(parser.tables[0], month, "new", source_url))
    records.extend(_rows_to_records(parser.tables[1], month, "secondhand", source_url))
    return records


def fetch(url: str, retries: int = 3) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "housing-price-training/1.0"})
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                return response.read().decode("utf-8", errors="replace")
        except Exception as error:  # official site occasionally closes long chunked responses
            last_error = error
            if attempt + 1 < retries:
                time.sleep(2 ** attempt)
    raise RuntimeError(f"下载失败: {url}") from last_error


def discover_urls(start_year: int = 2015, end_year: int = 2026, max_pages: int = 260) -> Dict[str, str]:
    """Crawl the official release directory and find monthly 70-city reports."""
    found: Dict[str, str] = {}
    for page in range(max_pages):
        page_url = INDEX_URL if page == 0 else INDEX_URL.replace(".html", f"_{page}.html")
        try:
            content = fetch(page_url)
        except Exception:
            continue
        for href, title in re.findall(r"<a[^>]+href=[\"']([^\"']+)[\"'][^>]+title=[\"']([^\"']+)[\"']", content, re.S):
            title = html_lib.unescape(re.sub(r"\s+", "", title))
            match = re.search(r"(20\d{2})年(\d{1,2})月份?" + re.escape(REPORT_TITLE), title)
            if not match:
                continue
            year, month = int(match.group(1)), int(match.group(2))
            if start_year <= year <= end_year:
                found[f"{year:04d}-{month:02d}"] = urljoin(page_url, href)
        if found and min(int(key[:4]) for key in found) <= start_year:
            break
    return dict(sorted(found.items()))


def collect(output: str, urls: Dict[str, str] = URLS) -> int:
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    all_records: List[Dict[str, object]] = []
    for month, url in urls.items():
        html = fetch(url)
        month_records = parse_index_tables(html, month, url)
        if len(month_records) < 100:
            raise ValueError(f"{month} 解析记录过少: {len(month_records)}")
        all_records.extend(month_records)
    fields = ["month", "city", "market", "month_on_month", "yoy", "year_avg", "methodology", "source_url"]
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(all_records)
    return len(all_records)


def collect_local_html(output: str, files: Dict[str, str]) -> int:
    """Parse already-downloaded official HTML files into the standard schema."""
    records: List[Dict[str, object]] = []
    for month, path in files.items():
        with open(path, "r", encoding="utf-8", errors="replace") as handle:
            month_records = parse_index_tables(handle.read(), month, path)
        if len(month_records) < 100:
            raise ValueError(f"{month} 本地页面解析记录过少: {len(month_records)}")
        records.extend(month_records)
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    fields = ["month", "city", "market", "month_on_month", "yoy", "year_avg", "methodology", "source_url"]
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="data/processed/housing_indices.csv")
    parser.add_argument("--start-year", type=int, default=2008)
    parser.add_argument("--end-year", type=int, default=2026)
    parser.add_argument("--max-index-pages", type=int, default=260)
    parser.add_argument("--sample", action="store_true", help="只采集内置的少量样本月份")
    args = parser.parse_args()
    urls = URLS if args.sample else discover_urls(args.start_year, args.end_year, args.max_index_pages)
    if not urls:
        raise SystemExit("未发现月报链接，请检查网络或提高 --max-index-pages")
    print(f"发现 {len(urls)} 个月报，范围 {min(urls)} 至 {max(urls)}")
    print(f"写入 {collect(args.output, urls)} 条记录到 {args.output}")
