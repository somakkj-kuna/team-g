# -*- coding: utf-8-sig -*-
"""
flag 파일 읽기·쓰기·초기화.

flag 파일 경로: src/tmp/flags/{agency}/{station_id}/{key}_flag.csv  (key=YYYYMM 또는 YYYYMMDD)
flag 컬럼 구조:
  time, agency, station_id, var_id, value, depth_m,
  flag_aqc1, reason_aqc1,   # AQC1: zero/range/dynamic_range/stuck/attenuated/spike(neighbor·tukey53h)/edge/consistency/cross
  flag_aqc2, reason_aqc2,   # AQC2: rolling 통계
  flag_mqc,  reason_mqc,    # MQC: 이벤트 기반 수동
  flag_final

설계 참고: 개별 검사(spike·attenuated·dynamic_range 등)는 별도 컬럼을 두지 않고
모두 해당 stage 컬럼(flag_aqc1 등)에 severity 최댓값으로 병합된다.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from src.libs.utils.config_loader import flags_dir

QC_ROOT  = Path(__file__).resolve().parents[3]
# FLAG_ROOT 는 실행 프로파일(QC_PROFILE)에 따라 flags/ 또는 flags_err/ 로 분기.
FLAG_ROOT = flags_dir()

FLAG_GOOD        = 1
FLAG_SUSPECT     = 2
FLAG_BAD         = 3
FLAG_INTERPOLATED = 4
FLAG_MISSING     = 9
FLAG_UNSET       = 0

SEVERITY = {
    FLAG_UNSET:        -1,
    FLAG_GOOD:          0,
    FLAG_SUSPECT:       1,
    FLAG_BAD:           2,
    FLAG_MISSING:       3,
    FLAG_INTERPOLATED:  0,
}

ALL_FLAG_COLS = [
    "flag_aqc1", "reason_aqc1",
    "flag_aqc2", "reason_aqc2",
    "flag_mqc",  "reason_mqc",
    "flag_final",
]


FLAG_INT_COLS = ["flag_aqc1", "flag_aqc2", "flag_mqc", "flag_final"]
FLAG_STR_COLS = ["reason_aqc1", "reason_aqc2", "reason_mqc"]


def flag_path(agency: str, station_id: str, key: str) -> Path:
    """key: YYYYMM(6자리) 또는 YYYYMMDD(8자리)"""
    return flags_dir() / agency / str(station_id) / f"{key}_flag.csv"


def load_flags(agency: str, station_id: str, key: str) -> pd.DataFrame:
    p = flag_path(agency, station_id, key)
    if not p.exists():
        return pd.DataFrame()
    df = pd.read_csv(p, encoding="utf-8-sig")
    for col in FLAG_INT_COLS:
        if col in df.columns:
            df[col] = df[col].fillna(0).astype(int)
    for col in FLAG_STR_COLS:
        if col in df.columns:
            df[col] = df[col].fillna("").astype(str)
    return df


def save_flags(df: pd.DataFrame, agency: str, station_id: str, key: str) -> None:
    p = flag_path(agency, station_id, key)
    p.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(p, index=False, encoding="utf-8-sig")


def init_flags(long_df: pd.DataFrame, station_id: str, agency: str) -> pd.DataFrame:
    """
    long format 관측 데이터로부터 초기 flag DataFrame 생성.
    결측(value=NaN)은 flag_aqc1=9(missing) 으로 초기화.
    """
    sub = long_df[
        (long_df["station_id"] == station_id) &
        (long_df["agency"] == agency)
    ].copy()

    keep = ["time", "agency", "station_id", "var_id", "value", "depth_m"]
    for c in keep:
        if c not in sub.columns:
            sub[c] = float("nan") if c in ("depth_m", "value") else ""

    flag_df = sub[keep].copy()

    flag_df["flag_aqc1"]  = FLAG_UNSET
    flag_df["reason_aqc1"] = ""
    flag_df["flag_aqc2"]  = FLAG_UNSET
    flag_df["reason_aqc2"] = ""
    flag_df["flag_mqc"]   = FLAG_UNSET
    flag_df["reason_mqc"]  = ""
    flag_df["flag_final"] = FLAG_UNSET

    missing_mask = flag_df["value"].isna()
    flag_df.loc[missing_mask, "flag_aqc1"]   = FLAG_MISSING
    flag_df.loc[missing_mask, "reason_aqc1"] = "missing"

    return flag_df.reset_index(drop=True)


def update_flags(flag_df: pd.DataFrame, stage: str,
                 updates: pd.DataFrame) -> pd.DataFrame:
    """
    특정 stage(aqc1/aqc2/mqc)의 flag·reason을 업데이트.
    updates 컬럼: time, var_id, flag, reason
    기존 값보다 severity가 높은 경우에만 덮어씀.
    """
    flag_col   = f"flag_{stage}"
    reason_col = f"reason_{stage}"

    flag_df = flag_df.copy()

    for _, row in updates.iterrows():
        mask = (
            (flag_df["time"]   == row["time"]) &
            (flag_df["var_id"] == row["var_id"])
        )
        if not mask.any():
            continue
        cur_flag = flag_df.loc[mask, flag_col].iloc[0]
        new_flag = int(row["flag"])
        if SEVERITY.get(new_flag, -1) > SEVERITY.get(cur_flag, -1):
            flag_df.loc[mask, flag_col]   = new_flag
            flag_df.loc[mask, reason_col] = str(row.get("reason", ""))

    return flag_df


def compute_final(flag_df: pd.DataFrame) -> pd.DataFrame:
    """
    flag_aqc1, flag_aqc2, flag_mqc 중 가장 심각한 값 → flag_final.
    UNSET(0) 행은 good(1)으로 확정.
    """
    flag_df = flag_df.copy()
    stages = ["flag_aqc1", "flag_aqc2", "flag_mqc"]

    def worst(row: pd.Series) -> int:
        vals = [int(row[s]) for s in stages if int(row[s]) != FLAG_UNSET]
        if not vals:
            return FLAG_GOOD
        return max(vals, key=lambda v: SEVERITY.get(v, -1))

    flag_df["flag_final"] = flag_df.apply(worst, axis=1)
    return flag_df
