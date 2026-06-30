# -*- coding: utf-8-sig -*-
"""
변화율 검사 (AQC1) — Rate of Change
시간당 변화량이 임계값을 초과하면 suspect/bad.
bad로 표시된 이전 값은 건너뛰고 마지막 정상값과 비교한다.
풍향처럼 circular 변수는 mode='circular' 로 설정.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def _circular_diff(a: float, b: float) -> float:
    """360도 순환 차이 (0~180 범위)"""
    d = abs(a - b) % 360
    return d if d <= 180 else 360 - d


def check_roc(series: pd.Series, cfg: dict,
              time_index: pd.DatetimeIndex | None = None,
              skip_series: pd.Series | None = None,
              cur_flags: pd.Series | None = None) -> pd.DataFrame:
    """
    cfg 키: suspect_per_hour, fail_per_hour
            mode ('linear' | 'circular')
            skip_below_col, skip_below_value (optional)
    time_index: series와 동일 길이의 DatetimeIndex (없으면 균등 간격 가정)
    cur_flags: 현재까지 누적된 flag (bad 값 건너뜀에 사용)
    반환: DataFrame[flag(int), reason(str)]
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    suspect_thr = float(cfg.get("suspect_per_hour", float("inf")))
    fail_thr    = float(cfg.get("fail_per_hour",    float("inf")))
    is_circular = cfg.get("mode", "linear") == "circular"
    skip_below  = cfg.get("skip_below_value")

    vals = series.values.astype(float)
    n    = len(vals)
    if n < 2:
        return result

    # 시간축 (초 단위) — pandas 3.x tz-aware는 astype(int64)가 μs 반환하므로
    # numpy datetime64[ns]로 강제 캐스팅 후 view(int64)로 항상 나노초 확보
    if time_index is not None:
        t_ns = (pd.to_datetime(time_index, utc=True)
                .values.astype("datetime64[ns]")
                .view(np.int64))
        times_sec = t_ns / 1e9
    else:
        times_sec = np.arange(n, dtype=float) * 3600.0

    flags_arr = None
    if cur_flags is not None:
        flags_arr = cur_flags.values

    def _is_bad(idx: int) -> bool:
        if flags_arr is None:
            return False
        # bad(3)/missing(9)만 건너뜀 — suspect는 이전 정상값으로 활용
        # (spike가 suspect 처리한 인접값을 건너뛰면 dt가 늘어나 roc가 희석됨)
        return int(flags_arr[idx]) >= FLAG_BAD

    for i in range(1, n):
        if missing.iloc[i]:
            continue

        # bad / missing 건너뛰고 마지막 정상 이전값 찾기
        p = i - 1
        while p >= 0 and (missing.iloc[p] or _is_bad(p)):
            p -= 1
        if p < 0:
            continue

        dt = (times_sec[i] - times_sec[p]) / 3600.0
        if dt <= 0:
            continue

        if skip_series is not None and skip_below is not None:
            sv = float(skip_series.iloc[i]) if not pd.isna(skip_series.iloc[i]) else 0.0
            if sv < skip_below:
                continue

        if is_circular:
            diff_per_hour = _circular_diff(vals[i], vals[p]) / dt
        else:
            diff_per_hour = abs(vals[i] - vals[p]) / dt

        if diff_per_hour >= fail_thr:
            result.iloc[i] = [FLAG_BAD,     f"roc_fail({diff_per_hour:.1f}/h)"]
        elif diff_per_hour >= suspect_thr:
            result.iloc[i] = [FLAG_SUSPECT, f"roc_suspect({diff_per_hour:.1f}/h)"]

    return result
