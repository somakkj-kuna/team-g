# -*- coding: utf-8-sig -*-
"""
QC 검사 패키지 공통 상수 및 헬퍼.
Flag: 1=good, 2=suspect, 3=bad, 9=missing
"""

import numpy as np
import pandas as pd

FLAG_GOOD = 1
FLAG_SUSPECT = 2
FLAG_BAD = 3
FLAG_MISSING = 9

__all__ = ["FLAG_GOOD", "FLAG_SUSPECT", "FLAG_BAD", "FLAG_MISSING", "_init_flags"]


def _init_flags(series: pd.Series) -> pd.Series:
    """NaN → MISSING(9), 나머지 → GOOD(1)로 초기화한 flag Series 반환."""
    flags = pd.Series(FLAG_GOOD, index=series.index, dtype=int)
    flags[series.isna()] = FLAG_MISSING
    return flags
