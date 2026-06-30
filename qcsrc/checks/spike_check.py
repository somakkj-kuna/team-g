# -*- coding: utf-8-sig -*-
"""
스파이크(급등락) 검사.
알고리즘 3종을 method 파라미터로 선택한다.
  'zscore' — 전역 평균/표준편차 기반 z점수 (정규 분포 가정)
  'iqr'    — 사분위 범위(IQR) 기반 (극단값에 강건)
  'median' — 이웃 중앙값 편차 기반 (기본값; 로컬 패턴 적응)
"""

import numpy as np
import pandas as pd
from qcsrc.checks import FLAG_BAD, _init_flags


def run(
    series: pd.Series,
    method: str = "median",
    threshold: float = 3.0,
    window: int = 3,
    **kwargs,
) -> pd.Series:
    """
    스파이크 탐지.

    Parameters
    ----------
    series    : DatetimeIndex를 가진 시계열
    method    : 'zscore' | 'iqr' | 'median'
    threshold : method별 판정 임계값
                  zscore → σ 단위 (예: 3.0)
                  iqr    → IQR 배수 (예: 1.5)
                  median → 원단위 절대 편차 (예: 3.0°C)
    window    : median 방법에서 각 방향 이웃 최대 개수
    """
    if method == "zscore":
        return _spike_zscore(series, threshold)
    if method == "iqr":
        return _spike_iqr(series, threshold)
    if method == "median":
        return _spike_median(series, threshold, window)
    raise ValueError(f"지원하지 않는 method: {method!r}  (zscore | iqr | median)")


# ---------------------------------------------------------------------------
# 내부 구현
# ---------------------------------------------------------------------------

def _spike_zscore(series: pd.Series, threshold: float) -> pd.Series:
    """전역 평균·표준편차 기반 z점수. |z| >= threshold → BAD."""
    flags = _init_flags(series)
    valid_vals = series.dropna()
    if len(valid_vals) < 2:
        return flags

    mean = valid_vals.mean()
    std = valid_vals.std()
    # std가 0에 가까우면 모든 값이 동일 → 스파이크 없음으로 처리
    if std < 1e-10:
        return flags

    z = (series - mean).abs() / std
    valid = ~series.isna()
    flags[valid & (z >= threshold)] = FLAG_BAD
    return flags


def _spike_iqr(series: pd.Series, threshold: float) -> pd.Series:
    """사분위 범위 기반. [Q1 - threshold*IQR, Q3 + threshold*IQR] 밖 → BAD."""
    flags = _init_flags(series)
    valid_vals = series.dropna()
    if len(valid_vals) < 4:
        return flags

    q1 = valid_vals.quantile(0.25)
    q3 = valid_vals.quantile(0.75)
    iqr = q3 - q1
    if iqr < 1e-10:
        return flags

    lower = q1 - threshold * iqr
    upper = q3 + threshold * iqr
    valid = ~series.isna()
    flags[valid & ((series < lower) | (series > upper))] = FLAG_BAD
    return flags


def _spike_median(series: pd.Series, threshold: float, window: int) -> pd.Series:
    """
    이웃 중앙값 편차 기반.
    각 값에 대해 좌우 최대 window개의 비NaN 이웃을 수집,
    중앙값과의 절대 편차가 threshold 이상이면 BAD.
    이웃이 2개 미만이면 판정을 건너뜀.
    """
    flags = _init_flags(series)
    vals = series.values.astype(float)
    n = len(vals)

    for i in range(n):
        if np.isnan(vals[i]):
            continue

        left = []
        for j in range(i - 1, -1, -1):
            if len(left) >= window:
                break
            if not np.isnan(vals[j]):
                left.append(vals[j])

        right = []
        for j in range(i + 1, n):
            if len(right) >= window:
                break
            if not np.isnan(vals[j]):
                right.append(vals[j])

        neighbors = left + right
        if len(neighbors) < 2:
            continue

        ref = float(np.median(neighbors))
        if abs(vals[i] - ref) >= threshold:
            flags.iloc[i] = FLAG_BAD

    return flags
