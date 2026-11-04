"""Canonical 70-city price panel: one definition of what the data is and when it is valid.

Everything that reads the panel (forecast, site build, update, acceptance) goes
through this module for the path, the era constants, the log-return matrix and
the validation rules, so there is one place to change them.

Interface
---------
``PANEL_PATH``                    the canonical file
``load_panel(path) -> Panel``     tidy frame + helpers
``Panel.returns(market, start)``  month × city log(MoM/100) matrix, plus a mask of bridged cells
``Panel.validate() -> Report``    hard errors and warnings (see ``validate``)
``quality_of(month)``             'low_consistency' | 'legacy' | 'current'

The standing guard is the **YoY-chain identity**: the product of twelve
consecutive month-on-month indices must reproduce the reported year-on-year
index (up to rounding, median gap ≈ 0.1).  It is what proved that official pages
beat the third-party mirror for four cities from 2021, and what shows that the
2006–2007 monthly changes cannot be chained (median gap ≈ 4 points).
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

PANEL_PATH = "data/processed/housing_indices_clean_v4.csv"
REGIME_BREAK = "2011-02"       # first month with directly fetched official pages / current survey method
CONSISTENT_FROM = "2008-01"    # earlier months fail the YoY-chain identity: MoM cannot be chained
MIRROR_TRUSTED_THROUGH = "2020-12"
MARKETS = ("new", "secondhand")
METHODOLOGIES = {"current", "current_cirea", "current_cirea_legacy_doc", "legacy_mirror", "mirror_filled"}
EXPECTED_CITIES = 70
IDENTITY_TOL = 2.0             # index points between chained MoM and reported YoY
IDENTITY_MAX_SHARE = 0.05      # share of cities allowed to violate it in one month (from CONSISTENT_FROM + 11)


def quality_of(month: str) -> str:
    """Per-month data quality tier (used for downloads and charts)."""
    if month < CONSISTENT_FROM:
        return "low_consistency"
    return "legacy" if month < REGIME_BREAK else "current"


def monthly_returns(frame: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Wide month × city matrix of log(MoM/100) on a continuous monthly index.

    Months missing from the record are bridged with the YoY identity
    r[t-12] = r[t] − (L[t] − L[t-1]), L = log(YoY/100), exact up to the 0.1-point
    rounding of published indices.  Bridged cells are returned as a boolean mask
    so callers can label them as derived.  (With the mirror gap-fill the current
    panel has none; the bridge stays for panels with real gaps.)
    """
    mom = frame.pivot_table(index="month", columns="city", values="month_on_month", aggfunc="first")
    yoy = frame.pivot_table(index="month", columns="city", values="yoy", aggfunc="first")
    months = pd.period_range(mom.index.min(), mom.index.max(), freq="M").strftime("%Y-%m")
    mom, yoy = mom.reindex(months), yoy.reindex(months)
    r = np.log(mom / 100.0)
    lyoy = np.log(yoy / 100.0)
    bridged = pd.DataFrame(False, index=r.index, columns=r.columns)
    values, lv = r.to_numpy(), lyoy.to_numpy()
    for i in range(len(months) - 12):
        missing = np.isnan(values[i])
        if not missing.any():
            continue
        est = values[i + 12] - (lv[i + 12] - lv[i + 11])
        fill = missing & ~np.isnan(est)
        values[i, fill] = est[fill]
        bridged.iloc[i, np.where(fill)[0]] = True
    return pd.DataFrame(values, index=r.index, columns=r.columns), bridged


def identity_gaps(frame: pd.DataFrame) -> pd.DataFrame:
    """|chained 12-month MoM − reported YoY| per (month, city); NaN where the window has a gap."""
    mom = frame.pivot_table(index="month", columns="city", values="month_on_month", aggfunc="first")
    yoy = frame.pivot_table(index="month", columns="city", values="yoy", aggfunc="first")
    months = pd.period_range(mom.index.min(), mom.index.max(), freq="M").strftime("%Y-%m")
    mom, yoy = mom.reindex(months), yoy.reindex(months)
    chain = (mom / 100.0).rolling(12).apply(np.prod, raw=True) * 100.0
    return (chain - yoy).abs()


@dataclass
class Report:
    errors: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.errors

    def as_dict(self) -> dict:
        return {"ok": self.ok, "errors": self.errors, "warnings": self.warnings, "stats": self.stats}


@dataclass
class Panel:
    frame: pd.DataFrame

    def market(self, market: str, start: str | None = None) -> pd.DataFrame:
        sub = self.frame[self.frame["market"].eq(market)]
        return sub[sub["month"] >= start] if start else sub

    def returns(self, market: str = "secondhand", start: str | None = None):
        return monthly_returns(self.market(market, start))

    @property
    def last_month(self) -> str:
        return self.frame["month"].max()

    def validate(self) -> Report:
        """Hard errors fail acceptance; warnings are listed with the data they concern."""
        f, rep = self.frame, Report()
        need = {"month", "city", "market", "month_on_month", "yoy", "methodology", "source_url"}
        if need - set(f.columns):
            rep.errors.append(f"missing columns: {sorted(need - set(f.columns))}")
            return rep
        if not f["month"].astype(str).str.fullmatch(r"\d{4}-\d{2}").all():
            rep.errors.append("month is not YYYY-MM everywhere")
        if set(f["market"]) - set(MARKETS):
            rep.errors.append(f"unknown markets: {sorted(set(f['market']) - set(MARKETS))}")
        bad = set(f["methodology"]) - METHODOLOGIES
        if bad:
            rep.errors.append(f"unknown methodology tags: {sorted(bad)}")
        dup = int(f.duplicated(["month", "city", "market"]).sum())
        if dup:
            rep.errors.append(f"{dup} duplicate (month, city, market) keys")
        for col, lo, hi in (("month_on_month", 70, 130), ("yoy", 50, 200)):   # the cleaner's hard limits
            out = f[~f[col].between(lo, hi)]
            if len(out):
                rep.errors.append(f"{len(out)} {col} values outside [{lo}, {hi}]")
        extreme = f[(~f["month_on_month"].between(85, 115)) | (~f["yoy"].between(60, 160))]
        if len(extreme):   # real events (Hainan 2010, Shenzhen 2016), listed rather than rejected
            ex = extreme.sort_values(["city", "month"]).drop_duplicates("city")[["city", "month"]]
            rep.warnings.append(f"{len(extreme)} extreme but plausible values in {extreme['city'].nunique()} cities (e.g. "
                                + ", ".join(f"{c} {m}" for c, m in ex.head(4).itertuples(index=False)) + ")")
        if f["source_url"].isna().any() or (f["source_url"].astype(str).str.len() == 0).any():
            rep.errors.append("rows without provenance (source_url)")
        starred = [c for c in set(f["city"]) if not str(c).isalpha()]
        if starred:
            rep.errors.append(f"city names with stray characters: {starred}")
        # coverage: 70 cities per (market, month); continuity of the second-hand series
        per = f.groupby(["market", "month"])["city"].nunique()
        short = per[per != EXPECTED_CITIES]
        if len(short):
            rep.errors.append(f"{len(short)} (market, month) with a city count != {EXPECTED_CITIES}: {short.head(3).to_dict()}")
        stats: dict = {"rows": int(len(f)), "cities": int(f["city"].nunique()), "last_month": self.last_month}
        for market in MARKETS:
            months = sorted(f.loc[f["market"].eq(market), "month"].unique())
            full = pd.period_range(months[0], months[-1], freq="M").strftime("%Y-%m")
            missing = sorted(set(full) - set(months))
            stats[market] = {"first": months[0], "last": months[-1], "months": len(months), "missing": missing}
            if market == "secondhand" and missing:
                rep.errors.append(f"second-hand series has gaps: {missing}")
            elif missing:
                rep.warnings.append(f"{market} gaps: {missing}")
        # era rules: where each methodology tag may appear
        era = f[(f["methodology"] == "legacy_mirror") & (f["month"] >= REGIME_BREAK)]
        if len(era):
            rep.errors.append(f"{len(era)} legacy_mirror rows at/after the regime break {REGIME_BREAK}")
        late = f[(f["methodology"] == "mirror_filled") & (f["month"] > MIRROR_TRUSTED_THROUGH)]
        if len(late):
            rep.errors.append(f"{len(late)} mirror_filled rows after {MIRROR_TRUSTED_THROUGH}, where the mirror swaps four cities")
        # the YoY-chain identity, era-aware
        id_stats = {}
        for market in MARKETS:
            gaps = identity_gaps(f[f["market"].eq(market)])
            valid_from = str(pd.Period(CONSISTENT_FROM, freq="M") + 11)
            ok_part = gaps.loc[gaps.index >= valid_from]
            share = (ok_part > IDENTITY_TOL).mean(axis=1)
            worst = share[share > IDENTITY_MAX_SHARE]
            if len(worst):
                rep.errors.append(f"{market}: YoY-chain identity violated for >{IDENTITY_MAX_SHARE:.0%} of cities in {len(worst)} months from {valid_from} (e.g. {worst.index[0]}: {worst.iloc[0]:.0%})")
            viol = ok_part.stack()
            viol = viol[viol > IDENTITY_TOL]
            if len(viol):
                cells = [f"{m} {c}" for (m, c) in viol.index[:12]]
                rep.warnings.append(f"{market}: {len(viol)} isolated identity violations from {valid_from} (e.g. {', '.join(cells[:4])})")
            early = gaps.loc[gaps.index < CONSISTENT_FROM].stack()
            id_stats[market] = {
                "median_gap_since_valid": round(float(np.nanmedian(ok_part.values)), 3),
                "max_share_since_valid": round(float(share.max()), 3) if len(share) else None,
                "violations_since_valid": int(len(viol)),
                "median_gap_before_consistent_from": round(float(early.median()), 2) if len(early) else None,
            }
        stats["identity"] = id_stats
        stats["quality_months"] = {q: int(sum(quality_of(m) == q for m in sorted(f["month"].unique()))) for q in ("low_consistency", "legacy", "current")}
        rep.stats = stats
        return rep


def load_panel(path: str = PANEL_PATH) -> Panel:
    return Panel(pd.read_csv(path))


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the canonical 70-city panel")
    parser.add_argument("--path", default=PANEL_PATH)
    parser.add_argument("--output", default="reports/data_validation.json")
    args = parser.parse_args()
    report = load_panel(args.path).validate()
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(json.dumps(report.as_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=1)[:3000])
    raise SystemExit(0 if report.ok else 1)


if __name__ == "__main__":
    main()
