# -*- coding: utf-8-sig -*-
"""
스파이크 검사 알고리즘 비교 벤치마크.
3종 방법(zscore, iqr, median) × 파라미터 그리드를 자동 실행해
precision / recall / F1을 DataFrame으로 정리한다.
"""

import pandas as pd
from qcsrc.checks import spike_check
from qcsrc.metrics import compute_metrics


# 기본 파라미터 그리드
_DEFAULT_THRESHOLDS = {
    "zscore": [2.0, 2.5, 3.0, 3.5, 4.0],
    "iqr":    [1.0, 1.5, 2.0, 3.0, 4.0],
    "median": [1.0, 2.0, 3.0, 5.0, 7.0],
}


def run_benchmark(
    series: pd.Series,
    labels: pd.Series,
    threshold_grid: dict = None,
    window: int = 3,
    positive_flag: int = 3,
) -> pd.DataFrame:
    """
    스파이크 검사 3종 × 파라미터 그리드 벤치마크.

    Parameters
    ----------
    series         : 검사 대상 시계열
    labels         : 정답 flag (같은 인덱스, 3=BAD가 양성)
    threshold_grid : {method: [threshold, ...]} 형태 오버라이드 (없으면 기본값 사용)
    window         : median 방법의 이웃 수
    positive_flag  : 이상 탐지 양성 클래스

    Returns
    -------
    DataFrame (method, threshold, precision, recall, f1) — f1 내림차순 정렬
    """
    grid = threshold_grid if threshold_grid is not None else _DEFAULT_THRESHOLDS

    rows = []
    for method, thresholds in grid.items():
        for thr in thresholds:
            pred = spike_check.run(series, method=method, threshold=thr, window=window)
            m = compute_metrics(labels, pred, positive_flag=positive_flag)
            rows.append(
                {
                    "method":    method,
                    "threshold": thr,
                    "precision": m["precision"],
                    "recall":    m["recall"],
                    "f1":        m["f1"],
                }
            )

    df = pd.DataFrame(rows).sort_values("f1", ascending=False).reset_index(drop=True)

    if not df.empty and df["f1"].iloc[0] > 0:
        best = df.iloc[0]
        print(
            f"[benchmark] 최고 F1: method={best['method']!r}, "
            f"threshold={best['threshold']:.2f}, "
            f"precision={best['precision']:.3f}, "
            f"recall={best['recall']:.3f}, "
            f"F1={best['f1']:.3f}"
        )
    else:
        print("[benchmark] F1 > 0 인 조합 없음 — 레이블 또는 파라미터를 확인하세요.")

    return df
