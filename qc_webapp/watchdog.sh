#!/bin/bash
# 조위관측소 QC 웹앱(8002) 감시: 응답 없으면 자동 재기동
# (NOSC 8000 / 연안침수 8001 은 건드리지 않음)
cd /home/data1/geosr/mwcho/claude_agent/qc_webapp || exit 1
PY=/home/mwcho/anaconda3/bin/python3
PORT="${PORT:-8002}"
while true; do
  if ! curl -s -o /dev/null --max-time 4 "http://127.0.0.1:${PORT}/api/health" 2>/dev/null; then
    fuser -k "${PORT}/tcp" 2>/dev/null
    sleep 1
    PORT="$PORT" nohup "$PY" app.py >> /tmp/qc_webapp.log 2>&1 &
    echo "[watchdog $(date '+%F %T')] ${PORT} 재기동" >> /tmp/qc_watchdog.log
    sleep 8
  fi
  sleep 15
done
