#!/bin/bash
# 조위관측소 QC 웹앱을 외부(http://27.112.246.50:8501/)에 노출.
#   8502? 아니오 — 외부 허용 포트는 8501 하나. 8501 relay 타겟을 8002(QC)로 전환한다.
#   ※ 이렇게 하면 NOSC 플랫폼(8000)은 외부 8501에서 일시적으로 보이지 않는다.
#     (내부 8000 자체는 계속 동작) NOSC를 다시 외부로 되돌리려면
#     RELAY_TARGET_PORT=8000 으로 relay 를 재기동하면 된다.
set -u
PY=/home/mwcho/anaconda3/bin/python3
APPDIR=/home/data1/geosr/mwcho/claude_agent/qc_webapp
RELAY=/home/data1/geosr/mwcho/claude_agent/relay_8501.py

echo "▶ QC 웹앱(8002) 재기동…"
pkill -f "qc_webapp/app.py" 2>/dev/null; sleep 1
( cd "$APPDIR" && PORT=8002 nohup "$PY" app.py > /tmp/qc_webapp.log 2>&1 & )

echo "▶ 워치독(8002 자동 복구) 기동…"
pkill -f "qc_webapp/watchdog.sh" 2>/dev/null
nohup bash "$APPDIR/watchdog.sh" > /tmp/qc_watchdog_run.log 2>&1 &

echo "▶ 외부 relay 8501 → 8002(QC) 전환…"
pkill -f "relay_8501.py" 2>/dev/null; sleep 1
fuser -k 8501/tcp 2>/dev/null; sleep 1   # 8501 다른 점유자(skill_score Streamlit 등) 정리
RELAY_TARGET_PORT=8002 nohup "$PY" "$RELAY" > /tmp/qc_relay.log 2>&1 &

sleep 2
if curl -s -o /dev/null --max-time 4 http://127.0.0.1:8002/api/health; then
  echo "✅ 완료 — 외부 접속: http://27.112.246.50:8501/"
else
  echo "⚠ QC 서버 헬스체크 실패 — /tmp/qc_webapp.log 확인"
fi
