#!/usr/bin/env python3
"""Acceptance gate (验收): data, model and site, with thresholds declared in one place.

    .venv/bin/python scripts/acceptance.py            # fast: reads saved results, runs the test suites
    .venv/bin/python scripts/acceptance.py --full     # also re-runs the forecast and checks it is reproducible

Writes ``reports/acceptance_<date>.md`` and exits 1 if any check FAILs.  WARN means a
documented limitation (shown on the site); MANUAL lists what a script cannot judge.

The model thresholds are *floors*, set a margin below what the walk-forward measured
when they were written -- they exist to catch regressions, not to certify the model as
good.  They were chosen after seeing results, which the report states.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from site_extras import next_release_estimate  # noqa: E402
from src.panel import CONSISTENT_FROM, IDENTITY_MAX_SHARE, load_panel  # noqa: E402

# ----------------------------------------------------------------- declared thresholds
SKILL_FLOOR = {1: 0.40, 3: 0.38, 6: 0.35, 12: 0.30, 24: 0.20}   # improvement over "no change" (walk-forward)
COVERAGE80_BAND = 0.07           # |coverage − 0.80| for horizons up to COVERAGE_UP_TO
COVERAGE_UP_TO = 24
COVERAGE80_FLOOR_FAR = 0.65      # at the longest horizon: below this is a WARN (a disclosed limitation)
COVERAGE95_FLOOR = 0.90
ENSEMBLE_VS_BEST_SINGLE = 1.10   # the combination may be at most 10% worse than the best single model (<= 12 months)
IDENTITY_MEDIAN_MAX = 0.30
PAGE_BUDGET_KB = 450             # initial JSON a page must load

Result = tuple  # (id, area, description, status, detail)
results: list[Result] = []


def check(cid: str, area: str, desc: str, ok: bool | None, detail: str, warn: bool = False) -> None:
    status = "PASS" if ok else ("WARN" if warn else "FAIL")
    results.append((cid, area, desc, status, detail))


def run(cmd: list[str]) -> tuple[bool, str]:
    p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True)
    tail = (p.stdout + p.stderr).strip().splitlines()[-3:]
    return p.returncode == 0, " | ".join(tail)


def load_json(path: str):
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


# ----------------------------------------------------------------- data
def data_checks() -> dict:
    panel = load_panel(str(ROOT / "data/processed/housing_indices_clean_v4.csv"))
    rep = panel.validate()
    check("D1", "数据", "面板校验无硬错误（键唯一、取值范围、口径标签、来源、城市名、70 城/月）", rep.ok,
          "; ".join(rep.errors) or f"0 错误，{len(rep.warnings)} 条警告（已列出）")
    sh = rep.stats["secondhand"]
    check("D2", "数据", "二手住宅连续无缺口，到最新月", not sh["missing"] and sh["last"] == panel.last_month,
          f"{sh['first']} → {sh['last']}，{sh['months']} 个月，缺口 {len(sh['missing'])}")
    idn = rep.stats["identity"]["secondhand"]
    check("D3", "数据", f"环比连乘 = 同比（{CONSISTENT_FROM} 起）：中位差与违例城市占比",
          idn["median_gap_since_valid"] <= IDENTITY_MEDIAN_MAX and (idn["max_share_since_valid"] or 0) <= IDENTITY_MAX_SHARE,
          f"中位差 {idn['median_gap_since_valid']}，单月最大违例占比 {idn['max_share_since_valid']}，孤立违例 {idn['violations_since_valid']} 个")
    log = load_json("reports/data_update_log.json")
    log = [log] if isinstance(log, dict) else log
    lm = [r["legacy_mirror"] for r in log if r.get("legacy_mirror")]
    ok = bool(lm) and all(x["compared_cells"] > 0 and x["identical_cells"] == x["compared_cells"] for x in lm)
    check("D4", "数据", "第三方镜像与官方页面在可对照单元逐格一致", ok,
          f"{lm[-1]['identical_cells']}/{lm[-1]['compared_cells']}" if lm else "无记录")
    manifest = load_json("site/data/manifest.json")
    check("D5", "数据", "站点 manifest、预测起点与面板最新月一致",
          manifest["data_through"] == panel.last_month == manifest["forecast"]["origin"],
          f"面板 {panel.last_month}，manifest {manifest['data_through']}，预测起点 {manifest['forecast']['origin']}")
    est = next_release_estimate(panel.last_month)
    check("D6", "数据", "数据是当前最新（下一期预计发布日还没到）", est >= date.today().isoformat(),
          f"最新 {panel.last_month}，下一期预计 {est}，今天 {date.today()}")
    check("D7", "数据", "站内历史起点 = 自洽检验起点", manifest["history_start"] == CONSISTENT_FROM and manifest["bundles"]["cum.json"]["start"] == CONSISTENT_FROM,
          f"history_start={manifest['history_start']}")
    return {"manifest": manifest, "panel": panel}


# ----------------------------------------------------------------- model
def model_checks(manifest: dict, full: bool) -> None:
    rep = load_json("reports/probabilistic_forecast_backtest.json")
    wf = rep["walk_forward"]
    skill = {int(h): v for h, v in wf["skill_vs_flat"].items()}
    cov80 = {int(h): v for h, v in wf["coverage"]["80"].items()}
    cov95 = {int(h): v for h, v in wf["coverage"]["95"].items()}
    bad = {h: round(skill[h], 3) for h, floor in SKILL_FLOOR.items() if skill[h] < floor}
    check("M1", "模型", "滚动回测：相对“价格不变”的误差改善不低于下限", not bad,
          ", ".join(f"+{h}: {skill[h]:.0%}≥{f:.0%}" for h, f in SKILL_FLOOR.items()) + (f"；未达标 {bad}" if bad else ""))
    off = {h: round(c, 3) for h, c in cov80.items() if h <= COVERAGE_UP_TO and abs(c - 0.8) > COVERAGE80_BAND}
    check("M2", "模型", f"80% 区间实际覆盖率在 0.80±{COVERAGE80_BAND}（+{COVERAGE_UP_TO} 个月内）", not off,
          ", ".join(f"+{h}: {c:.2f}" for h, c in sorted(cov80.items()) if h <= COVERAGE_UP_TO) + (f"；偏离 {off}" if off else ""))
    far = max(cov80)
    check("M3", "模型", f"最远期限（+{far}）的 80% 覆盖率", cov80[far] >= COVERAGE80_FLOOR_FAR, f"{cov80[far]:.2f}（下限 {COVERAGE80_FLOOR_FAR}；站内已按此标注）", warn=True)
    check("M4", "模型", "95% 区间实际覆盖率各期限不低于下限", all(c >= COVERAGE95_FLOOR for c in cov95.values()),
          ", ".join(f"+{h}: {c:.2f}" for h, c in sorted(cov95.items())))
    mae = {m: {int(h): v for h, v in d.items()} for m, d in wf["mae_pct_points"].items()}
    singles = ["naive", "drift12", "ar1", "damped", "global", "chronos2"]
    worst = {}
    for h in (1, 3, 6, 12):
        best = min(mae[m][h] for m in singles if h in mae[m])
        if mae["ensemble"][h] > ENSEMBLE_VS_BEST_SINGLE * best:
            worst[h] = (mae["ensemble"][h], best)
    check("M5", "模型", f"组合不比最佳单模型差超过 {int((ENSEMBLE_VS_BEST_SINGLE - 1) * 100)}%（+12 个月内）", not worst,
          ", ".join(f"+{h}: 组合 {mae['ensemble'][h]:.2f} / 最佳单 {min(mae[m][h] for m in singles if h in mae[m]):.2f}" for h in (1, 3, 6, 12)))
    hc = rep["hindcast"]
    inside = [hc["regions"]["全国"][k] for k in hc["regions"]["全国"]]
    ok_hc = all(x["lo80"] <= x["actual"] <= x["hi80"] for x in inside)
    check("M6", "模型", "实战回放：全国实际值全部落在 80% 区间内", ok_hc, f"起点 {hc['origin']}，{len(inside)} 个月", warn=True)
    ok, tail = run([sys.executable, "-m", "unittest", "tests.test_update_and_forecast.LearnAtTests", "-q"])
    check("M7", "模型", "无前视：未实现的起点不影响权重与区间（单元测试）", ok, tail)

    frame = pd.read_csv(ROOT / "data/processed/city_forecast_paths.csv")
    regions = frame["region"].nunique()
    qcols = ["q025", "q100", "q500", "q900", "q975"]
    mono = bool((frame[qcols].diff(axis=1).iloc[:, 1:] >= -1e-9).all().all())
    rng_ok = bool(frame[qcols].to_numpy().min() > 40 and frame[qcols].to_numpy().max() < 250)
    check("M8", "模型", "预测文件完整且合理：71 个地区 × 36 个月，分位数单调，指数在合理范围", regions == 71 and len(frame) == 71 * 36 and mono and rng_ok,
          f"{regions} 个地区，{len(frame)} 行，单调={mono}，范围 {frame[qcols].to_numpy().min():.0f}–{frame[qcols].to_numpy().max():.0f}")
    ledger = ROOT / "reports" / "forecast_ledger" / f"{manifest['data_through']}.csv"
    same = ledger.exists() and np.allclose(pd.read_csv(ledger)[qcols].to_numpy(), frame[qcols].to_numpy(), atol=1e-6)
    check("M9", "模型", "预测账本已冻结，且与当前预测文件一致", bool(same), f"{ledger.name} {'一致' if same else '缺失或不一致（重新冻结前须确认没有新数据公布）'}")
    zones = manifest["forecast"]
    check("M10", "模型", "可信度分区由回测计算（可作预测 ≤ 谨慎参考 ≤ 预测期）",
          0 < zones["reliable_through"] <= zones["caution_through"] <= zones["horizon_months"],
          f"可作预测 +{zones['reliable_through']}，谨慎参考 +{zones['caution_through']}，预测期 +{zones['horizon_months']}")
    if full:
        before = frame[qcols].to_numpy().copy()
        ok, tail = run([sys.executable, "-m", "src.probabilistic_forecast", "--tsfm", "data/processed/chronos2_paths.json"])
        after = pd.read_csv(ROOT / "data/processed/city_forecast_paths.csv")[qcols].to_numpy()
        check("M11", "模型", "可复现：用同样的输入重跑，预测逐值相同", ok and np.allclose(before, after, atol=1e-6), tail if not ok else f"最大差 {np.abs(before - after).max():.2e}")
    else:
        results.append(("M11", "模型", "可复现：重跑预测逐值相同", "SKIP", "加 --full 运行"))


# ----------------------------------------------------------------- site
def site_checks(manifest: dict) -> None:
    ok, tail = run([sys.executable, "-m", "unittest", "discover", "-s", "tests", "-q"])
    check("S1", "站点", "Python 测试全部通过（含数据面板校验、站点契约）", ok, tail)
    p = subprocess.run(["node", "--test", *map(str, sorted((ROOT / "tests/js").glob("*.test.mjs")))], cwd=ROOT, capture_output=True, text=True)
    import re as _re
    counts = dict(_re.findall(r"ℹ (tests|pass|fail) (\d+)", p.stdout))
    check("S2", "站点", "JS 纯函数模块测试全部通过", p.returncode == 0 and counts.get("fail") == "0", f"{counts.get('pass')}/{counts.get('tests')} 通过")
    bad = []
    for path in sorted((ROOT / "site/assets/js").rglob("*.js")):
        p = subprocess.run(["node", "--input-type=module", "--check"], input=path.read_text(encoding="utf-8"), capture_output=True, text=True)
        if p.returncode:
            bad.append(path.name)
    check("S3", "站点", "所有 JS 模块语法正确", not bad, f"{len(list((ROOT / 'site/assets/js').rglob('*.js')))} 个文件" + (f"；错误 {bad}" if bad else ""))
    # initial JSON payload per page, from the manifest sizes
    import re
    heavy = {}
    for page in sorted((ROOT / "site/assets/js/pages").glob("*.js")):
        text = page.read_text(encoding="utf-8")
        names = re.findall(r'boot\(\s*"[a-z]+"\s*,\s*\[([^\]]*)\]', text)
        total = sum(manifest["bundles"][f"{n}.json"]["bytes"] for g in names for n in re.findall(r'"([a-z_0-9]+)"', g)) + 2000
        heavy[page.stem] = round(total / 1024)
    over = {k: v for k, v in heavy.items() if v > PAGE_BUDGET_KB}
    check("S4", "站点", f"每页首屏 JSON 不超过 {PAGE_BUDGET_KB} KB", not over, ", ".join(f"{k} {v}KB" for k, v in heavy.items()))
    check("S5", "站点", "页面数量与文档一致（7 个页面、下载文件齐全）",
          len(list((ROOT / "site").glob("*.html"))) == 7 and len(manifest["downloads"]) >= 3,
          f"{len(list((ROOT / 'site').glob('*.html')))} 个页面，{len(manifest['downloads'])} 个下载")


def docs_checks() -> None:
    need = ["README.md", "docs/research-2026-11-upgrade.md", "docs/site-architecture.md", "site/README.md", "docs/project.md", "scripts/monthly_update.sh"]
    missing = [p for p in need if not (ROOT / p).exists()]
    check("R1", "文档", "README、调研、站点架构、更新脚本齐全", not missing, "齐全" if not missing else f"缺 {missing}")
    text = (ROOT / "docs/research-2026-11-upgrade.md").read_text(encoding="utf-8")
    check("R2", "文档", "调研文档如实记录了更正与局限（CIREA、2006–2007 不自洽、非盲选规则）",
          all(k in text for k in ("CIREA", "不通过", "不是盲选")), "三处关键更正均已写入")


MANUAL = [
    "浏览器逐页冒烟（总览、城市榜、城市页、数据统计、预测逻辑、数据与方法、论文）：无控制台错误、无空的时间标注",
    "折线 / K 线切换；深色 / 浅色；手机宽度无横向溢出",
    "论文双仓同步修订（本仓库与 liyuk.github.io）——不在本次范围，列在论文页“待修订项”",
]


def write_report(path: Path) -> int:
    fails = [r for r in results if r[3] == "FAIL"]
    lines = [f"# 验收报告 {date.today()}", "",
             f"结论：**{'通过' if not fails else '未通过'}**（{sum(r[3] == 'PASS' for r in results)} PASS · {sum(r[3] == 'WARN' for r in results)} WARN · "
             f"{len(fails)} FAIL · {sum(r[3] == 'SKIP' for r in results)} SKIP）", "",
             "> 模型阈值是下限，用来防止退化，不是对模型好坏的认证；它们是在看到回测结果之后设定的，留有余量。", "",
             "| 编号 | 领域 | 检查项 | 结果 | 实测 |", "|---|---|---|---|---|"]
    for cid, area, desc, status, detail in results:
        lines.append(f"| {cid} | {area} | {desc} | **{status}** | {detail.replace('|', '/')} |")
    manual = ROOT / "reports" / "acceptance_manual.md"
    lines += ["", "## 人工验收记录（脚本无法判断）", ""]
    lines += [manual.read_text(encoding="utf-8").rstrip()] if manual.exists() else [f"- [ ] {m}" for m in MANUAL]
    lines += [""]
    path.write_text("\n".join(lines), encoding="utf-8")
    return 1 if fails else 0


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--full", action="store_true", help="re-run the forecast and check reproducibility (slow)")
    parser.add_argument("--output", default=f"reports/acceptance_{date.today()}.md")
    args = parser.parse_args()
    ctx = data_checks()
    model_checks(ctx["manifest"], args.full)
    site_checks(ctx["manifest"])
    docs_checks()
    code = write_report(ROOT / args.output)
    for cid, area, desc, status, detail in results:
        print(f"[{status:4s}] {cid:4s} {desc} — {detail[:110]}")
    print(f"\nreport: {args.output}  exit={code}")
    raise SystemExit(code)


if __name__ == "__main__":
    main()
