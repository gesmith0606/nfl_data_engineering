"""Red zone target network features from PBP data.

Computes per-player red zone usage (targets, carries, TDs, shares) and
rolling features that capture red zone specialization vs general usage.
All rolling features use shift(1) for temporal safety.

Exports:
    RED_ZONE_FEATURE_COLUMNS: List of output feature column names.
    compute_red_zone_usage: Per-player per-week red zone raw stats.
    compute_red_zone_features: Rolling features with temporal lag.
"""

import logging

import numpy as np
import pandas as pd

from config import POSITION_AVG_RZ_TD_RATE

logger = logging.getLogger(__name__)

# Output feature columns for integration with player_feature_engineering
RED_ZONE_FEATURE_COLUMNS = [
    "rz_target_share_roll3",
    "rz_carry_share_roll3",
    "rz_td_rate_roll3",
    "rz_usage_vs_general",
    "team_rz_trips_roll3",
    "rz_td_regression",
    "opp_rz_td_rate_allowed_roll3",
]


# ---------------------------------------------------------------------------
# Red zone usage computation
# ---------------------------------------------------------------------------


def compute_red_zone_usage(
    pbp_df: pd.DataFrame,
    rosters_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per-player per-team per-week red zone usage from PBP.

    Filters PBP to red zone plays (yardline_100 <= 20) and aggregates
    targets, carries, touchdowns, and team-level metrics.

    Args:
        pbp_df: Play-by-play DataFrame with yardline_100, play_type,
            receiver_player_id, rusher_player_id, touchdown, posteam,
            season, week columns.
        rosters_df: Roster DataFrame with player_id, team, position.

    Returns:
        DataFrame with columns: player_id, team, season, week,
        rz_targets, rz_carries, rz_touches, rz_tds, rz_opportunities,
        rz_target_share, rz_carry_share, rz_td_rate,
        team_rz_trips, team_rz_td_rate, team_rz_pass_rate.
        Empty DataFrame if inputs are insufficient.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    required_cols = {"yardline_100", "play_type", "posteam", "season", "week"}
    missing = required_cols - set(pbp_df.columns)
    if missing:
        logger.warning("PBP missing columns for red zone: %s", missing)
        return pd.DataFrame()

    # Filter to red zone plays (yardline_100 <= 20 means inside opponent 20)
    rz = pbp_df[
        (pbp_df["yardline_100"].notna())
        & (pbp_df["yardline_100"] <= 20)
        & (pbp_df["play_type"].isin(["pass", "run"]))
    ].copy()

    if rz.empty:
        logger.info("No red zone plays found in PBP data")
        return pd.DataFrame()

    # Ensure touchdown column exists
    if "touchdown" not in rz.columns:
        rz["touchdown"] = 0
    rz["touchdown"] = rz["touchdown"].fillna(0).astype(int)

    # --- Team-level red zone stats per week ---
    team_rz = (
        rz.groupby(["posteam", "season", "week"])
        .agg(
            team_rz_plays=("play_type", "count"),
            team_rz_pass_plays=("play_type", lambda x: (x == "pass").sum()),
            team_rz_run_plays=("play_type", lambda x: (x == "run").sum()),
            team_rz_tds=("touchdown", "sum"),
        )
        .reset_index()
    )

    # Estimate red zone trips: count distinct drives in RZ
    # Use drive column if available, otherwise approximate from play sequence
    if "drive" in rz.columns:
        drive_trips = (
            rz.groupby(["posteam", "season", "week"])["drive"]
            .nunique()
            .reset_index()
            .rename(columns={"drive": "team_rz_trips"})
        )
        team_rz = team_rz.merge(
            drive_trips, on=["posteam", "season", "week"], how="left"
        )
    else:
        # Fallback: each RZ possession is roughly 3-4 plays
        team_rz["team_rz_trips"] = (
            (team_rz["team_rz_plays"] / 3.5).clip(lower=1).round()
        )

    team_rz["team_rz_td_rate"] = np.where(
        team_rz["team_rz_trips"] > 0,
        team_rz["team_rz_tds"] / team_rz["team_rz_trips"],
        np.nan,
    )
    team_rz["team_rz_pass_rate"] = np.where(
        team_rz["team_rz_plays"] > 0,
        team_rz["team_rz_pass_plays"] / team_rz["team_rz_plays"],
        np.nan,
    )

    # --- Per-player red zone targets ---
    receiver_rz = pd.DataFrame()
    if "receiver_player_id" in rz.columns:
        pass_plays = rz[
            (rz["play_type"] == "pass") & rz["receiver_player_id"].notna()
        ].copy()
        if not pass_plays.empty:
            receiver_rz = (
                pass_plays.groupby(["receiver_player_id", "posteam", "season", "week"])
                .agg(
                    rz_targets=("play_type", "count"),
                    rz_rec_tds=("touchdown", "sum"),
                )
                .reset_index()
                .rename(columns={"receiver_player_id": "player_id", "posteam": "team"})
            )

    # --- Per-player red zone carries ---
    rusher_rz = pd.DataFrame()
    if "rusher_player_id" in rz.columns:
        run_plays = rz[
            (rz["play_type"] == "run") & rz["rusher_player_id"].notna()
        ].copy()
        if not run_plays.empty:
            rusher_rz = (
                run_plays.groupby(["rusher_player_id", "posteam", "season", "week"])
                .agg(
                    rz_carries=("play_type", "count"),
                    rz_rush_tds=("touchdown", "sum"),
                )
                .reset_index()
                .rename(columns={"rusher_player_id": "player_id", "posteam": "team"})
            )

    # Combine receiver and rusher stats
    if receiver_rz.empty and rusher_rz.empty:
        logger.info("No player-level red zone stats found")
        return pd.DataFrame()

    merge_keys = ["player_id", "team", "season", "week"]
    if not receiver_rz.empty and not rusher_rz.empty:
        player_rz = receiver_rz.merge(rusher_rz, on=merge_keys, how="outer")
    elif not receiver_rz.empty:
        player_rz = receiver_rz.copy()
    else:
        player_rz = rusher_rz.copy()

    # Fill missing counts with 0
    for col in ["rz_targets", "rz_carries", "rz_rec_tds", "rz_rush_tds"]:
        if col not in player_rz.columns:
            player_rz[col] = 0
        player_rz[col] = player_rz[col].fillna(0).astype(int)

    player_rz["rz_touches"] = player_rz["rz_targets"] + player_rz["rz_carries"]
    player_rz["rz_tds"] = player_rz["rz_rec_tds"] + player_rz["rz_rush_tds"]

    # Join team-level stats
    player_rz = player_rz.merge(
        team_rz.rename(columns={"posteam": "team"}),
        on=["team", "season", "week"],
        how="left",
    )

    # Compute shares
    player_rz["rz_target_share"] = np.where(
        player_rz["team_rz_pass_plays"] > 0,
        player_rz["rz_targets"] / player_rz["team_rz_pass_plays"],
        np.nan,
    )
    player_rz["rz_carry_share"] = np.where(
        player_rz["team_rz_run_plays"] > 0,
        player_rz["rz_carries"] / player_rz["team_rz_run_plays"],
        np.nan,
    )
    player_rz["rz_td_rate"] = np.where(
        player_rz["rz_touches"] > 0,
        player_rz["rz_tds"] / player_rz["rz_touches"],
        np.nan,
    )
    player_rz["rz_opportunities"] = player_rz["team_rz_plays"]

    # Clean output columns
    out_cols = [
        "player_id",
        "team",
        "season",
        "week",
        "rz_targets",
        "rz_carries",
        "rz_touches",
        "rz_tds",
        "rz_opportunities",
        "rz_target_share",
        "rz_carry_share",
        "rz_td_rate",
        "team_rz_trips",
        "team_rz_td_rate",
        "team_rz_pass_rate",
    ]
    for c in out_cols:
        if c not in player_rz.columns:
            player_rz[c] = np.nan

    return player_rz[out_cols].drop_duplicates(
        subset=["player_id", "team", "season", "week"]
    )


# ---------------------------------------------------------------------------
# Rolling red zone features with temporal lag
# ---------------------------------------------------------------------------


def compute_red_zone_features(
    rz_usage_df: pd.DataFrame,
    player_weekly_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute rolling red zone features with shift(1) temporal lag.

    For each player-week, computes:
    - rz_target_share_roll3: rolling 3-game RZ target share
    - rz_carry_share_roll3: rolling 3-game RZ carry share
    - rz_td_rate_roll3: rolling 3-game RZ TD rate
    - rz_usage_vs_general: RZ target share / overall target share (>1 = RZ specialist)
    - team_rz_trips_roll3: team's rolling 3-game RZ trips per game
    - rz_td_regression: player's RZ TD rate vs position expected rate
    - opp_rz_td_rate_allowed_roll3: opponent defense's RZ TD rate allowed (rolling 3)

    All rolling features use shift(1) to prevent temporal leakage.

    Args:
        rz_usage_df: Output of compute_red_zone_usage with per-player-week
            red zone stats.
        player_weekly_df: Bronze player_weekly with player_id, recent_team,
            season, week, position, targets, target_share columns.

    Returns:
        DataFrame with player_id, season, week, and RED_ZONE_FEATURE_COLUMNS.
        Empty DataFrame if inputs are insufficient.
    """
    if rz_usage_df.empty:
        return pd.DataFrame()

    rz = rz_usage_df.copy()

    # Sort for rolling computations
    rz = rz.sort_values(["player_id", "season", "week"]).reset_index(drop=True)

    # --- Rolling player-level features with shift(1) ---
    group_cols = ["player_id", "season"]

    rz["rz_target_share_roll3"] = rz.groupby(group_cols)["rz_target_share"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )

    rz["rz_carry_share_roll3"] = rz.groupby(group_cols)["rz_carry_share"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )

    rz["rz_td_rate_roll3"] = rz.groupby(group_cols)["rz_td_rate"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )

    # --- Team-level rolling RZ trips ---
    # De-dup to team-level first, then join back
    team_trips = (
        rz[["team", "season", "week", "team_rz_trips"]]
        .drop_duplicates(subset=["team", "season", "week"])
        .sort_values(["team", "season", "week"])
    )
    team_trips["team_rz_trips_roll3"] = team_trips.groupby(["team", "season"])[
        "team_rz_trips"
    ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())

    rz = rz.merge(
        team_trips[["team", "season", "week", "team_rz_trips_roll3"]],
        on=["team", "season", "week"],
        how="left",
    )

    # --- RZ usage vs general target share ---
    if not player_weekly_df.empty and "target_share" in player_weekly_df.columns:
        pw = player_weekly_df[["player_id", "season", "week", "target_share"]].copy()
        pw = pw.rename(columns={"target_share": "general_target_share"})
        pw = pw.drop_duplicates(subset=["player_id", "season", "week"])

        rz = rz.merge(pw, on=["player_id", "season", "week"], how="left")

        # Compute general target share rolling with shift(1) for fair comparison
        rz["general_ts_roll3"] = rz.groupby(group_cols)[
            "general_target_share"
        ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())

        rz["rz_usage_vs_general"] = np.where(
            (rz["general_ts_roll3"].notna()) & (rz["general_ts_roll3"] > 0),
            rz["rz_target_share_roll3"] / rz["general_ts_roll3"],
            np.nan,
        )
        rz = rz.drop(
            columns=["general_target_share", "general_ts_roll3"], errors="ignore"
        )
    else:
        rz["rz_usage_vs_general"] = np.nan

    # --- TD regression feature ---
    # Compare player's RZ TD rate to position-average expected rate
    if not player_weekly_df.empty and "position" in player_weekly_df.columns:
        pos_map = player_weekly_df[["player_id", "position"]].drop_duplicates(
            subset=["player_id"], keep="last"
        )
        rz = rz.merge(pos_map, on="player_id", how="left")

        expected_rate = rz["position"].map(POSITION_AVG_RZ_TD_RATE).fillna(0.10)
        rz["rz_td_regression"] = np.where(
            rz["rz_td_rate_roll3"].notna(),
            rz["rz_td_rate_roll3"] - expected_rate,
            np.nan,
        )
        rz = rz.drop(columns=["position"], errors="ignore")
    else:
        rz["rz_td_regression"] = np.nan

    # --- Opponent RZ TD rate allowed (rolling 3, shift(1)) ---
    # Build defensive RZ TD rate from team_rz_td_rate (opponent perspective)
    def_rz = (
        rz[["team", "season", "week", "team_rz_td_rate"]]
        .drop_duplicates(subset=["team", "season", "week"])
        .sort_values(["team", "season", "week"])
    )
    def_rz["opp_rz_td_rate_allowed_roll3"] = def_rz.groupby(["team", "season"])[
        "team_rz_td_rate"
    ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())

    # Map opponent team from player_weekly
    if not player_weekly_df.empty:
        opp_cols = ["player_id", "season", "week"]
        if "opponent_team" in player_weekly_df.columns:
            opp_cols.append("opponent_team")
        elif "opponent" in player_weekly_df.columns:
            opp_cols.append("opponent")

        if len(opp_cols) > 3:
            opp_map = player_weekly_df[opp_cols].drop_duplicates(
                subset=["player_id", "season", "week"]
            )
            opp_col_name = opp_cols[-1]
            rz = rz.merge(opp_map, on=["player_id", "season", "week"], how="left")

            rz = rz.merge(
                def_rz[["team", "season", "week", "opp_rz_td_rate_allowed_roll3"]],
                left_on=[opp_col_name, "season", "week"],
                right_on=["team", "season", "week"],
                how="left",
                suffixes=("", "_opp"),
            )
            rz = rz.drop(
                columns=[opp_col_name, "team_opp"],
                errors="ignore",
            )
        else:
            rz["opp_rz_td_rate_allowed_roll3"] = np.nan
    else:
        rz["opp_rz_td_rate_allowed_roll3"] = np.nan

    # --- Output ---
    out_cols = ["player_id", "season", "week"] + RED_ZONE_FEATURE_COLUMNS
    for c in out_cols:
        if c not in rz.columns:
            rz[c] = np.nan

    result = rz[out_cols].drop_duplicates(subset=["player_id", "season", "week"])
    logger.info(
        "Computed %d red zone feature rows (%d players, %d weeks)",
        len(result),
        result["player_id"].nunique(),
        result["week"].nunique() if not result.empty else 0,
    )
    return result
