# -*- coding: utf-8-sig -*-
"""
일관성 검사 (AQC1) — 연동 변수 간 물리적 일관성 확인

cfg 키:
    propagate_bad            (bool)  — 참조 변수가 BAD이면 대상도 BAD
    ref_zero_threshold       (float) — 참조 값 < 임계값 = "정온 / 영값"
    target_nonzero_threshold (float) — 대상 값 > 임계값 = "비정상 양수"

사용 사례:
    wind_dir  ← wind_speed: propagate_bad=true
    wind_gust ← wind_speed: propagate_bad=true + ref_zero/target_nonzero
"""

from __future__ import annotations

import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def check_consistency(series: pd.Series, cfg: dict,
                      ref_series: pd.Series,
                      ref_flags: pd.Series) -> pd.DataFrame:
    """
    반환: DataFrame[flag(int8), reason(str)]
    """
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    propagate_bad      = cfg.get("propagate_bad", False)
    propagate_level    = cfg.get("propagate_level", "bad")   # "bad" | "suspect"
    propagate_flag     = FLAG_SUSPECT if propagate_level == "suspect" else FLAG_BAD
    propagate_label    = "consistency_suspect" if propagate_level == "suspect" else "consistency_fail"
    ref_zero_thr       = cfg.get("ref_zero_threshold")
    target_nonzero_thr = cfg.get("target_nonzero_threshold")

    for i in range(len(series)):
        if pd.isna(series.iloc[i]):
            continue

        ref_val  = None if pd.isna(ref_series.iloc[i]) else float(ref_series.iloc[i])
        ref_flag = int(ref_flags.iloc[i]) if not pd.isna(ref_flags.iloc[i]) else FLAG_GOOD

        # 규칙 1: 참조 변수 BAD → 대상을 propagate_level 등급으로 (MISSING 제외)
        if propagate_bad and FLAG_BAD <= ref_flag < FLAG_MISSING:
            result.iloc[i] = [propagate_flag, f"{propagate_label}(ref=bad)"]
            continue

        # 규칙 2: 참조 ≈ 0 인데 대상이 양수 → SUSPECT
        if (ref_zero_thr is not None and target_nonzero_thr is not None
                and ref_val is not None):
            if ref_val < ref_zero_thr and float(series.iloc[i]) > target_nonzero_thr:
                result.iloc[i] = [
                    FLAG_SUSPECT,
                    f"consistency_suspect(ref={ref_val:.2g}<{ref_zero_thr}, val={float(series.iloc[i]):.2g}>{target_nonzero_thr})",
                ]

    return result
