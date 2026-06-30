# -*- coding: utf-8 -*-
"""해양관측 QC 웹앱 — Flask 백엔드 (sample_data 3기관 사전 QC 결과 기반).

엔드포인트
  GET  /                                  정적 SPA(index.html)
  GET  /api/health                        헬스체크
  GET  /api/sources                       수집 현황(카테고리·기관 소스 매트릭스)
  GET  /api/stations?agency=              기관 관측소 목록
  GET  /api/variables?agency=&station=    관측소 변수별 QC 현황
  GET  /api/qc?agency=&station=&var=&period=   변수 시계열 + flag_final
  POST /api/chat                          QC 결과 기반 LLM 분석
  POST /api/report                        분석 → 한글(HWPX) 보고서
  GET  /api/report/download/<f>           보고서 다운로드
"""
import csv
import datetime as dt
import io
import os
import subprocess

from flask import Flask, Response, jsonify, request, send_from_directory

import data as D
import report as R
import variables as V
import sources as S

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
REPORTS_DIR = os.path.join(BASE_DIR, "reports")
os.makedirs(REPORTS_DIR, exist_ok=True)

CLAUDE_BIN = "/home/mwcho/.local/bin/claude"
CLAUDE_MODEL = "haiku"
CLAUDE_EFFORT = "low"

PERIOD_LABEL = {"1m": "최근 1개월", "1y": "최근 1년", "all": "전체 기간"}

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# LLM 호출 (claude CLI 헤드리스)
# ---------------------------------------------------------------------------
def run_claude(prompt, timeout=180):
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
@app.after_request
def _no_cache_static(resp):
    """개발 중 정적 자산(HTML/JS/CSS) 캐시 방지 → 변경 즉시 반영."""
    if request.path == "/" or request.path.startswith("/static/"):
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
    return resp


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
# 수집 현황 / 관측소 / 변수
# ---------------------------------------------------------------------------
@app.route("/api/sources")
def api_sources():
    return jsonify(S.collection_status())


@app.route("/api/stations")
def api_stations():
    agency = request.args.get("agency", "")
    return jsonify([D.station_meta(agency, s) for s in D.list_stations(agency)])


@app.route("/api/variables")
def api_variables():
    agency = request.args.get("agency", "")
    station = request.args.get("station", "")
    if not station:
        sts = D.list_stations(agency)
        station = sts[0] if sts else ""
    return jsonify({
        "agency": agency, "agencyName": D.agency_name(agency),
        "station": station, "name": D.station_name(agency, station),
        "variables": D.variable_status(agency, station),
    })


# ---------------------------------------------------------------------------
# 시계열 + QC flag
# ---------------------------------------------------------------------------
def _filter_series_time(series, period):
    """데이터 최신 시점 기준 기간(1m/1y/all) 필터. (sample_data는 2025년 고정)"""
    if not period or period == "all" or not series:
        return series
    days = 30 if period == "1m" else 365 if period == "1y" else None
    if days is None:
        return series
    last = max((p["time"] or "")[:10] for p in series if p.get("time"))
    try:
        y, m, d = (int(x) for x in last.split("-"))
        cut = (dt.date(y, m, d) - dt.timedelta(days=days)).isoformat()
    except (ValueError, TypeError):
        return series
    return [p for p in series if (p["time"] or "")[:10] >= cut]


@app.route("/api/qc")
def api_qc():
    agency = request.args.get("agency", "")
    station = request.args.get("station", "")
    var = request.args.get("var", V.DEFAULT_VAR)
    period = request.args.get("period")
    vmeta = V.get(var)
    series = _filter_series_time(D.load_series(agency, station, var), period)
    if not series:
        return jsonify(error="자료를 찾을 수 없습니다: %s/%s/%s" % (agency, station, var)), 404
    cnt = {1: 0, 2: 0, 3: 0, 4: 0, 9: 0}
    for p in series:
        cnt[p["flag"]] = cnt.get(p["flag"], 0) + 1
    n = len(series)
    retained = cnt[1] + cnt[2]
    flagged = cnt[3] + cnt[9]
    return jsonify({
        "agency": agency, "agencyName": D.agency_name(agency),
        "station": station, "name": D.station_name(agency, station),
        "var": var, "varName": vmeta["name"], "unit": vmeta["unit"],
        "n": n, "good": cnt[1], "suspect": cnt[2], "bad": cnt[3],
        "interp": cnt[4], "missing": cnt[9],
        "retained": retained, "flagged": flagged,
        "flag_rate_pct": round(100.0 * flagged / n, 1) if n else 0.0,
        "series": series,   # [{time, value, flag(1/2/3/4/9)}]
    })


# ---------------------------------------------------------------------------
# 카탈로그 / QC 자료 다운로드(CSV)
# ---------------------------------------------------------------------------
@app.route("/api/catalog")
def api_catalog():
    """전 기관 관측소 목록(+해역·변수). 검색·다운로드 범위 선택용."""
    return jsonify(D.list_all_stations())


_EXPORT_COLS = ["time", "agency", "station_id", "lat", "lon",
                "var_id", "value", "depth_m", "flag_final"]


@app.route("/api/download")
def api_download():
    """QC 필터 CSV 다운로드.
    params: targets='agency:station,...'  vars='all'|'v1,v2'
            start/end='YYYY-MM-DD'(옵션)  maxflag=int(flag_final 이하만)."""
    targets = request.args.get("targets", "")
    vars_p = (request.args.get("vars", "") or "").strip()
    start = (request.args.get("start") or "").strip() or None
    end = (request.args.get("end") or "").strip() or None
    try:
        max_flag = int(request.args.get("maxflag", str(D.FLAG_MISSING)))
    except (ValueError, TypeError):
        max_flag = D.FLAG_MISSING
    try:
        min_flag = int(request.args.get("minflag", "1"))
    except (ValueError, TypeError):
        min_flag = 1
    var_ids = None if (not vars_p or vars_p == "all") else [v for v in vars_p.split(",") if v]

    pairs = []
    for t in targets.split(","):
        t = t.strip()
        if ":" in t:
            a, s = t.split(":", 1)
            if a and s:
                pairs.append((a.strip(), s.strip()))
    # 경로/와일드카드 주입 차단 — 카탈로그에 실재하는 관측소만 허용
    allowed = D.valid_targets()
    pairs = [p for p in pairs if p in allowed]
    if not pairs:
        return jsonify(error="유효한 관측소가 없습니다."), 400

    buf = io.StringIO()
    buf.write("﻿")          # Excel 한글 BOM
    w = csv.writer(buf)
    w.writerow(_EXPORT_COLS)
    n = 0
    for a, s in pairs:
        for r in D.export_rows(a, s, var_ids, start, end, max_flag, min_flag):
            w.writerow([r.get(c, "") for c in _EXPORT_COLS])
            n += 1

    fname = "qc_export_%s.csv" % dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    return Response(
        buf.getvalue(), mimetype="text/csv",
        headers={
            "Content-Disposition": "attachment; filename=%s" % fname,
            "X-Row-Count": str(n),
            "Cache-Control": "no-store",
        },
    )


# ---------------------------------------------------------------------------
# LLM 분석 / 보고서 — sample_data flag → report.py 호환 ctx 변환
# ---------------------------------------------------------------------------
# flag_final → report.py 플래그(ok/range/spike/missing)
_FMAP = {1: "ok", 2: "ok", 4: "ok", 3: "range", 9: "missing"}


def _sample_context(agency, station, var, period):
    """sample_data 시계열 → report.station_stats 호환 통계 ctx. 없으면 None."""
    series = _filter_series_time(D.load_series(agency, station, var), period)
    if not series:
        return None
    vmeta = V.get(var)
    values, flags, n_flag = [], {}, 0
    for p in series:
        f = _FMAP.get(p["flag"], "missing")
        values.append({"date": (p["time"] or "")[:10], "value": p["value"],
                       "flag": f, "reason": ""})
        flags[f] = flags.get(f, 0) + 1
        if f != "ok":
            n_flag += 1
    qc = {"values": values, "flags": flags, "n": len(values), "n_flagged": n_flag,
          "params": {"range_min": 0.0, "range_max": 0.0, "window": 0, "mad_k": 0.0}}
    meta = D.station_meta(agency, station)
    st = {"obsCode": station, "name": meta["name"], "lat": meta["lat"], "lon": meta["lon"]}
    ctx = R.station_stats(st, qc, vmeta)
    ctx["period"] = period or "all"
    ctx["period_label"] = PERIOD_LABEL.get(period or "all", "전체 기간")
    ctx["agency"] = agency
    ctx["agency_name"] = D.agency_name(agency)
    return ctx


@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(force=True, silent=True) or {}
    agency = data.get("agency", "")
    station = data.get("station", "")
    var = data.get("var", V.DEFAULT_VAR)
    question = (data.get("message") or "").strip()
    period = data.get("period")
    ctx = _sample_context(agency, station, var, period)
    if ctx is None:
        return jsonify(ok=False, error="분석할 자료가 없습니다."), 404
    prompt = R.build_prompt(ctx, question)
    reply = run_claude(prompt)
    if not reply:
        return jsonify(ok=True, analysis=R.fallback_analysis(ctx, question), fallback=True)
    return jsonify(ok=True, analysis=reply, fallback=False)


@app.route("/api/report", methods=["POST"])
def api_report():
    data = request.get_json(force=True, silent=True) or {}
    agency = data.get("agency", "")
    station = data.get("station", "")
    question = (data.get("message") or "").strip()
    period = data.get("period")

    # 변수 정규화: vars(목록) 우선, 없으면 단일 var. 다중이면 하나의 통합 보고서.
    vars_in = data.get("vars")
    if isinstance(vars_in, str):
        varlist = [v.strip() for v in vars_in.split(",") if v.strip()]
    elif isinstance(vars_in, list):
        varlist = [str(v).strip() for v in vars_in if str(v).strip()]
    else:
        varlist = [data.get("var", V.DEFAULT_VAR)]
    # 재사용 분석: analyses{varkey:text}(다중) 또는 analysis(단일 호환)
    analyses_in = data.get("analyses") if isinstance(data.get("analyses"), dict) else {}
    analysis_single = (data.get("analysis") or "").strip()

    blocks = []
    for v in varlist:
        ctx = _sample_context(agency, station, v, period)
        if ctx is None:
            continue
        a = (analyses_in.get(v) or "").strip()
        if not a and len(varlist) == 1:
            a = analysis_single
        if not a:
            a = run_claude(R.build_prompt(ctx, question)) or R.fallback_analysis(ctx, question)
        blocks.append((ctx, a))
    if not blocks:
        return jsonify(ok=False, error="보고서로 만들 자료가 없습니다."), 404

    try:
        if len(blocks) == 1:
            fname = R.build_report(blocks[0][0], blocks[0][1], question, REPORTS_DIR)
        else:
            fname = R.build_report_multi(blocks, question, REPORTS_DIR)
    except Exception as e:
        import traceback
        app.logger.error(traceback.format_exc())
        return jsonify(ok=False, error="보고서 생성 실패: %s" % e), 500
    return jsonify(ok=True, filename=fname, url="/api/report/download/%s" % fname, n_vars=len(blocks))


@app.route("/api/report/download/<path:fname>")
def report_download(fname):
    return send_from_directory(REPORTS_DIR, fname, as_attachment=True)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8002"))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
