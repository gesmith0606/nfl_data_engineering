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
from typing import Dict, List, Optional, Tuple
import logging

from scoring_calculator import calculate_fantasy_points_df

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Weights for blending rolling windows
# ---------------------------------------------------------------------------
RECENCY_WEIGHTS = {
    "roll3": 0.45,  # Last 3 weeks — most predictive
    "roll6": 0.30,  # Last 6 weeks
    "std": 0.25,  # Season-to-date — increased to dampen boom/bust swings
}

# Regression-to-mean shrinkage applied after scoring.
# Backtest shows high projections systematically overshoot:
#   Proj 15-20 → actual ~13.7 (shrink ~0.80)
#   Proj 20-25 → actual ~15.6 (shrink ~0.70)
#   Proj 25+   → actual ~17   (shrink ~0.65)
PROJECTION_CEILING_SHRINKAGE = {
    15.0: 0.90,  # projections 15-20 pts → multiply by 0.90
    20.0: 0.85,  # projections 20-25 pts → multiply by 0.85
    25.0: 0.80,  # projections 25+ pts   → multiply by 0.80
}

# Stats to project by position
POSITION_STAT_PROFILE: Dict[str, List[str]] = {
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

# Usage-stability stat that indicates role consistency (higher = more reliable)
USAGE_STABILITY_STAT: Dict[str, str] = {
    "QB": "snap_pct",
    "RB": "carry_share",
    "WR": "target_share",
    "TE": "target_share",
}


# Conservative starter baselines (stats per game) by position.
# Backup = 40% of starter. Unknown = 25% of starter.
_STARTER_BASELINES: Dict[str, Dict[str, float]] = {
    "QB": {
        "passing_yards": 230.0,
        "passing_tds": 1.4,
        "interceptions": 0.8,
        "rushing_yards": 15.0,
        "rushing_tds": 0.1,
    },
    "RB": {
        "rushing_yards": 55.0,
        "rushing_tds": 0.4,
        "receptions": 3.0,
        "receiving_yards": 22.0,
        "receiving_tds": 0.1,
        "carries": 12.0,
    },
    "WR": {
        "receiving_yards": 60.0,
        "receiving_tds": 0.4,
        "receptions": 4.5,
        "targets": 6.5,
    },
    "TE": {
        "receiving_yards": 40.0,
        "receiving_tds": 0.3,
        "receptions": 3.0,
        "targets": 4.5,
    },
}

_ROLE_SCALE: Dict[str, float] = {
    "starter": 1.00,
    "backup": 0.40,
    "unknown": 0.25,
}

# League-average implied team scoring total (points) used for Vegas multiplier
_LEAGUE_AVG_IMPLIED_TOTAL: float = 23.0

# Empirically calibrated multipliers: implied real NFL total -> expected team
# fantasy budget (sum of QB+RB+WR+TE fantasy points).
# Derived from 2025 season: per-team seasonal fantasy points / games / avg implied total.
_IMPLIED_TO_FANTASY_MULT: Dict[str, float] = {
    "half_ppr": 3.36,
    "ppr": 3.77,
    "standard": 2.86,
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
    Return a [0.80, 1.15] multiplier based on usage stability.
    High snap%/target-share → multiplier > 1 (more reliable).
    Low usage → multiplier < 1 (less reliable, regression toward mean).

    Range tightened from [0.7, 1.3] based on backtest analysis showing
    that a wider range amplifies over-projection for high-usage players.
    """
    usage_col = USAGE_STABILITY_STAT.get(position, "snap_pct")
    if usage_col not in df.columns:
        return pd.Series(1.0, index=df.index)

    usage = df[usage_col].fillna(df[usage_col].median())
    # Normalize to [0.80, 1.15] range based on percentile
    percentile = usage.rank(pct=True)
    multiplier = 0.80 + 0.35 * percentile
    return multiplier.clip(0.80, 1.15)


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
    if opp_rankings.empty or "opponent" not in df.columns:
        return pd.Series(1.0, index=df.index)

    pos_rankings = opp_rankings[opp_rankings["position"] == position][
        ["team", "week", "season", "rank"]
    ].copy()
    pos_rankings = pos_rankings.rename(columns={"team": "opponent", "rank": "opp_rank"})

    merged = df.merge(pos_rankings, on=["season", "week", "opponent"], how="left")
    opp_rank = merged["opp_rank"].fillna(16)  # neutral if not found

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
    required = {"week", "home_team", "away_team"}
    if schedules_df.empty or not required.issubset(schedules_df.columns):
        logger.warning(
            "schedules_df missing required columns %s; bye detection skipped",
            required - set(schedules_df.columns),
        )
        return set()

    week_games = schedules_df[schedules_df["week"] == week]
    if week_games.empty:
        logger.debug("No games found for week %d; all teams treated as bye", week)
        return set()

    active_teams: set = set(week_games["home_team"].dropna().unique()) | set(
        week_games["away_team"].dropna().unique()
    )

    # All teams seen anywhere in the schedule (handles mid-season data)
    all_teams: set = set(schedules_df["home_team"].dropna().unique()) | set(
        schedules_df["away_team"].dropna().unique()
    )

    bye_teams = all_teams - active_teams
    logger.info("Week %d bye teams (%d): %s", week, len(bye_teams), sorted(bye_teams))
    return bye_teams


def _rookie_baseline(position: str, usage_role: str = "unknown") -> Dict[str, float]:
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

    scale = _ROLE_SCALE.get(usage_role, _ROLE_SCALE["unknown"])
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
    snap = row.get("snap_pct_std", np.nan)
    target = row.get("target_share_std", np.nan)

    if pd.notna(snap):
        if snap > 0.60:
            return "starter"
        if snap >= 0.30:
            return "backup"
        return "unknown"

    if pd.notna(target):
        return "starter" if target > 0.15 else "backup"

    return "unknown"


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
    if position == "RB" and spread_by_team is not None:
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
    pos_df = df[df["position"] == position].copy()
    if pos_df.empty:
        return pd.DataFrame()

    stat_cols = POSITION_STAT_PROFILE.get(position, [])

    # ------------------------------------------------------------------
    # Detect rows with no rolling history (rookies / newly available)
    # ------------------------------------------------------------------
    rolling_cols = []
    for stat in stat_cols:
        for suffix in ("roll3", "roll6", "std"):
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
                for suffix in ("roll3", "roll6", "std"):
                    col = f"{stat}_{suffix}"
                    if col not in pos_df.columns:
                        pos_df[col] = np.nan
                    pos_df.at[idx, col] = value

    pos_df["is_rookie_projection"] = all_nan_mask

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
        "proj_passing_yards": "passing_yards",
        "proj_passing_tds": "passing_tds",
        "proj_interceptions": "interceptions",
        "proj_rushing_yards": "rushing_yards",
        "proj_rushing_tds": "rushing_tds",
        "proj_receptions": "receptions",
        "proj_receiving_yards": "receiving_yards",
        "proj_receiving_tds": "receiving_tds",
        "proj_targets": "targets",
        "proj_carries": "carries",
    }
    # Drop original stat columns that conflict with projected column renames
    orig_stat_cols = [v for v in rename_map.values() if v in proj_df.columns]
    scoring_input = proj_df.drop(columns=orig_stat_cols, errors="ignore")
    scoring_input = scoring_input.rename(columns=rename_map).reset_index(drop=True)
    scoring_input = calculate_fantasy_points_df(
        scoring_input, scoring_format=scoring_format, output_col="projected_points"
    )
    # Rename scoring columns back to proj_ prefix for clarity
    reverse_map = {v: k for k, v in rename_map.items()}
    scoring_input = scoring_input.rename(columns=reverse_map)

    # Apply regression-to-mean shrinkage for high projections.
    # Backtest shows projections above 15 pts systematically overshoot.
    pts = scoring_input["projected_points"]
    shrink = pd.Series(1.0, index=scoring_input.index)
    for threshold in sorted(PROJECTION_CEILING_SHRINKAGE.keys()):
        factor = PROJECTION_CEILING_SHRINKAGE[threshold]
        shrink = shrink.where(pts < threshold, factor)
    scoring_input["projected_points"] = (pts * shrink).round(2)

    return scoring_input


def _compute_team_fantasy_budget(
    implied_total: float,
    scoring_format: str = "half_ppr",
) -> float:
    """Convert a real NFL implied team total to expected team fantasy budget.

    Uses empirically calibrated multipliers derived from the relationship
    between Vegas implied team totals and actual team fantasy point totals
    (QB+RB+WR+TE) across a full season.

    Args:
        implied_total: Vegas implied team scoring total (real NFL points).
        scoring_format: Fantasy scoring format. Must be a key in
            ``_IMPLIED_TO_FANTASY_MULT``.

    Returns:
        Expected total fantasy points for the team's skill players in the
        given scoring format.

    Example:
        >>> _compute_team_fantasy_budget(24.5, 'half_ppr')
        82.32
    """
    mult = _IMPLIED_TO_FANTASY_MULT.get(
        scoring_format, _IMPLIED_TO_FANTASY_MULT["half_ppr"]
    )
    return round(implied_total * mult, 2)


def apply_team_constraints(
    projections_df: pd.DataFrame,
    implied_totals: Optional[Dict[str, float]] = None,
    scoring_format: str = "half_ppr",
    dampen: float = 0.6,
    dead_zone: float = 0.10,
) -> pd.DataFrame:
    """Post-projection normalization to align team sums with implied totals.

    For each team with an implied total, computes the expected fantasy budget
    and compares it to the sum of projected points for active (non-bye,
    non-Out) players. If the ratio is outside the dead zone (+-10%), a
    dampened scaling factor is applied to projected points and stat columns.

    Args:
        projections_df: Projection DataFrame with ``recent_team``,
            ``projected_points``, and optionally ``is_bye_week``,
            ``injury_status`` columns.
        implied_totals: Dict of ``{team_abbr: implied_points}``. If None
            or empty, returns projections unchanged.
        scoring_format: Fantasy scoring format for budget computation.
        dampen: Dampening factor applied to the scaling adjustment.
            0.0 means no adjustment; 1.0 means full normalization.
            Default 0.6 provides a moderate pull toward the budget.
        dead_zone: Fractional tolerance around 1.0 within which no
            adjustment is made. Default 0.10 means +-10%.

    Returns:
        DataFrame with adjusted ``projected_points``, scaled ``proj_*``
        stat columns, a new ``team_constraint_factor`` column, and
        recalculated ``projected_floor`` / ``projected_ceiling`` if those
        columns existed in the input.
    """
    if implied_totals is None or not implied_totals or projections_df.empty:
        df = projections_df.copy()
        df["team_constraint_factor"] = 1.0
        return df

    if "recent_team" not in projections_df.columns:
        df = projections_df.copy()
        df["team_constraint_factor"] = 1.0
        return df

    df = projections_df.copy()
    df["team_constraint_factor"] = 1.0

    # Identify active players: not on bye, not Out/IR
    active_mask = pd.Series(True, index=df.index)
    if "is_bye_week" in df.columns:
        active_mask &= ~df["is_bye_week"].fillna(False).astype(bool)
    if "injury_status" in df.columns:
        out_statuses = {
            "Out",
            "Injured Reserve",
            "IR",
            "Physically Unable to Perform",
            "PUP",
            "Suspension",
        }
        active_mask &= ~df["injury_status"].isin(out_statuses)

    has_floor_ceiling = (
        "projected_floor" in df.columns and "projected_ceiling" in df.columns
    )

    proj_stat_cols = [
        c
        for c in df.columns
        if c.startswith("proj_") and c not in ("proj_season", "proj_week")
    ]

    for team, implied in implied_totals.items():
        team_active_mask = active_mask & (df["recent_team"] == team)
        if not team_active_mask.any():
            continue

        budget = _compute_team_fantasy_budget(implied, scoring_format)
        team_sum = df.loc[team_active_mask, "projected_points"].sum()

        if team_sum <= 0:
            continue

        ratio = budget / team_sum
        # Dead zone: skip if within +-dead_zone of 1.0
        if abs(ratio - 1.0) <= dead_zone:
            continue

        scale = 1.0 + dampen * (ratio - 1.0)

        df.loc[team_active_mask, "projected_points"] = (
            (df.loc[team_active_mask, "projected_points"] * scale)
            .round(2)
            .clip(lower=0.0)
        )

        for col in proj_stat_cols:
            df.loc[team_active_mask, col] = (
                (df.loc[team_active_mask, col] * scale).round(2).clip(lower=0.0)
            )

        df.loc[team_active_mask, "team_constraint_factor"] = round(scale, 4)

    # Recalculate floor/ceiling if they existed
    if has_floor_ceiling:
        pts = df["projected_points"]
        pos_mult = df["position"].map(_FLOOR_CEILING_MULT).fillna(0.40)
        df["projected_floor"] = (pts * (1.0 - pos_mult)).clip(lower=0).round(2)
        df["projected_ceiling"] = (pts * (1.0 + pos_mult)).round(2)

    return df


def generate_weekly_projections(
    silver_df: pd.DataFrame,
    opp_rankings: pd.DataFrame,
    season: int,
    week: int,
    scoring_format: str = "half_ppr",
    schedules_df: Optional[pd.DataFrame] = None,
    implied_totals: Optional[Dict[str, float]] = None,
    apply_constraints: bool = False,
) -> pd.DataFrame:
    """
    Generate weekly projections for all fantasy-relevant positions.

    Supports four optional enrichment layers (all backward-compatible):

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

    4. **Team constraints** (``apply_constraints``): Post-projection
       normalization that scales player projections so each team's total
       aligns with the implied team fantasy budget.  Requires
       ``implied_totals``.

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
        apply_constraints: If True and implied_totals is provided, apply
                        team-level constraints via ``apply_team_constraints()``
                        after all other adjustments.  Default False.

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
        (silver_df["season"] == season) & (silver_df["week"] == week - 1)
    ].copy()

    if target_df.empty:
        # Fallback: use most recent week available
        latest_week = silver_df[silver_df["season"] == season]["week"].max()
        target_df = silver_df[
            (silver_df["season"] == season) & (silver_df["week"] == latest_week)
        ].copy()
        logger.warning(
            f"Week {week} not found; using week {latest_week} as feature source"
        )

    # Stamp the projection week
    target_df["proj_season"] = season
    target_df["proj_week"] = week

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
    for position in ["QB", "RB", "WR", "TE"]:
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
    if implied_totals is not None and "recent_team" in combined.columns:
        vegas_mults = combined.apply(
            lambda row: _vegas_multiplier(
                player_team=row.get("recent_team", ""),
                implied_totals=implied_totals,
                position=row.get("position", ""),
                spread_by_team=spread_by_team,
            ),
            axis=1,
        )
        combined["vegas_multiplier"] = vegas_mults

        # Scale all projected stat columns and recalculate points
        proj_stat_cols_for_vegas = [
            c
            for c in combined.columns
            if c.startswith("proj_") and c not in ("proj_season", "proj_week")
        ]
        for col in proj_stat_cols_for_vegas:
            combined[col] = (combined[col] * combined["vegas_multiplier"]).round(2)

        # Recalculate projected_points after Vegas scaling
        rename_map = {
            "proj_passing_yards": "passing_yards",
            "proj_passing_tds": "passing_tds",
            "proj_interceptions": "interceptions",
            "proj_rushing_yards": "rushing_yards",
            "proj_rushing_tds": "rushing_tds",
            "proj_receptions": "receptions",
            "proj_receiving_yards": "receiving_yards",
            "proj_receiving_tds": "receiving_tds",
            "proj_targets": "targets",
            "proj_carries": "carries",
        }
        scoring_input = combined.rename(columns=rename_map)
        scoring_input = calculate_fantasy_points_df(
            scoring_input, scoring_format=scoring_format, output_col="projected_points"
        )
        for proj_col, stat_col in rename_map.items():
            if stat_col in scoring_input.columns:
                scoring_input[proj_col] = scoring_input[stat_col]
        combined = scoring_input
    else:
        combined["vegas_multiplier"] = 1.0

    # ------------------------------------------------------------------
    # 6. Bye week zeroing (applied after all other adjustments)
    # ------------------------------------------------------------------
    combined["is_bye_week"] = False
    if bye_teams and "recent_team" in combined.columns:
        bye_mask = combined["recent_team"].isin(bye_teams)
        if bye_mask.any():
            proj_stat_cols_all = [
                c
                for c in combined.columns
                if c.startswith("proj_") and c not in ("proj_season", "proj_week")
            ]
            combined.loc[bye_mask, proj_stat_cols_all] = 0.0
            combined.loc[bye_mask, "projected_points"] = 0.0
            combined.loc[bye_mask, "is_bye_week"] = True
            combined.loc[bye_mask, "vegas_multiplier"] = 1.0
            logger.info(
                "Zeroed projections for %d players on bye (teams: %s)",
                int(bye_mask.sum()),
                sorted(bye_teams),
            )

    # ------------------------------------------------------------------
    # 7. Team constraints (opt-in, after bye zeroing and injury)
    # ------------------------------------------------------------------
    if apply_constraints and implied_totals is not None:
        combined = apply_team_constraints(
            combined,
            implied_totals,
            scoring_format=scoring_format,
        )
        logger.info("Team constraints applied")

    # ------------------------------------------------------------------
    # 8. Assemble output columns
    # ------------------------------------------------------------------
    keep_cols = [
        "player_id",
        "player_name",
        "position",
        "recent_team",
        "proj_season",
        "proj_week",
    ]
    proj_stat_cols_out = [
        c for c in combined.columns if c.startswith("proj_") and c not in keep_cols
    ]
    flag_cols = [
        c
        for c in (
            "is_bye_week",
            "is_rookie_projection",
            "vegas_multiplier",
            "team_constraint_factor",
        )
        if c in combined.columns
    ]
    output_cols = keep_cols + proj_stat_cols_out + ["projected_points"] + flag_cols
    output_cols = [c for c in output_cols if c in combined.columns]

    result = (
        combined[output_cols]
        .sort_values("projected_points", ascending=False)
        .reset_index(drop=True)
    )
    result["position_rank"] = (
        result.groupby("position")["projected_points"]
        .rank(ascending=False, method="first")
        .astype(int)
    )

    logger.info(
        f"Projections generated: {len(result)} players for {season} week {week}"
    )
    return result


# ---------------------------------------------------------------------------
# Floor / ceiling confidence intervals
# ---------------------------------------------------------------------------

# Position-specific variance multipliers derived from backtest RMSE:
#   QB RMSE ~8.4, RB ~6.8, WR ~6.6, TE ~5.4
_FLOOR_CEILING_MULT = {"QB": 0.45, "RB": 0.40, "WR": 0.38, "TE": 0.35, "K": 0.40}


def add_floor_ceiling(df: pd.DataFrame) -> pd.DataFrame:
    """Add projected_floor and projected_ceiling columns based on position variance.

    Should be called AFTER all adjustments (injury, Vegas, bye) are applied
    so that floor/ceiling are always consistent with projected_points.

    Args:
        df: Projections DataFrame with 'projected_points' and 'position' columns.

    Returns:
        DataFrame with projected_floor and projected_ceiling columns added.
    """
    df = df.copy()
    pts = df["projected_points"]
    pos_mult = df["position"].map(_FLOOR_CEILING_MULT).fillna(0.40)
    df["projected_floor"] = (pts * (1.0 - pos_mult)).clip(lower=0).round(2)
    df["projected_ceiling"] = (pts * (1.0 + pos_mult)).round(2)
    return df


# ---------------------------------------------------------------------------
# Injury adjustments
# ---------------------------------------------------------------------------

INJURY_MULTIPLIERS: Dict[str, float] = {
    "Active": 1.0,
    "Questionable": 0.85,
    "Doubtful": 0.50,
    "Out": 0.0,
    "Injured Reserve": 0.0,
    "IR": 0.0,
    "Physically Unable to Perform": 0.0,
    "PUP": 0.0,
    "Suspension": 0.0,
}


def apply_injury_adjustments(
    projections_df: pd.DataFrame,
    injuries_df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Adjust projected fantasy points based on weekly injury report status.

    Players not listed on the injury report are assumed healthy (multiplier 1.0).
    Players listed as Out/IR/PUP receive zero projected points.

    Args:
        projections_df: Projection output from ``generate_weekly_projections()``.
        injuries_df:    Injury report DataFrame (from ``nfl.import_injuries()``).
                        Expected columns: ``gsis_id`` or ``player_name``,
                        ``report_status``.

    Returns:
        Projections DataFrame with added ``injury_status`` (str) and
        ``injury_multiplier`` (float) columns.  ``projected_points`` and
        all ``proj_*`` stat columns are scaled by the multiplier.
    """
    df = projections_df.copy()
    df["injury_status"] = "Active"
    df["injury_multiplier"] = 1.0

    if injuries_df is None or injuries_df.empty:
        logger.info("No injury data provided; all players treated as Active")
        return df

    # Determine join column — prefer gsis_id, fall back to player_name
    if "gsis_id" in df.columns and "gsis_id" in injuries_df.columns:
        join_col = "gsis_id"
    elif "player_id" in df.columns and "gsis_id" in injuries_df.columns:
        join_col = None  # need to map
        injuries_df = injuries_df.rename(columns={"gsis_id": "player_id"})
        join_col = "player_id"
    elif "player_name" in df.columns and "full_name" in injuries_df.columns:
        join_col = "player_name"
        injuries_df = injuries_df.rename(columns={"full_name": "player_name"})
    elif "player_name" in df.columns and "player_name" in injuries_df.columns:
        join_col = "player_name"
    else:
        logger.warning("Cannot join injury data — no common identifier column found")
        return df

    # Build a lookup: player -> most severe status
    status_col = "report_status" if "report_status" in injuries_df.columns else "status"
    if status_col not in injuries_df.columns:
        logger.warning("Injury DataFrame missing status column; skipping adjustment")
        return df

    inj_lookup = (
        injuries_df[[join_col, status_col]]
        .dropna(subset=[join_col, status_col])
        .drop_duplicates(subset=[join_col], keep="last")
        .set_index(join_col)[status_col]
        .to_dict()
    )

    df["injury_status"] = df[join_col].map(inj_lookup).fillna("Active")
    df["injury_multiplier"] = df["injury_status"].map(
        lambda s: INJURY_MULTIPLIERS.get(s, 0.85)  # unknown status → cautious
    )

    # Scale projections
    proj_cols = [
        c
        for c in df.columns
        if c.startswith("proj_") and c not in ("proj_season", "proj_week")
    ]
    for col in proj_cols:
        df[col] = (df[col] * df["injury_multiplier"]).round(2)
    df["projected_points"] = (df["projected_points"] * df["injury_multiplier"]).round(2)

    injured_count = (df["injury_multiplier"] < 1.0).sum()
    logger.info("Injury adjustments applied: %d players affected", injured_count)
    return df


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
    required = {"week", "home_team", "away_team"}
    if not required.issubset(schedules_df.columns):
        return {}

    week_games = schedules_df[schedules_df["week"] == week].copy()
    if week_games.empty:
        return {}

    spread_col = "spread_line" if "spread_line" in week_games.columns else None
    spread_by_team: Dict[str, float] = {}

    for _, row in week_games.iterrows():
        home = row["home_team"]
        away = row["away_team"]
        home_spread = (
            float(row[spread_col]) if spread_col and pd.notna(row[spread_col]) else 0.0
        )
        spread_by_team[home] = home_spread
        spread_by_team[away] = -home_spread  # mirror: if home is -7, away is +7

    return spread_by_team


def draft_capital_boost(draft_ovr: float, position: str) -> float:
    """Additive multiplier for rookie preseason projections.

    Linear decay from 1.20 at pick 1 to 1.00 at pick 64.
    Undrafted or picks 64+ get no boost.

    Args:
        draft_ovr: Overall draft pick number (1-based). NaN for undrafted.
        position: Position code (currently unused but available for future tuning).

    Returns:
        Multiplier >= 1.0.
    """
    if pd.isna(draft_ovr) or draft_ovr >= 64:
        return 1.0
    boost = 1.20 - (draft_ovr - 1) * (0.20 / 63)
    return round(max(1.0, boost), 3)


def generate_preseason_projections(
    seasonal_df: pd.DataFrame,
    scoring_format: str = "half_ppr",
    target_season: int = 2026,
    historical_df: Optional[pd.DataFrame] = None,
) -> pd.DataFrame:
    """
    Generate pre-season projections based on historical seasonal averages.

    Uses the last 2 seasons of data to project a full-season expected
    fantasy points total for each player (for draft rankings).

    Args:
        seasonal_df:    Player seasonal stats DataFrame (Bronze/Silver).
        scoring_format: Fantasy scoring format.
        target_season:  The upcoming season to project for.
        historical_df:  Optional Silver historical dimension table with draft_ovr
                        and gsis_id columns. When provided, rookies receive a
                        draft capital boost (up to +20% for pick 1).

    Returns:
        DataFrame ranked by projected_season_points descending.
    """
    df = seasonal_df.copy()

    # Use last 2 complete seasons
    recent_seasons = sorted(df["season"].unique())[-2:]
    df = df[df["season"].isin(recent_seasons)]

    if df.empty:
        logger.warning("No seasonal data for preseason projections")
        return pd.DataFrame()

    # Weight: more recent season counts double
    max_season = max(recent_seasons)
    df["season_weight"] = df["season"].apply(lambda s: 2.0 if s == max_season else 1.0)

    # Weighted average of seasonal stats
    stat_cols = [
        "passing_yards",
        "passing_tds",
        "interceptions",
        "rushing_yards",
        "rushing_tds",
        "carries",
        "receiving_yards",
        "receiving_tds",
        "receptions",
        "targets",
    ]
    available_stats = [c for c in stat_cols if c in df.columns]

    weighted = df.copy()
    for col in available_stats:
        weighted[col] = weighted[col].fillna(0) * weighted["season_weight"]

    group_cols = ["player_id", "position"]
    if "player_name" in weighted.columns:
        group_cols.append("player_name")
    if "recent_team" in weighted.columns:
        group_cols.append("recent_team")

    agg_dict = {col: "sum" for col in available_stats}
    agg_dict["season_weight"] = "sum"
    proj = weighted.groupby(group_cols, as_index=False).agg(agg_dict)

    # Normalize by total weight
    for col in available_stats:
        proj[col] = (proj[col] / proj["season_weight"]).round(2)
    proj.drop(columns=["season_weight"], inplace=True)

    # Scale to 17-game season (seasonal data = 17 games)
    # Projections already represent season totals; convert to per-game for comparability
    games = 17
    proj["projected_season_points"] = calculate_fantasy_points_df(
        proj, scoring_format=scoring_format, output_col="_pts"
    )["_pts"]

    proj["projected_season_points"] = proj["projected_season_points"].round(1)
    proj["proj_season"] = target_season

    # Draft capital boost for rookies
    if historical_df is not None and not historical_df.empty:
        # Join on player_id = gsis_id to get draft_ovr
        hist = (
            historical_df[["gsis_id", "draft_ovr", "draft_year"]]
            .dropna(subset=["gsis_id"])
            .copy()
        )
        hist = hist.rename(columns={"gsis_id": "player_id"})
        # De-duplicate: keep latest draft entry per player
        hist = hist.sort_values("draft_year", ascending=False).drop_duplicates(
            subset="player_id"
        )

        proj = proj.merge(hist[["player_id", "draft_ovr"]], on="player_id", how="left")

        # Identify rookies: players only present in the most recent season of data
        all_player_seasons = seasonal_df.groupby("player_id")["season"].nunique()
        rookies = set(all_player_seasons[all_player_seasons == 1].index)

        # Apply boost only to rookies with draft capital info
        mask = proj["player_id"].isin(rookies) & proj["draft_ovr"].notna()
        if mask.any():
            proj.loc[mask, "projected_season_points"] = proj.loc[mask].apply(
                lambda r: round(
                    r["projected_season_points"]
                    * draft_capital_boost(r["draft_ovr"], r["position"]),
                    1,
                ),
                axis=1,
            )
            boosted_count = mask.sum()
            logger.info(f"Draft capital boost applied to {boosted_count} rookies")

        proj.drop(columns=["draft_ovr"], inplace=True, errors="ignore")

    # Rank overall and by position
    pos_filter = proj["position"].isin(["QB", "RB", "WR", "TE"])
    proj = proj[pos_filter].copy()
    proj["overall_rank"] = (
        proj["projected_season_points"]
        .rank(ascending=False, method="first")
        .astype(int)
    )
    proj["position_rank"] = (
        proj.groupby("position")["projected_season_points"]
        .rank(ascending=False, method="first")
        .astype(int)
    )

    proj = proj.sort_values("overall_rank").reset_index(drop=True)
    logger.info(
        f"Preseason projections generated: {len(proj)} players for {target_season}"
    )
    return proj
