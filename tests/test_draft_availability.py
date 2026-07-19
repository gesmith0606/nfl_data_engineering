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
    expected_best_vorp_at_pick,
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


# ---------------------------------------------------------------------------
# expected_best_vorp_at_pick -- cost-of-waiting
# ---------------------------------------------------------------------------


def test_expected_best_vorp_two_candidate_hand_computed():
    """Two RB candidates -- verify the probability-weighted-sum formula by
    reconstructing it from prob_gone_before (the already-tested primitive)."""
    df = pd.DataFrame(
        {
            "position": ["RB", "RB"],
            "vorp": [50.0, 30.0],
            "adp_rank": [10.0, 20.0],
            "adp_stdev": [5.0, 5.0],
        }
    )
    pick_number = 15

    gone_a = prob_gone_before(pick_number, 10.0, 5.0)
    gone_b = prob_gone_before(pick_number, 20.0, 5.0)
    survive_a = 1.0 - gone_a
    survive_b = 1.0 - gone_b
    # A is processed first (higher VORP): P(A is best) = P(A survives).
    p_a_best = survive_a
    # B is best only if B survives AND A is already gone.
    p_b_best = survive_b * gone_a
    expected = p_a_best * 50.0 + p_b_best * 30.0

    result = expected_best_vorp_at_pick(df, pick_number)
    assert result["RB"] == pytest.approx(expected, abs=1e-9)


def test_expected_best_vorp_matches_single_candidate_when_alone():
    """A lone candidate's expected value is just survival_prob * its own vorp."""
    df = pd.DataFrame(
        {"position": ["WR"], "vorp": [40.0], "adp_rank": [25.0], "adp_stdev": [6.0]}
    )
    pick_number = 30
    survive = 1.0 - prob_gone_before(pick_number, 25.0, 6.0)
    result = expected_best_vorp_at_pick(df, pick_number)
    assert result["WR"] == pytest.approx(survive * 40.0, abs=1e-9)


def test_expected_best_vorp_walk_caps_at_near_certain_survival():
    """Once the top candidate is (near-)certain to survive, the walk stops --
    a much higher-VORP player later in iteration order must never appear
    (it can't, since the pool is walked VORP-descending), and a lower-VORP
    player right behind the capping candidate must not move the total."""
    df = pd.DataFrame(
        {
            "position": ["QB", "QB"],
            # A is a massive favorite to survive to pick 1 (ADP way in the
            # future) -- triggers the >=0.98 survival cap immediately.
            "vorp": [200.0, 100.0],
            "adp_rank": [500.0, 1.0],
            "adp_stdev": [5.0, 5.0],
        }
    )
    pick_number = 1
    result = expected_best_vorp_at_pick(df, pick_number)

    survive_a = 1.0 - prob_gone_before(pick_number, 500.0, 5.0)
    assert survive_a >= 0.98
    # Only A's own contribution -- B (vorp=100) never enters the sum.
    assert result["QB"] == pytest.approx(survive_a * 200.0, abs=1e-9)


def test_expected_best_vorp_excludes_players_missing_vorp_or_adp():
    df = pd.DataFrame(
        {
            "position": ["TE", "TE", "TE"],
            "vorp": [20.0, np.nan, 15.0],
            "adp_rank": [50.0, 55.0, np.nan],
            "adp_stdev": [5.0, 5.0, 5.0],
        }
    )
    pick_number = 40
    result = expected_best_vorp_at_pick(df, pick_number)
    # Only the first row is vorp/adp-complete -- expected value degenerates
    # to that single candidate's survival-weighted vorp.
    survive = 1.0 - prob_gone_before(pick_number, 50.0, 5.0)
    assert result["TE"] == pytest.approx(survive * 20.0, abs=1e-9)


def test_expected_best_vorp_per_position_breakdown():
    df = pd.DataFrame(
        {
            "position": ["RB", "WR"],
            "vorp": [60.0, 45.0],
            "adp_rank": [8.0, 12.0],
            "adp_stdev": [4.0, 4.0],
        }
    )
    result = expected_best_vorp_at_pick(df, pick_number=20)
    assert set(result.keys()) == {"RB", "WR"}
    assert all(v > 0 for v in result.values())


def test_expected_best_vorp_empty_dataframe_returns_empty_dict():
    df = pd.DataFrame(columns=["position", "vorp", "adp_rank"])
    assert expected_best_vorp_at_pick(df, pick_number=10) == {}


def test_expected_best_vorp_missing_required_columns_returns_empty_dict():
    df = pd.DataFrame({"position": ["RB"], "vorp": [10.0]})  # no adp_rank
    assert expected_best_vorp_at_pick(df, pick_number=10) == {}


def test_expected_best_vorp_no_stdev_column_uses_fallback():
    """Missing adp_stdev entirely (legacy sleeper_rank source) must not raise
    -- falls back the same way prob_gone_before does."""
    df = pd.DataFrame({"position": ["RB"], "vorp": [30.0], "adp_rank": [10.0]})
    result = expected_best_vorp_at_pick(df, pick_number=15)
    survive = 1.0 - prob_gone_before(15, 10.0, None)
    assert result["RB"] == pytest.approx(survive * 30.0, abs=1e-9)
