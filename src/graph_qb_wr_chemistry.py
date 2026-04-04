"""QB-WR chemistry graph features.

Tracks specific QB-WR pair performance over time to capture
combination-specific signal. Built from PBP pass play data.

Features use strict temporal lag (shift(1)) -- no current week data.

Exports:
    build_qb_wr_chemistry: Extract per-pair per-week stats from PBP.
    compute_chemistry_features: Rolling chemistry features per WR-week.
    QB_WR_CHEMISTRY_FEATURE_COLUMNS: List of output feature column names.
"""

import glob
import logging
import os
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")
SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")

QB_WR_CHEMISTRY_FEATURE_COLUMNS: List[str] = [
    "qb_wr_chemistry_epa_roll3",
    "qb_wr_pair_comp_rate_roll3",
    "qb_wr_pair_target_share",
    "qb_wr_pair_games_together",
    "qb_wr_pair_td_rate",
]


def build_qb_wr_chemistry(
    pbp_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Extract per QB-WR pair per week stats from PBP pass plays.

    Filters to pass plays where both passer_player_id and receiver_player_id
    are present, then aggregates targets, completions, yards, TDs, EPA,
    air yards, completion rate, and ADOT per pair per week.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns.
        rosters_df: Optional rosters DataFrame (reserved for future use).

    Returns:
        DataFrame with columns: passer_id, receiver_id, season, week,
        targets, completions, yards, tds, epa_sum, epa_mean, air_yards_mean,
        comp_rate, adot. Empty DataFrame if no pass plays found.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    # Filter to pass plays with both passer and receiver
    required = ["passer_player_id", "receiver_player_id", "season", "week"]
    for col in required:
        if col not in pbp_df.columns:
            logger.warning("Missing required column %s in PBP data", col)
            return pd.DataFrame()

    mask = (
        (pbp_df["play_type"] == "pass")
        & pbp_df["passer_player_id"].notna()
        & (pbp_df["passer_player_id"].astype(str).str.len() > 0)
        & pbp_df["receiver_player_id"].notna()
        & (pbp_df["receiver_player_id"].astype(str).str.len() > 0)
    )
    passes = pbp_df[mask].copy()
    if passes.empty:
        return pd.DataFrame()

    # Ensure columns exist with defaults
    for col, default in [
        ("complete_pass", 0),
        ("yards_gained", 0),
        ("pass_touchdown", 0),
        ("epa", 0.0),
        ("air_yards", 0.0),
    ]:
        if col not in passes.columns:
            passes[col] = default

    # Fill NaN values
    passes["complete_pass"] = passes["complete_pass"].fillna(0).astype(int)
    passes["yards_gained"] = passes["yards_gained"].fillna(0)
    passes["pass_touchdown"] = passes["pass_touchdown"].fillna(0).astype(int)
    passes["epa"] = passes["epa"].fillna(0.0)
    passes["air_yards"] = passes["air_yards"].fillna(0.0)

    group_keys = ["passer_player_id", "receiver_player_id", "season", "week"]

    # Use play_id for counting if available, else fall back to complete_pass
    count_col = "play_id" if "play_id" in passes.columns else "complete_pass"

    agg = passes.groupby(group_keys, as_index=False).agg(
        targets=(count_col, "count"),
        completions=("complete_pass", "sum"),
        yards=("yards_gained", "sum"),
        tds=("pass_touchdown", "sum"),
        epa_sum=("epa", "sum"),
        epa_mean=("epa", "mean"),
        air_yards_mean=("air_yards", "mean"),
    )

    # Compute completion rate and ADOT
    agg["comp_rate"] = np.where(
        agg["targets"] > 0,
        agg["completions"] / agg["targets"],
        0.0,
    )
    agg["adot"] = agg["air_yards_mean"]  # Already mean from agg

    # Rename ID columns for clarity
    agg = agg.rename(
        columns={
            "passer_player_id": "passer_id",
            "receiver_player_id": "receiver_id",
        }
    )

    logger.info(
        "Built %d QB-WR pair-week rows from %d pass plays",
        len(agg),
        len(passes),
    )
    return agg


def _get_qb_for_receivers(
    player_weekly_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Build a mapping of receiver player-weeks to their team's primary QB.

    Uses player_weekly to identify the QB with the most pass attempts per
    team-season-week.

    Args:
        player_weekly_df: Bronze player_weekly with player_id, recent_team,
            season, week, position, attempts.
        rosters_df: Optional rosters (unused, for future enrichment).

    Returns:
        DataFrame with columns: team, season, week, qb_player_id.
    """
    if player_weekly_df.empty:
        return pd.DataFrame()

    pw = player_weekly_df.copy()

    # Find QBs by position
    if "position" not in pw.columns:
        return pd.DataFrame()

    qbs = pw[pw["position"] == "QB"].copy()
    if qbs.empty:
        return pd.DataFrame()

    # Use attempts (passing attempts) to identify primary QB
    att_col = "attempts"
    if att_col not in qbs.columns:
        # Try alternative column names
        for alt in ["passing_attempts", "completions"]:
            if alt in qbs.columns:
                att_col = alt
                break
        else:
            # Fall back to just picking first QB per team-week
            att_col = None

    team_col = "recent_team" if "recent_team" in qbs.columns else "team"
    if team_col not in qbs.columns:
        return pd.DataFrame()

    if att_col and att_col in qbs.columns:
        # Pick QB with most attempts per team-week
        qbs[att_col] = qbs[att_col].fillna(0)
        idx = qbs.groupby([team_col, "season", "week"])[att_col].idxmax()
        primary_qbs = qbs.loc[idx, [team_col, "season", "week", "player_id"]].copy()
    else:
        # Deduplicate: first QB per team-week
        primary_qbs = qbs.drop_duplicates(
            subset=[team_col, "season", "week"], keep="first"
        )[[team_col, "season", "week", "player_id"]].copy()

    primary_qbs = primary_qbs.rename(
        columns={"player_id": "qb_player_id", team_col: "team"}
    )
    return primary_qbs


def compute_chemistry_features(
    qb_wr_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
    rosters_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute rolling QB-WR chemistry features per WR player-week.

    For each WR/TE player-week, finds their current team's QB, looks up
    the QB-WR pair's historical stats, and computes rolling features.
    All features use shift(1) for temporal safety.

    Args:
        qb_wr_df: Output of build_qb_wr_chemistry (pair-week stats).
        player_weekly_df: Bronze player_weekly with player_id, recent_team,
            season, week, position.
        rosters_df: Optional rosters for enrichment.

    Returns:
        DataFrame with columns: player_id, season, week, and
        QB_WR_CHEMISTRY_FEATURE_COLUMNS. One row per WR/TE player-week.
    """
    if qb_wr_df.empty or player_weekly_df.empty:
        return pd.DataFrame()

    pw = player_weekly_df.copy()
    team_col = "recent_team" if "recent_team" in pw.columns else "team"

    # Get WR/TE player-weeks
    receivers = pw[pw["position"].isin(["WR", "TE"])].copy()
    if receivers.empty:
        return pd.DataFrame()

    # Get primary QB per team-week
    qb_map = _get_qb_for_receivers(pw, rosters_df)
    if qb_map.empty:
        return pd.DataFrame()

    # Map each receiver to their team's QB
    receivers = receivers.merge(
        qb_map,
        left_on=[team_col, "season", "week"],
        right_on=["team", "season", "week"],
        how="left",
    )
    if (
        "team" in receivers.columns
        and team_col in receivers.columns
        and team_col != "team"
    ):
        receivers = receivers.drop(columns=["team"], errors="ignore")

    # Drop rows where we couldn't find a QB
    receivers = receivers[receivers["qb_player_id"].notna()].copy()
    if receivers.empty:
        return pd.DataFrame()

    # Sort pair data for rolling computations
    pair_data = qb_wr_df.copy()
    pair_data = pair_data.sort_values(["passer_id", "receiver_id", "season", "week"])

    # Compute rolling stats per pair (before shift -- shift applied later)
    pair_data["pair_key"] = (
        pair_data["passer_id"].astype(str) + "_" + pair_data["receiver_id"].astype(str)
    )

    # Rolling 3-game EPA
    pair_data["epa_roll3_raw"] = pair_data.groupby("pair_key")["epa_sum"].transform(
        lambda x: x.rolling(3, min_periods=1).mean()
    )

    # Rolling 3-game completion rate
    pair_data["comp_rate_roll3_raw"] = pair_data.groupby("pair_key")[
        "comp_rate"
    ].transform(lambda x: x.rolling(3, min_periods=1).mean())

    # Rolling 3-game targets for target share computation
    pair_data["targets_roll3_raw"] = pair_data.groupby("pair_key")["targets"].transform(
        lambda x: x.rolling(3, min_periods=1).sum()
    )

    # Cumulative games together
    pair_data["games_together_raw"] = pair_data.groupby("pair_key").cumcount() + 1

    # Rolling 6-game TD rate (TDs / targets)
    pair_data["tds_roll6_raw"] = pair_data.groupby("pair_key")["tds"].transform(
        lambda x: x.rolling(6, min_periods=1).sum()
    )
    pair_data["targets_roll6_raw"] = pair_data.groupby("pair_key")["targets"].transform(
        lambda x: x.rolling(6, min_periods=1).sum()
    )
    pair_data["td_rate_roll6_raw"] = np.where(
        pair_data["targets_roll6_raw"] > 0,
        pair_data["tds_roll6_raw"] / pair_data["targets_roll6_raw"],
        0.0,
    )

    # Apply shift(1) for temporal safety -- no current week data
    for col in [
        "epa_roll3_raw",
        "comp_rate_roll3_raw",
        "targets_roll3_raw",
        "games_together_raw",
        "td_rate_roll6_raw",
    ]:
        pair_data[col] = pair_data.groupby("pair_key")[col].shift(1)

    # Build lookup: (passer_id, receiver_id, season, week) -> features
    pair_lookup = pair_data[
        [
            "passer_id",
            "receiver_id",
            "season",
            "week",
            "epa_roll3_raw",
            "comp_rate_roll3_raw",
            "targets_roll3_raw",
            "games_together_raw",
            "td_rate_roll6_raw",
        ]
    ].copy()

    # Compute target share: this WR's targets / QB's total targets (rolling 3)
    # First get QB total targets per week
    qb_total_targets = (
        qb_wr_df.groupby(["passer_id", "season", "week"])["targets"]
        .sum()
        .reset_index()
        .rename(columns={"targets": "qb_total_targets"})
    )
    qb_total_targets = qb_total_targets.sort_values(["passer_id", "season", "week"])
    qb_total_targets["qb_total_targets_roll3"] = qb_total_targets.groupby("passer_id")[
        "qb_total_targets"
    ].transform(lambda x: x.rolling(3, min_periods=1).sum())
    # Shift for temporal safety
    qb_total_targets["qb_total_targets_roll3"] = qb_total_targets.groupby("passer_id")[
        "qb_total_targets_roll3"
    ].shift(1)

    pair_lookup = pair_lookup.merge(
        qb_total_targets[["passer_id", "season", "week", "qb_total_targets_roll3"]],
        on=["passer_id", "season", "week"],
        how="left",
    )

    pair_lookup["target_share_roll3"] = np.where(
        pair_lookup["qb_total_targets_roll3"] > 0,
        pair_lookup["targets_roll3_raw"] / pair_lookup["qb_total_targets_roll3"],
        np.nan,
    )

    # Join features to receiver player-weeks
    result = receivers[["player_id", team_col, "season", "week", "qb_player_id"]].merge(
        pair_lookup.rename(
            columns={"passer_id": "qb_player_id", "receiver_id": "player_id"}
        ),
        on=["player_id", "qb_player_id", "season", "week"],
        how="left",
    )

    # Rename to final feature columns
    result = result.rename(
        columns={
            "epa_roll3_raw": "qb_wr_chemistry_epa_roll3",
            "comp_rate_roll3_raw": "qb_wr_pair_comp_rate_roll3",
            "target_share_roll3": "qb_wr_pair_target_share",
            "games_together_raw": "qb_wr_pair_games_together",
            "td_rate_roll6_raw": "qb_wr_pair_td_rate",
        }
    )

    # Keep only output columns
    out_cols = ["player_id", "season", "week"] + QB_WR_CHEMISTRY_FEATURE_COLUMNS
    available = [c for c in out_cols if c in result.columns]
    result = result[available].copy()

    # Fill missing feature columns with NaN
    for col in QB_WR_CHEMISTRY_FEATURE_COLUMNS:
        if col not in result.columns:
            result[col] = np.nan

    # Deduplicate (one row per player-week)
    result = result.drop_duplicates(
        subset=["player_id", "season", "week"], keep="first"
    )

    logger.info(
        "Computed chemistry features: %d player-weeks, %d with non-null EPA",
        len(result),
        result["qb_wr_chemistry_epa_roll3"].notna().sum(),
    )
    return result
