"""Parse the public CIREA 70-city second-hand index attachments."""

from __future__ import annotations

import argparse
import csv
import os
import re
import subprocess
import tempfile
from typing import Dict, Iterable, List
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from .collector import normalize_city


WORD_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def _docx_tables(path: str) -> List[List[List[str]]]:
    with ZipFile(path) as archive:
        root = ET.fromstring(archive.read("word/document.xml"))
    tables = []
    for table in root.findall(".//w:tbl", WORD_NS):
        rows = []
        for row in table.findall("./w:tr", WORD_NS):
            cells = []
            for cell in row.findall("./w:tc", WORD_NS):
                cells.append("".join(cell.itertext()).replace("\n", " ").strip())
            rows.append(cells)
        tables.append(rows)
    return tables


def parse_cirea_tables(tables: List[List[List[str]]], year: int, source_url: str) -> List[Dict[str, object]]:
    records: List[Dict[str, object]] = []
    for table_index, table in enumerate(tables[:12], start=1):
        for row in table[2:]:
            if len(row) < 8:
                continue
            for offset in (0, 4):
                city = normalize_city(row[offset])
                if not city or city == "全国":
                    continue
                try:
                    records.append({
                        "month": f"{year:04d}-{table_index:02d}",
                        "city": city,
                        "market": "secondhand",
                        "month_on_month": float(row[offset + 1]),
                        "yoy": float(row[offset + 2]),
                        "year_avg": float(row[offset + 3]),
                        "methodology": "current_cirea",
                        "source_url": source_url,
                    })
                except ValueError:
                    continue
    return records


def collect_docx(path: str, year: int, output: str, source_url: str) -> int:
    records = parse_cirea_tables(_docx_tables(path), year, source_url)
    if len(records) < 800:
        raise ValueError(f"CIREA 文档解析记录过少: {len(records)}")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    fields = ["month", "city", "market", "month_on_month", "yoy", "year_avg", "methodology", "source_url"]
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return len(records)


def parse_cirea_text(text: str, source_url: str) -> List[Dict[str, object]]:
    """Parse legacy .doc files after conversion with macOS textutil.

    The old attachment is a two-column table exported as text. BEL characters
    separate cells, so each city is followed by mom, yoy and base-index values.
    """
    records: List[Dict[str, object]] = []
    headings = list(re.finditer(r"(20\d{2})年(\d{1,2})月70个大中城市二手住宅销售价格指数", text))
    for index, heading in enumerate(headings):
        year, month = int(heading.group(1)), int(heading.group(2))
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        section = text[heading.end():end].replace("\x07", "|")
        tokens = [token.strip() for token in section.split("|")]
        for position in range(len(tokens) - 3):
            city = normalize_city(tokens[position].replace("\ufeff", ""))
            if not city or city in {"城市", "二手住宅价格指数", "环比", "同比", "定基"}:
                continue
            if not re.search(r"[\u4e00-\u9fff]", city):
                continue
            try:
                mom, yoy, base = (float(tokens[position + offset]) for offset in (1, 2, 3))
            except ValueError:
                continue
            records.append({
                "month": f"{year:04d}-{month:02d}",
                "city": city,
                "market": "secondhand",
                "month_on_month": mom,
                "yoy": yoy,
                "year_avg": base,
                "methodology": "current_cirea_legacy_doc",
                "source_url": source_url,
            })
    return records


def collect_doc(path: str, output: str, source_url: str) -> int:
    """Convert a legacy .doc attachment to text and write normalized CSV."""
    with tempfile.NamedTemporaryFile(suffix=".txt") as temporary:
        subprocess.run(["textutil", "-convert", "txt", "-output", temporary.name, path], check=True)
        with open(temporary.name, "r", encoding="utf-8", errors="replace") as handle:
            records = parse_cirea_text(handle.read(), source_url)
    if len(records) < 3000:
        raise ValueError(f"CIREA 旧文档解析记录过少: {len(records)}")
    os.makedirs(os.path.dirname(output) or ".", exist_ok=True)
    fields = ["month", "city", "market", "month_on_month", "yoy", "year_avg", "methodology", "source_url"]
    with open(output, "w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(records)
    return len(records)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--year", type=int)
    parser.add_argument("--output", default="data/processed/cirea_secondhand.csv")
    parser.add_argument("--source-url", required=True)
    parser.add_argument("--legacy-doc", action="store_true")
    args = parser.parse_args()
    if args.legacy_doc:
        print(collect_doc(args.input, args.output, args.source_url))
    else:
        if args.year is None:
            raise SystemExit("非 legacy-doc 模式必须提供 --year")
        print(collect_docx(args.input, args.year, args.output, args.source_url))
