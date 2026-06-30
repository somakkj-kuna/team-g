#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
make_err_data.py — 합성 에러 테스트데이터 생성기

실제 raw 월별 CSV(wide format)를 복제한 뒤, QC 검사가 잡아낼 수 있도록
의도적인 이상치를 주입해 test/raw 아래에 저장한다. (--err 모드 입력용)

주입 에러 유형:
  missing  : 연속 결측(sentinel -999.0) 블록  → flag 9
  spike    : 단발 급변(큰 오프셋)             → flag 3 (spike)
  range    : 물리범위 초과값                  → flag 3 (range/dynamic_range)
  stuck    : 일정 구간 동일값 고착            → flag 2/3 (stuck)
  attenuated: 일정 구간 변동폭 축소           → flag 2 (attenuated)

사용법:
  python src/libs/tools/make_err_data.py --agency khoa --dataset tidal --yyyymm 202501
  옵션 --force : 이미 test/raw에 있어도 덮어씀 (기본은 있으면 재사용=skip)

출력: <QC_ERR_RAW_ROOT 또는 test/raw>/{agency}/{dataset}/{yyyy}/{dataset}_{yyyymm}.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

QC_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QC_ROOT))

from src.libs.utils import config_loader

SENTINEL = -999.0
# 에러를 주입할 대상 변수(컬럼명은 raw wide 헤더 기준)
TARGET_VARS = ["temp", "tide_real", "sal"]
# 물리범위 초과(range) 주입용 극단값
OUT_OF_RANGE = {"temp": 99.0, "tide_real": 9999.0, "sal": 99.0}


def _real_raw_base(agency: str, dataset: str) -> str:
    """실제 raw 루트(프로파일 무관). meta/agencies → qc_rules[paths] 순."""
    cfg = config_loader.load_agency(agency)
    base = cfg.get("datasets", {}).get(dataset, {}).get("prc_path", "")
    if base:
        return base
    rules = config_loader.load_rules()
    return (rules.get("paths", {}).get(agency, {})
                 .get(dataset, {}).get("raw", ""))


def _find_source(real_base: str, dataset: str, yyyymm: str) -> Path | None:
    yyyy = yyyymm[:4]
    year_dir = Path(real_base) / yyyy
    if not year_dir.exists():
        return None
    files = sorted(year_dir.glob(f"{dataset}_{yyyymm}*.csv"))
    return files[0] if files else None


def _inject_station_var(df: pd.DataFrame, idx: np.ndarray, col: str,
                        rng: np.random.Generator) -> dict:
    """한 관측소·변수 구간(idx, 시간순)에 각종 에러 주입. 주입 카운트 반환."""
    counts = {"missing": 0, "spike": 0, "range": 0, "stuck": 0, "attenuated": 0}
    vals = df.loc[idx, col].to_numpy(dtype=float, copy=True)
    # 실제 값이 있는 위치만 대상 (이미 sentinel인 곳은 제외)
    valid_pos = np.where(vals > SENTINEL + 1)[0]
    if len(valid_pos) < 60:
        return counts
    n = len(valid_pos)
    base_med = float(np.median(vals[valid_pos]))
    base_std = float(np.std(vals[valid_pos])) or 1.0

    # 1) missing 블록 (연속 24포인트)
    s = valid_pos[int(n * 0.10)]
    block = valid_pos[(valid_pos >= s) & (valid_pos < s + 24)]
    vals[block] = SENTINEL
    counts["missing"] += len(block)

    # 2) spike (산발 5포인트, +8σ)
    sp = rng.choice(valid_pos[int(n * 0.20):int(n * 0.40)],
                    size=min(5, max(1, n // 50)), replace=False)
    vals[sp] = base_med + 8.0 * base_std + 5.0
    counts["spike"] += len(sp)

    # 3) range 초과 (3포인트)
    rg = rng.choice(valid_pos[int(n * 0.45):int(n * 0.55)],
                    size=min(3, max(1, n // 80)), replace=False)
    vals[rg] = OUT_OF_RANGE.get(col, base_med + 1000.0)
    counts["range"] += len(rg)

    # 4) stuck (연속 30포인트 동일값)
    st0 = valid_pos[int(n * 0.60)]
    stk = valid_pos[(valid_pos >= st0) & (valid_pos < st0 + 30)]
    vals[stk] = base_med
    counts["stuck"] += len(stk)

    # 5) attenuated (연속 80포인트 변동폭 축소: 평균쪽으로 압축)
    at0 = valid_pos[int(n * 0.75)]
    att = valid_pos[(valid_pos >= at0) & (valid_pos < at0 + 80)]
    vals[att] = base_med + (vals[att] - base_med) * 0.01
    counts["attenuated"] += len(att)

    df.loc[idx, col] = vals
    return counts


def run(agency: str, dataset: str, yyyymm: str, force: bool = False) -> bool:
    yyyy = yyyymm[:4]
    out_base = config_loader.err_raw_root()
    out_path = out_base / agency / dataset / yyyy / f"{dataset}_{yyyymm}.csv"

    if out_path.exists() and not force:
        print(f"[make_err] 재사용(skip): {out_path} 이미 존재")
        return True

    real_base = _real_raw_base(agency, dataset)
    if not real_base:
        print(f"[make_err] 실패: {agency}/{dataset} 실제 raw 경로 미정")
        return False
    src = _find_source(real_base, dataset, yyyymm)
    if src is None:
        print(f"[make_err] 실패: 원본 raw 없음 ({real_base}/{yyyy}/{dataset}_{yyyymm}*.csv)")
        return False

    print(f"[make_err] 원본 로드: {src}")
    df = pd.read_csv(src, encoding="utf-8-sig", dtype={"station_id": str},
                     low_memory=False)

    target_cols = [c for c in TARGET_VARS if c in df.columns]
    if not target_cols:
        print(f"[make_err] 경고: 주입 대상 변수({TARGET_VARS}) 없음 — 원본 복사만 수행")

    rng = np.random.default_rng(int(yyyymm))
    df = df.sort_values(["station_id", "time"]).reset_index(drop=True)

    total = {"missing": 0, "spike": 0, "range": 0, "stuck": 0, "attenuated": 0}
    # 관측소별로 실제 값이 충분한 상위 3개에만 주입 (대조군 보존)
    stations = [s for s in df["station_id"].dropna().unique() if str(s).strip()]
    for col in target_cols:
        cand = []
        for stn in stations:
            idx = df.index[df["station_id"] == stn].to_numpy()
            vv = df.loc[idx, col].to_numpy(dtype=float)
            ok = int(np.sum(vv > SENTINEL + 1))
            if ok >= 200:
                cand.append((ok, stn, idx))
        cand.sort(reverse=True, key=lambda x: x[0])
        for _, stn, idx in cand[:3]:
            c = _inject_station_var(df, idx, col, rng)
            for k in total:
                total[k] += c[k]

    out_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out_path, index=False, encoding="utf-8-sig")
    print(f"[make_err] 저장: {out_path}  ({len(df)}행)")
    print(f"[make_err] 주입 요약: " +
          ", ".join(f"{k}={v}" for k, v in total.items()))
    return True


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",  required=True)
    p.add_argument("--dataset", required=True)
    p.add_argument("--yyyymm",  required=True)
    p.add_argument("--force",   action="store_true",
                   help="이미 test/raw에 있어도 덮어씀")
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    ok = run(a.agency, a.dataset, a.yyyymm, a.force)
    sys.exit(0 if ok else 1)
