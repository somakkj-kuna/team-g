# -*- coding: utf-8-sig -*-
"""
고착값(stuck) 검사.
연속으로 변화량이 min_change 이하인 구간의 길이가 window 이상이면 BAD로 판정.
전진 run-length 계산 후 역방향 전파로 구간 전체에 최대 run 길이를 부여한다.
"""

import numpy as np
import pandas as pd
from qcsrc.checks import FLAG_BAD, _init_flags


def run(
    series: pd.Series,
    min_change: float = 0.0,
    window: int = 6,
    **kwargs,
) -> pd.Series:
    """
    고착값 검사.

    Parameters
    ----------
    series     : DatetimeIndex를 가진 시계열
    min_change : 변화량이 이 값 이하면 '동일'로 간주 (0.0 = 완전 동일만)
    window     : 이 횟수 이상 연속 고착이면 BAD
    """
    flags = _init_flags(series)
    if window < 2:
        return flags

    vals = series.values.astype(float)
    n = len(vals)
    if n == 0:
        return flags

    # 전진 누적 run 길이: run_len[i] = i 위치에서 끝나는 run의 길이
    run_len = np.ones(n, dtype=int)
    for i in range(1, n):
        if np.isnan(vals[i]) or np.isnan(vals[i - 1]):
            # NaN은 run을 끊음
            run_len[i] = 1
        elif abs(vals[i] - vals[i - 1]) <= min_change:
            run_len[i] = run_len[i - 1] + 1

    # 역방향 전파: 각 위치에 자신이 속한 run의 전체 길이를 기록
    max_run = run_len.copy()
    for i in range(n - 2, -1, -1):
        if np.isnan(vals[i]) or np.isnan(vals[i + 1]):
            continue
        if abs(vals[i] - vals[i + 1]) <= min_change:
            if max_run[i + 1] > max_run[i]:
                max_run[i] = max_run[i + 1]

    for i in range(n):
        if not np.isnan(vals[i]) and max_run[i] >= window:
            flags.iloc[i] = FLAG_BAD

    return flags
