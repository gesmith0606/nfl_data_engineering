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
