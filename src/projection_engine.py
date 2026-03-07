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


# Conservative starter baselines (stats per game) by position.
# Backup = 40% of starter. Unknown = 25% of starter.
_STARTER_BASELINES: Dict[str, Dict[str, float]] = {
    'QB': {
        'passing_yards': 230.0,
        'passing_tds': 1.4,
        'interceptions': 0.8,
        'rushing_yards': 15.0,
        'rushing_tds': 0.1,
    },
    'RB': {
        'rushing_yards': 55.0,
        'rushing_tds': 0.4,
        'receptions': 3.0,
        'receiving_yards': 22.0,
        'receiving_tds': 0.1,
        'carries': 12.0,
    },
    'WR': {
        'receiving_yards': 60.0,
        'receiving_tds': 0.4,
        'receptions': 4.5,
        'targets': 6.5,
    },
    'TE': {
        'receiving_yards': 40.0,
        'receiving_tds': 0.3,
        'receptions': 3.0,
        'targets': 4.5,
    },
}

_ROLE_SCALE: Dict[str, float] = {
    'starter': 1.00,
    'backup': 0.40,
    'unknown': 0.25,
}

# League-average implied team scoring total (points) used for Vegas multiplier
_LEAGUE_AVG_IMPLIED_TOTAL: float = 23.0


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


def get_bye_teams(schedules_df: pd.DataFrame, week: int) -> set:
    """
    Return the set of team abbreviations that have a bye in the given week.

    A team is on bye if it does not appear in any game for that week,
    i.e. it is absent from both the ``home_team`` and ``away_team`` columns
    of ``schedules_df`` for the target week.

    Args:
        schedules_df: Game schedule DataFrame from ``nfl.import_schedules()``.
                      Must contain ``week``, ``home_team``, and ``away_team``
                      columns with standard 2–3-letter NFL team abbreviations.
        week:         The NFL week number to check (1-based).

    Returns:
        Set of team abbreviations on bye. Empty set if ``schedules_df`` is
        empty or lacks the required columns.

    Example:
        >>> bye_teams = get_bye_teams(schedules_df, week=9)
        >>> 'KC' in bye_teams
        True
    """
    required = {'week', 'home_team', 'away_team'}
    if schedules_df.empty or not required.issubset(schedules_df.columns):
        logger.warning(
            "schedules_df missing required columns %s; bye detection skipped",
            required - set(schedules_df.columns),
        )
        return set()

    week_games = schedules_df[schedules_df['week'] == week]
    if week_games.empty:
        logger.debug("No games found for week %d; all teams treated as bye", week)
        return set()

    active_teams: set = (
        set(week_games['home_team'].dropna().unique())
        | set(week_games['away_team'].dropna().unique())
    )

    # All teams seen anywhere in the schedule (handles mid-season data)
    all_teams: set = (
        set(schedules_df['home_team'].dropna().unique())
        | set(schedules_df['away_team'].dropna().unique())
    )

    bye_teams = all_teams - active_teams
    logger.info("Week %d bye teams (%d): %s", week, len(bye_teams), sorted(bye_teams))
    return bye_teams


def _rookie_baseline(position: str, usage_role: str = 'unknown') -> Dict[str, float]:
    """
    Return a conservative per-game stat baseline for a player with no rolling
    average history (rookies, newly acquired players, or players returning from
    extended injury absence).

    Roles determine what fraction of the starter baseline is applied:
        'starter' (snap_pct > 0.60 or target_share > 0.15): 100%
        'backup'  (snap_pct 0.30–0.60):                       40%
        'unknown' (no snap/usage data available):              25%

    Args:
        position:   Player position. One of 'QB', 'RB', 'WR', 'TE'.
                    Unrecognised positions return an empty dict.
        usage_role: Role classification string. Must be one of
                    'starter', 'backup', or 'unknown'.

    Returns:
        Dict mapping stat name to projected per-game value.  Returns empty
        dict for unrecognised positions so callers can handle gracefully.

    Example:
        >>> _rookie_baseline('RB', 'starter')
        {'rushing_yards': 55.0, 'rushing_tds': 0.4, ...}
        >>> _rookie_baseline('RB', 'backup')
        {'rushing_yards': 22.0, 'rushing_tds': 0.16, ...}
    """
    starter = _STARTER_BASELINES.get(position)
    if starter is None:
        logger.debug("No baseline defined for position '%s'", position)
        return {}

    scale = _ROLE_SCALE.get(usage_role, _ROLE_SCALE['unknown'])
    return {stat: round(value * scale, 2) for stat, value in starter.items()}


def _determine_usage_role(row: pd.Series) -> str:
    """
    Classify a player row as 'starter', 'backup', or 'unknown' based on
    the most recent available snap/usage data.

    Uses the season-to-date (``_std``) columns as the most stable signal:
        snap_pct_std or target_share_std.

    Args:
        row: A single player row from a Silver-layer DataFrame.

    Returns:
        Role string: 'starter', 'backup', or 'unknown'.
    """
    snap = row.get('snap_pct_std', np.nan)
    target = row.get('target_share_std', np.nan)

    if pd.notna(snap):
        if snap > 0.60:
            return 'starter'
        if snap >= 0.30:
            return 'backup'
        return 'unknown'

    if pd.notna(target):
        return 'starter' if target > 0.15 else 'backup'

    return 'unknown'


def _vegas_multiplier(
    player_team: str,
    implied_totals: Dict[str, float],
    position: str,
    spread_by_team: Optional[Dict[str, float]] = None,
) -> float:
    """
    Compute a Vegas-adjusted output multiplier for a player based on their
    team's implied scoring total relative to the league average.

    Base formula:
        raw = implied_totals.get(player_team, league_avg) / league_avg
        clipped to [0.80, 1.20]

    RB run-heavy bonus: If the game implied total < 20 AND the player's team
    is a big favourite (spread < -7 from that team's perspective), apply an
    additional 1.05x multiplier to reflect increased rushing volume in
    anticipated blowout wins.

    Args:
        player_team:     Two-or-three-letter NFL team abbreviation.
        implied_totals:  Dict of {team_abbr: implied_points} from
                         ``compute_implied_team_totals()``.
        position:        Player position ('QB', 'RB', 'WR', 'TE').
        spread_by_team:  Optional dict of {team_abbr: spread_from_team_perspective}.
                         Negative value means the team is favoured.  Required
                         for the RB run-heavy bonus; bonus is skipped if None.

    Returns:
        Multiplier float in the range [0.80, 1.26].  The upper bound extends
        slightly beyond 1.20 when the RB run-heavy bonus applies.

    Example:
        >>> _vegas_multiplier('KC', {'KC': 27.6}, 'QB')
        1.2
        >>> _vegas_multiplier('KC', {'KC': 27.6}, 'RB')
        1.2
    """
    league_avg = _LEAGUE_AVG_IMPLIED_TOTAL
    team_implied = implied_totals.get(player_team, league_avg)

    raw = team_implied / league_avg
    multiplier = float(np.clip(raw, 0.80, 1.20))

    # RB run-heavy bonus: low-scoring expected game + team is a big favourite
    if position == 'RB' and spread_by_team is not None:
        team_spread = spread_by_team.get(player_team, 0.0)
        if team_implied < 20.0 and team_spread < -7.0:
            multiplier *= 1.05

    return round(multiplier, 4)


def project_position(
    df: pd.DataFrame,
    position: str,
    opp_rankings: pd.DataFrame,
    scoring_format: str = "half_ppr",
) -> pd.DataFrame:
    """
    Generate projections for all players of a given position.

    Players with no rolling average history (all roll3/roll6/std columns are
    NaN) receive a conservative positional baseline via ``_rookie_baseline()``
    instead of being silently zeroed out.  These rows are flagged with
    ``is_rookie_projection = True``.

    Args:
        df:             Silver-layer player DataFrame filtered to the target week
                        (must include rolling average columns).
        position:       'QB', 'RB', 'WR', or 'TE'.
        opp_rankings:   Opponent positional rankings from Silver layer.
        scoring_format: Fantasy scoring format.

    Returns:
        DataFrame with projected stat columns + projected_points +
        is_rookie_projection (bool).
    """
    pos_df = df[df['position'] == position].copy()
    if pos_df.empty:
        return pd.DataFrame()

    stat_cols = POSITION_STAT_PROFILE.get(position, [])

    # ------------------------------------------------------------------
    # Detect rows with no rolling history (rookies / newly available)
    # ------------------------------------------------------------------
    rolling_cols = []
    for stat in stat_cols:
        for suffix in ('roll3', 'roll6', 'std'):
            col = f"{stat}_{suffix}"
            if col in pos_df.columns:
                rolling_cols.append(col)

    if rolling_cols:
        all_nan_mask: pd.Series = pos_df[rolling_cols].isna().all(axis=1)
    else:
        # No rolling columns present at all — treat every row as a rookie
        all_nan_mask = pd.Series(True, index=pos_df.index)

    # Fill rookie rows with positional baselines so _weighted_baseline
    # can operate uniformly over the whole DataFrame.
    if all_nan_mask.any():
        rookie_count = int(all_nan_mask.sum())
        logger.info(
            "Applying rookie baseline to %d %s player(s) with no rolling history",
            rookie_count,
            position,
        )
        for idx in pos_df.index[all_nan_mask]:
            role = _determine_usage_role(pos_df.loc[idx])
            baseline_stats = _rookie_baseline(position, role)
            for stat, value in baseline_stats.items():
                # Write the baseline value into each rolling column so that
                # _weighted_baseline blends them consistently.
                for suffix in ('roll3', 'roll6', 'std'):
                    col = f"{stat}_{suffix}"
                    if col not in pos_df.columns:
                        pos_df[col] = np.nan
                    pos_df.at[idx, col] = value

    pos_df['is_rookie_projection'] = all_nan_mask

    # ------------------------------------------------------------------
    # Standard projection pipeline (usage × matchup applied uniformly)
    # ------------------------------------------------------------------
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
    schedules_df: Optional[pd.DataFrame] = None,
    implied_totals: Optional[Dict[str, float]] = None,
) -> pd.DataFrame:
    """
    Generate weekly projections for all fantasy-relevant positions.

    Supports three optional enrichment layers (all backward-compatible):

    1. **Bye week handling** (``schedules_df``): Players whose team is on bye
       receive zeroed stats and ``projected_points = 0.0``.  Flagged with
       ``is_bye_week = True``.

    2. **Rookie / new-player fallback**: Players with no rolling average
       history receive a conservative positional baseline instead of
       projecting zero.  Flagged with ``is_rookie_projection = True``
       (set inside ``project_position``).

    3. **Vegas lines adjustment** (``implied_totals``): Each player's
       projected stats are scaled by ``_vegas_multiplier()`` after usage and
       matchup adjustments.  The applied multiplier is stored in the
       ``vegas_multiplier`` column.

    Args:
        silver_df:      Silver-layer DataFrame (all positions, current week).
        opp_rankings:   Opponent positional rankings (Silver layer).
        season:         NFL season year.
        week:           NFL week number (the week being projected).
        scoring_format: Fantasy scoring format ('half_ppr', 'ppr', 'standard').
        schedules_df:   Optional game schedule DataFrame for the target season.
                        Used for bye-week detection.  Must contain ``week``,
                        ``home_team``, and ``away_team`` columns.  Pass the
                        week-filtered slice or the full-season schedule — the
                        function filters internally.  If None, bye detection
                        is skipped.
        implied_totals: Optional dict of {team_abbr: implied_points} from
                        ``compute_implied_team_totals()``.  If None, Vegas
                        adjustment is skipped and ``vegas_multiplier`` defaults
                        to 1.0.

    Returns:
        Combined DataFrame with projections for QB/RB/WR/TE, sorted by
        ``projected_points`` descending.  Additional boolean columns:
        ``is_bye_week``, ``is_rookie_projection``.  Numeric column:
        ``vegas_multiplier``.
    """
    # ------------------------------------------------------------------
    # 1. Build feature DataFrame from the previous week's stats
    # ------------------------------------------------------------------
    target_df = silver_df[
        (silver_df['season'] == season) & (silver_df['week'] == week - 1)
    ].copy()

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

    # ------------------------------------------------------------------
    # 2. Determine bye teams (requires schedules_df for the target week)
    # ------------------------------------------------------------------
    bye_teams: set = set()
    if schedules_df is not None:
        bye_teams = get_bye_teams(schedules_df, week)

    # ------------------------------------------------------------------
    # 3. Build Vegas spread-by-team dict for the RB run-heavy bonus
    # ------------------------------------------------------------------
    spread_by_team: Optional[Dict[str, float]] = None
    if implied_totals is not None and schedules_df is not None:
        spread_by_team = _build_spread_by_team(schedules_df, week)

    # ------------------------------------------------------------------
    # 4. Run per-position projections
    # ------------------------------------------------------------------
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

    # ------------------------------------------------------------------
    # 5. Vegas multiplier adjustment
    # ------------------------------------------------------------------
    if implied_totals is not None and 'recent_team' in combined.columns:
        vegas_mults = combined.apply(
            lambda row: _vegas_multiplier(
                player_team=row.get('recent_team', ''),
                implied_totals=implied_totals,
                position=row.get('position', ''),
                spread_by_team=spread_by_team,
            ),
            axis=1,
        )
        combined['vegas_multiplier'] = vegas_mults

        # Scale all projected stat columns and recalculate points
        proj_stat_cols_for_vegas = [
            c for c in combined.columns
            if c.startswith('proj_') and c not in ('proj_season', 'proj_week')
        ]
        for col in proj_stat_cols_for_vegas:
            combined[col] = (combined[col] * combined['vegas_multiplier']).round(2)

        # Recalculate projected_points after Vegas scaling
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
        scoring_input = combined.rename(columns=rename_map)
        scoring_input = calculate_fantasy_points_df(
            scoring_input, scoring_format=scoring_format, output_col='projected_points'
        )
        for proj_col, stat_col in rename_map.items():
            if stat_col in scoring_input.columns:
                scoring_input[proj_col] = scoring_input[stat_col]
        combined = scoring_input
    else:
        combined['vegas_multiplier'] = 1.0

    # ------------------------------------------------------------------
    # 6. Bye week zeroing (applied after all other adjustments)
    # ------------------------------------------------------------------
    combined['is_bye_week'] = False
    if bye_teams and 'recent_team' in combined.columns:
        bye_mask = combined['recent_team'].isin(bye_teams)
        if bye_mask.any():
            proj_stat_cols_all = [
                c for c in combined.columns
                if c.startswith('proj_') and c not in ('proj_season', 'proj_week')
            ]
            combined.loc[bye_mask, proj_stat_cols_all] = 0.0
            combined.loc[bye_mask, 'projected_points'] = 0.0
            combined.loc[bye_mask, 'is_bye_week'] = True
            combined.loc[bye_mask, 'vegas_multiplier'] = 1.0
            logger.info(
                "Zeroed projections for %d players on bye (teams: %s)",
                int(bye_mask.sum()),
                sorted(bye_teams),
            )

    # ------------------------------------------------------------------
    # 7. Assemble output columns
    # ------------------------------------------------------------------
    keep_cols = [
        'player_id', 'player_name', 'position', 'recent_team',
        'proj_season', 'proj_week',
    ]
    proj_stat_cols_out = [c for c in combined.columns if c.startswith('proj_') and c not in keep_cols]
    flag_cols = [c for c in ('is_bye_week', 'is_rookie_projection', 'vegas_multiplier') if c in combined.columns]
    output_cols = keep_cols + proj_stat_cols_out + ['projected_points'] + flag_cols
    output_cols = [c for c in output_cols if c in combined.columns]

    result = combined[output_cols].sort_values('projected_points', ascending=False).reset_index(drop=True)
    result['position_rank'] = result.groupby('position')['projected_points'].rank(
        ascending=False, method='first'
    ).astype(int)

    logger.info(f"Projections generated: {len(result)} players for {season} week {week}")
    return result


def _build_spread_by_team(
    schedules_df: pd.DataFrame,
    week: int,
) -> Dict[str, float]:
    """
    Build a dict of {team_abbr: spread_from_team_perspective} for the
    given week.

    ``spread_line`` in the schedule is the home-team spread (negative when
    the home team is favoured).  The away team's spread is the mirror:
    ``-spread_line``.

    Args:
        schedules_df: Game schedule DataFrame containing ``week``,
                      ``home_team``, ``away_team``, and ``spread_line``.
        week:         NFL week to look up.

    Returns:
        Dict mapping team abbreviation to its spread from that team's
        perspective (negative = favoured).  Teams missing ``spread_line``
        data default to 0.0 (pick-em).
    """
    required = {'week', 'home_team', 'away_team'}
    if not required.issubset(schedules_df.columns):
        return {}

    week_games = schedules_df[schedules_df['week'] == week].copy()
    if week_games.empty:
        return {}

    spread_col = 'spread_line' if 'spread_line' in week_games.columns else None
    spread_by_team: Dict[str, float] = {}

    for _, row in week_games.iterrows():
        home = row['home_team']
        away = row['away_team']
        home_spread = float(row[spread_col]) if spread_col and pd.notna(row[spread_col]) else 0.0
        spread_by_team[home] = home_spread
        spread_by_team[away] = -home_spread  # mirror: if home is -7, away is +7

    return spread_by_team


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
