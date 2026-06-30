# -*- coding: utf-8-sig -*-
"""
Zero 검사 (AQC1 최초 단계)
- float dtype: 연속 2개 이상 0 → BAD
- int/uint dtype: 단일 0도 → BAD (정수 0은 센서 미수신 sentinel)
수온·염분처럼 0이 물리적으로 불가능하거나 sentinel로 사용되는 변수에 적용.
"""

from __future__ import annotations

import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_GOOD, FLAG_MISSING


def check_zero(series: pd.Series, cfg: dict) -> pd.DataFrame:
    """
    cfg 키: 없음
    반환: DataFrame[flag(int8), reason(str)]
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    is_int_dtype = series.dtype.kind in ("i", "u")
    zero_mask = ~missing & (series == 0)

    single_fail = bool(cfg.get("single_fail", False))

    if is_int_dtype:
        # 정수형: 단일 0도 센서 미수신 sentinel로 간주 → BAD
        result.loc[zero_mask, "flag"]   = FLAG_BAD
        result.loc[zero_mask, "reason"] = "zero_fail(int)"
    elif single_fail:
        # single_fail=true: 단독 0도 BAD (sal 등 0이 물리적으로 불가능한 변수)
        result.loc[zero_mask, "flag"]   = FLAG_BAD
        result.loc[zero_mask, "reason"] = "zero_fail(single)"
    else:
        # 실수형 기본: 연속 2개 이상인 0만 → BAD
        consec = zero_mask & (zero_mask.shift(1, fill_value=False) | zero_mask.shift(-1, fill_value=False))
        result.loc[consec, "flag"]   = FLAG_BAD
        result.loc[consec, "reason"] = "zero_fail(consec)"

    return result
