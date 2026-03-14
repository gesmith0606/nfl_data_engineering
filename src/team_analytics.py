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
