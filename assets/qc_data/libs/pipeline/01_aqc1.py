#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
01_aqc1.py — 1차 자동 QC (AQC1)
물리 범위·dynamic_range·stuck·attenuated·spike(neighbor/tukey53h)·ROC·교차 검사.
입력: src/tmp/sorted/{dataset}/{agency}_{yyyymm}.csv
출력: src/tmp/flags/{agency}/{station_id}/{yyyymm}_flag.csv (신규 또는 덮어쓰기)

사용법:
  python src/pipeline/01_aqc1.py --agency khoa --dataset tidal --yyyymm 202501
  python src/pipeline/01_aqc1.py --agency khoa --dataset tidal --yyyymm 202501 --station DT_0001
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
    init_flags, save_flags, SEVERITY,
)
from src.libs.utils.config_loader import (
    get_var_cfg, load_rules, infer_interval, result_dir, sorted_dir,
)
from src.libs.checks.zero_check        import check_zero
from src.libs.checks.range_check       import check_range
from src.libs.checks.spike_check       import check_spike
from src.libs.checks.stuck_check       import check_stuck
from src.libs.checks.roc_check         import check_roc
from src.libs.checks.cross_check       import check_reference, check_vertical, check_vector_range
from src.libs.checks.edge_check        import check_edge
from src.libs.checks.consistency_check import check_consistency
from src.libs.checks.attenuated_check  import check_attenuated
from src.libs.checks.dynamic_range_check import check_dynamic_range


def _load_var_buffer(agency: str, station_id: str, dataset: str,
                     var: str, yyyymm: str, hours: float,
                     from_tail: bool) -> tuple | None:
    """인접 월 변수 자료를 edge check buffer로 로드.
    from_tail=True: 해당 월 끝 hours시간 / False: 앞 hours시간
    반환: (series, flag_series, time_series) or None
    """
    year = int(yyyymm[:4])

    # 1순위: result flag CSV (flag_aqc1 포함)
    csv_path = (result_dir() / "flag" / agency / str(station_id)
                / str(year) / f"{agency}_{str(station_id)}_{yyyymm[:4]}_qc_flag.csv")
    # 2순위: sorted CSV (QC 없음 → FLAG_GOOD 처리)
    pq_path  = (sorted_dir() / dataset
                / f"{agency}_{yyyymm}.csv")

    df       = None
    has_flag = False

    if csv_path.exists():
        try:
            df = pd.read_csv(csv_path, encoding="utf-8-sig",
                             usecols=["time", "var_id", "value", "flag_aqc1"])
            # 연간 flag 파일에서 해당 월만 추출
            df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
            _mm = int(yyyymm[4:6])
            df = df[(df["time"].dt.year == int(yyyymm[:4])) &
                    (df["time"].dt.month == _mm)]
            has_flag = True
        except Exception:
            df = None

    if df is None and pq_path.exists():
        try:
            raw = pd.read_csv(pq_path, usecols=["time", "station_id", "var_id", "value"],
                              dtype={"station_id": str})
            raw["time"] = pd.to_datetime(raw["time"], utc=True)
            df  = raw[raw["station_id"] == station_id].copy()
        except Exception:
            df = None

    if df is None or df.empty:
        return None

    sub = df[df["var_id"] == var].copy()
    if sub.empty:
        return None

    sub["time"] = pd.to_datetime(sub["time"], utc=True)
    sub = sub.sort_values("time").reset_index(drop=True)

    td = pd.Timedelta(hours=hours)
    if from_tail:
        sub = sub[sub["time"] > sub["time"].iloc[-1] - td]
    else:
        sub = sub[sub["time"] <= sub["time"].iloc[0] + td]

    if sub.empty:
        return None

    series = sub["value"].reset_index(drop=True)
    flags  = (sub["flag_aqc1"].fillna(FLAG_GOOD).astype("int8").reset_index(drop=True)
              if has_flag else pd.Series([FLAG_GOOD] * len(sub), dtype="int8"))
    times  = sub["time"].reset_index(drop=True)

    return series, flags, times


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",  required=True)
    p.add_argument("--dataset", required=True)
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--yyyymm",   help="월별 처리 (YYYYMM)")
    g.add_argument("--yyyymmdd", help="일별 처리 (YYYYMMDD)")
    p.add_argument("--station", default=None, help="특정 관측소만 처리")
    return p.parse_args()


def _merge_flags(base: pd.Series, new: pd.Series,
                 base_reason: pd.Series, new_reason: pd.Series):
    """new가 base보다 severity 높으면 교체."""
    updated_flag   = base.copy()
    updated_reason = base_reason.copy()
    for i in range(len(base)):
        nf = int(new.iloc[i])
        bf = int(base.iloc[i])
        if SEVERITY.get(nf, -1) > SEVERITY.get(bf, -1):
            updated_flag.iloc[i]   = nf
            updated_reason.iloc[i] = new_reason.iloc[i]
    return updated_flag, updated_reason


def run_station(wide: pd.DataFrame, station_id: str, agency: str,
                dataset: str, key: str, rules: dict) -> None:
    """한 관측소의 AQC1 수행 및 flag 저장."""
    long_df = wide.copy()
    flag_df = init_flags(long_df, station_id, agency)

    interval = infer_interval(flag_df)

    variables = flag_df["var_id"].unique().tolist()

    # consistency 검사의 reference_col이 dependent 변수보다 먼저 처리되도록 재정렬
    _dep_to_ref: dict[str, str] = {}
    for v in variables:
        ref = (rules.get("variables", {}).get(v, {})
               .get("consistency", {}).get("reference_col"))
        if ref and ref in variables:
            _dep_to_ref[v] = ref

    _ordered: list[str] = []
    _visited: set[str] = set()

    def _visit(v: str) -> None:
        if v in _visited:
            return
        if v in _dep_to_ref:
            _visit(_dep_to_ref[v])
        _visited.add(v)
        _ordered.append(v)

    for v in variables:
        _visit(v)
    variables = _ordered

    for var in variables:
        mask = flag_df["var_id"] == var
        sub  = flag_df[mask].copy().sort_values("time").reset_index(drop=True)
        if sub.empty:
            continue

        series     = sub["value"]
        time_index = pd.to_datetime(sub["time"])
        cfg        = get_var_cfg(var, agency, station_id)
        enabled    = cfg.get("enabled_tests", {})

        cur_flag   = sub["flag_aqc1"].copy()
        cur_reason = sub["reason_aqc1"].copy()

        # 0. Zero 검사 (최초: 0.0 값 → 즉시 BAD)
        if enabled.get("zero", False):
            r = check_zero(series, cfg.get("zero", {}))
            cur_flag, cur_reason = _merge_flags(
                cur_flag, r["flag"], cur_reason, r["reason"])

        # 1. 범위 검사
        if enabled.get("range", False):
            range_cfg = cfg.get("range", {})
            if not enabled.get("seasonal", False):
                range_cfg = {k: v for k, v in range_cfg.items() if k != "seasonal"}
            r = check_range(series, range_cfg, time_index)
            cur_flag, cur_reason = _merge_flags(
                cur_flag, r["flag"], cur_reason, r["reason"])

        # 1-b. 동적 분위값 범위 검사 (계절 이상값; range_check의 계절화 확장)
        if enabled.get("dynamic_range", False):
            r = check_dynamic_range(series, cfg.get("dynamic_range", {}), time_index)
            cur_flag, cur_reason = _merge_flags(
                cur_flag, r["flag"], cur_reason, r["reason"])

        # 2. Stuck 검사
        if enabled.get("stuck", False):
            skip_s     = None
            skip_flags = None
            skip_col = cfg.get("stuck", {}).get("skip_below_col")
            if skip_col:
                skip_mask = flag_df["var_id"] == skip_col
                skip_s = (flag_df[skip_mask].sort_values("time")
                          .set_index("time")["value"]
                          .reindex(pd.DatetimeIndex(sub["time"]))
                          .values)
                skip_s = pd.Series(skip_s)
                # skip_col이 이미 처리된 경우 그 플래그도 전달
                skip_flags = (flag_df[skip_mask].sort_values("time")
                              .set_index("time")["flag_aqc1"]
                              .reindex(pd.DatetimeIndex(sub["time"]))
                              .fillna(FLAG_GOOD)
                              .astype("int8")
                              .values)
                skip_flags = pd.Series(skip_flags)
            r = check_stuck(series, cfg.get("stuck", {}), interval, skip_s, cur_flag, skip_flags)
            cur_flag, cur_reason = _merge_flags(
                cur_flag, r["flag"], cur_reason, r["reason"])

        # 2-a. 신호 감쇠 검사 (stuck 보완: 미세진동은 있으나 비정상적으로 좁은 신호)
        if enabled.get("attenuated", False):
            r = check_attenuated(series, cfg.get("attenuated", {}), time_index)
            cur_flag, cur_reason = _merge_flags(
                cur_flag, r["flag"], cur_reason, r["reason"])

        # 2-b. 일관성 검사 (연동 변수 간 물리적 일관성)
        if enabled.get("consistency", False):
            ref_col = cfg.get("consistency", {}).get("reference_col")
            if ref_col:
                ref_mask = flag_df["var_id"] == ref_col
                if ref_mask.any():
                    ref_base = flag_df[ref_mask].sort_values("time").set_index("time")
                    ref_s = pd.Series(
                        ref_base["value"].reindex(pd.DatetimeIndex(sub["time"])).values,
                        index=sub.index,
                    )
                    ref_f = pd.Series(
                        ref_base["flag_aqc1"]
                        .reindex(pd.DatetimeIndex(sub["time"]))
                        .fillna(FLAG_GOOD)
                        .astype("int8")
                        .values,
                        index=sub.index,
                    )
                    r = check_consistency(series, cfg.get("consistency", {}), ref_s, ref_f)
                    cur_flag, cur_reason = _merge_flags(
                        cur_flag, r["flag"], cur_reason, r["reason"])

        # 3. Edge 검사 (spike 전: 데이터 공백 직후 segment 시작값 선검사)
        # 월 경계 오검출 방지: 이전·다음 월을 buffer로 병합 후 현재 월 분만 반영
        # buf_hours = max(window, backward_window) — 이전 월 일주일치(168h) 확보
        if enabled.get("edge", False):
            edge_cfg  = cfg.get("edge", {})
            def _parse_h(s, default):
                s = str(s).strip().lower()
                return float(s[:-1]) * (24 if s.endswith("d") else 1) if s[-1].isalpha() else float(s)
            fwd_hours = _parse_h(edge_cfg.get("fwd_scan",
                            edge_cfg.get("window", "48h")), 48.0)
            buf_hours = fwd_hours

            ym = key[:6]
            y, mo = int(ym[:4]), int(ym[4:])
            prev_ym = f"{y-1 if mo==1 else y}{12 if mo==1 else mo-1:02d}"
            next_ym = f"{y+1 if mo==12 else y}{1 if mo==12 else mo+1:02d}"

            prev_buf = _load_var_buffer(agency, station_id, dataset, var,
                                        prev_ym, buf_hours, from_tail=True)
            next_buf = _load_var_buffer(agency, station_id, dataset, var,
                                        next_ym, buf_hours, from_tail=False)

            # [prev_buf] + [현재 월] + [next_buf] 결합
            s_parts = [series.reset_index(drop=True)]
            f_parts = [cur_flag.reset_index(drop=True)]
            t_parts = [pd.Series(pd.to_datetime(sub["time"], utc=True).values)]
            n_prev  = 0

            if prev_buf is not None:
                ps, pf, pt = prev_buf
                n_prev = len(ps)
                s_parts.insert(0, ps)
                f_parts.insert(0, pf)
                t_parts.insert(0, pd.Series(pt.values))

            if next_buf is not None:
                ns, nf, nt = next_buf
                s_parts.append(ns)
                f_parts.append(nf)
                t_parts.append(pd.Series(nt.values))

            e_series = pd.concat(s_parts, ignore_index=True)
            e_flags  = pd.concat(f_parts, ignore_index=True)
            e_times  = pd.concat(t_parts, ignore_index=True)

            r = check_edge(e_series, edge_cfg, e_flags, e_times)

            # 현재 월 해당 행만 flag 적용
            r_curr = r.iloc[n_prev : n_prev + len(series)].copy()
            r_curr.index = cur_flag.index
            cur_flag, cur_reason = _merge_flags(
                cur_flag, r_curr["flag"], cur_reason, r_curr["reason"])

        # 4. Spike 검사 — 수렴 반복 (블록형 이상값 전파 포착)
        # ① spike 전용 플래그(spike_acc)를 별도 관리: range/stuck suspect를 건너뛰지 않음.
        # ② 각 패스 결과로 완전 교체(REPLACE): 직전 패스의 오진을 다음 패스에서 정정 가능.
        #    MERGE 방식은 오진이 고정되는 문제가 있음.
        if enabled.get("spike", False):
            # hard_bad: zero/range/stuck fail 값 — 반복 내내 이웃창에서 제외
            # SUSPECT는 GOOD으로 초기화하여 이웃으로 포함
            hard_bad = cur_flag.copy().astype("int8")
            hard_bad[hard_bad == FLAG_SUSPECT] = FLAG_GOOD

            spike_acc    = hard_bad.copy()
            spike_reason = pd.Series([""] * len(cur_flag), index=cur_flag.index)
            for _ in range(10):
                r = check_spike(series, cfg.get("spike", {}), spike_acc, time_index)
                # spike 결과에 hard_bad 재적용: 반복마다 BAD 제외 기준 유지
                new_acc = r["flag"].copy()
                new_acc[hard_bad >= FLAG_BAD] = FLAG_BAD
                if (new_acc.values == spike_acc.values).all():
                    break
                spike_acc    = new_acc
                spike_reason = r["reason"].copy()
            cur_flag, cur_reason = _merge_flags(
                cur_flag, spike_acc, cur_reason, spike_reason)

        # 5. 변화율 검사 (spike가 bad 처리한 값은 건너뛰고 비교)
        if enabled.get("roc", False):
            skip_s = None
            skip_col = cfg.get("roc", {}).get("skip_below_col")
            if skip_col:
                skip_mask = flag_df["var_id"] == skip_col
                skip_s = (flag_df[skip_mask].sort_values("time")
                          .set_index("time")["value"]
                          .reindex(pd.DatetimeIndex(sub["time"]))
                          .values)
                skip_s = pd.Series(skip_s)
            r = check_roc(series, cfg.get("roc", {}), time_index, skip_s, cur_flag)
            cur_flag, cur_reason = _merge_flags(
                cur_flag, r["flag"], cur_reason, r["reason"])

        # 6. Reference 검사 (예: tide_real vs tide_pre)
        if enabled.get("reference", False):
            ref_col = cfg.get("reference", {}).get("column")
            ref_mask = flag_df["var_id"] == ref_col
            if ref_col and ref_mask.any():
                ref_sub = flag_df[ref_mask].sort_values("time").set_index("time")
                ref_series = pd.Series(
                    ref_sub["value"].reindex(pd.DatetimeIndex(sub["time"])).values,
                    index=sub.index)
                # 이미 처리된 경우 ref의 flag를 가져옴 (없으면 None)
                other_flags = None
                if "flag_aqc1" in ref_sub.columns:
                    other_flags = pd.Series(
                        ref_sub["flag_aqc1"].reindex(pd.DatetimeIndex(sub["time"])).fillna(0).astype(int).values,
                        index=sub.index)
                r = check_reference(series, ref_series,
                                    cfg.get("reference", {}), other_flags)
                cur_flag, cur_reason = _merge_flags(
                    cur_flag, r["flag"], cur_reason, r["reason"])

        # 7. 수직 일관성 검사
        if enabled.get("vertical", False):
            for rule in cfg.get("vertical", {}).get("rules", []):
                other_col  = rule.get("other")
                other_mask = flag_df["var_id"] == other_col
                if not other_mask.any():
                    continue
                other_sub = flag_df[other_mask].sort_values("time").set_index("time")
                other_series = pd.Series(
                    other_sub["value"].reindex(pd.DatetimeIndex(sub["time"])).values,
                    index=sub.index)
                # 이미 처리된 경우 other의 flag를 가져옴
                other_flags = None
                if "flag_aqc1" in other_sub.columns:
                    other_flags = pd.Series(
                        other_sub["flag_aqc1"].reindex(pd.DatetimeIndex(sub["time"])).fillna(0).astype(int).values,
                        index=sub.index)
                r = check_vertical(series, other_series, rule, other_flags)
                cur_flag, cur_reason = _merge_flags(
                    cur_flag, r["flag"], cur_reason, r["reason"])

        # 8. 벡터 크기 범위 검사
        if enabled.get("vector_range", False):
            pair_col  = cfg.get("vector_range", {}).get("pair_col")
            pair_mask = flag_df["var_id"] == pair_col
            if pair_col and pair_mask.any():
                pair_series = (flag_df[pair_mask].sort_values("time")
                               .set_index("time")["value"]
                               .reindex(pd.DatetimeIndex(sub["time"]))
                               .values)
                pair_series = pd.Series(pair_series, index=sub.index)
                r = check_vector_range(series, pair_series, cfg.get("vector_range", {}))
                cur_flag, cur_reason = _merge_flags(
                    cur_flag, r["flag"], cur_reason, r["reason"])

        # 결과 반영 (missing은 건드리지 않음)
        flag_df.loc[mask, "flag_aqc1"]   = cur_flag.values
        flag_df.loc[mask, "reason_aqc1"] = cur_reason.values

        # missing은 항상 유지
        missing_idx = flag_df[mask & (flag_df["value"].isna())].index
        flag_df.loc[missing_idx, "flag_aqc1"]   = FLAG_MISSING
        flag_df.loc[missing_idx, "reason_aqc1"] = "missing"

    # good(0→1) 확정
    unset = flag_df["flag_aqc1"] == 0
    flag_df.loc[unset, "flag_aqc1"] = FLAG_GOOD

    save_flags(flag_df, agency, station_id, key)
    good    = (flag_df["flag_aqc1"] == FLAG_GOOD).sum()
    suspect = (flag_df["flag_aqc1"] == FLAG_SUSPECT).sum()
    bad     = (flag_df["flag_aqc1"] == FLAG_BAD).sum()
    miss    = (flag_df["flag_aqc1"] == FLAG_MISSING).sum()
    print(f"  [aqc1] {station_id}: good={good} suspect={suspect} bad={bad} missing={miss}")


def run(agency: str, dataset: str, yyyymm: str,
        station_filter: str | None = None,
        yyyymmdd: str | None = None) -> None:
    key         = yyyymmdd if yyyymmdd else yyyymm
    yyyymm_key  = key[:6]
    sorted_path = (sorted_dir() / dataset
                   / f"{agency}_{yyyymm_key}.csv")
    if not sorted_path.exists():
        print(f"[aqc1] skip {agency}/{dataset}/{key}: sorted 파일 없음 (유효 데이터 없음)")
        return

    df = pd.read_csv(sorted_path, dtype={"station_id": str})
    if len(key) == 8:
        _prefix = f"{key[:4]}-{key[4:6]}-{key[6:8]}"
        df = df[df["time"].str.startswith(_prefix)].copy()
    df["time"] = pd.to_datetime(df["time"], utc=True)
    rules = load_rules()

    stations = df["station_id"].unique().tolist()
    if station_filter:
        stations = [s for s in stations if s == station_filter]
        if not stations:
            raise ValueError(f"관측소 {station_filter} 없음")

    print(f"[aqc1] {agency}/{dataset}/{key}  {len(stations)}개 관측소")
    for stn in stations:
        run_station(df, stn, agency, dataset, key, rules)


if __name__ == "__main__":
    args = parse_args()
    run(args.agency, args.dataset, args.yyyymm, args.station, getattr(args, "yyyymmdd", None))
