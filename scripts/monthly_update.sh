#!/usr/bin/env bash
# Monthly refresh: new NBS/PBOC/creprice data -> validate -> forecast -> site bundles -> acceptance gate.
# NBS publishes the 70-city report around the 15th-17th of each month.
#
#   bash scripts/monthly_update.sh
#
# Chronos-2 is optional: set TSFM_PY to a python with torch + chronos-forecasting
# (see requirements-tsfm.txt); without it the forecast runs on the local models only.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python

$PY -m src.update_data
# district reports: re-fetch the last three months (cached pages are never re-fetched, so this is cheap)
START=$($PY -c 'import datetime as d; t = d.date.today(); m = t.year * 12 + t.month - 4; print(f"{m // 12}-{m % 12 + 1:02d}")')
$PY -m src.creprice_panel --start "$START" --end "$(date +%Y-%m)" --output /tmp/creprice_district_panel.csv || echo "creprice update failed; continuing with cached pages"
$PY -m src.panel   # stop here if the new data fail validation
$PY -m src.probabilistic_forecast --export-returns
TSFM_ARG=()
if [[ -n "${TSFM_PY:-}" ]]; then
  "$TSFM_PY" src/tsfm_baseline.py
  TSFM_ARG=(--tsfm data/processed/chronos2_paths.json)
fi
$PY -m src.probabilistic_forecast "${TSFM_ARG[@]}"
$PY scripts/build_demo_data.py
$PY scripts/acceptance.py
echo "done. Review 'git status', then commit site/ and reports/forecast_ledger."
