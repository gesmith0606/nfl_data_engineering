"""Tests for src/draft_availability.py -- pick-availability probability."""

from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_availability import (  # noqa: E402
    prob_gone_before,
    prob_gone_before_vectorized,
)


def test_prob_gone_before_known_value_at_the_mean():
    # adp=10, stdev=5, evaluated exactly at pick 10 -> Phi(0) == 0.5.
    p = prob_gone_before(pick_number=10, adp=10, stdev=5)
    assert p == pytest.approx(0.5, abs=1e-9)


def test_prob_gone_before_far_future_pick_clamps_near_one():
    p = prob_gone_before(pick_number=500, adp=10, stdev=5)
    assert p == pytest.approx(0.99, abs=1e-9)


def test_prob_gone_before_far_past_pick_clamps_near_floor():
    p = prob_gone_before(pick_number=1, adp=200, stdev=5)
    assert p == pytest.approx(0.01, abs=1e-9)


def test_prob_gone_before_uses_fallback_sigma_when_stdev_missing():
    # No stdev -> sigma = max(3.0, 0.15 * adp) = max(3.0, 0.15*40) = 6.0.
    p_none = prob_gone_before(pick_number=40, adp=40, stdev=None)
    p_explicit = prob_gone_before(pick_number=40, adp=40, stdev=6.0)
    assert p_none == pytest.approx(p_explicit, abs=1e-9)
    assert p_none == pytest.approx(0.5, abs=1e-9)  # at the mean either way


def test_prob_gone_before_fallback_sigma_floor_for_low_adp():
    # adp=5 -> 0.15*5=0.75, floored to 3.0.
    p_floor = prob_gone_before(pick_number=8, adp=5, stdev=None)
    p_explicit = prob_gone_before(pick_number=8, adp=5, stdev=3.0)
    assert p_floor == pytest.approx(p_explicit, abs=1e-9)


def test_prob_gone_before_nonfinite_or_nonpositive_stdev_falls_back():
    fallback = prob_gone_before(pick_number=40, adp=40, stdev=6.0)
    assert prob_gone_before(pick_number=40, adp=40, stdev=float("nan")) == pytest.approx(
        fallback, abs=1e-9
    )
    assert prob_gone_before(pick_number=40, adp=40, stdev=0) == pytest.approx(
        fallback, abs=1e-9
    )
    assert prob_gone_before(pick_number=40, adp=40, stdev=-5) == pytest.approx(
        fallback, abs=1e-9
    )


def test_prob_gone_before_monotonic_in_pick_number():
    adp, stdev = 30, 8
    picks = [1, 10, 20, 30, 40, 50, 100]
    probs = [prob_gone_before(p, adp, stdev) for p in picks]
    assert all(probs[i] <= probs[i + 1] for i in range(len(probs) - 1))


def test_prob_gone_before_always_within_clamped_bounds():
    for pick in (1, 10, 100, 1000):
        for adp in (1, 50, 200):
            p = prob_gone_before(pick, adp, None)
            assert 0.01 <= p <= 0.99


# ---------------------------------------------------------------------------
# Vectorized
# ---------------------------------------------------------------------------


def test_vectorized_matches_scalar_with_explicit_stdev():
    df = pd.DataFrame(
        {
            "player_id": ["a", "b", "c"],
            "adp_rank": [10.0, 40.0, 100.0],
            "stdev": [5.0, np.nan, 12.0],
        }
    )
    result = prob_gone_before_vectorized(df, pick_number=40)
    expected = [
        prob_gone_before(40, 10.0, 5.0),
        prob_gone_before(40, 40.0, None),  # NaN stdev -> fallback
        prob_gone_before(40, 100.0, 12.0),
    ]
    np.testing.assert_allclose(result.to_numpy(), expected, atol=1e-9)


def test_vectorized_auto_detects_adp_stdev_column_name():
    df = pd.DataFrame(
        {"adp_rank": [10.0], "adp_stdev": [5.0]}
    )
    result = prob_gone_before_vectorized(df, pick_number=10)
    assert result.iloc[0] == pytest.approx(0.5, abs=1e-9)


def test_vectorized_no_stdev_column_uses_fallback_for_all_rows():
    df = pd.DataFrame({"adp_rank": [10.0, 40.0, 100.0]})
    result = prob_gone_before_vectorized(df, pick_number=40)
    expected = [prob_gone_before(40, adp, None) for adp in (10.0, 40.0, 100.0)]
    np.testing.assert_allclose(result.to_numpy(), expected, atol=1e-9)


def test_vectorized_missing_adp_yields_nan_not_error():
    df = pd.DataFrame({"adp_rank": [10.0, np.nan, 30.0]})
    result = prob_gone_before_vectorized(df, pick_number=20)
    assert math.isnan(result.iloc[1])
    assert not math.isnan(result.iloc[0])
    assert not math.isnan(result.iloc[2])


def test_vectorized_empty_dataframe_returns_empty_series():
    df = pd.DataFrame(columns=["adp_rank"])
    result = prob_gone_before_vectorized(df, pick_number=10)
    assert len(result) == 0


def test_vectorized_missing_adp_column_returns_all_nan():
    df = pd.DataFrame({"player_id": ["a", "b"]})
    result = prob_gone_before_vectorized(df, pick_number=10)
    assert result.isna().all()


def test_vectorized_results_clamped():
    df = pd.DataFrame({"adp_rank": [1.0, 500.0]})
    result = prob_gone_before_vectorized(df, pick_number=250, stdev_col=None)
    assert (result >= 0.01).all() and (result <= 0.99).all()
