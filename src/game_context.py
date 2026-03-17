"""
Game Context Module -- Schedule-derived features for prediction models.

Extracts weather, rest/travel, and coaching features from schedules Bronze data.
Unpivots home/away game rows into per-team per-week rows.
All output joinable on [team, season, week].
"""

import logging
from datetime import datetime
from math import radians, sin, cos, sqrt, atan2
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
import pytz

from src.config import STADIUM_COORDINATES, STADIUM_ID_COORDS

logger = logging.getLogger(__name__)


def _haversine_miles(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Compute great-circle distance in miles between two lat/lon points.

    Args:
        lat1: Latitude of point 1 in degrees.
        lon1: Longitude of point 1 in degrees.
        lat2: Latitude of point 2 in degrees.
        lon2: Longitude of point 2 in degrees.

    Returns:
        Distance in miles.
    """
    R = 3958.8  # Earth radius in miles
    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1
    a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


def _timezone_diff_hours(tz_name1: str, tz_name2: str, game_date: str) -> float:
    """Compute absolute timezone difference in hours on a specific date.

    Uses pytz for DST-aware offset computation. Returns 0.0 if either
    timezone name is missing or invalid.

    Args:
        tz_name1: IANA timezone name (e.g. 'America/New_York').
        tz_name2: IANA timezone name (e.g. 'America/Los_Angeles').
        game_date: Date string in 'YYYY-MM-DD' format.

    Returns:
        Absolute timezone difference in hours.
    """
    try:
        if not tz_name1 or not tz_name2:
            return 0.0
        dt = datetime.strptime(str(game_date), "%Y-%m-%d").replace(hour=12)
        tz1 = pytz.timezone(tz_name1)
        tz2 = pytz.timezone(tz_name2)
        offset1 = tz1.localize(dt).utcoffset().total_seconds() / 3600
        offset2 = tz2.localize(dt).utcoffset().total_seconds() / 3600
        return abs(offset1 - offset2)
    except (pytz.exceptions.UnknownTimeZoneError, ValueError, AttributeError):
        return 0.0


def _unpivot_schedules(schedules_df: pd.DataFrame) -> pd.DataFrame:
    """Convert home/away game rows to per-team rows.

    Each game produces two rows: one for home team, one for away team.
    Renames home_coach/away_coach -> head_coach, home_rest/away_rest -> rest_days.
    Adds is_home flag.

    Args:
        schedules_df: Raw schedules DataFrame with home_team, away_team columns.

    Returns:
        DataFrame with one row per team per game, sorted by [team, season, week].
    """
    home = schedules_df.rename(columns={
        "home_team": "team",
        "away_team": "opponent",
        "home_coach": "head_coach",
        "away_coach": "opponent_coach",
        "home_rest": "rest_days",
        "away_rest": "opponent_rest",
    }).assign(is_home=True)

    away = schedules_df.rename(columns={
        "away_team": "team",
        "home_team": "opponent",
        "away_coach": "head_coach",
        "home_coach": "opponent_coach",
        "away_rest": "rest_days",
        "home_rest": "opponent_rest",
    }).assign(is_home=False)

    cols = [
        "game_id", "season", "week", "team", "opponent",
        "head_coach", "opponent_coach", "rest_days", "opponent_rest",
        "is_home", "temp", "wind", "roof", "surface",
        "stadium_id", "stadium", "game_type", "gameday", "location",
    ]

    # Only select columns that exist in both frames
    available_cols = [c for c in cols if c in home.columns and c in away.columns]

    result = pd.concat([home[available_cols], away[available_cols]], ignore_index=True)
    return result.sort_values(["team", "season", "week"]).reset_index(drop=True)


def compute_weather_features(unpivoted_df: pd.DataFrame) -> pd.DataFrame:
    """Derive weather flags from raw temp/wind/roof/surface.

    Args:
        unpivoted_df: Per-team unpivoted schedules DataFrame.

    Returns:
        DataFrame with columns: team, season, week, is_dome, temperature,
        wind_speed, is_high_wind, is_cold, surface.
    """
    df = unpivoted_df[["team", "season", "week"]].copy()

    # Dome detection
    df["is_dome"] = unpivoted_df["roof"].isin(["dome", "closed"])

    # Temperature and wind with dome overrides
    df["temperature"] = unpivoted_df["temp"].copy().values
    df["wind_speed"] = unpivoted_df["wind"].copy().values
    df.loc[df["is_dome"], "temperature"] = 72.0
    df.loc[df["is_dome"], "wind_speed"] = 0.0

    # Derived flags (NaN -> False via fillna)
    df["is_high_wind"] = (df["wind_speed"] > 15).fillna(False).astype(bool)
    df["is_cold"] = (df["temperature"] <= 32).fillna(False).astype(bool)

    # Surface pass-through
    df["surface"] = unpivoted_df["surface"].values

    return df


def compute_rest_features(unpivoted_df: pd.DataFrame) -> pd.DataFrame:
    """Compute rest-related features from unpivoted schedules.

    Args:
        unpivoted_df: Per-team unpivoted schedules DataFrame.

    Returns:
        DataFrame with columns: team, season, week, rest_days, opponent_rest,
        is_short_rest, is_post_bye, rest_advantage.
    """
    df = unpivoted_df[["team", "season", "week"]].copy()

    df["rest_days"] = unpivoted_df["rest_days"].clip(upper=14)
    df["opponent_rest"] = unpivoted_df["opponent_rest"].clip(upper=14)

    df["is_short_rest"] = df["rest_days"] <= 6
    df["is_post_bye"] = df["rest_days"] >= 13
    df["rest_advantage"] = df["rest_days"] - df["opponent_rest"]

    return df


def compute_travel_features(unpivoted_df: pd.DataFrame) -> pd.DataFrame:
    """Compute travel distance and timezone differential for each team-game.

    Uses STADIUM_COORDINATES for team home locations and STADIUM_ID_COORDS
    for game venue locations. Home games (non-neutral) get 0 travel miles.

    Args:
        unpivoted_df: Per-team unpivoted schedules DataFrame.

    Returns:
        DataFrame with columns: team, season, week, travel_miles, tz_diff.
    """
    df = unpivoted_df[["team", "season", "week"]].copy()

    travel_miles = []
    tz_diffs = []

    for _, row in unpivoted_df.iterrows():
        team = row["team"]
        stadium_id = row.get("stadium_id", None)
        is_home = row.get("is_home", False)
        location = row.get("location", "Home")
        gameday = row.get("gameday", None)

        # Look up team home coordinates
        team_home = STADIUM_COORDINATES.get(team)
        if team_home is None:
            logger.warning("No home coordinates for team %s", team)
            travel_miles.append(np.nan)
            tz_diffs.append(0.0)
            continue

        team_lat, team_lon, team_tz = team_home[0], team_home[1], team_home[2]

        # Home game at own stadium (not neutral site) = 0 miles
        if is_home and location != "Neutral":
            travel_miles.append(0.0)
            tz_diffs.append(0.0)
            continue

        # Look up venue coordinates from stadium_id
        venue = STADIUM_ID_COORDS.get(stadium_id) if stadium_id else None
        if venue is None:
            if stadium_id:
                logger.warning("No coordinates for stadium_id %s", stadium_id)
            travel_miles.append(np.nan)
            tz_diffs.append(0.0)
            continue

        venue_lat, venue_lon, venue_tz = venue

        miles = _haversine_miles(team_lat, team_lon, venue_lat, venue_lon)
        travel_miles.append(round(miles, 1))

        tz_diff = _timezone_diff_hours(team_tz, venue_tz, gameday) if gameday else 0.0
        tz_diffs.append(tz_diff)

    df["travel_miles"] = travel_miles
    df["tz_diff"] = tz_diffs

    return df


def compute_coaching_features(
    unpivoted_df: pd.DataFrame,
    prior_season_coaches: Optional[Dict[str, str]] = None,
) -> pd.DataFrame:
    """Compute coaching change detection and tenure tracking.

    Detects off-season changes (vs prior season's final coach) and mid-season
    changes (week-over-week coach changes). Tracks consecutive coaching tenure.

    Args:
        unpivoted_df: Per-team unpivoted schedules DataFrame.
        prior_season_coaches: Optional dict of {team: coach_name} from prior
            season's final week. If None (first season), all coaching_change=False.

    Returns:
        DataFrame with columns: team, season, week, head_coach, coaching_change,
        coaching_tenure.
    """
    df = unpivoted_df[["team", "season", "week", "head_coach"]].copy()
    df = df.sort_values(["team", "season", "week"]).reset_index(drop=True)

    coaching_change = []
    coaching_tenure = []

    for team in df["team"].unique():
        team_mask = df["team"] == team
        team_rows = df[team_mask].copy()

        prev_coach = prior_season_coaches.get(team) if prior_season_coaches else None
        change_active = False
        tenure = 0

        for _, row in team_rows.iterrows():
            current_coach = row["head_coach"]

            if prev_coach is None:
                # First season of data -- no prior reference
                change_active = False
                tenure = tenure + 1 if tenure > 0 else 1
            elif current_coach != prev_coach:
                # Coach changed (off-season or mid-season)
                change_active = True
                tenure = 1
            else:
                # Same coach continues
                tenure += 1

            coaching_change.append(change_active)
            coaching_tenure.append(tenure)
            prev_coach = current_coach

    df["coaching_change"] = coaching_change
    df["coaching_tenure"] = coaching_tenure

    return df


def compute_game_context(
    schedules_df: pd.DataFrame,
    prior_season_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """Compute all game context features from schedules data.

    Orchestrates unpivoting and all feature computations, merging results
    on [team, season, week].

    Args:
        schedules_df: Raw schedules DataFrame for a single season.
        prior_season_df: Optional schedules for the prior season, used to
            extract prior_season_coaches for coaching change detection.

    Returns:
        Combined DataFrame with weather, rest, travel, and coaching features
        joinable on [team, season, week].
    """
    unpivoted = _unpivot_schedules(schedules_df)

    # Extract prior season coaches if prior data provided
    prior_season_coaches = None
    if prior_season_df is not None and len(prior_season_df) > 0:
        prior_unpivoted = _unpivot_schedules(prior_season_df)
        # Get coach from last week for each team
        last_week = (
            prior_unpivoted.sort_values("week")
            .groupby("team")
            .last()
            .reset_index()
        )
        prior_season_coaches = dict(
            zip(last_week["team"], last_week["head_coach"])
        )

    weather = compute_weather_features(unpivoted)
    rest = compute_rest_features(unpivoted)
    travel = compute_travel_features(unpivoted)
    coaching = compute_coaching_features(unpivoted, prior_season_coaches)

    # Start with base columns from unpivoted
    result = unpivoted[["team", "season", "week", "game_id", "is_home", "game_type"]].copy()

    # Merge each feature set on [team, season, week]
    for features_df in [weather, rest, travel, coaching]:
        # Drop duplicate key columns before merge to avoid suffixes
        merge_cols = [c for c in features_df.columns if c not in ["team", "season", "week"]]
        result = result.merge(
            features_df[["team", "season", "week"] + merge_cols],
            on=["team", "season", "week"],
            how="left",
        )

    return result
