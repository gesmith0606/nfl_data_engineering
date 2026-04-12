"""Unified evaluation: production heuristic + actual points as standalone functions.

Extracts the EXACT production heuristic logic from projection_engine.py into
reusable functions that can be called on any player-week DataFrame (including
the full feature vector from player_feature_engineering). This eliminates the
train/eval mismatch where residual models were trained against a simplified
heuristic but evaluated against the production heuristic.

Key functions:
    compute_production_heuristic: Reproduce production projected points.
    compute_actual_fantasy_points: Compute actual points from raw stats.
    build_opp_rankings: Build opponent rankings from Bronze data.

The heuristic replicates projection_engine.py exactly:
    1. _weighted_baseline (RECENCY_WEIGHTS: roll3=0.30, roll6=0.15, std=0.55)
    2. _usage_multiplier [0.80, 1.15]
    3. _matchup_factor [0.75, 1.25]
    4. calculate_fantasy_points_df
    5. PROJECTION_CEILING_SHRINKAGE (12/18/23 pt thresholds)

Does NOT include:
    - Vegas multiplier (not available in historical feature data)
    - Bye week zeroing (not applicable to training/backtest data)
    - Injury adjustments (separate layer)
"""

import glob
import logging
import os
from typing import List, Optional

import numpy as np
import pandas as pd

from projection_engine import (
    POSITION_STAT_PROFILE,
    compute_heuristic_baseline,
)
from scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
_BRONZE_DIR = os.path.join(_BASE_DIR, "data", "bronze")


# ---------------------------------------------------------------------------
# Production heuristic
# ---------------------------------------------------------------------------


def compute_production_heuristic(
    pos_data: pd.DataFrame,
    position: str,
    opp_rankings: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.Series:
    """Reproduce the production heuristic on a player-week DataFrame.

    Thin wrapper around ``projection_engine.compute_heuristic_baseline``,
    the single source of truth for heuristic computation.  Signature is
    preserved for backward compatibility with all existing call sites in
    ``hybrid_projection.py`` and ``bayesian_projection.py``.

    Applies the full production pipeline:
    1. _weighted_baseline (roll3/roll6/std blending with RECENCY_WEIGHTS)
    2. _usage_multiplier [0.80, 1.15]
    3. _matchup_factor [0.75, 1.25]
    4. calculate_fantasy_points_df
    5. PROJECTION_CEILING_SHRINKAGE (12/18/23 pt thresholds)

    Does NOT include Vegas multiplier, bye week zeroing, or injury adjustments.

    Args:
        pos_data: Position-filtered feature DataFrame with rolling columns
            (e.g. rushing_yards_roll3, rushing_yards_roll6, rushing_yards_std).
        position: Position code ('QB', 'RB', 'WR', 'TE').
        opp_rankings: Opponent rankings DataFrame compatible with
            _matchup_factor. Can be empty (matchup factor defaults to 1.0).
        scoring_format: Scoring format string.

    Returns:
        Series of production heuristic fantasy points aligned to pos_data.index.
    """
    return compute_heuristic_baseline(pos_data, position, opp_rankings, scoring_format)


# ---------------------------------------------------------------------------
# Actual fantasy points
# ---------------------------------------------------------------------------


def compute_actual_fantasy_points(
    df: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.Series:
    """Compute actual fantasy points from raw stat columns.

    Args:
        df: DataFrame with actual stat columns (passing_yards, etc.).
        scoring_format: Scoring format string.

    Returns:
        Series of actual fantasy points aligned to df.index.
    """
    work = calculate_fantasy_points_df(
        df.copy(), scoring_format=scoring_format, output_col="actual_pts"
    )
    return work["actual_pts"]


# ---------------------------------------------------------------------------
# Opponent rankings builder
# ---------------------------------------------------------------------------


def build_opp_rankings(
    seasons: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Build opponent positional rankings from Bronze data.

    Loads Bronze weekly and schedule data and computes opponent rankings
    using player_analytics.compute_opponent_rankings.

    Args:
        seasons: Seasons to include. Defaults to PLAYER_DATA_SEASONS.

    Returns:
        Opponent rankings DataFrame compatible with _matchup_factor.
        Empty DataFrame on failure.
    """
    from config import PLAYER_DATA_SEASONS

    if seasons is None:
        seasons = PLAYER_DATA_SEASONS

    try:
        # Load weekly data
        dfs = []
        for season in seasons:
            files = sorted(
                glob.glob(
                    os.path.join(
                        _BRONZE_DIR, f"players/weekly/season={season}/*.parquet"
                    )
                )
            )
            if files:
                dfs.append(pd.read_parquet(files[-1]))

        if not dfs:
            logger.warning("No Bronze weekly data for opponent rankings")
            return pd.DataFrame()

        weekly_df = pd.concat(dfs, ignore_index=True)
        if (
            "air_yards" not in weekly_df.columns
            and "receiving_air_yards" in weekly_df.columns
        ):
            weekly_df["air_yards"] = weekly_df["receiving_air_yards"].fillna(0)

        # Load schedules
        sched_dfs = []
        for season in seasons:
            for pattern in [
                f"games/season={season}/*.parquet",
                f"schedules/season={season}/*.parquet",
            ]:
                files = sorted(glob.glob(os.path.join(_BRONZE_DIR, pattern)))
                if files:
                    sdf = pd.read_parquet(files[-1])
                    if "season" not in sdf.columns:
                        sdf["season"] = season
                    sched_dfs.append(sdf)
                    break

        schedules_df = (
            pd.concat(sched_dfs, ignore_index=True) if sched_dfs else pd.DataFrame()
        )

        from player_analytics import compute_opponent_rankings

        opp_rankings = compute_opponent_rankings(weekly_df, schedules_df)
        logger.info("Built opponent rankings: %d rows", len(opp_rankings))
        return opp_rankings

    except Exception as e:
        logger.warning("Failed to build opponent rankings: %s", e)
        return pd.DataFrame()
