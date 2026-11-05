"""Design-system checks for the static site (used by scripts/acceptance.py).

Two kinds of check, both read straight from the source files so they cannot drift from what ships:

  * contrast   -- WCAG ratios computed from the tokens in site/assets/styles.css, in both themes.
                  Text roles need 4.5:1; data colours (lines, bars) need 3:1.
  * patterns   -- things the design brief forbids, scanned in CSS/JS/HTML: coloured side stripes, glyphs
                  standing in for icons, a second display font, modals, hero-metric markup, entrance
                  animations, decorative shadows around cards, a forced theme.

Each function returns [(id, description, ok, detail)].
"""

from __future__ import annotations

import colorsys
import re
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
CSS = SITE / "assets" / "styles.css"

TEXT_ROLES = ["foreground", "muted-foreground", "ink-2", "up", "down", "gold-text"]
DATA_ROLES = ["gold", "blue", "orange"]
MIN_TEXT, MIN_DATA = 4.5, 3.0


# ---------------------------------------------------------------- colour parsing
def _hsl(h: float, s: float, l: float) -> tuple[float, float, float]:
    r, g, b = colorsys.hls_to_rgb(h / 360.0, l / 100.0, s / 100.0)
    return r, g, b


def parse_color(value: str, tokens: dict[str, str], depth: int = 0) -> tuple[float, float, float] | None:
    value = value.strip()
    m = re.fullmatch(r"var\(--([a-z0-9-]+)\)", value)
    if m and depth < 6 and m.group(1) in tokens:
        return parse_color(tokens[m.group(1)], tokens, depth + 1)
    m = re.fullmatch(r"#([0-9a-fA-F]{6})", value)
    if m:
        h = m.group(1)
        return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    m = re.fullmatch(r"hsl\(\s*([\d.]+)\s+([\d.]+)%\s+([\d.]+)%\s*\)", value)
    if m:
        return _hsl(float(m.group(1)), float(m.group(2)), float(m.group(3)))
    return None


def luminance(rgb: tuple[float, float, float]) -> float:
    f = lambda c: c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    r, g, b = (f(c) for c in rgb)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def theme_tokens(css: str) -> dict[str, dict[str, str]]:
    """{'light': {...}, 'dark': {...}} -- dark inherits whatever it does not override."""
    def block(selector: str) -> dict[str, str]:
        m = re.search(re.escape(selector) + r"\s*\{(.*?)\n\}", css, re.S)
        return dict(re.findall(r"--([a-z0-9-]+):\s*([^;]+);", m.group(1))) if m else {}

    light = block(":root")
    dark = {**light, **block(':root[data-theme="dark"]')}
    return {"light": light, "dark": dark}


# ---------------------------------------------------------------- checks
def contrast_checks() -> list[tuple]:
    css = CSS.read_text(encoding="utf-8")
    out = []
    for theme, tokens in theme_tokens(css).items():
        bg = parse_color(tokens["background"], tokens)
        rows, bad = [], []
        for role in TEXT_ROLES:
            c = parse_color(tokens[role], tokens)
            ratio = contrast(c, bg)
            rows.append(f"{role} {ratio:.1f}")
            if ratio < MIN_TEXT:
                bad.append(f"{role} {ratio:.2f}")
        out.append((f"T-{theme}", f"文字对比度 ≥ {MIN_TEXT}:1（{theme} 主题，相对背景）", not bad, "；".join(rows) + (f"；未达标 {bad}" if bad else "")))
        rows, bad = [], []
        for role in DATA_ROLES:
            ratio = contrast(parse_color(tokens[role], tokens), bg)
            rows.append(f"{role} {ratio:.1f}")
            if ratio < MIN_DATA:
                bad.append(f"{role} {ratio:.2f}")
        out.append((f"D-{theme}", f"数据色（折线/柱）对比度 ≥ {MIN_DATA}:1（{theme} 主题）", not bad, "；".join(rows) + (f"；未达标 {bad}" if bad else "")))
        pf = contrast(parse_color(tokens["primary-foreground"], tokens), parse_color(tokens["primary"], tokens))
        out.append((f"P-{theme}", f"主按钮文字对比度 ≥ {MIN_TEXT}:1（{theme} 主题）", pf >= MIN_TEXT, f"{pf:.1f}"))
    return out


def _read(paths) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in paths)


def pattern_checks(css: str | None = None, js: str | None = None, html: str | None = None) -> list[tuple]:
    """Scan the shipped sources, or the given strings (the tests feed deliberately bad ones)."""
    css = CSS.read_text(encoding="utf-8") if css is None else css
    html_files = sorted(SITE.glob("*.html"))
    js = _read(sorted((SITE / "assets" / "js").rglob("*.js"))) if js is None else js
    html = _read(html_files) if html is None else html
    out = []

    stripes = [m for m in re.findall(r"border-(?:left|right)\s*:\s*([^;]+);", css) if not re.match(r"\s*(0|none|1px\s+solid\s+var\(--border\))", m)]
    out.append(("B1", "没有彩色侧边竖条（border-left/right 非 1px 中性色）", not stripes, f"{len(stripes)} 处" + (f"：{stripes[:2]}" if stripes else "")))

    glyphs = [g for g in ("✓", "✗", "✔", "✘", "★", "▲", "▼") if g in js or g in html]
    out.append(("B2", "没有用字符冒充图标（✓ ✗ ▲ ▼ 等）；图标来自统一的 Lucide 模块", not glyphs, f"发现 {glyphs}" if glyphs else "无"))

    fam = set(re.findall(r"font-family\s*:\s*([^;]+);", css)) | set(re.findall(r"--font:\s*([^;]+);", css))
    fams = {f.strip().split(",")[0].strip().strip('"') for f in fam}
    fams.discard("ui-monospace")                                     # code spans only
    out.append(("B3", "一个字体族（Geist，中文回退系统字体），没有衬线展示字体", fams <= {"Geist", '"Geist"', "var(--font)"} and "serif" not in css.lower().replace("sans-serif", ""), f"{sorted(fams)}"))

    modals = re.findall(r"class=\"[^\"]*\bmodal[^\"]*\"|role=\"dialog\"|\.modal\b", html + js + css)
    out.append(("B4", "没有为非阻断任务使用弹窗（口径说明是页面章节）", not modals, f"{len(modals)} 处" if modals else "无"))

    hero = re.findall(r"class=\"[^\"]*\b(?:kpis|kpi|stat-tile)\b", html + js)
    out.append(("B5", "没有“大数字 + 小标签”的 hero-metric 模板（关键数字用表格）", not hero, "无" if not hero else f"{hero[:2]}"))

    anim = re.findall(r"@keyframes\s+([a-z0-9-]+)", css)
    out.append(("B6", "没有装饰性入场动画（唯一的 keyframes 是加载骨架）", set(anim) <= {"sk"}, f"{anim}"))

    shadows = re.findall(r"box-shadow\s*:\s*([^;]+);", css)
    heavy = [s for s in shadows if re.search(r"-?\d+(?:px)?\s+-?\d+(?:px)?\s+(?:[2-9]\d|\d{3,})px", s)]   # offset-x may be a bare 0
    out.append(("B7", "没有大范围软阴影（边框与阴影二选一：卡片只用边框）", not heavy, f"{len(heavy)} 处" if heavy else "无"))

    forced = 'data-theme="dark"' in re.sub(r":root\[data-theme=\"dark\"\]", "", html)
    out.append(("B8", "主题跟随系统，没有强制深色/浅色", not forced and "prefers-color-scheme" in html, "页面头部脚本读取 prefers-color-scheme"))

    needs = {"::selection": "文字选中色", "caret-color": "输入光标色", "accent-color": "勾选框强调色", "scrollbar-color": "滚动条", ":focus-visible": "键盘焦点环", "tnum": "等宽数字（表格）"}
    miss = [name for key, name in needs.items() if key not in css and not (key == "tnum" and "tabular-nums" in css)]
    out.append(("B9", "浏览器默认元素已用色板主题化（选中色、光标、勾选框、滚动条、焦点环、数字）", not miss, "齐全" if not miss else f"缺 {miss}"))

    pages = {p.name: p.read_text(encoding="utf-8") for p in html_files} if html_files and html == _read(html_files) else {"(input)": html}
    main_missing = [n for n, t in pages.items() if "<main" not in t]
    nav_missing = [n for n, t in pages.items() if 'id="shell-header"' not in t]
    nav_hidden = any(re.search(r"display\s*:\s*none", blk) for blk in re.findall(r"(?<![\w-])\.nav\s*\{[^}]*\}", css))   # every .nav rule, incl. media queries
    out.append(("B10", "每页有 <main> 与统一页眉，导航在任何宽度都不隐藏", not main_missing and not nav_missing and not nav_hidden, f"缺 main {main_missing}，缺页眉 {nav_missing}，导航被隐藏 {nav_hidden}"))
    return out


def run_checks() -> list[tuple]:
    return contrast_checks() + pattern_checks()


if __name__ == "__main__":
    for cid, desc, ok, detail in run_checks():
        print(f"[{'PASS' if ok else 'FAIL'}] {cid:7s} {desc} — {detail}")
