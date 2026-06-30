#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
00_sort.py — 정렬·표준화 단계
raw CSV(monthly) → 월별(또는 일별) 표준화 long format CSV 로 변환.

사용법:
  python src/pipeline/00_sort.py --agency khoa --dataset tidal --yyyymm 202501     # 월별
  python src/pipeline/00_sort.py --agency khoa --dataset tidal --yyyymmdd 20260618 # 일별
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import pandas as pd

QC_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QC_ROOT))

from src.libs.utils.loader import (
    load_and_standardize,
    load_month_raw,
    standardize,
    apply_depth_mapping_nifs,
    derive_uv_components,
    _load_rules,
)
from src.libs.utils.config_loader import get_dataset_path, sorted_dir


def _date_range_env() -> tuple[str, str] | None:
    """환경변수 QC_RANGE_START/END(YYYYMMDD)로 일단위 범위 트리밍 여부 반환."""
    rs = os.environ.get("QC_RANGE_START", "").strip()
    re_ = os.environ.get("QC_RANGE_END", "").strip()
    if len(rs) == 8 and len(re_) == 8:
        return rs, re_
    return None


def _sorted_output_path(dataset: str, agency: str, key: str) -> Path:
    """key = yyyymm(6) 또는 yyyymmdd(8) — yyyymm(월별) 파일 반환.
    실행 프로파일(QC_PROFILE)에 따라 sorted/ 또는 sorted_err/ 로 분기."""
    yyyymm = key[:6]
    return sorted_dir() / dataset / f"{agency}_{yyyymm}.csv"


def _time_prefix(key: str) -> str:
    """key로부터 시간 문자열 필터 prefix 반환.
    yyyymm   → "YYYY-MM-"
    yyyymmdd → "YYYY-MM-DD"
    """
    if len(key) == 8:
        return f"{key[:4]}-{key[4:6]}-{key[6:8]}"
    return f"{key[:4]}-{key[4:6]}-"


def _has_period_data(out_path: Path, prefix: str) -> bool:
    """월별 파일이 존재하면 skip. 일별(prefix=YYYY-MM-DD)은 파일 내부 확인."""
    if not out_path.exists() or out_path.stat().st_size == 0:
        return False
    if len(prefix) <= 8:   # "YYYY-MM-" → 월별 → 파일 존재만으로 충분
        return True
    for chunk in pd.read_csv(out_path, usecols=["time"], chunksize=200_000,
                              encoding="utf-8-sig"):
        if chunk["time"].astype(str).str.startswith(prefix).any():
            return True
    return False


def _merge_day_into_monthly(out_path: Path, new_df: pd.DataFrame,
                               prefix: str) -> pd.DataFrame:
    """월별 파일에서 해당 일 기존 행을 제거하고 새 데이터를 추가 (일별 처리용)."""
    if not out_path.exists() or out_path.stat().st_size == 0:
        return new_df
    old_df = pd.read_csv(out_path, encoding="utf-8-sig", dtype={"station_id": str})
    old_df = old_df[~old_df["time"].astype(str).str.startswith(prefix)]
    return pd.concat([old_df, new_df], ignore_index=True)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",   required=True, help="khoa | nifs | kma")
    p.add_argument("--dataset",  required=True, help="tidal | buoy")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--yyyymm",   help="월별 처리 (예: 202501)")
    g.add_argument("--yyyymmdd", help="일별 처리 (예: 20260618)")
    return p.parse_args()


def _load_day(prc_path: str, yyyymmdd: str, agency: str,
              dataset: str | None = None) -> pd.DataFrame:
    """단일 일별 데이터 로드·표준화 (raw CSV 전용)."""
    yyyymm   = yyyymmdd[:6]
    yyyy     = yyyymmdd[:4]
    rules    = _load_rules()

    df = load_month_raw(prc_path, yyyymm, dataset, agency)
    df = standardize(df, rules, remap=False)
    df = apply_depth_mapping_nifs(df)
    df = derive_uv_components(df)

    day_start = pd.Timestamp(f"{yyyy}-{yyyymm[4:6]}-{yyyymmdd[6:8]}", tz="UTC")
    day_end   = day_start + pd.Timedelta(days=1)
    df = df[(df["time"] >= day_start) & (df["time"] < day_end)].copy()

    df = df.dropna(subset=["var_id"])
    df = df.sort_values(["station_id", "var_id", "time"]).reset_index(drop=True)
    return df


def run(agency: str, dataset: str,
        yyyymm: str | None = None, yyyymmdd: str | None = None) -> None:
    prc_path = get_dataset_path(agency, dataset)
    if not prc_path:
        raise ValueError(f"config/agencies/{agency}.toml 에 {dataset} 경로 없음")

    key    = yyyymmdd if yyyymmdd else yyyymm
    label  = yyyymmdd if yyyymmdd else yyyymm
    prefix = _time_prefix(key)

    out_path = _sorted_output_path(dataset, agency, key)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    date_range = _date_range_env()

    # 해당 기간 데이터가 이미 있으면 건너뜀.
    # 단, 일단위 범위 모드(QC_RANGE_*)는 트리밍 결과를 새로 써야 하므로 강제 재생성.
    if date_range is None and _has_period_data(out_path, prefix):
        print(f"[sort] 건너뜀: {prefix}* 데이터 이미 존재 ({out_path.name})")
        return

    print(f"[sort] {agency}/{dataset}/{label} 로드 중...")

    if yyyymmdd:
        df = _load_day(prc_path, yyyymmdd, agency, dataset=dataset)
    else:
        df = load_and_standardize(prc_path, yyyymm, agency=agency, dataset=dataset)

    if df.empty:
        print(f"[sort] 경고: {agency}/{dataset}/{label} 신규 데이터 없음")
        return

    # 유효하지 않은 station_id 행 제거
    # khoa: DT_0001 형식 / kma: 숫자형(955) / nifs: 소문자알파뉴메릭(bbbi5)
    _SID_PATTERNS = {
        "khoa": r"^[A-Za-z]{2,3}_[0-9]{4,}$",
        "kma":  r"^[0-9]+$",
        "nifs": r"^[a-z0-9]{4,}$",
    }
    sid_pattern = _SID_PATTERNS.get(agency, r"^[A-Za-z0-9_]{2,}$")
    before_filter = len(df)
    sid = df["station_id"].astype(str)
    valid_mask = df["station_id"].notna() & sid.str.match(sid_pattern)
    df = df[valid_mask]
    dropped = before_filter - len(df)
    if dropped > 0:
        print(f"[sort] 비정상 station_id {dropped}행 제거")

    if df.empty:
        print(f"[sort] 경고: {agency}/{dataset}/{label} 유효 데이터 없음")
        return

    df["time"] = pd.to_datetime(df["time"], utc=True).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    # 현재 기간에 해당하는 행만 저장 (인접 월 경계 데이터 제외)
    df = df[df["time"].str.startswith(prefix)]

    # 일단위 범위 모드: 시작일~종료일(YYYYMMDD) 밖의 일자 제거
    if date_range is not None:
        rs, re_ = date_range
        daykey = df["time"].str.slice(0, 10).str.replace("-", "", regex=False)
        before_rng = len(df)
        df = df[(daykey >= rs) & (daykey <= re_)]
        print(f"[sort] 일단위 범위 트리밍 {rs}~{re_}: {before_rng}→{len(df)}행")
        if df.empty:
            print(f"[sort] 경고: {label} 범위({rs}~{re_}) 내 데이터 없음 — 저장 건너뜀")
            return

    before = len(df)
    df = df.drop_duplicates(subset=["station_id", "var_id", "time"], keep="first")
    dup_count = before - len(df)
    if dup_count > 0:
        print(f"[sort] 중복 {dup_count}행 제거")

    # 월별 파일로 저장 (일별이면 기존 행과 merge)
    if yyyymmdd:
        df = _merge_day_into_monthly(out_path, df, prefix)
    df = df.sort_values(["station_id", "var_id", "time"]).reset_index(drop=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")

    print(f"[sort] 저장: {out_path}  ({len(df)}행, "
          f"{df['station_id'].nunique()}개 관측소, "
          f"{df['var_id'].nunique()}개 변수)")


if __name__ == "__main__":
    args = parse_args()
    run(args.agency, args.dataset, args.yyyymm, args.yyyymmdd)
