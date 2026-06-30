#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
02_aqc2.py — 2차 자동 QC (AQC2)
rolling 통계 기반 이상치 검사.
AQC1 flag가 없는(good/suspect) 행에만 적용.
입력: src/tmp/sorted + src/tmp/flags/{agency}/{station_id}/{key}_flag.csv
출력: flag 파일의 flag_aqc2, reason_aqc2 컬럼 갱신

사용법:
  python src/pipeline/02_aqc2.py --agency khoa --dataset tidal --yyyymm 202501
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

QC_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QC_ROOT))

from src.libs.utils.flag_io import (
    FLAG_GOOD, FLAG_SUSPECT, FLAG_BAD, FLAG_MISSING,
    load_flags, save_flags, SEVERITY,
)
from src.libs.utils.config_loader import get_var_cfg, load_rules, result_dir, sorted_dir
from src.libs.checks.stat_check import check_rolling

# 연간 flag CSV 캐시 (station_id×year 당 1회만 읽기)
_CSV_CACHE: dict[str, pd.DataFrame | None] = {}


def _adj_ym(yyyymm: str, delta: int) -> str:
    """yyyymm에서 delta개월 이동한 yyyymm 반환 (음수=이전, 양수=이후)."""
    y, mo = int(yyyymm[:4]), int(yyyymm[4:])
    mo += delta
    while mo <= 0:
        mo += 12; y -= 1
    while mo > 12:
        mo -= 12; y += 1
    return f"{y}{mo:02d}"


def _load_one_month_df(agency: str, station_id: str, dataset: str,
                       yyyymm: str) -> tuple[pd.DataFrame | None, bool]:
    """한 달치 raw DataFrame 로드 (flag CSV 우선, sorted CSV 대체).
    반환: (df, has_flag) — var 필터·시간 trim 없는 원본."""
    year = int(yyyymm[:4])
    csv_path = (result_dir() / "flag" / agency / str(station_id)
                / str(year) / f"{agency}_{station_id}_{year}_qc_flag.csv")
    pq_path  = (sorted_dir() / dataset
                / f"{agency}_{yyyymm}.csv")

    if csv_path.exists():
        try:
            cache_key = str(csv_path)
            if cache_key not in _CSV_CACHE:
                raw = pd.read_csv(csv_path, encoding="utf-8-sig",
                                  usecols=["time", "var_id", "value", "flag_aqc1"])
                raw["time"] = pd.to_datetime(raw["time"], utc=True, errors="coerce")
                _CSV_CACHE[cache_key] = raw
            cached = _CSV_CACHE[cache_key]
            if cached is not None:
                _mm = int(yyyymm[4:6])
                df = cached[(cached["time"].dt.year == year) & (cached["time"].dt.month == _mm)].copy()
                return df, True
        except Exception:
            pass

    if pq_path.exists():
        try:
            raw = pd.read_csv(pq_path, usecols=["time", "station_id", "var_id", "value"],
                              dtype={"station_id": str})
            raw["time"] = pd.to_datetime(raw["time"], utc=True)
            return raw[raw["station_id"] == station_id].copy(), False
        except Exception:
            pass

    return None, False


def _load_var_buffer(agency: str, station_id: str, dataset: str,
                     var: str, yyyymm: str | list, hours: float,
                     from_tail: bool) -> tuple | None:
    """인접 월(들) 변수 자료를 rolling buffer로 로드.
    yyyymm: 단일 월 문자열 또는 월 리스트 (리스트일 때 합산 후 trim).
    from_tail=True: 끝 hours시간 / False: 앞 hours시간
    반환: (series, flag_series, time_series) or None
    """
    months = [yyyymm] if isinstance(yyyymm, str) else yyyymm

    frames, has_flag = [], False
    for ym in months:
        df, hf = _load_one_month_df(agency, station_id, dataset, ym)
        if df is not None and not df.empty:
            frames.append(df)
            if hf:
                has_flag = True

    if not frames:
        return None

    combined = pd.concat(frames, ignore_index=True)
    sub = combined[combined["var_id"] == var].copy()
    if sub.empty:
        return None

    sub["time"] = pd.to_datetime(sub["time"], utc=True)
    sub = (sub.sort_values("time")
              .drop_duplicates(subset=["time"])
              .reset_index(drop=True))

    td = pd.Timedelta(hours=hours)
    if from_tail:
        sub = sub[sub["time"] > sub["time"].iloc[-1] - td]
    else:
        sub = sub[sub["time"] <= sub["time"].iloc[0] + td]

    if sub.empty:
        return None

    series = pd.to_numeric(sub["value"], errors="coerce").reset_index(drop=True)
    flags  = (sub["flag_aqc1"].fillna(FLAG_GOOD).astype("int8").reset_index(drop=True)
              if has_flag else pd.Series([FLAG_GOOD] * len(sub), dtype="int8"))
    times  = sub["time"].reset_index(drop=True)

    return series, flags, times


def _parse_window_hours(win_str: str) -> float:
    s = str(win_str).strip().lower()
    if s.endswith("h"):
        return float(s[:-1])
    if s.endswith("d"):
        return float(s[:-1]) * 24.0
    return float(s)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",  required=True)
    p.add_argument("--dataset", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--yyyymm",   help="월별 처리 (YYYYMM)")
    g.add_argument("--yyyymmdd", help="일별 처리 (YYYYMMDD)")
    p.add_argument("--station", default=None)
    return p.parse_args()


def run_station(station_id: str, agency: str, dataset: str, key: str) -> None:
    flag_df = load_flags(agency, station_id, key)
    if flag_df.empty:
        print(f"  [aqc2] {station_id}: flag 파일 없음 (01_aqc1 선행 필요)")
        return

    flag_df = flag_df.copy()

    ym = key[:6]
    prev_ym  = _adj_ym(ym, -1)
    prev_ym2 = _adj_ym(ym, -2)
    next_ym  = _adj_ym(ym, +1)
    next_ym2 = _adj_ym(ym, +2)

    for var in flag_df["var_id"].unique():
        mask = flag_df["var_id"] == var
        sub  = flag_df[mask].copy().sort_values("time").reset_index(drop=True)

        cfg     = get_var_cfg(var, agency, station_id)
        enabled = cfg.get("enabled_tests", {})

        if not enabled.get("rolling", False):
            continue

        rolling_cfg = cfg.get("rolling", {})
        if not rolling_cfg:
            print(f"  [aqc2] {station_id}/{var}: rolling 활성화되어 있으나 config 섹션 없음 — skip")
            continue
        win_hours   = _parse_window_hours(rolling_cfg.get("window", "744h"))
        buf_hours   = win_hours / 2.0  # centered rolling → 양쪽 절반씩 필요

        # 인접 월 buffer 로드
        prev_buf = _load_var_buffer(agency, station_id, dataset, var,
                                    [prev_ym, prev_ym2], buf_hours, from_tail=True)
        next_buf = _load_var_buffer(agency, station_id, dataset, var,
                                    [next_ym, next_ym2], buf_hours, from_tail=False)

        # [prev_buf] + [현재 월] + [next_buf] 결합
        parts_s = [sub["value"].reset_index(drop=True)]
        parts_f = [sub["flag_aqc1"].reset_index(drop=True)]
        parts_t = [pd.Series(pd.to_datetime(sub["time"], utc=True).values)]
        n_prev  = 0

        if prev_buf is not None:
            ps, pf, pt = prev_buf
            n_prev = len(ps)
            parts_s.insert(0, ps)
            parts_f.insert(0, pf)
            parts_t.insert(0, pd.Series(pt.values))

        if next_buf is not None:
            ns, nf, nt = next_buf
            parts_s.append(ns)
            parts_f.append(nf)
            parts_t.append(pd.Series(nt.values))

        combined_s = pd.concat(parts_s, ignore_index=True)
        combined_f = pd.concat(parts_f, ignore_index=True)
        combined_t = pd.concat(parts_t, ignore_index=True)

        # AQC1 BAD/MISSING → NaN (rolling 창 오염 방지)
        exclude = combined_f.isin([FLAG_BAD, FLAG_MISSING])
        combined_s_masked = combined_s.copy()
        combined_s_masked.loc[exclude] = float("nan")

        r_combined = check_rolling(combined_s_masked, rolling_cfg,
                                   pd.DatetimeIndex(pd.to_datetime(combined_t)))

        # 현재 월 해당 행만 추출
        r_curr = r_combined.iloc[n_prev : n_prev + len(sub)].reset_index(drop=True)

        # 벡터화: severity 비교 후 일괄 업데이트
        orig_idx  = flag_df[mask].sort_values("time").index  # sub와 동일 시간 순서
        valid     = ~sub["flag_aqc1"].isin([FLAG_BAD, FLAG_MISSING]).values
        new_sev   = r_curr["flag"].map(lambda f: SEVERITY.get(f, -1)).values
        cur_sev   = flag_df.loc[orig_idx, "flag_aqc2"].map(lambda f: SEVERITY.get(f, -1)).values
        upd       = valid & (new_sev > cur_sev)
        if upd.any():
            flag_df.loc[orig_idx[upd], "flag_aqc2"]   = r_curr["flag"].values[upd]
            flag_df.loc[orig_idx[upd], "reason_aqc2"] = r_curr["reason"].values[upd]

    # unset → good
    unset = flag_df["flag_aqc2"] == 0
    flag_df.loc[unset, "flag_aqc2"] = FLAG_GOOD

    save_flags(flag_df, agency, station_id, key)

    good    = (flag_df["flag_aqc2"] == FLAG_GOOD).sum()
    suspect = (flag_df["flag_aqc2"] == FLAG_SUSPECT).sum()
    bad     = (flag_df["flag_aqc2"] == FLAG_BAD).sum()
    print(f"  [aqc2] {station_id}: good={good} suspect={suspect} bad={bad}")


def run(agency: str, dataset: str, yyyymm: str,
        station_filter: str | None = None,
        yyyymmdd: str | None = None) -> None:
    _CSV_CACHE.clear()  # 월 단위 실행마다 캐시 초기화
    key         = yyyymmdd if yyyymmdd else yyyymm
    yyyymm_key  = key[:6]
    sorted_path = (sorted_dir() / dataset
                   / f"{agency}_{yyyymm_key}.csv")
    if not sorted_path.exists():
        print(f"[skip] sorted 파일 없음: {sorted_path} — 유효 데이터 없음")
        return

    df = pd.read_csv(sorted_path, dtype={"station_id": str})
    # 연간 파일에서 해당 기간만 추출
    if len(key) == 8:
        _prefix = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
        df = df[df["time"].str.startswith(_prefix)].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    stations = df["station_id"].unique().tolist()
    if station_filter:
        stations = [s for s in stations if s == station_filter]

    print(f"[aqc2] {agency}/{dataset}/{key}  {len(stations)}개 관측소")
    for stn in stations:
        run_station(stn, agency, dataset, key)


if __name__ == "__main__":
    args = parse_args()
    run(args.agency, args.dataset, args.yyyymm, args.station, getattr(args, "yyyymmdd", None))
