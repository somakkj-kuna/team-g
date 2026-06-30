# -*- coding: utf-8-sig -*-
"""checks/ 모듈 단위 테스트."""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd
import pytest

from qcsrc.checks import FLAG_GOOD, FLAG_SUSPECT, FLAG_BAD, FLAG_MISSING
from qcsrc.checks import range_check, spike_check, stuck_check, roc_check, edge_check
from qcsrc.checks import attenuated_check, dynamic_range_check


def _make(values, freq="1h", start="2025-01-01"):
    idx = pd.date_range(start=start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


# ---------------------------------------------------------------------------
# range_check
# ---------------------------------------------------------------------------

class TestRangeCheck:
    def test_normal_data_all_good(self):
        s = _make([0.0, 10.0, 20.0, 30.0])
        flags = range_check.run(s, vmin=-2.0, vmax=40.0)
        assert (flags == FLAG_GOOD).all()

    def test_below_min_flagged_bad(self):
        s = _make([-5.0, 10.0])
        flags = range_check.run(s, vmin=-2.0, vmax=40.0)
        assert flags.iloc[0] == FLAG_BAD
        assert flags.iloc[1] == FLAG_GOOD

    def test_above_max_flagged_bad(self):
        s = _make([10.0, 50.0])
        flags = range_check.run(s, vmin=-2.0, vmax=40.0)
        assert flags.iloc[0] == FLAG_GOOD
        assert flags.iloc[1] == FLAG_BAD

    def test_nan_preserved_as_missing(self):
        s = _make([np.nan, 10.0])
        flags = range_check.run(s, vmin=0.0, vmax=20.0)
        assert flags.iloc[0] == FLAG_MISSING
        assert flags.iloc[1] == FLAG_GOOD

    def test_all_nan_all_missing(self):
        s = _make([np.nan, np.nan])
        flags = range_check.run(s, vmin=0.0, vmax=100.0)
        assert (flags == FLAG_MISSING).all()


# ---------------------------------------------------------------------------
# spike_check (3종 알고리즘)
# ---------------------------------------------------------------------------

class TestSpikeCheckZscore:
    def test_smooth_series_no_spike(self):
        s = _make([20.0, 20.1, 20.2, 20.1, 20.0, 20.1])
        flags = spike_check.run(s, method="zscore", threshold=3.0)
        assert (flags == FLAG_GOOD).all()

    def test_clear_spike_flagged_bad(self):
        # 배경 7점(~20.0), 마지막에 100.0 삽입 → z ≈ 2.5 > threshold=2.0
        s = _make([20.0, 20.1, 20.0, 20.1, 20.0, 20.1, 20.0, 100.0])
        flags = spike_check.run(s, method="zscore", threshold=2.0)
        assert flags.iloc[7] == FLAG_BAD

    def test_nan_not_spiked(self):
        s = _make([20.0, np.nan, 20.0])
        flags = spike_check.run(s, method="zscore", threshold=2.0)
        assert flags.iloc[1] == FLAG_MISSING

    def test_single_value_no_spike(self):
        s = _make([20.0])
        flags = spike_check.run(s, method="zscore", threshold=3.0)
        assert flags.iloc[0] == FLAG_GOOD


class TestSpikeCheckIqr:
    def test_no_outlier_all_good(self):
        # 균일 분포 내 데이터
        s = _make([10.0, 11.0, 12.0, 11.0, 10.5, 11.5])
        flags = spike_check.run(s, method="iqr", threshold=1.5)
        assert (flags == FLAG_GOOD).all()

    def test_extreme_outlier_flagged_bad(self):
        # 대부분 10~12 범위, 극단값 100 삽입
        s = _make([10.0, 11.0, 12.0, 11.0, 10.0, 100.0])
        flags = spike_check.run(s, method="iqr", threshold=1.5)
        assert flags.iloc[5] == FLAG_BAD

    def test_nan_returns_missing(self):
        s = _make([10.0, np.nan, 10.0, 11.0])
        flags = spike_check.run(s, method="iqr", threshold=1.5)
        assert flags.iloc[1] == FLAG_MISSING


class TestSpikeCheckMedian:
    def test_gradual_change_no_spike(self):
        s = _make([10.0, 10.1, 10.2, 10.3, 10.4])
        flags = spike_check.run(s, method="median", threshold=5.0, window=3)
        assert (flags == FLAG_GOOD).all()

    def test_isolated_spike_flagged_bad(self):
        # 정상값 10.x, index 2에 30.0 삽입
        s = _make([10.0, 10.1, 30.0, 10.2, 10.0])
        flags = spike_check.run(s, method="median", threshold=5.0, window=3)
        assert flags.iloc[2] == FLAG_BAD
        assert flags.iloc[0] == FLAG_GOOD
        assert flags.iloc[4] == FLAG_GOOD

    def test_small_deviation_not_flagged(self):
        # 2.0 편차는 threshold=5.0 미만
        s = _make([10.0, 10.0, 12.0, 10.0, 10.0])
        flags = spike_check.run(s, method="median", threshold=5.0, window=3)
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_insufficient_neighbors_skipped(self):
        # 각 점의 이웃이 1개뿐(window=1) → min_neighbors(2) 미충족 → GOOD 유지
        s = _make([99.0, 10.0])
        flags = spike_check.run(s, method="median", threshold=1.0, window=1)
        assert (flags == FLAG_GOOD).all()


# ---------------------------------------------------------------------------
# stuck_check
# ---------------------------------------------------------------------------

class TestStuckCheck:
    def test_changing_values_no_stuck(self):
        s = _make([10.0, 10.1, 10.2, 10.3, 10.4, 10.5])
        flags = stuck_check.run(s, min_change=0.0, window=6)
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_long_run_flagged_bad(self):
        # 6개 연속 동일값, window=6 → 전부 BAD
        s = _make([10.0] * 6 + [10.5])
        flags = stuck_check.run(s, min_change=0.0, window=6)
        for i in range(6):
            assert flags.iloc[i] == FLAG_BAD
        assert flags.iloc[6] == FLAG_GOOD

    def test_short_run_below_window_all_good(self):
        # 3개 연속, window=6 → GOOD
        s = _make([10.0, 10.0, 10.0, 11.0, 12.0])
        flags = stuck_check.run(s, min_change=0.0, window=6)
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_nan_breaks_run(self):
        # NaN이 run을 분리 → 최대 run=2 < window=4 → GOOD
        s = _make([10.0, 10.0, np.nan, 10.0, 10.0])
        flags = stuck_check.run(s, min_change=0.0, window=4)
        assert flags.iloc[0] == FLAG_GOOD
        assert flags.iloc[1] == FLAG_GOOD
        assert flags.iloc[2] == FLAG_MISSING
        assert flags.iloc[3] == FLAG_GOOD
        assert flags.iloc[4] == FLAG_GOOD

    def test_min_change_tolerance(self):
        # 변화량 0.0005 <= min_change=0.001 → 동일 처리 → BAD
        s = _make([10.0000, 10.0005, 10.0010, 10.0015, 11.0])
        flags = stuck_check.run(s, min_change=0.001, window=4)
        for i in range(4):
            assert flags.iloc[i] == FLAG_BAD
        assert flags.iloc[4] == FLAG_GOOD


# ---------------------------------------------------------------------------
# roc_check
# ---------------------------------------------------------------------------

class TestRocCheck:
    def test_slow_change_all_good(self):
        # 매시간 0.1°C 변화 → rate=0.1/h < max_rate=5.0
        s = _make([10.0, 10.1, 10.2, 10.3])
        flags = roc_check.run(s, max_rate=5.0)
        assert (flags == FLAG_GOOD).all()

    def test_rapid_change_flagged_bad(self):
        # 1시간에 20°C 변화 → rate=20/h > 5.0
        s = _make([10.0, 30.0, 30.1])
        flags = roc_check.run(s, max_rate=5.0)
        assert flags.iloc[0] == FLAG_GOOD   # 첫 점: 이전값 없음
        assert flags.iloc[1] == FLAG_BAD    # 20/h > 5
        assert flags.iloc[2] == FLAG_GOOD   # 0.1/h < 5

    def test_nan_skipped_slow_across_gap(self):
        # NaN 건너뜀, 2h에 1°C 변화 → rate=0.5/h < 5.0
        s = _make([10.0, np.nan, 11.0])
        flags = roc_check.run(s, max_rate=5.0)
        assert flags.iloc[1] == FLAG_MISSING
        assert flags.iloc[2] == FLAG_GOOD

    def test_nan_skipped_rapid_across_gap(self):
        # NaN 건너뜀, 2h에 20°C 변화 → rate=10/h > 5.0
        s = _make([10.0, np.nan, 30.0])
        flags = roc_check.run(s, max_rate=5.0)
        assert flags.iloc[2] == FLAG_BAD

    def test_non_datetime_index_raises(self):
        s = pd.Series([1.0, 2.0], index=[0, 1])
        with pytest.raises(TypeError):
            roc_check.run(s, max_rate=5.0)


# ---------------------------------------------------------------------------
# edge_check
# ---------------------------------------------------------------------------

class TestEdgeCheck:
    def _make_with_gap(self):
        """36h 갭 이후 이상값(20.0)이 있는 시계열."""
        times = pd.DatetimeIndex([
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2025-01-01 01:00"),
            pd.Timestamp("2025-01-01 02:00"),
            pd.Timestamp("2025-01-03 00:00"),  # 46h 갭
            pd.Timestamp("2025-01-03 01:00"),
            pd.Timestamp("2025-01-03 02:00"),
        ])
        vals = [10.0, 10.1, 10.2, 20.0, 10.5, 10.6]
        return pd.Series(vals, index=times, dtype=float)

    def test_no_gap_no_flag(self):
        # 1시간 간격 연속 데이터, 갭 없음 → BAD 없음
        s = _make([10.0, 10.1, 10.2, 10.3, 10.4, 10.5])
        flags = edge_check.run(s, gap_min="24h", fwd_scan="4h",
                               n_start=3, abs_fail=5.0, abs_suspect=2.0)
        assert (flags == FLAG_GOOD).all()

    def test_outlier_after_gap_flagged_bad(self):
        s = self._make_with_gap()
        flags = edge_check.run(s, gap_min="24h", fwd_scan="4h",
                               n_start=3, abs_fail=5.0, abs_suspect=2.0)
        # 갭 이후 첫 값 20.0: fwd=[10.5, 10.6], ref=10.55, d=9.45 >= 5.0 → BAD
        assert flags.iloc[3] == FLAG_BAD
        # 갭 이전 첫 세 값: fwd=각각 10.x 수준 → GOOD
        assert flags.iloc[0] == FLAG_GOOD

    def test_normal_after_gap_not_flagged(self):
        # 갭 이후 값이 정상 범위이면 BAD 없음
        times = pd.DatetimeIndex([
            pd.Timestamp("2025-01-01 00:00"),
            pd.Timestamp("2025-01-01 01:00"),
            pd.Timestamp("2025-01-03 00:00"),  # 47h 갭
            pd.Timestamp("2025-01-03 01:00"),
            pd.Timestamp("2025-01-03 02:00"),
        ])
        vals = [10.0, 10.1, 10.2, 10.3, 10.4]
        s = pd.Series(vals, index=times, dtype=float)
        flags = edge_check.run(s, gap_min="24h", fwd_scan="4h",
                               n_start=3, abs_fail=5.0, abs_suspect=2.0)
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_nan_in_series_handled(self):
        # NaN이 포함된 경우 MISSING 처리, 오류 없음
        s = _make([10.0, np.nan, 10.1, 10.2])
        flags = edge_check.run(s, gap_min="24h", fwd_scan="4h",
                               n_start=3, abs_fail=5.0, abs_suspect=2.0)
        assert flags.iloc[1] == FLAG_MISSING


# ---------------------------------------------------------------------------
# attenuated_check (Phase 1)
# ---------------------------------------------------------------------------

class TestAttenuatedCheck:
    def test_normal_variation_all_good(self):
        # 변동량이 충분히 큰 정상 데이터 → 전부 GOOD
        vals = [20.0 + 0.5 * i for i in range(20)]
        s = _make(vals)
        flags = attenuated_check.run(s, window="5h", min_var=0.01, metric="std")
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_flat_signal_flagged_suspect(self):
        # 완전 동일값(std=0) → SUSPECT (window 이후부터 탐지)
        s = _make([20.0] * 20)
        flags = attenuated_check.run(s, window="5h", min_var=0.01, metric="std")
        # rolling window 채운 이후 구간은 SUSPECT
        assert (flags.iloc[5:] == FLAG_SUSPECT).all()

    def test_range_metric(self):
        # metric='range' 로도 동일 탐지
        s = _make([20.0] * 20)
        flags = attenuated_check.run(s, window="5h", min_var=0.01, metric="range")
        assert (flags.iloc[5:] == FLAG_SUSPECT).all()

    def test_nan_preserved_as_missing(self):
        s = _make([np.nan] + [20.0] * 15)
        flags = attenuated_check.run(s, window="5h", min_var=0.5, metric="std")
        assert flags.iloc[0] == FLAG_MISSING

    def test_invalid_metric_raises(self):
        s = _make([1.0, 2.0])
        with pytest.raises(ValueError):
            attenuated_check.run(s, window="2h", min_var=0.01, metric="bad_metric")

    def test_non_datetime_index_raises(self):
        s = pd.Series([1.0, 2.0], index=[0, 1])
        with pytest.raises(TypeError):
            attenuated_check.run(s, window="2h", min_var=0.01)


# ---------------------------------------------------------------------------
# spike_check — tukey53h method (Phase 2)
# ---------------------------------------------------------------------------

class TestSpikeTukey53H:
    def test_normal_data_all_good(self):
        # 노이즈 없는 단조 시계열 → 전부 GOOD
        s = _make([20.0 + 0.01 * i for i in range(30)])
        flags = spike_check.run(s, method="tukey53h", threshold=3.0)
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_isolated_spike_flagged_bad(self):
        # 자연 변동이 있는 신호에 큰 스파이크 삽입 → BAD
        # 완전 평탄 신호는 MAD=0 → 탐지 불가 (그 경우는 stuck/attenuated 검사 담당)
        rng = np.random.default_rng(42)
        base = [20.0 + 0.5 * np.sin(i * 0.4) + 0.1 * rng.normal() for i in range(21)]
        base[10] = 99.0
        s = _make(base)
        flags = spike_check.run(s, method="tukey53h", threshold=3.0)
        assert flags.iloc[10] == FLAG_BAD

    def test_flat_signal_mad_guard(self):
        # 완전 평탄 신호(MAD=0) → 오탐 없이 전부 GOOD
        s = _make([20.0] * 20)
        flags = spike_check.run(s, method="tukey53h", threshold=3.0)
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_nan_preserved_as_missing(self):
        vals = [np.nan] + [20.0] * 5 + [99.0] + [20.0] * 5
        s = _make(vals)
        flags = spike_check.run(s, method="tukey53h", threshold=3.0)
        assert flags.iloc[0] == FLAG_MISSING

    def test_invalid_method_raises(self):
        s = _make([1.0, 2.0])
        with pytest.raises(ValueError):
            spike_check.run(s, method="unknown")


# ---------------------------------------------------------------------------
# dynamic_range_check (Phase 3)
# ---------------------------------------------------------------------------

class TestDynamicRangeCheck:
    # 1월~12월 동일 범위 테이블 (테스트 편의)
    _TABLE_2 = {m: (-2.0, 35.0) for m in range(1, 13)}

    def test_normal_data_all_good(self):
        s = _make([10.0, 20.0, 30.0])
        flags = dynamic_range_check.run(s, quantile_table=self._TABLE_2)
        assert (flags[~s.isna()] == FLAG_GOOD).all()

    def test_above_max_flagged_bad(self):
        s = _make([10.0, 99.0])
        flags = dynamic_range_check.run(s, quantile_table=self._TABLE_2)
        assert flags.iloc[0] == FLAG_GOOD
        assert flags.iloc[1] == FLAG_BAD

    def test_below_min_flagged_bad(self):
        s = _make([-10.0, 10.0])
        flags = dynamic_range_check.run(s, quantile_table=self._TABLE_2)
        assert flags.iloc[0] == FLAG_BAD
        assert flags.iloc[1] == FLAG_GOOD

    def test_four_value_bounds_suspect(self):
        # (lo_bad, lo_sus, hi_sus, hi_bad) = (-5, -1, 30, 35)
        table_4 = {m: (-5.0, -1.0, 30.0, 35.0) for m in range(1, 13)}
        s = _make([-3.0, 10.0, 32.0, 40.0])
        flags = dynamic_range_check.run(s, quantile_table=table_4)
        assert flags.iloc[0] == FLAG_SUSPECT   # -3 → lo_bad~lo_sus 사이
        assert flags.iloc[1] == FLAG_GOOD
        assert flags.iloc[2] == FLAG_SUSPECT   # 32 → hi_sus~hi_bad 사이
        assert flags.iloc[3] == FLAG_BAD       # 40 > hi_bad

    def test_missing_month_fallback(self):
        # 1월만 테이블에 있고, fallback_range 적용
        table = {1: (-2.0, 35.0)}
        s = _make([99.0])   # 2025-01-01 → 1월, 테이블 있음
        flags = dynamic_range_check.run(s, quantile_table=table,
                                        fallback_range={"vmin": -2.0, "vmax": 35.0})
        assert flags.iloc[0] == FLAG_BAD

    def test_nan_preserved_as_missing(self):
        s = _make([np.nan, 10.0])
        flags = dynamic_range_check.run(s, quantile_table=self._TABLE_2)
        assert flags.iloc[0] == FLAG_MISSING
        assert flags.iloc[1] == FLAG_GOOD

    def test_non_datetime_index_raises(self):
        s = pd.Series([1.0, 2.0], index=[0, 1])
        with pytest.raises(TypeError):
            dynamic_range_check.run(s, quantile_table=self._TABLE_2)

    def test_invalid_mode_raises(self):
        s = _make([10.0])
        with pytest.raises(ValueError):
            dynamic_range_check.run(s, quantile_table=self._TABLE_2, mode="bad")
