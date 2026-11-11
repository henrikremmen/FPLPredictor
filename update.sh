#!/usr/bin/env bash
# Routine update in one command. Every step works out by itself what is due.
#   ./update.sh           own data, fresh forecast, prospective loop, top managers
#   ./update.sh retrain   also rebuild the training table and retrain before the forecast (slow)
set -euo pipefail
cd "$(dirname "$0")"
py=.venv/bin/python
step() { printf '\n== %s\n' "$1"; }

step "Own data (fpl-data)"
$py src/fpl_collect.py --data-root fpl-data auto
if [ -n "$(git -C fpl-data status --porcelain)" ]; then
  git -C fpl-data add -A
  git -C fpl-data commit -qm "data: local $(date -u +%FT%H:%MZ)"  # local history only, no push
fi

if [ "${1:-}" = retrain ]; then
  step "Training table and features"
  $py src/build_dataset.py
  $py src/build_features.py
  step "Retrain"
  $py src/nextgen_models.py
  $py src/decision_backtest.py
  $py src/production_models.py
fi

step "Forecast"
$py src/capture_fpl.py

# After the forecast, so a lock inside the 30-hour window reuses it instead of capturing again.
step "Prospective loop"
$py src/prospective_loop.py auto

step "Top managers"
$py src/top_managers.py collect

printf '\nDone.\n'
