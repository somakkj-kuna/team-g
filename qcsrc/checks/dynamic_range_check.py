# -*- coding: utf-8-sig -*-
"""
동적 분위값 기반 범위 검사 (Dynamic Range Check).
월별 또는 계절별 분위값 테이블을 이용해 계절성 이상값을 탐지한다.
고정 임계값 range_check의 확장판으로, 계절에 따라 임계값이 달라진다.
출처: Cheng et al. 2022 (CODC-QC), Ingleby & Huddleston 2007 (EN4), QARTOD 2020.
"""

import pandas as pd

from qcsrc.checks import FLAG_BAD, FLAG_SUSPECT, _init_flags

# 계절별 모드에서 사용하는 월→계절 기본 매핑 (한국 기상청 기준)
_DEFAULT_SEASON_MAP = {
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
    12: "winter", 1: "winter", 2: "winter",
}


def run(
    series: pd.Series,
    quantile_table: dict,
    fallback_range: dict = None,
    mode: str = "monthly",
    season_map: dict = None,
    **kwargs,
) -> pd.Series:
    """
    동적 분위값 범위 검사.

    Parameters
    ----------
    series          : DatetimeIndex를 가진 시계열
    quantile_table  : 분위값 테이블 (아래 형식 중 하나)
        월별 2값 (BAD만):
            {1: (lo, hi), 2: (lo, hi), ..., 12: (lo, hi)}
        월별 4값 (SUSPECT + BAD):
            {1: (lo_bad, lo_sus, hi_sus, hi_bad), ...}
        계절별도 동일 구조, 키를 'spring'/'summer'/'autumn'/'winter'로
    fallback_range  : 테이블에 없는 월/계절의 fallback {vmin: float, vmax: float}
                      None이면 해당 기간을 판정 건너뜀 (암묵적 GOOD)
    mode            : 'monthly' (월 1~12 키) | 'seasonal' (계절 문자열 키)
    season_map      : mode='seasonal'일 때 월→계절 매핑 dict (None이면 기본값 사용)
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("dynamic_range_check.run 은 DatetimeIndex 가 필요합니다.")

    flags = _init_flags(series)
    months = series.index.month

    if mode == "seasonal":
        s_map = season_map if season_map is not None else _DEFAULT_SEASON_MAP
        group_keys = months.map(s_map)
    elif mode == "monthly":
        group_keys = months
    else:
        raise ValueError(f"지원하지 않는 mode: {mode!r}  (monthly | seasonal)")

    for key in pd.Series(group_keys).unique():
        mask_group = (group_keys == key) & ~series.isna()

        if key not in quantile_table:
            # fallback: 고정 범위로 degradation
            if fallback_range is not None:
                vmin = fallback_range["vmin"]
                vmax = fallback_range["vmax"]
                flags[mask_group & (series < vmin)] = FLAG_BAD
                flags[mask_group & (series > vmax)] = FLAG_BAD
            continue

        bounds = quantile_table[key]

        if len(bounds) == 2:
            # (lo_bad, hi_bad) — BAD만
            lo_bad, hi_bad = bounds
            flags[mask_group & (series < lo_bad)] = FLAG_BAD
            flags[mask_group & (series > hi_bad)] = FLAG_BAD

        elif len(bounds) == 4:
            # (lo_bad, lo_sus, hi_sus, hi_bad) — SUSPECT + BAD 2단계
            lo_bad, lo_sus, hi_sus, hi_bad = bounds
            flags[mask_group & (series < lo_bad)] = FLAG_BAD
            flags[mask_group & (series > hi_bad)] = FLAG_BAD
            # SUSPECT는 BAD가 아닌 경우에만 덮어씀
            sus_lo = mask_group & (series >= lo_bad) & (series < lo_sus)
            sus_hi = mask_group & (series <= hi_bad) & (series > hi_sus)
            flags[sus_lo & (flags != FLAG_BAD)] = FLAG_SUSPECT
            flags[sus_hi & (flags != FLAG_BAD)] = FLAG_SUSPECT
        else:
            raise ValueError(
                f"quantile_table[{key!r}] 의 길이는 2 또는 4여야 합니다. "
                f"현재: {len(bounds)}"
            )

    return flags
