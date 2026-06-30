# -*- coding: utf-8-sig -*-
"""
Edge QC (AQC1)
gap_min 이상의 데이터 공백 이후 segment 시작 n_start개 값의 내부 일관성을 검사한다.

  a = 갭 이후 첫 번째(~n_start번째) 유효값
  b, c = a 이후 fwd_scan 시간 이내의 다음 유효값 (NaN/bad 건너뜀)
  ref  = mean(b, c)  — b만 있으면 b
  d    = |a - ref|

  d >= abs_fail    → BAD     edge_start_fail(d)
  d >= abs_suspect → SUSPECT edge_start_suspect(d)
  b, c 모두 없으면 skip
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def _parse_hours(val) -> float:
    s = str(val).strip().lower()
    if s.endswith("h"):
        return float(s[:-1])
    if s.endswith("d"):
        return float(s[:-1]) * 24.0
    return float(s)


def check_edge(series: pd.Series, cfg: dict,
               cur_flags: pd.Series | None = None,
               time_index: pd.Series | None = None) -> pd.DataFrame:
    """
    cfg 키:
      gap_min     (str,   기본 "24h") — 이 이상의 공백에서만 검사
      fwd_scan    (str,   기본 "48h") — b, c 탐색 전방 시간 창
      n_start     (int,   기본 3)     — segment 시작부 검사 개수
      abs_fail    (float, 필수)       — |a - ref| >= abs_fail → BAD
      abs_suspect (float, 선택)       — |a - ref| >= abs_suspect → SUSPECT
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    n = len(series)
    if n < 3 or time_index is None:
        return result

    abs_fail    = cfg.get("abs_fail", None)
    abs_suspect = cfg.get("abs_suspect", None)
    if abs_fail is None:
        return result
    abs_fail    = float(abs_fail)
    abs_suspect = float(abs_suspect) if abs_suspect is not None else None

    gap_min_sec  = _parse_hours(cfg.get("gap_min",  "24h")) * 3600.0
    fwd_scan_sec = _parse_hours(cfg.get("fwd_scan",
                    cfg.get("window", "48h"))) * 3600.0  # window는 하위 호환
    n_start      = int(cfg.get("n_start", 3))

    try:
        time_sec = (pd.to_datetime(time_index)
                    .values.astype("datetime64[ns]")
                    .view(np.int64) / 1e9)
    except Exception:
        return result

    vals      = series.values.astype(float)
    flags_arr = (cur_flags.values.astype(int)
                 if cur_flags is not None
                 else np.ones(n, dtype=int))

    def _usable(i: int) -> bool:
        return (not np.isnan(vals[i])
                and int(flags_arr[i]) not in (FLAG_BAD, FLAG_MISSING))

    # 유효 인덱스: gap 탐지에 사용
    valid_idx = [i for i in range(n) if _usable(i)]
    if len(valid_idx) < 2:
        return result

    # segment 시작 위치: 이전 유효값과 시간 차 >= gap_min 인 첫 유효값
    # (데이터셋 첫 번째 유효값도 포함 — 시작부 일관성 확인)
    seg_starts: list[int] = [valid_idx[0]]
    for k in range(1, len(valid_idx)):
        gap = time_sec[valid_idx[k]] - time_sec[valid_idx[k - 1]]
        if gap >= gap_min_sec:
            seg_starts.append(valid_idx[k])

    checked: set[int] = set()  # 동일 위치 중복 검사 방지

    for seg_start in seg_starts:
        # segment 내 첫 n_start개 유효값 수집
        to_check: list[int] = []
        for i in range(seg_start, n):
            if _usable(i):
                to_check.append(i)
                if len(to_check) == n_start:
                    break
            # 다음 유효값까지 또 다른 큰 갭이 있으면 새 segment로 처리되므로 중단
            if (to_check
                    and not np.isnan(vals[i])
                    and i != to_check[-1]
                    and (time_sec[i] - time_sec[to_check[-1]]) >= gap_min_sec):
                break

        for idx in to_check:
            if idx in checked:
                continue
            checked.add(idx)

            # b, c 탐색: idx+1부터 fwd_scan_sec 이내의 usable 값 최대 2개
            found: list[float] = []
            for j in range(idx + 1, n):
                dt = time_sec[j] - time_sec[idx]
                if dt > fwd_scan_sec:
                    break
                if _usable(j):
                    found.append(float(vals[j]))
                    if len(found) == 2:
                        break

            if not found:
                continue

            ref = float(np.mean(found))
            d   = abs(float(vals[idx]) - ref)

            if d >= abs_fail:
                result.iloc[idx] = [FLAG_BAD, f"edge_start_fail({d:.2f})"]
                flags_arr[idx] = FLAG_BAD
            elif abs_suspect is not None and d >= abs_suspect:
                result.iloc[idx] = [FLAG_SUSPECT, f"edge_start_suspect({d:.2f})"]
                flags_arr[idx] = FLAG_SUSPECT

    return result
