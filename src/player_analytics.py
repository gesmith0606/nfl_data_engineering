#!/usr/bin/env python3
"""
Player Analytics Module
Computes usage metrics, opponent defensive rankings, and rolling averages
for the Silver layer of the NFL data pipeline.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Usage Metrics
# ---------------------------------------------------------------------------

def compute_usage_metrics(
    weekly_df: pd.DataFrame,
    snap_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Compute per-player usage metrics from weekly stats and snap counts.

    Adds columns:
        target_share, air_yards_share, carry_share, rz_target_share,
        rz_carry_share, snap_pct (if snap_df provided)

    Args:
        weekly_df: Player weekly stats DataFrame (from nfl.import_weekly_data).
        snap_df:   Snap count DataFrame (from nfl.import_snap_counts), optional.

    Returns:
        DataFrame with usage metric columns appended.
    """
    df = weekly_df.copy()

    # --- Team-level aggregates per game ------------------------------------------------
    team_pass_cols = ['targets', 'air_yards']
    team_rush_cols = ['carries']
    rz_pass_cols = ['target_share']  # we'll use a proxy below

    # Sum per team per week
    team_agg = (
        df.groupby(['season', 'week', 'recent_team'], as_index=False)
        .agg(
            team_targets=('targets', 'sum'),
            team_air_yards=('air_yards', 'sum'),
            team_carries=('carries', 'sum'),
        )
    )
    team_agg.rename(columns={'recent_team': 'team'}, inplace=True)

    # Merge back
    df = df.merge(
        team_agg,
        left_on=['season', 'week', 'recent_team'],
        right_on=['season', 'week', 'team'],
        how='left',
    ).drop(columns=['team'])

    # --- Compute shares ----------------------------------------------------------------
    df['target_share'] = np.where(
        df['team_targets'] > 0,
        df['targets'] / df['team_targets'],
        np.nan,
    )
    df['air_yards_share'] = np.where(
        df['team_air_yards'] > 0,
        df['air_yards'] / df['team_air_yards'],
        np.nan,
    )
    df['carry_share'] = np.where(
        df['team_carries'] > 0,
        df['carries'] / df['team_carries'],
        np.nan,
    )

    # Red-zone shares (use wopr as proxy if available, else estimate from targets)
    if 'wopr' in df.columns:
        df['rz_target_share'] = df['wopr']  # WOPR is a composite air-yards+target metric
    elif 'target_share' in df.columns:
        df['rz_target_share'] = df['target_share']  # fallback

    # --- Merge snap counts -------------------------------------------------------------
    if snap_df is not None:
        snap_subset = snap_df[['player_id', 'season', 'week', 'snap_pct']].copy()
        df = df.merge(snap_subset, on=['player_id', 'season', 'week'], how='left')

    logger.info(f"Usage metrics computed for {len(df)} player-week rows")
    return df


# ---------------------------------------------------------------------------
# Opponent Defensive Rankings
# ---------------------------------------------------------------------------

def compute_opponent_rankings(
    weekly_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
    n_seasons: int = 3,
) -> pd.DataFrame:
    """
    Compute opponent defensive strength by position (points allowed per game).

    For each team+week, calculates how many fantasy points each position group
    scored *against* that defense. Ranks 1 (easiest) to 32 (hardest).

    Args:
        weekly_df:    Player weekly stats with fantasy_points column.
        schedules_df: Game schedule DataFrame (provides home/away team mapping).
        n_seasons:    Number of past seasons to include.

    Returns:
        DataFrame with columns: season, week, team, position,
        avg_pts_allowed, rank (1=easiest matchup).
    """
    df = weekly_df.copy()

    if 'fantasy_points_ppr' not in df.columns and 'fantasy_points' not in df.columns:
        logger.warning("No fantasy_points column found; skipping opponent rankings")
        return pd.DataFrame()

    pts_col = 'fantasy_points_ppr' if 'fantasy_points_ppr' in df.columns else 'fantasy_points'

    # Limit to relevant seasons
    if n_seasons and 'season' in df.columns:
        max_season = df['season'].max()
        df = df[df['season'] >= max_season - n_seasons + 1]

    # Build opponent lookup from schedules
    if schedules_df is not None and len(schedules_df) > 0:
        sched_subset = schedules_df[['season', 'week', 'home_team', 'away_team']].copy()
        # Each player's team faced the *other* team in that game
        home_map = sched_subset.rename(columns={'home_team': 'player_team', 'away_team': 'opponent'})
        away_map = sched_subset.rename(columns={'away_team': 'player_team', 'home_team': 'opponent'})
        opp_map = pd.concat([home_map, away_map], ignore_index=True)

        df = df.merge(
            opp_map,
            left_on=['season', 'week', 'recent_team'],
            right_on=['season', 'week', 'player_team'],
            how='left',
        ).drop(columns=['player_team'])
    else:
        df['opponent'] = np.nan

    if 'position' not in df.columns:
        logger.warning("No position column; cannot compute positional rankings")
        return pd.DataFrame()

    # Filter to fantasy-relevant positions
    df = df[df['position'].isin(['QB', 'RB', 'WR', 'TE'])]

    # Average fantasy points allowed per team per position per week
    opp_pts = (
        df.groupby(['season', 'week', 'opponent', 'position'], as_index=False)
        [pts_col].mean()
        .rename(columns={pts_col: 'avg_pts_allowed', 'opponent': 'team'})
    )

    # Rank within each season-week-position (1 = most pts allowed = easiest)
    opp_pts['rank'] = (
        opp_pts.groupby(['season', 'week', 'position'])[['avg_pts_allowed']]
        .rank(ascending=False)
        .astype(int)
    )

    logger.info(f"Opponent rankings computed: {len(opp_pts)} rows")
    return opp_pts


# ---------------------------------------------------------------------------
# Rolling Averages
# ---------------------------------------------------------------------------

ROLLING_STAT_COLS = [
    'passing_yards', 'passing_tds', 'interceptions',
    'rushing_yards', 'rushing_tds', 'carries',
    'receiving_yards', 'receiving_tds', 'receptions', 'targets',
    'air_yards', 'target_share', 'carry_share', 'snap_pct',
    'fantasy_points_ppr',
]


def compute_rolling_averages(
    df: pd.DataFrame,
    windows: List[int] = [3, 6],
) -> pd.DataFrame:
    """
    Compute rolling averages over the specified windows for key stat columns.

    Adds columns named like ``rushing_yards_roll3``, ``targets_roll6``, etc.

    Args:
        df:      Player weekly stats DataFrame (must include player_id, season, week).
        windows: Rolling window sizes in weeks.

    Returns:
        DataFrame with rolling average columns appended.
    """
    df = df.copy()
    df = df.sort_values(['player_id', 'season', 'week'])

    stat_cols = [c for c in ROLLING_STAT_COLS if c in df.columns]

    for window in windows:
        roll_cols = {}
        for col in stat_cols:
            roll_cols[f"{col}_roll{window}"] = (
                df.groupby(['player_id', 'season'])[col]
                .transform(lambda s: s.shift(1).rolling(window, min_periods=1).mean())
            )
        df = df.assign(**roll_cols)

    # Season-to-date average
    for col in stat_cols:
        df[f"{col}_std"] = (
            df.groupby(['player_id', 'season'])[col]
            .transform(lambda s: s.shift(1).expanding().mean())
        )

    logger.info(f"Rolling averages computed ({windows}) for {len(df)} rows")
    return df


# ---------------------------------------------------------------------------
# Game Script Indicators
# ---------------------------------------------------------------------------

def compute_game_script_indicators(
    weekly_df: pd.DataFrame,
    schedules_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add game script indicators based on final score differentials.

    Columns added:
        team_score, opp_score, score_diff,
        game_script  ('blowout_win', 'comfortable_win', 'close', 'losing', 'blowout_loss')

    Args:
        weekly_df:    Player weekly stats.
        schedules_df: Game schedules with score columns.

    Returns:
        DataFrame with game script columns appended.
    """
    df = weekly_df.copy()

    score_cols = [c for c in ['home_score', 'away_score'] if c in schedules_df.columns]
    if not score_cols:
        logger.warning("No score columns in schedules; skipping game script indicators")
        return df

    sched = schedules_df[['season', 'week', 'home_team', 'away_team', 'home_score', 'away_score']].copy()

    # Build team score lookup
    home_scores = sched.rename(columns={
        'home_team': 'player_team', 'home_score': 'team_score', 'away_score': 'opp_score'
    })[['season', 'week', 'player_team', 'team_score', 'opp_score']]

    away_scores = sched.rename(columns={
        'away_team': 'player_team', 'away_score': 'team_score', 'home_score': 'opp_score'
    })[['season', 'week', 'player_team', 'team_score', 'opp_score']]

    score_map = pd.concat([home_scores, away_scores], ignore_index=True)

    df = df.merge(
        score_map,
        left_on=['season', 'week', 'recent_team'],
        right_on=['season', 'week', 'player_team'],
        how='left',
    ).drop(columns=['player_team'])

    df['score_diff'] = df['team_score'] - df['opp_score']

    bins = [-100, -14, -7, 7, 14, 100]
    labels = ['blowout_loss', 'losing', 'close', 'comfortable_win', 'blowout_win']
    df['game_script'] = pd.cut(df['score_diff'], bins=bins, labels=labels)

    return df


# ---------------------------------------------------------------------------
# Vegas Lines Integration
# ---------------------------------------------------------------------------

def compute_implied_team_totals(schedules_df: pd.DataFrame) -> Dict[str, float]:
    """
    Derive implied team scoring totals from Vegas over/under and spread lines.

    Formulas:
        implied_home = (total_line / 2) - (spread_line / 2)
        implied_away = (total_line / 2) + (spread_line / 2)

    ``spread_line`` is the home-team spread (negative when home is favored).
    Missing ``total_line`` or ``spread_line`` values default to a 23.0
    league-average implied total for each affected team.

    Args:
        schedules_df: Game schedule DataFrame from ``nfl.import_schedules()``.
                      Must contain ``home_team`` and ``away_team`` columns.
                      Should contain ``total_line`` and ``spread_line`` columns.

    Returns:
        Dict mapping team abbreviation to implied scoring total (float).
        If a team appears in multiple games (e.g., post-season re-use of the
        same DataFrame), the last encountered game's value is kept — callers
        should pre-filter to the relevant week before calling this function.

    Example:
        >>> totals = compute_implied_team_totals(schedules_df)
        >>> totals['KC']
        26.5
    """
    LEAGUE_AVG_TOTAL: float = 23.0

    required_team_cols = {'home_team', 'away_team'}
    if not required_team_cols.issubset(schedules_df.columns):
        logger.warning(
            "schedules_df missing home_team/away_team columns; "
            "returning empty implied totals"
        )
        return {}

    df = schedules_df.copy()

    # Fill missing line data with league-average assumptions before arithmetic
    if 'total_line' not in df.columns:
        logger.warning("total_line column not found; defaulting all to %.1f", LEAGUE_AVG_TOTAL)
        df['total_line'] = LEAGUE_AVG_TOTAL * 2  # will halve below
    else:
        # A missing total_line means we default each team in that game to LEAGUE_AVG_TOTAL
        # Set total_line NaN rows to 2 * LEAGUE_AVG_TOTAL so the /2 yields the average
        df['total_line'] = df['total_line'].fillna(LEAGUE_AVG_TOTAL * 2)

    if 'spread_line' not in df.columns:
        logger.warning("spread_line column not found; treating spread as 0 for all games")
        df['spread_line'] = 0.0
    else:
        # Missing spread → treat as pick-em (0), so each team gets total_line / 2
        df['spread_line'] = df['spread_line'].fillna(0.0)

    # Vectorised implied totals
    df['implied_home'] = (df['total_line'] / 2) - (df['spread_line'] / 2)
    df['implied_away'] = (df['total_line'] / 2) + (df['spread_line'] / 2)

    # Clip to a sane range: no team is implied to score < 5 or > 45
    df['implied_home'] = df['implied_home'].clip(5.0, 45.0)
    df['implied_away'] = df['implied_away'].clip(5.0, 45.0)

    implied_totals: Dict[str, float] = {}
    for _, row in df.iterrows():
        implied_totals[row['home_team']] = float(row['implied_home'])
        implied_totals[row['away_team']] = float(row['implied_away'])

    logger.info(
        "Implied team totals computed for %d teams across %d games",
        len(implied_totals),
        len(df),
    )
    return implied_totals


# ---------------------------------------------------------------------------
# Home/Away + Dome Splits
# ---------------------------------------------------------------------------

def compute_venue_splits(
    df: pd.DataFrame,
    schedules_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Add home/away and dome/outdoor indicators.

    Args:
        df:           Player weekly stats.
        schedules_df: Schedules DataFrame (must include roof column if available).

    Returns:
        DataFrame with is_home and is_dome columns appended.
    """
    df = df.copy()

    sched_cols = ['season', 'week', 'home_team', 'away_team']
    if 'roof' in schedules_df.columns:
        sched_cols.append('roof')
    sched = schedules_df[sched_cols].copy()

    # Home flag
    home_map = sched[['season', 'week', 'home_team']].copy()
    home_map['is_home'] = True
    home_map = home_map.rename(columns={'home_team': 'player_team'})
    away_map = sched[['season', 'week', 'away_team']].copy()
    away_map['is_home'] = False
    away_map = away_map.rename(columns={'away_team': 'player_team'})
    venue_map = pd.concat([home_map, away_map], ignore_index=True)

    if 'roof' in sched.columns:
        roof_home = sched[['season', 'week', 'home_team', 'roof']].rename(columns={'home_team': 'player_team'})
        roof_away = sched[['season', 'week', 'away_team', 'roof']].rename(columns={'away_team': 'player_team'})
        roof_map = pd.concat([roof_home, roof_away], ignore_index=True)
        venue_map = venue_map.merge(roof_map, on=['season', 'week', 'player_team'], how='left')
        venue_map['is_dome'] = venue_map['roof'].isin(['dome', 'closed'])
        venue_map.drop(columns=['roof'], inplace=True)

    df = df.merge(
        venue_map,
        left_on=['season', 'week', 'recent_team'],
        right_on=['season', 'week', 'player_team'],
        how='left',
    ).drop(columns=['player_team'])

    return df
