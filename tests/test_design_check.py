import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import design_check as dc  # noqa: E402


class ColourMathTests(unittest.TestCase):
    def test_contrast_extremes_and_hsl_parsing(self):
        self.assertAlmostEqual(dc.contrast((0, 0, 0), (1, 1, 1)), 21.0, places=3)
        self.assertAlmostEqual(dc.contrast((1, 1, 1), (1, 1, 1)), 1.0, places=6)
        white = dc.parse_color("hsl(0 0% 100%)", {})
        self.assertEqual(tuple(round(c, 3) for c in white), (1.0, 1.0, 1.0))
        self.assertEqual(tuple(round(c * 255) for c in dc.parse_color("#2a78d6", {})), (0x2a, 0x78, 0xd6))

    def test_var_aliases_resolve_and_cycles_stop(self):
        tokens = {"a": "var(--b)", "b": "#ffffff", "x": "var(--y)", "y": "var(--x)"}
        self.assertEqual(dc.parse_color("var(--a)", tokens), (1.0, 1.0, 1.0))
        self.assertIsNone(dc.parse_color("var(--x)", tokens))

    def test_a_low_contrast_text_token_is_caught(self):
        css = ":root {\n  --background: hsl(0 0% 100%);\n  --foreground: hsl(0 0% 10%);\n  --muted-foreground: hsl(0 0% 75%);\n}\n"
        tokens = dc.theme_tokens(css)["light"]
        ratio = dc.contrast(dc.parse_color(tokens["muted-foreground"], tokens), dc.parse_color(tokens["background"], tokens))
        self.assertLess(ratio, dc.MIN_TEXT)


class BannedPatternTests(unittest.TestCase):
    GOOD_CSS = ".nav { display: flex; }\n.panel { border: 1px solid var(--border); }\n::selection{} input{caret-color:red;accent-color:red;scrollbar-color:red}\n:focus-visible{} td{font-variant-numeric:tabular-nums}\nbody{font-family:\"Geist\",sans-serif}\n--font: \"Geist\", sans-serif;"
    GOOD_HTML = '<head><script>matchMedia("(prefers-color-scheme: dark)")</script></head><div id="shell-header"></div><main></main>'

    def _failed(self, **kw):
        base = dict(css=self.GOOD_CSS, js="", html=self.GOOD_HTML)
        base.update(kw)
        return {cid for cid, _, ok, _ in dc.pattern_checks(**base) if not ok}

    def test_the_good_baseline_passes_everything(self):
        self.assertEqual(self._failed(), set())

    def test_side_stripe_is_caught(self):
        self.assertIn("B1", self._failed(css=self.GOOD_CSS + "\n.callout { border-left: 3px solid gold; }"))

    def test_glyph_icons_are_caught(self):
        self.assertIn("B2", self._failed(js='el.innerHTML = "✓ 区间内"'))

    def test_serif_display_font_is_caught(self):
        self.assertIn("B3", self._failed(css=self.GOOD_CSS + '\nh1 { font-family: "Songti SC", serif; }'))

    def test_modal_is_caught(self):
        self.assertIn("B4", self._failed(html=self.GOOD_HTML + '<div class="modal-back"></div>'))

    def test_hero_metric_markup_is_caught(self):
        self.assertIn("B5", self._failed(html=self.GOOD_HTML + '<div class="kpis"></div>'))

    def test_entrance_animation_is_caught(self):
        self.assertIn("B6", self._failed(css=self.GOOD_CSS + "\n@keyframes fadeUp { from { opacity: 0 } }"))

    def test_big_soft_shadow_is_caught(self):
        self.assertIn("B7", self._failed(css=self.GOOD_CSS + "\n.panel { box-shadow: 0 12px 40px rgba(0,0,0,.35); }"))

    def test_forced_theme_is_caught(self):
        self.assertIn("B8", self._failed(html=self.GOOD_HTML.replace("<head>", '<html data-theme="dark"><head>')))

    def test_missing_browser_surface_theming_is_caught(self):
        self.assertIn("B9", self._failed(css=self.GOOD_CSS.replace("::selection{}", "")))

    def test_hidden_mobile_nav_is_caught(self):
        """The bug this check exists for: the nav was hidden inside a media query."""
        css = self.GOOD_CSS + "\n@media (max-width: 900px) {\n  .nav { display: none; }\n}"
        self.assertIn("B10", self._failed(css=css))


class ShippedSiteTests(unittest.TestCase):
    def test_the_real_site_passes_every_check(self):
        failed = [(cid, detail) for cid, _, ok, detail in dc.run_checks() if not ok]
        self.assertEqual(failed, [])


if __name__ == "__main__":
    unittest.main()
