# -*- coding: utf-8-sig -*-
"""
경계(edge/gap) 검사.
데이터 공백(gap) 이후 복귀 구간 첫 n_start 값의 내부 일관성을 검사한다.
이전값(bwd) 참조 없이 복귀 직후 전방(fwd) 값끼리만 비교해 오탐을 최소화한다.
월 경계 오검출 방지 buffer는 상위 파이프라인에서 처리한다.
"""

import numpy as np
import pandas as pd
from qcsrc.checks import FLAG_BAD, FLAG_SUSPECT, _init_flags


def run(
    series: pd.Series,
    gap_min: str = "24h",
    fwd_scan: str = "48h",
    n_start: int = 3,
    abs_fail: float = 2.0,
    abs_suspect: float = 1.0,
    **kwargs,
) -> pd.Series:
    """
    갭(gap) 이후 복귀 구간 edge 검사.

    Parameters
    ----------
    series      : DatetimeIndex를 가진 시계열
    gap_min     : 이 시간 이상의 공백이어야 segment 시작으로 간주 (예: '24h')
    fwd_scan    : segment 시작값의 전방 참조 탐색 범위 (예: '48h')
    n_start     : segment 시작부에서 검사할 유효값 개수
    abs_fail    : 편차 이 이상 → BAD
    abs_suspect : 편차 이 이상 → SUSPECT (< abs_fail)
    """
    if not isinstance(series.index, pd.DatetimeIndex):
        raise TypeError("edge_check.run 은 DatetimeIndex 가 필요합니다.")

    flags = _init_flags(series)
    vals = series.values.astype(float)
    times = series.index
    n = len(vals)

    gap_td = pd.Timedelta(gap_min)
    fwd_td = pd.Timedelta(fwd_scan)

    # 유효 위치 목록 (NaN 제외)
    valid_idxs = [i for i in range(n) if not np.isnan(vals[i])]
    if not valid_idxs:
        return flags

    # segment 시작 위치 탐지:
    #   - 데이터셋 첫 유효값
    #   - 직전 유효값과 시간 차 >= gap_min인 위치
    segment_starts = [valid_idxs[0]]
    for k in range(1, len(valid_idxs)):
        prev_pos = valid_idxs[k - 1]
        curr_pos = valid_idxs[k]
        if (times[curr_pos] - times[prev_pos]) >= gap_td:
            segment_starts.append(curr_pos)

    for seg_i in segment_starts:
        # segment 시작부 첫 n_start 유효값을 후보로 수집
        candidates = []
        j = seg_i
        while len(candidates) < n_start and j < n:
            if not np.isnan(vals[j]):
                candidates.append(j)
            j += 1

        for ck in candidates:
            # 후보 직후 fwd_scan 이내의 다음 유효값 최대 2개 수집 (bwd 참조 없음)
            fwd_vals = []
            for fj in range(ck + 1, n):
                if (times[fj] - times[ck]) > fwd_td:
                    break
                if not np.isnan(vals[fj]):
                    fwd_vals.append(vals[fj])
                    if len(fwd_vals) >= 2:
                        break

            if not fwd_vals:
                continue  # 전방 참조 없으면 판정 불가

            ref = float(np.mean(fwd_vals))
            d = abs(vals[ck] - ref)

            if d >= abs_fail:
                flags.iloc[ck] = FLAG_BAD
            elif d >= abs_suspect and flags.iloc[ck] == 1:
                # 더 심각한 flag가 이미 있으면 덮어쓰지 않음
                flags.iloc[ck] = FLAG_SUSPECT

    return flags
