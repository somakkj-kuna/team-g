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


if __name__ == "__main__":
    # 직접 실행 예시: 인위적인 스파이크를 삽입한 시계열로 3종 알고리즘 비교
    import numpy as np

    rng = np.random.default_rng(42)
    n = 200
    base = 20.0 + rng.normal(0, 0.5, n)      # 기저 수온 시계열
    labels_arr = pd.Series([1] * n)           # 정답 플래그 (1=good)

    # 인위적 스파이크 삽입
    spike_indices = [30, 80, 150]
    for idx in spike_indices:
        base[idx] += 15.0                     # +15°C 급등
        labels_arr.iloc[idx] = 3              # 정답: BAD

    series_example = pd.Series(
        base,
        index=pd.date_range("2026-01-01", periods=n, freq="1h"),
        name="sur_temp",
    )

    print("=== 스파이크 검사 벤치마크 (zscore / iqr / median) ===")
    result_df = run_benchmark(series_example, labels_arr)
    print(result_df.head(10).to_string(index=False))
