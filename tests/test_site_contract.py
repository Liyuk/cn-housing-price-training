"""Contract between the Python build and the static pages.

The manifest is the seam: pages ask for bundles by name and take every date,
span and frequency from the manifest.  These tests fail if a page references a
bundle that is not built, a label that names an unknown bundle, a script that
does not exist, or an ES-module import that does not resolve.
"""

import json
import re
import unittest
from pathlib import Path

SITE = Path(__file__).resolve().parent.parent / "site"
JS = SITE / "assets" / "js"


def manifest() -> dict:
    return json.loads((SITE / "data" / "manifest.json").read_text(encoding="utf-8"))


class SiteContractTests(unittest.TestCase):
    def test_every_bundle_a_page_loads_is_built_and_in_the_manifest(self):
        bundles = set(manifest()["bundles"])
        loaded = set()
        for path in (JS / "pages").glob("*.js"):
            text = path.read_text(encoding="utf-8")
            for group in re.findall(r'boot\(\s*"[a-z]+"\s*,\s*\[([^\]]*)\]', text):
                loaded.update(re.findall(r'"([a-z_0-9]+)"', group))
            loaded.update(re.findall(r'(?:Data\.(?:load|tryLoad)|load)\(\s*"([a-z_0-9]+)"\s*\)', text))
        loaded.discard("manifest")
        self.assertTrue(loaded, "no bundle references found: the pattern must be stale")
        for name in sorted(loaded):
            self.assertTrue((SITE / "data" / f"{name}.json").exists(), f"{name}.json is loaded by a page but not built")
            self.assertIn(f"{name}.json", bundles, f"{name}.json is built but missing from the manifest")

    def test_vintage_labels_name_real_bundles(self):
        info = set(manifest()["bundles"]) | set(manifest().get("districts", {}))
        for page in SITE.glob("*.html"):
            for kind in ("data-vintage", "data-span"):
                for name in re.findall(rf'{kind}="([^"]+)"', page.read_text(encoding="utf-8")):
                    self.assertIn(name, info, f"{page.name}: {kind}={name!r} is not in the manifest")

    def test_pages_have_their_script_and_no_hardcoded_data_through_date(self):
        data_through = manifest()["data_through"]
        for page in SITE.glob("*.html"):
            text = page.read_text(encoding="utf-8")
            script = re.search(r'src="(assets/js/pages/[a-z]+\.js)"', text)
            self.assertIsNotNone(script, f"{page.name} has no page script")
            self.assertTrue((SITE / script.group(1)).exists())
            # "data through" must come from the manifest, never be typed into a page
            self.assertNotIn(f"截至 {data_through}", text, f"{page.name} hard-codes the data-through month")

    def test_every_es_module_import_resolves(self):
        for path in JS.rglob("*.js"):
            for spec in re.findall(r'from\s+"(\.[^"]+)"', path.read_text(encoding="utf-8")):
                self.assertTrue((path.parent / spec).resolve().exists(), f"{path.relative_to(SITE)} imports missing {spec}")

    def test_manifest_describes_every_built_file(self):
        m = manifest()
        for name in m["bundles"]:
            self.assertTrue((SITE / "data" / name).exists(), name)
        for city, info in m["districts"].items():
            self.assertTrue((SITE / info["file"]).exists(), info["file"])
        for d in m["downloads"]:
            self.assertTrue((SITE / d["file"]).exists(), d["file"])

    def test_time_fields_are_consistent(self):
        m = manifest()
        self.assertRegex(m["data_through"], r"^\d{4}-\d{2}$")
        self.assertRegex(m["next_release_estimate"], r"^\d{4}-\d{2}-\d{2}$")
        self.assertGreater(m["next_release_estimate"][:7], m["data_through"])          # the next report is after the latest one
        cum = m["bundles"]["cum.json"]
        self.assertEqual(cum["end"], m["data_through"])                                 # chart history ends at the panel's last month
        fan = m["bundles"]["fan.json"]
        self.assertEqual(fan["origin"], m["data_through"])                              # forecast starts where the data ends
        self.assertGreater(fan["start"], fan["origin"])
        self.assertLess(m["regime_break"]["month"], m["data_through"])
        self.assertEqual(cum["start"], m["history_start"])                              # history starts where the data become consistent
        z = m["forecast"]
        self.assertLessEqual(z["reliable_through"], z["caution_through"])               # zones come from the scorecard, in order
        self.assertLessEqual(z["caution_through"], z["horizon_months"])
        self.assertGreater(z["reliable_through"], 0)

    def test_new_home_series_line_up_with_the_second_hand_series(self):
        load = lambda n: json.loads((SITE / "data" / n).read_text(encoding="utf-8"))
        cum, new = load("cum.json"), load("cum_new.json")
        self.assertEqual(cum["months"], new["months"])                                  # overlays are index-aligned in the trend view
        self.assertEqual(set(cum["series"]), set(new["series"]))
        self.assertEqual(cum["regime_break"], new["regime_break"])
        self.assertTrue(all(len(v) == len(new["months"]) for v in new["series"].values()))

    def test_the_ledger_bundle_matches_the_frozen_files_it_describes(self):
        import hashlib
        root = SITE.parent
        ledger = json.loads((SITE / "data" / "ledger.json").read_text(encoding="utf-8"))
        self.assertTrue(ledger["entries"])
        for e in ledger["entries"]:
            frozen = root / e["frozen"]["file"]
            self.assertEqual(e["frozen"]["sha256"], hashlib.sha256(frozen.read_bytes()).hexdigest(), f"{e['origin']}: bundle is stale")
            self.assertEqual(len(e["months"]), manifest()["forecast"]["horizon_months"])
            self.assertLessEqual(len(e["actual"]["months"]), len(e["months"]))
        self.assertEqual(ledger["entries"][-1]["origin"], manifest()["forecast"]["origin"])   # the latest forecast is in the ledger


if __name__ == "__main__":
    unittest.main()
