# -*- coding: utf-8-sig -*-
"""
신호 감쇠(Attenuated Signal) 검사 (AQC1)
rolling window 내 변동량(표준편차 또는 max-min 범위)이 min_var 이하로 지속되면 SUSPECT.
stuck_check(완전 고착)와 상보적: 미세 진동은 있지만 물리적으로 불가능할 정도로
신호 폭이 좁아지는 센서 감쇠 현상을 탐지한다.

출처: QARTOD Manual (IOOS/NOAA 2020) — Attenuated Signal Test (필수 검사).
서버 컨벤션: check_XXX(series, cfg, time_index) -> DataFrame[flag(int8), reason(str)].
"""

from __future__ import annotations

import pandas as pd

from ..utils.flag_io import FLAG_GOOD, FLAG_SUSPECT, FLAG_MISSING


def check_attenuated(series: pd.Series, cfg: dict,
                     time_index: pd.Series | None = None) -> pd.DataFrame:
    """
    series    : 단일 변수 시계열 (RangeIndex, NaN = 결측)
    cfg       : variables.{var}.attenuated 섹션
        window  (str)   rolling 윈도우 (기본 '72h'; 정수 입력 시 표본 개수)
        min_var (float) 이 값 미만 변동량이 지속되면 SUSPECT (변수별 튜닝 필수)
        metric  (str)   'std' (rolling 표준편차) | 'range' (rolling max-min)
    time_index: series와 동일 길이의 datetime (시간 기반 window 계산용)
    반환: DataFrame[flag(int), reason(str)]
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    if len(series) < 2:
        return result

    window  = cfg.get("window", "72h")
    min_var = cfg.get("min_var")
    metric  = str(cfg.get("metric", "std"))

    # min_var 미설정 시 검사 무의미 → GOOD 유지
    if min_var is None:
        return result
    min_var = float(min_var)

    # 시간 기반 rolling을 위해 DatetimeIndex 부여 (없으면 위치 기반)
    if time_index is not None:
        ts = pd.Series(series.values, index=pd.to_datetime(time_index))
    else:
        ts = pd.Series(series.values, index=series.index)

    min_periods = 2
    if metric == "std":
        variation = ts.rolling(window, min_periods=min_periods).std()
    elif metric == "range":
        # apply 루프 대신 내장 집계 조합으로 성능 확보
        variation = (
            ts.rolling(window, min_periods=min_periods).max()
            - ts.rolling(window, min_periods=min_periods).min()
        )
    else:
        raise ValueError(f"지원하지 않는 metric: {metric!r}  (std | range)")

    variation = variation.values  # 위치 정렬
    valid = (~missing).values
    for i in range(len(series)):
        if not valid[i]:
            continue
        v = variation[i]
        if v == v and v < min_var:   # not NaN and below threshold
            result.iloc[i] = [FLAG_SUSPECT, f"attenuated({v:.3f}<{min_var})"]

    return result
