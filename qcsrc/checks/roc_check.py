# -*- coding: utf-8-sig -*-
"""
변화율(Rate-of-Change, ROC) 검사.
이전 유효값 대비 시간당 변화율이 max_rate 이상이면 BAD로 판정한다.
NaN을 건너뛰고 마지막 유효값 위치를 추적한다.
"""

import numpy as np
import pandas as pd
from qcsrc.checks import FLAG_BAD, _init_flags


def run(series: pd.Series, max_rate: float, **kwargs) -> pd.Series:
    """
    시간당 변화율 검사.

    Parameters
    ----------
    series   : DatetimeIndex를 가진 시계열
    max_rate : 시간당 허용 최대 변화량 (원단위/h)
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("roc_check.run 은 DatetimeIndex 가 필요합니다.")

    flags = _init_flags(series)
    vals = series.values.astype(float)
    times = series.index
    n = len(vals)

    prev_idx = None  # 직전 유효값 위치

    for i in range(n):
        if np.isnan(vals[i]):
            continue

        if prev_idx is not None:
            dt_sec = (times[i] - times[prev_idx]).total_seconds()
            if dt_sec > 0:
                rate = abs(vals[i] - vals[prev_idx]) / (dt_sec / 3600.0)
                if rate >= max_rate:
                    flags.iloc[i] = FLAG_BAD

        prev_idx = i

    return flags
