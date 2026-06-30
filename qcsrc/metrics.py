# -*- coding: utf-8-sig -*-
"""
QC 성능 지표 계산 모듈.
합성 ground-truth 레이블과 예측 flag를 비교해 precision / recall / F1 / confusion matrix를 반환한다.
flag=3 (BAD)을 이상 탐지 양성(positive)으로 정의한다.
"""

import numpy as np
import pandas as pd
from typing import Dict, Any


def compute_metrics(
    y_true: pd.Series,
    y_pred: pd.Series,
    positive_flag: int = 3,
) -> Dict[str, Any]:
    """
    QC flag 예측 성능 계산.

    Parameters
    ----------
    y_true        : 정답 flag (int Series)
    y_pred        : 예측 flag (int Series)
    positive_flag : 이상 탐지 양성 클래스 (기본 3=BAD)

    Returns
    -------
    dict {precision, recall, f1, confusion_matrix: {tp, fp, fn, tn}}
    """
    if len(y_true) != len(y_pred):
        raise ValueError("y_true 와 y_pred 의 길이가 다릅니다.")

    true_pos = (y_true == positive_flag).astype(int).values
    pred_pos = (y_pred == positive_flag).astype(int).values

    tp = int(np.sum((true_pos == 1) & (pred_pos == 1)))
    fp = int(np.sum((true_pos == 0) & (pred_pos == 1)))
    fn = int(np.sum((true_pos == 1) & (pred_pos == 0)))
    tn = int(np.sum((true_pos == 0) & (pred_pos == 0)))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall    = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1        = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "precision": round(precision, 4),
        "recall":    round(recall, 4),
        "f1":        round(f1, 4),
        "confusion_matrix": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }
