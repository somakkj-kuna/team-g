#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
06_clean_export.py — 분석용 clean CSV 저장
flag 컬럼 없이 QC 통과 데이터만 저장.
입력: result/flag/{agency}/{station_id}/{yyyy}/{yyyymm}_flag.csv
출력: result/final/{agency}/{station_id}/{yyyy}/{yyyymm}_final.csv

포함 기준 (--mode 로 선택):
  good     : flag_final == 1 만 포함 (기본값)
  suspect  : flag_final == 1 또는 2 포함

출력 컬럼:
  time, agency, station_id, lat, lon, var_id, value, depth_m

사용법:
  python src/pipeline/06_clean_export.py --agency khoa --dataset tidal --yyyymm 202501
  python src/pipeline/06_clean_export.py --agency khoa --dataset tidal --yyyymm 202501 --mode suspect
  python src/pipeline/06_clean_export.py --agency khoa --dataset tidal --yyyymm 202501 --station DT_0001
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

QC_ROOT    = Path(__file__).resolve().parents[3]
FLAG_ROOT  = QC_ROOT / "result" / "flag"
FINAL_ROOT = QC_ROOT / "result" / "final"
sys.path.insert(0, str(QC_ROOT))

CLEAN_COLUMNS = ["time", "agency", "station_id", "lat", "lon", "var_id", "value"]

MODE_FLAGS = {
    "good":    [1],
    "suspect": [1, 2],
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",  required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--yyyymm",  required=True)
    p.add_argument("--station", default=None)
    p.add_argument("--mode",    default="suspect",
                   choices=["good", "suspect"],
                   help="good=flag1만, suspect=flag1+2 포함 (기본값: suspect)")
    return p.parse_args()


def run_station(station_id: str, agency: str, yyyymm: str,
                mode: str) -> None:
    yyyy     = yyyymm[:4]
    qc_path  = FLAG_ROOT / agency / station_id / yyyy / f"{agency}_{station_id}_{yyyymm}_qc_flag.csv"
    if not qc_path.exists():
        print(f"  [clean] {station_id}: qc 파일 없음 — 건너뜀")
        return

    df = pd.read_csv(qc_path)
    df["flag_final"] = pd.to_numeric(df["flag_final"], errors="coerce").fillna(0).astype(int)

    keep_flags = MODE_FLAGS[mode]
    clean_df = df[df["flag_final"].isin(keep_flags)].copy()

    # flag 컬럼 제거, 분석 컬럼만 유지
    for col in CLEAN_COLUMNS:
        if col not in clean_df.columns:
            clean_df[col] = ""

    clean_df = clean_df[CLEAN_COLUMNS].reset_index(drop=True)

    total    = len(df)
    kept     = len(clean_df)
    dropped  = total - kept

    out_dir  = FINAL_ROOT / agency / station_id / yyyy
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{agency}_{station_id}_{yyyymm}_qc_final.csv"
    clean_df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"  [clean] {station_id} → {out_path.name}  "
          f"유지 {kept}/{total}  제거 {dropped}  (mode={mode})")


def run(agency: str, dataset: str, yyyymm: str,
        station_filter: str | None = None,
        mode: str = "good") -> None:
    yyyy = yyyymm[:4]

    # 해당 agency/*/yyyy 아래의 qc 파일 목록으로 대상 관측소 파악
    agency_dir = FLAG_ROOT / agency
    if not agency_dir.exists():
        raise FileNotFoundError(f"결과 폴더 없음: {agency_dir}")

    stations = sorted([
        d.name for d in agency_dir.iterdir()
        if d.is_dir() and (d / yyyy / f"{agency}_{d.name}_{yyyymm}_qc_flag.csv").exists()
    ])

    if station_filter:
        stations = [s for s in stations if s == station_filter]
        if not stations:
            raise ValueError(f"관측소 {station_filter} 없음 또는 qc 파일 미생성")

    print(f"[clean] {agency}/{dataset}/{yyyymm}  {len(stations)}개 관측소  (mode={mode})")
    for stn in stations:
        run_station(stn, agency, yyyymm, mode)


if __name__ == "__main__":
    args = parse_args()
    run(args.agency, args.dataset, args.yyyymm, args.station, args.mode)
