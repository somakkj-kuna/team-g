# -*- coding: utf-8-sig -*-
"""
전처리 CSV(daily) 또는 raw CSV(monthly) → 월별 DataFrame 로드 및 변수명 표준화
입력:
  prc 모드: {dataset_path}/{yyyy}/{yyyymmdd}.csv  (long format, 일별)  ※ 기본
  raw 모드: {dataset_path}/{yyyy}/{dataset}_{yyyymm}.csv  (wide format, monthly)
출력: 표준화된 long format DataFrame (1H snapshot)

운영 파이프라인(00_sort)은 raw 모드(load_and_standardize → load_month_raw)를 사용한다.
load_month()는 QC.md 2.1 규격의 전처리 prc CSV를 직접 읽는 보조 로더이다.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

QC_ROOT = Path(__file__).resolve().parents[3]
CONFIG_PATH = QC_ROOT / "src" / "config" / "qc_rules.toml"

NUMERIC_SENTINELS: set[float] = set()


def _load_rules() -> dict:
    with open(CONFIG_PATH, "rb") as f:
        content = f.read()
    if content.startswith(b"\xef\xbb\xbf"):
        content = content[3:]
    return tomllib.loads(content.decode("utf-8"))


def _build_alias_map(rules: dict) -> dict[str, str]:
    """원시 var_id → 표준 var_id 역방향 매핑"""
    alias_map: dict[str, str] = {}
    for std_name, aliases in rules["standardization"]["var_aliases"].items():
        for a in aliases:
            alias_map[a] = std_name
    return alias_map


def _build_sentinels(rules: dict) -> set[float]:
    return set(rules["standardization"]["missing_sentinels"]["values"])


def _resample_hourly_snapshot(df: pd.DataFrame) -> pd.DataFrame:
    """Long format을 1H snapshot으로 변환. 정시에 가장 가까운 관측값 선택."""
    df = df.copy()
    df["_time_h"] = df["time"].dt.round("1h")
    df["_dist"]   = (df["time"] - df["_time_h"]).abs()
    df = (
        df.sort_values(["station_id", "var_id", "_time_h", "_dist"])
          .groupby(["station_id", "var_id", "_time_h"], as_index=False)
          .first()
          .drop(columns=["_dist", "time"])
          .rename(columns={"_time_h": "time"})
    )
    return df


def load_month(dataset_path: str | Path, yyyymm: str) -> pd.DataFrame:
    """
    전처리 prc 일별 CSV(long format)를 읽어 한 달치 DataFrame 반환.
    dataset_path: /data/DATA/OBS/prc/tidal 등
    파일 패턴: {dataset_path}/{yyyy}/{yyyymm}*.csv  (QC.md 2.1 규격)
    CSV가 없으면 parquet(.parquet)로 fallback 한다(하위호환).
    """
    root = Path(dataset_path)
    yyyy = yyyymm[:4]
    year_dir = root / yyyy
    if not year_dir.exists():
        raise FileNotFoundError(f"연도 디렉터리 없음: {year_dir}")

    files = sorted(year_dir.glob(f"{yyyymm}*.csv"))
    if files:
        frames = [pd.read_csv(f, encoding="utf-8-sig", dtype={"station_id": str})
                  for f in files]
    else:
        pq = sorted(year_dir.glob(f"{yyyymm}*.parquet"))
        if not pq:
            raise FileNotFoundError(f"{year_dir} 에서 {yyyymm}* CSV/parquet 없음")
        frames = [pd.read_parquet(f) for f in pq]

    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True)
    return df


def load_month_raw(dataset_path: str | Path, yyyymm: str,
                   dataset: str, agency: str,
                   start_after: pd.Timestamp | None = None) -> pd.DataFrame:
    """
    Raw 월별 wide-format CSV → 1H snapshot long format DataFrame.
    파일 패턴: {dataset_path}/{yyyy}/{dataset}_{yyyymm}.csv
    """
    root = Path(dataset_path)
    yyyy = yyyymm[:4]
    year_dir = root / yyyy
    if not year_dir.exists():
        raise FileNotFoundError(f"연도 디렉터리 없음: {year_dir}")

    files = sorted(year_dir.glob(f"{dataset}_{yyyymm}*.csv"))
    if not files:
        raise FileNotFoundError(f"{year_dir} 에서 {dataset}_{yyyymm}*.csv 없음")

    _NA_VALUES = ["-", "--", "N/A", "NA", "n/a", "null", "NULL", ""]
    frames = []
    for f in files:
        if start_after is None:
            frames.append(pd.read_csv(f, encoding="utf-8-sig",
                                      na_values=_NA_VALUES, keep_default_na=False,
                                      low_memory=False))
            continue
        for chunk in pd.read_csv(f, encoding="utf-8-sig", chunksize=200_000,
                                  na_values=_NA_VALUES, keep_default_na=False,
                                  low_memory=False):
            chunk["time"] = pd.to_datetime(chunk["time"], utc=True, errors="coerce")
            chunk = chunk[chunk["time"] > start_after]
            if not chunk.empty:
                frames.append(chunk)

    if not frames:
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
    df = df.dropna(subset=["time", "station_id"])

    # 메타 컬럼 외 나머지를 변수로 처리
    meta_cols = ["time", "station_id", "lat", "lon"]
    # 이름 메타 + *_depth_m 형태의 수심 보조 컬럼 제외 (NIFS: sur_depth_m 등)
    drop_cols = ["station_name_k", "station_type", "area_name"]
    drop_cols += [c for c in df.columns if c.endswith("_depth_m") or c.endswith("_depth")]
    df = df.drop(columns=[c for c in drop_cols if c in df.columns])

    value_cols = [c for c in df.columns if c not in meta_cols]
    df_long = df.melt(id_vars=meta_cols, value_vars=value_cols,
                      var_name="var_id", value_name="value")
    df_long["agency"]  = agency
    df_long["depth_m"] = float("nan")
    df_long["value"]   = pd.to_numeric(df_long["value"], errors="coerce")

    return _resample_hourly_snapshot(df_long)


def standardize(df: pd.DataFrame, rules: dict | None = None,
                remap: bool = True) -> pd.DataFrame:
    """
    var_id 표준화 + sentinel → NaN 처리.
    remap=False: sentinel 처리만 수행 (raw 모드에서 변수명 그대로 유지 시 사용).
    """
    if rules is None:
        rules = _load_rules()

    sentinels = _build_sentinels(rules)

    df = df.copy()
    if remap:
        alias_map = _build_alias_map(rules)
        df["var_id"] = df["var_id"].map(lambda v: alias_map.get(v, v))
    df.loc[df["value"].isin(sentinels), "value"] = float("nan")
    return df


def apply_depth_mapping_nifs(df: pd.DataFrame) -> pd.DataFrame:
    """
    NIFS 부이: depth_m 기반으로 temp → sur/mid/bot_temp 재매핑.
    df는 이미 standardize() 통과한 상태. agency == 'nifs' 행만 처리.
    """
    if "depth_m" not in df.columns:
        return df

    df = df.copy()
    mask_nifs = (df["agency"] == "nifs") & (df["var_id"] == "sur_temp")
    nifs = df[mask_nifs].copy()

    if nifs.empty:
        return df

    def remap_station(sub: pd.DataFrame) -> pd.DataFrame:
        depths = sorted(sub["depth_m"].dropna().unique())
        n = len(depths)
        if n == 0:
            return sub
        mapping: dict[float, str] = {}
        if n == 1:
            mapping[depths[0]] = "sur_temp"
        elif n == 2:
            mapping[depths[0]] = "sur_temp"
            mapping[depths[1]] = "bot_temp"
        else:
            mapping[depths[0]] = "sur_temp"
            mapping[depths[-1]] = "bot_temp"
            for d in depths[1:-1]:
                mapping[d] = "mid_temp"
        sub = sub.copy()
        sub["var_id"] = sub["depth_m"].map(mapping).fillna(sub["var_id"])
        return sub

    remapped = nifs.groupby("station_id", group_keys=False).apply(remap_station)
    df.loc[mask_nifs, "var_id"] = remapped["var_id"].values
    return df


def derive_uv_components(df: pd.DataFrame) -> pd.DataFrame:
    """
    speed + direction 쌍으로부터 u/v 성분을 파생하여 long format 행으로 추가.

    변환 규칙:
      wind    (기상 관측 — 바람이 불어오는 방향):
        wind_u = -speed * sin(dir_rad)
        wind_v = -speed * cos(dir_rad)
      current (해양 관측 — 흐름이 향하는 방향):
        current_u = speed * sin(dir_rad)
        current_v = speed * cos(dir_rad)

    speed 또는 dir 어느 한쪽이 결측이면 해당 시각의 u/v 도 NaN.
    """
    PAIRS = [
        ("wind_speed",    "wind_dir",      "wind_u",    "wind_v",    "wind"),
        ("current_speed", "current_dir",    "current_u", "current_v", "ocean"),
    ]

    meta_cols = [c for c in ("station_id", "time", "agency", "lat", "lon", "depth_m")
                 if c in df.columns]
    existing_vars = set(df["var_id"].unique())
    new_rows: list[pd.DataFrame] = []

    for speed_var, dir_var, u_var, v_var, convention in PAIRS:
        # raw 데이터에 이미 u 또는 v가 있으면 재계산 불필요
        if u_var in existing_vars or v_var in existing_vars:
            continue
        speed_df = df[df["var_id"] == speed_var][meta_cols + ["value"]].rename(
            columns={"value": "speed"})
        dir_df   = df[df["var_id"] == dir_var][meta_cols + ["value"]].rename(
            columns={"value": "direction"})

        if speed_df.empty or dir_df.empty:
            continue

        join_cols = [c for c in ("station_id", "time", "depth_m") if c in meta_cols]
        merged = speed_df.merge(dir_df[join_cols + ["direction"]],
                                on=join_cols, how="inner")
        if merged.empty:
            continue

        rad = np.radians(merged["direction"].values.astype(float))
        spd = merged["speed"].values.astype(float)

        if convention == "wind":
            u_vals = -spd * np.sin(rad)
            v_vals = -spd * np.cos(rad)
        else:
            u_vals = spd * np.sin(rad)
            v_vals = spd * np.cos(rad)

        for var_name, vals in ((u_var, u_vals), (v_var, v_vals)):
            tmp = merged[meta_cols].copy()
            tmp["var_id"] = var_name
            tmp["value"]  = vals
            new_rows.append(tmp)

    if not new_rows:
        return df

    return pd.concat([df] + new_rows, ignore_index=True)


def load_and_standardize(dataset_path: str | Path, yyyymm: str,
                          agency: str | None = None,
                          dataset: str | None = None,
                          start_after: pd.Timestamp | None = None) -> pd.DataFrame:
    """
    load_month(prc parquet) 또는 load_month_raw(raw CSV) 자동 선택 후
    standardize + nifs depth mapping 한 번에 수행.
    """
    rules    = _load_rules()
    root     = Path(dataset_path)
    yyyy     = yyyymm[:4]
    year_dir = root / yyyy

    # raw CSV 전용 (parquet 미사용)
    if not (dataset and agency):
        raise ValueError("agency, dataset 인수 필수")
    df = load_month_raw(dataset_path, yyyymm, dataset, agency, start_after=start_after)
    # raw 모드: 변수명 그대로 사용 (alias 재매핑 안 함)
    df = standardize(df, rules, remap=False)
    df = apply_depth_mapping_nifs(df)
    df = derive_uv_components(df)

    df = df.dropna(subset=["var_id"])
    df = df.sort_values(["station_id", "var_id", "time"]).reset_index(drop=True)
    return df
