# -*- coding: utf-8-sig -*-
"""물리 범위 검사: [vmin, vmax] 밖 값을 BAD로 판정."""

import pandas as pd
from qcsrc.checks import FLAG_BAD, _init_flags


def run(series: pd.Series, vmin: float, vmax: float, **kwargs) -> pd.Series:
    """
    물리 범위 [vmin, vmax]를 벗어난 값을 BAD(3)로 판정.
    NaN은 MISSING(9), 범위 내 유효값은 GOOD(1).
    """
    flags = _init_flags(series)
    valid = ~series.isna()
    flags[valid & (series < vmin)] = FLAG_BAD
    flags[valid & (series > vmax)] = FLAG_BAD
    return flags
