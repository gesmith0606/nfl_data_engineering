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

import numpy as np
import pandas as pd

from config import (
    LABEL_COLUMNS,
    SILVER_PLAYER_LOCAL_DIRS,
    SILVER_TEAM_LOCAL_DIRS,
    TEAM_DIVISIONS,
)
from team_analytics import apply_team_rolling

# Base directories for local data
_BASE_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)))
SILVER_DIR = os.path.join(_BASE_DIR, "data", "silver")
BRONZE_DIR = os.path.join(_BASE_DIR, "data", "bronze")

# Re-export for downstream consumers
SILVER_TEAM_SOURCES = SILVER_TEAM_LOCAL_DIRS

# Columns that identify a row but are not features
_IDENTIFIER_COLUMNS = {
    "game_id",
    "season",
    "week",
    "game_type",
    "team_home",
    "team_away",
    "home_team",
    "away_team",
    "team",
    "is_home",
}

# Columns to exclude from differencing (non-numeric identifiers that may
# survive as numeric dtype)
_NON_DIFF_COLS = {
    "season",
    "week",
    "is_home",
}


def _read_latest_local(subdir: str, season: int) -> pd.DataFrame:
    """Read the latest Silver parquet file for a given subdirectory and season.

    Weekly transformations nest their output under week=W/ while season-
    scoped runs write directly under season=Y/ — both layouts are globbed.
    "Latest" is decided by the filename-embedded YYYYMMDD_HHMMSS timestamp
    (basename sort), never the path, so a week=9 directory cannot lexically
    outrank week=18.

    Args:
        subdir: Relative path under data/silver/ (e.g. 'teams/pbp_metrics').
        season: NFL season year.

    Returns:
        DataFrame from latest parquet file, or empty DataFrame if not found.
    """
    candidates = []
    for pattern in (
        os.path.join(SILVER_DIR, subdir, f"season={season}", "*.parquet"),
        os.path.join(SILVER_DIR, subdir, f"season={season}", "week=*", "*.parquet"),
    ):
        candidates.extend(glob.glob(pattern))
    if not candidates:
        return pd.DataFrame()
    return pd.read_parquet(max(candidates, key=os.path.basename))


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
        "game_id",
        "season",
        "week",
        "game_type",
        "home_team",
        "away_team",
        "home_score",
        "away_score",
        "result",
        "spread_line",
        "total_line",
    ]
    # Add div_game if present in schedules
    if "div_game" in df.columns:
        keep_cols.append("div_game")

    available = [c for c in keep_cols if c in df.columns]
    return df[available].copy()


def _compute_momentum_features(season: int) -> pd.DataFrame:
    """Compute game momentum/streak features from Bronze schedule results.

    Produces per-team-per-week momentum signals:
    - win_streak: signed consecutive win/loss counter (positive=winning, negative=losing)
    - ats_cover_sum3: rolling sum of ATS covers over last 3 games
    - ats_margin_avg3: rolling mean of ATS margin over last 3 games

    All features use shift(1) to prevent same-game leakage.

    Args:
        season: NFL season year.

    Returns:
        DataFrame with [game_id, season, week, team, win_streak, ats_cover_sum3, ats_margin_avg3].
    """
    sched = _read_bronze_schedules(season)
    if sched.empty:
        return pd.DataFrame()

    # Reshape to per-team rows: home and away perspectives
    home = sched[
        ["game_id", "season", "week", "home_team", "result", "spread_line"]
    ].copy()
    home = home.rename(columns={"home_team": "team"})
    home["won"] = (home["result"] > 0).astype(int)
    home["ats_cover"] = ((home["result"] - home["spread_line"]) > 0).astype(int)
    home["ats_margin"] = home["result"] - home["spread_line"]

    away = sched[
        ["game_id", "season", "week", "away_team", "result", "spread_line"]
    ].copy()
    away = away.rename(columns={"away_team": "team"})
    away["won"] = (away["result"] < 0).astype(int)  # away wins when result < 0
    away["ats_cover"] = ((-away["result"] + away["spread_line"]) > 0).astype(int)
    away["ats_margin"] = -away["result"] + away["spread_line"]

    combined = pd.concat([home, away], ignore_index=True)
    combined = combined.sort_values(["team", "season", "week"])

    # Compute win_streak: signed consecutive counter
    def _streak(won_series: pd.Series) -> pd.Series:
        """Compute signed streak: +N for consecutive wins, -N for consecutive losses."""
        streak = pd.Series(0, index=won_series.index, dtype=float)
        prev = 0.0
        for i, val in enumerate(won_series.values):
            if val == 1:
                prev = max(prev, 0) + 1
            else:
                prev = min(prev, 0) - 1
            streak.iloc[i] = prev
        return streak

    combined["win_streak_raw"] = combined.groupby(["team", "season"])["won"].transform(
        _streak
    )
    # shift(1) AFTER computing streak (Pitfall 6)
    combined["win_streak"] = combined.groupby(["team", "season"])[
        "win_streak_raw"
    ].transform(lambda s: s.shift(1))

    # ATS cover rolling sum (shift(1) inside transform)
    combined["ats_cover_sum3"] = combined.groupby(["team", "season"])[
        "ats_cover"
    ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).sum())

    # ATS margin rolling mean (shift(1) inside transform)
    combined["ats_margin_avg3"] = combined.groupby(["team", "season"])[
        "ats_margin"
    ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())

    return combined[
        [
            "game_id",
            "season",
            "week",
            "team",
            "win_streak",
            "ats_cover_sum3",
            "ats_margin_avg3",
        ]
    ].copy()


# Raw (same-week) player-aggregate stat columns computed by
# _compute_player_team_features(). These names deliberately never appear in
# get_feature_columns()'s allowlist -- only their apply_team_rolling()
# derivatives (_roll3/_roll6/_std) are pre-game knowable and get selected as
# model features. Mirrors teams/player_quality's construction exactly (see
# scripts/silver_player_quality_transformation.py::transform_season).
_PLAYER_TEAM_STAT_COLS = [
    "qb_dakota",
    "qb_cpoe",
    "qb_pressure_rate",
    "skill_snap_share_hhi",
    "skill_target_share_hhi",
    "skill_snap_participation_count",
    "wr_weighted_separation",
    "wr_weighted_yac_oe",
    "rb_weighted_ryoe",
    "rb_time_to_los",
]


def _herfindahl(shares: pd.Series) -> float:
    """Herfindahl-Hirschman concentration index of a share series.

    1/N (evenly split) is minimal concentration; 1.0 (one player has it all)
    is maximal. Shares are renormalized to sum to 1 before squaring so the
    index is well-defined regardless of the input's own normalization.

    Args:
        shares: Raw per-player share values (e.g. snap_pct) for one team-week.

    Returns:
        HHI in [0, 1], or 0.0 if all shares are zero/missing.
    """
    s = shares.fillna(0.0).clip(lower=0.0)
    total = s.sum()
    if total <= 0:
        return 0.0
    norm = s / total
    return float((norm**2).sum())


def _share_weighted_avg(group: pd.DataFrame, value_col: str, weight_col: str) -> float:
    """Share-weighted average of a value column within one team-week group.

    Args:
        group: Rows for one (team, season, week), one row per player.
        value_col: Column to average (e.g. an NGS metric).
        weight_col: Column to weight by (e.g. target_share or carry_share).

    Returns:
        Weighted average, or NaN if no rows have both a valid value and
        positive weight (real sparsity -- e.g. NGS qualification thresholds
        -- not a bug; see .planning/OPPORTUNITY_SCAN_2026_08_16.md).
    """
    if value_col not in group.columns or weight_col not in group.columns:
        return np.nan
    w = group[weight_col].fillna(0.0)
    v = group[value_col]
    mask = v.notna() & (w > 0)
    if not mask.any():
        return np.nan
    return float((v[mask] * w[mask]).sum() / w[mask].sum())


def _compute_player_team_features(season: int) -> pd.DataFrame:
    """Compute team-week player-aggregate features from repaired players/usage + players/advanced.

    Move #2 of the 2026-08-16 opportunity scan: the game ensemble has never
    read player-level Silver. Builds ~10 team-week raw aggregates from
    ``players/usage`` (usage shares, dakota) and ``players/advanced`` (NGS/PFR),
    joined on player_id/gsis_id (real ids, never name-only -- see
    knowledge-vault concepts/gated-experiment-coverage-check.md's join-key
    lesson). Idea groups:

    - QB trailing efficiency composite: starter's dakota, NGS CPOE, PFR
      pressure rate (starter = max pass attempts that team-week).
    - Skill-corps snap/target concentration (Herfindahl) + rotation depth
      (count of RB/WR/TE with snap_pct >= 0.30).
    - Weighted receiver separation / YAC-over-expected (NGS, target-share
      weighted across WR/TE).
    - Rushing-room efficiency (NGS rush-yards-over-expected/att and
      time-to-line-of-scrimmage, carry-share weighted across RB).

    Construction mirrors ``silver_player_quality_transformation.py`` exactly:
    raw values are SAME-WEEK actuals (fine -- they are never themselves
    exposed as a model feature), then ``apply_team_rolling`` shift(1)-lags
    them into ``_roll3``/``_roll6``/``_std`` columns, and only those pass
    ``get_feature_columns()``'s rolling-suffix allowlist. Does not duplicate
    existing ``teams/player_quality`` columns (qb_passing_epa, rb_weighted_epa,
    wr_te_weighted_epa, *_injury_impact, backup_qb_start).

    Args:
        season: NFL season year.

    Returns:
        DataFrame with [team, season, week] + _PLAYER_TEAM_STAT_COLS raw
        columns plus their _roll3/_roll6/_std derivatives. Empty DataFrame if
        players/usage Silver is unavailable for the season.
    """
    usage = _read_latest_local(SILVER_PLAYER_LOCAL_DIRS["usage"], season)
    if usage.empty:
        return pd.DataFrame()

    usage = usage.rename(columns={"recent_team": "team"})
    usage_cols = [
        "player_id",
        "team",
        "season",
        "week",
        "position",
        "attempts",
        "dakota",
        "snap_pct",
        "target_share",
        "carry_share",
    ]
    df = usage[[c for c in usage_cols if c in usage.columns]].copy()

    advanced = _read_latest_local(SILVER_PLAYER_LOCAL_DIRS["advanced"], season)
    adv_metric_cols = [
        "ngs_completion_percentage_above_expectation",
        "pfr_times_pressured_pct",
        "ngs_avg_separation",
        "ngs_avg_yac_above_expectation",
        "ngs_rush_yards_over_expected_per_att",
        "ngs_avg_time_to_los",
    ]
    if not advanced.empty:
        adv = advanced.rename(columns={"player_gsis_id": "player_id"})
        adv_cols = ["player_id", "season", "week"] + [
            c for c in adv_metric_cols if c in adv.columns
        ]
        df = df.merge(adv[adv_cols], on=["player_id", "season", "week"], how="left")
    for col in adv_metric_cols:
        if col not in df.columns:
            df[col] = np.nan

    team_weeks = df[["team", "season", "week"]].drop_duplicates()

    # --- QB trailing efficiency composite (starter = max attempts) ---
    qb = df[df["position"] == "QB"]
    if not qb.empty and "attempts" in qb.columns and qb["attempts"].notna().any():
        idx = qb.groupby(["team", "season", "week"])["attempts"].idxmax()
        qb_feats = qb.loc[
            idx,
            [
                "team",
                "season",
                "week",
                "dakota",
                "ngs_completion_percentage_above_expectation",
                "pfr_times_pressured_pct",
            ],
        ].rename(
            columns={
                "dakota": "qb_dakota",
                "ngs_completion_percentage_above_expectation": "qb_cpoe",
                "pfr_times_pressured_pct": "qb_pressure_rate",
            }
        )
    else:
        qb_feats = pd.DataFrame(
            columns=[
                "team",
                "season",
                "week",
                "qb_dakota",
                "qb_cpoe",
                "qb_pressure_rate",
            ]
        )

    # --- Skill-corps concentration/continuity (RB/WR/TE) ---
    skill = df[df["position"].isin(["RB", "WR", "TE"])]
    conc_rows = [
        {
            "team": team,
            "season": season_,
            "week": week,
            "skill_snap_share_hhi": _herfindahl(g["snap_pct"]),
            "skill_target_share_hhi": _herfindahl(g["target_share"]),
            "skill_snap_participation_count": int((g["snap_pct"] >= 0.30).sum()),
        }
        for (team, season_, week), g in skill.groupby(["team", "season", "week"])
    ]
    conc_feats = (
        pd.DataFrame(conc_rows)
        if conc_rows
        else pd.DataFrame(
            columns=[
                "team",
                "season",
                "week",
                "skill_snap_share_hhi",
                "skill_target_share_hhi",
                "skill_snap_participation_count",
            ]
        )
    )

    # --- Weighted receiver separation / YAC-OE (WR/TE, target_share-weighted) ---
    wrte = df[df["position"].isin(["WR", "TE"])]
    sep_rows = [
        {
            "team": team,
            "season": season_,
            "week": week,
            "wr_weighted_separation": _share_weighted_avg(
                g, "ngs_avg_separation", "target_share"
            ),
            "wr_weighted_yac_oe": _share_weighted_avg(
                g, "ngs_avg_yac_above_expectation", "target_share"
            ),
        }
        for (team, season_, week), g in wrte.groupby(["team", "season", "week"])
    ]
    sep_feats = (
        pd.DataFrame(sep_rows)
        if sep_rows
        else pd.DataFrame(
            columns=[
                "team",
                "season",
                "week",
                "wr_weighted_separation",
                "wr_weighted_yac_oe",
            ]
        )
    )

    # --- Rushing-room efficiency (RB, carry_share-weighted) ---
    rb = df[df["position"] == "RB"]
    rush_rows = [
        {
            "team": team,
            "season": season_,
            "week": week,
            "rb_weighted_ryoe": _share_weighted_avg(
                g, "ngs_rush_yards_over_expected_per_att", "carry_share"
            ),
            "rb_time_to_los": _share_weighted_avg(
                g, "ngs_avg_time_to_los", "carry_share"
            ),
        }
        for (team, season_, week), g in rb.groupby(["team", "season", "week"])
    ]
    rush_feats = (
        pd.DataFrame(rush_rows)
        if rush_rows
        else pd.DataFrame(
            columns=["team", "season", "week", "rb_weighted_ryoe", "rb_time_to_los"]
        )
    )

    result = team_weeks.copy()
    for feats in (qb_feats, conc_feats, sep_feats, rush_feats):
        result = result.merge(feats, on=["team", "season", "week"], how="left")

    for col in _PLAYER_TEAM_STAT_COLS:
        if col not in result.columns:
            result[col] = np.nan

    result = apply_team_rolling(result, _PLAYER_TEAM_STAT_COLS, windows=[3, 6])
    return result


def _assemble_team_features(
    season: int, include_player_features: bool = False
) -> pd.DataFrame:
    """Load and merge all Silver team sources for a season.

    Uses game_context as the base (has game_id, is_home, team, season, week),
    then left-joins each additional Silver source on [team, season, week].

    Args:
        season: NFL season year.
        include_player_features: If True, additionally merge the team-week
            player-aggregate features from ``_compute_player_team_features``
            (players/usage + players/advanced). Default False keeps the
            shipped 120-feature path byte-for-byte unchanged (opt-in, per
            .planning/ENSEMBLE_PLAYER_FEATURES_2026_08_16.md).

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
            df,
            on=["team", "season", "week"],
            how="left",
            suffixes=("", f"__{name}"),
        )
        # Drop duplicate columns from join (suffixed copies)
        dup_cols = [c for c in base.columns if c.endswith(f"__{name}")]
        base = base.drop(columns=dup_cols)

    if include_player_features:
        player_feats = _compute_player_team_features(season)
        if not player_feats.empty:
            base = base.merge(
                player_feats,
                on=["team", "season", "week"],
                how="left",
                suffixes=("", "__playerfeat"),
            )
            dup_cols = [c for c in base.columns if c.endswith("__playerfeat")]
            base = base.drop(columns=dup_cols)

    return base


def assemble_game_features(
    season: int, include_player_features: bool = False
) -> pd.DataFrame:
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
        include_player_features: If True, additionally assemble the
            players/usage + players/advanced team-aggregate features (opt-in;
            default False leaves the shipped 120-feature path unchanged).

    Returns:
        DataFrame with one row per game, differential features, and labels.
    """
    # Step 1: Assemble per-team features
    team_df = _assemble_team_features(
        season, include_player_features=include_player_features
    )
    if team_df.empty:
        return pd.DataFrame()

    # Fill wins/losses with 0 where NaN (early season)
    for col in ["wins", "losses", "ties"]:
        if col in team_df.columns:
            team_df[col] = team_df[col].fillna(0)

    # Step 1b: Merge momentum features (win_streak, ATS cover/margin)
    momentum = _compute_momentum_features(season)
    if not momentum.empty:
        team_df = team_df.merge(
            momentum,
            on=["team", "season", "week"],
            how="left",
            suffixes=("", "__momentum"),
        )
        # Drop any duplicate columns from merge
        dup_cols = [c for c in team_df.columns if c.endswith("__momentum")]
        team_df = team_df.drop(columns=dup_cols)

    # Step 2: Split into home and away
    home = team_df[team_df["is_home"] == True].copy()  # noqa: E712
    away = team_df[team_df["is_home"] == False].copy()  # noqa: E712

    if home.empty or away.empty:
        return pd.DataFrame()

    # Step 3: Join home and away on game_id
    game_df = home.merge(
        away,
        on=["game_id", "season", "week"],
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
        "team",
        "game_type",
        "is_home",
        "head_coach",
        "surface",
        "coaching_change",
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
        label_cols_from_sched = [
            "game_id",
            "home_score",
            "away_score",
            "result",
            "spread_line",
            "total_line",
        ]
        if "div_game" in schedules.columns:
            label_cols_from_sched.append("div_game")

        avail_label_cols = [c for c in label_cols_from_sched if c in schedules.columns]
        sched_subset = schedules[avail_label_cols].copy()

        # Drop any existing label columns from game_df before merge
        existing_labels = [
            c for c in sched_subset.columns if c in game_df.columns and c != "game_id"
        ]
        game_df = game_df.drop(columns=existing_labels, errors="ignore")

        game_df = game_df.merge(sched_subset, on="game_id", how="inner")

    # Step 7: Compute derived labels and game_type in one batch to avoid fragmentation
    derived = {}
    if "home_score" in game_df.columns and "away_score" in game_df.columns:
        derived["actual_margin"] = (
            game_df["home_score"].values - game_df["away_score"].values
        )
        derived["actual_total"] = (
            game_df["home_score"].values + game_df["away_score"].values
        )

    if "game_type_home" in game_df.columns:
        derived["game_type"] = game_df["game_type_home"].values
    elif "game_type" not in game_df.columns:
        derived["game_type"] = "REG"

    if derived:
        game_df = pd.concat(
            [game_df, pd.DataFrame(derived, index=game_df.index)], axis=1
        )

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
        "is_dome",
        "rest_advantage",
        "is_short_rest",
        "is_post_bye",
        "travel_miles",
        "tz_diff",
        "coaching_tenure",
        "div_game",
        "temperature",
        "wind_speed",
        "is_cold",
        "is_high_wind",
        "rest_days",
        "opponent_rest",
        # Market data -- pre-game knowable only (D-05)
        # RETROSPECTIVE features (spread_shift, total_shift, spread_move_abs,
        # total_move_abs, spread_magnitude, total_magnitude, crosses_key_spread,
        # crosses_key_total, closing_spread, closing_total, is_steam_move) are
        # NOT listed here and are automatically excluded by get_feature_columns().
        # See D-06/D-08.
        "opening_spread",
        "opening_total",
    }

    # Pre-game knowable cumulative columns (computed before the game)
    _PRE_GAME_CUMULATIVE = {
        "wins",
        "losses",
        "ties",
        "win_pct",
        "division_rank",
        "games_behind_division_leader",
        "ref_penalties_per_game",
        "backup_qb_start",
        "win_streak",
        "ats_cover_sum3",
        "ats_margin_avg3",
    }

    def _is_rolling(col: str) -> bool:
        """Check if column is a properly lagged rolling feature."""
        return "roll3" in col or "roll6" in col or "std" in col or "ewm3" in col

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
    include_player_features: bool = False,
) -> pd.DataFrame:
    """Assemble game features for multiple seasons and concatenate.

    Args:
        seasons: List of season years. Defaults to PREDICTION_SEASONS from config.
        include_player_features: If True, assemble each season with the
            players/usage + players/advanced team-aggregate features (opt-in;
            default False leaves the shipped 120-feature path unchanged).

    Returns:
        Combined DataFrame with all seasons' game features.
    """
    if seasons is None:
        from config import PREDICTION_SEASONS

        seasons = PREDICTION_SEASONS

    frames = []
    for season in seasons:
        df = assemble_game_features(
            season, include_player_features=include_player_features
        )
        if not df.empty:
            frames.append(df)

    if not frames:
        return pd.DataFrame()

    return pd.concat(frames, ignore_index=True)
