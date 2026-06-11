"""Route-participation features from PBP participation data (plan 2.2).

Routes-run data is paid (PFF/FTN), but a route-participation proxy is free:
the share of team dropbacks a player was on the field for, computed from
``data/bronze/pbp_participation`` (``offense_players`` per play) joined to
PBP ``qb_dropback`` flags. This is the standard "route rate" workhorse that
consensus projections lean on — usage/role changes show up in route
participation a week before they show up in points.

Leakage discipline:
    - ``route_rate``, ``dropbacks_on_field``, and ``team_dropbacks`` describe
      the week being played — they are stored for Silver completeness but are
      NOT model features (registered in
      player_feature_engineering._SAME_WEEK_RAW_STATS).
    - Model features are the strictly lagged variants (shift-1 applied before
      rolling/slope):

      ``route_rate_trail4``
          Trailing 4-week mean of route_rate; reflects stable role.
          NaN for the first 2 games in a season (min_periods=2).

      ``route_rate_delta``
          Week-over-week change of the trailing mean:
          trail4[week-1] − trail4[week-2].  Both inputs are already lagged, so
          this is safe.  Requires at least 3 games in the window.

      ``route_rate_slope``
          Linear trend (slope coefficient from OLS) of the trailing 4 raw
          route-rate values (all shifted by 1).  Positive = role growing;
          negative = role shrinking.  NaN when fewer than 3 prior weeks of
          data are available.

Exports:
    compute_route_participation: per player-week route rate + lagged features.
    ROUTE_PARTICIPATION_FEATURES: lagged model-feature column names.
"""

import logging
from typing import List

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Lagged model features produced by this module (raw route_rate is excluded
# from model features as a same-week stat; its counts are also excluded).
ROUTE_PARTICIPATION_FEATURES: List[str] = [
    "route_rate_trail4",
    "route_rate_delta",
    "route_rate_slope",
]

_TRAIL_WINDOW = 4
_MIN_GAMES = 2  # Minimum observations for the rolling mean
_SLOPE_MIN_GAMES = 3  # Minimum observations to fit a slope


def _ols_slope(series: "pd.Series") -> float:
    """Compute OLS slope for a numeric series.

    Uses indices 0..n-1 as the x-axis so the slope is
    (change per additional game).  Returns NaN when fewer than
    ``_SLOPE_MIN_GAMES`` non-null values are present.

    Args:
        series: Numeric Series of route-rate values.

    Returns:
        Slope coefficient or NaN if insufficient data.
    """
    values = series.dropna().values
    n = len(values)
    if n < _SLOPE_MIN_GAMES:
        return float("nan")
    x = np.arange(n, dtype=float)
    x_mean = x.mean()
    y_mean = values.mean()
    num = ((x - x_mean) * (values - y_mean)).sum()
    den = ((x - x_mean) ** 2).sum()
    if den == 0:
        return float("nan")
    return float(num / den)


def _compute_slope_vectorized(
    group: "pd.Series",
    window: int,
    min_obs: int,
) -> "pd.Series":
    """Compute trailing OLS slope for a player-season group.

    Applied after shift(1) so every window contains only past data.

    Args:
        group: Series of already-shifted route_rate values.
        window: Number of trailing weeks for the slope.
        min_obs: Minimum non-null observations required.

    Returns:
        Series of slope values aligned to the original index.
    """

    def _slope_for_window(sub: "pd.Series") -> float:
        valid = sub.dropna()
        if len(valid) < min_obs:
            return float("nan")
        x = np.arange(len(valid), dtype=float)
        x_m = x.mean()
        y_m = valid.values.mean()
        num = ((x - x_m) * (valid.values - y_m)).sum()
        den = ((x - x_m) ** 2).sum()
        return float("nan") if den == 0 else float(num / den)

    return group.rolling(window, min_periods=min_obs).apply(
        _slope_for_window, raw=False
    )


def compute_route_participation(
    pbp_df: pd.DataFrame,
    participation_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute per player-week route participation and lagged feature set.

    For each (player, team, season, week): the fraction of the team's QB
    dropbacks where the player appears in ``offense_players``. All offensive
    players (including OL/QB, who participate at ~1.0) are emitted — position
    filtering happens at consumption time via the player-frame join.

    Lagged model features (strict shift-1 within season before rolling):

    - ``route_rate_trail4``: trailing 4-week mean.
    - ``route_rate_delta``: week-over-week change of the trailing mean.
    - ``route_rate_slope``: OLS slope over the trailing 4 shifted values.

    Args:
        pbp_df: Play-by-play DataFrame with columns game_id, play_id, season,
            week, posteam, qb_dropback.
        participation_df: Participation DataFrame with columns game_id, play_id,
            offense_players (semicolon-separated gsis player IDs).

    Returns:
        DataFrame with columns: player_id, season, week, recent_team,
        route_rate, dropbacks_on_field, team_dropbacks, route_rate_trail4,
        route_rate_delta, route_rate_slope.
        Empty DataFrame when inputs are unusable.
    """
    required_pbp = {"game_id", "play_id", "season", "week", "posteam", "qb_dropback"}
    required_part = {"game_id", "play_id", "offense_players"}

    if pbp_df.empty or participation_df.empty:
        logger.warning("Route participation: empty input DataFrames — skipping")
        return pd.DataFrame()

    missing_pbp = required_pbp - set(pbp_df.columns)
    missing_part = required_part - set(participation_df.columns)
    if missing_pbp or missing_part:
        logger.warning(
            "Route participation: missing columns — PBP: %s, participation: %s",
            missing_pbp,
            missing_part,
        )
        return pd.DataFrame()

    # --- Join participation to dropback plays ---------------------------------
    plays = participation_df[list(required_part)].merge(
        pbp_df[list(required_pbp)], on=["game_id", "play_id"], how="inner"
    )
    dropbacks = plays[
        (plays["qb_dropback"] == 1) & plays["offense_players"].notna()
    ].copy()

    if dropbacks.empty:
        logger.warning("Route participation: no dropbacks with participation data")
        return pd.DataFrame()

    # --- Team dropbacks per week ----------------------------------------------
    team_db = (
        dropbacks.groupby(["posteam", "season", "week"])["play_id"]
        .count()
        .rename("team_dropbacks")
        .reset_index()
    )

    # --- Explode player IDs ---------------------------------------------------
    # offense_players is a semicolon-separated string of gsis IDs
    exploded = dropbacks.assign(
        player_id=dropbacks["offense_players"].str.split(";")
    ).explode("player_id")
    exploded["player_id"] = exploded["player_id"].str.strip()
    exploded = exploded[exploded["player_id"].notna() & (exploded["player_id"] != "")]

    # --- Player dropbacks per week -------------------------------------------
    on_field = (
        exploded.groupby(["player_id", "posteam", "season", "week"])["play_id"]
        .count()
        .rename("dropbacks_on_field")
        .reset_index()
    )

    # --- Merge and compute raw rate ------------------------------------------
    rr = on_field.merge(team_db, on=["posteam", "season", "week"], how="left")
    rr["route_rate"] = rr["dropbacks_on_field"] / rr["team_dropbacks"].clip(lower=1)
    rr = rr.rename(columns={"posteam": "recent_team"})

    # --- Lagged trailing features (all within-season, shift(1) applied) ------
    rr = rr.sort_values(["player_id", "season", "week"]).reset_index(drop=True)
    grouped = rr.groupby(["player_id", "season"])["route_rate"]

    # Shift-1 trailing 4-week mean
    rr["route_rate_trail4"] = grouped.transform(
        lambda s: s.shift(1).rolling(_TRAIL_WINDOW, min_periods=_MIN_GAMES).mean()
    )

    # Week-over-week delta of the trailing mean (both sides already lagged)
    rr["route_rate_delta"] = rr.groupby(["player_id", "season"])[
        "route_rate_trail4"
    ].transform(lambda s: s.diff(1))

    # OLS slope over the trailing 4 raw values (shifted within-season first)
    shifted = rr.groupby(["player_id", "season"])["route_rate"].transform(
        lambda s: s.shift(1)
    )
    rr["_route_rate_shifted"] = shifted
    rr["route_rate_slope"] = rr.groupby(["player_id", "season"])[
        "_route_rate_shifted"
    ].transform(lambda s: _compute_slope_vectorized(s, _TRAIL_WINDOW, _SLOPE_MIN_GAMES))
    rr = rr.drop(columns=["_route_rate_shifted"])

    logger.info(
        "Route participation: %d player-weeks | trail4 non-null: %d | "
        "delta non-null: %d | slope non-null: %d",
        len(rr),
        int(rr["route_rate_trail4"].notna().sum()),
        int(rr["route_rate_delta"].notna().sum()),
        int(rr["route_rate_slope"].notna().sum()),
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
            "route_rate_delta",
            "route_rate_slope",
        ]
    ]
