import unittest
import csv
import os
import tempfile

from src.collector import normalize_city, parse_index_tables
from src.cirea_sources import parse_cirea_tables, parse_cirea_text
from src.clean import clean_price_data
from src.beijing_sources import parse_beijing_stats
from src.local_report import build_district_relationship_report
from src.evaluate import split_time_holdout
from src.macro_sources import parse_lpr, parse_real_estate_metrics
from src.train import add_temporal_features, load_features
from src.train import feature_columns
from src.audit import audit_price_panel
from src.sample import sample_panel
from src.explain import permutation_importance_report
from src.source_labels import classify_source, label_rows


class PipelineTests(unittest.TestCase):
    def test_normalize_city_removes_full_width_spacing(self):
        self.assertEqual(normalize_city("北　　京"), "北京")
        self.assertEqual(normalize_city("秦 皇 岛"), "秦皇岛")

    def test_parse_index_tables_reads_both_markets(self):
        html = """
        <table><tr><th>城市</th><th>环比</th><th>同比</th><th>平均</th>
        <th>城市</th><th>环比</th><th>同比</th><th>平均</th></tr>
        <tr><td>上月=100</td><td>上年同月=100</td><td>上年同期=100</td><td>平均</td>
        <td>上月=100</td><td>上年同月=100</td><td>上年同期=100</td><td>平均</td></tr>
        <tr><td>北　　京</td><td>99.8</td><td>98.0</td><td>98.5</td>
        <td>上　　海</td><td>100.1</td><td>101.0</td><td>100.5</td></tr></table>
        <table><tr><th>城市</th><th>环比</th><th>同比</th><th>平均</th>
        <th>城市</th><th>环比</th><th>同比</th><th>平均</th></tr>
        <tr><td>上月=100</td><td>上年同月=100</td><td>上年同期=100</td><td>平均</td>
        <td>上月=100</td><td>上年同月=100</td><td>上年同期=100</td><td>平均</td></tr>
        <tr><td>北　　京</td><td>99.0</td><td>95.0</td><td>96.0</td>
        <td>上　　海</td><td>99.5</td><td>97.0</td><td>98.0</td></tr></table>
        """
        rows = parse_index_tables(html, "2025-01", "https://example.test")
        self.assertEqual(len(rows), 4)
        self.assertEqual(rows[0]["city"], "北京")
        self.assertEqual(rows[0]["market"], "new")
        self.assertEqual(rows[2]["market"], "secondhand")
        self.assertEqual(rows[2]["yoy"], 95.0)

    def test_parse_lpr_extracts_one_and_five_year_rates(self):
        text = "2024年4月22日，1年期LPR为3.45%，5年期以上LPR为3.95%。"
        result = parse_lpr(text, "2024-04", "https://example.test")
        self.assertEqual(result["lpr_1y"], 3.45)
        self.assertEqual(result["lpr_5y"], 3.95)

    def test_parse_real_estate_metrics_extracts_national_values(self):
        text = "房地产开发投资完成额 10000 亿元，其中：住宅投资 8000 亿元；房屋施工面积 50000 万平方米；房屋新开工面积 20000 万平方米；房屋竣工面积 15000 万平方米；新建商品房销售面积 20000 万平方米，下降5.0%；新建商品房销售额 18000 亿元，下降8.0%；商品房待售面积 30000 万平方米；房地产开发企业到位资金 12000 亿元。"
        result = parse_real_estate_metrics(text, "2024-01", "https://example.test")
        self.assertEqual(result["development_investment_value"], 10000.0)
        self.assertEqual(result["housing_investment_value"], 8000.0)
        self.assertEqual(result["inventory_area"], 30000.0)
        self.assertEqual(result["new_home_sales_area"], 20000.0)
        self.assertEqual(result["new_home_sales_value"], 18000.0)

    def test_load_features_can_join_monthly_macro_features(self):
        with tempfile.TemporaryDirectory() as directory:
            price_path = os.path.join(directory, "price.csv")
            macro_path = os.path.join(directory, "macro.csv")
            fields = ["month", "city", "market", "month_on_month", "yoy", "year_avg"]
            with open(price_path, "w", newline="", encoding="utf8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                for market in ("new", "secondhand"):
                    writer.writerow({"month": "2024-01", "city": "北京", "market": market, "month_on_month": 100, "yoy": 100, "year_avg": 100})
            with open(macro_path, "w", newline="", encoding="utf8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["month", "lpr_5y"])
                writer.writeheader()
                writer.writerow({"month": "2024-01", "lpr_5y": 4.2})
            features = load_features(price_path, macro_path)
            self.assertEqual(float(features.iloc[0]["lpr_5y"]), 4.2)

    def test_temporal_features_use_only_prior_city_observations(self):
        import pandas as pd

        frame = pd.DataFrame({
            "month": ["2024-01", "2024-02", "2024-03", "2024-01"],
            "city": ["北京", "北京", "北京", "上海"],
            "yoy_new": [100.0, 101.0, 103.0, 98.0],
            "month_on_month_new": [99.0, 100.0, 101.0, 100.0],
            "yoy_secondhand": [95.0, 96.0, 99.0, 97.0],
            "month_on_month_secondhand": [98.0, 99.0, 100.0, 99.0],
        })
        result = add_temporal_features(frame)
        march = result[(result["city"] == "北京") & (result["month"] == "2024-03")].iloc[0]
        self.assertEqual(march["yoy_new_lag1"], 101.0)
        self.assertEqual(march["yoy_new_delta1"], 2.0)
        self.assertAlmostEqual(march["yoy_new_roll3"], 101.3333, places=3)
        self.assertEqual(march["yoy_secondhand_lag1"], 96.0)
        self.assertTrue(pd.isna(result[(result["city"] == "北京") & (result["month"] == "2024-01")].iloc[0]["yoy_new_lag1"]))

    def test_forecast_features_exclude_current_secondhand_target_fields(self):
        import pandas as pd

        frame = pd.DataFrame({
            "month_on_month_new": [100.0], "yoy_new": [100.0], "year_avg_new": [100.0],
            "month_on_month_secondhand": [99.0], "yoy_secondhand": [98.0], "year_avg_secondhand": [99.0],
            "month_num": [1], "month_sin": [0.5], "month_cos": [0.8], "city_tier": [1],
            "yoy_new_lag1": [100.0], "month_on_month_new_lag1": [100.0],
            "yoy_secondhand_lag1": [99.0], "month_on_month_secondhand_lag1": [100.0],
        })
        numeric, _ = feature_columns(frame)
        self.assertNotIn("yoy_secondhand", numeric)
        self.assertNotIn("month_on_month_secondhand", numeric)
        self.assertIn("yoy_secondhand_lag1", numeric)

    def test_audit_price_panel_reports_missing_months(self):
        import pandas as pd

        frame = pd.DataFrame([
            {"month": "2024-01", "city": "北京", "market": "secondhand", "yoy": 99},
            {"month": "2024-02", "city": "北京", "market": "secondhand", "yoy": 98},
        ])
        result = audit_price_panel(frame, start_month="2024-01", end_month="2024-03", expected_cities=1)
        self.assertEqual(result["rows"], 2)
        self.assertEqual(result["missing_months"], ["2024-03"])

    def test_sample_panel_is_reproducible_and_keeps_selected_cities(self):
        import pandas as pd

        frame = pd.DataFrame([
            {"month": "2024-01", "city": city, "market": market, "yoy": 100}
            for city in ("北京", "上海", "重庆")
            for market in ("new", "secondhand")
        ])
        result = sample_panel(frame, cities=["北京", "重庆"], markets=["secondhand"])
        self.assertEqual(set(result["city"]), {"北京", "重庆"})
        self.assertEqual(set(result["market"]), {"secondhand"})
        self.assertEqual(list(result["city"]), ["北京", "重庆"])

    def test_permutation_importance_returns_sorted_feature_scores(self):
        import pandas as pd

        frame = pd.DataFrame({
            "month": ["2024-01", "2024-02", "2024-03", "2024-04"],
            "month_num": [1, 2, 3, 4], "month_sin": [0, 1, 0, -1], "month_cos": [1, 0, -1, 0],
            "city_tier": [1, 1, 2, 2], "yoy_new_lag1": [99, 100, 101, 102],
            "month_on_month_new_lag1": [99, 100, 100, 101],
            "yoy_secondhand_lag1": [98, 99, 100, 101],
            "month_on_month_secondhand_lag1": [99, 99, 100, 100],
            "city": ["北京", "北京", "上海", "上海"], "yoy_secondhand": [99, 100, 101, 102],
        })
        result = permutation_importance_report(frame, test_months=1, n_repeats=2)
        self.assertTrue(result)
        self.assertGreaterEqual(result[0]["importance_mean"], result[-1]["importance_mean"])

    def test_parse_cirea_tables_reads_monthly_secondhand_series(self):
        table = [
            ["城市", "环比", "同比", "累计", "城市", "环比", "同比", "累计"],
            ["", "上月=100", "上年同月=100", "平均", "", "上月=100", "上年同月=100", "平均"],
            ["北　　京", "99.8", "101.0", "101.0", "上　　海", "100.1", "102.0", "102.0"],
        ]
        rows = parse_cirea_tables([table], 2023, "https://example.test/file.docx")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["month"], "2023-01")
        self.assertEqual(rows[0]["market"], "secondhand")
        self.assertEqual(rows[1]["city"], "上海")

    def test_parse_cirea_legacy_text_reads_two_column_monthly_tables(self):
        text = """2019年1月70个大中城市二手住宅销售价格指数\n城市\x07环比\x07同比\x07定基\x07城市\x07环比\x07同比\x07定基\x07北　　京\x0799.9\x0798.6\x07145.2\x07唐　　山\x07100.2\x07108.3\x07114.6\x07"""
        rows = parse_cirea_text(text, "https://example.test/file.doc")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["month"], "2019-01")
        self.assertEqual(rows[0]["city"], "北京")
        self.assertEqual(rows[1]["yoy"], 108.3)

    def test_clean_price_data_deduplicates_and_canonicalizes_city(self):
        with tempfile.TemporaryDirectory() as directory:
            input_path = os.path.join(directory, "input.csv")
            output_path = os.path.join(directory, "output.csv")
            fields = ["month", "city", "market", "month_on_month", "yoy", "year_avg", "methodology", "source_url"]
            rows = [
                {"month": "2023-01", "city": "襄樊", "market": "secondhand", "month_on_month": "99.0", "yoy": "98.0", "year_avg": "98.0", "methodology": "legacy", "source_url": "old"},
                {"month": "2023-01", "city": "襄阳", "market": "secondhand", "month_on_month": "99.1", "yoy": "98.1", "year_avg": "98.1", "methodology": "current", "source_url": "new"},
                {"month": "2023-01", "city": "北京", "market": "secondhand", "month_on_month": "999", "yoy": "98.0", "year_avg": "98.0", "methodology": "current", "source_url": "bad"},
            ]
            with open(input_path, "w", newline="", encoding="utf8") as handle:
                writer = csv.DictWriter(handle, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)
            result = clean_price_data(input_path, output_path)
            self.assertEqual(len(result), 1)
            self.assertEqual(result.iloc[0]["city"], "襄阳")
            self.assertEqual(result.iloc[0]["source_url"], "new")

    def test_split_time_holdout_uses_latest_month_as_test(self):
        import pandas as pd

        frame = pd.DataFrame({"month": ["2023-01", "2023-02", "2023-02"], "value": [1, 2, 3]})
        train, test = split_time_holdout(frame, test_months=1)
        self.assertEqual(set(train["month"]), {"2023-01"})
        self.assertEqual(set(test["month"]), {"2023-02"})

    def test_parse_beijing_district_transactions(self):
        html = """
        <p>2025年10月存量房网上签约</p>
        <table>
          <tr><td>所在区</td><td>全市</td><td>朝阳</td><td>海淀</td></tr>
          <tr><td>套数</td><td>100</td><td>20</td><td>30</td></tr>
          <tr><td>成交面积(m2)</td><td>10000</td><td>2000</td><td>3000</td></tr>
        </table>
        """
        rows = parse_beijing_stats(html, "https://example.test")
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["district"], "朝阳")
        self.assertEqual(rows[0]["online_signing_count"], 20.0)

    def test_district_relationship_report_explains_missing_price(self):
        import pandas as pd

        frame = pd.DataFrame([
            {"month": "2025-10", "city": "北京", "district": "朝阳", "market": "secondhand", "online_signing_count": 20, "online_signing_area_m2": 2000},
            {"month": "2025-10", "city": "北京", "district": "海淀", "market": "secondhand", "online_signing_count": 30, "online_signing_area_m2": 3000},
            {"month": "2025-10", "city": "北京", "district": "丰台", "market": "secondhand", "online_signing_count": 10, "online_signing_area_m2": 800},
        ])
        report = build_district_relationship_report(frame)
        self.assertIn("没有区级成交单价", report)
        self.assertIn("成交套数与成交面积相关系数", report)

    def test_source_labels_distinguish_official_transaction_and_listing_data(self):
        official = classify_source({
            "source_url": "https://zjw.beijing.gov.cn/bjjs/fdcjy/wqht/fcsjtj/index.shtml",
            "source_type": "official",
            "methodology": "monthly_online_signing",
        })
        listing = classify_source({
            "source_url": "https://www.creprice.cn/report/bj/2026-05.html",
            "source_type": "third_party_report",
            "methodology": "reported_avg_listing_price_top10",
        })
        self.assertEqual(official["source_tier"], "A_official")
        self.assertEqual(official["price_basis"], "transaction_volume_area")
        self.assertEqual(listing["source_tier"], "C_public_third_party")
        self.assertEqual(listing["price_basis"], "listing_price")
        self.assertFalse(listing["is_transaction_price"])

    def test_label_rows_preserves_original_fields_and_adds_provenance(self):
        rows = [{"city": "北京", "source_url": "https://www.stats.gov.cn/", "methodology": "official"}]
        result = label_rows(rows)
        self.assertEqual(result[0]["city"], "北京")
        self.assertEqual(result[0]["source_tier"], "A_official")
        self.assertIn("training_role", result[0])

    def test_source_labels_find_official_urls_in_macro_source_columns(self):
        result = classify_source({
            "source_url_real_estate": "https://www.stats.gov.cn/sj/zxfb/202606/example.html",
            "methodology": "cumulative_ytd_official",
        })
        self.assertEqual(result["source_tier"], "A_official")


if __name__ == "__main__":
    unittest.main()
