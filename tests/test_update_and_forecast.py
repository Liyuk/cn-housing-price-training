"""Tests for the update pipeline, probabilistic forecast helpers and the ledger.

All offline: HTML is built inline and the forecast helpers run on synthetic
series, so the suite stays fast (no GBM training, no network).
"""

import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from src.collector import normalize_city, parse_index_tables
from src.forecast_ledger import freeze, score_ledger
from src.probabilistic_forecast import (
    MODELS,
    band_scale,
    weighted_quantile,
    _local_forecast,
    city_tier,
    ensemble_path,
    learn_at,
    monthly_returns,
    national_path,
)
from src.update_data import merge_panel


def _table(title: str, rows: list[tuple], fixed_base: bool = False) -> str:
    """One NBS-style 70-city table with two city blocks per row."""
    head = "<tr><th>城市</th><th>环比</th><th>同比</th><th>定基</th><th>城市</th><th>环比</th><th>同比</th><th>定基</th></tr>"
    unit = "<tr><td>上月=100</td><td>上年同月=100</td><td>2010年=100</td><td>上月=100</td><td>上年同月=100</td><td>2010年=100</td></tr>"
    body = "".join(
        "<tr>" + "".join(f"<td>{c}</td>" for c in row) + "</tr>" for row in rows
    )
    return f"<table><tr><td>{title}</td></tr>{head}{unit}{body}</table>"


def _city_rows(prefix: str, mom: float, yoy: float) -> list[tuple]:
    names = [f"{prefix}{i:02d}" for i in range(70)]
    rows = []
    for a, b in zip(names[::2], names[1::2]):
        rows.append((a, mom, yoy, 120.0, b, mom, yoy, 121.0))
    return rows


class ParserEraTests(unittest.TestCase):
    def test_normalize_city_strips_footnote_asterisks(self):
        self.assertEqual(normalize_city("北　京*"), "北京")
        self.assertEqual(normalize_city("北京＊"), "北京")

    def test_old_pages_pick_tables_by_header_not_position(self):
        """2014-style page: 新建住宅 (incl. affordable) first, then 新建商品住宅, 二手住宅."""
        html = (
            _table("城市 新建住宅价格指数", _city_rows("甲", 111.0, 111.0))        # must be skipped
            + _table("城市 新建商品住宅价格指数", _city_rows("乙", 100.1, 105.0))
            + _table("城市 二手住宅价格指数", _city_rows("丙", 99.5, 98.0))
        )
        rows = parse_index_tables(html, "2014-06", "https://example.test")
        by_market = {m: [r for r in rows if r["market"] == m] for m in ("new", "secondhand")}
        self.assertEqual(len(by_market["new"]), 70)
        self.assertTrue(all(r["city"].startswith("乙") for r in by_market["new"]))
        self.assertTrue(all(r["city"].startswith("丙") for r in by_market["secondhand"]))
        self.assertEqual(by_market["secondhand"][0]["month_on_month"], 99.5)

    def test_fixed_base_column_is_not_read_as_year_average(self):
        html = _table("城市 新建商品住宅价格指数", _city_rows("乙", 100.1, 105.0)) \
            + _table("城市 二手住宅价格指数", _city_rows("丙", 99.5, 98.0))
        rows = parse_index_tables(html, "2014-06", "https://example.test")
        self.assertTrue(all(r["year_avg"] is None for r in rows))

    def test_fifteen_city_comparison_table_is_ignored(self):
        small = "<table><tr><td>表1: 15个一线和热点二线城市新建商品住宅价格变动对比表</td></tr><tr><td>城市</td><td>环比</td></tr><tr><td>北京</td><td>99.9</td></tr></table>"
        html = small + _table("表3：70个大中城市新建商品住宅价格指数", _city_rows("乙", 100.0, 100.0)) \
            + _table("表4：70个大中城市二手住宅价格指数", _city_rows("丙", 100.0, 100.0))
        rows = parse_index_tables(html, "2016-12", "https://example.test")
        self.assertEqual(len(rows), 140)


class MergePriorityTests(unittest.TestCase):
    def test_official_cells_replace_reposts_and_changes_are_reported(self):
        with tempfile.TemporaryDirectory() as tmp:
            panel = os.path.join(tmp, "panel.csv")
            fields = ["month", "city", "market", "month_on_month", "yoy", "year_avg", "methodology", "source_url"]
            old = pd.DataFrame([
                ["2021-01", "徐州", "secondhand", 100.5, 105.0, None, "current_cirea_legacy_doc", "cirea"],
                ["2021-01", "扬州", "secondhand", 101.0, 109.1, None, "current_cirea_legacy_doc", "cirea"],
                ["2021-02", "徐州", "secondhand", 100.2, 104.0, None, "current_cirea_legacy_doc", "cirea"],
            ], columns=fields)
            old.to_csv(panel, index=False)
            new = pd.DataFrame([
                ["2021-01", "徐州", "secondhand", 101.0, 109.1, None, "current", "nbs"],
                ["2021-01", "扬州", "secondhand", 100.5, 105.0, None, "current", "nbs"],
            ], columns=fields)
            merged, changed = merge_panel(panel, new, panel)
            self.assertEqual(len(merged), 3)
            xz = merged[(merged["city"] == "徐州") & (merged["month"] == "2021-01")].iloc[0]
            self.assertEqual((xz["methodology"], xz["month_on_month"]), ("current", 101.0))
            self.assertEqual(len(changed), 2)           # both swapped cells surfaced, not silently overwritten
            kept = merged[merged["month"] == "2021-02"].iloc[0]
            self.assertEqual(kept["methodology"], "current_cirea_legacy_doc")


class ForecastHelperTests(unittest.TestCase):
    def test_gap_months_are_bridged_from_the_yoy_identity(self):
        """Delete one month of MoM; it is recovered from YoY[t]/YoY[t-1] a year later."""
        months = pd.period_range("2020-01", "2021-12", freq="M").strftime("%Y-%m")
        rng = np.random.default_rng(0)
        mom = 100 + rng.normal(0, 0.3, len(months))
        price = np.cumprod(mom / 100.0)
        yoy = np.full(len(months), np.nan)
        yoy[12:] = price[12:] / price[:-12] * 100
        rows = [{"month": m, "city": "甲", "market": "secondhand", "month_on_month": mom[i], "yoy": yoy[i] if i >= 12 else 100.0}
                for i, m in enumerate(months)]
        frame = pd.DataFrame(rows)
        truth = frame.loc[frame["month"] == "2020-06", "month_on_month"].item()
        frame = frame[frame["month"] != "2020-06"]
        r, bridged = monthly_returns(frame)
        self.assertTrue(bridged.loc["2020-06", "甲"])
        self.assertAlmostEqual(100 * np.exp(r.loc["2020-06", "甲"]), truth, places=6)

    def test_local_models_return_requested_horizon(self):
        hist = np.log(np.linspace(99.5, 100.3, 60) / 100)
        for name in ("naive", "drift12", "ar1", "damped"):
            self.assertEqual(len(_local_forecast(name, hist, 24)), 24)

    def test_damped_forecast_decays_toward_zero(self):
        hist = np.full(36, np.log(99.6 / 100))
        path = _local_forecast("damped", hist, 36)
        self.assertLess(abs(path[-1]), abs(path[0]))

    def test_national_path_matches_mean_of_city_indices(self):
        city_cum = np.log(np.array([[1.01, 1.02], [0.99, 0.98]]))      # two cities, two months
        got = np.exp(national_path(city_cum))
        expect_m1 = (1.01 + 0.99) / 2
        expect_m2 = expect_m1 * ((1.02 / 1.01 + 0.98 / 0.99) / 2)
        np.testing.assert_allclose(got, [expect_m1, expect_m2], rtol=1e-9)

    def test_city_tier_buckets(self):
        self.assertEqual((city_tier("北京"), city_tier("成都"), city_tier("唐山")), (1, 2, 3))


def _records(origins, horizon, errors):
    """Synthetic backtest records: model k is off by errors[k] everywhere."""
    out = {}
    for o in origins:
        actual = np.zeros((6, horizon))
        out[o] = {"actual": actual, "scale": np.full((6, horizon), 0.004) * np.sqrt(np.arange(1, horizon + 1))[None, :],
                  "paths": {name: np.full((6, horizon), errors[i]) for i, name in enumerate(MODELS) if i < len(errors)}}
    return out


class LearnAtTests(unittest.TestCase):
    ORIGINS = [str(p) for p in pd.period_range("2016-01", "2023-01", freq="3M").strftime("%Y-%m")]

    def test_no_lookahead_only_origins_with_realised_horizon_count(self):
        """Changing a record whose h-month outcome is not yet known must not change anything."""
        horizon = 12
        recs = _records(self.ORIGINS, horizon, [0.02, 0.005, 0.01, 0.03, 0.02])
        now = "2019-06"
        base_w, base_q, *_ = learn_at(recs, self.ORIGINS, now, horizon)
        future = [o for o in self.ORIGINS if o > now][0]               # origin after `now`: invisible
        recs[future]["paths"]["naive"] = recs[future]["paths"]["naive"] + 5.0
        recs[future]["actual"] = recs[future]["actual"] - 5.0
        w2, q2, *_ = learn_at(recs, self.ORIGINS, now, horizon)
        np.testing.assert_allclose(base_w, w2)
        np.testing.assert_allclose(base_q, q2)

    def test_better_model_gets_more_weight(self):
        horizon = 12
        recs = _records(self.ORIGINS, horizon, [0.05, 0.001, 0.05, 0.05, 0.05])
        w, *_ = learn_at(recs, self.ORIGINS, "2023-01", horizon, top_k=None)
        self.assertEqual(int(np.argmax(w[:, 5])), MODELS.index("drift12"))
        np.testing.assert_allclose(w.sum(axis=0), 1.0, atol=1e-9)

    def test_top_k_averages_only_the_best_k_models_by_past_error(self):
        horizon = 12
        recs = _records(self.ORIGINS, horizon, [0.05, 0.001, 0.002, 0.05, 0.05])    # drift12 and ar1 are best
        w, *_ = learn_at(recs, self.ORIGINS, "2023-01", horizon, top_k=2)
        best = {MODELS.index("drift12"), MODELS.index("ar1")}
        self.assertEqual({k for k in range(len(MODELS)) if w[k, 5] > 0}, best)
        self.assertAlmostEqual(float(w[MODELS.index("drift12"), 5]), 0.5)

    def test_long_horizons_use_the_fixed_damped_rule(self):
        horizon = 24
        recs = _records(self.ORIGINS, horizon, [0.01, 0.005, 0.02, 0.03, 0.02])
        w, *_ = learn_at(recs, self.ORIGINS, "2023-01", horizon)
        self.assertEqual(w[MODELS.index("damped"), 20], 1.0)

    def test_quantile_bands_never_narrow_with_horizon(self):
        horizon = 12
        recs = _records(self.ORIGINS, horizon, [0.01, 0.01, 0.01, 0.01, 0.01])
        rng = np.random.default_rng(1)
        for rec in recs.values():
            rec["actual"] = rng.normal(0, 0.01, rec["actual"].shape)
        _, q_city, *_ = learn_at(recs, self.ORIGINS, "2023-01", horizon)
        self.assertTrue(np.all(np.diff(q_city[4]) >= -1e-12))          # upper tail non-decreasing
        self.assertTrue(np.all(np.diff(q_city[0]) <= 1e-12))           # lower tail non-increasing

    def test_ensemble_path_is_a_weighted_average(self):
        paths = {"naive": np.ones((2, 3)), "damped": np.zeros((2, 3))}
        w = np.zeros((len(MODELS), 3)); w[MODELS.index("naive")] = 0.25; w[MODELS.index("damped")] = 0.75
        np.testing.assert_allclose(ensemble_path(paths, w), 0.25)


class BandScaleTests(unittest.TestCase):
    def _returns(self, drift_wobble: float):
        rng = np.random.default_rng(0)
        months = pd.period_range("2015-01", "2022-12", freq="M").strftime("%Y-%m")
        wob = np.cumsum(rng.normal(0, drift_wobble, len(months)))
        return pd.DataFrame({"甲": rng.normal(0, 0.002, len(months)) + wob * 0.01}, index=months)

    def test_scale_grows_with_horizon_and_with_trend_instability(self):
        calm, wobbly = self._returns(0.0001), self._returns(0.01)
        sc_calm, sc_wob = band_scale(calm, "2022-12", 36), band_scale(wobbly, "2022-12", 36)
        self.assertTrue(np.all(np.diff(sc_calm[0]) > 0))
        self.assertGreater(sc_wob[0, -1], sc_calm[0, -1])        # unstable drift widens the long-horizon band
        self.assertEqual(sc_calm.shape, (1, 36))

    def test_drift_term_dominates_long_horizons(self):
        sc = band_scale(self._returns(0.01), "2022-12", 36)[0]
        self.assertGreater(sc[35] / sc[0], np.sqrt(36))           # faster than a pure random walk (sqrt h)


class WeightedQuantileTests(unittest.TestCase):
    def test_equal_weights_match_the_plain_quantile(self):
        x = np.arange(1.0, 101.0)
        np.testing.assert_allclose(weighted_quantile(x, np.ones(100), [0.5]), [50.5], atol=0.6)

    def test_recent_observations_pull_the_quantile(self):
        x = np.concatenate([np.full(50, -1.0), np.full(50, 1.0)])     # old = -1, recent = +1
        w = np.concatenate([np.full(50, 0.01), np.full(50, 1.0)])
        self.assertGreater(float(weighted_quantile(x, w, [0.5])[0]), 0.9)


class LedgerTests(unittest.TestCase):
    def _forecast(self):
        rows = []
        for region in ("全国", "甲", "乙"):
            for h in (1, 2):
                rows.append({"region": region, "month": f"2026-1{h}", "h": h, "q025": 98.0, "q100": 99.0 - h * 0.1,
                             "q500": 99.8, "q900": 100.5, "q975": 101.0, "mom_point": 99.8})
        return pd.DataFrame(rows)

    def test_freeze_never_overwrites(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp)
            _, fresh = freeze(self._forecast(), "2026-09", d)
            self.assertTrue(fresh)
            changed = self._forecast().assign(q500=50.0)
            _, fresh2 = freeze(changed, "2026-09", d)
            self.assertFalse(fresh2)
            self.assertEqual(pd.read_csv(d / "2026-09.csv")["q500"].iloc[0], 99.8)

    def test_score_waits_for_data_then_scores_inside_band(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "ledger"
            freeze(self._forecast(), "2026-09", d)
            panel = Path(tmp) / "panel.csv"
            base = [{"month": "2026-09", "city": c, "market": "secondhand", "month_on_month": 100.0, "yoy": 100.0} for c in ("甲", "乙")]
            pd.DataFrame(base).to_csv(panel, index=False)
            waiting = score_ledger(str(panel), d)[0]
            self.assertEqual(waiting["months_scored"], 0)
            nxt = base + [{"month": "2026-10", "city": c, "market": "secondhand", "month_on_month": 99.8, "yoy": 99.0} for c in ("甲", "乙")]
            pd.DataFrame(nxt).to_csv(panel, index=False)
            scored = score_ledger(str(panel), d)[0]
            self.assertEqual(scored["months_scored"], 1)
            first = scored["scored"][0]
            self.assertEqual(first["city_inside80"], 1.0)
            self.assertAlmostEqual(first["national"]["actual"], 99.8, places=2)


if __name__ == "__main__":
    unittest.main()
