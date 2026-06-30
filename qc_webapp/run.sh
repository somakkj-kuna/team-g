#!/usr/bin/env bash
# 조위관측소 수온 QC 웹앱 실행 스크립트
# 사용법:  bash run.sh        (기본 포트 8002)
#          PORT=9002 bash run.sh
set -e
cd "$(dirname "$0")"
PY=/home/mwcho/anaconda3/bin/python3   # flask 보유 (base 3.9)
PORT="${PORT:-8002}"
echo "▶ 조위관측소 수온 QC 웹앱 시작 — http://$(hostname -I | awk '{print $1}'):${PORT}/"
PORT="$PORT" exec "$PY" app.py
