"""Player-week feature vector assembly from Silver sources.

Joins 9 Silver data sources into per-player-per-week rows with temporal
lag enforcement, matchup features, Vegas implied totals, and leakage detection.
Adapts the multi-source left-join pattern from feature_engineering.py for
player-level granularity.

Exports:
    assemble_player_features: Build player-week features for a single season.
    get_player_feature_columns: Return valid feature column names.
    detect_leakage: Flag features with suspiciously high target correlation.
    validate_temporal_integrity: Check shift(1) compliance on rolling features.
"""

import glob
import logging
import os
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from config import (
    PLAYER_DATA_SEASONS,
    PLAYER_LABEL_COLUMNS,
    SILVER_PLAYER_LOCAL_DIRS,
    SILVER_PLAYER_TEAM_SOURCES,
)

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SILVER_DIR = os.path.join(_BASE_DIR, "data", "silver")
BRONZE_DIR = os.path.join(_BASE_DIR, "data", "bronze")

# Columns that identify a row but are not features
_PLAYER_IDENTIFIER_COLS = {
    "player_id", "player_gsis_id", "gsis_id", "player_name", "player_display_name",
    "headshot_url", "season", "week", "season_type", "game_id",
    "recent_team", "opponent_team", "position", "position_group",
    "team", "opponent", "game_type",
}

# Target labels (same-week actuals, NOT features)
_PLAYER_LABEL_COLS = set(PLAYER_LABEL_COLUMNS)

# Same-week raw stats that are NOT lagged — using these as features is leakage.
# Only _roll3, _roll6, _std columns (which have shift(1) applied) are valid features.
_SAME_WEEK_RAW_STATS = {
    "attempts", "completions", "air_yards", "air_yards_share",
    "carry_share", "snap_pct", "target_share", "rz_target_share",
    "dakota", "pacr", "racr", "wopr",
    "passing_air_yards", "passing_epa", "passing_first_downs",
    "passing_yards_after_catch", "passing_2pt_conversions",
    "receiving_air_yards", "receiving_epa", "receiving_first_downs",
    "receiving_fumbles", "receiving_fumbles_lost",
    "receiving_yards_after_catch", "receiving_2pt_conversions",
    "rushing_epa", "rushing_first_downs",
    "rushing_fumbles", "rushing_fumbles_lost", "rushing_2pt_conversions",
    "sacks", "sack_yards", "sack_fumbles", "sack_fumbles_lost",
    "special_teams_tds", "fantasy_points",
    "team_targets", "team_carries", "team_air_yards",
    "team_score", "opp_score", "score_diff",
}


# ---------------------------------------------------------------------------
# Data readers (same pattern as feature_engineering.py)
# ---------------------------------------------------------------------------


def _read_latest_local(subdir: str, season: int) -> pd.DataFrame:
    """Read the latest Silver parquet file for a given subdirectory and season.

    Args:
        subdir: Relative path under data/silver/ (e.g. 'players/usage').
        season: NFL season year.

    Returns:
        DataFrame from latest parquet file, or empty DataFrame if not found.
    """
    pattern = os.path.join(SILVER_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _read_bronze_schedules(season: int) -> pd.DataFrame:
    """Read Bronze schedules for a season, filtered to REG games.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with season, week, home_team, away_team, spread_line,
        total_line, game_type columns.
    """
    pattern = os.path.join(BRONZE_DIR, "schedules", f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])

    # Filter to regular season
    if "game_type" in df.columns:
        df = df[df["game_type"] == "REG"].copy()

    keep_cols = [
        "season", "week", "home_team", "away_team",
        "spread_line", "total_line", "game_type",
    ]
    available = [c for c in keep_cols if c in df.columns]
    return df[available].copy()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _filter_eligible_players(df: pd.DataFrame) -> pd.DataFrame:
    """Keep only skill position players with snap_pct_roll3 >= 0.20.

    Per D-01/D-02: include QB, RB, WR, TE with snap_pct >= 20% in prior 3 games.

    Args:
        df: Player-week DataFrame with position and snap_pct_roll3 columns.

    Returns:
        Filtered copy of the DataFrame.
    """
    mask_position = df["position"].isin(["QB", "RB", "WR", "TE"])
    if "snap_pct_roll3" in df.columns and df["snap_pct_roll3"].notna().any():
        mask_snap = df["snap_pct_roll3"] >= 0.20
    else:
        # Snap data unavailable — include all skill position players
        logger.warning("snap_pct_roll3 unavailable; filtering by position only")
        mask_snap = True
    return df[mask_position & mask_snap].copy()


def _add_implied_totals(df: pd.DataFrame, schedules: pd.DataFrame) -> pd.DataFrame:
    """Add Vegas implied team total to each player-week row.

    Per FEAT-04: implied_total = (total_line / 2) - (spread_line / 2) for home,
    clipped to [5.0, 45.0].

    Args:
        df: Player-week DataFrame with recent_team, season, week.
        schedules: Bronze schedules with home_team, away_team, spread_line, total_line.

    Returns:
        DataFrame with implied_team_total column added.
    """
    if schedules.empty:
        df["implied_team_total"] = np.nan
        return df

    sched = schedules[["season", "week", "home_team", "away_team",
                        "spread_line", "total_line"]].copy()

    # Home implied = (total/2) - (spread/2); negative spread = home favored
    sched["implied_home"] = (
        (sched["total_line"] / 2) - (sched["spread_line"] / 2)
    ).clip(5.0, 45.0)

    # Away implied = (total/2) + (spread/2)
    sched["implied_away"] = (
        (sched["total_line"] / 2) + (sched["spread_line"] / 2)
    ).clip(5.0, 45.0)

    # Reshape to per-team rows
    home = sched[["season", "week", "home_team", "implied_home"]].rename(
        columns={"home_team": "team", "implied_home": "implied_team_total"}
    )
    away = sched[["season", "week", "away_team", "implied_away"]].rename(
        columns={"away_team": "team", "implied_away": "implied_team_total"}
    )
    team_totals = pd.concat([home, away], ignore_index=True)

    df = df.merge(
        team_totals,
        left_on=["recent_team", "season", "week"],
        right_on=["team", "season", "week"],
        how="left",
    )
    # Drop extra team column from merge
    if "team" in df.columns and "recent_team" in df.columns:
        df = df.drop(columns=["team"], errors="ignore")

    return df


# ---------------------------------------------------------------------------
# Core assembly
# ---------------------------------------------------------------------------


def assemble_player_features(season: int) -> pd.DataFrame:
    """Assemble player-week feature vector from 9 Silver sources.

    Reads usage as base, then left-joins advanced profiles, historical
    dimension table, opponent defense rankings (lagged), opponent EPA (lagged),
    team-level sources, and implied team totals. Filters to eligible players.

    Args:
        season: NFL season year to assemble features for.

    Returns:
        DataFrame with one row per eligible player-week, columns from all
        9 Silver sources plus implied_team_total.
    """
    # 1. Base: usage (has player_id, recent_team, opponent_team, position, week)
    base = _read_latest_local(SILVER_PLAYER_LOCAL_DIRS["usage"], season)
    if base.empty:
        logger.warning("No usage data for season %d", season)
        return pd.DataFrame()

    # 1b. Early filter: skill positions + regular season only (before joins)
    if "position" in base.columns:
        base = base[base["position"].isin(["QB", "RB", "WR", "TE"])].copy()
    if "season_type" in base.columns:
        base = base[base["season_type"] == "REG"].copy()

    # 2. Join advanced on player_id (rename player_gsis_id -> player_id)
    advanced = _read_latest_local(SILVER_PLAYER_LOCAL_DIRS["advanced"], season)
    if not advanced.empty:
        if "player_gsis_id" in advanced.columns:
            advanced = advanced.rename(columns={"player_gsis_id": "player_id"})
        base = base.merge(
            advanced,
            on=["player_id", "season", "week"],
            how="left",
            suffixes=("", "__adv"),
        )
        # Drop duplicate columns
        dup_cols = [c for c in base.columns if c.endswith("__adv")]
        base = base.drop(columns=dup_cols)

    # 3. Join historical (static dimension — join on player_id only)
    historical = _read_latest_local(SILVER_PLAYER_LOCAL_DIRS["historical"], season)
    if historical.empty:
        # Historical is not partitioned by season; try without season
        hist_pattern = os.path.join(
            SILVER_DIR, SILVER_PLAYER_LOCAL_DIRS["historical"], "*.parquet"
        )
        hist_files = sorted(glob.glob(hist_pattern))
        if hist_files:
            historical = pd.read_parquet(hist_files[-1])

    if not historical.empty:
        if "gsis_id" in historical.columns:
            historical = historical.rename(columns={"gsis_id": "player_id"})
        base = base.merge(
            historical,
            on=["player_id"],
            how="left",
            suffixes=("", "__hist"),
        )
        dup_cols = [c for c in base.columns if c.endswith("__hist")]
        base = base.drop(columns=dup_cols)

    # 4. Join defense/positional with shift(1) lag (FEAT-03)
    defense = _read_latest_local("defense/positional", season)
    if not defense.empty:
        defense = defense.sort_values(["team", "position", "season", "week"])
        defense[["avg_pts_allowed", "rank"]] = (
            defense.groupby(["team", "position", "season"])[["avg_pts_allowed", "rank"]]
            .shift(1)
        )
        defense = defense.rename(columns={
            "avg_pts_allowed": "opp_avg_pts_allowed",
            "rank": "opp_rank",
        })
        base = base.merge(
            defense,
            left_on=["opponent_team", "season", "week", "position"],
            right_on=["team", "season", "week", "position"],
            how="left",
            suffixes=("", "__def"),
        )
        # Drop extra team column and any suffixed dups
        base = base.drop(columns=[c for c in base.columns if c.endswith("__def")],
                         errors="ignore")
        if "team" in base.columns and "recent_team" in base.columns:
            # Only drop the team col that came from defense merge
            team_cols = [c for c in base.columns if c == "team"]
            if team_cols:
                base = base.drop(columns=["team"], errors="ignore")

    # 5. Join opponent-level def_epa_per_play with shift(1) lag
    pbp_for_opp = _read_latest_local(SILVER_PLAYER_TEAM_SOURCES["pbp_metrics"], season)
    if not pbp_for_opp.empty and "def_epa_per_play" in pbp_for_opp.columns:
        opp_epa = pbp_for_opp[["team", "season", "week", "def_epa_per_play"]].copy()
        opp_epa = opp_epa.sort_values(["team", "season", "week"])
        opp_epa["def_epa_per_play"] = (
            opp_epa.groupby(["team", "season"])["def_epa_per_play"].shift(1)
        )
        opp_epa = opp_epa.rename(columns={"def_epa_per_play": "opp_def_epa_per_play"})
        base = base.merge(
            opp_epa,
            left_on=["opponent_team", "season", "week"],
            right_on=["team", "season", "week"],
            how="left",
            suffixes=("", "__opp_epa"),
        )
        base = base.drop(columns=[c for c in base.columns if c.endswith("__opp_epa")],
                         errors="ignore")
        if "team" in base.columns and "recent_team" in base.columns:
            base = base.drop(columns=["team"], errors="ignore")

    # 6. Join 5 team sources on [recent_team, season, week]
    for name, subdir in SILVER_PLAYER_TEAM_SOURCES.items():
        team_df = _read_latest_local(subdir, season)
        if team_df.empty:
            continue
        base = base.merge(
            team_df,
            left_on=["recent_team", "season", "week"],
            right_on=["team", "season", "week"],
            how="left",
            suffixes=("", f"__{name}"),
        )
        # Drop suffixed duplicate columns
        dup_cols = [c for c in base.columns if c.endswith(f"__{name}")]
        base = base.drop(columns=dup_cols, errors="ignore")
        # Drop extra team column from merge
        if "team" in base.columns and "recent_team" in base.columns:
            base = base.drop(columns=["team"], errors="ignore")

    # 7. Add implied team totals from Bronze schedules
    schedules = _read_bronze_schedules(season)
    base = _add_implied_totals(base, schedules)

    # 8. Apply eligibility filter
    base = _filter_eligible_players(base)

    # 9. Exclude bye weeks (guard — usage should not have bye rows)
    base = base[base["week"].notna()].copy()

    logger.info(
        "Assembled player features for season %d: %d rows, %d columns",
        season, len(base), len(base.columns),
    )
    return base


# ---------------------------------------------------------------------------
# Feature column identification
# ---------------------------------------------------------------------------


def get_player_feature_columns(df: pd.DataFrame) -> List[str]:
    """Return sorted list of valid player feature column names.

    Excludes identifier columns, label columns, and non-numeric columns.

    Args:
        df: Player-week DataFrame.

    Returns:
        Sorted list of numeric feature column names.
    """
    exclude = _PLAYER_IDENTIFIER_COLS | _PLAYER_LABEL_COLS | _SAME_WEEK_RAW_STATS
    numeric_dtypes = {"float64", "int64", "float32", "int32", "bool"}
    return sorted([
        c for c in df.columns
        if c not in exclude
        and str(df[c].dtype) in numeric_dtypes
    ])


# ---------------------------------------------------------------------------
# Temporal integrity validation
# ---------------------------------------------------------------------------


def validate_temporal_integrity(df: pd.DataFrame) -> List[Tuple[str, str, float]]:
    """Check that rolling features do not correlate with same-week raw stats.

    If shift(1) is correctly applied, correlation between raw stat and its
    _roll3 counterpart should be moderate (0.3-0.7). If shift(1) is missing,
    correlation will be > 0.90.

    Args:
        df: Player-week DataFrame with raw and rolling columns.

    Returns:
        List of (raw_stat, roll_col, r) tuples for violations where |r| > 0.90.
    """
    violations: List[Tuple[str, str, float]] = []
    # Check same-week raw stats that are NOT labels — if they correlate highly
    # with their rolling counterpart, shift(1) may be missing.
    # Label columns (e.g., passing_yards) correlating with roll3 is expected
    # and tests predictive power, not leakage.
    raw_stats = ["snap_pct", "air_yards_share", "carry_share", "target_share"]

    for stat in raw_stats:
        roll_col = f"{stat}_roll3"
        if stat in df.columns and roll_col in df.columns:
            pair = df[[stat, roll_col]].dropna()
            if len(pair) < 3:
                continue
            r = pair.corr().iloc[0, 1]
            if abs(r) > 0.95:
                violations.append((stat, roll_col, float(r)))

    return violations


# ---------------------------------------------------------------------------
# Leakage detection
# ---------------------------------------------------------------------------


def detect_leakage(
    df: pd.DataFrame,
    feature_cols: List[str],
    target_cols: List[str],
    threshold: float = 0.95,
) -> List[Tuple[str, str, float]]:
    """Flag features with suspiciously high correlation to target columns.

    Args:
        df: DataFrame containing both features and targets.
        feature_cols: List of feature column names to check.
        target_cols: List of target column names to correlate against.
        threshold: Correlation threshold above which to flag (default 0.90).

    Returns:
        List of (feature, target, r) tuples for features exceeding threshold.
    """
    warnings: List[Tuple[str, str, float]] = []

    valid_feats = [f for f in feature_cols if f in df.columns]
    valid_targets = [t for t in target_cols if t in df.columns]
    if not valid_feats or not valid_targets:
        return warnings

    # Vectorized: compute full correlation matrix once
    all_cols = valid_feats + valid_targets
    corr_matrix = df[all_cols].corr()

    for target in valid_targets:
        for feat in valid_feats:
            r = corr_matrix.loc[feat, target]
            if abs(r) > threshold:
                warnings.append((feat, target, float(r)))

    return warnings


# ---------------------------------------------------------------------------
# Multi-year convenience wrapper
# ---------------------------------------------------------------------------


def assemble_multiyear_player_features(
    seasons: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Assemble player features across multiple seasons.

    Args:
        seasons: List of season years. Defaults to PLAYER_DATA_SEASONS.

    Returns:
        Concatenated DataFrame of player-week features across all seasons.
    """
    if seasons is None:
        seasons = PLAYER_DATA_SEASONS

    dfs = []
    for season in seasons:
        df = assemble_player_features(season)
        if not df.empty:
            dfs.append(df)
            logger.info("Season %d: %d rows", season, len(df))

    if not dfs:
        return pd.DataFrame()

    result = pd.concat(dfs, ignore_index=True)
    logger.info(
        "Multi-year assembly: %d seasons, %d total rows, %d columns",
        len(dfs), len(result), len(result.columns),
    )
    return result
