# -*- coding: utf-8-sig -*-
"""
물리 범위 검사 (AQC1)
- 연중 고정 범위 초과 → bad
- 계절별 추가 narrowing 가능 (sur_sal 등)
"""

from __future__ import annotations

import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def check_range(series: pd.Series, cfg: dict,
                time_index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    """
    series    : 단일 변수 시계열 (NaN = 결측)
    cfg       : variables.{var}.range 섹션
    time_index: series와 동일 길이의 datetime (계절 범위용)
    반환: DataFrame[flag(int), reason(str)]
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    general_range = cfg.get("general_range", {}) or {}
    v_min = general_range.get("min", cfg.get("min"))
    v_max = general_range.get("max", cfg.get("max"))

    if v_min is not None:
        mask = (~missing) & (series < v_min)
        result.loc[mask, "flag"]   = FLAG_BAD
        result.loc[mask, "reason"] = f"below_range({v_min})"

    if v_max is not None:
        mask = (~missing) & (series > v_max)
        result.loc[mask, "flag"]   = FLAG_BAD
        result.loc[mask, "reason"] = f"above_range({v_max})"

    # 계절별 narrowing
    seasonal = cfg.get("seasonal", [])
    if seasonal and time_index is not None:
        months = pd.to_datetime(time_index).dt.month
        for season in seasonal:
            s_months = season.get("months", [])
            s_min    = season.get("min")
            s_max    = season.get("max")
            in_season = pd.Series(months.isin(s_months), index=series.index)
            if s_min is not None:
                mask = (~missing) & in_season & (series < s_min)
                result.loc[mask, "flag"]   = FLAG_BAD
                result.loc[mask, "reason"] = (
                    f"below_seasonal_{season['label']}({s_min})"
                )
            if s_max is not None:
                mask = (~missing) & in_season & (series > s_max)
                result.loc[mask, "flag"]   = FLAG_BAD
                result.loc[mask, "reason"] = (
                    f"above_seasonal_{season['label']}({s_max})"
                )

    return result
