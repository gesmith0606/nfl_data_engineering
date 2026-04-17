#!/usr/bin/env python3
"""
Next Gen Stats Feature Engineering

Integrates NFL Next Gen Stats (NGS) data into the projection pipeline.
NGS provides tracking-based metrics that capture player quality beyond
box score stats:
- Receivers: separation, cushion, YAC above expected
- QBs: completion % above expected, aggressiveness, time to throw
- RBs: rush yards over expected, efficiency

These features help distinguish players with sustainable production
from those relying on unsustainable luck.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def load_ngs_data(
    seasons: List[int],
    stat_type: str = "receiving",
) -> pd.DataFrame:
    """Load NGS data from Bronze layer or nfl-data-py.

    Args:
        seasons: List of seasons to load.
        stat_type: One of 'receiving', 'passing', 'rushing'.

    Returns:
        NGS DataFrame with player_gsis_id, season, week, and stat columns.
    """
    import os
    import glob as globmod

    project_root = os.path.join(os.path.dirname(__file__), "..")
    bronze_dir = os.path.join(project_root, "data", "bronze", "ngs")

    # Try local Bronze first
    dfs = []
    for s in seasons:
        pattern = os.path.join(bronze_dir, f"season={s}", "*.parquet")
        files = sorted(globmod.glob(pattern))
        if files:
            df = pd.read_parquet(files[-1])
            # Filter to stat type based on available columns
            if stat_type == "receiving" and "avg_separation" in df.columns:
                dfs.append(df)
            elif stat_type == "passing" and "aggressiveness" in df.columns:
                dfs.append(df)
            elif stat_type == "rushing" and "efficiency" in df.columns:
                dfs.append(df)

    if dfs:
        result = pd.concat(dfs, ignore_index=True)
        logger.info(
            "Loaded %d NGS %s rows from local Bronze", len(result), stat_type
        )
        return result

    # Fallback: nfl-data-py
    try:
        import nfl_data_py as nfl

        result = nfl.import_ngs_data(stat_type, seasons)
        logger.info(
            "Loaded %d NGS %s rows from nfl-data-py", len(result), stat_type
        )
        return result
    except Exception as e:
        logger.warning("Failed to load NGS %s data: %s", stat_type, e)
        return pd.DataFrame()


def compute_ngs_receiving_features(
    ngs_recv: pd.DataFrame,
    up_to_week: Optional[int] = None,
) -> pd.DataFrame:
    """Compute rolling NGS receiving features per player.

    Features:
    - avg_separation_r3: 3-week rolling separation
    - avg_yac_above_expected_r3: YAC above expectation
    - catch_pct_r3: catch percentage rolling
    - ngs_quality_score: composite quality metric

    Args:
        ngs_recv: NGS receiving DataFrame.
        up_to_week: Only use data up to this week (for backtest leakage prevention).

    Returns:
        DataFrame with player_gsis_id, season, week, and NGS feature columns.
    """
    if ngs_recv.empty:
        return pd.DataFrame()

    df = ngs_recv.copy()

    # Filter to regular season
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]

    if up_to_week is not None and "week" in df.columns:
        df = df[df["week"] <= up_to_week]

    if df.empty:
        return pd.DataFrame()

    # Compute rolling features
    df = df.sort_values(["player_gsis_id", "season", "week"])

    feature_cols = ["avg_separation", "avg_yac_above_expectation", "catch_percentage"]
    available = [c for c in feature_cols if c in df.columns]

    if not available:
        logger.warning("No NGS receiving feature columns found")
        return pd.DataFrame()

    result_frames = []
    for col in available:
        roll_col = f"{col}_r3"
        df[roll_col] = (
            df.groupby(["player_gsis_id", "season"])[col]
            .transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
        )

    # Composite quality score: higher is better
    if "avg_separation" in df.columns and "avg_yac_above_expectation" in df.columns:
        sep = df.get("avg_separation_r3", df.get("avg_separation", 0))
        yac = df.get("avg_yac_above_expectation_r3", df.get("avg_yac_above_expectation", 0))
        df["ngs_recv_quality"] = (
            sep.fillna(0) * 0.5 + yac.fillna(0) * 0.3
        ).round(3)

    keep_cols = ["player_gsis_id", "season", "week"]
    ngs_features = [c for c in df.columns if c.endswith("_r3") or c == "ngs_recv_quality"]
    keep_cols.extend(ngs_features)
    keep_cols = [c for c in keep_cols if c in df.columns]

    return df[keep_cols]


def compute_ngs_rushing_features(
    ngs_rush: pd.DataFrame,
    up_to_week: Optional[int] = None,
) -> pd.DataFrame:
    """Compute rolling NGS rushing features per player.

    Features:
    - rush_yards_over_expected_r3: RYOE rolling average
    - efficiency_r3: rushing efficiency
    - ngs_rush_quality: composite quality metric

    Returns:
        DataFrame with player_gsis_id, season, week, and NGS rushing features.
    """
    if ngs_rush.empty:
        return pd.DataFrame()

    df = ngs_rush.copy()

    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]

    if up_to_week is not None and "week" in df.columns:
        df = df[df["week"] <= up_to_week]

    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["player_gsis_id", "season", "week"])

    for col in ["rush_yards_over_expected_per_att", "efficiency"]:
        if col in df.columns:
            df[f"{col}_r3"] = (
                df.groupby(["player_gsis_id", "season"])[col]
                .transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
            )

    # Composite rush quality
    ryoe = df.get("rush_yards_over_expected_per_att_r3", pd.Series(0, index=df.index))
    eff = df.get("efficiency_r3", pd.Series(0, index=df.index))
    df["ngs_rush_quality"] = (ryoe.fillna(0) * 0.6 + eff.fillna(0) * 0.4).round(3)

    keep_cols = ["player_gsis_id", "season", "week"]
    ngs_features = [c for c in df.columns if c.endswith("_r3") or c == "ngs_rush_quality"]
    keep_cols.extend(ngs_features)
    keep_cols = [c for c in keep_cols if c in df.columns]

    return df[keep_cols]


def compute_ngs_passing_features(
    ngs_pass: pd.DataFrame,
    up_to_week: Optional[int] = None,
) -> pd.DataFrame:
    """Compute rolling NGS passing features per player.

    Features:
    - completion_pct_above_expected_r3: CPOE rolling
    - aggressiveness_r3: throw aggressiveness
    - avg_time_to_throw_r3: pocket time

    Returns:
        DataFrame with player_gsis_id, season, week, and NGS passing features.
    """
    if ngs_pass.empty:
        return pd.DataFrame()

    df = ngs_pass.copy()

    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]

    if up_to_week is not None and "week" in df.columns:
        df = df[df["week"] <= up_to_week]

    if df.empty:
        return pd.DataFrame()

    df = df.sort_values(["player_gsis_id", "season", "week"])

    for col in [
        "completion_percentage_above_expectation",
        "aggressiveness",
        "avg_time_to_throw",
    ]:
        if col in df.columns:
            df[f"{col}_r3"] = (
                df.groupby(["player_gsis_id", "season"])[col]
                .transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())
            )

    # Composite passing quality
    cpoe = df.get(
        "completion_percentage_above_expectation_r3",
        pd.Series(0, index=df.index),
    )
    df["ngs_pass_quality"] = cpoe.fillna(0).round(3)

    keep_cols = ["player_gsis_id", "season", "week"]
    ngs_features = [c for c in df.columns if c.endswith("_r3") or c == "ngs_pass_quality"]
    keep_cols.extend(ngs_features)
    keep_cols = [c for c in keep_cols if c in df.columns]

    return df[keep_cols]


def apply_ngs_adjustment(
    projections_df: pd.DataFrame,
    ngs_features_df: pd.DataFrame,
    quality_col: str = "ngs_recv_quality",
    adjustment_range: tuple = (0.95, 1.08),
) -> pd.DataFrame:
    """Apply NGS quality adjustment to projections.

    Players with above-average NGS quality get a small boost.
    Players with below-average NGS quality get a mild reduction.

    Args:
        projections_df: Base projections with player_id column.
        ngs_features_df: NGS features with player_gsis_id column.
        quality_col: Which quality column to use for adjustment.
        adjustment_range: (min_mult, max_mult) for the adjustment factor.

    Returns:
        Projections with NGS-adjusted projected_points.
    """
    if ngs_features_df.empty or quality_col not in ngs_features_df.columns:
        return projections_df

    df = projections_df.copy()

    # Join on player_id = player_gsis_id
    join_col = "player_id" if "player_id" in df.columns else "player_name"
    ngs_join = "player_gsis_id"

    if join_col == "player_id" and ngs_join in ngs_features_df.columns:
        # Get latest NGS quality per player
        latest_ngs = (
            ngs_features_df.sort_values(["season", "week"])
            .drop_duplicates(subset=[ngs_join], keep="last")[[ngs_join, quality_col]]
            .rename(columns={ngs_join: join_col})
        )

        df = df.merge(latest_ngs, on=join_col, how="left")

        if quality_col in df.columns:
            quality = df[quality_col].fillna(0)
            # Normalize to adjustment range
            median_q = quality[quality != 0].median() if (quality != 0).any() else 0
            if median_q != 0:
                factor = 1.0 + (quality - median_q) * 0.02  # 2% per unit above median
                factor = factor.clip(*adjustment_range)
                df["projected_points"] = (
                    df["projected_points"] * factor
                ).round(2)
                df["ngs_adjustment"] = factor.round(4)
                logger.info(
                    "NGS adjustment applied: %d players, range [%.3f, %.3f]",
                    (factor != 1.0).sum(),
                    factor.min(),
                    factor.max(),
                )

    return df
