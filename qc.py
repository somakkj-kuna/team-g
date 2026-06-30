# -*- coding: utf-8 -*-
"""조위관측소 수온 시계열 품질관리(QC) — 이상치 검출 모듈.

이 모듈은 *교체 가능한 QC 엔진*이다. 지금은 간단한 이상치 제거(물리범위 +
이동중앙값 기반 MAD)만 구현하지만, 나중에 사용자가 제시할 QC 스킬(MD 명세)에
맞춰 `run_qc()` 의 내부 구현만 바꾸면 웹/백엔드는 그대로 동작하도록 인터페이스를
고정해 둔다.

인터페이스 계약
---------------
run_qc(series, params) -> dict
  입력  series : [[date:str, mean:float, min:float, max:float, count:int], ...]
        params: QC 파라미터(아래 DEFAULT_PARAMS 참고), 일부만 줘도 됨
  출력  {
          "values":  [{"date","value","flag","reason"}...],  # 전체 포인트별 결과
          "flags":   {flag_name: count, ...},                 # 플래그별 개수
          "n": 전체개수, "n_flagged": 이상치개수,
          "params": 실제 적용된 파라미터,
        }
  flag 값: "ok"(정상) | "range"(물리범위 초과) | "spike"(이동중앙값 대비 급변)
           | "missing"(결측/비수치)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# QC 기본 파라미터 — 한반도 주변해역 표층수온 기준
DEFAULT_PARAMS: Dict[str, Any] = {
    "range_min": -2.0,   # 물리적 하한(℃) — 해수 결빙점 부근
    "range_max": 35.0,   # 물리적 상한(℃)
    "window": 7,         # 이동중앙값 윈도(포인트 수, 홀수 권장)
    "mad_k": 3.5,        # MAD 임계 — |x-중앙값| > k*1.4826*MAD 이면 이상치
}


def _median(xs: List[float]) -> float:
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return float("nan")
    m = n // 2
    return s[m] if n % 2 else 0.5 * (s[m - 1] + s[m])


def run_qc(series: List[List[Any]], params: Optional[Dict[str, Any]] = None,
           base: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """시계열에 대한 이상치 QC 수행.

    base : 변수별 기본 파라미터(없으면 DEFAULT_PARAMS, 수온 기준). 누락 키를 채운다.
    params : 사용자가 UI 등에서 덮어쓴 파라미터.
    """
    p = dict(DEFAULT_PARAMS)
    if base:
        for k, v in base.items():
            if k in p and v is not None:
                p[k] = type(DEFAULT_PARAMS[k])(v)
    if params:
        for k, v in params.items():
            if k in p and v is not None:
                p[k] = type(DEFAULT_PARAMS[k])(v)

    rmin, rmax = p["range_min"], p["range_max"]
    win = max(3, int(p["window"]) | 1)   # 홀수 강제, 최소 3
    half = win // 2
    k = float(p["mad_k"])

    # 1) 포인트 추출 + 결측/범위 1차 플래그
    pts: List[Dict[str, Any]] = []
    for row in series:
        date = row[0]
        val = row[1] if len(row) > 1 else None
        if val is None or not isinstance(val, (int, float)):
            pts.append({"date": date, "value": None, "flag": "missing", "reason": "결측"})
            continue
        val = float(val)
        if val < rmin or val > rmax:
            pts.append({"date": date, "value": val, "flag": "range",
                        "reason": "물리범위(%.1f~%.1f℃) 벗어남" % (rmin, rmax)})
        else:
            pts.append({"date": date, "value": val, "flag": "ok", "reason": ""})

    # 2) 이동중앙값 기반 MAD 이상치(계절변동 제거 후 잔차 기준)
    #    range/missing 으로 이미 걸린 값은 제외하고 정상 후보에만 적용
    vals = [pt["value"] for pt in pts]
    n = len(pts)
    for i in range(n):
        if pts[i]["flag"] != "ok":
            continue
        lo, hi = max(0, i - half), min(n, i + half + 1)
        window_vals = [vals[j] for j in range(lo, hi)
                       if j != i and pts[j]["flag"] in ("ok", "range")
                       and vals[j] is not None]
        if len(window_vals) < 3:
            continue
        med = _median(window_vals)
        mad = _median([abs(v - med) for v in window_vals])
        # MAD=0(평탄 구간) 대비 보호
        scale = 1.4826 * mad if mad > 1e-9 else None
        resid = abs(vals[i] - med)
        if scale is not None and resid > k * scale:
            pts[i]["flag"] = "spike"
            pts[i]["reason"] = "이동중앙값 대비 급변(잔차 %.2f℃ > %.1f×MAD)" % (resid, k)

    # 3) 집계
    flags: Dict[str, int] = {}
    for pt in pts:
        flags[pt["flag"]] = flags.get(pt["flag"], 0) + 1
    n_flagged = sum(c for f, c in flags.items() if f != "ok")

    return {
        "values": pts,
        "flags": flags,
        "n": n,
        "n_flagged": n_flagged,
        "params": p,
    }
