#!/usr/bin/env python
# -*- coding: utf-8-sig -*-
"""
anomaly_summary.py — QC 결과의 결측·이상치 비율 요약 및 '너무 적음' 판정

result(또는 err_result)/flag 아래 연간 flag CSV를 읽어 flag_final 분포를 집계하고,
이상치(suspect+bad) 비율이 임계값 미만이면 'TOO_FEW'로 판정한다.
run_qc.sh가 일반 실행 후 호출해, 이상치가 너무 적으면 합성 테스트데이터 생성을 안내한다.

사용법:
  python src/libs/tools/anomaly_summary.py --agency khoa --dataset tidal --year 2025
  옵션 --threshold 0.005  (이상치 비율 임계, 기본 0.5%)
표준출력 마지막 줄: "VERDICT: TOO_FEW" 또는 "VERDICT: OK"
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

QC_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(QC_ROOT))

from src.libs.utils.config_loader import result_dir

MISSING = 9
SUSPECT = 2
BAD = 3


def run(agency: str, dataset: str, year: str, threshold: float) -> str:
    flag_root = result_dir() / "flag" / agency
    files = sorted(flag_root.glob(f"*/{year}/{agency}_*_{year}_qc_flag.csv"))
    if not files:
        print(f"[anomaly] flag 파일 없음: {flag_root}/*/{year}/")
        print("VERDICT: TOO_FEW")
        return "TOO_FEW"

    total = 0
    cnt = {1: 0, 2: 0, 3: 0, 4: 0, 9: 0}
    for f in files:
        try:
            df = pd.read_csv(f, usecols=["flag_final"], encoding="utf-8-sig")
        except Exception:
            continue
        vc = df["flag_final"].value_counts()
        for k, v in vc.items():
            cnt[int(k)] = cnt.get(int(k), 0) + int(v)
            total += int(v)

    non_missing = total - cnt.get(MISSING, 0)
    anomalies = cnt.get(SUSPECT, 0) + cnt.get(BAD, 0)
    ratio = (anomalies / non_missing) if non_missing > 0 else 0.0

    print(f"[anomaly] {agency}/{dataset}/{year}  파일 {len(files)}개")
    print(f"[anomaly] flag_final 분포: {dict(sorted(cnt.items()))}  (총 {total}행)")
    print(f"[anomaly] 결측 {cnt.get(MISSING,0)}행, "
          f"이상치(suspect+bad) {anomalies}행, "
          f"이상치 비율 {ratio*100:.3f}% (임계 {threshold*100:.3f}%)")

    verdict = "TOO_FEW" if ratio < threshold else "OK"
    print(f"VERDICT: {verdict}")
    return verdict


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--agency",   required=True)
    p.add_argument("--dataset",  required=True)
    p.add_argument("--year",     required=True)
    p.add_argument("--threshold", type=float, default=0.005)
    return p.parse_args()


if __name__ == "__main__":
    a = parse_args()
    run(a.agency, a.dataset, a.year, a.threshold)
