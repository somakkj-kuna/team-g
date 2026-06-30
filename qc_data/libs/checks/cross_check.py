# -*- coding: utf-8-sig -*-
"""
교차 변수 검사 (AQC1)
1. reference_check: 기준 변수(예: tide_pre)와의 차이 비교
2. vertical_check : 수직층(sur/mid/bot_temp) 간 물리적 일관성
3. vector_range   : u-v 쌍으로 합성 크기 범위 검사

bad-skip 원칙: 상대 변수가 이미 bad인 시점은 비교를 건너뜀 (오탐 방지).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def check_reference(series: pd.Series, ref_series: pd.Series,
                    cfg: dict,
                    other_flags: pd.Series | None = None) -> pd.DataFrame:
    """
    cfg 키: suspect_threshold, fail_threshold
    other_flags: ref_series에 해당하는 flag — bad인 시점은 비교 건너뜀
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    suspect_thr = float(cfg.get("suspect_threshold", float("inf")))
    fail_thr    = float(cfg.get("fail_threshold",    float("inf")))
    ref_col     = cfg.get("column", "reference")

    # ref가 bad인 시점은 비교 무효
    ref_bad = pd.Series(False, index=series.index)
    if other_flags is not None:
        ref_bad = pd.Series(other_flags.values == FLAG_BAD, index=series.index)

    diff = (series - ref_series).abs()

    valid = (~missing) & (~ref_series.isna()) & (~ref_bad)
    mask_fail    = valid & (diff >= fail_thr)
    mask_suspect = valid & (diff >= suspect_thr) & (~mask_fail)

    result.loc[mask_fail,    "flag"]   = FLAG_BAD
    result.loc[mask_fail,    "reason"] = diff[mask_fail].map(
        lambda d: f"ref_fail(diff={d:.1f},{ref_col})")

    result.loc[mask_suspect, "flag"]   = FLAG_SUSPECT
    result.loc[mask_suspect, "reason"] = diff[mask_suspect].map(
        lambda d: f"ref_suspect(diff={d:.1f},{ref_col})")

    return result


def check_vertical(series: pd.Series, other_series: pd.Series,
                   cfg: dict,
                   other_flags: pd.Series | None = None) -> pd.DataFrame:
    """
    cfg 키: min_diff, max_diff (series - other 범위)
    other_flags: other_series에 해당하는 flag — bad인 시점은 비교 건너뜀
    예: mid_temp - sur_temp 이 min_diff ~ max_diff 범위 벗어나면 bad.
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    min_diff = cfg.get("min_diff")
    max_diff = cfg.get("max_diff")
    other    = cfg.get("other", "other")

    # 상대 변수가 bad인 시점은 비교 무효
    other_bad = pd.Series(False, index=series.index)
    if other_flags is not None:
        other_bad = pd.Series(
            other_flags.values == FLAG_BAD, index=series.index)

    diff = series - other_series
    both_valid = (~missing) & (~other_series.isna()) & (~other_bad)

    if min_diff is not None:
        mask = both_valid & (diff < min_diff)
        result.loc[mask, "flag"]   = FLAG_BAD
        result.loc[mask, "reason"] = f"vertical_low({other},diff={min_diff})"

    if max_diff is not None:
        mask = both_valid & (diff > max_diff)
        result.loc[mask, "flag"]   = FLAG_BAD
        result.loc[mask, "reason"] = f"vertical_high({other},diff={max_diff})"

    return result


def check_vector_range(u_series: pd.Series, v_series: pd.Series,
                       cfg: dict) -> pd.DataFrame:
    """
    u-v 쌍의 합성 크기(sqrt(u²+v²)) 범위 검사.
    cfg 키: min, max
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(u_series), dtype="int8"),
        "reason": [""] * len(u_series),
    }, index=u_series.index)

    missing = u_series.isna() | v_series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    v_min = cfg.get("min")
    v_max = cfg.get("max")

    mag = np.sqrt(u_series ** 2 + v_series ** 2)

    if v_min is not None:
        mask = (~missing) & (mag < v_min)
        result.loc[mask, "flag"]   = FLAG_BAD
        result.loc[mask, "reason"] = mag[mask].map(
            lambda m: f"vec_below_range({m:.1f})")

    if v_max is not None:
        mask = (~missing) & (mag > v_max)
        result.loc[mask, "flag"]   = FLAG_BAD
        result.loc[mask, "reason"] = mag[mask].map(
            lambda m: f"vec_above_range({m:.1f})")

    return result
