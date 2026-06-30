# -*- coding: utf-8-sig -*-
"""
스파이크 검사 (AQC1)
method 파라미터로 알고리즘 선택 (cfg.method, 기본 'neighbor'):
  'neighbor' — 앞뒤 이웃 평균 편차 기반 (서버 기존 방식, 시간간격·즉시갱신 인식)
  'tukey53h' — Tukey 53H 필터 잔차 + MAD 기반 (QARTOD 표준; 로컬 트렌드 추종)
  'zscore'   — 전역 평균/표준편차 z점수 (정규 분포 가정)
  'iqr'      — 사분위 범위(IQR) 기반 (극단값에 강건)
  'median'   — 이웃 중앙값 편차 기반 (neighbor의 중앙값 변형)

neighbor 방식 개선 사항:
  - 시간 간격 인식: max_gap_hours(기본 6h) 초과 이웃은 참조 불가 → 탐색 중단
  - 다중 이웃: 양쪽 최대 neighbor_count(기본 3)개 good값 수집 후 평균 참조
  - bad/suspect 이웃은 건너뛰고, 시간 간격 내 가장 가까운 정상값부터 수집
  - 즉시 갱신: 스파이크 판정 시 flags_arr 즉시 업데이트 → 연속 블록 오류 검출
    (B1 BAD → flags_arr 반영 → B2 평가 시 B1 제외 → B2도 정상값 대비 비교)

출처(tukey53h): QARTOD Manual (IOOS/NOAA 2020), Castelão 2021 (CoTeDe).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from ..utils.flag_io import FLAG_BAD, FLAG_SUSPECT, FLAG_GOOD, FLAG_MISSING


def _init_result(series: pd.Series) -> pd.DataFrame:
    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)
    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"
    return result


def check_spike(series: pd.Series, cfg: dict,
                cur_flags: pd.Series | None = None,
                time_index: pd.Series | None = None) -> pd.DataFrame:
    """
    cfg 키:
      method (str, 기본 'neighbor') — 'neighbor'|'tukey53h'|'zscore'|'iqr'|'median'
      suspect(float), fail(float)   — neighbor/median 절대편차, zscore=σ, iqr=배수
      threshold (float)             — tukey53h MAD 배수 N (없으면 fail 사용, 기본 3.0)
      max_gap_hours (float, 기본 6.0) — neighbor: 시간차 초과 시 탐색 중단
      neighbor_count (int,   기본 3)  — neighbor/median 양쪽 최대 수집 개수
    cur_flags : 현재까지 누적된 flag (neighbor에서 suspect 이상 이웃 건너뜀)
    time_index: series와 동일 길이의 datetime Series
    반환: DataFrame[flag(int), reason(str)]
    """
    method = str(cfg.get("method", "neighbor")).lower()
    if method == "tukey53h":
        return _spike_tukey53h(series, cfg)
    if method == "zscore":
        return _spike_zscore(series, cfg)
    if method == "iqr":
        return _spike_iqr(series, cfg)
    if method == "median":
        return _spike_median(series, cfg)
    if method != "neighbor":
        raise ValueError(
            f"지원하지 않는 spike method: {method!r}  "
            f"(neighbor | tukey53h | zscore | iqr | median)")

    result = pd.DataFrame({
        "flag":   pd.array([FLAG_GOOD] * len(series), dtype="int8"),
        "reason": [""] * len(series),
    }, index=series.index)

    missing = series.isna()
    result.loc[missing, "flag"]   = FLAG_MISSING
    result.loc[missing, "reason"] = "missing"

    vals = series.values.astype(float)
    n    = len(vals)
    if n < 3:
        return result

    suspect_thr    = float(cfg.get("suspect",       float("inf")))
    fail_thr       = float(cfg.get("fail",          float("inf")))
    max_gap_hours  = float(cfg.get("max_gap_hours", 6.0))
    neighbor_count = int(cfg.get("neighbor_count",  3))
    max_gap_sec    = max_gap_hours * 3600.0

    # 시간 배열 (초 단위 epoch): 시간 간격 계산에 사용
    time_arr: np.ndarray | None = None
    if time_index is not None:
        try:
            time_arr = (pd.to_datetime(time_index)
                        .values.astype("datetime64[ns]")
                        .view(np.int64) / 1e9)
        except Exception:
            time_arr = None

    # 가변 복사본: 스파이크 판정 시 즉시 반영 → 후속 이웃 탐색에서 제외됨
    flags_arr = np.zeros(n, dtype=int)
    if cur_flags is not None:
        flags_arr[:] = cur_flags.values.astype(int)

    def _is_bad(idx: int) -> bool:
        return int(flags_arr[idx]) >= FLAG_SUSPECT

    def _neighbors(center: int, direction: int) -> list[float]:
        """center에서 direction(-1=좌, +1=우) 방향으로 최대 neighbor_count개의
        good·non-missing 값을 수집한다.
        시간 간격이 max_gap_sec를 초과하는 이웃을 만나는 순간 탐색을 중단한다."""
        found: list[float] = []
        j = center + direction
        while 0 <= j < n and len(found) < neighbor_count:
            if not np.isnan(vals[j]) and not _is_bad(j):
                if time_arr is not None:
                    if abs(time_arr[j] - time_arr[center]) > max_gap_sec:
                        break  # 시간 간격 초과 → 이 방향 탐색 종료
                found.append(vals[j])
            j += direction
        return found

    for i in range(n):
        if missing.iloc[i]:
            continue

        left_vals  = _neighbors(i, -1)
        right_vals = _neighbors(i, +1)

        # 총 2개 이상의 유효 이웃이 있으면 비교 가능 (한쪽이 전부 BAD여도 허용)
        all_neighbors = left_vals + right_vals
        if len(all_neighbors) < 2:
            continue

        ref = float(np.mean(all_neighbors))
        d   = abs(vals[i] - ref)

        if d >= fail_thr:
            result.iloc[i] = [FLAG_BAD,     f"spike_fail({d:.2f})"]
            flags_arr[i] = FLAG_BAD      # 즉시 반영: 이후 이웃 탐색에서 제외
        elif d >= suspect_thr:
            result.iloc[i] = [FLAG_SUSPECT, f"spike_suspect({d:.2f})"]
            flags_arr[i] = FLAG_SUSPECT  # 즉시 반영

    return result


# ---------------------------------------------------------------------------
# 대체 method 구현 (config method= 로 선택)
# ---------------------------------------------------------------------------

def _spike_tukey53h(series: pd.Series, cfg: dict) -> pd.DataFrame:
    """
    Tukey 53H 필터 잔차 + MAD 기반 스파이크 탐지 (QARTOD 표준).
      S1 = 길이 5 중앙값(T5) → S2 = S1 길이 3 중앙값(T3)
      S3 = S2 Hanning 가중평균(1/4,1/2,1/4) → smooth baseline
      residual = series - S3
      |residual| >= threshold * 1.5 * MAD → BAD
    threshold(=cfg.threshold, 없으면 cfg.fail, 기본 3.0)는 MAD 배수 N (QARTOD 권고 N=2~4).
    경계 맹점: 양 끝 2포인트는 S3=NaN → 판정 불가(알려진 한계).
    MAD=0(완전 평탄) 가드: stuck/attenuated 담당 영역이므로 GOOD 유지.
    """
    result = _init_result(series)
    valid = ~series.isna()

    threshold = float(cfg.get("threshold", cfg.get("fail", 3.0)))

    s1 = series.rolling(5, center=True, min_periods=3).median()
    s2 = s1.rolling(3, center=True, min_periods=2).median()
    s3 = s2.rolling(3, center=True, min_periods=3).apply(
        lambda w: 0.25 * w[0] + 0.5 * w[1] + 0.25 * w[2], raw=True)

    residual = series - s3
    valid_res = residual.dropna()
    if len(valid_res) < 3:
        return result

    mad = (valid_res - valid_res.median()).abs().median()
    if mad < 1e-10:
        return result

    threshold_val = threshold * 1.5 * mad
    res_abs = residual.abs()
    mask = (valid & residual.notna() & (res_abs >= threshold_val)).values
    for i in range(len(series)):
        if mask[i]:
            result.iloc[i] = [FLAG_BAD, f"spike_tukey53h({res_abs.iloc[i]:.2f}>={threshold_val:.2f})"]
    return result


def _spike_zscore(series: pd.Series, cfg: dict) -> pd.DataFrame:
    """전역 평균·표준편차 z점수. |z|>=fail→BAD, >=suspect→SUSPECT."""
    result = _init_result(series)
    vals = series.dropna()
    if len(vals) < 2:
        return result
    mean = vals.mean()
    std = vals.std()
    if std < 1e-10:
        return result
    fail_thr    = float(cfg.get("fail", float("inf")))
    suspect_thr = float(cfg.get("suspect", float("inf")))
    z = (series - mean).abs() / std
    valid = ~series.isna()
    for i in range(len(series)):
        if not valid.iloc[i]:
            continue
        zi = float(z.iloc[i])
        if zi >= fail_thr:
            result.iloc[i] = [FLAG_BAD, f"spike_zscore({zi:.2f}σ)"]
        elif zi >= suspect_thr:
            result.iloc[i] = [FLAG_SUSPECT, f"spike_zscore({zi:.2f}σ)"]
    return result


def _spike_iqr(series: pd.Series, cfg: dict) -> pd.DataFrame:
    """사분위 범위 기반. [Q1-k*IQR, Q3+k*IQR] 밖→BAD (k=cfg.fail, 기본 1.5)."""
    result = _init_result(series)
    vals = series.dropna()
    if len(vals) < 4:
        return result
    q1, q3 = vals.quantile(0.25), vals.quantile(0.75)
    iqr = q3 - q1
    if iqr < 1e-10:
        return result
    k = float(cfg.get("fail", 1.5))
    lower, upper = q1 - k * iqr, q3 + k * iqr
    valid = ~series.isna()
    for i in range(len(series)):
        if not valid.iloc[i]:
            continue
        x = float(series.iloc[i])
        if x < lower or x > upper:
            result.iloc[i] = [FLAG_BAD, f"spike_iqr({x:.2f})"]
    return result


def _spike_median(series: pd.Series, cfg: dict) -> pd.DataFrame:
    """이웃 중앙값 편차 기반. 좌우 window개 이웃 중앙값과 절대편차로 판정."""
    result = _init_result(series)
    vals = series.values.astype(float)
    n = len(vals)
    fail_thr    = float(cfg.get("fail", float("inf")))
    suspect_thr = float(cfg.get("suspect", float("inf")))
    window = int(cfg.get("neighbor_count", 3))
    for i in range(n):
        if np.isnan(vals[i]):
            continue
        left = []
        for j in range(i - 1, -1, -1):
            if len(left) >= window:
                break
            if not np.isnan(vals[j]):
                left.append(vals[j])
        right = []
        for j in range(i + 1, n):
            if len(right) >= window:
                break
            if not np.isnan(vals[j]):
                right.append(vals[j])
        neighbors = left + right
        if len(neighbors) < 2:
            continue
        ref = float(np.median(neighbors))
        d = abs(vals[i] - ref)
        if d >= fail_thr:
            result.iloc[i] = [FLAG_BAD, f"spike_median_fail({d:.2f})"]
        elif d >= suspect_thr:
            result.iloc[i] = [FLAG_SUSPECT, f"spike_median_suspect({d:.2f})"]
    return result
