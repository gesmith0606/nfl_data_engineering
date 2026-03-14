#!/usr/bin/env python3
"""
Team Analytics Module

Computes team-level PBP metrics and tendencies for the Silver layer of the
NFL data pipeline. Provides shared utility functions (play filtering, rolling
window application) used by all team metric computation functions.

Metric computation functions are added in Plans 02 and 03.
"""

import pandas as pd
import numpy as np
from typing import List, Optional
import logging

logger = logging.getLogger(__name__)


def _filter_valid_plays(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Filter play-by-play data to valid regular-season run/pass plays with EPA.

    Keeps only rows where:
        - season_type == 'REG' (regular season)
        - week <= 18
        - play_type in ('pass', 'run')
        - epa is not NaN

    Args:
        pbp_df: Raw play-by-play DataFrame (from nfl.import_pbp_data or Bronze).

    Returns:
        Filtered copy of the DataFrame containing only valid plays.
    """
    df = pbp_df.copy()

    # Regular season only
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    else:
        logger.warning("No season_type column; skipping season_type filter")

    # Week cap at 18 (regular season)
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    # Run and pass plays only
    if "play_type" in df.columns:
        df = df[df["play_type"].isin(["pass", "run"])]
    else:
        logger.warning("No play_type column; cannot filter to pass/run plays")

    # Drop rows where EPA is missing
    if "epa" in df.columns:
        df = df.dropna(subset=["epa"])
    else:
        logger.warning("No epa column found; skipping EPA NaN filter")

    logger.info(
        "Filtered to %d valid plays from %d total rows", len(df), len(pbp_df)
    )
    return df.reset_index(drop=True)


def apply_team_rolling(
    df: pd.DataFrame,
    stat_cols: List[str],
    windows: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Apply shifted rolling averages and season-to-date expanding average by team.

    For each stat column and window size, creates a column named
    ``{col}_roll{window}`` using ``shift(1).rolling(window, min_periods=1).mean()``
    grouped by ``['team', 'season']``.

    Also creates ``{col}_std`` (season-to-date expanding average) using
    ``shift(1).expanding().mean()`` grouped by ``['team', 'season']``.

    The shift(1) ensures only *prior* weeks are used (no look-ahead bias).

    Args:
        df: Team-level weekly stats DataFrame. Must contain 'team', 'season',
            and 'week' columns plus the columns listed in stat_cols.
        stat_cols: List of numeric column names to compute rolling averages for.
        windows: Rolling window sizes in weeks. Defaults to [3, 6].

    Returns:
        DataFrame with rolling average and STD columns appended.
    """
    if windows is None:
        windows = [3, 6]

    df = df.copy()
    df = df.sort_values(["team", "season", "week"])

    available_cols = [c for c in stat_cols if c in df.columns]
    if not available_cols:
        logger.warning("No stat_cols found in DataFrame; returning unchanged")
        return df

    # Rolling averages per window
    for window in windows:
        roll_cols = {}
        for col in available_cols:
            roll_cols[f"{col}_roll{window}"] = (
                df.groupby(["team", "season"])[col]
                .transform(
                    lambda s: s.shift(1).rolling(window, min_periods=1).mean()
                )
            )
        df = df.assign(**roll_cols)

    # Season-to-date expanding average
    for col in available_cols:
        df[f"{col}_std"] = (
            df.groupby(["team", "season"])[col]
            .transform(lambda s: s.shift(1).expanding().mean())
        )

    logger.info(
        "Team rolling averages computed (%s) for %d rows, %d stat columns",
        windows,
        len(df),
        len(available_cols),
    )
    return df


# ---------------------------------------------------------------------------
# PBP Performance Metric Functions (Plan 02)
# ---------------------------------------------------------------------------


def compute_team_epa(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute team EPA per play for offense and defense with pass/rush splits.

    Groups plays by possessing team (offense) and defending team (defense)
    to calculate mean EPA per play at the team-week level.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_epa_per_play,
        off_pass_epa, off_rush_epa, def_epa_per_play.
    """
    # Offense EPA: overall + pass/rush splits
    off_all = (
        valid_plays.groupby(["posteam", "season", "week"])["epa"]
        .mean()
        .reset_index()
        .rename(columns={"posteam": "team", "epa": "off_epa_per_play"})
    )

    off_pass = (
        valid_plays[valid_plays["play_type"] == "pass"]
        .groupby(["posteam", "season", "week"])["epa"]
        .mean()
        .reset_index()
        .rename(columns={"posteam": "team", "epa": "off_pass_epa"})
    )

    off_rush = (
        valid_plays[valid_plays["play_type"] == "run"]
        .groupby(["posteam", "season", "week"])["epa"]
        .mean()
        .reset_index()
        .rename(columns={"posteam": "team", "epa": "off_rush_epa"})
    )

    # Defense EPA
    def_all = (
        valid_plays.groupby(["defteam", "season", "week"])["epa"]
        .mean()
        .reset_index()
        .rename(columns={"defteam": "team", "epa": "def_epa_per_play"})
    )

    # Merge all offense components
    off = off_all.merge(off_pass, on=["team", "season", "week"], how="left")
    off = off.merge(off_rush, on=["team", "season", "week"], how="left")

    # Merge offense + defense
    result = off.merge(def_all, on=["team", "season", "week"], how="outer")

    logger.info("Team EPA computed for %d team-weeks", len(result))
    return result


def compute_team_success_rate(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute team success rate for offense and defense.

    Success rate is the mean of the binary 'success' column per team-week.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_success_rate, def_success_rate.
    """
    off = (
        valid_plays.groupby(["posteam", "season", "week"])["success"]
        .mean()
        .reset_index()
        .rename(columns={"posteam": "team", "success": "off_success_rate"})
    )

    defense = (
        valid_plays.groupby(["defteam", "season", "week"])["success"]
        .mean()
        .reset_index()
        .rename(columns={"defteam": "team", "success": "def_success_rate"})
    )

    result = off.merge(defense, on=["team", "season", "week"], how="outer")

    logger.info("Team success rate computed for %d team-weeks", len(result))
    return result


def compute_team_cpoe(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute team CPOE (Completion Probability Over Expected) for offense.

    Aggregates as the mean of non-null play-level CPOE values. CPOE is an
    offense-only metric (no defense CPOE).

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_cpoe.
    """
    # Filter to rows with valid CPOE (non-null)
    cpoe_plays = valid_plays.dropna(subset=["cpoe"])

    result = (
        cpoe_plays.groupby(["posteam", "season", "week"])["cpoe"]
        .mean()
        .reset_index()
        .rename(columns={"posteam": "team", "cpoe": "off_cpoe"})
    )

    logger.info("Team CPOE computed for %d team-weeks", len(result))
    return result


def compute_red_zone_metrics(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute red zone efficiency metrics for offense and defense.

    Red zone is defined as yardline_100 <= 20. TD rate uses a drive-based
    denominator (unique drives entering the red zone) rather than play count.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_rz_epa,
        off_rz_success_rate, off_rz_pass_rate, off_rz_td_rate,
        def_rz_epa, def_rz_success_rate, def_rz_pass_rate, def_rz_td_rate.
    """
    rz = valid_plays[valid_plays["yardline_100"] <= 20].copy()

    if rz.empty:
        logger.info("No red zone plays found")
        return pd.DataFrame(columns=[
            "team", "season", "week",
            "off_rz_epa", "off_rz_success_rate", "off_rz_pass_rate", "off_rz_td_rate",
            "def_rz_epa", "def_rz_success_rate", "def_rz_pass_rate", "def_rz_td_rate",
        ])

    def _agg_rz(df: pd.DataFrame, team_col: str, prefix: str) -> pd.DataFrame:
        """Aggregate red zone metrics for a given team column."""
        agg = df.groupby([team_col, "season", "week"]).agg(
            rz_epa=("epa", "mean"),
            rz_success_rate=("success", "mean"),
            rz_pass_rate=("pass_attempt", "mean"),
            rz_tds=("touchdown", "sum"),
            rz_drives=("drive", "nunique"),
        ).reset_index()

        agg[f"{prefix}_rz_td_rate"] = agg["rz_tds"] / agg["rz_drives"]
        agg = agg.rename(columns={
            team_col: "team",
            "rz_epa": f"{prefix}_rz_epa",
            "rz_success_rate": f"{prefix}_rz_success_rate",
            "rz_pass_rate": f"{prefix}_rz_pass_rate",
        })
        # Drop intermediate columns
        agg = agg.drop(columns=["rz_tds", "rz_drives"])
        return agg

    off_rz = _agg_rz(rz, "posteam", "off")
    def_rz = _agg_rz(rz, "defteam", "def")

    result = off_rz.merge(def_rz, on=["team", "season", "week"], how="outer")

    logger.info("Red zone metrics computed for %d team-weeks", len(result))
    return result


def compute_pbp_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Orchestrate all PBP metric computations and apply rolling windows.

    Pipeline:
        1. Filter valid plays
        2. Compute EPA, success rate, CPOE, and red zone metrics
        3. Merge all results
        4. Apply rolling windows to all stat columns

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        DataFrame with all PBP metrics plus rolling (_roll3, _roll6, _std) columns.
    """
    valid = _filter_valid_plays(pbp_df)

    if valid.empty:
        logger.warning("No valid plays after filtering; returning empty DataFrame")
        return pd.DataFrame()

    # Compute individual metrics
    epa_df = compute_team_epa(valid)
    success_df = compute_team_success_rate(valid)
    cpoe_df = compute_team_cpoe(valid)
    rz_df = compute_red_zone_metrics(valid)

    # Merge all on (team, season, week)
    merged = epa_df.merge(success_df, on=["team", "season", "week"], how="outer")
    merged = merged.merge(cpoe_df, on=["team", "season", "week"], how="outer")
    if not rz_df.empty:
        merged = merged.merge(rz_df, on=["team", "season", "week"], how="outer")

    # Identify stat columns (everything except team/season/week)
    key_cols = {"team", "season", "week"}
    stat_cols = [c for c in merged.columns if c not in key_cols]

    # Apply rolling windows
    result = apply_team_rolling(merged, stat_cols)

    logger.info(
        "PBP metrics complete: %d rows, %d teams, seasons %s-%s",
        len(result),
        result["team"].nunique(),
        result["season"].min(),
        result["season"].max(),
    )
    return result
