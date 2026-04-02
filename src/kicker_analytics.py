#!/usr/bin/env python3
"""
Kicker Analytics Module

Computes kicker stats from play-by-play data, team-level kicker opportunity
features, and opponent defensive features that drive field goal volume.

All functions operate on DataFrames — no direct S3 or API calls.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Kicker scoring constants
# ---------------------------------------------------------------------------
KICKER_SCORING: Dict[str, float] = {
    "fg_made": 3.0,
    "fg_made_50plus": 5.0,  # replaces the 3-pt base for 50+ yarders
    "xp_made": 1.0,
    "fg_missed": -1.0,
    "xp_missed": -1.0,
}

# Distance bucket boundaries (yards)
_SHORT_MAX = 39
_MEDIUM_MAX = 49


# ---------------------------------------------------------------------------
# 1. Kicker stat extraction from PBP
# ---------------------------------------------------------------------------


def compute_kicker_stats(
    pbp_df: pd.DataFrame,
    season: int,
    week: Optional[int] = None,
) -> pd.DataFrame:
    """Extract per-kicker, per-week stats from play-by-play data.

    Computes FG attempts/makes by distance bucket (short <40, medium 40-49,
    long 50+), XP attempts/makes, accuracy rates, and fantasy points.

    Args:
        pbp_df: Play-by-play DataFrame with columns: play_type, kicker_player_id,
            kicker_player_name, field_goal_result, kick_distance,
            extra_point_result, posteam, season, week.
        season: NFL season to filter.
        week: Optional week filter. If None, returns all weeks for the season.

    Returns:
        DataFrame with one row per kicker per week, columns:
            kicker_player_id, kicker_player_name, team, season, week,
            fg_att, fg_made, fg_att_short, fg_made_short,
            fg_att_medium, fg_made_medium, fg_att_long, fg_made_long,
            fg_pct, fg_pct_short, fg_pct_medium, fg_pct_long,
            xp_att, xp_made, xp_pct,
            fantasy_points
    """
    if pbp_df.empty:
        logger.warning("Empty PBP DataFrame; returning empty kicker stats")
        return pd.DataFrame()

    df = pbp_df[pbp_df["season"] == season].copy()
    if week is not None:
        df = df[df["week"] == week]

    if df.empty:
        return pd.DataFrame()

    # --- Field goals ---
    fg_df = df[
        (df["play_type"] == "field_goal") & df["kicker_player_id"].notna()
    ].copy()

    fg_df["fg_made"] = (fg_df["field_goal_result"] == "made").astype(int)
    fg_df["distance"] = fg_df["kick_distance"].fillna(0).astype(float)

    # Distance buckets
    fg_df["bucket"] = pd.cut(
        fg_df["distance"],
        bins=[0, _SHORT_MAX, _MEDIUM_MAX, 100],
        labels=["short", "medium", "long"],
        right=True,
    )

    fg_agg = (
        fg_df.groupby(
            ["kicker_player_id", "kicker_player_name", "posteam", "season", "week"]
        )
        .agg(
            fg_att=("fg_made", "count"),
            fg_made=("fg_made", "sum"),
        )
        .reset_index()
    )

    # Per-bucket aggregates
    for bucket_name in ["short", "medium", "long"]:
        bucket_data = fg_df[fg_df["bucket"] == bucket_name]
        bucket_agg = (
            bucket_data.groupby(
                ["kicker_player_id", "kicker_player_name", "posteam", "season", "week"]
            )
            .agg(
                **{
                    f"fg_att_{bucket_name}": ("fg_made", "count"),
                    f"fg_made_{bucket_name}": ("fg_made", "sum"),
                }
            )
            .reset_index()
        )
        fg_agg = fg_agg.merge(
            bucket_agg,
            on=["kicker_player_id", "kicker_player_name", "posteam", "season", "week"],
            how="left",
        )

    # Fill NaN bucket counts with 0
    bucket_cols = [
        c for c in fg_agg.columns if c.startswith("fg_att_") or c.startswith("fg_made_")
    ]
    fg_agg[bucket_cols] = fg_agg[bucket_cols].fillna(0).astype(int)

    # --- Extra points ---
    xp_df = df[
        (df["play_type"] == "extra_point") & df["kicker_player_id"].notna()
    ].copy()

    xp_df["xp_made"] = (xp_df["extra_point_result"] == "good").astype(int)

    xp_agg = (
        xp_df.groupby(
            ["kicker_player_id", "kicker_player_name", "posteam", "season", "week"]
        )
        .agg(
            xp_att=("xp_made", "count"),
            xp_made=("xp_made", "sum"),
        )
        .reset_index()
    )

    # --- Merge FG + XP ---
    if fg_agg.empty and xp_agg.empty:
        return pd.DataFrame()

    merge_keys = ["kicker_player_id", "kicker_player_name", "posteam", "season", "week"]
    if not fg_agg.empty and not xp_agg.empty:
        result = fg_agg.merge(xp_agg, on=merge_keys, how="outer")
    elif not fg_agg.empty:
        result = fg_agg.copy()
    else:
        result = xp_agg.copy()

    # Fill NaN numeric columns
    numeric_cols = [c for c in result.columns if c not in merge_keys]
    result[numeric_cols] = result[numeric_cols].fillna(0).astype(int)

    # Accuracy rates
    result["fg_pct"] = np.where(
        result["fg_att"] > 0, result["fg_made"] / result["fg_att"], 0.0
    )
    for bucket_name in ["short", "medium", "long"]:
        att_col = f"fg_att_{bucket_name}"
        made_col = f"fg_made_{bucket_name}"
        pct_col = f"fg_pct_{bucket_name}"
        if att_col in result.columns and made_col in result.columns:
            result[pct_col] = np.where(
                result[att_col] > 0, result[made_col] / result[att_col], 0.0
            )
        else:
            result[pct_col] = 0.0

    xp_att_col = "xp_att" if "xp_att" in result.columns else None
    if xp_att_col:
        result["xp_pct"] = np.where(
            result["xp_att"] > 0, result["xp_made"] / result["xp_att"], 0.0
        )
    else:
        result["xp_pct"] = 0.0

    # Fantasy points
    result["fantasy_points"] = (
        (result.get("fg_made", 0) - result.get("fg_made_long", 0))
        * KICKER_SCORING["fg_made"]
        + result.get("fg_made_long", 0) * KICKER_SCORING["fg_made_50plus"]
        + result.get("xp_made", 0) * KICKER_SCORING["xp_made"]
        + (result.get("fg_att", 0) - result.get("fg_made", 0))
        * KICKER_SCORING["fg_missed"]
        + (result.get("xp_att", 0) - result.get("xp_made", 0))
        * KICKER_SCORING["xp_missed"]
    ).round(2)

    result = result.rename(columns={"posteam": "team"})

    logger.info(
        "Computed kicker stats: %d kicker-weeks for season %d%s",
        len(result),
        season,
        f" week {week}" if week else "",
    )
    return result


# ---------------------------------------------------------------------------
# 2. Team-level kicker opportunity features
# ---------------------------------------------------------------------------


def compute_team_kicker_features(
    pbp_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Compute per-team, per-week kicker opportunity features.

    Features (rolling 3-game average, shifted by 1 week):
        - red_zone_stall_rate: (RZ drives - RZ TDs) / RZ drives
        - fg_attempts_per_game: rolling average of FG attempts
        - fg_range_drives: drives reaching inside the 40 yard line

    Args:
        pbp_df: Play-by-play DataFrame.
        schedules_df: Schedule DataFrame with home_team, away_team, week.
        season: NFL season.

    Returns:
        DataFrame with team, season, week, and feature columns.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    df = pbp_df[pbp_df["season"] == season].copy()
    if df.empty:
        return pd.DataFrame()

    weeks = sorted(df["week"].unique())
    records = []

    for team in df["posteam"].dropna().unique():
        team_plays = df[df["posteam"] == team]

        for wk in weeks:
            wk_plays = team_plays[team_plays["week"] == wk]
            if wk_plays.empty:
                continue

            # Red zone drives: plays where yardline_100 <= 20
            rz_plays = wk_plays[wk_plays["yardline_100"].fillna(100) <= 20]
            rz_drives = rz_plays["drive"].nunique() if not rz_plays.empty else 0
            rz_tds = rz_plays["touchdown"].sum() if not rz_plays.empty else 0
            rz_stall = (rz_drives - rz_tds) / rz_drives if rz_drives > 0 else 0.0

            # FG attempts
            fg_att = len(wk_plays[wk_plays["play_type"] == "field_goal"])

            # Drives reaching FG range (inside 40)
            fg_range_plays = wk_plays[wk_plays["yardline_100"].fillna(100) <= 40]
            fg_range_drives = (
                fg_range_plays["drive"].nunique() if not fg_range_plays.empty else 0
            )

            records.append(
                {
                    "team": team,
                    "season": season,
                    "week": wk,
                    "rz_stall_rate_raw": rz_stall,
                    "fg_attempts_raw": fg_att,
                    "fg_range_drives_raw": fg_range_drives,
                }
            )

    if not records:
        return pd.DataFrame()

    features_df = pd.DataFrame(records)

    # Rolling 3-game average, shifted by 1 (so week N uses weeks N-3 to N-1)
    features_df = features_df.sort_values(["team", "week"])
    for col in ["rz_stall_rate_raw", "fg_attempts_raw", "fg_range_drives_raw"]:
        out_col = col.replace("_raw", "")
        features_df[out_col] = features_df.groupby("team")[col].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        )

    # Drop raw columns
    features_df = features_df.drop(
        columns=["rz_stall_rate_raw", "fg_attempts_raw", "fg_range_drives_raw"]
    )

    # Rename for clarity
    features_df = features_df.rename(
        columns={
            "rz_stall_rate": "red_zone_stall_rate",
            "fg_attempts": "fg_attempts_per_game",
        }
    )

    logger.info(
        "Computed team kicker features: %d team-weeks for season %d",
        len(features_df),
        season,
    )
    return features_df


# ---------------------------------------------------------------------------
# 3. Opponent kicker-relevant defensive features
# ---------------------------------------------------------------------------


def compute_opponent_kicker_features(
    pbp_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    season: int,
) -> pd.DataFrame:
    """Compute per-defense, per-week features relevant to opposing kicker value.

    Features (rolling 3-game average, shifted by 1 week):
        - opp_rz_td_rate_allowed: how often opposing offenses score TDs in RZ
        - opp_fg_range_drives_allowed: drives opponent allows into FG range

    Args:
        pbp_df: Play-by-play DataFrame.
        schedules_df: Schedule DataFrame (unused currently, kept for API consistency).
        season: NFL season.

    Returns:
        DataFrame with defense_team, season, week, and feature columns.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    df = pbp_df[pbp_df["season"] == season].copy()
    if df.empty:
        return pd.DataFrame()

    weeks = sorted(df["week"].unique())
    records = []

    for def_team in df["defteam"].dropna().unique():
        def_plays = df[df["defteam"] == def_team]

        for wk in weeks:
            wk_plays = def_plays[def_plays["week"] == wk]
            if wk_plays.empty:
                continue

            # Opposing offense red zone performance
            rz_plays = wk_plays[wk_plays["yardline_100"].fillna(100) <= 20]
            rz_drives = rz_plays["drive"].nunique() if not rz_plays.empty else 0
            rz_tds = rz_plays["touchdown"].sum() if not rz_plays.empty else 0
            rz_td_rate = rz_tds / rz_drives if rz_drives > 0 else 0.0

            # Drives opponent allows into FG range (inside 40)
            fg_range_plays = wk_plays[wk_plays["yardline_100"].fillna(100) <= 40]
            fg_range_drives = (
                fg_range_plays["drive"].nunique() if not fg_range_plays.empty else 0
            )

            records.append(
                {
                    "defense_team": def_team,
                    "season": season,
                    "week": wk,
                    "opp_rz_td_rate_raw": rz_td_rate,
                    "opp_fg_range_drives_raw": fg_range_drives,
                }
            )

    if not records:
        return pd.DataFrame()

    opp_df = pd.DataFrame(records)
    opp_df = opp_df.sort_values(["defense_team", "week"])

    for col in ["opp_rz_td_rate_raw", "opp_fg_range_drives_raw"]:
        out_col = col.replace("_raw", "")
        opp_df[out_col] = opp_df.groupby("defense_team")[col].transform(
            lambda x: x.rolling(3, min_periods=1).mean().shift(1)
        )

    opp_df = opp_df.drop(columns=["opp_rz_td_rate_raw", "opp_fg_range_drives_raw"])
    opp_df = opp_df.rename(
        columns={
            "opp_rz_td_rate": "opp_rz_td_rate_allowed",
            "opp_fg_range_drives": "opp_fg_range_drives_allowed",
        }
    )

    logger.info(
        "Computed opponent kicker features: %d defense-weeks for season %d",
        len(opp_df),
        season,
    )
    return opp_df
