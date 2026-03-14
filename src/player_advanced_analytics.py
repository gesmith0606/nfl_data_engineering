#!/usr/bin/env python3
"""
Player Advanced Analytics Module

Computes player-level advanced metrics from NGS, PFR, and QBR data sources
for the Silver layer. Provides rolling window utilities adapted from the
team_analytics pattern, with player-level grouping and min_periods=3.

Functions:
    apply_player_rolling - Rolling averages grouped by [player_gsis_id, season]
    compute_ngs_receiving_profile - NGS WR/TE separation, catch prob, air yards
    compute_ngs_passing_profile - NGS QB time-to-throw, aggressiveness, CPAE
    compute_ngs_rushing_profile - NGS RB rush yards over expected, efficiency
    compute_pfr_pressure_rate - PFR QB pressure, sack, hurry rates
    compute_pfr_team_blitz_rate - PFR team-level blitz aggregation
    compute_qbr_profile - ESPN QBR total, points added
    log_nan_coverage - Log % non-null for advanced stat columns
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Column constants: raw source columns to extract from each data source
# ---------------------------------------------------------------------------

NGS_RECEIVING_COLS = [
    "avg_separation",
    "catch_percentage",
    "avg_intended_air_yards",
    "avg_cushion",
    "avg_yac",
    "avg_expected_yac",
    "avg_yac_above_expectation",
]

NGS_PASSING_COLS = [
    "avg_time_to_throw",
    "aggressiveness",
    "avg_completed_air_yards",
    "avg_intended_air_yards",
    "avg_air_yards_differential",
    "completion_percentage_above_expectation",
    "expected_completion_percentage",
]

NGS_RUSHING_COLS = [
    "rush_yards_over_expected",
    "rush_yards_over_expected_per_att",
    "efficiency",
    "avg_time_to_los",
    "rush_pct_over_expected",
]

PFR_PRESSURE_COLS = [
    "times_pressured_pct",
    "times_sacked",
    "times_hurried",
    "times_hit",
    "times_blitzed",
    "passing_bad_throw_pct",
]

PFR_DEF_BLITZ_COLS = [
    "def_times_blitzed",
    "def_times_hurried",
    "def_sacks",
    "def_pressures",
]

QBR_COLS = [
    "qbr_total",
    "pts_added",
    "qb_plays",
    "epa_total",
]


# ---------------------------------------------------------------------------
# Rolling window utility
# ---------------------------------------------------------------------------


def apply_player_rolling(
    df: pd.DataFrame,
    stat_cols: List[str],
    windows: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Apply shifted rolling averages and season-to-date expanding average by player.

    Mirrors team_analytics.apply_team_rolling() but groups by
    [player_gsis_id, season] with min_periods=3 (stricter than team version).

    For each stat column and window size, creates:
        - {col}_roll{window}: shifted rolling mean with min_periods=3
        - {col}_std: season-to-date expanding mean (shift(1))

    Args:
        df: Player-level weekly stats DataFrame. Must contain 'player_gsis_id',
            'season', and 'week' columns plus the columns in stat_cols.
        stat_cols: List of numeric column names to compute rolling averages for.
        windows: Rolling window sizes in weeks. Defaults to [3, 6].

    Returns:
        DataFrame with rolling average and STD columns appended.
    """
    if windows is None:
        windows = [3, 6]

    df = df.copy()
    df = df.sort_values(["player_gsis_id", "season", "week"])

    available_cols = [c for c in stat_cols if c in df.columns]
    if not available_cols:
        logger.warning("No stat_cols found in DataFrame; returning unchanged")
        return df

    group_keys = ["player_gsis_id", "season"]

    # Rolling averages per window
    for window in windows:
        roll_cols = {}
        for col in available_cols:
            roll_cols[f"{col}_roll{window}"] = df.groupby(group_keys)[col].transform(
                lambda s: s.shift(1).rolling(window, min_periods=3).mean()
            )
        df = df.assign(**roll_cols)

    # Season-to-date expanding average
    for col in available_cols:
        df[f"{col}_std"] = df.groupby(group_keys)[col].transform(
            lambda s: s.shift(1).expanding().mean()
        )

    logger.info(
        "Player rolling averages computed (windows=%s) for %d rows, %d stat columns",
        windows,
        len(df),
        len(available_cols),
    )
    return df


# ---------------------------------------------------------------------------
# Helper: generic profile computation
# ---------------------------------------------------------------------------


def _compute_profile(
    df: pd.DataFrame,
    source_cols: List[str],
    prefix: str,
    key_cols: List[str],
    filter_week_gt_zero: bool = True,
) -> pd.DataFrame:
    """Generic profile computation: extract columns, prefix, apply rolling.

    Args:
        df: Input DataFrame with raw source columns.
        source_cols: List of raw column names to extract.
        prefix: Prefix to add to column names (e.g., 'ngs_', 'pfr_', 'qbr_').
        key_cols: Key columns to preserve (e.g., player_gsis_id, season, week).
        filter_week_gt_zero: If True, filter out week <= 0 rows.

    Returns:
        DataFrame with prefixed columns and rolling windows applied.
    """
    df = df.copy()

    # Filter week > 0 if requested
    if filter_week_gt_zero and "week" in df.columns:
        df = df[df["week"] > 0].copy()

    # Find available source columns
    available = [c for c in source_cols if c in df.columns]

    if not available:
        logger.warning(
            "No %s columns found in input DataFrame (expected: %s); returning empty",
            prefix,
            source_cols,
        )
        # Return DataFrame with expected schema but no rows
        expected_cols = key_cols.copy()
        for col in source_cols:
            expected_cols.append(f"{prefix}{col}")
        return pd.DataFrame(columns=expected_cols)

    # Preserve key columns + available source columns
    keep_cols = [c for c in key_cols if c in df.columns] + available
    result = df[keep_cols].copy()

    # Rename with prefix
    rename_map = {col: f"{prefix}{col}" for col in available}
    result = result.rename(columns=rename_map)

    # Apply rolling if player_gsis_id is present
    prefixed_cols = [f"{prefix}{col}" for col in available]
    if "player_gsis_id" in result.columns:
        result = apply_player_rolling(result, prefixed_cols)

    return result


# ---------------------------------------------------------------------------
# NGS Profile Functions
# ---------------------------------------------------------------------------


def compute_ngs_receiving_profile(ngs_recv_df: pd.DataFrame) -> pd.DataFrame:
    """Extract NGS receiving metrics and apply player-level rolling windows.

    Filters out week 0 (seasonal aggregates). Selects separation, catch
    probability, intended air yards, cushion, YAC metrics. Prefixes all
    columns with 'ngs_'.

    Args:
        ngs_recv_df: NGS receiving DataFrame from Bronze.

    Returns:
        DataFrame with ngs_ prefixed columns + rolling windows.
    """
    return _compute_profile(
        ngs_recv_df,
        source_cols=NGS_RECEIVING_COLS,
        prefix="ngs_",
        key_cols=["player_gsis_id", "season", "week"],
        filter_week_gt_zero=True,
    )


def compute_ngs_passing_profile(ngs_pass_df: pd.DataFrame) -> pd.DataFrame:
    """Extract NGS passing metrics and apply player-level rolling windows.

    Filters out week 0. Selects time-to-throw, aggressiveness, completed air
    yards, CPAE metrics. Prefixes all columns with 'ngs_'.

    Args:
        ngs_pass_df: NGS passing DataFrame from Bronze.

    Returns:
        DataFrame with ngs_ prefixed columns + rolling windows.
    """
    return _compute_profile(
        ngs_pass_df,
        source_cols=NGS_PASSING_COLS,
        prefix="ngs_",
        key_cols=["player_gsis_id", "season", "week"],
        filter_week_gt_zero=True,
    )


def compute_ngs_rushing_profile(ngs_rush_df: pd.DataFrame) -> pd.DataFrame:
    """Extract NGS rushing metrics and apply player-level rolling windows.

    Filters out week 0. Selects RYOE, efficiency, time to LOS. Prefixes all
    columns with 'ngs_'.

    Args:
        ngs_rush_df: NGS rushing DataFrame from Bronze.

    Returns:
        DataFrame with ngs_ prefixed columns + rolling windows.
    """
    return _compute_profile(
        ngs_rush_df,
        source_cols=NGS_RUSHING_COLS,
        prefix="ngs_",
        key_cols=["player_gsis_id", "season", "week"],
        filter_week_gt_zero=True,
    )


# ---------------------------------------------------------------------------
# PFR Profile Functions
# ---------------------------------------------------------------------------


def compute_pfr_pressure_rate(pfr_pass_df: pd.DataFrame) -> pd.DataFrame:
    """Extract PFR pressure metrics for QBs and apply rolling windows.

    Selects times_pressured_pct, sacked, hurried, hit, blitzed, bad_throw_pct.
    Prefixes all columns with 'pfr_'.

    Args:
        pfr_pass_df: PFR passing DataFrame from Bronze.

    Returns:
        DataFrame with pfr_ prefixed columns + rolling windows.
    """
    return _compute_profile(
        pfr_pass_df,
        source_cols=PFR_PRESSURE_COLS,
        prefix="pfr_",
        key_cols=["player_gsis_id", "player", "team", "season", "week"],
        filter_week_gt_zero=False,
    )


def compute_pfr_team_blitz_rate(pfr_def_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate PFR defender-level blitz data to team level with rolling windows.

    Sums def_times_blitzed, def_times_hurried, def_sacks, def_pressures
    per (team, season, week). Prefixes aggregated columns with 'pfr_def_'.
    Applies team-level rolling using apply_team_rolling from team_analytics.

    Args:
        pfr_def_df: PFR defender-level DataFrame from Bronze.

    Returns:
        Team-level DataFrame with pfr_def_ prefixed columns + rolling windows.
    """
    from team_analytics import apply_team_rolling

    df = pfr_def_df.copy()

    available = [c for c in PFR_DEF_BLITZ_COLS if c in df.columns]
    if not available:
        logger.warning(
            "No PFR defender columns found; returning empty DataFrame"
        )
        return pd.DataFrame(columns=["team", "season", "week"])

    # Aggregate defender rows to team level
    agg_dict = {col: "sum" for col in available}
    team_agg = df.groupby(["team", "season", "week"]).agg(agg_dict).reset_index()

    # Rename with pfr_def_ prefix (source cols already have def_ prefix,
    # so we add pfr_ to make pfr_def_*)
    rename_map = {col: f"pfr_{col}" for col in available}
    team_agg = team_agg.rename(columns=rename_map)

    # Apply team-level rolling
    prefixed_cols = list(rename_map.values())
    team_agg = apply_team_rolling(team_agg, prefixed_cols)

    logger.info(
        "PFR team blitz rate computed for %d team-weeks", len(team_agg)
    )
    return team_agg


# ---------------------------------------------------------------------------
# QBR Profile Function
# ---------------------------------------------------------------------------


def compute_qbr_profile(qbr_df: pd.DataFrame) -> pd.DataFrame:
    """Extract ESPN QBR metrics and apply player-level rolling windows.

    Selects qbr_total, pts_added, qb_plays, epa_total. Prefixes all
    columns with 'qbr_'.

    Args:
        qbr_df: ESPN QBR DataFrame from Bronze.

    Returns:
        DataFrame with qbr_ prefixed columns + rolling windows.
    """
    return _compute_profile(
        qbr_df,
        source_cols=QBR_COLS,
        prefix="qbr_",
        key_cols=["player_gsis_id", "player", "team", "season", "week"],
        filter_week_gt_zero=False,
    )


# ---------------------------------------------------------------------------
# NaN Coverage Logging
# ---------------------------------------------------------------------------


def log_nan_coverage(
    df: pd.DataFrame,
    advanced_cols: List[str],
) -> None:
    """Log the percentage of non-null values for each advanced stat column.

    Args:
        df: DataFrame to inspect.
        advanced_cols: List of column names to check coverage for.
    """
    total = len(df)
    if total == 0:
        logger.info("Empty DataFrame; no coverage to report")
        return

    for col in advanced_cols:
        if col in df.columns:
            non_null = df[col].notna().sum()
            pct = (non_null / total) * 100
            logger.info("Coverage: %s = %.1f%% non-null (%d/%d)", col, pct, non_null, total)
        else:
            logger.info("Coverage: %s = column not present", col)
