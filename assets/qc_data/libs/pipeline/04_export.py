#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
04_export.py — 최종 CSV 저장

출력 ①  result/flag/{agency}/{station_id}/{yyyy}/{agency}_{station_id}_{yyyy}_qc_flag.csv
출력 ②  result/final/{agency}/{station_id}/{yyyy}/{agency}_{station_id}_{yyyy}_qc_final.csv

  컬럼 ①: time, agency, station_id, lat, lon, var_id, value, depth_m,
           flag_final, flag_aqc1, reason_aqc1, flag_aqc2, reason_aqc2, flag_mqc, reason_mqc
  컬럼 ②: time, agency, station_id, lat, lon, var_id, value  (flag_final==1,2 행)

월별로 반복 호출되며 연간 파일에 누적된다.
  - 연간 파일이 없으면 생성
  - 이미 있으면 해당 월(또는 일)에 해당하는 기존 행을 제거한 뒤 새 데이터를 추가
    → 동일 기간 재실행 시 새 결과로 덮어씌워짐

사용법:
  python src/pipeline/04_export.py --agency khoa --dataset tidal --yyyymm 202501
  python src/pipeline/04_export.py --agency khoa --dataset tidal --year 2025   # 하위 호환용 no-op
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

QC_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QC_ROOT))

from src.libs.utils.flag_io import load_flags, save_flags, compute_final
from src.libs.utils.config_loader import result_dir, sorted_dir

# 실행 프로파일(QC_PROFILE)에 따라 result/ 또는 err_result/ 로 분기.
FLAG_ROOT  = result_dir() / "flag"
FINAL_ROOT = result_dir() / "final"

CSV_COLUMNS = [
    "time", "agency", "station_id", "lat", "lon",
    "var_id", "value", "depth_m",
    "flag_final", "flag_aqc1", "reason_aqc1",
    "flag_aqc2", "reason_aqc2", "flag_mqc", "reason_mqc",
]

FINAL_COLUMNS_BASE  = ["time", "agency", "station_id", "lat", "lon", "var_id", "value"]
FINAL_COLUMNS_DEPTH = ["time", "agency", "station_id", "lat", "lon", "var_id", "value", "depth_m"]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",  required=True)
    p.add_argument("--dataset", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--yyyymm",   help="단월 처리 (YYYYMM)")
    g.add_argument("--yyyymmdd", help="일별 처리 (YYYYMMDD)")
    g.add_argument("--year",     help="하위 호환용 — 이 모드는 no-op (연간 파일은 월별 처리 시 자동 생성)")
    p.add_argument("--station", default=None)
    return p.parse_args()


def _merge_into_annual(annual_path: Path, new_df: pd.DataFrame,
                       time_prefix: str) -> None:
    """연간 파일에 새 데이터를 월(또는 일) 단위로 병합한다.
    - 파일 없음 → 그대로 저장
    - 파일 있음 → 해당 기간(time_prefix) 기존 행 제거 → 새 데이터 추가 → 정렬 저장
    """
    if annual_path.exists():
        existing = pd.read_csv(annual_path, dtype=str)
        existing = existing[~existing["time"].str.startswith(time_prefix)]
        combined = pd.concat([existing, new_df], ignore_index=True)
        combined = combined.sort_values(["var_id", "time"]).reset_index(drop=True)
        combined.to_csv(annual_path, index=False, encoding="utf-8-sig")
    else:
        new_df.to_csv(annual_path, index=False, encoding="utf-8-sig")


def run_station(station_id: str, agency: str, yyyymm: str,
                sorted_df: pd.DataFrame,
                key: str | None = None) -> None:
    flag_df = load_flags(agency, station_id, key if key else yyyymm)
    if flag_df.empty:
        print(f"  [export] {station_id}: flag 없음 — 건너뜀")
        return

    flag_df = compute_final(flag_df)

    # lat/lon 보강
    sorted_df = sorted_df.copy()
    sorted_df["station_id"] = sorted_df["station_id"].astype(str)
    flag_df["station_id"]   = flag_df["station_id"].astype(str)
    meta = (sorted_df[sorted_df["station_id"] == station_id]
            [["station_id", "lat", "lon"]]
            .drop_duplicates("station_id"))
    if not meta.empty:
        flag_df = flag_df.merge(meta, on="station_id", how="left",
                                suffixes=("", "_meta"))
        if "lat_meta" in flag_df.columns:
            flag_df["lat"] = flag_df["lat_meta"]
            flag_df["lon"] = flag_df["lon_meta"]
            flag_df = flag_df.drop(columns=["lat_meta", "lon_meta"])

    for col in CSV_COLUMNS:
        if col not in flag_df.columns:
            flag_df[col] = ""

    out_df = flag_df[CSV_COLUMNS].copy()
    out_df["time"] = pd.to_datetime(out_df["time"]).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    out_df = out_df.sort_values(["var_id", "time"]).reset_index(drop=True)

    yyyy = yyyymm[:4]
    mm   = yyyymm[4:6]
    is_daily = key is not None and len(str(key)) == 8
    if is_daily:
        dd = str(key)[6:8]
        time_prefix = f"{yyyy}-{mm}-{dd}"
    else:
        time_prefix = f"{yyyy}-{mm}-"

    # ① flag 파일 (연간 단일 파일)
    flag_dir  = FLAG_ROOT / agency / str(station_id) / yyyy
    flag_dir.mkdir(parents=True, exist_ok=True)
    flag_fname = f"{agency}_{station_id}_{yyyy}_qc_flag.csv"
    flag_path  = flag_dir / flag_fname

    # 경계 데이터 제거: sorted 파일에 포함된 인접 월 행은 저장하지 않음
    out_df_curr = out_df[out_df["time"].str.startswith(time_prefix)].copy()
    _merge_into_annual(flag_path, out_df_curr, time_prefix)

    good    = (out_df_curr["flag_final"].astype(int) == 1).sum()
    suspect = (out_df_curr["flag_final"].astype(int) == 2).sum()
    bad     = (out_df_curr["flag_final"].astype(int) == 3).sum()
    miss    = (out_df_curr["flag_final"].astype(int) == 9).sum()
    print(f"  [export] {station_id} → {flag_fname}  "
          f"good={good} suspect={suspect} bad={bad} missing={miss}")

    # ② final 파일 (flag_final==1,2 행)
    final_src = out_df_curr[out_df_curr["flag_final"].astype(int).isin([1, 2])].copy()
    has_depth = (
        "depth_m" in final_src.columns
        and pd.to_numeric(final_src["depth_m"], errors="coerce").notna().any()
    )
    final_cols = FINAL_COLUMNS_DEPTH if has_depth else FINAL_COLUMNS_BASE
    for col in final_cols:
        if col not in final_src.columns:
            final_src[col] = ""
    final_df = final_src[final_cols].copy()

    final_dir  = FINAL_ROOT / agency / station_id / yyyy
    final_dir.mkdir(parents=True, exist_ok=True)
    final_fname = f"{agency}_{station_id}_{yyyy}_qc_final.csv"
    final_path  = final_dir / final_fname

    _merge_into_annual(final_path, final_df, time_prefix)
    kept = len(final_df)
    print(f"  [export] {station_id} → {final_fname}  good+suspect={kept}행")


def run(agency: str, dataset: str, yyyymm: str,
        station_filter: str | None = None,
        yyyymmdd: str | None = None) -> None:
    key        = yyyymmdd if yyyymmdd else yyyymm
    out_yyyymm = yyyymmdd[:6] if yyyymmdd else yyyymm

    yyyymm_key  = key[:6]
    sorted_path = (sorted_dir() / dataset
                   / f"{agency}_{yyyymm_key}.csv")
    if not sorted_path.exists():
        print(f"[skip] sorted 파일 없음: {sorted_path} — 유효 데이터 없음")
        return

    df = pd.read_csv(sorted_path, dtype={"station_id": str})
    # 일별 처리일 때만 해당 일자로 추가 필터
    if len(key) == 8:
        _prefix = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
        df = df[df["time"].str.startswith(_prefix)].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    stations = df["station_id"].unique().tolist()
    if station_filter:
        stations = [s for s in stations if s == station_filter]

    label = yyyymmdd if yyyymmdd else yyyymm
    print(f"[export] {agency}/{dataset}/{label}  {len(stations)}개 관측소")
    for stn in stations:
        run_station(stn, agency, out_yyyymm, df, key)

    # 내보내기 완료 후 tmp flags 삭제
    from src.libs.utils.flag_io import flag_path
    for stn in stations:
        fp = flag_path(agency, stn, key)
        if fp.exists():
            fp.unlink()


if __name__ == "__main__":
    args = parse_args()
    if args.year:
        # 하위 호환용: 월별 처리 시 이미 연간 파일이 완성되므로 no-op
        print(f"[export] --year {args.year} — 연간 파일은 월별 처리 시 자동 완성됨. skip.")
    elif args.yyyymmdd:
        run(args.agency, args.dataset, args.yyyymmdd[:6],
            args.station, args.yyyymmdd)
    else:
        run(args.agency, args.dataset, args.yyyymm, args.station)
