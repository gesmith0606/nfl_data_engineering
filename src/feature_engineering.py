"""Game-level differential feature assembly from Silver team sources.

Transforms per-team-per-week Silver features into per-game rows with
home-away differential columns, plus labels from Bronze schedules.
This is the core data pipeline feeding XGBoost models.

Exports:
    assemble_game_features: Build game-level features for a single season.
    assemble_multiyear_features: Concatenate multiple seasons of game features.
    get_feature_columns: Return valid feature column names (no labels/identifiers).
    SILVER_TEAM_SOURCES: Mapping of source name to local subdirectory.
"""

import glob
import os
from typing import List, Optional

import pandas as pd

from config import LABEL_COLUMNS, SILVER_TEAM_LOCAL_DIRS, TEAM_DIVISIONS

# Base directories for local data
_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)))
SILVER_DIR = os.path.join(_BASE_DIR, "data", "silver")
BRONZE_DIR = os.path.join(_BASE_DIR, "data", "bronze")

# Re-export for downstream consumers
SILVER_TEAM_SOURCES = SILVER_TEAM_LOCAL_DIRS

# Columns that identify a row but are not features
_IDENTIFIER_COLUMNS = {
    "game_id", "season", "week", "game_type",
    "team_home", "team_away", "home_team", "away_team",
    "team", "is_home",
}

# Columns to exclude from differencing (non-numeric identifiers that may
# survive as numeric dtype)
_NON_DIFF_COLS = {
    "season", "week", "is_home",
}


def _read_latest_local(subdir: str, season: int) -> pd.DataFrame:
    """Read the latest Silver parquet file for a given subdirectory and season.

    Args:
        subdir: Relative path under data/silver/ (e.g. 'teams/pbp_metrics').
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
        DataFrame with game_id, season, week, home_team, away_team,
        home_score, away_score, result, spread_line, total_line, div_game.
    """
    pattern = os.path.join(BRONZE_DIR, "schedules", f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        return pd.DataFrame()
    df = pd.read_parquet(files[-1])

    # Filter to regular season
    df = df[df["game_type"] == "REG"].copy()

    keep_cols = [
        "game_id", "season", "week", "game_type",
        "home_team", "away_team", "home_score", "away_score",
        "result", "spread_line", "total_line",
    ]
    # Add div_game if present in schedules
    if "div_game" in df.columns:
        keep_cols.append("div_game")

    available = [c for c in keep_cols if c in df.columns]
    return df[available].copy()


def _assemble_team_features(season: int) -> pd.DataFrame:
    """Load and merge all Silver team sources for a season.

    Uses game_context as the base (has game_id, is_home, team, season, week),
    then left-joins each additional Silver source on [team, season, week].

    Args:
        season: NFL season year.

    Returns:
        Merged per-team-per-week DataFrame with all Silver columns.
    """
    # Start with game_context as base (has game_id and is_home)
    base = _read_latest_local("teams/game_context", season)
    if base.empty:
        return pd.DataFrame()

    # Join remaining sources
    for name, subdir in SILVER_TEAM_SOURCES.items():
        if name == "game_context":
            continue  # Already loaded as base
        df = _read_latest_local(subdir, season)
        if df.empty:
            continue
        base = base.merge(
            df, on=["team", "season", "week"], how="left",
            suffixes=("", f"__{name}"),
        )
        # Drop duplicate columns from join (suffixed copies)
        dup_cols = [c for c in base.columns if c.endswith(f"__{name}")]
        base = base.drop(columns=dup_cols)

    return base


def assemble_game_features(season: int) -> pd.DataFrame:
    """Build game-level differential features for a single season.

    Pipeline:
    1. Load all Silver team sources and merge per-team-per-week
    2. Split into home and away DataFrames
    3. Join on game_id to create game-level rows
    4. Compute home-away differentials for numeric columns
    5. Join Bronze schedules for labels (scores, spread, total)
    6. Filter to REG games only

    Args:
        season: NFL season year.

    Returns:
        DataFrame with one row per game, differential features, and labels.
    """
    # Step 1: Assemble per-team features
    team_df = _assemble_team_features(season)
    if team_df.empty:
        return pd.DataFrame()

    # Fill wins/losses with 0 where NaN (early season)
    for col in ["wins", "losses", "ties"]:
        if col in team_df.columns:
            team_df[col] = team_df[col].fillna(0)

    # Step 2: Split into home and away
    home = team_df[team_df["is_home"] == True].copy()  # noqa: E712
    away = team_df[team_df["is_home"] == False].copy()  # noqa: E712

    if home.empty or away.empty:
        return pd.DataFrame()

    # Step 3: Join home and away on game_id
    game_df = home.merge(
        away, on=["game_id", "season", "week"],
        suffixes=("_home", "_away"),
    )

    # Step 4: Identify numeric columns for differencing
    # Get columns that appear with both _home and _away suffixes
    home_cols = [c for c in game_df.columns if c.endswith("_home")]
    away_cols = [c for c in game_df.columns if c.endswith("_away")]

    home_base = {c[:-5] for c in home_cols}  # strip "_home"
    away_base = {c[:-5] for c in away_cols}  # strip "_away"
    common_base = home_base & away_base

    # Compute differentials for numeric columns only
    # Build all diff columns at once to avoid DataFrame fragmentation
    skip_bases = _NON_DIFF_COLS | {
        "team", "game_type", "is_home", "head_coach",
        "surface", "coaching_change",
    }
    diff_data = {}
    for col_base in sorted(common_base):
        if col_base in skip_bases:
            continue
        home_col = f"{col_base}_home"
        away_col = f"{col_base}_away"
        if game_df[home_col].dtype in ("float64", "int64", "float32", "int32"):
            diff_data[f"diff_{col_base}"] = (
                game_df[home_col].values - game_df[away_col].values
            )
    if diff_data:
        diff_df = pd.DataFrame(diff_data, index=game_df.index)
        game_df = pd.concat([game_df, diff_df], axis=1)

    # Step 5: Add non-differential context columns
    # Division game flag — computed into diff_data to avoid fragmentation
    if "team_home" in game_df.columns and "team_away" in game_df.columns:
        home_div = game_df["team_home"].map(TEAM_DIVISIONS)
        away_div = game_df["team_away"].map(TEAM_DIVISIONS)
        div_game_vals = (home_div == away_div).astype(int).values
    else:
        div_game_vals = pd.array([0] * len(game_df), dtype="int64")
    context_df = pd.DataFrame({"div_game": div_game_vals}, index=game_df.index)
    game_df = pd.concat([game_df, context_df], axis=1)

    # Step 6: Join Bronze schedules for labels
    schedules = _read_bronze_schedules(season)
    if not schedules.empty:
        # Keep only label columns from schedules (avoid duplicating existing cols)
        label_cols_from_sched = ["game_id", "home_score", "away_score",
                                 "result", "spread_line", "total_line"]
        if "div_game" in schedules.columns:
            label_cols_from_sched.append("div_game")

        avail_label_cols = [c for c in label_cols_from_sched if c in schedules.columns]
        sched_subset = schedules[avail_label_cols].copy()

        # Drop any existing label columns from game_df before merge
        existing_labels = [c for c in sched_subset.columns
                           if c in game_df.columns and c != "game_id"]
        game_df = game_df.drop(columns=existing_labels, errors="ignore")

        game_df = game_df.merge(sched_subset, on="game_id", how="inner")

    # Step 7: Compute derived labels and game_type in one batch to avoid fragmentation
    derived = {}
    if "home_score" in game_df.columns and "away_score" in game_df.columns:
        derived["actual_margin"] = game_df["home_score"].values - game_df["away_score"].values
        derived["actual_total"] = game_df["home_score"].values + game_df["away_score"].values

    if "game_type_home" in game_df.columns:
        derived["game_type"] = game_df["game_type_home"].values
    elif "game_type" not in game_df.columns:
        derived["game_type"] = "REG"

    if derived:
        game_df = pd.concat([game_df, pd.DataFrame(derived, index=game_df.index)], axis=1)

    # Filter to REG only and defragment
    game_df = game_df[game_df["game_type"] == "REG"].copy()

    return game_df


def get_feature_columns(game_df: pd.DataFrame) -> List[str]:
    """Return list of valid feature column names from an assembled game DataFrame.

    Only includes features that are knowable BEFORE the game starts:
    - Rolling/lagged stats (_roll3, _roll6, _std) — use prior-week data only
    - Pre-game context (weather, rest, dome, travel, coaching tenure)
    - Cumulative record (wins, losses, win_pct, division_rank)
    - Referee tendencies (season-level)

    Excludes same-week raw stats (e.g. off_epa_per_play for that game)
    which would constitute data leakage.

    Args:
        game_df: DataFrame from assemble_game_features().

    Returns:
        List of column names suitable for model training.
    """
    exclude = set(LABEL_COLUMNS) | _IDENTIFIER_COLUMNS

    # Also exclude team name columns with suffixes
    for suffix in ("_home", "_away"):
        exclude.add(f"team{suffix}")
        exclude.add(f"head_coach{suffix}")
        exclude.add(f"surface{suffix}")
        exclude.add(f"coaching_change{suffix}")
        exclude.add(f"game_type{suffix}")

    # Pre-game knowable context columns (not derived from game outcome)
    _PRE_GAME_CONTEXT = {
        "is_dome", "rest_advantage", "is_short_rest", "is_post_bye",
        "travel_miles", "tz_diff", "coaching_tenure", "div_game",
        "temperature", "wind_speed", "is_cold", "is_high_wind",
        "rest_days", "opponent_rest",
    }

    # Pre-game knowable cumulative columns (computed before the game)
    _PRE_GAME_CUMULATIVE = {
        "wins", "losses", "ties", "win_pct", "division_rank",
        "games_behind_division_leader", "ref_penalties_per_game",
        "backup_qb_start",
    }

    def _is_rolling(col: str) -> bool:
        """Check if column is a properly lagged rolling feature."""
        return "roll3" in col or "roll6" in col or "std" in col

    def _is_pre_game_context(col: str) -> bool:
        """Check if column is a pre-game knowable context feature."""
        base = col
        for suffix in ("_home", "_away"):
            if col.endswith(suffix):
                base = col[: -len(suffix)]
                break
        if base.startswith("diff_"):
            base = base[5:]
        return base in _PRE_GAME_CONTEXT or base in _PRE_GAME_CUMULATIVE

    feature_cols = []
    for col in game_df.columns:
        if col in exclude:
            continue
        if not game_df[col].dtype in ("float64", "int64", "float32", "int32", "bool"):
            continue

        if col.startswith("diff_"):
            # Only allow diffs of rolling features or pre-game data
            if _is_rolling(col) or _is_pre_game_context(col):
                feature_cols.append(col)
            continue

        if col.endswith("_home") or col.endswith("_away"):
            # Only allow pre-game context columns with suffixes
            if _is_pre_game_context(col):
                feature_cols.append(col)
            continue

        # Non-suffixed columns: only if pre-game or rolling
        if _is_rolling(col) or _is_pre_game_context(col):
            feature_cols.append(col)

    return sorted(feature_cols)


def assemble_multiyear_features(
    seasons: Optional[List[int]] = None,
) -> pd.DataFrame:
    """Assemble game features for multiple seasons and concatenate.

    Args:
        seasons: List of season years. Defaults to PREDICTION_SEASONS from config.

    Returns:
        Combined DataFrame with all seasons' game features.
    """
    if seasons is None:
        from config import PREDICTION_SEASONS
        seasons = PREDICTION_SEASONS

    frames = []
    for season in seasons:
        df = assemble_game_features(season)
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)
