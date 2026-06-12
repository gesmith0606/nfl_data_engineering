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

TPRR (Targets Per Route Run) features (Experiment 1, Task #3):
    TPRR = targets / dropbacks_on_field per week. Measures target conversion
    efficiency per route run. YoY r≈0.65 — the stickiest WR role-quality stat.
    All TPRR features are strictly lagged (shift-1 within season):

      ``tprr``
          Raw targets-per-route-run for the week (same-week stat, stored for
          Silver completeness but NOT a model feature).

      ``tprr_trail4``
          Trailing 4-week mean TPRR (strictly lagged).  This is the primary
          TPRR feature — stable role signal that persists across seasons.
          NaN when fewer than 2 lagged games available.

      ``tprr_trail4_slope``
          OLS slope of the trailing 4 lagged TPRR values.  Positive = player
          increasingly targeted per route; the "rising TPRR" breakout pattern.
          NaN when fewer than 3 lagged games available.

      ``tprr_x_route_slope``
          Interaction term: tprr_trail4 * route_rate_slope.  High TPRR + rising
          route rate = classic breakout pattern; low TPRR + falling route rate
          = fade. This cross-signal captures the combined momentum. NaN when
          either component is NaN.

Exports:
    compute_route_participation: per player-week route rate + lagged features.
    compute_tprr_features: TPRR features joined to an existing route-rate frame.
    ROUTE_PARTICIPATION_FEATURES: lagged model-feature column names.
    TPRR_FEATURES: TPRR model-feature column names.
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

# TPRR model features (all strictly lagged; raw tprr is same-week).
TPRR_FEATURES: List[str] = [
    "tprr_trail4",
    "tprr_trail4_slope",
    "tprr_x_route_slope",
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


def compute_tprr_features(
    route_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
) -> pd.DataFrame:
    """Compute trailing TPRR (targets per route run) features.

    TPRR = targets / dropbacks_on_field per week.  All model features are
    strictly lagged (shift-1 within season) so no week-N target data leaks
    into the projection for week N.

    Handling of missing data:
    - Players without participation data (2019 and earlier, ~7% of 2020,
      ~7% of 2021) get NaN for all TPRR features; the heuristic falls back
      to the target-share baseline for those rows.
    - Zero-dropbacks rows (special teams, inactive) get TPRR = NaN.

    Args:
        route_df: DataFrame from ``compute_route_participation`` (or the
            stored Silver parquet) with columns player_id, season, week,
            dropbacks_on_field.
        weekly_df: Bronze weekly player stats with columns player_id, season,
            week, targets.

    Returns:
        DataFrame with columns: player_id, season, week, tprr,
        tprr_trail4, tprr_trail4_slope, tprr_x_route_slope.
        One row per (player_id, season, week) that appears in route_df.
        Returns empty DataFrame if inputs lack required columns.
    """
    required_route = {"player_id", "season", "week", "dropbacks_on_field"}
    required_weekly = {"player_id", "season", "week", "targets"}
    if route_df.empty or not required_route.issubset(route_df.columns):
        logger.warning("compute_tprr_features: route_df missing required columns")
        return pd.DataFrame()
    if weekly_df.empty or not required_weekly.issubset(weekly_df.columns):
        logger.warning("compute_tprr_features: weekly_df missing required columns")
        return pd.DataFrame()

    # Join targets onto route frame (inner join — only rows with both)
    tprr = route_df[["player_id", "season", "week", "dropbacks_on_field"]].merge(
        weekly_df[["player_id", "season", "week", "targets"]].copy(),
        on=["player_id", "season", "week"],
        how="left",
    )
    tprr["targets"] = tprr["targets"].fillna(0.0)

    # Raw TPRR: targets / routes-run proxy (dropbacks_on_field)
    # Zero dropbacks → NaN (player not on field for passes)
    tprr["tprr"] = np.where(
        tprr["dropbacks_on_field"] > 0,
        tprr["targets"] / tprr["dropbacks_on_field"],
        np.nan,
    )

    # Sort for within-season lagged transforms
    tprr = tprr.sort_values(["player_id", "season", "week"]).reset_index(drop=True)

    # Lagged trailing 4-week mean TPRR (shift-1 within season)
    tprr["tprr_trail4"] = tprr.groupby(["player_id", "season"])["tprr"].transform(
        lambda s: s.shift(1).rolling(_TRAIL_WINDOW, min_periods=_MIN_GAMES).mean()
    )

    # OLS slope of trailing 4 lagged TPRR values
    shifted_tprr = tprr.groupby(["player_id", "season"])["tprr"].transform(
        lambda s: s.shift(1)
    )
    tprr["_tprr_shifted"] = shifted_tprr
    tprr["tprr_trail4_slope"] = tprr.groupby(["player_id", "season"])[
        "_tprr_shifted"
    ].transform(
        lambda s: _compute_slope_vectorized(s, _TRAIL_WINDOW, _SLOPE_MIN_GAMES)
    )
    tprr = tprr.drop(columns=["_tprr_shifted"])

    # Interaction: tprr_trail4 × route_rate_slope (if present in route_df)
    if "route_rate_slope" in route_df.columns:
        tprr = tprr.merge(
            route_df[["player_id", "season", "week", "route_rate_slope"]],
            on=["player_id", "season", "week"],
            how="left",
        )
        tprr["tprr_x_route_slope"] = tprr["tprr_trail4"] * tprr["route_rate_slope"]
        tprr = tprr.drop(columns=["route_rate_slope"])
    else:
        tprr["tprr_x_route_slope"] = np.nan

    logger.info(
        "TPRR features: %d player-weeks | tprr non-null: %d | "
        "trail4 non-null: %d | slope non-null: %d | interaction non-null: %d",
        len(tprr),
        int(tprr["tprr"].notna().sum()),
        int(tprr["tprr_trail4"].notna().sum()),
        int(tprr["tprr_trail4_slope"].notna().sum()),
        int(tprr["tprr_x_route_slope"].notna().sum()),
    )

    return tprr[
        [
            "player_id",
            "season",
            "week",
            "tprr",
            "tprr_trail4",
            "tprr_trail4_slope",
            "tprr_x_route_slope",
        ]
    ]
