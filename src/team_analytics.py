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

from config import EWM_TARGET_COLS, TEAM_DIVISIONS

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
    ewm_cols: Optional[List[str]] = None,
    ewm_halflife: int = 3,
) -> pd.DataFrame:
    """Apply shifted rolling averages and season-to-date expanding average by team.

    For each stat column and window size, creates a column named
    ``{col}_roll{window}`` using ``shift(1).rolling(window, min_periods=1).mean()``
    grouped by ``['team', 'season']``.

    Also creates ``{col}_std`` (season-to-date expanding average) using
    ``shift(1).expanding().mean()`` grouped by ``['team', 'season']``.

    Optionally creates ``{col}_ewm{ewm_halflife}`` columns for specified
    ewm_cols using exponentially weighted moving average with shift(1) lag.

    The shift(1) ensures only *prior* weeks are used (no look-ahead bias).

    Args:
        df: Team-level weekly stats DataFrame. Must contain 'team', 'season',
            and 'week' columns plus the columns listed in stat_cols.
        stat_cols: List of numeric column names to compute rolling averages for.
        windows: Rolling window sizes in weeks. Defaults to [3, 6].
        ewm_cols: Optional list of column names to compute EWM for. Only columns
            present in df are processed. Defaults to None (no EWM).
        ewm_halflife: Half-life for EWM in number of periods. Defaults to 3.

    Returns:
        DataFrame with rolling average, STD, and optional EWM columns appended.
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

    # Exponentially weighted moving average (optional)
    if ewm_cols:
        available_ewm = [c for c in ewm_cols if c in df.columns]
        ewm_data = {}
        for col in available_ewm:
            ewm_data[f"{col}_ewm{ewm_halflife}"] = (
                df.groupby(["team", "season"])[col]
                .transform(
                    lambda s: s.shift(1).ewm(
                        halflife=ewm_halflife, min_periods=1
                    ).mean()
                )
            )
        if ewm_data:
            df = df.assign(**ewm_data)

    logger.info(
        "Team rolling averages computed (%s) for %d rows, %d stat columns",
        windows,
        len(df),
        len(available_cols),
    )
    return df


# ---------------------------------------------------------------------------
# Special Teams Filter Helper (needed by Plan 02 compute functions)
# ---------------------------------------------------------------------------


def _filter_st_plays(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Filter play-by-play data to special teams plays (regular season, week <= 18).

    Uses a union filter: ``special_teams_play == 1`` OR
    ``play_type in ('field_goal', 'punt', 'kickoff', 'extra_point')``.

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        Filtered copy of the DataFrame containing only ST plays.
    """
    df = pbp_df.copy()

    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    st_types = ["field_goal", "punt", "kickoff", "extra_point"]
    st_mask = pd.Series(False, index=df.index)
    if "special_teams_play" in df.columns:
        st_mask = st_mask | (df["special_teams_play"] == 1)
    if "play_type" in df.columns:
        st_mask = st_mask | df["play_type"].isin(st_types)

    result = df[st_mask].reset_index(drop=True)
    logger.info(
        "Filtered to %d ST plays from %d total rows", len(result), len(pbp_df)
    )
    return result


# ---------------------------------------------------------------------------
# Complex PBP-Derived Metric Functions (Plan 02)
# ---------------------------------------------------------------------------


def _parse_top_seconds(top_str) -> float:
    """Parse a time-of-possession string in 'M:SS' format to total seconds.

    Args:
        top_str: Time string like '7:13' or NaN.

    Returns:
        Float seconds (e.g. 433.0) or np.nan if parsing fails.
    """
    if pd.isna(top_str):
        return np.nan
    try:
        parts = str(top_str).split(":")
        return float(parts[0]) * 60 + float(parts[1])
    except (ValueError, IndexError):
        return np.nan


def _fg_bucket(distance) -> Optional[str]:
    """Classify a field goal kick distance into an NFL-standard bucket.

    Args:
        distance: Kick distance in yards.

    Returns:
        'short' (<30), 'mid' (30-39), 'long' (40-49), '50plus' (50+),
        or None if distance is NaN.
    """
    if pd.isna(distance):
        return None
    if distance < 30:
        return "short"
    elif distance < 40:
        return "mid"
    elif distance < 50:
        return "long"
    else:
        return "50plus"


def compute_fg_accuracy(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute field goal accuracy by distance bucket per team-week.

    Filters to special teams plays with ``field_goal_attempt == 1``, then
    classifies each attempt by ``kick_distance`` into NFL-standard buckets
    (short <30, mid 30-39, long 40-49, 50+).

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        DataFrame with columns: team, season, week, fg_att, fg_pct,
        fg_pct_short, fg_pct_mid, fg_pct_long, fg_pct_50plus.
    """
    output_cols = [
        "team", "season", "week", "fg_att", "fg_pct",
        "fg_pct_short", "fg_pct_mid", "fg_pct_long", "fg_pct_50plus",
    ]

    st = _filter_st_plays(pbp_df)
    if "field_goal_attempt" not in st.columns:
        logger.info("No field_goal_attempt column; returning empty FG DataFrame")
        return pd.DataFrame(columns=output_cols)

    fg = st[st["field_goal_attempt"] == 1].copy()
    if fg.empty:
        logger.info("No field goal attempts found")
        return pd.DataFrame(columns=output_cols)

    fg["made"] = (fg["field_goal_result"] == "made").astype(int)
    fg["bucket"] = fg["kick_distance"].apply(_fg_bucket)

    # Overall accuracy per team-week
    overall = fg.groupby(["posteam", "season", "week"]).agg(
        fg_att=("made", "count"),
        fg_pct=("made", "mean"),
    ).reset_index().rename(columns={"posteam": "team"})

    # Per-bucket accuracy
    bucket_acc = (
        fg.dropna(subset=["bucket"])
        .groupby(["posteam", "season", "week", "bucket"])["made"]
        .mean()
        .reset_index()
        .rename(columns={"posteam": "team", "made": "pct"})
    )

    # Pivot buckets to columns
    for bucket_name in ["short", "mid", "long", "50plus"]:
        col_name = f"fg_pct_{bucket_name}"
        bucket_data = bucket_acc[bucket_acc["bucket"] == bucket_name][
            ["team", "season", "week", "pct"]
        ].rename(columns={"pct": col_name})
        overall = overall.merge(
            bucket_data, on=["team", "season", "week"], how="left"
        )

    logger.info("FG accuracy computed for %d team-weeks", len(overall))
    return overall[output_cols]


def compute_return_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute kick/punt return averages and touchback rates per team-week.

    Touchback detection uses proxy columns since no explicit touchback column
    exists: kickoff touchback = ``return_yards == 0`` AND
    ``kickoff_returner_player_id IS NULL``; punt touchback =
    ``punt_in_endzone == 1``.

    Metrics are attributed to the *returning* team (defteam for kickoffs and
    punts, since the kicking/punting team is posteam).

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        DataFrame with columns: team, season, week, ko_return_avg,
        ko_touchback_rate, punt_return_avg, punt_touchback_rate.
    """
    output_cols = [
        "team", "season", "week", "ko_return_avg", "ko_touchback_rate",
        "punt_return_avg", "punt_touchback_rate",
    ]

    st = _filter_st_plays(pbp_df)
    if st.empty:
        logger.info("No ST plays found; returning empty return metrics")
        return pd.DataFrame(columns=output_cols)

    # --- Kickoff returns ---
    ko = st[st.get("kickoff_attempt", pd.Series(dtype=float)) == 1].copy()
    ko_result = pd.DataFrame(columns=["team", "season", "week", "ko_return_avg", "ko_touchback_rate"])

    if not ko.empty and "return_yards" in ko.columns:
        ko["is_touchback"] = (ko["return_yards"] == 0) & (
            ko["kickoff_returner_player_id"].isna()
        )
        ko_agg = ko.groupby(["defteam", "season", "week"]).agg(
            total_kickoffs=("is_touchback", "count"),
            touchbacks=("is_touchback", "sum"),
        ).reset_index()

        # Return avg excludes touchbacks
        ko_returns = ko[~ko["is_touchback"]]
        if not ko_returns.empty:
            ko_ret_avg = (
                ko_returns.groupby(["defteam", "season", "week"])["return_yards"]
                .mean()
                .reset_index()
                .rename(columns={"return_yards": "ko_return_avg"})
            )
            ko_agg = ko_agg.merge(
                ko_ret_avg, on=["defteam", "season", "week"], how="left"
            )
        else:
            ko_agg["ko_return_avg"] = np.nan

        ko_agg["ko_touchback_rate"] = ko_agg["touchbacks"] / ko_agg["total_kickoffs"]
        ko_result = ko_agg.rename(columns={"defteam": "team"})[
            ["team", "season", "week", "ko_return_avg", "ko_touchback_rate"]
        ]

    # --- Punt returns ---
    punts = st[st.get("punt_attempt", pd.Series(dtype=float)) == 1].copy()
    punt_result = pd.DataFrame(columns=["team", "season", "week", "punt_return_avg", "punt_touchback_rate"])

    if not punts.empty and "return_yards" in punts.columns:
        punts["is_touchback"] = punts.get("punt_in_endzone", pd.Series(0, index=punts.index)) == 1
        punt_agg = punts.groupby(["defteam", "season", "week"]).agg(
            total_punts=("is_touchback", "count"),
            touchbacks=("is_touchback", "sum"),
        ).reset_index()

        # Return avg excludes touchbacks
        punt_returns = punts[~punts["is_touchback"]]
        if not punt_returns.empty:
            punt_ret_avg = (
                punt_returns.groupby(["defteam", "season", "week"])["return_yards"]
                .mean()
                .reset_index()
                .rename(columns={"return_yards": "punt_return_avg"})
            )
            punt_agg = punt_agg.merge(
                punt_ret_avg, on=["defteam", "season", "week"], how="left"
            )
        else:
            punt_agg["punt_return_avg"] = np.nan

        punt_agg["punt_touchback_rate"] = punt_agg["touchbacks"] / punt_agg["total_punts"]
        punt_result = punt_agg.rename(columns={"defteam": "team"})[
            ["team", "season", "week", "punt_return_avg", "punt_touchback_rate"]
        ]

    # --- Merge kickoff and punt ---
    if ko_result.empty and punt_result.empty:
        logger.info("No return metrics computed")
        return pd.DataFrame(columns=output_cols)

    if ko_result.empty:
        result = punt_result.copy()
        result["ko_return_avg"] = np.nan
        result["ko_touchback_rate"] = np.nan
    elif punt_result.empty:
        result = ko_result.copy()
        result["punt_return_avg"] = np.nan
        result["punt_touchback_rate"] = np.nan
    else:
        result = ko_result.merge(
            punt_result, on=["team", "season", "week"], how="outer"
        )

    logger.info("Return metrics computed for %d team-weeks", len(result))
    return result[output_cols]


def compute_drive_efficiency(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute drive efficiency metrics (3-and-out rate, avg drive stats) per team-week.

    Groups plays by drive first, then aggregates to team-week level.
    A 3-and-out is a drive with <= 3 plays AND no first downs AND no touchdowns.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_three_and_out_rate,
        off_avg_drive_plays, off_avg_drive_yards, off_drives_per_game,
        def_three_and_out_rate, def_avg_drive_plays, def_avg_drive_yards.
    """
    output_cols = [
        "team", "season", "week", "off_three_and_out_rate",
        "off_avg_drive_plays", "off_avg_drive_yards", "off_drives_per_game",
        "def_three_and_out_rate", "def_avg_drive_plays", "def_avg_drive_yards",
    ]

    if valid_plays.empty:
        logger.info("No valid plays; returning empty drive efficiency DataFrame")
        return pd.DataFrame(columns=output_cols)

    def _drive_agg(df: pd.DataFrame, team_col: str, prefix: str) -> pd.DataFrame:
        """Aggregate drive-level stats for a given team column."""
        # Drive-level aggregation
        drive_stats = df.groupby([team_col, "season", "week", "drive"]).agg(
            plays=("play_id", "count") if "play_id" in df.columns else ("epa", "count"),
            first_downs=("first_down", "sum") if "first_down" in df.columns else ("success", "sum"),
            touchdowns=("touchdown", "sum") if "touchdown" in df.columns else ("epa", lambda x: 0),
            drive_yards=("yards_gained", "sum") if "yards_gained" in df.columns else ("epa", lambda x: 0),
        ).reset_index()

        # Flag 3-and-out drives
        drive_stats["is_three_and_out"] = (
            (drive_stats["plays"] <= 3)
            & (drive_stats["first_downs"] == 0)
            & (drive_stats["touchdowns"] == 0)
        )

        # Aggregate to team-week
        team_week = drive_stats.groupby([team_col, "season", "week"]).agg(
            three_and_out_rate=("is_three_and_out", "mean"),
            avg_drive_plays=("plays", "mean"),
            avg_drive_yards=("drive_yards", "mean"),
            drives_per_game=("drive", "nunique"),
        ).reset_index()

        team_week = team_week.rename(columns={
            team_col: "team",
            "three_and_out_rate": f"{prefix}_three_and_out_rate",
            "avg_drive_plays": f"{prefix}_avg_drive_plays",
            "avg_drive_yards": f"{prefix}_avg_drive_yards",
            "drives_per_game": f"{prefix}_drives_per_game",
        })

        return team_week

    off = _drive_agg(valid_plays, "posteam", "off")
    def_df = _drive_agg(valid_plays, "defteam", "def")
    # Drop def_drives_per_game (not in output spec)
    if "def_drives_per_game" in def_df.columns:
        def_df = def_df.drop(columns=["def_drives_per_game"])

    result = off.merge(def_df, on=["team", "season", "week"], how="outer")

    logger.info("Drive efficiency computed for %d team-weeks", len(result))
    return result[output_cols]


def compute_top(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute time of possession (seconds) per team-week.

    Parses ``drive_time_of_possession`` from 'M:SS' string format to seconds,
    takes the max per drive (since each play in a drive carries the same
    drive-level TOP value), then sums across drives per team-week.

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        DataFrame with columns: team, season, week, off_top_seconds, def_top_seconds.
    """
    output_cols = ["team", "season", "week", "off_top_seconds", "def_top_seconds"]

    df = pbp_df.copy()

    # Basic filters
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    if "drive_time_of_possession" not in df.columns:
        logger.info("No drive_time_of_possession column; returning empty TOP DataFrame")
        return pd.DataFrame(columns=output_cols)

    df["top_seconds"] = df["drive_time_of_possession"].apply(_parse_top_seconds)

    if df["top_seconds"].isna().all():
        logger.info("All TOP values are NaN; returning empty TOP DataFrame")
        return pd.DataFrame(columns=output_cols)

    # Offense TOP: max TOP per drive (all plays in a drive have same value), then sum
    off_drive = (
        df.groupby(["posteam", "season", "week", "drive"])["top_seconds"]
        .max()
        .reset_index()
    )
    off_top = (
        off_drive.groupby(["posteam", "season", "week"])["top_seconds"]
        .sum()
        .reset_index()
        .rename(columns={"posteam": "team", "top_seconds": "off_top_seconds"})
    )

    # Defense TOP: same logic but grouped by defteam
    def_drive = (
        df.groupby(["defteam", "season", "week", "drive"])["top_seconds"]
        .max()
        .reset_index()
    )
    def_top = (
        def_drive.groupby(["defteam", "season", "week"])["top_seconds"]
        .sum()
        .reset_index()
        .rename(columns={"defteam": "team", "top_seconds": "def_top_seconds"})
    )

    result = off_top.merge(def_top, on=["team", "season", "week"], how="outer")

    logger.info("TOP computed for %d team-weeks", len(result))
    return result[output_cols]


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

    # Apply rolling windows (with EWM for core EPA/success/CPOE metrics)
    result = apply_team_rolling(merged, stat_cols, ewm_cols=EWM_TARGET_COLS)

    logger.info(
        "PBP metrics complete: %d rows, %d teams, seasons %s-%s",
        len(result),
        result["team"].nunique(),
        result["season"].min(),
        result["season"].max(),
    )
    return result


# ---------------------------------------------------------------------------
# Tendency Metric Functions (Plan 03)
# ---------------------------------------------------------------------------


def compute_pace(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute pace (total pass+run plays per game) per team-week.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, pace.
    """
    result = (
        valid_plays.groupby(["posteam", "season", "week"])
        .size()
        .reset_index(name="pace")
        .rename(columns={"posteam": "team"})
    )
    logger.info("Pace computed for %d team-weeks", len(result))
    return result[["team", "season", "week", "pace"]]


def compute_proe(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute Pass Rate Over Expected (PROE) per team-week.

    PROE = actual_pass_rate - mean(xpass).
    NaN xpass rows are excluded from mean(xpass) by pandas, but included
    in total play count for actual_pass_rate.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, proe.
    """
    agg = valid_plays.groupby(["posteam", "season", "week"]).agg(
        total_plays=("pass_attempt", "count"),
        pass_plays=("pass_attempt", "sum"),
        mean_xpass=("xpass", "mean"),  # NaN excluded by pandas mean
    ).reset_index()

    agg["actual_pass_rate"] = agg["pass_plays"] / agg["total_plays"]
    agg["proe"] = agg["actual_pass_rate"] - agg["mean_xpass"]

    result = agg.rename(columns={"posteam": "team"})
    logger.info("PROE computed for %d team-weeks", len(result))
    return result[["team", "season", "week", "proe"]]


def compute_fourth_down_aggressiveness(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute 4th down aggressiveness (go rate and success rate) per team-week.

    Accepts raw PBP and applies its own filtering: season_type=='REG',
    week<=18, down==4, play_type in ['pass','run','punt','field_goal'].

    Args:
        pbp_df: Raw play-by-play DataFrame (unfiltered).

    Returns:
        DataFrame with columns: team, season, week, fourth_down_go_rate,
        fourth_down_success_rate.
    """
    df = pbp_df.copy()

    # Apply basic filters
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    # 4th down plays only
    df = df[df["down"] == 4]

    # Only meaningful 4th down decisions
    df = df[df["play_type"].isin(["pass", "run", "punt", "field_goal"])]

    if df.empty:
        logger.info("No 4th down plays found")
        return pd.DataFrame(columns=[
            "team", "season", "week", "fourth_down_go_rate", "fourth_down_success_rate",
        ])

    # go_attempt: pass or run on 4th down
    df["go_attempt"] = df["play_type"].isin(["pass", "run"]).astype(int)

    agg = df.groupby(["posteam", "season", "week"]).agg(
        go_attempts=("go_attempt", "sum"),
        total_decisions=("go_attempt", "count"),
        converted=("fourth_down_converted", "sum"),
        failed=("fourth_down_failed", "sum"),
    ).reset_index()

    agg["fourth_down_go_rate"] = agg["go_attempts"] / agg["total_decisions"]

    # Success rate: only on go attempts; NaN when zero go attempts
    total_go_outcomes = agg["converted"] + agg["failed"]
    agg["fourth_down_success_rate"] = np.where(
        total_go_outcomes > 0,
        agg["converted"] / total_go_outcomes,
        np.nan,
    )

    result = agg.rename(columns={"posteam": "team"})
    logger.info("4th down aggressiveness computed for %d team-weeks", len(result))
    return result[["team", "season", "week", "fourth_down_go_rate", "fourth_down_success_rate"]]


def compute_early_down_run_rate(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute early-down (1st and 2nd down) run rate per team-week.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, early_down_run_rate.
    """
    early = valid_plays[valid_plays["down"] <= 2].copy()

    if early.empty:
        logger.info("No early-down plays found")
        return pd.DataFrame(columns=["team", "season", "week", "early_down_run_rate"])

    agg = early.groupby(["posteam", "season", "week"]).agg(
        rush_attempts=("rush_attempt", "sum"),
        total_plays=("rush_attempt", "count"),
    ).reset_index()

    agg["early_down_run_rate"] = agg["rush_attempts"] / agg["total_plays"]

    result = agg.rename(columns={"posteam": "team"})
    logger.info("Early-down run rate computed for %d team-weeks", len(result))
    return result[["team", "season", "week", "early_down_run_rate"]]


def compute_tendency_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Orchestrate all tendency metric computations and apply rolling windows.

    Pipeline:
        1. Filter valid plays (for pace, PROE, early-down run rate)
        2. Compute pace, PROE, early-down run rate from valid plays
        3. Compute 4th down aggressiveness from raw PBP (needs punt/FG)
        4. Merge all on (team, season, week)
        5. Apply rolling windows to all stat columns

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        DataFrame with all tendency metrics plus rolling (_roll3, _roll6, _std) columns.
    """
    valid = _filter_valid_plays(pbp_df)

    if valid.empty:
        logger.warning("No valid plays after filtering; returning empty DataFrame")
        return pd.DataFrame()

    # Compute individual metrics
    pace_df = compute_pace(valid)
    proe_df = compute_proe(valid)
    early_df = compute_early_down_run_rate(valid)
    fourth_df = compute_fourth_down_aggressiveness(pbp_df)  # Raw PBP for punt/FG

    # Merge all on (team, season, week)
    merged = pace_df.merge(proe_df, on=["team", "season", "week"], how="outer")
    merged = merged.merge(early_df, on=["team", "season", "week"], how="outer")
    if not fourth_df.empty:
        merged = merged.merge(fourth_df, on=["team", "season", "week"], how="outer")

    # Identify stat columns (everything except team/season/week)
    key_cols = {"team", "season", "week"}
    stat_cols = [c for c in merged.columns if c not in key_cols]

    # Apply rolling windows
    result = apply_team_rolling(merged, stat_cols)

    logger.info(
        "Tendency metrics complete: %d rows, %d teams, seasons %s-%s",
        len(result),
        result["team"].nunique(),
        result["season"].min(),
        result["season"].max(),
    )
    return result


# ---------------------------------------------------------------------------
# Strength of Schedule (SOS) Functions (Plan 16-01)
# ---------------------------------------------------------------------------


def _build_opponent_schedule(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Extract unique (team, season, week, opponent) from play-by-play data.

    Groups by (game_id, posteam) to get one row per team-game, then extracts
    the opponent (defteam). This avoids inflating the schedule with per-play rows.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, opponent.
    """
    games = (
        valid_plays[["game_id", "posteam", "defteam", "season", "week"]]
        .drop_duplicates(subset=["game_id", "posteam"])
        .rename(columns={"posteam": "team", "defteam": "opponent"})
    )
    result = games[["team", "season", "week", "opponent"]].reset_index(drop=True)
    logger.info("Opponent schedule built: %d team-games", len(result))
    return result


def compute_sos_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute opponent-adjusted EPA and schedule difficulty rankings.

    Pipeline:
        1. Filter valid plays and compute raw team EPA per week
        2. Build opponent schedule from PBP
        3. For each team-week, compute lagged SOS using opponents' EPA
           from weeks 1 through W-1 only
        4. Week 1: adj_epa = raw_epa (no opponents faced yet), SOS = NaN
        5. Week 2+: off_sos = mean(opponents' def_epa through W-1),
           adj_off_epa = raw_off_epa - off_sos
        6. Rank 1-N per season-week (rank 1 = hardest schedule)
        7. Apply rolling windows to SOS stat columns

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        DataFrame with columns: team, season, week, off_sos_score,
        def_sos_score, adj_off_epa, adj_def_epa, off_sos_rank, def_sos_rank
        plus rolling (_roll3, _roll6, _std) columns.
    """
    valid = _filter_valid_plays(pbp_df)

    if valid.empty:
        logger.warning("No valid plays after filtering; returning empty DataFrame")
        return pd.DataFrame()

    # Step 1: Get raw team EPA per week
    team_epa = compute_team_epa(valid)

    # Step 2: Build opponent schedule from PBP
    schedule = _build_opponent_schedule(valid)

    # Step 3: For each team-week, compute lagged SOS
    rows = []
    for (team, season), group in schedule.groupby(["team", "season"]):
        weeks = sorted(group["week"].unique())
        for week in weeks:
            # Get raw EPA for this team-week
            raw = team_epa[
                (team_epa["team"] == team)
                & (team_epa["season"] == season)
                & (team_epa["week"] == week)
            ]
            if raw.empty:
                continue  # Bye week — skip

            raw_off = raw["off_epa_per_play"].iloc[0]
            raw_def = raw["def_epa_per_play"].iloc[0]

            # Opponents faced in prior weeks
            prior_opps = group[group["week"] < week]

            if prior_opps.empty:
                # Week 1: no opponents faced yet
                rows.append(
                    {
                        "team": team,
                        "season": season,
                        "week": week,
                        "off_sos_score": np.nan,
                        "def_sos_score": np.nan,
                        "adj_off_epa": raw_off,
                        "adj_def_epa": raw_def,
                    }
                )
            else:
                # Get each opponent's EPA from the specific week they were faced
                opp_epa_rows = []
                for _, opp_row in prior_opps.iterrows():
                    opp_team = opp_row["opponent"]
                    opp_week = opp_row["week"]
                    opp_data = team_epa[
                        (team_epa["team"] == opp_team)
                        & (team_epa["season"] == season)
                        & (team_epa["week"] == opp_week)
                    ]
                    if not opp_data.empty:
                        opp_epa_rows.append(opp_data.iloc[0])

                if opp_epa_rows:
                    opp_epa_df = pd.DataFrame(opp_epa_rows)
                    # off_sos = opponents' DEF EPA (how well opponents defended)
                    off_sos = opp_epa_df["def_epa_per_play"].mean()
                    # def_sos = opponents' OFF EPA (how well opponents attacked)
                    def_sos = opp_epa_df["off_epa_per_play"].mean()
                else:
                    off_sos = np.nan
                    def_sos = np.nan

                rows.append(
                    {
                        "team": team,
                        "season": season,
                        "week": week,
                        "off_sos_score": off_sos,
                        "def_sos_score": def_sos,
                        "adj_off_epa": raw_off - off_sos if not np.isnan(off_sos) else raw_off,
                        "adj_def_epa": raw_def - def_sos if not np.isnan(def_sos) else raw_def,
                    }
                )

    result = pd.DataFrame(rows)

    if result.empty:
        logger.warning("No SOS rows computed; returning empty DataFrame")
        return pd.DataFrame()

    # Step 4: Add rankings per season-week (rank 1 = hardest schedule)
    result["off_sos_rank"] = result.groupby(["season", "week"])[
        "off_sos_score"
    ].rank(ascending=False, method="min")
    result["def_sos_rank"] = result.groupby(["season", "week"])[
        "def_sos_score"
    ].rank(ascending=False, method="min")

    # Step 5: Apply rolling windows to stat columns
    stat_cols = ["off_sos_score", "def_sos_score", "adj_off_epa", "adj_def_epa"]
    result = apply_team_rolling(result, stat_cols)

    logger.info(
        "SOS metrics complete: %d rows, %d teams, seasons %s-%s",
        len(result),
        result["team"].nunique(),
        result["season"].min(),
        result["season"].max(),
    )
    return result


# ---------------------------------------------------------------------------
# Situational Splits Functions (Plan 16-02)
# ---------------------------------------------------------------------------


def compute_situational_splits(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute situational EPA splits: home/away, divisional, and game script.

    Produces a wide-format DataFrame with one row per (team, season, week)
    containing 12 split columns plus rolling window variants.

    Split columns:
        - home_off_epa, away_off_epa: offensive EPA when playing at home/away
        - home_def_epa, away_def_epa: defensive EPA when playing at home/away
        - div_off_epa, nondiv_off_epa: offensive EPA vs divisional/non-divisional opponents
        - div_def_epa, nondiv_def_epa: defensive EPA vs divisional/non-divisional opponents
        - leading_off_epa, trailing_off_epa: offensive EPA when leading (>=7) or trailing (<=-7)
        - leading_def_epa, trailing_def_epa: defensive EPA when leading (>=7) or trailing (<=-7)

    Non-applicable situations produce NaN (e.g., home_off_epa is NaN for away games).
    Neutral plays (-6 <= score_differential <= 6) are excluded from game script splits.

    Args:
        pbp_df: Raw play-by-play DataFrame with home_team, away_team,
                score_differential, and standard PBP columns.

    Returns:
        Wide-format DataFrame with situational split columns plus rolling variants.
    """
    valid = _filter_valid_plays(pbp_df)

    if valid.empty:
        logger.warning("No valid plays after filtering; returning empty DataFrame")
        return pd.DataFrame()

    # Ensure required columns exist
    for col in ["home_team", "score_differential"]:
        if col not in valid.columns:
            logger.warning("Missing column %s; returning empty DataFrame", col)
            return pd.DataFrame()

    # --- Tag each play ---
    valid = valid.copy()
    valid["is_home_off"] = valid["posteam"] == valid["home_team"]
    valid["is_home_def"] = valid["defteam"] == valid["home_team"]

    # Divisional tagging (handle missing teams gracefully)
    valid["posteam_div"] = valid["posteam"].map(TEAM_DIVISIONS)
    valid["defteam_div"] = valid["defteam"].map(TEAM_DIVISIONS)
    valid["is_divisional"] = (
        valid["posteam_div"].notna()
        & valid["defteam_div"].notna()
        & (valid["posteam_div"] == valid["defteam_div"])
    )

    # Game script tagging
    valid["is_leading"] = valid["score_differential"] >= 7
    valid["is_trailing"] = valid["score_differential"] <= -7

    # --- Helper to compute mean EPA for a filtered subset ---
    def _mean_epa(df: pd.DataFrame, team_col: str, mask: pd.Series) -> pd.DataFrame:
        """Compute mean EPA grouped by (team_col, season, week) for rows where mask is True."""
        subset = df[mask]
        if subset.empty:
            return pd.DataFrame(columns=[team_col, "season", "week", "epa"])
        return (
            subset.groupby([team_col, "season", "week"])["epa"]
            .mean()
            .reset_index()
        )

    # --- Compute all 12 splits ---
    # Home/away offense
    home_off = _mean_epa(valid, "posteam", valid["is_home_off"])
    home_off = home_off.rename(columns={"posteam": "team", "epa": "home_off_epa"})

    away_off = _mean_epa(valid, "posteam", ~valid["is_home_off"])
    away_off = away_off.rename(columns={"posteam": "team", "epa": "away_off_epa"})

    # Home/away defense
    home_def = _mean_epa(valid, "defteam", valid["is_home_def"])
    home_def = home_def.rename(columns={"defteam": "team", "epa": "home_def_epa"})

    away_def = _mean_epa(valid, "defteam", ~valid["is_home_def"])
    away_def = away_def.rename(columns={"defteam": "team", "epa": "away_def_epa"})

    # Divisional offense/defense
    div_off = _mean_epa(valid, "posteam", valid["is_divisional"])
    div_off = div_off.rename(columns={"posteam": "team", "epa": "div_off_epa"})

    nondiv_off = _mean_epa(valid, "posteam", ~valid["is_divisional"])
    nondiv_off = nondiv_off.rename(columns={"posteam": "team", "epa": "nondiv_off_epa"})

    div_def = _mean_epa(valid, "defteam", valid["is_divisional"])
    div_def = div_def.rename(columns={"defteam": "team", "epa": "div_def_epa"})

    nondiv_def = _mean_epa(valid, "defteam", ~valid["is_divisional"])
    nondiv_def = nondiv_def.rename(columns={"defteam": "team", "epa": "nondiv_def_epa"})

    # Game script offense (exclude neutral)
    leading_off = _mean_epa(valid, "posteam", valid["is_leading"])
    leading_off = leading_off.rename(columns={"posteam": "team", "epa": "leading_off_epa"})

    trailing_off = _mean_epa(valid, "posteam", valid["is_trailing"])
    trailing_off = trailing_off.rename(columns={"posteam": "team", "epa": "trailing_off_epa"})

    # Game script defense
    leading_def = _mean_epa(valid, "defteam", valid["is_leading"])
    leading_def = leading_def.rename(columns={"defteam": "team", "epa": "leading_def_epa"})

    trailing_def = _mean_epa(valid, "defteam", valid["is_trailing"])
    trailing_def = trailing_def.rename(columns={"defteam": "team", "epa": "trailing_def_epa"})

    # --- Merge all splits into wide format ---
    # Start with all unique (team, season, week) combinations from offense + defense
    off_keys = valid[["posteam", "season", "week"]].rename(columns={"posteam": "team"})
    def_keys = valid[["defteam", "season", "week"]].rename(columns={"defteam": "team"})
    all_keys = pd.concat([off_keys, def_keys]).drop_duplicates().reset_index(drop=True)

    result = all_keys
    for split_df in [
        home_off, away_off, home_def, away_def,
        div_off, nondiv_off, div_def, nondiv_def,
        leading_off, trailing_off, leading_def, trailing_def,
    ]:
        if not split_df.empty:
            result = result.merge(split_df, on=["team", "season", "week"], how="left")

    # --- Apply rolling windows ---
    split_cols = [
        "home_off_epa", "away_off_epa", "home_def_epa", "away_def_epa",
        "div_off_epa", "nondiv_off_epa", "div_def_epa", "nondiv_def_epa",
        "leading_off_epa", "trailing_off_epa", "leading_def_epa", "trailing_def_epa",
    ]
    # Ensure all split columns exist (some might be missing if all empty)
    for col in split_cols:
        if col not in result.columns:
            result[col] = np.nan

    result = apply_team_rolling(result, split_cols)

    logger.info(
        "Situational splits complete: %d rows, %d teams, seasons %s-%s",
        len(result),
        result["team"].nunique(),
        result["season"].min(),
        result["season"].max(),
    )
    return result


# ---------------------------------------------------------------------------
# PBP-Derived Metric Functions (Phase 21, Plan 01)
# ---------------------------------------------------------------------------


def _filter_st_plays(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Filter play-by-play data to special teams plays only.

    Keeps rows where ``special_teams_play == 1`` OR ``play_type`` is one of
    field_goal, punt, kickoff, extra_point. Also applies REG season and
    week <= 18 guards (same pattern as compute_fourth_down_aggressiveness).

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        Filtered DataFrame containing only special teams plays.
    """
    df = pbp_df.copy()

    # Regular season only
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    st_types = ["field_goal", "punt", "kickoff", "extra_point"]
    st_flag_mask = pd.Series(False, index=df.index)
    if "special_teams_play" in df.columns:
        st_flag_mask = df["special_teams_play"] == 1

    type_mask = pd.Series(False, index=df.index)
    if "play_type" in df.columns:
        type_mask = df["play_type"].isin(st_types)

    result = df[st_flag_mask | type_mask].reset_index(drop=True)
    logger.info("Filtered to %d special teams plays from %d rows", len(result), len(pbp_df))
    return result


def compute_penalty_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute team penalty counts and yards split by offense/defense per game.

    Receives raw PBP and applies its own season_type/week filters. Uses
    ``penalty == 1`` flag and splits offensive vs defensive penalties via
    ``penalty_team == posteam`` or ``penalty_team == defteam``.

    Args:
        pbp_df: Raw play-by-play DataFrame (unfiltered).

    Returns:
        DataFrame with columns: team, season, week, off_penalties,
        off_penalty_yards, def_penalties, def_penalty_yards.
    """
    df = pbp_df.copy()

    # Apply basic filters
    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    # Filter to penalty plays
    if "penalty" not in df.columns:
        logger.warning("No penalty column found; returning empty DataFrame")
        return pd.DataFrame(columns=[
            "team", "season", "week",
            "off_penalties", "off_penalty_yards", "def_penalties", "def_penalty_yards",
        ])

    pen = df[df["penalty"] == 1].copy()
    pen = pen.dropna(subset=["penalty_team"])

    if pen.empty:
        logger.info("No penalty plays found")
        return pd.DataFrame(columns=[
            "team", "season", "week",
            "off_penalties", "off_penalty_yards", "def_penalties", "def_penalty_yards",
        ])

    # Offensive penalties (penalty_team == posteam)
    off_pen = pen[pen["penalty_team"] == pen["posteam"]]
    off_agg = (
        off_pen.groupby(["posteam", "season", "week"])
        .agg(off_penalties=("penalty", "sum"), off_penalty_yards=("penalty_yards", "sum"))
        .reset_index()
        .rename(columns={"posteam": "team"})
    )

    # Defensive penalties (penalty_team == defteam)
    def_pen = pen[pen["penalty_team"] == pen["defteam"]]
    def_agg = (
        def_pen.groupby(["defteam", "season", "week"])
        .agg(def_penalties=("penalty", "sum"), def_penalty_yards=("penalty_yards", "sum"))
        .reset_index()
        .rename(columns={"defteam": "team"})
    )

    result = off_agg.merge(def_agg, on=["team", "season", "week"], how="outer")
    result = result.fillna({"off_penalties": 0, "off_penalty_yards": 0, "def_penalties": 0, "def_penalty_yards": 0})

    logger.info("Penalty metrics computed for %d team-weeks", len(result))
    return result


def compute_opp_drawn_penalties(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute opponent-drawn penalty counts and yards per team-game.

    'Drawn' penalties are those committed by the opponent. Offensive penalties
    drawn = defensive penalties grouped by the offensive team (posteam benefits
    from opponent's defensive penalties).

    Args:
        pbp_df: Raw play-by-play DataFrame (unfiltered).

    Returns:
        DataFrame with columns: team, season, week, off_penalties_drawn,
        off_penalty_yards_drawn, def_penalties_drawn, def_penalty_yards_drawn.
    """
    df = pbp_df.copy()

    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    if "penalty" not in df.columns:
        logger.warning("No penalty column found; returning empty DataFrame")
        return pd.DataFrame(columns=[
            "team", "season", "week",
            "off_penalties_drawn", "off_penalty_yards_drawn",
            "def_penalties_drawn", "def_penalty_yards_drawn",
        ])

    pen = df[df["penalty"] == 1].copy()
    pen = pen.dropna(subset=["penalty_team"])

    if pen.empty:
        logger.info("No penalty plays found")
        return pd.DataFrame(columns=[
            "team", "season", "week",
            "off_penalties_drawn", "off_penalty_yards_drawn",
            "def_penalties_drawn", "def_penalty_yards_drawn",
        ])

    # Offensive penalties drawn = defensive penalties (penalty_team == defteam)
    # grouped by posteam (the offense benefits)
    def_committed = pen[pen["penalty_team"] == pen["defteam"]]
    off_drawn = (
        def_committed.groupby(["posteam", "season", "week"])
        .agg(off_penalties_drawn=("penalty", "sum"), off_penalty_yards_drawn=("penalty_yards", "sum"))
        .reset_index()
        .rename(columns={"posteam": "team"})
    )

    # Defensive penalties drawn = offensive penalties (penalty_team == posteam)
    # grouped by defteam (the defense benefits)
    off_committed = pen[pen["penalty_team"] == pen["posteam"]]
    def_drawn = (
        off_committed.groupby(["defteam", "season", "week"])
        .agg(def_penalties_drawn=("penalty", "sum"), def_penalty_yards_drawn=("penalty_yards", "sum"))
        .reset_index()
        .rename(columns={"defteam": "team"})
    )

    result = off_drawn.merge(def_drawn, on=["team", "season", "week"], how="outer")
    result = result.fillna({
        "off_penalties_drawn": 0, "off_penalty_yards_drawn": 0,
        "def_penalties_drawn": 0, "def_penalty_yards_drawn": 0,
    })

    logger.info("Opponent-drawn penalty metrics computed for %d team-weeks", len(result))
    return result


def compute_turnover_luck(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Compute fumble-based turnover luck metrics with expanding window.

    Uses season-to-date cumulative recovery rate with shift(1) lag (NOT
    rolling windows). A team is 'turnover lucky' when own recovery rate
    exceeds 0.60 and 'unlucky' when below 0.40.

    Args:
        pbp_df: Raw play-by-play DataFrame (unfiltered).

    Returns:
        DataFrame with columns: team, season, week, fumbles_lost,
        fumbles_forced, own_fumble_recovery_rate, opp_fumble_recovery_rate,
        is_turnover_lucky.
    """
    df = pbp_df.copy()

    if "season_type" in df.columns:
        df = df[df["season_type"] == "REG"]
    if "week" in df.columns:
        df = df[df["week"] <= 18]

    empty_cols = [
        "team", "season", "week", "fumbles_lost", "fumbles_forced",
        "own_fumble_recovery_rate", "opp_fumble_recovery_rate", "is_turnover_lucky",
    ]

    if "fumble" not in df.columns:
        logger.warning("No fumble column found; returning empty DataFrame")
        return pd.DataFrame(columns=empty_cols)

    fumbles = df[df["fumble"] == 1].copy()

    if fumbles.empty:
        logger.info("No fumble plays found")
        return pd.DataFrame(columns=empty_cols)

    # Offensive fumble stats (team had ball)
    fumbles["own_recovered"] = (
        fumbles["fumble_recovery_1_team"] == fumbles["posteam"]
    ).astype(int)
    fumbles["own_lost"] = (
        fumbles["fumble_recovery_1_team"] != fumbles["posteam"]
    ).astype(int)
    # Handle null recovery team as not counted
    null_recovery = fumbles["fumble_recovery_1_team"].isna()
    fumbles.loc[null_recovery, "own_recovered"] = 0
    fumbles.loc[null_recovery, "own_lost"] = 0

    off_agg = (
        fumbles.groupby(["posteam", "season", "week"])
        .agg(
            fumbles_lost=("own_lost", "sum"),
            total_own_fumbles=("fumble", "sum"),
            own_recovered=("own_recovered", "sum"),
        )
        .reset_index()
        .rename(columns={"posteam": "team"})
    )
    off_agg["own_fumble_recovery_rate"] = np.where(
        off_agg["total_own_fumbles"] > 0,
        off_agg["own_recovered"] / off_agg["total_own_fumbles"],
        np.nan,
    )

    # Defensive fumble stats (opponent had ball)
    fumbles["forced_recovered"] = (
        fumbles["fumble_recovery_1_team"] == fumbles["defteam"]
    ).astype(int)

    def_agg = (
        fumbles.groupby(["defteam", "season", "week"])
        .agg(
            fumbles_forced=("fumble", "sum"),
            def_recovered=("forced_recovered", "sum"),
        )
        .reset_index()
        .rename(columns={"defteam": "team"})
    )
    def_agg["opp_fumble_recovery_rate"] = np.where(
        def_agg["fumbles_forced"] > 0,
        def_agg["def_recovered"] / def_agg["fumbles_forced"],
        np.nan,
    )

    # Merge
    result = off_agg[["team", "season", "week", "fumbles_lost", "own_fumble_recovery_rate"]].merge(
        def_agg[["team", "season", "week", "fumbles_forced", "opp_fumble_recovery_rate"]],
        on=["team", "season", "week"],
        how="outer",
    )

    # Fill NaN counts with 0
    result = result.fillna({"fumbles_lost": 0, "fumbles_forced": 0})

    # Season-to-date expanding recovery rate with shift(1) lag
    result = result.sort_values(["team", "season", "week"])
    for col in ["own_fumble_recovery_rate", "opp_fumble_recovery_rate"]:
        result[f"{col}_std"] = (
            result.groupby(["team", "season"])[col]
            .transform(lambda s: s.shift(1).expanding().mean())
        )

    # Turnover luck flag based on current-week own recovery rate
    result["is_turnover_lucky"] = np.where(
        result["own_fumble_recovery_rate"] > 0.60, 1,
        np.where(result["own_fumble_recovery_rate"] < 0.40, -1, 0),
    )

    logger.info("Turnover luck metrics computed for %d team-weeks", len(result))
    return result


def compute_red_zone_trips(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute red zone trip volume using drive-level unique counts.

    Red zone is yardline_100 <= 20. Trips are counted as unique drives
    entering the red zone, producing 3-5 per team-game (not play count).

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_rz_trips, def_rz_trips.
    """
    rz = valid_plays[valid_plays["yardline_100"] <= 20].copy()

    if rz.empty:
        logger.info("No red zone plays found")
        return pd.DataFrame(columns=["team", "season", "week", "off_rz_trips", "def_rz_trips"])

    # Offensive RZ trips
    off_trips = (
        rz.groupby(["posteam", "season", "week"])["drive"]
        .nunique()
        .reset_index()
        .rename(columns={"posteam": "team", "drive": "off_rz_trips"})
    )

    # Defensive RZ trips
    def_trips = (
        rz.groupby(["defteam", "season", "week"])["drive"]
        .nunique()
        .reset_index()
        .rename(columns={"defteam": "team", "drive": "def_rz_trips"})
    )

    result = off_trips.merge(def_trips, on=["team", "season", "week"], how="outer")
    result = result.fillna({"off_rz_trips": 0, "def_rz_trips": 0})

    logger.info("Red zone trips computed for %d team-weeks", len(result))
    return result


def compute_third_down_rates(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute 3rd down conversion rates for offense and defense.

    Rate = third_down_converted / (third_down_converted + third_down_failed).
    Division by zero produces NaN.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_third_down_rate,
        def_third_down_rate.
    """
    third = valid_plays[valid_plays["down"] == 3].copy()

    if third.empty:
        logger.info("No 3rd down plays found")
        return pd.DataFrame(columns=["team", "season", "week", "off_third_down_rate", "def_third_down_rate"])

    # Offensive 3rd down rate
    off_agg = (
        third.groupby(["posteam", "season", "week"])
        .agg(converted=("third_down_converted", "sum"), failed=("third_down_failed", "sum"))
        .reset_index()
    )
    total = off_agg["converted"] + off_agg["failed"]
    off_agg["off_third_down_rate"] = np.where(total > 0, off_agg["converted"] / total, np.nan)
    off_agg = off_agg.rename(columns={"posteam": "team"})[["team", "season", "week", "off_third_down_rate"]]

    # Defensive 3rd down rate
    def_agg = (
        third.groupby(["defteam", "season", "week"])
        .agg(converted=("third_down_converted", "sum"), failed=("third_down_failed", "sum"))
        .reset_index()
    )
    total_d = def_agg["converted"] + def_agg["failed"]
    def_agg["def_third_down_rate"] = np.where(total_d > 0, def_agg["converted"] / total_d, np.nan)
    def_agg = def_agg.rename(columns={"defteam": "team"})[["team", "season", "week", "def_third_down_rate"]]

    result = off_agg.merge(def_agg, on=["team", "season", "week"], how="outer")

    logger.info("3rd down rates computed for %d team-weeks", len(result))
    return result


def compute_explosive_plays(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute explosive play rates for offense and defense.

    Explosive pass = yards_gained >= 20. Explosive rush = yards_gained >= 10.
    Rates are computed as explosive plays / total plays of that type.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_explosive_pass_rate,
        off_explosive_rush_rate, def_explosive_pass_rate, def_explosive_rush_rate.
    """
    empty_cols = [
        "team", "season", "week",
        "off_explosive_pass_rate", "off_explosive_rush_rate",
        "def_explosive_pass_rate", "def_explosive_rush_rate",
    ]

    if valid_plays.empty:
        return pd.DataFrame(columns=empty_cols)

    df = valid_plays.copy()
    df["explosive_pass"] = ((df["play_type"] == "pass") & (df["yards_gained"] >= 20)).astype(int)
    df["explosive_rush"] = ((df["play_type"] == "run") & (df["yards_gained"] >= 10)).astype(int)
    df["is_pass"] = (df["play_type"] == "pass").astype(int)
    df["is_rush"] = (df["play_type"] == "run").astype(int)

    # Offense
    off_agg = (
        df.groupby(["posteam", "season", "week"])
        .agg(
            exp_pass=("explosive_pass", "sum"),
            exp_rush=("explosive_rush", "sum"),
            total_pass=("is_pass", "sum"),
            total_rush=("is_rush", "sum"),
        )
        .reset_index()
    )
    off_agg["off_explosive_pass_rate"] = np.where(
        off_agg["total_pass"] > 0, off_agg["exp_pass"] / off_agg["total_pass"], np.nan
    )
    off_agg["off_explosive_rush_rate"] = np.where(
        off_agg["total_rush"] > 0, off_agg["exp_rush"] / off_agg["total_rush"], np.nan
    )
    off_agg = off_agg.rename(columns={"posteam": "team"})[
        ["team", "season", "week", "off_explosive_pass_rate", "off_explosive_rush_rate"]
    ]

    # Defense
    def_agg = (
        df.groupby(["defteam", "season", "week"])
        .agg(
            exp_pass=("explosive_pass", "sum"),
            exp_rush=("explosive_rush", "sum"),
            total_pass=("is_pass", "sum"),
            total_rush=("is_rush", "sum"),
        )
        .reset_index()
    )
    def_agg["def_explosive_pass_rate"] = np.where(
        def_agg["total_pass"] > 0, def_agg["exp_pass"] / def_agg["total_pass"], np.nan
    )
    def_agg["def_explosive_rush_rate"] = np.where(
        def_agg["total_rush"] > 0, def_agg["exp_rush"] / def_agg["total_rush"], np.nan
    )
    def_agg = def_agg.rename(columns={"defteam": "team"})[
        ["team", "season", "week", "def_explosive_pass_rate", "def_explosive_rush_rate"]
    ]

    result = off_agg.merge(def_agg, on=["team", "season", "week"], how="outer")

    logger.info("Explosive play rates computed for %d team-weeks", len(result))
    return result


def compute_sack_rates(valid_plays: pd.DataFrame) -> pd.DataFrame:
    """Compute sack rates for offense and defense.

    Offensive sack rate = sacks / dropbacks (pass_attempt sum, which includes
    sacks in PBP data). Defensive sack rate uses the same formula from the
    defender's perspective.

    Args:
        valid_plays: Filtered PBP DataFrame (output of _filter_valid_plays).

    Returns:
        DataFrame with columns: team, season, week, off_sack_rate, def_sack_rate.
    """
    if valid_plays.empty:
        return pd.DataFrame(columns=["team", "season", "week", "off_sack_rate", "def_sack_rate"])

    df = valid_plays.copy()

    # Ensure sack column exists
    if "sack" not in df.columns:
        logger.warning("No sack column found; returning empty DataFrame")
        return pd.DataFrame(columns=["team", "season", "week", "off_sack_rate", "def_sack_rate"])

    # Offensive sack rate
    off_agg = (
        df.groupby(["posteam", "season", "week"])
        .agg(sacks=("sack", "sum"), dropbacks=("pass_attempt", "sum"))
        .reset_index()
    )
    off_agg["off_sack_rate"] = np.where(
        off_agg["dropbacks"] > 0, off_agg["sacks"] / off_agg["dropbacks"], np.nan
    )
    off_agg = off_agg.rename(columns={"posteam": "team"})[["team", "season", "week", "off_sack_rate"]]

    # Defensive sack rate
    def_agg = (
        df.groupby(["defteam", "season", "week"])
        .agg(sacks=("sack", "sum"), dropbacks=("pass_attempt", "sum"))
        .reset_index()
    )
    def_agg["def_sack_rate"] = np.where(
        def_agg["dropbacks"] > 0, def_agg["sacks"] / def_agg["dropbacks"], np.nan
    )
    def_agg = def_agg.rename(columns={"defteam": "team"})[["team", "season", "week", "def_sack_rate"]]

    result = off_agg.merge(def_agg, on=["team", "season", "week"], how="outer")

    logger.info("Sack rates computed for %d team-weeks", len(result))
    return result


# ---------------------------------------------------------------------------
# PBP-Derived Metrics Orchestrator (Phase 21, Plan 03)
# ---------------------------------------------------------------------------


def compute_pbp_derived_metrics(pbp_df: pd.DataFrame) -> pd.DataFrame:
    """Orchestrate all PBP-derived metric computations and apply rolling windows.

    Calls 11 individual compute functions, merges results on (team, season, week),
    and applies rolling windows to all stat columns except turnover luck (which uses
    its own expanding window internally).

    Args:
        pbp_df: Raw play-by-play DataFrame.

    Returns:
        DataFrame with all PBP-derived metrics plus rolling (_roll3, _roll6, _std) columns.
    """
    valid = _filter_valid_plays(pbp_df)

    if valid.empty:
        logger.warning("No valid plays after filtering; returning empty DataFrame")
        return pd.DataFrame()

    # Functions receiving raw PBP (apply own filters)
    penalties_df = compute_penalty_metrics(pbp_df)
    opp_penalties_df = compute_opp_drawn_penalties(pbp_df)
    turnover_df = compute_turnover_luck(pbp_df)
    fg_df = compute_fg_accuracy(pbp_df)
    return_df = compute_return_metrics(pbp_df)
    top_df = compute_top(pbp_df)

    # Functions receiving filtered valid plays
    rz_trips_df = compute_red_zone_trips(valid)
    third_down_df = compute_third_down_rates(valid)
    explosive_df = compute_explosive_plays(valid)
    drive_df = compute_drive_efficiency(valid)
    sack_df = compute_sack_rates(valid)

    # Merge all on (team, season, week)
    dfs = [
        penalties_df, opp_penalties_df, turnover_df, rz_trips_df,
        fg_df, return_df, third_down_df, explosive_df, drive_df,
        sack_df, top_df,
    ]

    merged = dfs[0]
    for df in dfs[1:]:
        if not df.empty:
            merged = merged.merge(df, on=["team", "season", "week"], how="outer")

    # Identify stat columns, excluding turnover luck (uses expanding window internally)
    key_cols = {"team", "season", "week"}
    turnover_cols = {
        "fumbles_lost", "fumbles_forced", "own_fumble_recovery_rate",
        "opp_fumble_recovery_rate", "is_turnover_lucky",
    }
    stat_cols = [c for c in merged.columns if c not in key_cols and c not in turnover_cols]

    # Apply rolling windows
    result = apply_team_rolling(merged, stat_cols)

    logger.info(
        "PBP-derived metrics complete: %d rows, %d teams, %d columns",
        len(result), result["team"].nunique(), len(result.columns),
    )
    return result
