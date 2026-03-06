#!/usr/bin/env python3
"""
Fantasy Football Projection Engine

Generates weekly player projections using weighted historical averages
adjusted for opponent defensive strength and positional usage stability.

Approach:
    1. Start from a player's recent rolling averages (3-week, 6-week, season-to-date)
    2. Apply a usage-stability weight (snap % / target share)
    3. Adjust baseline by opponent positional matchup factor
    4. Convert projected stats to fantasy points via scoring_calculator

Designed to work entirely from DataFrames — no direct S3 calls here.
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Optional
import logging

from scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weights for blending rolling windows
# ---------------------------------------------------------------------------
RECENCY_WEIGHTS = {
    'roll3': 0.50,   # Last 3 weeks — most predictive
    'roll6': 0.30,   # Last 6 weeks
    'std':   0.20,   # Season-to-date
}

# Stats to project by position
POSITION_STAT_PROFILE: Dict[str, List[str]] = {
    'QB': ['passing_yards', 'passing_tds', 'interceptions', 'rushing_yards', 'rushing_tds'],
    'RB': ['rushing_yards', 'rushing_tds', 'carries', 'receptions', 'receiving_yards', 'receiving_tds'],
    'WR': ['targets', 'receptions', 'receiving_yards', 'receiving_tds'],
    'TE': ['targets', 'receptions', 'receiving_yards', 'receiving_tds'],
}

# Usage-stability stat that indicates role consistency (higher = more reliable)
USAGE_STABILITY_STAT: Dict[str, str] = {
    'QB': 'snap_pct',
    'RB': 'carry_share',
    'WR': 'target_share',
    'TE': 'target_share',
}


# ---------------------------------------------------------------------------
# Core projection functions
# ---------------------------------------------------------------------------

def _weighted_baseline(df: pd.DataFrame, stat: str) -> pd.Series:
    """
    Blend roll3, roll6, and season-to-date columns for a single stat.
    Falls back gracefully if columns are missing.
    """
    result = pd.Series(0.0, index=df.index)
    total_weight = 0.0

    for suffix, weight in RECENCY_WEIGHTS.items():
        col = f"{stat}_{suffix}"
        if col in df.columns:
            result += df[col].fillna(0) * weight
            total_weight += weight

    if total_weight > 0:
        result /= total_weight

    return result


def _usage_multiplier(df: pd.DataFrame, position: str) -> pd.Series:
    """
    Return a [0.7, 1.3] multiplier based on usage stability.
    High snap%/target-share → multiplier > 1 (more reliable).
    Low usage → multiplier < 1 (less reliable, regression toward mean).
    """
    usage_col = USAGE_STABILITY_STAT.get(position, 'snap_pct')
    if usage_col not in df.columns:
        return pd.Series(1.0, index=df.index)

    usage = df[usage_col].fillna(df[usage_col].median())
    # Normalize to [0.7, 1.3] range based on percentile
    percentile = usage.rank(pct=True)
    multiplier = 0.7 + 0.6 * percentile
    return multiplier.clip(0.7, 1.3)


def _matchup_factor(
    df: pd.DataFrame,
    opp_rankings: pd.DataFrame,
    position: str,
) -> pd.Series:
    """
    Look up opponent defensive ranking and return a matchup adjustment factor.

    Rank 1 (easiest) → factor ~1.15
    Rank 16 (median) → factor ~1.00
    Rank 32 (hardest) → factor ~0.85
    """
    if opp_rankings.empty or 'opponent' not in df.columns:
        return pd.Series(1.0, index=df.index)

    pos_rankings = opp_rankings[opp_rankings['position'] == position][
        ['team', 'week', 'season', 'rank']
    ].copy()
    pos_rankings = pos_rankings.rename(columns={'team': 'opponent', 'rank': 'opp_rank'})

    merged = df.merge(pos_rankings, on=['season', 'week', 'opponent'], how='left')
    opp_rank = merged['opp_rank'].fillna(16)  # neutral if not found

    # Linear scale: rank 1 → 1.15, rank 32 → 0.85
    factor = 1.15 - (opp_rank - 1) * (0.30 / 31)
    factor.index = df.index
    return factor.clip(0.75, 1.25)


def project_position(
    df: pd.DataFrame,
    position: str,
    opp_rankings: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """
    Generate projections for all players of a given position.

    Args:
        df:             Silver-layer player DataFrame filtered to the target week
                        (must include rolling average columns).
        position:       'QB', 'RB', 'WR', or 'TE'.
        opp_rankings:   Opponent positional rankings from Silver layer.
        scoring_format: Fantasy scoring format.

    Returns:
        DataFrame with projected stat columns + projected_points.
    """
    pos_df = df[df['position'] == position].copy()
    if pos_df.empty:
        return pd.DataFrame()

    stat_cols = POSITION_STAT_PROFILE.get(position, [])
    usage_mult = _usage_multiplier(pos_df, position)
    matchup = _matchup_factor(pos_df, opp_rankings, position)

    proj_stats = {}
    for stat in stat_cols:
        baseline = _weighted_baseline(pos_df, stat)
        proj_stats[f"proj_{stat}"] = (baseline * usage_mult * matchup).round(2)

    proj_df = pos_df.assign(**proj_stats)

    # Map projected stat column names to scoring calculator expectations
    rename_map = {
        'proj_passing_yards': 'passing_yards',
        'proj_passing_tds': 'passing_tds',
        'proj_interceptions': 'interceptions',
        'proj_rushing_yards': 'rushing_yards',
        'proj_rushing_tds': 'rushing_tds',
        'proj_receptions': 'receptions',
        'proj_receiving_yards': 'receiving_yards',
        'proj_receiving_tds': 'receiving_tds',
        'proj_targets': 'targets',
        'proj_carries': 'carries',
    }
    # Temporarily rename projected cols for scoring calculator
    scoring_input = proj_df.rename(columns=rename_map)
    scoring_input = calculate_fantasy_points_df(
        scoring_input, scoring_format=scoring_format, output_col='projected_points'
    )
    # Put original proj_ columns back
    for proj_col, stat_col in rename_map.items():
        if stat_col in scoring_input.columns:
            scoring_input[proj_col] = scoring_input[stat_col]

    return scoring_input


def generate_weekly_projections(
    silver_df: pd.DataFrame,
    opp_rankings: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """
    Generate weekly projections for all fantasy-relevant positions.

    Args:
        silver_df:      Silver-layer DataFrame (all positions, current week).
        opp_rankings:   Opponent positional rankings (Silver layer).
        season:         NFL season year.
        week:           NFL week number.
        scoring_format: Fantasy scoring format.

    Returns:
        Combined DataFrame with projections for QB/RB/WR/TE, sorted by
        projected_points descending.
    """
    # Filter to the target week's data (upcoming week — use previous stats as features)
    target_df = silver_df[(silver_df['season'] == season) & (silver_df['week'] == week - 1)].copy()

    if target_df.empty:
        # Fallback: use most recent week available
        latest_week = silver_df[silver_df['season'] == season]['week'].max()
        target_df = silver_df[
            (silver_df['season'] == season) & (silver_df['week'] == latest_week)
        ].copy()
        logger.warning(f"Week {week} not found; using week {latest_week} as feature source")

    # Stamp the projection week
    target_df['proj_season'] = season
    target_df['proj_week'] = week

    all_projections = []
    for position in ['QB', 'RB', 'WR', 'TE']:
        logger.info(f"Projecting {position}...")
        pos_proj = project_position(target_df, position, opp_rankings, scoring_format)
        if not pos_proj.empty:
            all_projections.append(pos_proj)

    if not all_projections:
        logger.warning("No projections generated")
        return pd.DataFrame()

    combined = pd.concat(all_projections, ignore_index=True)

    # Keep only the most relevant output columns
    keep_cols = [
        'player_id', 'player_name', 'position', 'recent_team',
        'proj_season', 'proj_week',
    ]
    proj_stat_cols = [c for c in combined.columns if c.startswith('proj_') and c not in keep_cols]
    output_cols = keep_cols + proj_stat_cols + ['projected_points']
    output_cols = [c for c in output_cols if c in combined.columns]

    result = combined[output_cols].sort_values('projected_points', ascending=False).reset_index(drop=True)
    result['position_rank'] = result.groupby('position')['projected_points'].rank(
        ascending=False, method='first'
    ).astype(int)

    logger.info(f"Projections generated: {len(result)} players for {season} week {week}")
    return result


def generate_preseason_projections(
    seasonal_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
    target_season: int = 2026,
) -> pd.DataFrame:
    """
    Generate pre-season projections based on historical seasonal averages.

    Uses the last 2 seasons of data to project a full-season expected
    fantasy points total for each player (for draft rankings).

    Args:
        seasonal_df:    Player seasonal stats DataFrame (Bronze/Silver).
        scoring_format: Fantasy scoring format.
        target_season:  The upcoming season to project for.

    Returns:
        DataFrame ranked by projected_season_points descending.
    """
    df = seasonal_df.copy()

    # Use last 2 complete seasons
    recent_seasons = sorted(df['season'].unique())[-2:]
    df = df[df['season'].isin(recent_seasons)]

    if df.empty:
        logger.warning("No seasonal data for preseason projections")
        return pd.DataFrame()

    # Weight: more recent season counts double
    max_season = max(recent_seasons)
    df['season_weight'] = df['season'].apply(lambda s: 2.0 if s == max_season else 1.0)

    # Weighted average of seasonal stats
    stat_cols = [
        'passing_yards', 'passing_tds', 'interceptions',
        'rushing_yards', 'rushing_tds', 'carries',
        'receiving_yards', 'receiving_tds', 'receptions', 'targets',
    ]
    available_stats = [c for c in stat_cols if c in df.columns]

    weighted = df.copy()
    for col in available_stats:
        weighted[col] = weighted[col].fillna(0) * weighted['season_weight']

    group_cols = ['player_id', 'position']
    if 'player_name' in weighted.columns:
        group_cols.append('player_name')
    if 'recent_team' in weighted.columns:
        group_cols.append('recent_team')

    agg_dict = {col: 'sum' for col in available_stats}
    agg_dict['season_weight'] = 'sum'
    proj = weighted.groupby(group_cols, as_index=False).agg(agg_dict)

    # Normalize by total weight
    for col in available_stats:
        proj[col] = (proj[col] / proj['season_weight']).round(2)
    proj.drop(columns=['season_weight'], inplace=True)

    # Scale to 17-game season (seasonal data = 17 games)
    # Projections already represent season totals; convert to per-game for comparability
    games = 17
    proj['projected_season_points'] = calculate_fantasy_points_df(
        proj, scoring_format=scoring_format, output_col='_pts'
    )['_pts']

    proj['projected_season_points'] = proj['projected_season_points'].round(1)
    proj['proj_season'] = target_season

    # Rank overall and by position
    pos_filter = proj['position'].isin(['QB', 'RB', 'WR', 'TE'])
    proj = proj[pos_filter].copy()
    proj['overall_rank'] = proj['projected_season_points'].rank(ascending=False, method='first').astype(int)
    proj['position_rank'] = proj.groupby('position')['projected_season_points'].rank(
        ascending=False, method='first'
    ).astype(int)

    proj = proj.sort_values('overall_rank').reset_index(drop=True)
    logger.info(f"Preseason projections generated: {len(proj)} players for {target_season}")
    return proj
