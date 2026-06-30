# -*- coding: utf-8 -*-
"""조위관측소 수온 QC 웹앱 — Flask 백엔드.

엔드포인트
  GET  /                          정적 SPA(index.html)
  GET  /api/health               헬스체크
  GET  /api/stations             관측소 목록(메타)
  GET  /api/qc?obs=DT_0001&...    단일 관측소 시계열 + QC 결과
  GET  /api/qc/summary?...        전 관측소 QC 요약(이상치 개수 등)
  POST /api/chat                  데이터(QC 결과) 기반 LLM 분석
  POST /api/report                분석 내용 → 한글(HWPX) 보고서 생성
  GET  /api/report/download/<f>   보고서 다운로드
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
import time

from flask import Flask, jsonify, request, send_from_directory

import data as D
import qc as QC
import report as R
import variables as V

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

# 기존 NOSC 플랫폼과 동일한 LLM/보고서 스킬 경로 재사용
CLAUDE_BIN = "/home/mwcho/.local/bin/claude"
CLAUDE_MODEL = "haiku"   # 분석 속도↑ (분량은 프롬프트가 섹션 강제). 품질 더 원하면 'sonnet'
CLAUDE_EFFORT = "low"

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# LLM 호출 (claude CLI 헤드리스)
# ---------------------------------------------------------------------------
def run_claude(prompt, timeout=180):
    """claude -p 헤드리스 호출. 실패 시 None."""
    try:
        env = dict(os.environ)
        env.setdefault("HOME", "/home/mwcho")
        proc = subprocess.run(
            [CLAUDE_BIN, "-p", prompt, "--model", CLAUDE_MODEL, "--effort", CLAUDE_EFFORT,
             "--disallowed-tools", "WebSearch", "WebFetch", "--output-format", "text"],
            capture_output=True, text=True, timeout=timeout, env=env, cwd=BASE_DIR,
        )
        out = (proc.stdout or "").strip()
        if proc.returncode == 0 and out:
            return out
        app.logger.warning("claude rc=%s err=%s", proc.returncode, (proc.stderr or "")[:300])
        return None
    except Exception as e:
        app.logger.warning("claude call failed: %s", e)
        return None


# ---------------------------------------------------------------------------
# 정적 SPA
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return send_from_directory(STATIC_DIR, "index.html")


@app.route("/static/<path:fname>")
def static_files(fname):
    return send_from_directory(STATIC_DIR, fname)


@app.route("/api/health")
def health():
    return jsonify(ok=True, time=dt.datetime.now().isoformat())


# ---------------------------------------------------------------------------
# QC API
# ---------------------------------------------------------------------------
def _parse_params(args) -> dict:
    out = {}
    for key in QC.DEFAULT_PARAMS:
        if key in args and args.get(key) != "":
            out[key] = args.get(key)
    return out


@app.route("/api/variables")
def api_variables():
    """변수(관측 항목) 목록 + 변수별 수집 현황."""
    return jsonify(D.variable_status())


@app.route("/api/stations")
def api_stations():
    var = request.args.get("var", V.DEFAULT_VAR)
    return jsonify(D.list_stations(var))


@app.route("/api/qc")
def api_qc():
    var = request.args.get("var", V.DEFAULT_VAR)
    vmeta = V.get(var)
    obs = request.args.get("obs", "")
    st = D.load_station(var, obs)
    if st is None:
        return jsonify(error="관측소를 찾을 수 없습니다: %s/%s" % (var, obs)), 404
    params = _parse_params(request.args)
    result = QC.run_qc(st.get("series", []), params, base=vmeta["qc"])
    return jsonify({
        "var": var, "varName": vmeta["name"],
        "obsCode": st.get("obsCode"),
        "name": st.get("name"),
        "lat": st.get("lat"),
        "lon": st.get("lon"),
        "unit": vmeta["unit"],
        "qc": result,
    })


@app.route("/api/qc/summary")
def api_qc_summary():
    var = request.args.get("var", V.DEFAULT_VAR)
    vmeta = V.get(var)
    params = _parse_params(request.args)
    rows = []
    for meta in D.list_stations(var):
        st = D.load_station(var, meta["obsCode"])
        if st is None:
            continue
        r = QC.run_qc(st.get("series", []), params, base=vmeta["qc"])
        rows.append({
            "obsCode": meta["obsCode"],
            "name": meta["name"],
            "lat": meta.get("lat"),
            "lon": meta.get("lon"),
            "n": r["n"],
            "n_flagged": r["n_flagged"],
            "flags": r["flags"],
        })
    rows.sort(key=lambda x: x["n_flagged"], reverse=True)
    eff = QC.run_qc([], params, base=vmeta["qc"])["params"]
    return jsonify({"var": var, "varName": vmeta["name"], "unit": vmeta["unit"],
                    "params": eff, "stations": rows})


# ---------------------------------------------------------------------------
# QC 통계 산출 (LLM 입력 / 보고서 표 공용)
# ---------------------------------------------------------------------------
def _qc_context(var, obs, params):
    """단일 관측소(또는 __ALL__) QC 결과 → 통계 dict. 없으면 None."""
    vmeta = V.get(var)
    if obs == "__ALL__":
        return _qc_context_all(var, params)
    st = D.load_station(var, obs)
    if st is None:
        return None
    r = QC.run_qc(st.get("series", []), params, base=vmeta["qc"])
    return R.station_stats(st, r, vmeta)


def _qc_context_all(var, params):
    """전 관측소 통합 QC 통계."""
    vmeta = V.get(var)
    stations = []
    for meta in D.list_stations(var):
        st = D.load_station(var, meta["obsCode"])
        if st is None:
            continue
        r = QC.run_qc(st.get("series", []), params, base=vmeta["qc"])
        stations.append(R.station_stats(st, r, vmeta))
    return R.network_stats(stations, params, vmeta)


# ---------------------------------------------------------------------------
# 분석/보고서 API
# ---------------------------------------------------------------------------
@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    var = data.get("var", V.DEFAULT_VAR)
    obs = data.get("obs", "")
    question = (data.get("message") or "").strip()
    params = data.get("params") or {}
    ctx = _qc_context(var, obs, params)
    if ctx is None:
        return jsonify(ok=False, error="분석할 관측소 자료가 없습니다."), 404

    prompt = R.build_prompt(ctx, question)
    reply = run_claude(prompt)
    if not reply:
        reply = R.fallback_analysis(ctx, question)
        return jsonify(ok=True, analysis=reply, fallback=True, scope=ctx.get("scope"))
    return jsonify(ok=True, analysis=reply, fallback=False, scope=ctx.get("scope"))


@app.route("/api/report", methods=["POST"])
def api_report():
    data = request.get_json(force=True, silent=True) or {}
    var = data.get("var", V.DEFAULT_VAR)
    obs = data.get("obs", "")
    question = (data.get("message") or "").strip()
    analysis = (data.get("analysis") or "").strip()
    params = data.get("params") or {}
    ctx = _qc_context(var, obs, params)
    if ctx is None:
        return jsonify(ok=False, error="보고서로 만들 관측소 자료가 없습니다."), 404
    if not analysis:
        # 분석 내용이 없으면 즉석에서 생성 시도
        analysis = run_claude(R.build_prompt(ctx, question)) or R.fallback_analysis(ctx, question)

    try:
        fname = R.build_report(ctx, analysis, question, REPORTS_DIR)
    except Exception as e:
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify(ok=False, error="보고서 생성 실패: %s" % e), 500
    return jsonify(ok=True, filename=fname, url="/api/report/download/%s" % fname)


@app.route("/api/report/download/<path:fname>")
def report_download(fname):
    return send_from_directory(REPORTS_DIR, fname, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8002"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
