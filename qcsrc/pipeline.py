# -*- coding: utf-8-sig -*-
"""
QC 파이프라인 진입점.
전처리 → range → spike → stuck → roc → edge 순으로 단계별 실행.
각 단계의 flag를 DataFrame 열로 보존하고, 최종 flag를 severity 기준 최댓값으로 결합한다.

Severity 순위(수치 최대값이 최우선): MISSING(9) > BAD(3) > SUSPECT(2) > GOOD(1)
"""

import pandas as pd

from qcsrc import preprocess
from qcsrc.checks import range_check, spike_check, stuck_check, roc_check, edge_check


def run_pipeline(series: pd.Series, config: dict) -> pd.DataFrame:
    """
    전처리 → range → spike → stuck → roc → edge 순으로 실행.
    각 단계 flag를 열로 가진 DataFrame 반환.
    최종 flag는 가장 나쁜 값(severity 기준 max)으로 결합.

    Parameters
    ----------
    series : DatetimeIndex를 가진 원시 시계열
    config : 파이프라인 설정 dict

    config 키:
        resample_freq  : 리샘플 주기 문자열 (예: '1H')
        fill_method    : 보간 방법 ('linear' | 'ffill' | 'bfill')
        range   : dict(vmin, vmax)
        spike   : dict(method, threshold[, window])
        stuck   : dict(min_change, window)
        roc     : dict(max_rate)
        edge    : dict(gap_min, fwd_scan, n_start, abs_fail, abs_suspect)

    Returns
    -------
    DataFrame 컬럼:
        value, flag_range, flag_spike, flag_stuck, flag_roc, flag_edge, flag_final
    """
    # ------------------------------------------------------------------
    # 1. 전처리
    # ------------------------------------------------------------------
    s = series.copy()

    if "resample_freq" in config:
        s = preprocess.resample(s, config["resample_freq"])

    if "fill_method" in config:
        s = preprocess.fill_missing(s, config["fill_method"])

    # ------------------------------------------------------------------
    # 2. 각 QC 검사 단계 실행
    # ------------------------------------------------------------------
    results = pd.DataFrame({"value": s})

    results["flag_range"] = (
        range_check.run(s, **config["range"])
        if "range" in config
        else pd.Series(1, index=s.index, dtype=int)
    )

    results["flag_spike"] = (
        spike_check.run(s, **config["spike"])
        if "spike" in config
        else pd.Series(1, index=s.index, dtype=int)
    )

    results["flag_stuck"] = (
        stuck_check.run(s, **config["stuck"])
        if "stuck" in config
        else pd.Series(1, index=s.index, dtype=int)
    )

    results["flag_roc"] = (
        roc_check.run(s, **config["roc"])
        if "roc" in config
        else pd.Series(1, index=s.index, dtype=int)
    )

    results["flag_edge"] = (
        edge_check.run(s, **config["edge"])
        if "edge" in config
        else pd.Series(1, index=s.index, dtype=int)
    )

    # ------------------------------------------------------------------
    # 3. 최종 flag: severity 기준 최댓값 (수치 최대 = 가장 나쁨)
    # ------------------------------------------------------------------
    flag_cols = [c for c in results.columns if c.startswith("flag_")]
    results["flag_final"] = results[flag_cols].max(axis=1)

    return results
