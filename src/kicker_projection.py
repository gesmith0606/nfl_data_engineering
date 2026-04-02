#!/usr/bin/env python3
"""
Kicker Projection Engine

Generates weekly kicker fantasy projections using:
    - Historical kicker accuracy and volume (rolling averages)
    - Team-level red zone stall rate and FG opportunity features
    - Opponent defensive features (RZ TD rate allowed)
    - Game script multiplier (spread-based)
    - Venue/weather adjustments (dome, altitude, wind)

Designed to integrate alongside the main projection_engine.py for
QB/RB/WR/TE projections.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

from kicker_analytics import KICKER_SCORING

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Teams that play in domed/enclosed stadiums (no weather impact)
DOME_TEAMS = {"ARI", "ATL", "DAL", "DET", "HOU", "IND", "LV", "MIN", "NO", "LA", "LAC"}

# Denver — high altitude increases FG range
HIGH_ALTITUDE_TEAMS = {"DEN"}

# Default kicker baseline stats per game (league average)
_KICKER_BASELINE = {
    "fg_att_per_game": 1.8,
    "fg_pct": 0.84,
    "fg_pct_long": 0.72,
    "xp_att_per_game": 3.2,
    "xp_pct": 0.94,
}

# Floor/ceiling variance for kickers
_KICKER_VARIANCE = 0.40


# ---------------------------------------------------------------------------
# Game script multiplier
# ---------------------------------------------------------------------------


def _game_script_multiplier(spread: float) -> float:
    """Compute a game-script multiplier for kicker projections.

    Close games (|spread| < 7) produce more FG opportunities.
    Blowouts (|spread| > 14) reduce FG attempts (garbage time / kneel-downs).

    Args:
        spread: Point spread from the kicker's team perspective.
            Negative means the kicker's team is favored.

    Returns:
        Multiplier in [0.85, 1.10].
    """
    abs_spread = abs(spread)
    if abs_spread < 7.0:
        return 1.10
    elif abs_spread > 14.0:
        return 0.85
    else:
        return 1.0


# ---------------------------------------------------------------------------
# Venue / weather multiplier
# ---------------------------------------------------------------------------


def _venue_weather_multiplier(
    home_team: str,
    wind: Optional[float] = None,
    roof: Optional[str] = None,
) -> float:
    """Compute a venue/weather adjustment for kicker accuracy.

    - Dome: 1.05x (no weather interference)
    - High altitude (Denver): 1.05x for distance (thinner air helps range)
    - High wind (>15 mph): 0.90x

    These are multiplicative if multiple apply, though in practice dome
    and wind are mutually exclusive.

    Args:
        home_team: Home team abbreviation (determines venue).
        wind: Wind speed in mph. None if unavailable.
        roof: Roof type from PBP ('dome', 'outdoors', 'closed', 'open').

    Returns:
        Multiplier, typically in [0.85, 1.10].
    """
    mult = 1.0

    is_dome = home_team in DOME_TEAMS or (
        roof is not None and roof.lower() in ("dome", "closed")
    )

    if is_dome:
        mult *= 1.05
    elif wind is not None and wind > 15.0:
        mult *= 0.90

    if home_team in HIGH_ALTITUDE_TEAMS:
        mult *= 1.05

    return round(mult, 4)


# ---------------------------------------------------------------------------
# Opponent RZ defense multiplier
# ---------------------------------------------------------------------------


def _opponent_rz_multiplier(
    opp_rz_td_rate: float,
    league_avg_rz_td_rate: float = 0.55,
) -> float:
    """Compute multiplier based on opponent red zone TD defense.

    A stingy RZ defense (low TD rate allowed) means more FG opportunities
    for the opposing kicker.

    Args:
        opp_rz_td_rate: Opponent's RZ TD rate allowed (0-1).
        league_avg_rz_td_rate: League average RZ TD rate for baseline.

    Returns:
        Multiplier in [0.90, 1.15].
    """
    if opp_rz_td_rate < league_avg_rz_td_rate:
        # Stingy defense -> more FGs -> boost kicker
        return 1.10
    elif opp_rz_td_rate > league_avg_rz_td_rate + 0.10:
        # Generous defense -> more TDs -> fewer FGs
        return 0.90
    return 1.0


# ---------------------------------------------------------------------------
# Main projection function
# ---------------------------------------------------------------------------


def generate_kicker_projections(
    kicker_stats_df: pd.DataFrame,
    team_features_df: pd.DataFrame,
    opp_features_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    season: int,
    week: int,
) -> pd.DataFrame:
    """Generate weekly kicker fantasy projections.

    Projection formula:
        base_fg_pts = team_fg_attempts_per_game * kicker_fg_pct * pts_per_fg
        base_xp_pts = team_implied_xp * kicker_xp_pct * pts_per_xp
        total = (base_fg_pts + base_xp_pts) * game_script * opponent_rz * venue

    Args:
        kicker_stats_df: Per-kicker per-week stats from compute_kicker_stats().
        team_features_df: Team kicker features from compute_team_kicker_features().
        opp_features_df: Opponent features from compute_opponent_kicker_features().
        schedules_df: Game schedule with spread_line, total_line, home_team,
            away_team, week columns.
        season: Target season.
        week: Target week to project.

    Returns:
        DataFrame with columns: player_id, player_name, team, position,
            projected_fg_makes, projected_xp_makes, projected_points,
            projected_floor, projected_ceiling, season, week, is_bye_week.
    """
    if kicker_stats_df.empty:
        logger.warning("Empty kicker stats; returning empty projections")
        return pd.DataFrame()

    # Use week-1 stats as feature source (same as main projection engine)
    feature_week = week - 1
    if feature_week < 1:
        feature_week = 1

    # Build rolling kicker performance (last 3 weeks before target week)
    kicker_season = kicker_stats_df[kicker_stats_df["season"] == season].copy()
    if kicker_season.empty:
        logger.warning("No kicker stats for season %d", season)
        return pd.DataFrame()

    kicker_season = kicker_season.sort_values(["kicker_player_id", "week"])

    # Compute rolling 3-week averages for each kicker
    rolling_stats = []
    for kid, group in kicker_season.groupby("kicker_player_id"):
        prior = group[group["week"] <= feature_week].tail(3)
        if prior.empty:
            # Use season totals as fallback
            prior = group[group["week"] < week]
        if prior.empty:
            continue

        kicker_name = prior["kicker_player_name"].iloc[-1]
        team = prior["team"].iloc[-1]

        rolling_stats.append(
            {
                "kicker_player_id": kid,
                "kicker_player_name": kicker_name,
                "team": team,
                "avg_fg_att": prior["fg_att"].mean(),
                "avg_fg_made": prior["fg_made"].mean(),
                "avg_fg_pct": prior["fg_pct"].mean(),
                "avg_fg_pct_long": (
                    prior["fg_pct_long"].mean()
                    if "fg_pct_long" in prior.columns
                    else _KICKER_BASELINE["fg_pct_long"]
                ),
                "avg_xp_att": (
                    prior["xp_att"].mean()
                    if "xp_att" in prior.columns
                    else _KICKER_BASELINE["xp_att_per_game"]
                ),
                "avg_xp_made": (
                    prior["xp_made"].mean()
                    if "xp_made" in prior.columns
                    else _KICKER_BASELINE["xp_att_per_game"]
                    * _KICKER_BASELINE["xp_pct"]
                ),
                "avg_xp_pct": (
                    prior["xp_pct"].mean()
                    if "xp_pct" in prior.columns
                    else _KICKER_BASELINE["xp_pct"]
                ),
            }
        )

    if not rolling_stats:
        return pd.DataFrame()

    kicker_df = pd.DataFrame(rolling_stats)

    # Get schedule info for the target week
    week_schedule = pd.DataFrame()
    if not schedules_df.empty and "week" in schedules_df.columns:
        week_schedule = schedules_df[schedules_df["week"] == week]

    # Build team -> opponent and spread mappings
    team_opponent: Dict[str, str] = {}
    team_spread: Dict[str, float] = {}
    team_home: Dict[str, str] = {}  # team -> home_team of the game
    team_wind: Dict[str, Optional[float]] = {}
    team_roof: Dict[str, Optional[str]] = {}

    if not week_schedule.empty:
        for _, game in week_schedule.iterrows():
            home = game.get("home_team", "")
            away = game.get("away_team", "")
            spread = game.get("spread_line", 0.0)
            wind_val = game.get("wind", None)
            roof_val = game.get("roof", None)

            if pd.notna(home) and pd.notna(away):
                team_opponent[home] = away
                team_opponent[away] = home
                # spread_line is from home perspective; negative = home favored
                team_spread[home] = float(spread) if pd.notna(spread) else 0.0
                team_spread[away] = -float(spread) if pd.notna(spread) else 0.0
                team_home[home] = home
                team_home[away] = home
                team_wind[home] = float(wind_val) if pd.notna(wind_val) else None
                team_wind[away] = float(wind_val) if pd.notna(wind_val) else None
                team_roof[home] = str(roof_val) if pd.notna(roof_val) else None
                team_roof[away] = str(roof_val) if pd.notna(roof_val) else None

    # Merge team features
    if not team_features_df.empty:
        tf = team_features_df[
            (team_features_df["season"] == season) & (team_features_df["week"] == week)
        ]
        if tf.empty:
            # Try feature_week
            tf = team_features_df[
                (team_features_df["season"] == season)
                & (team_features_df["week"] == feature_week)
            ]
        if not tf.empty:
            kicker_df = kicker_df.merge(
                tf[
                    [
                        "team",
                        "red_zone_stall_rate",
                        "fg_attempts_per_game",
                        "fg_range_drives",
                    ]
                ],
                on="team",
                how="left",
            )

    # Merge opponent features
    if not opp_features_df.empty:
        kicker_df["opponent"] = kicker_df["team"].map(team_opponent)
        of = opp_features_df[
            (opp_features_df["season"] == season) & (opp_features_df["week"] == week)
        ]
        if of.empty:
            of = opp_features_df[
                (opp_features_df["season"] == season)
                & (opp_features_df["week"] == feature_week)
            ]
        if not of.empty:
            kicker_df = kicker_df.merge(
                of[
                    [
                        "defense_team",
                        "opp_rz_td_rate_allowed",
                        "opp_fg_range_drives_allowed",
                    ]
                ],
                left_on="opponent",
                right_on="defense_team",
                how="left",
            )
            kicker_df.drop(columns=["defense_team"], errors="ignore", inplace=True)

    # --- Compute projections ---
    projections = []

    for _, row in kicker_df.iterrows():
        team = row["team"]

        # Base FG projection
        fg_att = row.get("fg_attempts_per_game", row["avg_fg_att"])
        if pd.isna(fg_att) or fg_att == 0:
            fg_att = row["avg_fg_att"]
        if pd.isna(fg_att):
            fg_att = _KICKER_BASELINE["fg_att_per_game"]

        fg_pct = row["avg_fg_pct"]
        if pd.isna(fg_pct) or fg_pct == 0:
            fg_pct = _KICKER_BASELINE["fg_pct"]

        fg_pct_long = row.get("avg_fg_pct_long", _KICKER_BASELINE["fg_pct_long"])
        if pd.isna(fg_pct_long):
            fg_pct_long = _KICKER_BASELINE["fg_pct_long"]

        # Approximate: ~25% of FG attempts are 50+ based on league data
        fg_makes_short_med = fg_att * 0.75 * fg_pct
        fg_makes_long = fg_att * 0.25 * fg_pct_long
        total_fg_makes = fg_makes_short_med + fg_makes_long

        fg_points = (
            fg_makes_short_med * KICKER_SCORING["fg_made"]
            + fg_makes_long * KICKER_SCORING["fg_made_50plus"]
        )

        # Base XP projection
        xp_att = row.get("avg_xp_att", _KICKER_BASELINE["xp_att_per_game"])
        if pd.isna(xp_att):
            xp_att = _KICKER_BASELINE["xp_att_per_game"]
        xp_pct = row.get("avg_xp_pct", _KICKER_BASELINE["xp_pct"])
        if pd.isna(xp_pct):
            xp_pct = _KICKER_BASELINE["xp_pct"]
        xp_makes = xp_att * xp_pct
        xp_points = xp_makes * KICKER_SCORING["xp_made"]

        # Miss penalty
        fg_misses = fg_att - total_fg_makes
        xp_misses = xp_att - xp_makes
        miss_penalty = (
            fg_misses * KICKER_SCORING["fg_missed"]
            + xp_misses * KICKER_SCORING["xp_missed"]
        )

        base_points = fg_points + xp_points + miss_penalty

        # --- Apply multipliers ---
        spread = team_spread.get(team, 0.0)
        game_script = _game_script_multiplier(spread)

        opp_rz_rate = row.get("opp_rz_td_rate_allowed", 0.55)
        if pd.isna(opp_rz_rate):
            opp_rz_rate = 0.55
        opp_mult = _opponent_rz_multiplier(opp_rz_rate)

        home = team_home.get(team, team)
        wind = team_wind.get(team, None)
        roof = team_roof.get(team, None)
        venue_mult = _venue_weather_multiplier(home, wind=wind, roof=roof)

        total_points = base_points * game_script * opp_mult * venue_mult
        total_points = max(0.0, total_points)

        projections.append(
            {
                "player_id": row["kicker_player_id"],
                "player_name": row["kicker_player_name"],
                "team": team,
                "recent_team": team,
                "position": "K",
                "projected_fg_makes": round(total_fg_makes * game_script * opp_mult, 2),
                "projected_xp_makes": round(xp_makes, 2),
                "projected_points": round(total_points, 2),
                "projected_floor": round(total_points * (1.0 - _KICKER_VARIANCE), 2),
                "projected_ceiling": round(total_points * (1.0 + _KICKER_VARIANCE), 2),
                "season": season,
                "week": week,
                "is_bye_week": False,
                "game_script_mult": round(game_script, 4),
                "opp_rz_mult": round(opp_mult, 4),
                "venue_mult": round(venue_mult, 4),
            }
        )

    if not projections:
        return pd.DataFrame()

    result = pd.DataFrame(projections)

    # --- Bye week zeroing ---
    if not week_schedule.empty:
        active_teams = set()
        if "home_team" in week_schedule.columns:
            active_teams |= set(week_schedule["home_team"].dropna())
        if "away_team" in week_schedule.columns:
            active_teams |= set(week_schedule["away_team"].dropna())

        if active_teams:
            bye_mask = ~result["team"].isin(active_teams)
            if bye_mask.any():
                result.loc[bye_mask, "projected_fg_makes"] = 0.0
                result.loc[bye_mask, "projected_xp_makes"] = 0.0
                result.loc[bye_mask, "projected_points"] = 0.0
                result.loc[bye_mask, "projected_floor"] = 0.0
                result.loc[bye_mask, "projected_ceiling"] = 0.0
                result.loc[bye_mask, "is_bye_week"] = True

    # Rank
    result["position_rank"] = (
        result["projected_points"].rank(ascending=False, method="first").astype(int)
    )

    result = result.sort_values("projected_points", ascending=False).reset_index(
        drop=True
    )

    logger.info(
        "Generated kicker projections: %d kickers for season %d week %d",
        len(result),
        season,
        week,
    )
    return result
