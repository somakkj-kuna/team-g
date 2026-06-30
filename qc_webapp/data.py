# -*- coding: utf-8 -*-
"""sample_data 기반 데이터 로더 — 3기관(KHOA/KMA/NIFS) 관측소 사전 QC 결과.

데이터 출처: qc_webapp/sample_data/sample_data/  (server131 미러)
  QC flag CSV: home/collect/QC/result/flag/{agency}/{station}/{yyyy}/{agency}_{station}_{yyyy}_qc_flag.csv
    컬럼: time,agency,station_id,lat,lon,var_id,value,depth_m,flag_final,
          flag_aqc1,reason_aqc1,flag_aqc2,reason_aqc2,flag_mqc,reason_mqc
  flag_final: 1=good 2=suspect 3=bad 4=interpolated 9=missing
이미 QC된 결과를 그대로 표출한다(보존=good/suspect, 제거=bad/missing).
"""
from __future__ import annotations

import csv
import glob
import json
import os
from typing import Any, Dict, List, Optional

import variables as V

SAMPLE_ROOT = os.environ.get(
    "QC_SAMPLE_ROOT",
    "/home/data1/geosr/mwcho/claude_agent/qc_webapp/sample_data/sample_data",
)
QC_ROOT = os.path.join(SAMPLE_ROOT, "home", "collect", "QC")
FLAG_ROOT = os.path.join(QC_ROOT, "result", "flag")

AGENCY_META = {
    "khoa": {"name": "국립해양조사원", "dataset": "tidal"},
    "kma":  {"name": "기상청",        "dataset": "buoy"},
    "nifs": {"name": "국립수산과학원", "dataset": "buoy"},
}

# flag_final 코드
FLAG_GOOD, FLAG_SUSPECT, FLAG_BAD, FLAG_INTERP, FLAG_MISSING = 1, 2, 3, 4, 9
RETAINED = {FLAG_GOOD, FLAG_SUSPECT}        # 보존(분석 사용 가능)
REMOVED = {FLAG_BAD, FLAG_MISSING}          # 제거(QC 탈락)

_rows_cache: Dict[tuple, Any] = {}          # (agency,station) -> (mtime, rows)
_name_cache: Dict[tuple, str] = {}

# 사전계산 카탈로그(대규모 관측소에서 전체 행 적재 없이 메타·변수 제공)
CATALOG_JSON = os.path.join(QC_ROOT, "catalog.json")
_catalog_cache = None                       # (list, idx) 또는 None(미로딩)


def _catalog():
    """catalog.json(있으면) 로드 → (목록, {(agency,station):항목}). 없으면 ([], {})."""
    global _catalog_cache
    if _catalog_cache is None:
        lst = []
        if os.path.exists(CATALOG_JSON):
            try:
                with open(CATALOG_JSON, encoding="utf-8") as f:
                    lst = json.load(f)
            except (ValueError, OSError):
                lst = []
        idx = {(s.get("agency"), s.get("station")): s for s in lst}
        _catalog_cache = (lst, idx)
    return _catalog_cache


# 기관별 집계(대시보드 카드용 — 전 관측소 행 스캔 회피)
SUMMARY_JSON = os.path.join(QC_ROOT, "summary.json")
_summary_cache = None


def agency_summary(agency: str):
    """summary.json의 기관 집계 {n_stations,n_vars,total,retained,flagged} 또는 None."""
    global _summary_cache
    if _summary_cache is None:
        s = {}
        if os.path.exists(SUMMARY_JSON):
            try:
                with open(SUMMARY_JSON, encoding="utf-8") as f:
                    s = json.load(f)
            except (ValueError, OSError):
                s = {}
        _summary_cache = s
    return _summary_cache.get(agency)


# ── 카탈로그 ────────────────────────────────────────────────
def list_agencies() -> List[str]:
    if not os.path.isdir(FLAG_ROOT):
        return []
    return [d for d in sorted(os.listdir(FLAG_ROOT))
            if os.path.isdir(os.path.join(FLAG_ROOT, d))]


def agency_name(agency: str) -> str:
    return AGENCY_META.get(agency, {}).get("name", agency)


def agency_dataset(agency: str) -> str:
    return AGENCY_META.get(agency, {}).get("dataset", "")


def list_stations(agency: str) -> List[str]:
    d = os.path.join(FLAG_ROOT, agency)
    if not os.path.isdir(d):
        return []
    return [s for s in sorted(os.listdir(d)) if os.path.isdir(os.path.join(d, s))]


def _flag_files(agency: str, station: str) -> List[str]:
    return sorted(glob.glob(os.path.join(FLAG_ROOT, agency, station, "*", "*_qc_flag.csv")))


def _load_rows(agency: str, station: str) -> List[Dict[str, str]]:
    files = _flag_files(agency, station)
    if not files:
        return []
    key = (agency, station)
    mtime = sum(os.path.getmtime(f) for f in files)
    cached = _rows_cache.get(key)
    if cached and cached[0] == mtime:
        return cached[1]
    rows: List[Dict[str, str]] = []
    for fp in files:
        with open(fp, encoding="utf-8-sig", newline="") as f:
            rows.extend(csv.DictReader(f))
    _rows_cache[key] = (mtime, rows)
    return rows


def station_name(agency: str, station: str) -> str:
    key = (agency, station)
    if key in _name_cache:
        return _name_cache[key]
    c = _catalog()[1].get(key)
    if c and c.get("name"):
        _name_cache[key] = c["name"]
        return c["name"]
    name = station
    tp = os.path.join(QC_ROOT, "meta", "stations", agency.upper(), station + ".toml")
    if os.path.exists(tp):
        with open(tp, encoding="utf-8") as f:
            for line in f:
                s = line.strip()
                if s.startswith("name_k"):
                    name = s.split("=", 1)[1].strip().strip('"').strip("'")
                    break
    _name_cache[key] = name
    return name


def station_meta(agency: str, station: str) -> Dict[str, Any]:
    c = _catalog()[1].get((agency, station))   # 카탈로그 우선(전체 행 적재 회피)
    if c is not None:
        return {"station_id": station, "name": c.get("name") or station,
                "lat": c.get("lat"), "lon": c.get("lon")}
    lat = lon = None
    for r in _load_rows(agency, station):
        if r.get("lat"):
            try:
                lat = float(r["lat"]); lon = float(r["lon"]); break
            except (ValueError, TypeError):
                pass
    return {"station_id": station, "name": station_name(agency, station),
            "lat": lat, "lon": lon}


def list_variables(agency: str, station: str) -> List[str]:
    out: List[str] = []
    seen = set()
    for r in _load_rows(agency, station):
        v = r.get("var_id")
        if v and v not in seen:
            seen.add(v); out.append(v)
    return out


# ── 통계 / 시계열 ───────────────────────────────────────────
def _to_int(x: Any, default: int = 0) -> int:
    try:
        return int(float(x))
    except (ValueError, TypeError):
        return default


def _to_float(x: Any) -> Optional[float]:
    if x is None or x == "" or x == "-999" or x == "-999.0":
        return None
    try:
        return float(x)
    except (ValueError, TypeError):
        return None


def variable_status(agency: str, station: str) -> List[Dict[str, Any]]:
    """var_id별 QC 통계(good/suspect/bad/interp/missing + 보존/제거/보존율)."""
    agg: Dict[str, Dict[str, int]] = {}
    for r in _load_rows(agency, station):
        v = r.get("var_id")
        if not v:
            continue
        a = agg.setdefault(v, {"n": 0, "good": 0, "suspect": 0, "bad": 0,
                               "interp": 0, "missing": 0})
        a["n"] += 1
        ff = _to_int(r.get("flag_final"), 0)
        if ff == FLAG_GOOD:
            a["good"] += 1
        elif ff == FLAG_SUSPECT:
            a["suspect"] += 1
        elif ff == FLAG_BAD:
            a["bad"] += 1
        elif ff == FLAG_INTERP:
            a["interp"] += 1
        elif ff == FLAG_MISSING:
            a["missing"] += 1
    out: List[Dict[str, Any]] = []
    for v in list_variables(agency, station):
        a = agg.get(v, {"n": 0, "good": 0, "suspect": 0, "bad": 0, "interp": 0, "missing": 0})
        meta = V.get(v)
        n = a["n"]
        retained = a["good"] + a["suspect"]
        flagged = a["bad"] + a["missing"]
        out.append({
            "key": v, "name": meta["name"], "unit": meta["unit"],
            "collected": n > 0,
            "n": n, "retained": retained, "flagged": flagged,
            "good": a["good"], "suspect": a["suspect"], "bad": a["bad"],
            "interp": a["interp"], "missing": a["missing"],
            "flag_rate_pct": round(100.0 * flagged / n, 1) if n else 0.0,
        })
    return out


def load_series(agency: str, station: str, var_id: str) -> List[Dict[str, Any]]:
    """var_id 시계열: [{time, value, flag}]  (flag=flag_final 정수)."""
    series: List[Dict[str, Any]] = []
    for r in _load_rows(agency, station):
        if r.get("var_id") != var_id:
            continue
        series.append({
            "time": r.get("time"),
            "value": _to_float(r.get("value")),
            "flag": _to_int(r.get("flag_final"), FLAG_MISSING),
        })
    return series


# ── 해역 분류 / 카탈로그 / 내보내기 ─────────────────────────
def station_region(lat: Any, lon: Any) -> str:
    """위경도로 서해/남해/동해 구분(한반도 연안 근사 규칙). 미상이면 '기타'."""
    try:
        lat = float(lat); lon = float(lon)
    except (TypeError, ValueError):
        return "기타"
    # 동해안은 북상하며 서쪽으로 휜다(속초 128.6·강릉 128.9·포항 129.4) → lon>=128.5로 포착
    if lon >= 128.5 and lat >= 35.4:      # 동해(포항·울산·강릉·속초 등 동해안)
        return "동해"
    if lon < 126.5:                       # 서해안 서측(목포·신안·변산 등)
        return "서해"
    if lat < 35.4:                        # 남부 연안(해남~부산)
        return "남해"
    return "서해"                          # 그 외 서해안 북부(인천·군산 등)


REGIONS = ["서해", "남해", "동해"]


def valid_targets() -> set:
    """카탈로그에 실재하는 (agency, station) 화이트리스트. 다운로드 경로주입 방지용."""
    return {(a, s) for a in list_agencies() for s in list_stations(a)}


def list_all_stations() -> List[Dict[str, Any]]:
    """전 기관 관측소 카탈로그(+해역·변수목록). 검색/다운로드 범위 선택용.
    catalog.json(사전계산)이 있으면 그대로 사용(전체 행 적재 회피)."""
    lst = _catalog()[0]
    if lst:
        return lst
    out: List[Dict[str, Any]] = []
    for agency in list_agencies():
        for st in list_stations(agency):
            meta = station_meta(agency, st)
            vlist = []
            for v in list_variables(agency, st):
                vm = V.get(v)
                vlist.append({"key": v, "name": vm["name"], "unit": vm["unit"]})
            out.append({
                "agency": agency, "agencyName": agency_name(agency),
                "station": st, "name": meta["name"],
                "lat": meta["lat"], "lon": meta["lon"],
                "region": station_region(meta["lat"], meta["lon"]),
                "vars": vlist,
            })
    return out


def export_rows(agency: str, station: str, var_ids=None,
                start: Optional[str] = None, end: Optional[str] = None,
                max_flag: int = FLAG_MISSING, min_flag: int = FLAG_GOOD):
    """필터된 raw 행을 yield. var_ids=None이면 전체 변수.
    조건: min_flag <= flag_final <= max_flag, start<=time[:10]<=end(있을 때).
    (예: min_flag=2,max_flag=9 → '주의 이상' 의심·불량·보간·결측만)."""
    vset = set(var_ids) if var_ids else None
    for r in _load_rows(agency, station):
        if vset is not None and r.get("var_id") not in vset:
            continue
        ff = _to_int(r.get("flag_final"), FLAG_MISSING)
        if ff > max_flag or ff < min_flag:
            continue
        t = (r.get("time") or "")[:10]
        if start and t < start:
            continue
        if end and t > end:
            continue
        yield r
