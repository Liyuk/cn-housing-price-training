import tempfile
import unittest
from pathlib import Path

import pandas as pd

from src.creprice_panel import collect, fetch_page, merge_rankings, month_range, parse_report
from src.update_data import MIRROR_TRUSTED_THROUGH, legacy_mirror_rows, mirror_gap_rows

PAGE = """
<table><tr><th>排名</th><th>区市县</th><th>售租比</th><th>平均单价（元/㎡）</th><th>环比</th></tr>
<tr><td>1</td><td>西城区</td>
<!--  <td>--><!--</td>-->
<td class="green">11.2万</td><td>-5.16%</td></tr>
<tr><td>2</td><td>东城区</td><td class="green">96200</td><td>+0.4%</td></tr></table>
<table><tr><th>排名</th><th>区市县</th><th>售租比</th><th>平均单价（元/月/㎡）</th><th>环比</th></tr>
<tr><td>1</td><td>西城区</td><td>137.08</td><td>+1.96%</td></tr>
<tr><td>2</td><td>昌平区</td><td>79.77</td><td>-0.1%</td></tr></table>
"""


class CrepriceParseTests(unittest.TestCase):
    def test_commented_cell_does_not_shift_columns_and_wan_units_are_expanded(self):
        parsed = parse_report(PAGE)
        self.assertEqual([r["district"] for r in parsed["price"]], ["西城", "东城"])
        self.assertEqual(parsed["price"][0]["value"], 112000.0)
        self.assertEqual(parsed["price"][0]["mom_pct"], -5.16)
        self.assertEqual(parsed["rent"][0]["value"], 137.08)       # the rent table is told apart by 元/月/㎡

    def test_wan_conversion_has_no_float_noise(self):
        page = PAGE.replace("11.2万", "9.62万")
        self.assertEqual(parse_report(page)["price"][0]["value"], 96200.0)

    def test_yield_is_derived_only_where_both_rankings_list_the_district(self):
        rows = {r["district"]: r for r in merge_rankings("北京", "2026-04", parse_report(PAGE), "u")}
        self.assertAlmostEqual(rows["西城"]["gross_yield_pct"], 137.08 * 12 / 112000 * 100, places=2)
        self.assertIsNone(rows["东城"]["gross_yield_pct"])           # in the price ranking only
        self.assertIsNone(rows["昌平"]["price_yuan_m2"])             # in the rent ranking only: a gap, not a guess

    def test_month_range_is_inclusive_and_crosses_years(self):
        self.assertEqual(month_range("2025-11", "2026-02"), ["2025-11", "2025-12", "2026-01", "2026-02"])


class CrepriceFetchTests(unittest.TestCase):
    def test_cached_page_is_never_fetched_again(self):
        with tempfile.TemporaryDirectory() as tmp:
            calls = []
            get = lambda url: calls.append(url) or PAGE
            f = Path(tmp) / "bj" / "2026-04.html"
            fetch_page("u", f, get, sleep=lambda s: None)
            fetch_page("u", f, get, sleep=lambda s: None)
            self.assertEqual(len(calls), 1)

    def test_connection_resets_back_off_then_succeed(self):
        with tempfile.TemporaryDirectory() as tmp:
            attempts, sleeps = [], []

            def get(url):
                attempts.append(1)
                if len(attempts) < 3:
                    raise ConnectionResetError("reset")
                return PAGE

            page = fetch_page("u", Path(tmp) / "x.html", get, delay=2.0, sleep=sleeps.append)
            self.assertIsNotNone(page)
            self.assertEqual(len(attempts), 3)
            self.assertIn(5.0, sleeps)                                # backed off after the first reset

    def test_persistent_failure_returns_none_so_a_long_run_continues(self):
        with tempfile.TemporaryDirectory() as tmp:
            def get(url):
                raise ConnectionResetError("reset")
            self.assertIsNone(fetch_page("u", Path(tmp) / "x.html", get, sleep=lambda s: None, retries=2))

    def test_offline_collect_reads_cache_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = Path(tmp) / "bj"
            cache.mkdir()
            (cache / "2026-04.html").write_text(PAGE, encoding="utf-8")
            def boom(url):
                raise AssertionError("network must not be touched offline")
            frame = collect(["北京"], "2026-03", "2026-04", cache_dir=tmp, get=boom, offline=True)
            self.assertEqual(set(frame["month"]), {"2026-04"})


MIRROR = """"DATE","ADCODE","CITY","FixedBase","HouseIDX","ResidentIDX","CommodityHouseIDX","SecondHandIDX"
"2010-12-01","110000","北京","环比","","","100.4","100.2"
"2010-12-01","110000","北京","同比","","","103.0","101.0"
"2012-02-01","110000","北京","环比","","","100.1","100.3"
"2012-02-01","110000","北京","同比","","","102.0","101.5"
"2021-02-01","110000","北京","环比","","","100.0","100.0"
"2021-02-01","110000","北京","同比","","","101.0","101.0"
"""


class MirrorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / "m.csv")
        Path(self.path).write_text(MIRROR, encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_legacy_rows_cover_only_months_before_the_first_official_month(self):
        rows, _ = legacy_mirror_rows(self.path, before="2011-02")
        self.assertEqual(set(rows["month"]), {"2010-12"})
        self.assertEqual(set(rows["methodology"]), {"legacy_mirror"})
        self.assertEqual(set(rows["market"]), {"new", "secondhand"})

    def test_agreement_check_counts_identical_cells(self):
        official = pd.DataFrame([
            {"month": "2012-02", "city": "北京", "market": "secondhand", "month_on_month": 100.3, "yoy": 101.5},
            {"month": "2012-02", "city": "北京", "market": "new", "month_on_month": 100.0, "yoy": 102.0},   # differs
        ])
        _, check = legacy_mirror_rows(self.path, before="2011-02", official=official)
        self.assertEqual((check["compared_cells"], check["identical_cells"]), (2, 1))

    def test_gap_fill_uses_only_missing_months_within_the_trusted_range(self):
        panel = pd.DataFrame([{"month": "2012-02", "market": "secondhand"}])       # secondhand 2012-02 already present
        gaps = mirror_gap_rows(self.path, panel)
        keys = set(zip(gaps["market"], gaps["month"]))
        self.assertEqual(keys, {("new", "2012-02")})                               # only the market that is missing
        self.assertEqual(set(gaps["methodology"]), {"mirror_filled"})
        self.assertNotIn("2021-02", set(gaps["month"]))                            # after the mirror's 2021 swap: never used
        self.assertLessEqual(max(gaps["month"]), MIRROR_TRUSTED_THROUGH)


if __name__ == "__main__":
    unittest.main()
