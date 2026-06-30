# -*- coding: utf-8-sig -*-
"""pipeline.py 통합 테스트."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd
import pytest

from qcsrc.pipeline import run_pipeline
from qcsrc.checks import FLAG_GOOD, FLAG_BAD, FLAG_MISSING


def _base_series():
    """파이프라인 검증용 기본 시계열."""
    vals = [20.1, 20.2, 20.1, 99.9, 20.3, 20.3, 20.3, 20.3, 20.3, np.nan]
    idx = pd.date_range("2026-01-01", periods=10, freq="1h")
    return pd.Series(vals, index=idx, dtype=float)


_BASE_CFG = {
    "resample_freq": "1h",
    "fill_method": "linear",
    "range": {"vmin": -5.0, "vmax": 40.0},
    "spike": {"method": "median", "threshold": 3.0},
    "stuck": {"min_change": 0.001, "window": 4},
    "roc": {"max_rate": 5.0},
}


class TestPipelineBasic:
    def test_returns_dataframe(self):
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        assert isinstance(result, pd.DataFrame)

    def test_expected_columns_present(self):
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        expected = {"value", "flag_range", "flag_spike", "flag_stuck",
                    "flag_roc", "flag_edge", "flag_final"}
        assert expected.issubset(set(result.columns))

    def test_output_length_matches_resampled(self):
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        assert len(result) == len(s)

    def test_all_flags_are_valid_codes(self):
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        valid_codes = {1, 2, 3, 9}
        for col in result.columns:
            if col.startswith("flag_"):
                assert set(result[col].unique()).issubset(valid_codes), \
                    f"{col} 에 유효하지 않은 flag 코드 포함"


class TestPipelineAnomalyDetection:
    def test_range_violation_detected(self):
        # 99.9 > vmax=40 → flag_range=BAD
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        assert result["flag_range"].iloc[3] == FLAG_BAD

    def test_stuck_run_detected(self):
        # 20.3 이 5번 연속(index 4-8), window=4 → flag_stuck=BAD
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        stuck_flags = result["flag_stuck"].iloc[4:9]
        assert (stuck_flags == FLAG_BAD).all()

    def test_final_flag_is_worst(self):
        # flag_final 은 각 행 flag 열의 최댓값
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        flag_cols = [c for c in result.columns if c.startswith("flag_") and c != "flag_final"]
        expected_final = result[flag_cols].max(axis=1)
        assert (result["flag_final"] == expected_final).all()

    def test_nan_propagated_as_missing(self):
        # 마지막 NaN → fill_method=linear 외삽 불가 → MISSING 또는 GOOD(보간된 경우)
        s = _base_series()
        result = run_pipeline(s, _BASE_CFG)
        # NaN이 있는 위치(index 9)의 flag_final 이 MISSING(9)이거나 값이 보간된 경우 GOOD 허용
        last_final = result["flag_final"].iloc[9]
        assert last_final in (FLAG_GOOD, FLAG_MISSING)


class TestPipelineMinimalConfig:
    def test_no_checks_runs_without_error(self):
        # 검사 단계 없는 최소 config
        s = _base_series()
        cfg = {"resample_freq": "1h", "fill_method": "linear"}
        result = run_pipeline(s, cfg)
        assert "flag_final" in result.columns
        # 검사 없으면 모든 flag는 GOOD 또는 MISSING
        valid_codes = {FLAG_GOOD, FLAG_MISSING}
        assert set(result["flag_final"].unique()).issubset(valid_codes)

    def test_single_check_spike_only(self):
        s = _base_series()
        cfg = {"spike": {"method": "median", "threshold": 3.0}}
        result = run_pipeline(s, cfg)
        # 99.9 는 spike 로 탐지되어야 함
        assert result["flag_spike"].iloc[3] == FLAG_BAD
