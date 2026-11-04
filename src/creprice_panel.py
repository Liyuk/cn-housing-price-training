"""Multi-city district price and rent panel from creprice.cn monthly reports.

creprice.cn publishes one report page per city and month
(``/report/<city code>/<YYYY-MM>.html``) with two top-10 district rankings:
average residential price (yuan/m²) and average rent (yuan/month/m²).  The
page's own 售租比 column is commented out in the HTML, so the gross rental
yield is derived here as ``rent × 12 / price`` where both rankings list the
same district.

Interface: ``collect(cities, start, end, offline=False)`` returns a tidy DataFrame
(``offline=True`` builds it from the on-disk cache only); the CLI
writes it to CSV.  Everything else (HTTP retries, polite pacing, the on-disk
HTML cache that makes reruns offline and resumable, table parsing, merging
the two rankings) is hidden behind it.

Data character -- these are third-party listing/market estimates, not
transactions, and each page lists only the top 10 districts by that ranking,
so a district can appear in some months and not others.  Rows keep
``source_type = third_party_report`` and are never mixed into the official
panel.
"""

from __future__ import annotations

import argparse
import html as html_lib
import re
import time
import urllib.request
from datetime import date
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional

import pandas as pd

CITY_CODES: Dict[str, str] = {
    "北京": "bj", "上海": "sh", "广州": "gz", "深圳": "sz", "重庆": "cq", "杭州": "hz", "成都": "cd",
    "武汉": "wh", "西安": "xa", "天津": "tj", "苏州": "su", "青岛": "qd", "长沙": "cs", "郑州": "zz",
    "合肥": "hf", "福州": "fz", "厦门": "xm", "济南": "jn", "大连": "dl", "昆明": "km", "南宁": "nn",
    "长春": "cc", "贵阳": "gy",
}
# First-pass coverage: the largest cities.  `collect` accepts any name in CITY_CODES; the site
# build reads whatever is cached (offline), so widening this list only costs collection time.
DEFAULT_CITIES = ["北京", "上海", "广州", "深圳", "杭州", "成都", "武汉", "西安", "重庆", "天津", "苏州", "长沙"]
BASE = "https://www.creprice.cn/report/{code}/{month}.html"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36",
    "Accept-Language": "zh-CN,zh;q=0.9",
}
_WAN = re.compile(r"^([0-9]+(?:\.[0-9]+)?)万$")
_PCT = re.compile(r"([+\-])?([0-9]+(?:\.[0-9]+)?)%")


def month_range(start: str, end: str) -> List[str]:
    """Inclusive YYYY-MM range."""
    y, m = map(int, start.split("-"))
    ey, em = map(int, end.split("-"))
    out, cur = [], date(y, m, 1)
    while cur <= date(ey, em, 1):
        out.append(cur.strftime("%Y-%m"))
        cur = date(cur.year + (cur.month == 12), cur.month % 12 + 1, 1)
    return out


def _number(text: str) -> Optional[float]:
    wan = _WAN.match(text)
    if wan:
        return round(float(wan.group(1)) * 10_000, 2)
    try:
        return float(text)
    except ValueError:
        return None


def parse_report(page: str) -> Dict[str, List[dict]]:
    """Return {'price': [...], 'rent': [...]} district rows from one report page.

    HTML comments are stripped first: the page hides the 售租比 cell inside
    ``<!-- -->`` and a naive tag-stripper would otherwise leak the comment
    markers into the cell text.
    """
    page = re.sub(r"<!--.*?-->", "", page, flags=re.S)
    out: Dict[str, List[dict]] = {"price": [], "rent": []}
    for table in re.findall(r"<table.*?</table>", page, re.S):
        head = re.sub(r"\s+", "", re.sub(r"<[^>]+>", " ", table))
        if "平均单价" not in head:
            continue
        kind = "rent" if "元/月/㎡" in head else "price"
        for row in re.findall(r"<tr.*?</tr>", table, re.S):
            cells = [re.sub(r"\s+", "", html_lib.unescape(re.sub(r"<[^>]+>", "", c)))
                     for c in re.findall(r"<t[dh].*?</t[dh]>", row, re.S)]
            if len(cells) < 4 or not cells[0].isdigit():
                continue
            value = _number(cells[-2])
            if value is None:
                continue
            mom = _PCT.search(cells[-1])
            out[kind].append({
                "rank": int(cells[0]),
                "district": re.sub(r"区$", "", cells[1]),
                "value": value,
                "mom_pct": None if not mom else round((-1.0 if mom.group(1) == "-" else 1.0) * float(mom.group(2)), 2),
            })
    return out


def merge_rankings(city: str, month: str, parsed: Dict[str, List[dict]], url: str) -> List[dict]:
    """One row per district appearing in either ranking, with derived yield."""
    price = {r["district"]: r for r in parsed["price"]}
    rent = {r["district"]: r for r in parsed["rent"]}
    rows = []
    for district in sorted(set(price) | set(rent)):
        p, r = price.get(district), rent.get(district)
        rows.append({
            "city": city, "district": district, "month": month,
            "price_yuan_m2": p["value"] if p else None, "price_mom_pct": p["mom_pct"] if p else None,
            "price_rank": p["rank"] if p else None,
            "rent_yuan_m2_month": r["value"] if r else None, "rent_mom_pct": r["mom_pct"] if r else None,
            "rent_rank": r["rank"] if r else None,
            "gross_yield_pct": round(r["value"] * 12 / p["value"] * 100, 2) if p and r and p["value"] else None,
            "source_url": url, "source_type": "third_party_report",
        })
    return rows


def _http_get(url: str) -> str:
    request = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read()
    for encoding in ("utf-8", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def fetch_page(url: str, cache_file: Path, get: Callable[[str], str] = _http_get,
               delay: float = 2.0, retries: int = 4, sleep: Callable[[float], None] = time.sleep,
               offline: bool = False) -> Optional[str]:
    """Cached fetch.  Connection resets (rate limiting) back off 5/15/45 s; a month
    that still fails is returned as None so a long run keeps going and a rerun
    retries only the gaps."""
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    if offline:
        return None
    wait = 5.0
    for attempt in range(retries):
        try:
            sleep(delay)
            page = get(url)
            if "平均单价" in page:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                cache_file.write_text(page, encoding="utf-8")
                return page
            return None  # page exists but has no report (not published yet)
        except Exception:
            if attempt + 1 < retries:
                sleep(wait)
                wait *= 3
    return None


def collect(cities: Iterable[str], start: str, end: str, cache_dir: str = "data/raw/creprice",
            delay: float = 2.0, get: Callable[[str], str] = _http_get,
            sleep: Callable[[float], None] = time.sleep, progress: Callable[[str], None] = lambda s: None,
            offline: bool = False) -> pd.DataFrame:
    rows: List[dict] = []
    for city in cities:
        code = CITY_CODES[city]
        missing = 0
        for month in month_range(start, end):
            url = BASE.format(code=code, month=month)
            page = fetch_page(url, Path(cache_dir) / code / f"{month}.html", get, delay, sleep=sleep, offline=offline)
            if page is None:
                missing += 1
                continue
            rows.extend(merge_rankings(city, month, parse_report(page), url))
        progress(f"{city}: {len(rows)} rows so far, {missing} months unavailable")
    return pd.DataFrame(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--cities", nargs="*", default=DEFAULT_CITIES)
    parser.add_argument("--start", default="2022-01")
    parser.add_argument("--end", default=date.today().strftime("%Y-%m"))
    parser.add_argument("--output", default="data/processed/creprice_district_panel.csv")
    parser.add_argument("--cache", default="data/raw/creprice")
    parser.add_argument("--delay", type=float, default=2.0, help="seconds between network requests")
    args = parser.parse_args()
    frame = collect(args.cities, args.start, args.end, args.cache, args.delay, progress=lambda s: print(s, flush=True))
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.output, index=False, encoding="utf-8-sig")
    print(f"wrote {len(frame)} rows, {frame['month'].nunique() if len(frame) else 0} months, "
          f"{frame['city'].nunique() if len(frame) else 0} cities -> {args.output}")


if __name__ == "__main__":
    main()
