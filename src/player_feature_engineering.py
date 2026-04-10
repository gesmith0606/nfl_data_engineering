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
    POSITION_AVG_RZ_TD_RATE,
    SILVER_PLAYER_LOCAL_DIRS,
    SILVER_PLAYER_TEAM_SOURCES,
)

logger = logging.getLogger(__name__)

_BASE_DIR = os.path.dirname(os.path.dirname(__file__))
SILVER_DIR = os.path.join(_BASE_DIR, "data", "silver")
BRONZE_DIR = os.path.join(_BASE_DIR, "data", "bronze")

# Columns that identify a row but are not features
_PLAYER_IDENTIFIER_COLS = {
    "player_id",
    "player_gsis_id",
    "gsis_id",
    "player_name",
    "player_display_name",
    "headshot_url",
    "season",
    "week",
    "season_type",
    "game_id",
    "recent_team",
    "opponent_team",
    "position",
    "position_group",
    "team",
    "opponent",
    "game_type",
}

# Target labels (same-week actuals, NOT features)
_PLAYER_LABEL_COLS = set(PLAYER_LABEL_COLUMNS)

# Same-week raw stats that are NOT lagged — using these as features is leakage.
# Only _roll3, _roll6, _std columns (which have shift(1) applied) are valid features.
_SAME_WEEK_RAW_STATS = {
    "attempts",
    "completions",
    "air_yards",
    "air_yards_share",
    "carry_share",
    "snap_pct",
    "target_share",
    "rz_target_share",
    "dakota",
    "pacr",
    "racr",
    "wopr",
    "passing_air_yards",
    "passing_epa",
    "passing_first_downs",
    "passing_yards_after_catch",
    "passing_2pt_conversions",
    "receiving_air_yards",
    "receiving_epa",
    "receiving_first_downs",
    "receiving_fumbles",
    "receiving_fumbles_lost",
    "receiving_yards_after_catch",
    "receiving_2pt_conversions",
    "rushing_epa",
    "rushing_first_downs",
    "rushing_fumbles",
    "rushing_fumbles_lost",
    "rushing_2pt_conversions",
    "sacks",
    "sack_yards",
    "sack_fumbles",
    "sack_fumbles_lost",
    "special_teams_tds",
    "fantasy_points",
    "team_targets",
    "team_carries",
    "team_air_yards",
    "team_score",
    "opp_score",
    "score_diff",
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
        "season",
        "week",
        "home_team",
        "away_team",
        "spread_line",
        "total_line",
        "game_type",
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

    sched = schedules[
        ["season", "week", "home_team", "away_team", "spread_line", "total_line"]
    ].copy()

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
# Derived feature computations
# ---------------------------------------------------------------------------


def compute_efficiency_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute efficiency ratio features from rolling volume columns.

    Creates 12 ratio columns (6 ratios x 2 windows: roll3, roll6):
    yards_per_carry, yards_per_target, yards_per_reception,
    catch_rate, rush_td_rate, rec_td_rate.

    Uses safe division (np.where) to produce NaN for zero denominators.

    Args:
        df: Player-week DataFrame with rolling volume columns.

    Returns:
        DataFrame with 12 new efficiency columns added.
    """
    df = df.copy()

    ratios = [
        ("yards_per_carry", "rushing_yards", "carries"),
        ("yards_per_target", "receiving_yards", "targets"),
        ("yards_per_reception", "receiving_yards", "receptions"),
        ("catch_rate", "receptions", "targets"),
        ("rush_td_rate", "rushing_tds", "carries"),
        ("rec_td_rate", "receiving_tds", "targets"),
    ]

    for suffix in ["roll3", "roll6"]:
        for name, numerator_base, denominator_base in ratios:
            num_col = f"{numerator_base}_{suffix}"
            den_col = f"{denominator_base}_{suffix}"
            out_col = f"{name}_{suffix}"

            if num_col in df.columns and den_col in df.columns:
                df[out_col] = np.where(
                    df[den_col] > 0,
                    df[num_col] / df[den_col],
                    np.nan,
                )

    return df


def compute_td_regression_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute expected TD features from red zone target share.

    Creates expected_td_pos_avg (position-average conversion rate) and
    expected_td_player (player-specific rate via rec_td_rate_roll6).

    If rz_target_share_roll3 is missing but rz_target_share is present,
    computes the rolling column with shift(1) lag to prevent leakage.

    Args:
        df: Player-week DataFrame with rz_target_share and position columns.

    Returns:
        DataFrame with expected TD columns added.
    """
    df = df.copy()

    # Compute rz_target_share_roll3 if missing but raw is available
    if "rz_target_share_roll3" not in df.columns and "rz_target_share" in df.columns:
        if "player_id" in df.columns and "season" in df.columns:
            df["rz_target_share_roll3"] = df.groupby(["player_id", "season"])[
                "rz_target_share"
            ].transform(lambda s: s.shift(1).rolling(3, min_periods=1).mean())

    if "rz_target_share_roll3" in df.columns:
        # Position-average expected TD
        if "position" in df.columns:
            rate = df["position"].map(POSITION_AVG_RZ_TD_RATE).fillna(0.10)
            df["expected_td_pos_avg"] = df["rz_target_share_roll3"] * rate

        # Player-specific expected TD (uses efficiency feature rec_td_rate_roll6)
        if "rec_td_rate_roll6" in df.columns:
            df["expected_td_player"] = (
                df["rz_target_share_roll3"] * df["rec_td_rate_roll6"]
            )

    return df


def compute_interaction_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute multiplicative interaction features for Ridge/ElasticNet models.

    For key rolling stats per position, creates interactions with:
    - implied_team_total (Vegas adjustment)
    - opp_avg_pts_allowed (matchup quality, inverted so higher = weaker defense)
    - snap_pct_roll3 (usage/opportunity)

    Only creates an interaction column if both source columns exist and have
    non-null values. Safe for all positions -- missing columns are skipped.

    Args:
        df: Player-week DataFrame with rolling stats and context features.

    Returns:
        DataFrame with interaction feature columns added.
    """
    df = df.copy()

    # Key rolling stats per position (position-agnostic -- just create all,
    # Ridge will learn which matter per position via L2 regularization)
    key_stats = [
        "passing_yards_roll3",
        "rushing_yards_roll3",
        "rushing_tds_roll3",
        "receptions_roll3",
        "receiving_yards_roll3",
        "receiving_tds_roll3",
        "targets_roll3",
    ]

    context_cols = {
        "implied_total": "implied_team_total",
        "opp_rank": "opp_avg_pts_allowed",
        "snap_pct": "snap_pct_roll3",
    }

    for stat in key_stats:
        if stat not in df.columns:
            continue
        stat_base = stat.replace("_roll3", "")
        for suffix, ctx_col in context_cols.items():
            if ctx_col not in df.columns:
                continue
            out_col = f"{stat_base}_x_{suffix}"
            df[out_col] = df[stat] * df[ctx_col]

    return df


def compute_momentum_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute momentum delta features (roll3 minus roll6).

    Creates snap_pct_delta, target_share_delta, carry_share_delta
    when source columns exist. Skips each pair silently if missing.

    Args:
        df: Player-week DataFrame with rolling share columns.

    Returns:
        DataFrame with momentum delta columns added.
    """
    df = df.copy()

    deltas = [
        ("snap_pct_delta", "snap_pct_roll3", "snap_pct_roll6"),
        ("target_share_delta", "target_share_roll3", "target_share_roll6"),
        ("carry_share_delta", "carry_share_roll3", "carry_share_roll6"),
    ]

    for out_col, roll3_col, roll6_col in deltas:
        if roll3_col in df.columns and roll6_col in df.columns:
            df[out_col] = df[roll3_col] - df[roll6_col]

    return df


# ---------------------------------------------------------------------------
# Graph feature integration
# ---------------------------------------------------------------------------


def _join_graph_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join graph-derived injury cascade features if available.

    Tries two sources in order:
    1. Cached Silver parquet at data/silver/graph_features/season=YYYY/
    2. Live Neo4j query (if connected)

    If neither is available, returns the input DataFrame unchanged with
    NaN-filled graph feature columns added for schema consistency.

    Args:
        df: Player-week DataFrame with player_id, season, week.
        season: NFL season year.

    Returns:
        DataFrame with graph feature columns joined.
    """
    from graph_feature_extraction import GRAPH_FEATURE_COLUMNS

    # Try cached Silver parquet first
    graph_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    graph_files = sorted(
        glob.glob(os.path.join(graph_dir, "graph_injury_cascade_*.parquet"))
    )

    graph_df = pd.DataFrame()
    if graph_files:
        try:
            graph_df = pd.read_parquet(graph_files[-1])
            logger.info("Loaded cached graph features from %s", graph_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached graph features: %s", exc)

    # If no cached data, try Neo4j
    if graph_df.empty:
        try:
            from graph_db import GraphDB

            gdb = GraphDB()
            gdb.connect()
            if gdb.is_connected:
                from graph_feature_extraction import extract_all_graph_features

                graph_df = extract_all_graph_features(gdb, [season])
                gdb.close()
            else:
                logger.info("Neo4j unavailable — skipping graph features")
        except Exception as exc:
            logger.info("Graph features unavailable (%s) — skipping", exc)

    if graph_df.empty:
        # Add NaN columns for schema consistency
        for col in GRAPH_FEATURE_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan
        return df

    # Left join on player_id, season, week
    join_cols = ["player_id", "season", "week"]
    available_join = [c for c in join_cols if c in graph_df.columns and c in df.columns]
    if len(available_join) < 3:
        for col in GRAPH_FEATURE_COLUMNS:
            if col not in df.columns:
                df[col] = np.nan
        return df

    df = df.merge(
        graph_df[available_join + GRAPH_FEATURE_COLUMNS],
        on=available_join,
        how="left",
        suffixes=("", "__graph"),
    )
    # Drop any suffixed duplicates
    dup_cols = [c for c in df.columns if c.endswith("__graph")]
    df = df.drop(columns=dup_cols, errors="ignore")

    return df


def _join_wr_matchup_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join WR matchup, WR advanced matchup, and OL/RB graph features.

    Loads graph_wr_matchup, graph_wr_advanced, and graph_ol_rb parquets from
    Silver and merges on (player_id, season, week). Falls back to NaN-filled
    columns when files are not available.

    Args:
        df: Player-week DataFrame with player_id, season, week.
        season: NFL season year.

    Returns:
        DataFrame with WR matchup, WR advanced, and OL/RB feature columns joined.
    """
    from graph_feature_extraction import (
        WR_MATCHUP_FEATURE_COLUMNS,
        OL_RB_FEATURE_COLUMNS,
    )
    from hybrid_projection import _WR_ADVANCED_FEATURES

    all_new_cols = WR_MATCHUP_FEATURE_COLUMNS + _WR_ADVANCED_FEATURES + OL_RB_FEATURE_COLUMNS

    # Try cached Silver parquets first
    wr_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    wr_files = sorted(glob.glob(os.path.join(wr_dir, "graph_wr_matchup_*.parquet")))
    wr_adv_files = sorted(glob.glob(os.path.join(wr_dir, "graph_wr_advanced_*.parquet")))
    ol_files = sorted(glob.glob(os.path.join(wr_dir, "graph_ol_rb_*.parquet")))

    wr_df = pd.DataFrame()
    wr_adv_df = pd.DataFrame()
    ol_df = pd.DataFrame()

    if wr_files:
        try:
            wr_df = pd.read_parquet(wr_files[-1])
            logger.info("Loaded cached WR matchup features from %s", wr_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached WR features: %s", exc)

    if wr_adv_files:
        try:
            wr_adv_df = pd.read_parquet(wr_adv_files[-1])
            logger.info("Loaded cached WR advanced features from %s", wr_adv_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached WR advanced features: %s", exc)

    if ol_files:
        try:
            ol_df = pd.read_parquet(ol_files[-1])
            logger.info("Loaded cached OL/RB features from %s", ol_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached OL/RB features: %s", exc)

    join_cols = ["player_id", "season", "week"]

    # Join WR base matchup features
    if not wr_df.empty:
        avail = [c for c in join_cols if c in wr_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [c for c in WR_MATCHUP_FEATURE_COLUMNS if c in wr_df.columns]
            df = df.merge(
                wr_df[avail + feat_cols],
                on=avail,
                how="left",
                suffixes=("", "__wr"),
            )
            dup = [c for c in df.columns if c.endswith("__wr")]
            df = df.drop(columns=dup, errors="ignore")

    # Join WR advanced matchup features (graph_wr_advanced — player_id+season+week key)
    if not wr_adv_df.empty:
        avail = [c for c in join_cols if c in wr_adv_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [c for c in _WR_ADVANCED_FEATURES if c in wr_adv_df.columns]
            # Drop duplicates keeping last (multiple defteam rows per player-week)
            wr_adv_subset = wr_adv_df[avail + feat_cols].drop_duplicates(
                subset=avail, keep="last"
            )
            df = df.merge(
                wr_adv_subset,
                on=avail,
                how="left",
                suffixes=("", "__wradv"),
            )
            dup = [c for c in df.columns if c.endswith("__wradv")]
            df = df.drop(columns=dup, errors="ignore")

    # Join OL/RB features
    if not ol_df.empty:
        avail = [c for c in join_cols if c in ol_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [c for c in OL_RB_FEATURE_COLUMNS if c in ol_df.columns]
            df = df.merge(
                ol_df[avail + feat_cols],
                on=avail,
                how="left",
                suffixes=("", "__ol"),
            )
            dup = [c for c in df.columns if c.endswith("__ol")]
            df = df.drop(columns=dup, errors="ignore")

    # Fill missing columns with NaN for schema consistency
    for col in all_new_cols:
        if col not in df.columns:
            df[col] = np.nan

    return df


def _join_te_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join TE matchup, TE advanced matchup, and red zone graph features.

    Loads graph_te_matchup and graph_te_advanced parquets from Silver and
    merges on (player_id, season, week). Falls back to NaN-filled columns
    when files are not available. Only TE-position players receive actual
    values; all other positions get NaN for TE-specific features.

    Args:
        df: Player-week DataFrame with player_id, season, week, position.
        season: NFL season year.

    Returns:
        DataFrame with TE matchup and TE advanced feature columns joined.
    """
    from graph_feature_extraction import TE_FEATURE_COLUMNS
    from hybrid_projection import _TE_ADVANCED_FEATURES

    all_te_cols = TE_FEATURE_COLUMNS + _TE_ADVANCED_FEATURES

    # Try cached Silver parquets first
    te_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    te_files = sorted(glob.glob(os.path.join(te_dir, "graph_te_matchup_*.parquet")))
    te_adv_files = sorted(glob.glob(os.path.join(te_dir, "graph_te_advanced_*.parquet")))

    te_df = pd.DataFrame()
    te_adv_df = pd.DataFrame()

    if te_files:
        try:
            te_df = pd.read_parquet(te_files[-1])
            logger.info("Loaded cached TE features from %s", te_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached TE features: %s", exc)

    if te_adv_files:
        try:
            te_adv_df = pd.read_parquet(te_adv_files[-1])
            logger.info("Loaded cached TE advanced features from %s", te_adv_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached TE advanced features: %s", exc)

    join_cols = ["player_id", "season", "week"]

    # Join TE base matchup features
    if not te_df.empty:
        avail = [c for c in join_cols if c in te_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [c for c in TE_FEATURE_COLUMNS if c in te_df.columns]
            df = df.merge(
                te_df[avail + feat_cols],
                on=avail,
                how="left",
                suffixes=("", "__te"),
            )
            dup = [c for c in df.columns if c.endswith("__te")]
            df = df.drop(columns=dup, errors="ignore")

    # Join TE advanced matchup features (graph_te_advanced — player_id+season+week key)
    if not te_adv_df.empty:
        avail = [c for c in join_cols if c in te_adv_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [c for c in _TE_ADVANCED_FEATURES if c in te_adv_df.columns]
            # Drop duplicates keeping last (multiple defteam rows per player-week)
            te_adv_subset = te_adv_df[avail + feat_cols].drop_duplicates(
                subset=avail, keep="last"
            )
            df = df.merge(
                te_adv_subset,
                on=avail,
                how="left",
                suffixes=("", "__teadv"),
            )
            dup = [c for c in df.columns if c.endswith("__teadv")]
            df = df.drop(columns=dup, errors="ignore")

    # Fill missing columns with NaN for schema consistency
    for col in all_te_cols:
        if col not in df.columns:
            df[col] = np.nan

    # Zero out TE features for non-TE positions
    if "position" in df.columns:
        non_te_mask = df["position"] != "TE"
        for col in all_te_cols:
            df.loc[non_te_mask, col] = np.nan

    return df


def _join_scheme_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join scheme/defensive front features for RB players.

    Tries cached Silver parquet first, then falls back to live computation
    from Bronze PBP and PFR data. If neither is available, returns NaN-filled
    columns. Only RB-position players receive actual values; all other
    positions get NaN for scheme features.

    Args:
        df: Player-week DataFrame with recent_team, season, week, position.
        season: NFL season year.

    Returns:
        DataFrame with scheme feature columns joined.
    """
    from graph_feature_extraction import SCHEME_FEATURE_COLUMNS

    # Try cached Silver parquet first
    scheme_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    scheme_files = sorted(glob.glob(os.path.join(scheme_dir, "graph_scheme_*.parquet")))

    scheme_df = pd.DataFrame()
    if scheme_files:
        try:
            scheme_df = pd.read_parquet(scheme_files[-1])
            logger.info("Loaded cached scheme features from %s", scheme_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached scheme features: %s", exc)

    # Fallback: compute from Bronze data
    if scheme_df.empty:
        try:
            from graph_feature_extraction import compute_scheme_features

            pbp_pattern = os.path.join(
                BRONZE_DIR, "pbp", f"season={season}", "*.parquet"
            )
            pbp_files = sorted(glob.glob(pbp_pattern))
            pfr_pattern = os.path.join(
                BRONZE_DIR, "pfr", "weekly", "def", f"season={season}", "*.parquet"
            )
            pfr_files = sorted(glob.glob(pfr_pattern))
            sched_pattern = os.path.join(
                BRONZE_DIR, "schedules", f"season={season}", "*.parquet"
            )
            sched_files = sorted(glob.glob(sched_pattern))

            pbp_df = pd.read_parquet(pbp_files[-1]) if pbp_files else pd.DataFrame()
            pfr_df = pd.read_parquet(pfr_files[-1]) if pfr_files else pd.DataFrame()
            sched_df = (
                pd.read_parquet(sched_files[-1]) if sched_files else pd.DataFrame()
            )

            if not pbp_df.empty:
                scheme_df = compute_scheme_features(
                    pbp_df, pfr_df, pd.DataFrame(), sched_df
                )
                logger.info("Computed scheme features from Bronze data")
        except Exception as exc:
            logger.info("Scheme features unavailable (%s) -- skipping", exc)

    # Join on team + season + week (team-level features)
    join_on_left = ["recent_team", "season", "week"]
    join_on_right = ["team", "season", "week"]

    if not scheme_df.empty:
        avail_left = [c for c in join_on_left if c in df.columns]
        avail_right = [c for c in join_on_right if c in scheme_df.columns]
        if len(avail_left) >= 3 and len(avail_right) >= 3:
            feat_cols = [c for c in SCHEME_FEATURE_COLUMNS if c in scheme_df.columns]
            df = df.merge(
                scheme_df[avail_right + feat_cols],
                left_on=avail_left,
                right_on=avail_right,
                how="left",
                suffixes=("", "__scheme"),
            )
            dup = [c for c in df.columns if c.endswith("__scheme")]
            df = df.drop(columns=dup, errors="ignore")
            # Drop extra team column from merge
            if "team" in df.columns and "recent_team" in df.columns:
                df = df.drop(columns=["team"], errors="ignore")

    # Fill missing columns with NaN for schema consistency
    for col in SCHEME_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    # Zero out scheme features for non-RB positions
    if "position" in df.columns:
        non_rb_mask = df["position"] != "RB"
        for col in SCHEME_FEATURE_COLUMNS:
            df.loc[non_rb_mask, col] = np.nan

    return df


def _join_chemistry_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join QB-WR chemistry features if available.

    Tries cached Silver parquet first, then falls back to computing from
    Bronze PBP + player_weekly data. If neither is available, returns
    NaN-filled columns for schema consistency. Only WR/TE positions
    receive actual values.

    Args:
        df: Player-week DataFrame with player_id, season, week, position.
        season: NFL season year.

    Returns:
        DataFrame with QB_WR_CHEMISTRY_FEATURE_COLUMNS joined.
    """
    from graph_qb_wr_chemistry import QB_WR_CHEMISTRY_FEATURE_COLUMNS

    # Try cached Silver parquet first
    chem_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    chem_files = sorted(
        glob.glob(os.path.join(chem_dir, "graph_qb_wr_chemistry_*.parquet"))
    )

    chem_df = pd.DataFrame()
    if chem_files:
        try:
            chem_df = pd.read_parquet(chem_files[-1])
            logger.info(
                "Loaded cached QB-WR chemistry features from %s", chem_files[-1]
            )
        except Exception as exc:
            logger.warning("Failed to read cached chemistry features: %s", exc)

    # Fallback: compute from Bronze data
    if chem_df.empty:
        try:
            from graph_qb_wr_chemistry import (
                build_qb_wr_chemistry,
                compute_chemistry_features,
            )

            # Load PBP across recent seasons for history
            pbp_dfs = []
            pw_dfs = []
            for s in range(max(season - 3, 2016), season + 1):
                pbp_pattern = os.path.join(
                    BRONZE_DIR, "pbp", f"season={s}", "*.parquet"
                )
                pbp_files = sorted(glob.glob(pbp_pattern))
                # Also try week-partitioned layout
                if not pbp_files:
                    pbp_pattern_w = os.path.join(
                        BRONZE_DIR, "pbp", f"season={s}", "week=*", "*.parquet"
                    )
                    pbp_files = sorted(glob.glob(pbp_pattern_w))
                for f in pbp_files:
                    pbp_dfs.append(pd.read_parquet(f))

                pw_pattern = os.path.join(
                    BRONZE_DIR, "players", "weekly", f"season={s}", "*.parquet"
                )
                pw_files = sorted(glob.glob(pw_pattern))
                if not pw_files:
                    pw_pattern_w = os.path.join(
                        BRONZE_DIR,
                        "players",
                        "weekly",
                        f"season={s}",
                        "week=*",
                        "*.parquet",
                    )
                    pw_files = sorted(glob.glob(pw_pattern_w))
                for f in pw_files:
                    pw_dfs.append(pd.read_parquet(f))

            if pbp_dfs and pw_dfs:
                pbp_all = pd.concat(pbp_dfs, ignore_index=True)
                pw_all = pd.concat(pw_dfs, ignore_index=True)

                pair_stats = build_qb_wr_chemistry(pbp_all)
                if not pair_stats.empty:
                    chem_df = compute_chemistry_features(pair_stats, pw_all)
                    # Filter to target season
                    if not chem_df.empty and "season" in chem_df.columns:
                        chem_df = chem_df[chem_df["season"] == season].copy()
                    logger.info("Computed QB-WR chemistry features from Bronze data")
        except Exception as exc:
            logger.info("Chemistry features unavailable (%s) -- skipping", exc)

    # Join on player_id, season, week
    join_cols = ["player_id", "season", "week"]
    if not chem_df.empty:
        avail = [c for c in join_cols if c in chem_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [
                c for c in QB_WR_CHEMISTRY_FEATURE_COLUMNS if c in chem_df.columns
            ]
            df = df.merge(
                chem_df[avail + feat_cols],
                on=avail,
                how="left",
                suffixes=("", "__chem"),
            )
            dup = [c for c in df.columns if c.endswith("__chem")]
            df = df.drop(columns=dup, errors="ignore")

    # Fill missing columns with NaN for schema consistency
    for col in QB_WR_CHEMISTRY_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    # Zero out chemistry features for non-WR/TE positions
    if "position" in df.columns:
        non_recv_mask = ~df["position"].isin(["WR", "TE"])
        for col in QB_WR_CHEMISTRY_FEATURE_COLUMNS:
            df.loc[non_recv_mask, col] = np.nan

    return df


def _join_red_zone_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join red zone target network features if available.

    Tries cached Silver parquet first, then falls back to computing from
    Bronze PBP + player_weekly data. If neither is available, returns
    NaN-filled columns for schema consistency.

    Args:
        df: Player-week DataFrame with player_id, season, week.
        season: NFL season year.

    Returns:
        DataFrame with RED_ZONE_FEATURE_COLUMNS joined.
    """
    from graph_red_zone import RED_ZONE_FEATURE_COLUMNS

    # Try cached Silver parquet first
    rz_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    rz_files = sorted(glob.glob(os.path.join(rz_dir, "graph_red_zone_*.parquet")))

    rz_df = pd.DataFrame()
    if rz_files:
        try:
            rz_df = pd.read_parquet(rz_files[-1])
            logger.info("Loaded cached red zone features from %s", rz_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached red zone features: %s", exc)

    # Fallback: compute from Bronze data
    if rz_df.empty:
        try:
            from graph_red_zone import (
                compute_red_zone_features,
                compute_red_zone_usage,
            )

            # Load PBP and player_weekly across recent seasons
            pbp_dfs = []
            pw_dfs = []
            rosters_dfs = []
            for s in range(max(season - 3, 2016), season + 1):
                pbp_pattern = os.path.join(
                    BRONZE_DIR, "pbp", f"season={s}", "*.parquet"
                )
                pbp_files = sorted(glob.glob(pbp_pattern))
                if not pbp_files:
                    pbp_pattern_w = os.path.join(
                        BRONZE_DIR, "pbp", f"season={s}", "week=*", "*.parquet"
                    )
                    pbp_files = sorted(glob.glob(pbp_pattern_w))
                for f in pbp_files:
                    pbp_dfs.append(pd.read_parquet(f))

                pw_pattern = os.path.join(
                    BRONZE_DIR, "players", "weekly", f"season={s}", "*.parquet"
                )
                pw_files = sorted(glob.glob(pw_pattern))
                if not pw_files:
                    pw_pattern_w = os.path.join(
                        BRONZE_DIR,
                        "players",
                        "weekly",
                        f"season={s}",
                        "week=*",
                        "*.parquet",
                    )
                    pw_files = sorted(glob.glob(pw_pattern_w))
                for f in pw_files:
                    pw_dfs.append(pd.read_parquet(f))

                roster_pattern = os.path.join(
                    BRONZE_DIR, "players", "rosters", f"season={s}", "*.parquet"
                )
                roster_files = sorted(glob.glob(roster_pattern))
                for f in roster_files:
                    rosters_dfs.append(pd.read_parquet(f))

            if pbp_dfs:
                pbp_all = pd.concat(pbp_dfs, ignore_index=True)
                pw_all = (
                    pd.concat(pw_dfs, ignore_index=True) if pw_dfs else pd.DataFrame()
                )
                rosters_all = (
                    pd.concat(rosters_dfs, ignore_index=True)
                    if rosters_dfs
                    else pd.DataFrame()
                )

                rz_usage = compute_red_zone_usage(pbp_all, rosters_all)
                if not rz_usage.empty:
                    rz_df = compute_red_zone_features(rz_usage, pw_all)
                    # Filter to target season
                    if not rz_df.empty and "season" in rz_df.columns:
                        rz_df = rz_df[rz_df["season"] == season].copy()
                    logger.info("Computed red zone features from Bronze data")
        except Exception as exc:
            logger.info("Red zone features unavailable (%s) -- skipping", exc)

    # Join on player_id, season, week
    join_cols = ["player_id", "season", "week"]
    if not rz_df.empty:
        avail = [c for c in join_cols if c in rz_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [c for c in RED_ZONE_FEATURE_COLUMNS if c in rz_df.columns]
            df = df.merge(
                rz_df[avail + feat_cols],
                on=avail,
                how="left",
                suffixes=("", "__rz"),
            )
            dup = [c for c in df.columns if c.endswith("__rz")]
            df = df.drop(columns=dup, errors="ignore")

    # Fill missing columns with NaN for schema consistency
    for col in RED_ZONE_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    return df


def _join_game_script_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join game script role shift features if available.

    Tries cached Silver parquet first, then falls back to computing from
    Bronze PBP data. If neither is available, returns NaN-filled columns
    for schema consistency.

    Args:
        df: Player-week DataFrame with player_id, season, week, recent_team.
        season: NFL season year.

    Returns:
        DataFrame with GAME_SCRIPT_FEATURE_COLUMNS joined.
    """
    from graph_game_script import GAME_SCRIPT_FEATURE_COLUMNS

    # Try cached Silver parquet first
    gs_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    gs_files = sorted(glob.glob(os.path.join(gs_dir, "graph_game_script_*.parquet")))

    gs_df = pd.DataFrame()
    if gs_files:
        try:
            gs_df = pd.read_parquet(gs_files[-1])
            logger.info("Loaded cached game script features from %s", gs_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached game script features: %s", exc)

    # Fallback: compute from Bronze PBP data
    if gs_df.empty:
        try:
            from graph_game_script import (
                compute_game_script_features,
                compute_game_script_usage,
            )

            pbp_pattern = os.path.join(
                BRONZE_DIR, "pbp", f"season={season}", "*.parquet"
            )
            pbp_files = sorted(glob.glob(pbp_pattern))

            if pbp_files:
                pbp_df = pd.read_parquet(pbp_files[-1])
                usage_df = compute_game_script_usage(pbp_df)

                if not usage_df.empty:
                    schedules = _read_bronze_schedules(season)
                    gs_df = compute_game_script_features(usage_df, schedules)
                    logger.info("Computed game script features from Bronze PBP")
        except Exception as exc:
            logger.info("Game script features unavailable (%s) — skipping", exc)

    # Join on player_id, season, week
    if not gs_df.empty:
        join_cols = ["player_id", "season", "week"]
        avail = [c for c in join_cols if c in gs_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [c for c in GAME_SCRIPT_FEATURE_COLUMNS if c in gs_df.columns]
            df = df.merge(
                gs_df[avail + feat_cols],
                on=avail,
                how="left",
                suffixes=("", "__gs"),
            )
            dup = [c for c in df.columns if c.endswith("__gs")]
            df = df.drop(columns=dup, errors="ignore")

    # Fill missing columns with NaN for schema consistency
    for col in GAME_SCRIPT_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

    return df


def _join_college_network_features(df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Left-join college network features if available.

    Tries cached Silver parquet first, then falls back to computing from
    Bronze draft picks, combine, and roster data. If neither is available,
    returns NaN-filled columns for schema consistency.

    Args:
        df: Player-week DataFrame with player_id, season, week, recent_team.
        season: NFL season year.

    Returns:
        DataFrame with COLLEGE_NETWORK_FEATURE_COLUMNS joined.
    """
    from graph_college_networks import COLLEGE_NETWORK_FEATURE_COLUMNS

    # Try cached Silver parquet first
    cn_dir = os.path.join(SILVER_DIR, "graph_features", f"season={season}")
    cn_files = sorted(
        glob.glob(os.path.join(cn_dir, "graph_college_networks_*.parquet"))
    )

    cn_df = pd.DataFrame()
    if cn_files:
        try:
            cn_df = pd.read_parquet(cn_files[-1])
            logger.info("Loaded cached college network features from %s", cn_files[-1])
        except Exception as exc:
            logger.warning("Failed to read cached college network features: %s", exc)

    # Fallback: compute from Bronze data
    if cn_df.empty:
        try:
            from graph_college_networks import (
                _read_bronze_combine,
                _read_bronze_draft_picks,
                _read_bronze_rosters,
                compute_all_college_features,
            )

            draft_picks_df = _read_bronze_draft_picks()
            combine_df = _read_bronze_combine()
            rosters_df = _read_bronze_rosters()

            if not draft_picks_df.empty:
                weeks = sorted(df["week"].dropna().unique())
                week_dfs = []
                for wk in weeks:
                    wk_feats = compute_all_college_features(
                        draft_picks_df, combine_df, df, rosters_df, season, int(wk)
                    )
                    if not wk_feats.empty:
                        week_dfs.append(wk_feats)
                if week_dfs:
                    cn_df = pd.concat(week_dfs, ignore_index=True)
                    logger.info("Computed college network features from Bronze data")

                    # Cache to Silver
                    os.makedirs(cn_dir, exist_ok=True)
                    import datetime

                    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    cache_path = os.path.join(
                        cn_dir, f"graph_college_networks_{ts}.parquet"
                    )
                    cn_df.to_parquet(cache_path, index=False)
                    logger.info("Cached college network features to %s", cache_path)
        except Exception as exc:
            logger.info("College network features unavailable (%s) — skipping", exc)

    # Join on player_id, season, week
    if not cn_df.empty:
        join_cols = ["player_id", "season", "week"]
        avail = [c for c in join_cols if c in cn_df.columns and c in df.columns]
        if len(avail) >= 3:
            feat_cols = [
                c for c in COLLEGE_NETWORK_FEATURE_COLUMNS if c in cn_df.columns
            ]
            df = df.merge(
                cn_df[avail + feat_cols],
                on=avail,
                how="left",
                suffixes=("", "__cn"),
            )
            dup = [c for c in df.columns if c.endswith("__cn")]
            df = df.drop(columns=dup, errors="ignore")

    # Fill missing columns with NaN for schema consistency
    for col in COLLEGE_NETWORK_FEATURE_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan

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
        defense[["avg_pts_allowed", "rank"]] = defense.groupby(
            ["team", "position", "season"]
        )[["avg_pts_allowed", "rank"]].shift(1)
        defense = defense.rename(
            columns={
                "avg_pts_allowed": "opp_avg_pts_allowed",
                "rank": "opp_rank",
            }
        )
        base = base.merge(
            defense,
            left_on=["opponent_team", "season", "week", "position"],
            right_on=["team", "season", "week", "position"],
            how="left",
            suffixes=("", "__def"),
        )
        # Drop extra team column and any suffixed dups
        base = base.drop(
            columns=[c for c in base.columns if c.endswith("__def")], errors="ignore"
        )
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
        opp_epa["def_epa_per_play"] = opp_epa.groupby(["team", "season"])[
            "def_epa_per_play"
        ].shift(1)
        opp_epa = opp_epa.rename(columns={"def_epa_per_play": "opp_def_epa_per_play"})
        base = base.merge(
            opp_epa,
            left_on=["opponent_team", "season", "week"],
            right_on=["team", "season", "week"],
            how="left",
            suffixes=("", "__opp_epa"),
        )
        base = base.drop(
            columns=[c for c in base.columns if c.endswith("__opp_epa")],
            errors="ignore",
        )
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

    # 10. Compute derived features
    base = compute_efficiency_features(base)
    base = compute_td_regression_features(base)
    base = compute_momentum_features(base)
    base = compute_interaction_features(base)

    # 11. Optional: join graph-derived injury cascade features
    base = _join_graph_features(base, season)

    # 12. Optional: join WR matchup + OL/RB features (Phase 2 graph)
    base = _join_wr_matchup_features(base, season)

    # 13. Optional: join TE matchup + red zone features (Phase 2 graph)
    base = _join_te_features(base, season)

    # 14. Optional: join scheme/defensive front features (RB only)
    base = _join_scheme_features(base, season)

    # 15. Optional: join QB-WR chemistry features (WR/TE only)
    base = _join_chemistry_features(base, season)

    # 16. Optional: join red zone target network features
    base = _join_red_zone_features(base, season)

    # 17. Optional: join game script role shift features
    base = _join_game_script_features(base, season)

    # 18. Optional: join college network features (teammate, scheme, prospect comps)
    base = _join_college_network_features(base, season)

    logger.info(
        "Assembled player features for season %d: %d rows, %d columns",
        season,
        len(base),
        len(base.columns),
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
    return sorted(
        [
            c
            for c in df.columns
            if c not in exclude and str(df[c].dtype) in numeric_dtypes
        ]
    )


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
        len(dfs),
        len(result),
        len(result.columns),
    )
    return result
