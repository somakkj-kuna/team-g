# -*- coding: utf-8 -*-
"""QC 통계 산출 · LLM 프롬프트 · 한글(HWPX) 보고서 생성.

- station_stats / network_stats : QC 결과 → 분석·보고서 공용 통계 dict
- build_prompt / fallback_analysis : 데이터 기반 LLM 분석 입출력
- build_report : 통계 + 분석 텍스트 + QC 차트(PNG) → HWPX 파일

HWPX 생성은 기존 NOSC 플랫폼과 동일한 geosr-hwpx 스킬(YeoboBuilder)을 재사용한다.
matplotlib 한글 폰트가 환경에 없으므로 차트 축/제목은 영문으로 표기한다.
"""
from __future__ import annotations

import os
import re
import sys
import time
from typing import Any, Dict, List, Optional

HWPX_SCRIPTS = "/home/data1/geosr/mwcho/claude_agent/geosr-hwpx/geosr-hwpx/scripts"

FLAG_KO = {"ok": "정상", "range": "물리범위 초과", "spike": "급변(이상치)", "missing": "결측"}


# ---------------------------------------------------------------------------
# 통계 산출
# ---------------------------------------------------------------------------
def _round(x, n=2):
    try:
        return round(float(x), n)
    except (TypeError, ValueError):
        return None


def station_stats(st: Dict[str, Any], qc: Dict[str, Any],
                  vmeta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """단일 관측소 QC 결과 → 통계 dict."""
    vmeta = vmeta or {"key": "water_temp", "name": "수온", "unit": "℃"}
    vals = qc["values"]
    ok = [p for p in vals if p["flag"] == "ok" and p["value"] is not None]
    flagged = [p for p in vals if p["flag"] not in ("ok",)]
    okv = [p["value"] for p in ok]
    okd = [p["date"] for p in ok]

    trend = None
    if len(okv) >= 2:
        # 단순 최소제곱 기울기(℃/관측간격) → ℃/일 환산은 표본 간격 가정 없이 생략
        n = len(okv)
        xs = list(range(n))
        mx = sum(xs) / n
        my = sum(okv) / n
        denom = sum((x - mx) ** 2 for x in xs)
        if denom:
            slope = sum((xs[i] - mx) * (okv[i] - my) for i in range(n)) / denom
            trend = _round(slope, 4)

    stat = {
        "scope": "station",
        "var": vmeta["key"], "var_name": vmeta["name"],
        "obsCode": st.get("obsCode"),
        "name": st.get("name"),
        "lat": st.get("lat"),
        "lon": st.get("lon"),
        "unit": vmeta["unit"],
        "n": qc["n"],
        "n_flagged": qc["n_flagged"],
        "n_ok": len(ok),
        "flags": qc["flags"],
        "flag_rate_pct": _round(100.0 * qc["n_flagged"] / qc["n"], 1) if qc["n"] else 0.0,
        "params": qc["params"],
        "start": okd[0] if okd else None,
        "end": okd[-1] if okd else None,
        "mean": _round(sum(okv) / len(okv)) if okv else None,
        "tmin": _round(min(okv)) if okv else None,
        "tmax": _round(max(okv)) if okv else None,
        "first": {"date": okd[0], "value": _round(okv[0])} if okv else None,
        "last": {"date": okd[-1], "value": _round(okv[-1])} if okv else None,
        "trend_per_step": trend,
        # 이상치 상세(최대 30개) — 보고서 표/프롬프트 공용
        "outliers": [{"date": p["date"], "value": p["value"],
                      "flag": p["flag"], "flag_ko": FLAG_KO.get(p["flag"], p["flag"]),
                      "reason": p["reason"]} for p in flagged][:30],
        "series_ok": list(zip(okd, okv)),   # 차트용(정상값)
        "series_all": [(p["date"], p["value"], p["flag"]) for p in vals],
    }
    return stat


def network_stats(stations: List[Dict[str, Any]], params: Dict[str, Any],
                  vmeta: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """전 관측소 통합 통계."""
    vmeta = vmeta or {"key": "water_temp", "name": "수온", "unit": "℃"}
    valid = [s for s in stations if s.get("mean") is not None]
    total_n = sum(s["n"] for s in stations)
    total_flag = sum(s["n_flagged"] for s in stations)
    by_flag: Dict[str, int] = {}
    for s in stations:
        for f, c in s["flags"].items():
            if f != "ok":
                by_flag[f] = by_flag.get(f, 0) + c
    worst = sorted(stations, key=lambda s: s["n_flagged"], reverse=True)[:10]
    warmest = max(valid, key=lambda s: s["mean"], default=None)
    coolest = min(valid, key=lambda s: s["mean"], default=None)
    return {
        "scope": "network",
        "var": vmeta["key"], "var_name": vmeta["name"], "unit": vmeta["unit"],
        "name": "전국 조위관측소",
        "n_stations": len(stations),
        "params": params or (stations[0]["params"] if stations else {}),
        "total_n": total_n,
        "total_flagged": total_flag,
        "flag_rate_pct": _round(100.0 * total_flag / total_n, 1) if total_n else 0.0,
        "by_flag": by_flag,
        "network_mean": _round(sum(s["mean"] for s in valid) / len(valid)) if valid else None,
        "warmest": {"name": warmest["name"], "mean": warmest["mean"]} if warmest else None,
        "coolest": {"name": coolest["name"], "mean": coolest["mean"]} if coolest else None,
        "worst": [{"name": s["name"], "obsCode": s["obsCode"], "n": s["n"],
                   "n_flagged": s["n_flagged"], "flags": s["flags"]} for s in worst],
        "stations": [{"name": s["name"], "obsCode": s["obsCode"], "mean": s["mean"],
                      "tmin": s["tmin"], "tmax": s["tmax"],
                      "n_flagged": s["n_flagged"]} for s in stations],
    }


# ---------------------------------------------------------------------------
# LLM 프롬프트 / 폴백
# ---------------------------------------------------------------------------
def _ctx_json(ctx: Dict[str, Any]) -> str:
    import json
    # 차트용 원시 시계열은 프롬프트에서 제외(비대화 방지)
    slim = {k: v for k, v in ctx.items() if k not in ("series_ok", "series_all")}
    return json.dumps(slim, ensure_ascii=False)


def build_prompt(ctx: Dict[str, Any], question: str) -> str:
    p = ctx["params"]
    vn = ctx.get("var_name", "수온")
    u = ctx.get("unit", "℃")
    qc_desc = ("QC 방법: ①물리범위 검사(%.1f~%.1f%s 벗어나면 'range') "
               "②이동중앙값(윈도 %d) 기반 MAD 급변 검출(|잔차|>%.1f×1.4826×MAD 이면 'spike') "
               "③비수치는 'missing'." % (p["range_min"], p["range_max"], u, p["window"], p["mad_k"]))
    if ctx["scope"] == "network":
        focus = ("전국 조위관측소 %d개소의 %s 자료에 대한 품질관리(QC) 결과 통합 분석"
                 % (ctx["n_stations"], vn))
    else:
        focus = ("%s 조위관측소(%s) %s 자료의 품질관리(QC) 결과 분석"
                 % (ctx.get("name"), ctx.get("obsCode"), vn))

    sections_guide = (
        "1) 분석 개요 — 분석 대상·자료원(국립해양조사원 조위관측소 실측 %s, data.go.kr)·QC 방법·분석 목적\n"
        "2) 데이터 품질 진단 — 전체 관측수, 정상/이상치 개수와 비율, 플래그(급변/범위초과/결측)별 분포 해석\n"
        "3) 이상치 상세 검토 — 검출된 이상치의 시점·값·사유를 짚고, 계측 오류 가능성/실제 현상 가능성을 구분해 논의\n"
        "4) %s 시계열 특성 — 기간 평균·범위, 시작/종료 값과 변화, 추세, 계절적 맥락\n"
        "5) 권고 사항 — 자료 활용 시 주의점, 추가 QC(이웃 관측소 비교·기후값 검사 등) 제안\n"
        "6) 결론 — 핵심 요약"
    ) % (vn, vn)
    return (
        "당신은 해양 관측자료 품질관리(QC) 전문가입니다. 아래 QC 결과(JSON)를 근거로 "
        "%s를 수행하세요.\n\n"
        "[분석 범위] %s\n%s\n\n"
        "[QC 결과 데이터]\n%s\n\n"
        "[사용자 질문]\n%s\n\n"
        "작성 규칙:\n"
        "- 반드시 아래 6개 섹션 구조를 지키고, 각 섹션은 '# 제목' 한 줄로 시작하세요.\n"
        "- 각 항목은 '- '로 시작하는 글머리표로 쓰고, 데이터의 구체적 수치를 인용하세요.\n"
        "- 데이터에 없는 사실을 지어내지 말고, 불확실하면 가능성으로 서술하세요.\n"
        "- 한국어로, 보고서에 바로 넣을 수 있는 분량(섹션당 2~5개 항목)으로 작성하세요.\n\n"
        "[섹션 구조]\n%s\n"
        % (focus, ctx.get("period_label", "전체 기간"), qc_desc, _ctx_json(ctx),
           question or "(특정 질문 없음 — 전반적 QC 품질 진단 수행)", sections_guide)
    )


def fallback_analysis(ctx: Dict[str, Any], question: str) -> str:
    """LLM 호출 실패 시 통계 기반 임시 분석."""
    vn = ctx.get("var_name", "수온")
    u = ctx.get("unit", "℃")
    if ctx["scope"] == "network":
        return (
            "# 분석 개요\n"
            "- 대상: 전국 조위관측소 %d개소 %s QC 결과\n"
            "- 자료원: 국립해양조사원 조위관측소 실측 %s (data.go.kr)\n"
            "# 데이터 품질 진단\n"
            "- 전체 관측 %d점 중 이상치 %d점 (%.1f%%)\n"
            "- 플래그 분포: %s\n"
            "# 참고\n"
            "- (LLM 엔진 응답 실패로 통계 기반 임시 요약을 표시합니다.)\n"
            % (ctx["n_stations"], vn, vn, ctx["total_n"], ctx["total_flagged"],
               ctx["flag_rate_pct"], ctx["by_flag"])
        )
    return (
        "# 분석 개요\n"
        "- 대상: %s 조위관측소(%s) %s QC 결과\n"
        "- 분석 기간: %s ~ %s\n"
        "# 데이터 품질 진단\n"
        "- 전체 %d점 중 정상 %d점, 이상치 %d점 (%.1f%%)\n"
        "- 플래그 분포: %s\n"
        "# %s 시계열 특성\n"
        "- 기간 평균 %s%s (범위 %s~%s%s)\n"
        "# 참고\n"
        "- (LLM 엔진 응답 실패로 통계 기반 임시 요약을 표시합니다.)\n"
        % (ctx.get("name"), ctx.get("obsCode"), vn, ctx.get("start"), ctx.get("end"),
           ctx["n"], ctx["n_ok"], ctx["n_flagged"], ctx["flag_rate_pct"], ctx["flags"],
           vn, ctx.get("mean"), u, ctx.get("tmin"), ctx.get("tmax"), u)
    )


def parse_structured(text: str):
    """'# 섹션' / '- 항목' / '  - 하위' → (heading, [items]) 리스트."""
    sections = []
    cur = None
    for raw in text.splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        if line.lstrip().startswith("#"):
            heading = line.lstrip("#").strip()
            cur = {"heading": heading or "내용", "items": []}
            sections.append(cur)
        else:
            is_sub = bool(re.match(r"^\s{2,}[-·*]", raw)) or raw.startswith("  ")
            item = line.strip().lstrip("-•·*").strip()
            if not item:
                continue
            if cur is None:
                cur = {"heading": "분석 내용", "items": []}
                sections.append(cur)
            cur["items"].append({"text": item, "sub": is_sub})
    if not sections:
        sections = [{"heading": "분석 내용", "items": [{"text": text.strip(), "sub": False}]}]
    return sections


# ---------------------------------------------------------------------------
# QC 차트 (matplotlib, 영문 라벨)
# ---------------------------------------------------------------------------
def _qc_chart_png(ctx: Dict[str, Any], outdir: str, key: str) -> Optional[str]:
    """단일 관측소 QC 시계열(정상 라인 + 이상치 마커) PNG. 실패 시 None."""
    if ctx["scope"] != "station" or not ctx.get("series_all"):
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import matplotlib.dates as mdates
        from datetime import datetime

        sa = ctx["series_all"]
        dates = [datetime.strptime(d, "%Y-%m-%d") for d, v, f in sa if v is not None]
        vals = [v for d, v, f in sa if v is not None]
        ok_d = [datetime.strptime(d, "%Y-%m-%d") for d, v, f in sa if v is not None and f == "ok"]
        ok_v = [v for d, v, f in sa if v is not None and f == "ok"]
        sp = [(datetime.strptime(d, "%Y-%m-%d"), v) for d, v, f in sa if v is not None and f == "spike"]
        rg = [(datetime.strptime(d, "%Y-%m-%d"), v) for d, v, f in sa if v is not None and f == "range"]

        fig, ax = plt.subplots(figsize=(9, 3.6), dpi=130)
        ax.plot(dates, vals, color="#9aa7b4", lw=0.8, alpha=0.6, label="Raw", zorder=1)
        ax.plot(ok_d, ok_v, color="#2f6fd0", lw=1.6, marker="o", ms=2.5, label="QC passed", zorder=2)
        if sp:
            ax.scatter([d for d, v in sp], [v for d, v in sp], color="#e0403f",
                       s=42, marker="x", lw=1.6, label="Spike", zorder=3)
        if rg:
            ax.scatter([d for d, v in rg], [v for d, v in rg], color="#e0a020",
                       s=42, marker="D", label="Out of range", zorder=3)
        unit_ascii = {"℃": "degC", "psu": "psu", "cm": "cm", "hPa": "hPa", "m/s": "m/s"}.get(
            ctx.get("unit", ""), ctx.get("unit", ""))
        ax.set_ylabel("Value (%s)" % unit_ascii, fontsize=11)
        ax.set_title("%s  QC time series" % ctx.get("obsCode"),
                     fontsize=11, fontweight="bold")
        ax.grid(True, alpha=0.25)
        ax.legend(fontsize=8, loc="best")
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
        fig.autofmt_xdate(rotation=30)
        fig.tight_layout()
        path = os.path.join(outdir, "qc_chart_%s.png" % key)
        fig.savefig(path)
        plt.close(fig)
        return path
    except Exception:
        return None


def _network_chart_png(ctx: Dict[str, Any], outdir: str, key: str) -> Optional[str]:
    """전 관측소 이상치 개수 막대그래프(상위 15개). 실패 시 None."""
    if ctx["scope"] != "network":
        return None
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        rows = sorted(ctx["stations"], key=lambda s: s["n_flagged"], reverse=True)[:15]
        rows = [r for r in rows if r["n_flagged"] > 0]
        if not rows:
            return None
        labels = [r["obsCode"] for r in rows]
        vals = [r["n_flagged"] for r in rows]
        fig, ax = plt.subplots(figsize=(9, 3.6), dpi=130)
        ax.bar(range(len(vals)), vals, color="#e0403f")
        ax.set_xticks(range(len(vals)))
        ax.set_xticklabels(labels, rotation=45, ha="right", fontsize=8)
        ax.set_ylabel("Flagged points", fontsize=11)
        ax.set_title("Flagged points by station (top %d)" % len(rows),
                     fontsize=11, fontweight="bold")
        ax.grid(True, axis="y", alpha=0.25)
        fig.tight_layout()
        path = os.path.join(outdir, "qc_network_%s.png" % key)
        fig.savefig(path)
        plt.close(fig)
        return path
    except Exception:
        return None


# ---------------------------------------------------------------------------
# HWPX 보고서 생성
# ---------------------------------------------------------------------------
def build_report(ctx: Dict[str, Any], analysis: str, question: str, reports_dir: str) -> str:
    """통계 + 분석 텍스트 + 차트 → HWPX 파일 생성, 파일명 반환."""
    if HWPX_SCRIPTS not in sys.path:
        sys.path.insert(0, HWPX_SCRIPTS)
    from yebobu_builder import YeoboBuilder

    vn = ctx.get("var_name", "수온")
    u = ctx.get("unit", "℃")
    plab = ctx.get("period_label", "전체 기간")
    ts = time.strftime("%Y%m%d_%H%M%S")
    nm = re.sub(r"[^0-9A-Za-z가-힣]", "", (ctx.get("name") or "관측소")) or "관측소"
    fname = "%s_%s_%sQC_보고서_%s.hwpx" % (nm, plab.replace(" ", ""), vn, ts)
    out_path = os.path.join(reports_dir, fname)
    figdir = os.path.join(reports_dir, "figs")
    os.makedirs(figdir, exist_ok=True)

    b = YeoboBuilder()
    if ctx["scope"] == "network":
        title = "전국 조위관측소 %s 품질관리(QC) 분석 보고서" % vn
    else:
        title = "%s 조위관측소 %s 품질관리(QC) 분석 보고서" % (ctx.get("name"), vn)
    b.title(title)

    p = ctx["params"]
    b.section("분석 개요")
    b.item("분석 범위: %s (작성일 %s 기준)" % (plab, time.strftime("%Y-%m-%d")))
    if ctx["scope"] == "network":
        b.item("분석 대상: 전국 조위관측소 %d개소 %s 자료" % (ctx["n_stations"], vn))
    else:
        b.item("분석 대상: %s 조위관측소(%s) %s 자료" % (ctx.get("name"), ctx.get("obsCode"), vn))
        b.item("분석 기간: %s ~ %s" % (ctx.get("start"), ctx.get("end")))
    b.item("자료 출처: 국립해양조사원 조위관측소 실측 %s (data.go.kr)" % vn)
    b.item("QC 방법: 물리범위 검사(%.1f~%.1f%s) + 이동중앙값(윈도 %d) 기반 MAD 급변 검출(k=%.1f)"
           % (p["range_min"], p["range_max"], u, p["window"], p["mad_k"]))
    if question:
        b.item("분석 요청: %s" % question)
    b.item("작성일: %s" % time.strftime("%Y-%m-%d"))

    # QC 통계 표
    if ctx["scope"] == "network":
        b.section("QC 통계 요약")
        b.data_table(["항목", "값"], [
            ["관측소 수", "%d개" % ctx["n_stations"]],
            ["전체 관측수", "%d점" % ctx["total_n"]],
            ["이상치 합계", "%d점 (%.1f%%)" % (ctx["total_flagged"], ctx["flag_rate_pct"])],
            ["플래그 분포", ", ".join("%s %d" % (FLAG_KO.get(k, k), v) for k, v in ctx["by_flag"].items()) or "없음"],
            ["광역 평균 %s" % vn, "%s %s" % (ctx["network_mean"], u)],
            ["최댓값 관측소", "%s · %s %s" % (ctx["warmest"]["name"], ctx["warmest"]["mean"], u) if ctx["warmest"] else "-"],
            ["최솟값 관측소", "%s · %s %s" % (ctx["coolest"]["name"], ctx["coolest"]["mean"], u) if ctx["coolest"] else "-"],
        ], col_widths=[16000, 26000], caption="표 1. 전국 QC 통계 요약")

        worst_rows = [[w["name"] or w["obsCode"], "%d점" % w["n"], "%d점" % w["n_flagged"]]
                      for w in ctx["worst"] if w["n_flagged"] > 0]
        if worst_rows:
            b.section("이상치 다수 관측소")
            b.data_table(["관측소", "전체", "이상치"], worst_rows,
                         col_widths=[18000, 12000, 12000], caption="표 2. 이상치 상위 관측소")
    else:
        b.section("QC 통계 요약")
        b.data_table(["항목", "값"], [
            ["전체 관측수", "%d점" % ctx["n"]],
            ["정상", "%d점" % ctx["n_ok"]],
            ["이상치", "%d점 (%.1f%%)" % (ctx["n_flagged"], ctx["flag_rate_pct"])],
            ["플래그 분포", ", ".join("%s %d" % (FLAG_KO.get(k, k), v) for k, v in ctx["flags"].items())],
            ["기간 평균 %s" % vn, "%s %s" % (ctx.get("mean"), u)],
            ["%s 범위" % vn, "%s ~ %s %s" % (ctx.get("tmin"), ctx.get("tmax"), u)],
            ["시작/종료 값", "%s%s → %s%s" % (ctx["first"]["value"] if ctx["first"] else "-", u,
                                          ctx["last"]["value"] if ctx["last"] else "-", u)],
        ], col_widths=[16000, 26000], caption="표 1. QC 통계 요약")

        out_rows = [[o["date"], "%s %s" % (o["value"], u) if o["value"] is not None else "-",
                     o["flag_ko"]] for o in ctx["outliers"]]
        if out_rows:
            b.section("검출된 이상치 목록")
            b.data_table(["일자", vn, "유형"], out_rows,
                         col_widths=[14000, 14000, 14000], caption="표 2. 이상치 상세 (최대 30건)")

    # LLM 분석 본문
    for sec in parse_structured(analysis):
        b.section(sec["heading"])
        for it in sec["items"]:
            (b.sub if it["sub"] else b.item)(it["text"])

    # 차트
    chart = (_network_chart_png if ctx["scope"] == "network" else _qc_chart_png)(ctx, figdir, ts)
    if chart and os.path.exists(chart):
        b.section("시각 자료")
        cap = ("그림 1. 관측소별 이상치 개수" if ctx["scope"] == "network"
               else "그림 1. QC 시계열 (정상값·이상치 표시)")
        b.figure(chart, caption=cap, width_hwpunit=45000)

    b.build(out_path, title=title, creator="(주)지오시스템리서치 예보사업부")
    return fname


def build_report_multi(blocks: List[Any], question: str, reports_dir: str) -> str:
    """동일 관측소·기간의 여러 변수 (ctx, analysis)를 하나의 HWPX로 통합. 파일명 반환.

    blocks: [(ctx, analysis_text), ...]  (각 ctx는 station scope, var만 다름)
    구조: 분석 개요 → 변수별 QC 통계 요약(표) → 변수별 상세(통계표·이상치표·LLM분석·차트)."""
    if not blocks:
        raise ValueError("blocks is empty")
    if len(blocks) == 1:
        return build_report(blocks[0][0], blocks[0][1], question, reports_dir)
    if HWPX_SCRIPTS not in sys.path:
        sys.path.insert(0, HWPX_SCRIPTS)
    from yebobu_builder import YeoboBuilder

    first = blocks[0][0]
    name = first.get("name") or "관측소"
    obs = first.get("obsCode")
    plab = first.get("period_label", "전체 기간")
    today = time.strftime("%Y-%m-%d")
    ts = time.strftime("%Y%m%d_%H%M%S")
    nm = re.sub(r"[^0-9A-Za-z가-힣]", "", name) or "관측소"
    var_names = [c.get("var_name") or c.get("var") for c, _ in blocks]
    fname = "%s_%s_QC보고서_%d변수_%s.hwpx" % (nm, plab.replace(" ", ""), len(blocks), ts)
    out_path = os.path.join(reports_dir, fname)
    figdir = os.path.join(reports_dir, "figs")
    os.makedirs(figdir, exist_ok=True)

    b = YeoboBuilder()
    title = "%s 관측자료 품질관리(QC) 분석 보고서" % name
    b.title(title)

    # 분석 개요
    b.section("분석 개요")
    b.item("분석 범위: %s (작성일 %s 기준)" % (plab, today))
    b.item("분석 대상: %s 관측소(%s)" % (name, obs))
    b.item("분석 변수: %s (%d종)" % (", ".join(var_names), len(blocks)))
    b.item("자료 출처: 국립해양조사원·기상청·국립수산과학원 관측소 실측자료")
    if question:
        b.item("분석 요청: %s" % question)
    b.item("작성일: %s" % today)

    # 변수별 QC 통계 요약(통합 표)
    b.section("변수별 QC 통계 요약")
    sum_rows = []
    for ctx, _ in blocks:
        u = ctx.get("unit", "")
        has = ctx.get("mean") is not None
        sum_rows.append([
            ctx.get("var_name") or ctx.get("var"),
            "%d" % ctx["n"],
            "%d" % ctx["n_ok"],
            "%d (%.1f%%)" % (ctx["n_flagged"], ctx["flag_rate_pct"]),
            ("%s%s" % (ctx.get("mean"), u)) if has else "-",
            ("%s ~ %s%s" % (ctx.get("tmin"), ctx.get("tmax"), u)) if has else "-",
        ])
    b.data_table(["변수", "관측수", "정상", "이상치", "평균", "범위"], sum_rows,
                 col_widths=[9000, 6000, 6000, 8000, 6000, 7000],
                 caption="표 1. 변수별 QC 통계 요약")

    # 변수별 상세
    for idx, (ctx, analysis) in enumerate(blocks, 1):
        vn = ctx.get("var_name") or ctx.get("var")
        u = ctx.get("unit", "")
        b.section("%d. %s 품질관리 결과" % (idx, vn))
        b.data_table(["항목", "값"], [
            ["전체 관측수", "%d점" % ctx["n"]],
            ["정상", "%d점" % ctx["n_ok"]],
            ["이상치", "%d점 (%.1f%%)" % (ctx["n_flagged"], ctx["flag_rate_pct"])],
            ["플래그 분포", ", ".join("%s %d" % (FLAG_KO.get(k, k), v) for k, v in ctx["flags"].items())],
            ["기간 평균", "%s %s" % (ctx.get("mean"), u)],
            ["범위", "%s ~ %s %s" % (ctx.get("tmin"), ctx.get("tmax"), u)],
            ["분석 기간", "%s ~ %s" % (ctx.get("start"), ctx.get("end"))],
        ], col_widths=[16000, 26000], caption="표 %d. %s QC 통계" % (idx + 1, vn))

        out_rows = [[o["date"], "%s %s" % (o["value"], u) if o["value"] is not None else "-",
                     o["flag_ko"]] for o in ctx["outliers"]]
        if out_rows:
            b.data_table(["일자", vn, "유형"], out_rows,
                         col_widths=[14000, 14000, 14000],
                         caption="표 %d-1. %s 이상치 (최대 30건)" % (idx + 1, vn))

        # LLM 분석 본문 — 변수 섹션 하위로 한 단계 들여쓰기(섹션 제목→ㅇ, 항목→-)
        for sec in parse_structured(analysis):
            b.item(sec["heading"])
            for it in sec["items"]:
                b.sub(it["text"])

        chart = _qc_chart_png(ctx, figdir, "%s_%d" % (ts, idx))
        if chart and os.path.exists(chart):
            b.figure(chart, caption="그림 %d. %s QC 시계열 (정상값·이상치 표시)" % (idx, vn),
                     width_hwpunit=45000)

    b.build(out_path, title=title, creator="(주)지오시스템리서치 예보사업부")
    return fname
