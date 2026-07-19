"""Tests for src/draft_tiers.py -- positional tier clustering at natural gaps."""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_tiers import compute_tiers  # noqa: E402


def _synthetic_position(
    position: str, n: int, tier_breaks: list, base: float = 300.0, seed: int = 0
):
    """Build a synthetic sorted-desc points column with deliberate cliffs.

    ``tier_breaks`` is a list of indices (0-based, into the *sorted*
    sequence) where a big point cliff should occur, so the caller knows
    exactly how many tiers to expect. Gentle (non-break) drops carry a
    little noise -- a perfectly constant decline is unrealistic and would
    give the rolling std a degenerate zero, which is not what "natural gap"
    detection is meant to handle.
    """
    rng = np.random.default_rng(seed)
    pts = []
    val = base
    for i in range(n):
        if i in tier_breaks:
            val -= 40.0  # a deliberate cliff
        else:
            val -= max(0.5, 2.0 + rng.normal(0, 0.4))  # gentle, noisy decline
        pts.append(val)
    rows = [
        {"player_id": f"{position}{i}", "position": position, "projected_season_points": p}
        for i, p in enumerate(pts)
    ]
    return rows


def test_tiers_split_at_deliberate_cliffs():
    # 4 tiers of 6 players each, separated by a 40-pt cliff.
    breaks = [6, 12, 18]
    rows = _synthetic_position("WR", 24, breaks)
    df = pd.DataFrame(rows)
    tiers = compute_tiers(df)

    ordered = df.assign(tier=tiers).sort_values(
        "projected_season_points", ascending=False
    )
    assert ordered["tier"].nunique() == 4
    # First 6 (best) players share tier 1, next 6 share tier 2, etc.
    tier_values = ordered["tier"].to_numpy()
    assert len(set(tier_values[:6])) == 1
    assert len(set(tier_values[6:12])) == 1
    assert tier_values[0] != tier_values[6]
    assert tier_values[6] != tier_values[12]


def test_tier_is_monotonic_non_decreasing_as_points_decrease():
    rng = np.random.default_rng(42)
    n = 60
    # Realistic-ish shape: sharp early drop-off, flattening tail, some noise.
    pts = 350 - np.cumsum(rng.uniform(0.5, 6.0, size=n))
    rows = [
        {"player_id": f"RB{i}", "position": "RB", "projected_season_points": p}
        for i, p in enumerate(pts)
    ]
    df = pd.DataFrame(rows)
    tiers = compute_tiers(df)

    ordered = df.assign(tier=tiers).sort_values(
        "projected_season_points", ascending=False
    )
    tier_seq = ordered["tier"].to_numpy()
    assert all(tier_seq[i] <= tier_seq[i + 1] for i in range(len(tier_seq) - 1))


def test_nan_points_get_nan_tier():
    rows = [
        {"player_id": "d1", "position": "DST", "projected_season_points": np.nan},
        {"player_id": "d2", "position": "DST", "projected_season_points": np.nan},
        {"player_id": "wr1", "position": "WR", "projected_season_points": 300.0},
        {"player_id": "wr2", "position": "WR", "projected_season_points": 250.0},
    ]
    df = pd.DataFrame(rows)
    tiers = compute_tiers(df)
    assert pd.isna(tiers.loc[df["position"] == "DST"]).all()
    assert tiers.loc[df["position"] == "WR"].notna().all()


def test_realistic_pool_lands_in_sane_tier_count_per_position():
    """QB/RB/WR/TE pools of realistic size should land in roughly 5-10 tiers."""
    rng = np.random.default_rng(7)
    rows = []
    specs = {
        "QB": (32, 380, 130),
        "RB": (65, 340, 40),
        "WR": (80, 320, 30),
        "TE": (40, 260, 40),
    }
    for pos, (n, top, floor) in specs.items():
        # A smooth exponential-ish decay from top to floor, plus noise --
        # mimics real fantasy point distributions (elite tier, steep drop,
        # long flat replacement-level tail).
        curve = floor + (top - floor) * np.exp(-np.linspace(0, 3, n))
        noisy = curve + rng.normal(0, 2.0, size=n)
        for i, pts in enumerate(sorted(noisy, reverse=True)):
            rows.append(
                {
                    "player_id": f"{pos}{i}",
                    "position": pos,
                    "projected_season_points": float(pts),
                }
            )
    df = pd.DataFrame(rows)
    tiers = compute_tiers(df)
    out = df.assign(tier=tiers)

    for pos in specs:
        n_tiers = out.loc[out["position"] == pos, "tier"].nunique()
        assert 3 <= n_tiers <= 10, f"{pos} landed in {n_tiers} tiers"


def test_max_tiers_cap_is_respected():
    # Force many small cliffs -- without a cap this would produce far more
    # than max_tiers tiers.
    breaks = list(range(1, 20))
    rows = _synthetic_position("QB", 20, breaks)
    df = pd.DataFrame(rows)
    tiers = compute_tiers(df, max_tiers=5)
    assert tiers.nunique() <= 5


def test_empty_dataframe_returns_empty_series():
    df = pd.DataFrame(columns=["player_id", "position", "projected_season_points"])
    tiers = compute_tiers(df)
    assert len(tiers) == 0


def test_single_player_position_gets_tier_one():
    df = pd.DataFrame(
        [{"player_id": "k1", "position": "K", "projected_season_points": 120.0}]
    )
    tiers = compute_tiers(df)
    assert tiers.iloc[0] == 1
