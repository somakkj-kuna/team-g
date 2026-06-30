# -*- coding: utf-8-sig -*-
"""
동적 분위값 기반 범위 검사 (Dynamic Range Check, AQC1)
월별 또는 계절별 분위값 테이블을 이용해 "고정 범위 내이지만 계절적으로 비정상"인
값을 탐지한다. 고정 임계값 range_check의 계절화 확장판.

출처: Cheng et al. 2022 (CODC-QC), Ingleby & Huddleston 2007 (EN4), QARTOD 2020.
서버 컨벤션: check_XXX(series, cfg, time_index) -> DataFrame[flag(int8), reason(str)].

TOML 설정 예 (월별 4값 = SUSPECT+BAD 2단계):
  [variables.sur_temp.dynamic_range]
  mode = "monthly"
  [variables.sur_temp.dynamic_range.table]
  "1"  = [-2.0, 0.0, 14.0, 18.0]   # (lo_bad, lo_sus, hi_sus, hi_bad)
  "8"  = [18.0, 30.0]              # (lo_bad, hi_bad) — BAD만
  [variables.sur_temp.dynamic_range.fallback]
  vmin = -2.0
  vmax = 40.0
"""

from __future__ import annotations

import pandas as pd

from ..utils.flag_io import FLAG_GOOD, FLAG_BAD, FLAG_SUSPECT, FLAG_MISSING

# 계절별 모드 월→계절 기본 매핑 (한국 기상청 기준)
_DEFAULT_SEASON_MAP = {
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
    12: "winter", 1: "winter", 2: "winter",
}


def _norm_table(table: dict, mode: str) -> dict:
    """TOML 문자열 키 테이블을 표준 키(int 월 / str 계절)로 정규화."""
    norm: dict = {}
    for k, v in table.items():
        if mode == "monthly":
            try:
                key = int(k)
            except (ValueError, TypeError):
                continue
        else:
            key = str(k)
        norm[key] = tuple(float(x) for x in v)
    return norm


def check_dynamic_range(series: pd.Series, cfg: dict,
                        time_index: pd.Series | None = None) -> pd.DataFrame:
    """
    series    : 단일 변수 시계열 (RangeIndex, NaN = 결측)
    cfg       : variables.{var}.dynamic_range 섹션
        table    (dict) 분위값 테이블 — 키="1".."12"(monthly) 또는 계절명(seasonal),
                        값=[lo_bad, hi_bad] 또는 [lo_bad, lo_sus, hi_sus, hi_bad]
        mode     (str)  'monthly' | 'seasonal'
        fallback (dict) 테이블에 없는 월/계절용 {vmin, vmax} (없으면 해당 기간 GOOD 유지)
        season_map (dict) seasonal 모드 월→계절 매핑 (없으면 기본값)
    time_index: series와 동일 길이의 datetime (월/계절 판정용, 필수)
    반환: DataFrame[flag(int), reason(str)]
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    raw_table = cfg.get("table", {}) or {}
    if time_index is None or not raw_table:
        # 분위값 테이블 없으면 검사 무의미 → GOOD 유지 (콜드스타트)
        return result

    mode = str(cfg.get("mode", "monthly"))
    table = _norm_table(raw_table, mode)
    months = pd.to_datetime(time_index).dt.month.values

    if mode == "seasonal":
        s_map = cfg.get("season_map") or _DEFAULT_SEASON_MAP
        s_map = {int(k): v for k, v in s_map.items()}
        group_keys = [s_map.get(int(m)) for m in months]
    elif mode == "monthly":
        group_keys = [int(m) for m in months]
    else:
        raise ValueError(f"지원하지 않는 mode: {mode!r}  (monthly | seasonal)")

    fallback = cfg.get("fallback")
    vals = series.values
    flags = result["flag"].values.copy()
    reasons = result["reason"].tolist()

    for i in range(len(series)):
        if missing.iloc[i]:
            continue
        key = group_keys[i]
        x = float(vals[i])

        if key not in table:
            if fallback is not None:
                vmin = float(fallback["vmin"])
                vmax = float(fallback["vmax"])
                if x < vmin:
                    flags[i] = FLAG_BAD; reasons[i] = f"dyn_below_fallback({vmin})"
                elif x > vmax:
                    flags[i] = FLAG_BAD; reasons[i] = f"dyn_above_fallback({vmax})"
            continue

        bounds = table[key]
        if len(bounds) == 2:
            lo_bad, hi_bad = bounds
            if x < lo_bad:
                flags[i] = FLAG_BAD; reasons[i] = f"dyn_below({key}:{lo_bad})"
            elif x > hi_bad:
                flags[i] = FLAG_BAD; reasons[i] = f"dyn_above({key}:{hi_bad})"
        elif len(bounds) == 4:
            lo_bad, lo_sus, hi_sus, hi_bad = bounds
            if x < lo_bad or x > hi_bad:
                flags[i] = FLAG_BAD
                reasons[i] = (f"dyn_below({key}:{lo_bad})" if x < lo_bad
                              else f"dyn_above({key}:{hi_bad})")
            elif x < lo_sus:
                flags[i] = FLAG_SUSPECT; reasons[i] = f"dyn_susp_low({key}:{lo_sus})"
            elif x > hi_sus:
                flags[i] = FLAG_SUSPECT; reasons[i] = f"dyn_susp_high({key}:{hi_sus})"
        else:
            raise ValueError(
                f"dynamic_range table[{key!r}] 길이는 2 또는 4여야 합니다. 현재: {len(bounds)}")

    result["flag"] = pd.array(flags, dtype="int8")
    result["reason"] = reasons
    return result
