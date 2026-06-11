#!/usr/bin/env python3
"""
Veteran Prior Blending — fixes two systematic early-season failure modes.

**Problem 1 — Established starters buried after 1-2 quiet weeks:**
    WR recency weights use std=1.00 (pure season-to-date).  After two zero-
    or near-zero games, the season-to-date mean is near zero, and there is no
    signal from the prior season.  Players like D.Smith (2022 w3: ours 0.5,
    actual 26.9) collapse in the projection even though consensus rightly
    carries the prior-season expectation.

**Problem 2 — Stars returning from IR/suspension misrouted through rookie fallback:**
    When rolling windows are entirely NaN (player absent for several weeks),
    ``project_position`` treats the player as a rookie and applies a
    conservative positional baseline.  CMC 2024 w11: ours 3.32 with
    ``is_rookie_projection=True``, consensus 19.5, actual 12.6.

**Mechanism — veteran prior blend:**
    1. Compute a per-player *prior*: previous-season per-game half-PPR rate
       (and per-game usage stats: targets/carries/yards).  Computed from
       Bronze player_weekly data via ``build_player_priors``.
    2. Blend:  ``proj = w(n) * rolling + (1 - w(n)) * prior``
       where ``n`` is the number of games the player has actually played
       in the rolling lookback window.  ``w(n)`` reaches ~1.0 by
       ``N_FULL_WEIGHT`` games; mostly prior at n <= 1.
       The blend weight schedule and team-change decay are all sweepable.
    3. Return-from-absence routing: any player with ``is_rookie_projection=True``
       but ≥1 prior NFL season of meaningful play (``games_played >=
       MIN_PRIOR_GAMES``) is rerouted — prior stats fill the NaN rolling
       columns instead of the generic positional baseline.

All parameters are exposed as module-level constants so the lab sweep can
monkey-patch them directly, following the existing pattern in projection_engine.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Sweepable parameters (module-level constants for lab patching)
# ---------------------------------------------------------------------------

# Number of games-played in the lookback at which w(n) saturates at 1.0.
# For WR recency=std, the lookback is the full season to date so this
# represents "enough games to stop leaning on the prior".
N_FULL_WEIGHT: int = 5

# Shape of the weight schedule.  w(n) = 1 - exp(-SCHEDULE_STEEPNESS * n).
# steepness=0.7 → w(1)≈0.50, w(2)≈0.75, w(3)≈0.88, w(5)≈0.97.
# steepness=0.5 → w(1)≈0.39, w(2)≈0.63, w(3)≈0.78, w(5)≈0.92.
SCHEDULE_STEEPNESS: float = 0.7

# Minimum prior-season games for a player to be classified as a "veteran"
# who should never fall through to the generic rookie positional baseline.
# CMC played 16 games in 2023; Hopkins played 16 in 2021.  We set this
# conservatively at 4 games (e.g. partial seasons still count as veteran).
MIN_PRIOR_GAMES: int = 4

# Decay factor applied to the prior per-game rate when the player has
# changed teams since the prior season.  1.0 = no decay (full prior),
# 0.0 = decay entirely to positional baseline.
TEAM_CHANGE_DECAY: float = 0.7

# Positional baseline per-game stats used as the "floor prior" for team-
# changers and players with low prior game counts.  Matches the starter
# tier from projection_engine._STARTER_BASELINES but expressed as per-game
# half-PPR rates and the component stats projected in POSITION_STAT_PROFILE.
_POSITIONAL_PRIOR_BASELINES: Dict[str, Dict[str, float]] = {
    "QB": {
        "passing_yards": 230.0,
        "passing_tds": 1.4,
        "interceptions": 0.8,
        "rushing_yards": 15.0,
        "rushing_tds": 0.1,
        "half_ppr": 16.5,
    },
    "RB": {
        "rushing_yards": 55.0,
        "rushing_tds": 0.4,
        "carries": 12.0,
        "receptions": 3.0,
        "receiving_yards": 22.0,
        "receiving_tds": 0.1,
        "half_ppr": 10.5,
    },
    "WR": {
        "receiving_yards": 60.0,
        "receiving_tds": 0.4,
        "receptions": 4.5,
        "targets": 6.5,
        "half_ppr": 9.8,
    },
    "TE": {
        "receiving_yards": 40.0,
        "receiving_tds": 0.3,
        "receptions": 3.0,
        "targets": 4.5,
        "half_ppr": 7.2,
    },
}

# First-week-back discount: multiplier applied to the prior for players
# whose rolling window is entirely NaN (return-from-absence, n=0).
# 1.0 = no discount; 0.85 = mild downgrade for first-game-back uncertainty.
FIRST_WEEK_BACK_DISCOUNT: float = 0.85

# Stats used for per-game prior computation per position.
# Subset of POSITION_STAT_PROFILE from projection_engine.
_PRIOR_STAT_COLS: Dict[str, List[str]] = {
    "QB": [
        "passing_yards",
        "passing_tds",
        "interceptions",
        "rushing_yards",
        "rushing_tds",
    ],
    "RB": [
        "rushing_yards",
        "rushing_tds",
        "carries",
        "receptions",
        "receiving_yards",
        "receiving_tds",
    ],
    "WR": ["targets", "receptions", "receiving_yards", "receiving_tds"],
    "TE": ["targets", "receptions", "receiving_yards", "receiving_tds"],
}

# Regular-season week boundary (used to filter out playoff rows when computing priors)
MAX_REGULAR_WEEK: int = 18


# ---------------------------------------------------------------------------
# Prior computation
# ---------------------------------------------------------------------------


def build_player_priors(
    weekly_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
    min_games: int = MIN_PRIOR_GAMES,
) -> pd.DataFrame:
    """Compute per-player, per-season prior from Bronze weekly data.

    For each player-season pair, aggregates per-game averages of all
    ``_PRIOR_STAT_COLS`` plus the actual fantasy points (``half_ppr`` column
    or computed on-the-fly).  The result is indexed by ``(player_id, season)``
    and represents the *prior season's* per-game expectation.

    Callers project for season S should pass ``weekly_df`` that covers at
    least season ``S-1`` so that ``get_player_prior`` can find the prior.

    Args:
        weekly_df: Bronze player_weekly DataFrame with at least
            ``player_id``, ``season``, ``week``, ``position``,
            ``recent_team``, and the per-game stat columns.
        scoring_format: Fantasy scoring format for actual-FP computation.
            Only ``'half_ppr'`` is used internally (the prior is always
            stored in half-PPR and rescaled at query time if needed, but
            for now the lab sweeps only run half_ppr).
        min_games: Minimum games played in the season for the prior to be
            considered *meaningful* (players with fewer games get the
            positional baseline as their prior).

    Returns:
        DataFrame with columns:
            player_id, season, position, recent_team,
            games_played, half_ppr_per_game,
            {stat}_per_game for each stat in _PRIOR_STAT_COLS,
        indexed by ``['player_id', 'season']``.
    """
    if weekly_df.empty:
        logger.warning("build_player_priors: empty weekly_df")
        return pd.DataFrame()

    # Compute actual fantasy points if not already present
    fp_col = "actual_fp_vpblend"
    work = weekly_df.copy()

    try:
        from scoring_calculator import calculate_fantasy_points_df

        work = calculate_fantasy_points_df(
            work, scoring_format=scoring_format, output_col=fp_col
        )
    except Exception as exc:
        logger.warning("Could not compute fantasy points for priors: %s", exc)
        fp_col = None

    # Restrict to regular season weeks only
    work = work[work["week"] <= MAX_REGULAR_WEEK].copy()

    if "position" not in work.columns:
        logger.warning("build_player_priors: 'position' column missing")
        return pd.DataFrame()

    skill_positions = {"QB", "RB", "WR", "TE"}
    work = work[work["position"].isin(skill_positions)].copy()

    # Aggregate per (player_id, season)
    agg_cols = ["player_id", "season", "position", "recent_team"]
    missing = [c for c in ["player_id", "season"] if c not in work.columns]
    if missing:
        logger.warning("build_player_priors: missing required columns %s", missing)
        return pd.DataFrame()

    rows = []
    for (player_id, season), grp in work.groupby(["player_id", "season"], sort=False):
        position = grp["position"].iloc[-1]
        recent_team = (
            grp["recent_team"].iloc[-1] if "recent_team" in grp.columns else None
        )
        games = len(grp)

        stat_per_game: Dict[str, float] = {}
        for stat in _PRIOR_STAT_COLS.get(position, []):
            if stat in grp.columns:
                stat_per_game[f"{stat}_per_game"] = float(grp[stat].fillna(0).mean())
            else:
                stat_per_game[f"{stat}_per_game"] = 0.0

        half_ppr_pg = 0.0
        if fp_col and fp_col in grp.columns:
            half_ppr_pg = float(grp[fp_col].fillna(0).mean())

        row = {
            "player_id": player_id,
            "season": season,
            "position": position,
            "recent_team": recent_team,
            "games_played": games,
            "half_ppr_per_game": half_ppr_pg,
        }
        row.update(stat_per_game)
        rows.append(row)

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(rows).set_index(["player_id", "season"])


def get_player_prior(
    player_id: str,
    proj_season: int,
    position: str,
    priors_df: pd.DataFrame,
    current_team: Optional[str] = None,
    min_games: int = MIN_PRIOR_GAMES,
    team_change_decay: float = TEAM_CHANGE_DECAY,
) -> Dict[str, float]:
    """Look up a player's prior for a given projection season.

    Searches for the most recent prior season (``proj_season - 1`` first,
    then ``proj_season - 2``) in ``priors_df``.  Returns per-game stat
    averages.  Decays toward the positional baseline when:
      - The player has changed teams since the prior season.
      - The player played fewer than ``min_games`` in the prior season.

    Args:
        player_id: NFL player identifier.
        proj_season: The season being projected (e.g. 2024).
        position: Player position code ('QB', 'RB', 'WR', 'TE').
        priors_df: Output of ``build_player_priors``.
        current_team: Team abbreviation in the projected season (for team-
            change detection).
        min_games: Minimum games in the prior season to use the raw prior
            without fallback.
        team_change_decay: Blend weight applied when the player changed
            teams; prior stats are lerped toward the positional baseline
            at ``(1 - team_change_decay)``.

    Returns:
        Dict mapping stat name to per-game projected value.  Returns the
        positional baseline when no prior is found.
    """
    baseline = _POSITIONAL_PRIOR_BASELINES.get(position, {})
    stat_names = _PRIOR_STAT_COLS.get(position, [])

    if priors_df.empty:
        return {s: baseline.get(s, 0.0) for s in stat_names}

    prior_row = None
    for look_back in [1, 2]:
        look_season = proj_season - look_back
        key = (player_id, look_season)
        if key in priors_df.index:
            prior_row = priors_df.loc[key]
            break

    if prior_row is None:
        # No prior found → positional baseline
        return {s: baseline.get(s, 0.0) for s in stat_names}

    games_played = int(prior_row.get("games_played", 0))

    if games_played < min_games:
        # Too few games → positional baseline (player was marginal/injured)
        return {s: baseline.get(s, 0.0) for s in stat_names}

    # Build the raw prior per-game stats
    raw: Dict[str, float] = {}
    for stat in stat_names:
        key_col = f"{stat}_per_game"
        raw[stat] = float(prior_row.get(key_col, baseline.get(stat, 0.0)))

    # Team-change decay: lerp raw prior toward positional baseline
    prior_team = prior_row.get("recent_team", None)
    changed_teams = (
        current_team is not None
        and prior_team is not None
        and str(current_team).upper() != str(prior_team).upper()
    )

    if changed_teams and team_change_decay < 1.0:
        blended: Dict[str, float] = {}
        for stat in stat_names:
            blended[stat] = team_change_decay * raw[stat] + (
                1.0 - team_change_decay
            ) * baseline.get(stat, 0.0)
        return blended

    return raw


# ---------------------------------------------------------------------------
# Games-played count helper
# ---------------------------------------------------------------------------


def count_games_in_lookback(
    player_id: str,
    proj_season: int,
    proj_week: int,
    weekly_df: pd.DataFrame,
) -> int:
    """Count games played in the rolling-window lookback for a projected week.

    The projection for week W uses the Silver feature row from week W-1, whose
    rolling averages cover weeks 1 through W-2 (shift-1 transform in
    compute_rolling_averages).  We therefore count *current-season games where
    the player had meaningful stats in weeks 1 through W-2* — i.e.
    ``week < proj_week - 1``.

    A "game played" is a row where at least one of the core offensive stats
    (yards, carries, receptions, targets) is > 0.  Players who appeared on
    the roster but had zero production (bye or DNP rows) are excluded so that
    padded zeros don't inflate the count and cause the blend to prematurely
    weight toward the (empty) rolling average.

    Args:
        player_id: NFL player identifier.
        proj_season: The season being projected.
        proj_week: The week being projected (1-based).
        weekly_df: Bronze player_weekly DataFrame.

    Returns:
        Integer count of productive game-weeks in the rolling lookback.
        Returns 0 when the player has no current-season production before
        the lookback window (return-from-absence case).
    """
    if weekly_df.empty or "player_id" not in weekly_df.columns:
        return 0

    player_rows = weekly_df[weekly_df["player_id"] == player_id]
    if player_rows.empty:
        return 0

    # Rolling averages cover weeks strictly before the feature row (shift-1).
    # Feature row is week W-1; rolling averages cover weeks 1 .. W-2.
    lookback_cutoff = proj_week - 1  # weeks STRICTLY less than this
    window = player_rows[
        (player_rows["season"] == proj_season)
        & (player_rows["week"] < lookback_cutoff)
        & (player_rows["week"] <= MAX_REGULAR_WEEK)
    ]

    if window.empty:
        return 0

    # Count rows with meaningful offensive activity
    activity_cols = [
        c
        for c in [
            "passing_yards",
            "rushing_yards",
            "receiving_yards",
            "carries",
            "receptions",
            "targets",
        ]
        if c in window.columns
    ]
    if not activity_cols:
        return len(window)

    active_mask = (window[activity_cols].fillna(0) > 0).any(axis=1)
    return int(active_mask.sum())


# ---------------------------------------------------------------------------
# Blend weight schedule
# ---------------------------------------------------------------------------


def blend_weight(
    n_games: int, n_full: int = N_FULL_WEIGHT, steepness: float = SCHEDULE_STEEPNESS
) -> float:
    """Return rolling weight w(n) in [0, 1] for n games played.

    Uses a saturating exponential:  w(n) = 1 - exp(-steepness * n).
    At n=0: w=0 (all prior).  At n→∞: w→1 (all rolling).

    Clipped so that w(n_full) is treated as 1.0 (full rolling weight).

    Args:
        n_games: Number of games played in the lookback window.
        n_full: Games at which rolling weight is considered saturated.
        steepness: Controls how quickly weight shifts from prior to rolling.

    Returns:
        Float blend weight in [0.0, 1.0].

    Examples:
        >>> blend_weight(0)   # return-from-absence
        0.0
        >>> blend_weight(5)   # ~saturated
        0.97
    """
    if n_games <= 0:
        return 0.0
    raw = 1.0 - np.exp(-steepness * n_games)
    # Saturate at n_full
    sat = 1.0 - np.exp(-steepness * n_full)
    return float(min(raw / sat, 1.0))


# ---------------------------------------------------------------------------
# Core application function
# ---------------------------------------------------------------------------


def apply_veteran_prior_blend(
    target_df: pd.DataFrame,
    priors_df: pd.DataFrame,
    weekly_df: pd.DataFrame,
    position: str,
    proj_season: int,
    proj_week: int,
    n_full: int = N_FULL_WEIGHT,
    steepness: float = SCHEDULE_STEEPNESS,
    min_prior_games: int = MIN_PRIOR_GAMES,
    team_change_decay: float = TEAM_CHANGE_DECAY,
    first_week_back_discount: float = FIRST_WEEK_BACK_DISCOUNT,
) -> pd.DataFrame:
    """Blend veteran prior stats into rolling-column values before projection.

    For each player row in ``target_df``:
      1. Count games played in the lookback window (``count_games_in_lookback``).
      2. Compute blend weight ``w = blend_weight(n_games)``.
      3. Interpolate each rolling column:
         ``blended_val = w * rolling_val + (1 - w) * prior_val``
      4. For players with all-NaN rolling columns (``is_rookie_projection``
         candidates) **and** a valid veteran prior (≥ min_prior_games), fill
         rolling columns with the prior-based value (with first-week-back
         discount) instead of the generic positional baseline.  This
         ``is_veteran_return`` flag is set to ``True`` on those rows.

    Modifies rolling columns in-place on a copy of ``target_df`` filtered
    to ``position``.  Callers should replace the position slice in their
    full DataFrame with the returned result.

    Args:
        target_df: Silver-layer feature rows (typically week W-1 features
            used to project week W).  Must include ``player_id``,
            ``position``, ``recent_team``, and rolling stat columns.
        priors_df: Output of ``build_player_priors`` covering at least
            season ``proj_season - 1``.
        weekly_df: Full Bronze weekly DataFrame (all seasons in lookback).
        position: Position to process ('QB', 'RB', 'WR', 'TE').
        proj_season: The season being projected.
        proj_week: The week being projected.
        n_full: Passed through to ``blend_weight``.
        steepness: Passed through to ``blend_weight``.
        min_prior_games: Minimum prior-season games to qualify as veteran.
        team_change_decay: Lerp weight toward baseline on team change.
        first_week_back_discount: Multiplier on prior when n_games == 0
            (return-from-absence discount).

    Returns:
        Modified copy of the position-filtered rows with blended rolling
        columns and an added boolean column ``is_veteran_return``.
    """
    pos_df = target_df[target_df["position"] == position].copy()
    if pos_df.empty:
        return pos_df

    stat_cols = _PRIOR_STAT_COLS.get(position, [])
    rolling_suffixes = ["roll3", "roll6", "std"]

    pos_df["is_veteran_return"] = False

    for idx, row in pos_df.iterrows():
        player_id = row.get("player_id")
        if not player_id:
            continue

        current_team = row.get("recent_team", None)

        # Count games in lookback
        n_games = count_games_in_lookback(player_id, proj_season, proj_week, weekly_df)

        # Get veteran prior stats
        prior_stats = get_player_prior(
            player_id=player_id,
            proj_season=proj_season,
            position=position,
            priors_df=priors_df,
            current_team=current_team,
            min_games=min_prior_games,
            team_change_decay=team_change_decay,
        )

        # Determine if this is a return-from-absence row
        # (all rolling columns are NaN — was going to hit rookie fallback)
        all_rolling_cols = [
            f"{stat}_{suf}"
            for stat in stat_cols
            for suf in rolling_suffixes
            if f"{stat}_{suf}" in pos_df.columns
        ]
        is_all_nan = (
            len(all_rolling_cols) > 0 and pos_df.loc[idx, all_rolling_cols].isna().all()
        )

        # Check if this is a genuine veteran (has meaningful prior)
        prior_row = None
        for look_back in [1, 2]:
            look_season = proj_season - look_back
            key = (player_id, look_season)
            if not priors_df.empty and key in priors_df.index:
                prior_row = priors_df.loc[key]
                break

        is_veteran = (
            prior_row is not None
            and int(prior_row.get("games_played", 0)) >= min_prior_games
        )

        if is_all_nan and is_veteran:
            # Return-from-absence veteran: fill rolling cols with prior
            # (with first-week-back discount applied)
            discount = first_week_back_discount if n_games == 0 else 1.0
            for stat in stat_cols:
                prior_val = prior_stats.get(stat, 0.0) * discount
                for suf in rolling_suffixes:
                    col = f"{stat}_{suf}"
                    if col not in pos_df.columns:
                        pos_df[col] = np.nan
                    pos_df.at[idx, col] = prior_val
            pos_df.at[idx, "is_veteran_return"] = True
            logger.debug(
                "Veteran return-from-absence: %s %s %d w%d n_games=%d " "discount=%.2f",
                player_id,
                position,
                proj_season,
                proj_week,
                n_games,
                discount,
            )
            continue  # Skip the blend step — rolling cols now carry the prior

        # Normal blend path: mix rolling values with prior
        # Only blend if the player has a genuine veteran prior; players with
        # no prior history (unknown/new player) must keep NaN rolling columns
        # so the engine routes them through the rookie fallback correctly.
        if not is_veteran:
            continue

        w = blend_weight(n_games, n_full=n_full, steepness=steepness)
        if w >= 1.0:
            continue  # Full rolling weight — no blend needed

        for stat in stat_cols:
            prior_val = prior_stats.get(stat, 0.0)
            for suf in rolling_suffixes:
                col = f"{stat}_{suf}"
                if col not in pos_df.columns:
                    continue
                current_val = pos_df.at[idx, col]
                if pd.isna(current_val):
                    # NaN rolling value for veteran — use prior directly
                    pos_df.at[idx, col] = prior_val
                else:
                    pos_df.at[idx, col] = round(
                        w * current_val + (1.0 - w) * prior_val, 2
                    )

    return pos_df
