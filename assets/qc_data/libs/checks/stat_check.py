# -*- coding: utf-8-sig -*-
from __future__ import annotations
import numpy as np
import pandas as pd
from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def check_rolling(series: pd.Series, cfg: dict,
                  time_index: pd.DatetimeIndex | None = None) -> pd.DataFrame:
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    })

    missing_arr = series.isna().values

    result.loc[missing_arr, "flag"]   = FLAG_MISSING
    result.loc[missing_arr, "reason"] = "missing"

    window      = cfg.get("window", "24h")
    suspect_sig = float(cfg.get("suspect_sigma", 3.0))
    fail_sig    = float(cfg.get("fail_sigma",    5.0))
    min_periods = int(cfg.get("min_periods", 6))
    min_std     = float(cfg.get("min_std", 0.0))
    n_iter      = int(cfg.get("iterations", 1))

    # 반복 sigma clipping: 이전 iteration에서 flagged된 값을 NaN으로 마스킹 후 재계산
    masked_vals = series.values.astype(float).copy()

    for _ in range(n_iter):
        if time_index is not None:
            ts = pd.Series(masked_vals, index=pd.to_datetime(time_index))
        else:
            ts = pd.Series(masked_vals, index=series.index)

        roll      = ts.rolling(window=window, center=True, min_periods=min_periods)
        roll_std  = roll.std().clip(lower=min_std)
        dev_arr   = ((ts - roll.mean()).abs() / roll_std).values

        valid        = ~missing_arr & ~np.isnan(dev_arr)
        fail_mask    = valid & (dev_arr >= fail_sig)
        suspect_mask = valid & (dev_arr >= suspect_sig) & ~fail_mask

        # 현재 flag 배열 (업데이트 판단용)
        cur_flags = result["flag"].values

        # BAD 업데이트: 아직 BAD/MISSING이 아닌 행만
        new_bad = fail_mask & (cur_flags != FLAG_BAD) & (cur_flags != FLAG_MISSING)
        result.loc[new_bad, "flag"] = FLAG_BAD
        if new_bad.any():
            result.loc[new_bad, "reason"] = [
                f"rolling_fail(dev={d:.2f}\u03c3)" for d in dev_arr[new_bad]
            ]

        # SUSPECT 업데이트: 아직 GOOD인 행만
        new_sus = suspect_mask & (cur_flags == FLAG_GOOD)
        result.loc[new_sus, "flag"] = FLAG_SUSPECT
        if new_sus.any():
            result.loc[new_sus, "reason"] = [
                f"rolling_suspect(dev={d:.2f}\u03c3)" for d in dev_arr[new_sus]
            ]

        # 다음 iteration을 위해 이번에 flagged된 값 NaN 마스킹
        masked_vals[fail_mask | suspect_mask] = float("nan")

    return result
