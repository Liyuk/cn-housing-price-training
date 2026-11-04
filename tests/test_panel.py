import unittest

import numpy as np
import pandas as pd

from src.panel import CONSISTENT_FROM, REGIME_BREAK, Panel, identity_gaps, quality_of

CITIES = [f"城{chr(0x4e00 + i)}" for i in range(70)]       # 70 distinct, purely alphabetic names


def synthetic(start="2012-01", months=30, seed=0, market_gap=None) -> pd.DataFrame:
    """Both markets, 70 cities, MoM random around 100, YoY = chained 12 MoM (so the identity holds)."""
    rng = np.random.default_rng(seed)
    idx = pd.period_range(start, periods=months, freq="M").strftime("%Y-%m")
    rows = []
    for market in ("new", "secondhand"):
        mom = np.round(100 + rng.normal(0, 0.4, (months, 70)), 1)
        chain = pd.DataFrame(mom / 100).rolling(12).apply(np.prod, raw=True).to_numpy() * 100
        for t, month in enumerate(idx):
            if market == "secondhand" and market_gap == month:
                continue
            for c, city in enumerate(CITIES):
                y = round(float(chain[t, c]), 1) if t >= 11 else 100.0
                rows.append({"month": month, "city": city, "market": market, "month_on_month": float(mom[t, c]), "yoy": y,
                             "methodology": "current", "source_url": "https://example.test"})
    return pd.DataFrame(rows)


class ValidatorTests(unittest.TestCase):
    def test_a_consistent_panel_passes(self):
        rep = Panel(synthetic()).validate()
        self.assertTrue(rep.ok, rep.errors)
        self.assertLess(rep.stats["identity"]["secondhand"]["median_gap_since_valid"], 0.3)

    def test_swapped_city_pair_is_caught_by_the_yoy_chain_identity(self):
        """The real-world failure: two cities' rows swapped from some month on."""
        df = synthetic()
        late = df["month"] >= "2013-06"
        a, b = CITIES[3], CITIES[4]
        for col in ("month_on_month", "yoy"):
            ia = df.index[late & (df["city"] == a) & (df["market"] == "secondhand")]
            ib = df.index[late & (df["city"] == b) & (df["market"] == "secondhand")]
            va, vb = df.loc[ia, col].to_numpy().copy(), df.loc[ib, col].to_numpy().copy()
            df.loc[ia, col], df.loc[ib, col] = vb, va
        # swapping BOTH mom and yoy keeps each city internally consistent from the swap on, but breaks the
        # 12-month windows that straddle it: the guard must see those months
        gaps = identity_gaps(df[df["market"] == "secondhand"])
        self.assertGreater(float(gaps.loc["2013-06":"2014-04", [a, b]].max().max()), 2.0)

    def test_duplicates_gaps_and_unknown_tags_are_errors(self):
        df = synthetic()
        dup = pd.concat([df, df.iloc[:1]])
        self.assertTrue(any("duplicate" in e for e in Panel(dup).validate().errors))
        gap = synthetic(market_gap="2013-03")
        self.assertTrue(any("gaps" in e for e in Panel(gap).validate().errors))
        bad = df.copy()
        bad.loc[bad.index[0], "methodology"] = "mystery"
        self.assertTrue(any("methodology" in e for e in Panel(bad).validate().errors))

    def test_city_names_with_stray_characters_are_rejected(self):
        df = synthetic()
        df.loc[df["city"] == CITIES[0], "city"] = CITIES[0] + "*"
        self.assertTrue(any("stray" in e for e in Panel(df).validate().errors))

    def test_legacy_rows_after_the_regime_break_are_an_error(self):
        df = synthetic(start="2011-06", months=24)
        df.loc[df.index[:5], "methodology"] = "legacy_mirror"
        self.assertTrue(any("regime break" in e for e in Panel(df).validate().errors))

    def test_provenance_is_required(self):
        df = synthetic()
        df.loc[df.index[0], "source_url"] = ""
        self.assertTrue(any("provenance" in e for e in Panel(df).validate().errors))

    def test_extreme_but_plausible_values_are_warned_not_rejected(self):
        df = synthetic()
        df.loc[df.index[5], "month_on_month"] = 120.0
        rep = Panel(df).validate()
        self.assertFalse(any("month_on_month" in e for e in rep.errors))
        self.assertTrue(any("extreme" in w for w in rep.warnings))


class QualityTests(unittest.TestCase):
    def test_quality_tiers_follow_the_era_constants(self):
        self.assertEqual(quality_of("2007-12"), "low_consistency")
        self.assertEqual(quality_of(CONSISTENT_FROM), "legacy")
        self.assertEqual(quality_of("2011-01"), "legacy")
        self.assertEqual(quality_of(REGIME_BREAK), "current")

    def test_the_real_panel_passes_validation(self):
        from src.panel import PANEL_PATH, load_panel
        from pathlib import Path
        if not Path(PANEL_PATH).exists():
            self.skipTest("processed panel not present (git-ignored)")
        rep = load_panel().validate()
        self.assertTrue(rep.ok, rep.errors)


if __name__ == "__main__":
    unittest.main()
