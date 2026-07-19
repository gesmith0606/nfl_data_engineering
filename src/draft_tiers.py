#!/usr/bin/env python3
"""
Positional tier clustering for the draft board.

Within each position, players are sorted by projected points (descending)
and split into tiers at "natural gaps" -- a new tier starts wherever the
point drop from the previous player is unusually large relative to that
position's overall volatility of drops. This turns a flat ranked list into
the tier groupings a human draft cheat-sheet would show (e.g. "Tier 1
RBs", "Tier 2 RBs", ...), which is a much better drafting signal than raw
rank: the gap between rank 4 and rank 5 at a position might be enormous
(tier break) while the gap between rank 12 and rank 13 is trivial (same
tier).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# Minimum point-drop threshold floor so a dead-flat stretch of the pool
# (std ~= 0, e.g. many replacement-level players in a row) doesn't spawn a
# new tier on every single tiny fluctuation.
_EPSILON = 0.5

# Gap-vs-volatility multiplier: a drop must exceed this fraction of the
# position's overall std of drops to count as a tier break. Tuned so
# realistic QB/RB/WR/TE pools land in roughly 5-10 tiers (see
# test_draft_tiers.py).
_GAP_STD_MULTIPLIER = 0.35
def compute_tiers(
    df: pd.DataFrame,
    points_col: str = "projected_season_points",
    position_col: str = "position",
    max_tiers: int = 10,
) -> pd.Series:
    """Assign a positional tier (1 = best) to every row of ``df``.

    Args:
        df: DataFrame of players. Must contain ``points_col`` and
            ``position_col``.
        points_col: Column of projected points to rank/tier by.
        position_col: Column identifying each player's position; tiers are
            computed independently within each position group.
        max_tiers: Hard cap on the number of tiers produced per position.
            When the natural-gap algorithm would produce more, the smallest
            gaps are merged first (largest gaps always win a tier break).

    Returns:
        A ``pd.Series`` aligned to ``df.index`` of tier integers (``1``
        = best). Rows with NaN points (e.g. DST with no model) get NaN.
    """
    tier = pd.Series(np.nan, index=df.index, dtype=float)
    if df.empty or points_col not in df.columns or position_col not in df.columns:
        return tier

    for _, group in df.groupby(position_col):
        pts = group[points_col]
        valid_idx = pts[pts.notna()].index
        if len(valid_idx) == 0:
            continue
        sub = group.loc[valid_idx, points_col].sort_values(ascending=False)
        n = len(sub)
        if n == 1:
            tier.loc[sub.index] = 1
            continue

        # drops[i] = point drop causing sub.iloc[i+1] to start (>= 0).
        drops = (-sub.diff().dropna()).to_numpy()
        # Volatility of this position's successive drops, rolled up across the
        # whole position (rather than a narrow local window): a narrow window
        # gets contaminated by the cliffs themselves (the very thing we're
        # trying to detect), spiking right after a tier break and producing
        # spurious extra splits. A position-wide std is a stable yardstick
        # for "is this drop unusually large for this position".
        std = float(np.std(drops)) if len(drops) > 1 else 0.0
        threshold = max(_GAP_STD_MULTIPLIER * std, _EPSILON)
        is_break = drops > threshold  # is_break[i] -> boundary before sub.iloc[i+1]

        boundaries = [i + 1 for i, b in enumerate(is_break) if b]  # 0-based positions in sub

        if len(boundaries) + 1 > max_tiers:
            # Keep the largest gaps as boundaries; drop the smallest ones
            # first until we're within the cap.
            excess = (len(boundaries) + 1) - max_tiers
            boundary_gap = sorted(
                ((b, drops[b - 1]) for b in boundaries), key=lambda x: x[1]
            )
            drop_set = {b for b, _ in boundary_gap[:excess]}
            boundaries = [b for b in boundaries if b not in drop_set]

        tier_ids = np.ones(n, dtype=int)
        current = 1
        boundary_set = set(boundaries)
        for i in range(1, n):
            if i in boundary_set:
                current += 1
            tier_ids[i] = current

        tier.loc[sub.index] = tier_ids

    return tier


__all__ = ["compute_tiers"]
