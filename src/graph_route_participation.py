"""Route-participation features from PBP participation data (plan 2.2).

Routes-run data is paid (PFF/FTN), but a route-participation proxy is free:
the share of team dropbacks a player was on the field for, computed from
``data/bronze/pbp_participation`` (``offense_players`` per play) joined to
PBP ``qb_dropback`` flags. This is the standard "route rate" workhorse that
consensus projections lean on — usage/role changes show up in route
participation a week before they show up in points.

Leakage discipline:
    - ``route_rate`` (and the underlying counts) describe the week being
      played — they are stored for Silver but are NOT model features
      (registered in player_feature_engineering._SAME_WEEK_RAW_STATS).
    - Model features are the lagged variants computed here with shift(1):
      ``route_rate_trail4`` (trailing 4-game mean) and
      ``route_rate_delta_trail2`` (week-over-week change, both weeks lagged).

Exports:
    compute_route_participation: per player-week route rate + lagged form.
    ROUTE_PARTICIPATION_FEATURES: lagged model-feature column names.
"""

import logging
from typing import List

import pandas as pd

logger = logging.getLogger(__name__)

# Lagged model features produced by this module (raw route_rate is excluded
# from model features as a same-week stat).
ROUTE_PARTICIPATION_FEATURES: List[str] = [
    "route_rate_trail4",
    "route_rate_delta_trail2",
]

_TRAIL_WINDOW = 4
_MIN_GAMES = 2


def compute_route_participation(
    pbp_df: pd.DataFrame,
    participation_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per player-week route participation and lagged form features.

    For each (player, team, season, week): the fraction of the team's QB
    dropbacks where the player appears in ``offense_players``. All offensive
    players (including OL/QB at ~1.0) are emitted — position filtering
    happens at consumption time via the player-frame join.

    Args:
        pbp_df: Play-by-play DataFrame with game_id, play_id, season, week,
            posteam, qb_dropback columns.
        participation_df: Participation DataFrame with game_id, play_id,
            offense_players (semicolon-separated gsis ids).

    Returns:
        DataFrame with columns: player_id, season, week, recent_team,
        route_rate, dropbacks_on_field, team_dropbacks, route_rate_trail4,
        route_rate_delta_trail2. Empty DataFrame when inputs are unusable.
    """
    required_pbp = {"game_id", "play_id", "season", "week", "posteam", "qb_dropback"}
    required_part = {"game_id", "play_id", "offense_players"}
    if (
        pbp_df.empty
        or participation_df.empty
        or not required_pbp.issubset(pbp_df.columns)
        or not required_part.issubset(participation_df.columns)
    ):
        logger.warning("Route participation: missing inputs/columns — skipping")
        return pd.DataFrame()

    plays = participation_df[list(required_part)].merge(
        pbp_df[list(required_pbp)], on=["game_id", "play_id"], how="inner"
    )
    dropbacks = plays[
        (plays["qb_dropback"] == 1) & plays["offense_players"].notna()
    ].copy()
    if dropbacks.empty:
        logger.warning("Route participation: no dropbacks with participation")
        return pd.DataFrame()

    team_db = (
        dropbacks.groupby(["posteam", "season", "week"])["play_id"]
        .count()
        .rename("team_dropbacks")
        .reset_index()
    )

    exploded = dropbacks.assign(
        player_id=dropbacks["offense_players"].str.split(";")
    ).explode("player_id")
    exploded["player_id"] = exploded["player_id"].str.strip()
    exploded = exploded[exploded["player_id"] != ""]

    on_field = (
        exploded.groupby(["player_id", "posteam", "season", "week"])["play_id"]
        .count()
        .rename("dropbacks_on_field")
        .reset_index()
    )

    rr = on_field.merge(team_db, on=["posteam", "season", "week"], how="left")
    rr["route_rate"] = rr["dropbacks_on_field"] / rr["team_dropbacks"]
    rr = rr.rename(columns={"posteam": "recent_team"})

    # Lagged form features (strict shift(1); within season).
    rr = rr.sort_values(["player_id", "season", "week"])
    grouped = rr.groupby(["player_id", "season"])["route_rate"]
    rr["route_rate_trail4"] = grouped.transform(
        lambda s: s.shift(1).rolling(_TRAIL_WINDOW, min_periods=_MIN_GAMES).mean()
    )
    # Week-over-week momentum using only past weeks: rate(W-1) - rate(W-2).
    rr["route_rate_delta_trail2"] = grouped.transform(lambda s: s.shift(1) - s.shift(2))

    logger.info(
        "Route participation: %d player-weeks (%d with trail features)",
        len(rr),
        int(rr["route_rate_trail4"].notna().sum()),
    )
    return rr[
        [
            "player_id",
            "season",
            "week",
            "recent_team",
            "route_rate",
            "dropbacks_on_field",
            "team_dropbacks",
            "route_rate_trail4",
            "route_rate_delta_trail2",
        ]
    ]
