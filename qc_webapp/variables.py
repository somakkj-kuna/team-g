# -*- coding: utf-8 -*-
"""관측 변수(var_id) 레지스트리 — sample_data long CSV의 var_id 기준.

sample_data QC 결과(flag/final CSV)는 long 포맷으로 한 행에 1개 var_id를 담는다.
여기서는 var_id → 한글명·단위 매핑만 제공한다. (QC는 이미 수행된 flag_final 사용)
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

# var_id 메타 (한글명, 단위). sample_data 3기관에서 등장하는 변수 + qc_rules.toml 변수.
VARIABLES: List[Dict[str, Any]] = [
    {"key": "temp",          "name": "수온",        "unit": "℃"},
    {"key": "sur_temp",      "name": "표층수온",    "unit": "℃"},
    {"key": "mid_temp",      "name": "중층수온",    "unit": "℃"},
    {"key": "bot_temp",      "name": "저층수온",    "unit": "℃"},
    {"key": "sal",           "name": "염분",        "unit": "psu"},
    {"key": "tide_real",     "name": "실측조위",    "unit": "cm"},
    {"key": "tide_pre",      "name": "예측조위",    "unit": "cm"},
    {"key": "air_temp",      "name": "기온",        "unit": "℃"},
    {"key": "air_pres",      "name": "기압",        "unit": "hPa"},
    {"key": "air_humi",      "name": "습도",        "unit": "%"},
    {"key": "wave_h",        "name": "파고",        "unit": "m"},
    {"key": "wind_dir",      "name": "풍향",        "unit": "°"},
    {"key": "wind_speed",    "name": "풍속",        "unit": "m/s"},
    {"key": "wind_gust",     "name": "돌풍",        "unit": "m/s"},
    {"key": "wind_u",        "name": "풍속 U성분",  "unit": "m/s"},
    {"key": "wind_v",        "name": "풍속 V성분",  "unit": "m/s"},
    {"key": "current_speed", "name": "유속",        "unit": "m/s"},
    {"key": "current_dir",   "name": "유향",        "unit": "°"},
    {"key": "current_u",     "name": "유속 U성분",  "unit": "m/s"},
    {"key": "current_v",     "name": "유속 V성분",  "unit": "m/s"},
]

_BY_KEY = {v["key"]: v for v in VARIABLES}
DEFAULT_VAR = "temp"


def get(key: Optional[str]) -> Dict[str, Any]:
    """var_id 메타 반환. 미등록 key는 key 자체를 이름으로 사용(단위 빈값)."""
    if key in _BY_KEY:
        return _BY_KEY[key]
    return {"key": key or DEFAULT_VAR, "name": key or DEFAULT_VAR, "unit": ""}


def keys() -> List[str]:
    return [v["key"] for v in VARIABLES]
