# -*- coding: utf-8 -*-
"""조위관측소 다변수 자료 로더.

자료 루트: downloads/  (변수별 하위 디렉터리, 예: khoa_water_temp/)
각 관측소 파일 DT_XXXX.json 스키마:
  {"obsCode","name","lat","lon","unit","interval_min","count",
   "series": [[date, mean, min, max, count], ...]}
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional

import variables as V

DATA_ROOT = os.environ.get(
    "QC_DATA_ROOT",
    "/home/data1/geosr/mwcho/claude_agent/downloads",
)


def var_dir(var_key: str) -> str:
    return os.path.join(DATA_ROOT, V.get(var_key)["dir"])


def list_stations(var_key: str = V.DEFAULT_VAR) -> List[Dict[str, Any]]:
    """변수의 관측소 목록(메타). 자료 없으면 빈 리스트."""
    d = var_dir(var_key)
    if not os.path.isdir(d):
        return []
    idx = os.path.join(d, "stations.json")
    if os.path.exists(idx):
        with open(idx, encoding="utf-8") as f:
            return json.load(f)
    out = []
    for fn in sorted(os.listdir(d)):
        if fn.startswith("DT_") and fn.endswith(".json"):
            with open(os.path.join(d, fn), encoding="utf-8") as f:
                j = json.load(f)
            out.append({k: j.get(k) for k in ("obsCode", "name", "lat", "lon", "count")})
    return out


def load_station(var_key: str, obs_code: str) -> Optional[Dict[str, Any]]:
    """단일 관측소 전체 자료(시계열 포함). 없으면 None."""
    if not obs_code or not obs_code.replace("_", "").isalnum():
        return None
    path = os.path.join(var_dir(var_key), "%s.json" % obs_code)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def variable_status() -> List[Dict[str, Any]]:
    """변수별 수집 현황 — 관측소 수, 총 관측점, 자료 기간, 수집 여부."""
    out = []
    for v in V.VARIABLES:
        sts = list_stations(v["key"])
        n_st = len(sts)
        total_pts = 0
        dmin = dmax = None
        # 자료 기간/총량은 개별 파일을 읽어야 정확 → 관측소 수가 많지 않아 부담 적음
        for meta in sts:
            st = load_station(v["key"], meta["obsCode"])
            if not st:
                continue
            ser = st.get("series") or []
            total_pts += len(ser)
            if ser:
                d0, d1 = ser[0][0], ser[-1][0]
                dmin = d0 if dmin is None or d0 < dmin else dmin
                dmax = d1 if dmax is None or d1 > dmax else dmax
        out.append({
            "key": v["key"], "name": v["name"], "unit": v["unit"],
            "collected": n_st > 0,
            "n_stations": n_st,
            "total_points": total_pts,
            "start": dmin, "end": dmax,
            "qc": v["qc"],
        })
    return out
