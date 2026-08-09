"""Early-season shrinkage toward a prior-season per-game baseline.

Lever 1 from ``.planning/CONSENSUS_ERROR_DECOMPOSITION.md`` finding #1: weeks
3-6 lose ~0.3-0.46 MAE to Sleeper/ESPN across QB/RB/WR/TE, worst of any
week band. Hypothesis: our rolling-average features have at most 1-3
current-season games of history that early, so projections lean too hard on
a thin in-season sample, while consensus sources blend in
preseason/analyst priors that adapt to role changes faster.

This module blends a small, decaying weight of the player's PRIOR-SEASON
per-game score into the projection for weeks 3-6 only (zero elsewhere),
mirroring the ``prop_implied.apply_props_blend`` pattern: a pure
``proj' = (1-w)*proj + w*prior`` blend, opt-in via a CLI flag, with
provenance columns for auditability.

Prior-season (not preseason-lines) is deliberate: it is available for every
backtest season (2022-2024) as well as production, whereas the preseason
props/consensus parquet only exists from 2026 onward.
"""

from typing import Dict, Optional

import pandas as pd

from scoring_calculator import calculate_fantasy_points_df

#: Decaying blend weight by week — heaviest in week 3 (least current-season
#: signal), tapering to 0.1 by week 6, and 0 (untouched) outside 3-6.
EARLY_SEASON_PRIOR_WEIGHTS: Dict[int, float] = {3: 0.4, 4: 0.3, 5: 0.2, 6: 0.1}

#: Minimum prior-season games played to trust the per-game average — below
#: this the sample is noisier than the rolling-average baseline it would
#: replace, so the player gets no adjustment.
MIN_PRIOR_GAMES = 6

#: Positions this lever applies to (per CONSENSUS_ERROR_DECOMPOSITION.md,
#: all four skill positions show the same early-season pattern).
EARLY_SEASON_PRIOR_POSITIONS = {"QB", "RB", "WR", "TE"}


def compute_prior_season_ppg(
    prior_weekly_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
    min_games: int = MIN_PRIOR_GAMES,
) -> pd.DataFrame:
    """Per-player prior-season points-per-game, gated on a minimum sample.

    Args:
        prior_weekly_df: Bronze ``players/weekly`` rows for season S-1
            (all weeks, all positions) — e.g. from
            ``data/bronze/players/weekly/season={S-1}``.
        scoring_format: Scoring format key for ``calculate_fantasy_points_df``.
        min_games: Minimum games played in the prior season to include a
            player. Players below this (or entirely absent) get no row here,
            which ``apply_early_season_prior`` treats as "no adjustment."

    Returns:
        DataFrame with columns ``player_id``, ``prior_ppg``, ``prior_games``.
        Empty (with those columns) if the input is empty or lacks
        ``player_id``.
    """
    empty = pd.DataFrame(columns=["player_id", "prior_ppg", "prior_games"])
    if (
        prior_weekly_df is None
        or prior_weekly_df.empty
        or "player_id" not in prior_weekly_df.columns
    ):
        return empty

    scored = calculate_fantasy_points_df(
        prior_weekly_df, scoring_format=scoring_format, output_col="_prior_game_pts"
    )
    grouped = (
        scored.groupby("player_id")["_prior_game_pts"]
        .agg(prior_ppg="mean", prior_games="count")
        .reset_index()
    )
    return grouped[grouped["prior_games"] >= min_games].reset_index(drop=True)


def apply_early_season_prior(
    proj_df: pd.DataFrame,
    prior_ppg_df: pd.DataFrame,
    week: int,
    scale: float = 1.0,
    weight_schedule: Optional[Dict[int, float]] = None,
    points_col: str = "projected_points",
) -> pd.DataFrame:
    """Blend ``points_col`` toward the player's prior-season PPG, weeks 3-6.

    ``proj' = (1-w)*proj + w*prior_ppg`` where
    ``w = scale * weight_schedule.get(week, 0)`` — zero (no-op) outside the
    weight schedule's weeks, for players with no qualifying prior-season row,
    and for positions outside ``EARLY_SEASON_PRIOR_POSITIONS``.

    Args:
        proj_df: Projections with ``player_id``, ``position``, ``points_col``.
        prior_ppg_df: Output of :func:`compute_prior_season_ppg`.
        week: Current projection week (int).
        scale: Single knob multiplying the fixed weight schedule (default
            1.0 = schedule as-is; 0 disables the blend entirely).
        weight_schedule: Per-week blend weight (default
            ``EARLY_SEASON_PRIOR_WEIGHTS``).
        points_col: Points column to blend in place.

    Returns:
        ``proj_df`` with ``points_col`` updated and a new
        ``prior_season_ppg`` provenance column (NaN where unavailable).
    """
    schedule = (
        weight_schedule if weight_schedule is not None else EARLY_SEASON_PRIOR_WEIGHTS
    )
    proj = proj_df.copy()
    proj["prior_season_ppg"] = float("nan")

    w = schedule.get(week, 0.0) * scale
    if w <= 0:
        return proj
    if prior_ppg_df is None or prior_ppg_df.empty or "player_id" not in proj.columns:
        return proj

    lookup = prior_ppg_df.drop_duplicates("player_id").copy()
    lookup["player_id"] = lookup["player_id"].astype(str)
    lookup = lookup.set_index("player_id")["prior_ppg"]
    prior = proj["player_id"].astype(str).map(lookup)
    proj["prior_season_ppg"] = prior

    mask = proj["position"].isin(EARLY_SEASON_PRIOR_POSITIONS) & prior.notna()
    if mask.any():
        proj.loc[mask, points_col] = (
            (1.0 - w) * proj.loc[mask, points_col] + w * prior[mask]
        ).round(2)
    return proj
