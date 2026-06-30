# -*- coding: utf-8-sig -*-
"""
전처리 모듈: 리샘플, 결측 보간, 물리 범위 마스킹.
파이프라인에서 QC 검사 이전에 호출된다.
"""

import numpy as np
import pandas as pd


def resample(series: pd.Series, freq: str, agg: str = "mean") -> pd.Series:
    """
    지정 주기(freq)로 리샘플.
    agg='mean': 평균 집계 / agg='ffill': 마지막값 전진 채움.
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("resample 은 DatetimeIndex 가 필요합니다.")
    if agg == "ffill":
        return series.resample(freq).ffill()
    return series.resample(freq).mean()


def fill_missing(series: pd.Series, method: str = "linear") -> pd.Series:
    """
    결측 보간.
    method: 'linear' (시간축 선형보간) | 'ffill' (전진채움) | 'bfill' (후진채움).
    """
    if method == "linear":
        # 시간 인덱스 기반 선형 보간 — 양 끝 외삽은 하지 않음(limit_direction='both' 제외)
        return series.interpolate(method="time")
    if method == "ffill":
        return series.ffill()
    if method == "bfill":
        return series.bfill()
    raise ValueError(f"지원하지 않는 보간 방법: {method!r}  (linear | ffill | bfill)")


def mask_extreme(series: pd.Series, vmin: float, vmax: float) -> pd.Series:
    """물리 범위 [vmin, vmax] 밖 값을 NaN으로 교체. QC 전 전처리 or 독립 유틸리티로 사용."""
    masked = series.copy()
    masked[(masked < vmin) | (masked > vmax)] = np.nan
    return masked
