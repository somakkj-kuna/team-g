# -*- coding: utf-8-sig -*-
"""
고착값 검사 (AQC1)
연속으로 동일한 값이 반복되면 suspect/bad.
bad로 표시된 값이 끼어 있으면 run을 리셋한다 (센서 동결 구간에 이상 포인트가 있으면 중단).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def check_stuck(series: pd.Series, cfg: dict, interval: str = "hourly",
                skip_series: pd.Series | None = None,
                cur_flags: pd.Series | None = None,
                skip_flags: pd.Series | None = None) -> pd.DataFrame:
    """
    cfg 키: stuck.{interval}.suspect_count, fail_count, epsilon
            skip_below_col, skip_below_value (optional)
    cur_flags:  현재까지 누적된 flag — bad 값이 끼면 run 리셋
    skip_flags: skip_below_col 변수의 현재 flag — BAD이면 skip 무시
                (센서 고장으로 skip_col 자체가 BAD일 때 연동 변수도 검사)
    반환: DataFrame[flag(int), reason(str)]
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    profile = (cfg.get(interval)
               or cfg.get("hourly")
               or {})
    suspect_count = int(profile.get("suspect_count", 999))
    fail_count    = int(profile.get("fail_count",    999))
    epsilon       = float(cfg.get("epsilon", 0.0))
    skip_below_value = cfg.get("skip_below_value")

    vals = series.values.astype(float)
    n    = len(vals)

    flags_arr = None
    if cur_flags is not None:
        flags_arr = cur_flags.values

    skip_flags_arr = None
    if skip_flags is not None:
        skip_flags_arr = skip_flags.values

    def _is_bad(idx: int) -> bool:
        if flags_arr is None:
            return False
        return int(flags_arr[idx]) >= FLAG_BAD

    def _skip_col_is_bad(idx: int) -> bool:
        if skip_flags_arr is None:
            return False
        return int(skip_flags_arr[idx]) >= FLAG_BAD

    run_len = np.ones(n, dtype=int)
    for i in range(1, n):
        if missing.iloc[i]:
            run_len[i] = 1
            continue
        # 이전 값이 bad면 run 리셋 (bad가 끊는 역할)
        if _is_bad(i - 1):
            run_len[i] = 1
            continue
        if missing.iloc[i - 1]:
            run_len[i] = 1
            continue
        if skip_series is not None and skip_below_value is not None:
            sv = float(skip_series.iloc[i]) if not pd.isna(skip_series.iloc[i]) else 0.0
            # skip_col 자체가 BAD(센서 고장)이면 skip 면제를 적용하지 않음
            if sv < skip_below_value and not _skip_col_is_bad(i):
                run_len[i] = 1
                continue
        if abs(vals[i] - vals[i - 1]) <= epsilon:
            run_len[i] = run_len[i - 1] + 1
        else:
            run_len[i] = 1

    # 각 위치에 run 전체 길이를 역방향으로 전파:
    # run_len[i+1] == run_len[i]+1 이면 i는 같은 run에 속하므로 i+1의 값을 물려받음.
    max_run_len = run_len.copy()
    for i in range(n - 2, -1, -1):
        if run_len[i + 1] == run_len[i] + 1:
            max_run_len[i] = max_run_len[i + 1]

    # fail_count 이상인 run → 처음부터 끝까지 전부 bad
    # suspect_count 이상인 run → 처음부터 끝까지 전부 suspect
    for i in range(n):
        if missing.iloc[i]:
            continue
        total = int(max_run_len[i])
        if total < suspect_count:
            continue
        if total >= fail_count:
            result.iloc[i] = [FLAG_BAD,     f"stuck_fail(run={total})"]
        else:
            result.iloc[i] = [FLAG_SUSPECT, f"stuck_suspect(run={total})"]

    return result
