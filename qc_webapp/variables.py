# -*- coding: utf-8 -*-
"""조위관측소 QC 대상 변수(관측 항목) 레지스트리.

KHOA 조위관측소는 수온 외에도 조위·염분·기온·기압·풍속 등 여러 항목을 관측한다.
각 변수는 자료 디렉터리(downloads/<dir>)·단위·물리 QC 기본 파라미터를 가진다.
새 변수를 추가하려면 VARIABLES 에 항목을 더하고 같은 스키마의 자료를
downloads/<dir>/ 아래에 두면 UI·QC·보고서가 자동으로 인식한다.

자료 스키마(변수 공통): DT_XXXX.json
  {"obsCode","name","lat","lon","unit","interval_min","count",
   "series": [[date, mean, min, max, count], ...]}
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# 변수별 QC 기본 파라미터 — range_min/max 는 항목의 물리적 범위(한반도 주변해역 기준)
VARIABLES: List[Dict[str, Any]] = [
    {"key": "water_temp", "name": "수온", "unit": "℃", "dir": "khoa_water_temp",
     "qc": {"range_min": -2.0, "range_max": 35.0, "window": 7, "mad_k": 3.5}},
    {"key": "tide", "name": "조위", "unit": "cm", "dir": "khoa_tide",
     "qc": {"range_min": -100.0, "range_max": 1100.0, "window": 7, "mad_k": 4.0}},
    {"key": "salinity", "name": "염분", "unit": "psu", "dir": "khoa_salinity",
     "qc": {"range_min": 0.0, "range_max": 40.0, "window": 7, "mad_k": 3.5}},
    {"key": "air_temp", "name": "기온", "unit": "℃", "dir": "khoa_air_temp",
     "qc": {"range_min": -30.0, "range_max": 45.0, "window": 7, "mad_k": 3.5}},
    {"key": "air_pressure", "name": "기압", "unit": "hPa", "dir": "khoa_air_pressure",
     "qc": {"range_min": 900.0, "range_max": 1100.0, "window": 7, "mad_k": 4.0}},
    {"key": "wind_speed", "name": "풍속", "unit": "m/s", "dir": "khoa_wind",
     "qc": {"range_min": 0.0, "range_max": 75.0, "window": 7, "mad_k": 4.0}},
]

_BY_KEY = {v["key"]: v for v in VARIABLES}
DEFAULT_VAR = "water_temp"


def get(key: Optional[str]) -> Dict[str, Any]:
    """변수 메타 반환. 알 수 없는 key 는 기본 변수(수온)."""
    return _BY_KEY.get(key or DEFAULT_VAR, _BY_KEY[DEFAULT_VAR])


def keys() -> List[str]:
    return [v["key"] for v in VARIABLES]
