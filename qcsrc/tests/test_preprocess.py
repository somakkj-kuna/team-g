# -*- coding: utf-8-sig -*-
"""preprocess.py 단위 테스트."""

import sys
import os

# qcsrc 패키지가 있는 프로젝트 루트를 sys.path에 추가
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd
import pytest

from qcsrc.preprocess import resample, fill_missing, mask_extreme


def _make(values, freq="1h", start="2025-01-01"):
    """DatetimeIndex를 가진 pd.Series 생성 헬퍼."""
    idx = pd.date_range(start=start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# resample
# ---------------------------------------------------------------------------

class TestResample:
    def test_mean_reduces_length(self):
        # 1시간 간격 4개 → 2시간 간격 mean → 2개
        s = _make([10.0, 12.0, 14.0, 16.0], freq="1h")
        r = resample(s, "2h", agg="mean")
        assert len(r) == 2
        assert abs(r.iloc[0] - 11.0) < 1e-9  # mean(10, 12)
        assert abs(r.iloc[1] - 15.0) < 1e-9  # mean(14, 16)

    def test_ffill_preserves_last_valid(self):
        # NaN이 있는 경우 ffill agg는 직전값으로 채움
        s = _make([10.0, np.nan, 12.0, np.nan], freq="1h")
        r = resample(s, "1h", agg="ffill")
        # ffill: 리샘플 후 NaN을 앞값으로 채움
        assert not r.isna().all()

    def test_non_datetime_index_raises(self):
        s = pd.Series([1.0, 2.0], index=[0, 1])
        with pytest.raises(TypeError):
            resample(s, "1h")


# ---------------------------------------------------------------------------
# fill_missing
# ---------------------------------------------------------------------------

class TestFillMissing:
    def test_linear_interpolates_midpoint(self):
        # [10, NaN, 12] → 선형 보간 → [10, 11, 12]
        s = _make([10.0, np.nan, 12.0])
        r = fill_missing(s, method="linear")
        assert not r.isna().any()
        assert abs(r.iloc[1] - 11.0) < 1e-6

    def test_ffill_propagates_forward(self):
        s = _make([10.0, np.nan, np.nan, 14.0])
        r = fill_missing(s, method="ffill")
        assert r.iloc[1] == 10.0
        assert r.iloc[2] == 10.0

    def test_bfill_propagates_backward(self):
        s = _make([np.nan, np.nan, 12.0])
        r = fill_missing(s, method="bfill")
        assert r.iloc[0] == 12.0
        assert r.iloc[1] == 12.0

    def test_invalid_method_raises(self):
        s = _make([1.0, 2.0])
        with pytest.raises(ValueError):
            fill_missing(s, method="cubic")


# ---------------------------------------------------------------------------
# mask_extreme
# ---------------------------------------------------------------------------

class TestMaskExtreme:
    def test_within_range_unchanged(self):
        s = _make([0.0, 10.0, 20.0])
        r = mask_extreme(s, vmin=-5.0, vmax=25.0)
        assert not r.isna().any()

    def test_out_of_range_becomes_nan(self):
        # -10 은 vmin 미만, 50 은 vmax 초과
        s = _make([-10.0, 5.0, 50.0])
        r = mask_extreme(s, vmin=0.0, vmax=40.0)
        assert np.isnan(r.iloc[0])
        assert not np.isnan(r.iloc[1])
        assert np.isnan(r.iloc[2])

    def test_all_valid_no_nan(self):
        s = _make([1.0, 2.0, 3.0])
        r = mask_extreme(s, vmin=0.0, vmax=10.0)
        assert r.isna().sum() == 0
