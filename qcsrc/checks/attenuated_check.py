# -*- coding: utf-8-sig -*-
"""
신호 감쇠(Attenuated Signal) 검사.
rolling window 내 변동량(표준편차 또는 max-min 범위)이 min_var 이하로 지속되면 SUSPECT.
stuck_check(완전 고착)와 상보적: 미세 진동은 있지만 물리적으로 불가능할 정도로 좁은 신호 탐지.
출처: QARTOD Manual (IOOS/NOAA 2020) — Attenuated Signal Test.
"""

import pandas as pd

from qcsrc.checks import FLAG_SUSPECT, _init_flags


def run(
    series: pd.Series,
    window: str = "72h",
    min_var: float = 0.01,
    metric: str = "std",
    **kwargs,
) -> pd.Series:
    """
    신호 감쇠 검사.

    Parameters
    ----------
    series  : DatetimeIndex를 가진 시계열
    window  : rolling 윈도우 크기 (시간 문자열 권장, 예: '72h'; 정수도 허용)
    min_var : 이 값 미만의 변동량이 지속되면 SUSPECT
              기본값 0.01은 수온(°C) 기준; 변수별 튜닝 필요
    metric  : 변동량 측정 방식
              'std'   — rolling 표준편차 (평균 변동성)
              'range' — rolling (max - min) (절대 범위)
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("attenuated_check.run 은 DatetimeIndex 가 필요합니다.")

    flags = _init_flags(series)
    valid = ~series.isna()

    # window 크기에 따른 최소 데이터 포인트 (너무 작으면 전부 SUSPECT 오탐 방지)
    min_periods = 2

    if metric == "std":
        variation = series.rolling(window, min_periods=min_periods).std()
    elif metric == "range":
        # apply 루프 대신 내장 집계 조합으로 성능 확보
        variation = (
            series.rolling(window, min_periods=min_periods).max()
            - series.rolling(window, min_periods=min_periods).min()
        )
    else:
        raise ValueError(f"지원하지 않는 metric: {metric!r}  (std | range)")

    attenuated = valid & variation.notna() & (variation < min_var)
    flags[attenuated] = FLAG_SUSPECT

    return flags
