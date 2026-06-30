#!/usr/bin/env bash
# OBS 미수집 기록 + 지연 재수집 진입점 (collect_test 샌드박스)
# 사용:
#   run_recollect.sh                 # pass: detect->backfill->sweep (기본, 기준=어제)
#   run_recollect.sh detect --date 20260628 --lookback 7
#   run_recollect.sh backfill --limit 3
#   run_recollect.sh sweep
#   run_recollect.sh backfill --force --provider khoa --dataset tidal --date 20260628
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PY=/home/collect/appl/miniconda3/envs/dataenv/bin/python
exec "$PY" "$SCRIPT_DIR/libs/recollect.py" "$@"
