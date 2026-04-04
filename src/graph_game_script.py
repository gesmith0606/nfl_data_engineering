"""Game script role shift features — how player usage changes by score state.

Computes per-player usage splits across five game script zones (leading_big,
leading, close, trailing, trailing_big) from play-by-play data, then builds
rolling features that capture role sensitivity to game flow.

All rolling features use shift(1) to prevent temporal leakage.

Exports:
    compute_game_script_usage: Per-player per-game usage by script zone.
    compute_game_script_features: Rolling features + predicted script boost.
    GAME_SCRIPT_FEATURE_COLUMNS: List of output feature column names.
"""

import logging
from typing import List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Game script zone boundaries (from offensive team perspective)
SCRIPT_ZONES = {
    "leading_big": (14, None),  # score_diff >= 14
    "leading": (7, 14),  # 7 <= score_diff < 14
    "close": (-6, 7),  # -6 <= score_diff <= 6  (upper exclusive adjusted below)
    "trailing": (-13, -6),  # -13 <= score_diff < -6  (upper exclusive adjusted below)
    "trailing_big": (None, -13),  # score_diff < -13  (upper exclusive adjusted below)
}

# Output feature columns
GAME_SCRIPT_FEATURE_COLUMNS = [
    "usage_when_trailing_roll3",
    "usage_when_leading_roll3",
    "garbage_time_share_roll3",
    "clock_killer_share_roll3",
    "script_volatility",
    "predicted_script_boost",
]


# ---------------------------------------------------------------------------
# Zone classification
# ---------------------------------------------------------------------------


def _classify_script_zone(score_diff: float) -> str:
    """Classify a score differential into a game script zone.

    Args:
        score_diff: Score differential from offensive team's perspective
            (positive = leading).

    Returns:
        One of: leading_big, leading, close, trailing, trailing_big.
    """
    if score_diff >= 14:
        return "leading_big"
    elif score_diff >= 7:
        return "leading"
    elif score_diff >= -6:
        return "close"
    elif score_diff >= -13:
        return "trailing"
    else:
        return "trailing_big"


# ---------------------------------------------------------------------------
# Core computation: per-player per-game script usage
# ---------------------------------------------------------------------------


def compute_game_script_usage(
    pbp_df: pd.DataFrame,
    player_weekly_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute per-player per-game usage breakdown by game script zone.

    For each play, determines the script zone from score_differential (or
    computes it from posteam_score - defteam_score). Then aggregates player
    involvement (targets, carries, yards, TDs, receptions) per zone per game.

    Args:
        pbp_df: Play-by-play DataFrame with standard nflverse columns including
            play_type, score_differential (or posteam_score/defteam_score),
            receiver_player_id, rusher_player_id, yards_gained, touchdown,
            complete_pass, posteam, season, week.
        player_weekly_df: Optional player weekly data for supplemental info.
            Not required for core computation.

    Returns:
        DataFrame with columns: player_id, season, week, recent_team,
        and per-zone columns (targets_close, carries_leading_big, etc.)
        plus total columns and zone share columns.
        Empty DataFrame if PBP data is insufficient.
    """
    if pbp_df.empty:
        return pd.DataFrame()

    df = pbp_df.copy()

    # Compute score differential if not present
    if "score_differential" not in df.columns:
        if "posteam_score" in df.columns and "defteam_score" in df.columns:
            df["score_differential"] = df["posteam_score"] - df["defteam_score"]
        else:
            logger.warning(
                "No score_differential or posteam_score/defteam_score in PBP"
            )
            return pd.DataFrame()

    # Classify each play into a script zone
    df["script_zone"] = df["score_differential"].apply(_classify_script_zone)

    # Filter to skill plays (pass and run only)
    skill_mask = df["play_type"].isin(["pass", "run"])
    df = df[skill_mask].copy()

    if df.empty:
        return pd.DataFrame()

    # Build player-play rows for targets and carries
    rows: List[dict] = []

    # --- Targets (pass plays with a receiver) ---
    pass_plays = df[
        (df["play_type"] == "pass") & df["receiver_player_id"].notna()
    ].copy()

    if not pass_plays.empty:
        for _, play in pass_plays.iterrows():
            rows.append(
                {
                    "player_id": str(play["receiver_player_id"]),
                    "season": int(play["season"]),
                    "week": int(play["week"]),
                    "recent_team": str(play["posteam"]),
                    "script_zone": play["script_zone"],
                    "targets": 1,
                    "carries": 0,
                    "receptions": int(play.get("complete_pass", 0) or 0),
                    "yards": float(play.get("yards_gained", 0) or 0),
                    "tds": int(play.get("pass_touchdown", 0) or 0),
                }
            )

    # --- Carries (run plays with a rusher) ---
    run_plays = df[(df["play_type"] == "run") & df["rusher_player_id"].notna()].copy()

    if not run_plays.empty:
        for _, play in run_plays.iterrows():
            rows.append(
                {
                    "player_id": str(play["rusher_player_id"]),
                    "season": int(play["season"]),
                    "week": int(play["week"]),
                    "recent_team": str(play["posteam"]),
                    "script_zone": play["script_zone"],
                    "targets": 0,
                    "carries": 1,
                    "receptions": 0,
                    "yards": float(play.get("yards_gained", 0) or 0),
                    "tds": int(play.get("rush_touchdown", 0) or 0),
                }
            )

    if not rows:
        return pd.DataFrame()

    play_df = pd.DataFrame(rows)

    # Aggregate per player-game-zone
    zone_agg = (
        play_df.groupby(["player_id", "season", "week", "recent_team", "script_zone"])
        .agg(
            targets=("targets", "sum"),
            carries=("carries", "sum"),
            receptions=("receptions", "sum"),
            yards=("yards", "sum"),
            tds=("tds", "sum"),
            plays=("targets", "count"),
        )
        .reset_index()
    )

    # Pivot zones into columns
    zones = ["leading_big", "leading", "close", "trailing", "trailing_big"]
    stats = ["targets", "carries", "receptions", "yards", "tds", "plays"]

    # First get player-game totals
    game_totals = (
        zone_agg.groupby(["player_id", "season", "week", "recent_team"])[stats]
        .sum()
        .reset_index()
    )
    game_totals = game_totals.rename(columns={s: f"total_{s}" for s in stats})

    # Pivot each zone
    result = game_totals.copy()
    for zone in zones:
        zone_data = zone_agg[zone_agg["script_zone"] == zone].copy()
        if zone_data.empty:
            for s in stats:
                result[f"{s}_{zone}"] = 0
            continue
        zone_data = zone_data.rename(columns={s: f"{s}_{zone}" for s in stats})
        zone_data = zone_data.drop(columns=["script_zone"])
        result = result.merge(
            zone_data,
            on=["player_id", "season", "week", "recent_team"],
            how="left",
        )

    # Fill NaN zone columns with 0
    zone_cols = [f"{s}_{z}" for z in zones for s in stats]
    for col in zone_cols:
        if col in result.columns:
            result[col] = result[col].fillna(0).astype(int)
        else:
            result[col] = 0

    # Compute zone share columns (usage_pct in each zone)
    for zone in zones:
        for stat in ["targets", "carries"]:
            total_col = f"total_{stat}"
            zone_col = f"{stat}_{zone}"
            share_col = f"{stat}_share_{zone}"
            result[share_col] = np.where(
                result[total_col] > 0,
                result[zone_col] / result[total_col],
                0.0,
            )

    logger.info("Computed game script usage: %d player-game rows", len(result))
    return result


# ---------------------------------------------------------------------------
# Rolling features
# ---------------------------------------------------------------------------


def compute_game_script_features(
    game_script_df: pd.DataFrame,
    schedules_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute rolling game script features from per-game script usage.

    For each player-week, computes shift(1) lagged rolling features:
    - usage_when_trailing_roll3: share of targets+carries when trailing/trailing_big
    - usage_when_leading_roll3: share when leading/leading_big
    - garbage_time_share_roll3: share of production (yards) in trailing_big
    - clock_killer_share_roll3: share of carries when leading_big (RB-specific)
    - script_volatility: std dev of zone usage shares across zones
    - predicted_script_boost: multiplier based on predicted spread

    All rolling features use shift(1) for temporal safety.

    Args:
        game_script_df: Output of compute_game_script_usage with per-zone
            usage columns and totals.
        schedules_df: Optional Bronze schedules with spread_line for
            predicted_script_boost. If None, boost is set to 1.0.

    Returns:
        DataFrame with player_id, season, week, and GAME_SCRIPT_FEATURE_COLUMNS.
        Empty DataFrame if input is empty.
    """
    if game_script_df.empty:
        return pd.DataFrame()

    df = game_script_df.copy()
    df = df.sort_values(["player_id", "season", "week"]).reset_index(drop=True)

    # --- Compute raw per-game ratios ---

    # Total usage = targets + carries
    df["total_usage"] = df["total_targets"] + df["total_carries"]

    # Trailing usage share (trailing + trailing_big)
    trailing_usage = (
        df.get("targets_trailing", 0)
        + df.get("carries_trailing", 0)
        + df.get("targets_trailing_big", 0)
        + df.get("carries_trailing_big", 0)
    )
    df["trailing_usage_share"] = np.where(
        df["total_usage"] > 0, trailing_usage / df["total_usage"], 0.0
    )

    # Leading usage share (leading + leading_big)
    leading_usage = (
        df.get("targets_leading", 0)
        + df.get("carries_leading", 0)
        + df.get("targets_leading_big", 0)
        + df.get("carries_leading_big", 0)
    )
    df["leading_usage_share"] = np.where(
        df["total_usage"] > 0, leading_usage / df["total_usage"], 0.0
    )

    # Garbage time share (yards in trailing_big / total yards)
    df["garbage_time_share_raw"] = np.where(
        df["total_yards"] > 0,
        df.get("yards_trailing_big", 0) / df["total_yards"],
        0.0,
    )

    # Clock killer share (carries in leading_big / total carries)
    df["clock_killer_share_raw"] = np.where(
        df["total_carries"] > 0,
        df.get("carries_leading_big", 0) / df["total_carries"],
        0.0,
    )

    # Script volatility: std dev across the 5 zone usage shares
    zone_share_cols = []
    for zone in ["leading_big", "leading", "close", "trailing", "trailing_big"]:
        col = f"usage_share_{zone}"
        df[col] = np.where(
            df["total_usage"] > 0,
            (df.get(f"targets_{zone}", 0) + df.get(f"carries_{zone}", 0))
            / df["total_usage"],
            0.0,
        )
        zone_share_cols.append(col)

    df["script_volatility_raw"] = df[zone_share_cols].std(axis=1)

    # --- Apply shift(1) rolling aggregations ---
    group = df.groupby(["player_id", "season"])

    df["usage_when_trailing_roll3"] = group["trailing_usage_share"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    df["usage_when_leading_roll3"] = group["leading_usage_share"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    df["garbage_time_share_roll3"] = group["garbage_time_share_raw"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    df["clock_killer_share_roll3"] = group["clock_killer_share_raw"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )
    df["script_volatility"] = group["script_volatility_raw"].transform(
        lambda s: s.shift(1).rolling(3, min_periods=1).mean()
    )

    # --- Predicted script boost ---
    df["predicted_script_boost"] = 1.0

    if schedules_df is not None and not schedules_df.empty:
        df = _add_predicted_script_boost(df, schedules_df)

    # Select output columns
    out_cols = [
        "player_id",
        "season",
        "week",
        "recent_team",
    ] + GAME_SCRIPT_FEATURE_COLUMNS
    for c in out_cols:
        if c not in df.columns:
            df[c] = np.nan

    result = df[out_cols].copy()
    logger.info("Computed game script features: %d player-week rows", len(result))
    return result


def _add_predicted_script_boost(
    df: pd.DataFrame,
    schedules_df: pd.DataFrame,
) -> pd.DataFrame:
    """Add predicted_script_boost based on Vegas spread from schedules.

    Multiplier: 1.0 + (predicted_spread * 0.01), capped at [0.90, 1.10].
    Where predicted_spread is from the team's perspective (negative = favorite).

    For 7+ point favorites: boosts leading usage players.
    For 7+ point underdogs: boosts trailing usage players.
    Combined: boost = base * (1 + trailing_roll3 * factor) for underdogs,
              boost = base * (1 + leading_roll3 * factor) for favorites.

    Args:
        df: Player-week DataFrame with recent_team, season, week,
            usage_when_trailing_roll3, usage_when_leading_roll3.
        schedules_df: Bronze schedules with home_team, away_team, spread_line.

    Returns:
        DataFrame with predicted_script_boost column updated.
    """
    sched = schedules_df.copy()

    # Filter to regular season if game_type available
    if "game_type" in sched.columns:
        sched = sched[sched["game_type"] == "REG"].copy()

    required = {"season", "week", "home_team", "away_team", "spread_line"}
    if not required.issubset(sched.columns):
        return df

    # Reshape to per-team spread (from team perspective: negative = favored)
    # spread_line is typically: home_team spread (negative if home favored)
    home = sched[["season", "week", "home_team", "spread_line"]].copy()
    home = home.rename(columns={"home_team": "team", "spread_line": "team_spread"})

    away = sched[["season", "week", "away_team", "spread_line"]].copy()
    away["spread_line"] = -away["spread_line"]  # flip for away team
    away = away.rename(columns={"away_team": "team", "spread_line": "team_spread"})

    team_spreads = pd.concat([home, away], ignore_index=True)

    df = df.merge(
        team_spreads,
        left_on=["recent_team", "season", "week"],
        right_on=["team", "season", "week"],
        how="left",
    )
    if "team" in df.columns and "recent_team" in df.columns:
        df = df.drop(columns=["team"], errors="ignore")

    # Compute boost: 1.0 + (spread * 0.01) capped at [0.90, 1.10]
    # Negative spread = favorite (leading expected), positive = underdog (trailing expected)
    if "team_spread" in df.columns:
        # Base multiplier from spread magnitude
        raw_boost = 1.0 + (df["team_spread"].fillna(0) * -0.01)
        df["predicted_script_boost"] = raw_boost.clip(0.90, 1.10)
    else:
        df["predicted_script_boost"] = 1.0

    # Clean up
    df = df.drop(columns=["team_spread"], errors="ignore")

    return df
