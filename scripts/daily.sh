#!/bin/bash
# Daily NAV refresh + report generation.
# Intended to run each morning (see README "Daily automation"), after the
# previous day's fund NAVs have been published.
#
# Environment overrides:
#   MUTUAL_FUND_DATA     data directory (default: <repo>/data)
#   MUTUAL_FUND_REPORTS  output/log directory (default: ~/Documents/Mutual-Fund-Reports)
#   MUTUAL_FUND_FROM     report start date, YYYY-MM-DD (default: 2026-01-01)

set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO"

PYTHON="$(command -v python3)"
DATA_DIR="${MUTUAL_FUND_DATA:-$REPO/data}"
LOG_DIR="${MUTUAL_FUND_REPORTS:-$HOME/Documents/Mutual-Fund-Reports}"
FROM="${MUTUAL_FUND_FROM:-2026-01-01}"
mkdir -p "$LOG_DIR"

run() {
  PYTHONPATH="$REPO/src" "$PYTHON" -m mutual_fund --data "$DATA_DIR" "$@"
}

{
  echo "=== $(date '+%Y-%m-%d %H:%M:%S') daily run ==="
  # Fetching can fail (network hiccup, changed source page) — that should not
  # stop the report from being generated with the NAVs we already have.
  run fetch-nav || echo "fetch-nav failed (continuing with existing NAVs)"
  run fetch-fx || echo "fetch-fx failed (continuing with existing rates)"
  run report --from "$FROM" --out "$LOG_DIR" || echo "report failed"
  echo
} >> "$LOG_DIR/daily.log" 2>&1

echo "Done. Log: $LOG_DIR/daily.log"
