#!/usr/bin/env python3
"""Projection Backtesting Framework.

Compares model projections against actual fantasy points for historical
weeks to measure accuracy and identify systematic biases.

Usage:
    python scripts/backtest_projections.py --seasons 2023,2024 --scoring half_ppr
    python scripts/backtest_projections.py --seasons 2024 --weeks 1-10

    # Beat-the-consensus head-to-head (Phase 1.1):
    python scripts/backtest_projections.py --seasons 2022,2023,2024 \\
        --scoring half_ppr --vs-consensus
"""

import sys
import os
import argparse
import glob as globmod
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np
from scipy import stats as scipy_stats

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nfl_data_integration import NFLDataFetcher
from scoring_calculator import calculate_fantasy_points_df, list_scoring_formats
from player_analytics import (
    compute_usage_metrics,
    compute_rolling_averages,
    compute_defensive_strength,
    compute_opponent_rankings,
    compute_implied_team_totals,
)
from projection_engine import generate_weekly_projections

try:
    from ml_projection_router import generate_ml_projections

    HAS_ML_ROUTER = True
except ImportError:
    HAS_ML_ROUTER = False

try:
    from player_feature_engineering import (
        assemble_player_features,
        get_player_feature_columns,
    )

    HAS_FEATURE_ENGINEERING = True
except ImportError:
    HAS_FEATURE_ENGINEERING = False


logging.basicConfig(level=logging.WARNING, format="%(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Consensus benchmark constants (Phase 1.1).
_CONSENSUS_SOURCE: str = "sleeper"
_CONSENSUS_MIN_PTS: float = 5.0  # Minimum consensus projection to include.
_TOP_N: Dict[str, int] = {"QB": 12, "TE": 12, "RB": 24, "WR": 24}
_CONSENSUS_POSITIONS: List[str] = ["QB", "RB", "WR", "TE"]


def parse_weeks(weeks_str: str) -> List[int]:
    """Parse '1-10' or '1,5,10' into a list of ints."""
    if "-" in weeks_str:
        start, end = weeks_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(w) for w in weeks_str.split(",")]


def compute_actuals(
    weekly_df: pd.DataFrame, season: int, week: int, scoring_format: str
) -> pd.DataFrame:
    """Compute actual fantasy points for a specific week.

    Always keeps player_id when present so that the merge in run_backtest
    can use an exact ID join instead of a name-based join.  Name-based joins
    fan out when two different players share an abbreviated name (e.g.
    Tyreek Hill and Taysom Hill both become "T.Hill"), producing duplicate
    rows with different actual_points for the same projection row.
    """
    week_data = weekly_df[
        (weekly_df["season"] == season) & (weekly_df["week"] == week)
    ].copy()
    if week_data.empty:
        return pd.DataFrame()

    week_data = calculate_fantasy_points_df(
        week_data, scoring_format=scoring_format, output_col="actual_points"
    )

    # Always include player_id; fall back gracefully if it is absent.
    keep = ["player_id", "player_name", "position", "recent_team", "actual_points"]
    keep = [c for c in keep if c in week_data.columns]
    return week_data[keep]


def build_silver_features(
    weekly_df: pd.DataFrame, season: int, up_to_week: int
) -> pd.DataFrame:
    """Build Silver-layer features using only data available up to a given week."""
    hist = weekly_df[
        (weekly_df["season"] == season) & (weekly_df["week"] < up_to_week)
    ].copy()
    if hist.empty or len(hist) < 5:
        # Need some history; try including prior season
        prior = weekly_df[weekly_df["season"] == season - 1].copy()
        hist = pd.concat([prior, hist], ignore_index=True)

    if hist.empty:
        return pd.DataFrame()

    try:
        usage = compute_usage_metrics(hist)
        rolling = compute_rolling_averages(usage)
        return rolling
    except Exception as e:
        logger.debug(
            "Feature build failed for season=%d week<%d: %s", season, up_to_week, e
        )
        return pd.DataFrame()


def _load_local_parquet(base_dir: str, pattern: str) -> pd.DataFrame:
    """Load latest parquet from local data directory."""
    import glob as globmod

    files = sorted(globmod.glob(os.path.join(base_dir, pattern)))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _prepare_weekly(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure air_yards column exists for analytics functions."""
    if "air_yards" not in df.columns:
        if "receiving_air_yards" in df.columns:
            df = df.copy()
            df["air_yards"] = df["receiving_air_yards"].fillna(0)
    return df


def _compute_week_implied_totals(
    schedules_df: pd.DataFrame, week: int
) -> Optional[Dict]:
    """Compute per-team implied scoring totals from schedule lines for a week."""
    required = {"week", "home_team", "away_team", "total_line", "spread_line"}
    if schedules_df.empty or not required.issubset(schedules_df.columns):
        return None

    games = schedules_df[schedules_df["week"] == week].dropna(
        subset=["total_line", "spread_line"]
    )
    if games.empty:
        return None

    implied: Dict[str, float] = {}
    for _, row in games.iterrows():
        total = float(row["total_line"])
        spread = float(row["spread_line"])
        # nflverse convention: spread_line is the expected HOME margin
        # (positive = home favored), so the home implied total is
        # (total + spread) / 2.
        implied[row["home_team"]] = round((total + spread) / 2, 2)
        implied[row["away_team"]] = round((total - spread) / 2, 2)

    return implied


# ---------------------------------------------------------------------------
# Consensus benchmark helpers (Phase 1.1)
# ---------------------------------------------------------------------------


def load_consensus_for_seasons(
    seasons: List[int],
    weeks: Optional[List[int]],
    scoring_format: str,
    silver_root: str,
    source: str = _CONSENSUS_SOURCE,
) -> pd.DataFrame:
    """Load Silver external projections for the given seasons/weeks.

    Reads from ``data/silver/external_projections/season=YYYY/week=WW/``.

    Args:
        seasons: List of season years to load.
        weeks: Specific weeks to load (None = all found).
        scoring_format: Scoring format string.
        silver_root: Root path for silver external projections.
        source: Source label to filter on (default "sleeper").

    Returns:
        DataFrame with columns: player_id, player_name, season, week,
        consensus_proj. Empty if no data found.
    """
    dfs: List[pd.DataFrame] = []
    target_weeks = set(weeks) if weeks else set(range(1, 19))

    for season in seasons:
        season_dir = os.path.join(silver_root, f"season={season}")
        if not os.path.isdir(season_dir):
            logger.warning("No Silver data for season=%d at %s", season, season_dir)
            continue
        for week in target_weeks:
            week_dir = os.path.join(season_dir, f"week={week:02d}")
            if not os.path.isdir(week_dir):
                continue
            files = sorted(globmod.glob(os.path.join(week_dir, "*.parquet")))
            if not files:
                continue
            try:
                df = pd.read_parquet(files[-1])
            except Exception as exc:
                logger.warning("Could not read %s: %s", files[-1], exc)
                continue

            # Filter to requested source and scoring format
            if "source" in df.columns:
                df = df[df["source"] == source].copy()
            if (
                "scoring_format" in df.columns
                and scoring_format in df["scoring_format"].values
            ):
                df = df[df["scoring_format"] == scoring_format].copy()

            if df.empty:
                continue

            df = df.rename(columns={"projected_points": "consensus_proj"})
            df["season"] = int(season)
            df["week"] = int(week)
            dfs.append(
                df[["player_id", "player_name", "season", "week", "consensus_proj"]]
            )

    if not dfs:
        return pd.DataFrame(
            columns=["player_id", "player_name", "season", "week", "consensus_proj"]
        )
    return pd.concat(dfs, ignore_index=True)


def _build_name_to_id_map(weekly_df: pd.DataFrame) -> Dict[str, str]:
    """Build a lowercase player_name -> player_id lookup from weekly data.

    Used as a fallback when direct player_id join fails.

    Args:
        weekly_df: Weekly player stats DataFrame.

    Returns:
        Dict mapping normalised name to player_id string.
    """
    if "player_id" not in weekly_df.columns or "player_name" not in weekly_df.columns:
        return {}
    name_map: Dict[str, str] = {}
    for _, row in weekly_df[["player_name", "player_id"]].drop_duplicates().iterrows():
        name = str(row["player_name"]).strip().lower()
        pid = str(row["player_id"]).strip()
        if name and pid:
            name_map[name] = pid
    return name_map


def join_consensus(
    results_df: pd.DataFrame,
    consensus_df: pd.DataFrame,
) -> pd.DataFrame:
    """Join our backtest results with consensus projections.

    Join key: (player_id, season, week).  Falls back to (player_name, season,
    week) for rows where our results frame lacks player_id or the IDs don't
    match.  Only rows that match on the consensus side survive (inner join
    semantics on the consensus key).

    The leak rule is enforced by construction: consensus_df contains only
    projected values — actuals are never present on that side.

    Args:
        results_df: DataFrame from run_backtest() with at least:
            player_name, season, week, projected_points, actual_points,
            position.
        consensus_df: DataFrame from load_consensus_for_seasons() with:
            player_id, player_name, season, week, consensus_proj.

    Returns:
        DataFrame with both our projection and consensus, restricted to rows
        that matched on both sides.  Added column: consensus_proj.
    """
    if results_df.empty or consensus_df.empty:
        return pd.DataFrame()

    join_keys_id = ["player_id", "season", "week"]
    join_keys_name = ["player_name", "season", "week"]

    # Path 1: join on player_id if available in both frames
    has_id_in_results = "player_id" in results_df.columns
    has_id_in_consensus = "player_id" in consensus_df.columns

    if has_id_in_results and has_id_in_consensus:
        # Ensure types align
        results_copy = results_df.copy()
        consensus_copy = consensus_df.copy()
        results_copy["player_id"] = results_copy["player_id"].astype(str).str.strip()
        consensus_copy["player_id"] = (
            consensus_copy["player_id"].astype(str).str.strip()
        )

        merged = results_copy.merge(
            consensus_copy[join_keys_id + ["consensus_proj"]],
            on=join_keys_id,
            how="inner",
        )
        if not merged.empty:
            return merged

    # Path 2: fallback join on player_name (normalised)
    logger.info("player_id join produced 0 matches; falling back to player_name join")
    results_copy = results_df.copy()
    consensus_copy = consensus_df.copy()
    results_copy["_name_norm"] = results_copy["player_name"].str.strip().str.lower()
    consensus_copy["_name_norm"] = consensus_copy["player_name"].str.strip().str.lower()

    merged = results_copy.merge(
        consensus_copy[["_name_norm", "season", "week", "consensus_proj"]],
        on=["_name_norm", "season", "week"],
        how="inner",
    ).drop(columns=["_name_norm"])

    return merged


def compute_spearman_rank_corr(
    df: pd.DataFrame,
    proj_col: str,
    actual_col: str,
    position: str,
) -> float:
    """Compute mean within-position-week Spearman rank correlation.

    For each (season, week) group, compute the Spearman rank correlation
    between projected and actual points, then average across weeks.

    Args:
        df: DataFrame with proj_col, actual_col, season, week columns.
        proj_col: Column name for projected points.
        actual_col: Column name for actual points.
        position: Position label (for logging only).

    Returns:
        Mean Spearman rank correlation (float, NaN if not computable).
    """
    week_corrs: List[float] = []
    for (season, week), grp in df.groupby(["season", "week"]):
        if len(grp) < 3:
            continue
        rho, _ = scipy_stats.spearmanr(grp[proj_col], grp[actual_col])
        if not np.isnan(rho):
            week_corrs.append(rho)
    if not week_corrs:
        return float("nan")
    return float(np.mean(week_corrs))


def compute_top_n_hit_rate(
    df: pd.DataFrame,
    proj_col: str,
    actual_col: str,
    position: str,
) -> float:
    """Compute Top-N hit rate: fraction of actual top-N captured in projected top-N.

    For each (season, week) group, take the top-N actual scorers.  Count
    what fraction of them appear in the projected top-N.  Average across weeks.

    Args:
        df: DataFrame with proj_col, actual_col, season, week columns.
        proj_col: Column name for projected points.
        actual_col: Column name for actual points.
        position: Position used to look up N in _TOP_N.

    Returns:
        Mean hit rate in [0, 1] (float, NaN if not computable).
    """
    n = _TOP_N.get(position, 12)
    week_rates: List[float] = []
    for (season, week), grp in df.groupby(["season", "week"]):
        if len(grp) < n:
            continue
        actual_top = set(grp.nlargest(n, actual_col).index)
        proj_top = set(grp.nlargest(n, proj_col).index)
        overlap = len(actual_top & proj_top)
        week_rates.append(overlap / n)
    if not week_rates:
        return float("nan")
    return float(np.mean(week_rates))


def print_consensus_report(
    matched_df: pd.DataFrame,
    scoring_format: str,
) -> None:
    """Print the head-to-head consensus benchmark report.

    Args:
        matched_df: DataFrame with columns: projected_points, consensus_proj,
            actual_points, position, season, week.
        scoring_format: Scoring format label for the header.
    """
    if matched_df.empty:
        print("No matched player-weeks for consensus benchmark.")
        return

    # Apply consensus filter: consensus projection >= 5 pts
    df = matched_df[matched_df["consensus_proj"] >= _CONSENSUS_MIN_PTS].copy()
    if df.empty:
        print(f"No player-weeks with consensus_proj >= {_CONSENSUS_MIN_PTS}.")
        return

    print(f"\n{'=' * 78}")
    print(f"BEAT-THE-CONSENSUS REPORT — {scoring_format.upper()} (Phase 1.1)")
    print(f"{'=' * 78}")
    print(
        f"Population: weeks 3-18, consensus_proj >= {_CONSENSUS_MIN_PTS} pts, "
        f"positions: {', '.join(_CONSENSUS_POSITIONS)}"
    )

    n_total = len(df)
    n_weeks = df[["season", "week"]].drop_duplicates().shape[0]
    n_seasons = df["season"].nunique()
    print(
        f"Matched player-weeks: {n_total:,} | Weeks: {n_weeks} | Seasons: {n_seasons}"
    )
    match_rate = n_total / (
        matched_df["position"].isin(_CONSENSUS_POSITIONS).sum() + 1e-9
    )
    print(f"Match rate (of backtest rows): {match_rate*100:.1f}%\n")

    # Header
    print(
        f"{'Position':<8} {'Sys':<10} {'MAE':>7} {'vs Cons':>9} "
        f"{'SpearmanR':>10} {'Top-N HR':>9} {'n':>7}"
    )
    print(f"{'-' * 62}")

    # Overall row first
    pos_data_all = df[df["position"].isin(_CONSENSUS_POSITIONS)]

    for label, pos_filter in [("OVERALL", None)] + [
        (pos, pos) for pos in _CONSENSUS_POSITIONS
    ]:
        pos_df = (
            pos_data_all
            if pos_filter is None
            else pos_data_all[pos_data_all["position"] == pos_filter]
        )
        if pos_df.empty:
            continue

        pos_label = label if pos_filter is None else pos_filter
        n = len(pos_df)
        position_for_topn = pos_filter if pos_filter else "WR"  # unused for overall

        # Our metrics
        our_mae = (pos_df["projected_points"] - pos_df["actual_points"]).abs().mean()
        our_spearman = compute_spearman_rank_corr(
            pos_df, "projected_points", "actual_points", pos_label
        )
        our_topn = (
            compute_top_n_hit_rate(
                pos_df, "projected_points", "actual_points", pos_label
            )
            if pos_filter
            else float("nan")
        )

        # Consensus metrics
        con_mae = (pos_df["consensus_proj"] - pos_df["actual_points"]).abs().mean()
        con_spearman = compute_spearman_rank_corr(
            pos_df, "consensus_proj", "actual_points", pos_label
        )
        con_topn = (
            compute_top_n_hit_rate(pos_df, "consensus_proj", "actual_points", pos_label)
            if pos_filter
            else float("nan")
        )

        mae_delta = our_mae - con_mae  # positive = we're worse; negative = we're better
        spearman_delta = our_spearman - con_spearman

        # Print ours
        spearman_str = f"{our_spearman:.3f}" if not np.isnan(our_spearman) else "  N/A"
        topn_str = f"{our_topn:.3f}" if not np.isnan(our_topn) else "  N/A"
        print(
            f"{pos_label:<8} {'Ours':<10} {our_mae:>7.2f} {' ':>9} "
            f"{spearman_str:>10} {topn_str:>9} {n:>7,}"
        )

        # Print consensus
        spearman_str_c = (
            f"{con_spearman:.3f}" if not np.isnan(con_spearman) else "  N/A"
        )
        topn_str_c = f"{con_topn:.3f}" if not np.isnan(con_topn) else "  N/A"
        mae_delta_str = f"{mae_delta:+.2f}"
        print(
            f"{'':<8} {'Sleeper':<10} {con_mae:>7.2f} {mae_delta_str:>9} "
            f"{spearman_str_c:>10} {topn_str_c:>9} {n:>7,}"
        )

        if pos_filter is not None:
            print(f"  -> SpearmanR delta (ours - cons): {spearman_delta:+.3f}")
        print()

    # Summary verdict
    overall_df = pos_data_all
    our_mae_overall = (
        (overall_df["projected_points"] - overall_df["actual_points"]).abs().mean()
    )
    con_mae_overall = (
        (overall_df["consensus_proj"] - overall_df["actual_points"]).abs().mean()
    )
    gap = our_mae_overall - con_mae_overall
    verdict = (
        f"Ours BEATS consensus by {abs(gap):.2f} MAE pts"
        if gap < -0.01
        else (
            f"Consensus BEATS ours by {abs(gap):.2f} MAE pts"
            if gap > 0.01
            else "Ours matches consensus (gap < 0.01 MAE)"
        )
    )
    print(f"\nVERDICT (consensus subset, all positions): {verdict}")
    print(
        "Note: Compare ours vs consensus on the SAME matched subset. "
        "Do not compare to the full-population 4.71 MAE."
    )


def run_backtest(
    seasons: List[int],
    weeks: Optional[List[int]],
    scoring_format: str,
    use_ml: bool = False,
    apply_constraints: bool = False,
    full_features: bool = False,
) -> pd.DataFrame:
    """Run backtesting across specified seasons and weeks.

    Args:
        seasons: Seasons to backtest.
        weeks: Specific weeks (None = 3-18).
        scoring_format: Scoring format string.
        use_ml: Use ML projection router.
        apply_constraints: Apply team-level constraints.
        full_features: When True and use_ml is True, assemble the full
            466-column feature vector from player_feature_engineering and
            pass it to the ML projection router for richer residual
            correction. Requires local Silver data.
    """
    fetcher = NFLDataFetcher()
    project_root = os.path.join(os.path.dirname(__file__), "..")
    bronze_dir = os.path.join(project_root, "data", "bronze")

    # Fetch all weekly data upfront — try local Bronze first
    all_seasons = list(set(seasons + [s - 1 for s in seasons]))
    print(f"Loading weekly data for seasons: {all_seasons}")

    dfs = []
    for s in sorted(all_seasons):
        local = _load_local_parquet(bronze_dir, f"players/weekly/season={s}/*.parquet")
        if not local.empty:
            dfs.append(local)
    if dfs:
        weekly_df = pd.concat(dfs, ignore_index=True)
        print(f"Loaded {len(weekly_df):,} weekly rows from local Bronze")
    else:
        weekly_df = fetcher.fetch_player_weekly(all_seasons)
        print(f"Loaded {len(weekly_df):,} weekly rows from nfl-data-py")

    weekly_df = _prepare_weekly(weekly_df)

    # Load schedules for opponent rankings (and implied totals if --constrain)
    sched_dfs = []
    for s in sorted(all_seasons):
        local = _load_local_parquet(bronze_dir, f"games/season={s}/*.parquet")
        if local.empty:
            local = _load_local_parquet(bronze_dir, f"schedules/season={s}/*.parquet")
        if not local.empty:
            if "season" not in local.columns:
                local["season"] = s
            sched_dfs.append(local)
    schedules_df = (
        pd.concat(sched_dfs, ignore_index=True) if sched_dfs else pd.DataFrame()
    )
    if not schedules_df.empty:
        print(f"Loaded {len(schedules_df):,} schedule rows")
        if apply_constraints:
            has_lines = {"total_line", "spread_line"}.issubset(schedules_df.columns)
            print(f"  Constraints enabled — Vegas lines available: {has_lines}")

    # Load snap counts across all backtest seasons (week-partitioned Bronze)
    snap_dfs = []
    for s in sorted(all_seasons):
        snap_pattern = os.path.join(bronze_dir, f"players/snaps/season={s}/week=*/*.parquet")
        import glob as _glob
        snap_files = sorted(_glob.glob(snap_pattern))
        if snap_files:
            season_snaps = pd.concat(
                [pd.read_parquet(f) for f in snap_files], ignore_index=True
            )
            snap_dfs.append(season_snaps)
    snap_counts_df: Optional[pd.DataFrame] = None
    if snap_dfs:
        snap_counts_df = pd.concat(snap_dfs, ignore_index=True)
        if "week" in snap_counts_df.columns:
            snap_counts_df["week"] = pd.to_numeric(snap_counts_df["week"], errors="coerce")
        if "season" in snap_counts_df.columns:
            snap_counts_df["season"] = pd.to_numeric(snap_counts_df["season"], errors="coerce")
        if "offense_pct" in snap_counts_df.columns:
            snap_counts_df["offense_pct"] = pd.to_numeric(
                snap_counts_df["offense_pct"], errors="coerce"
            ).fillna(0.0)
        print(f"Loaded {len(snap_counts_df):,} snap-count rows across {len(snap_dfs)} season(s)")
    else:
        print("No snap count data found — RB snap-collapse signal will be skipped")

    # Load route participation features (Silver graph_features) for WR slope-collapse
    silver_dir = os.path.join(project_root, "data", "silver")
    route_parts = []
    for s in sorted(all_seasons):
        route_pattern = os.path.join(
            silver_dir, f"graph_features/season={s}/graph_route_participation_*.parquet"
        )
        route_files = sorted(globmod.glob(route_pattern))
        if route_files:
            route_parts.append(pd.read_parquet(route_files[-1]))
    route_df: Optional[pd.DataFrame] = pd.concat(route_parts, ignore_index=True) if route_parts else None
    if route_df is not None:
        print(f"Loaded {len(route_df):,} route-participation rows for WR slope-collapse")
    else:
        print("No route participation data found — WR slope-collapse signal will be skipped")

    # Pre-assemble full feature vectors per season (if requested)
    season_features: Dict[int, pd.DataFrame] = {}
    if full_features and use_ml and HAS_FEATURE_ENGINEERING:
        print("\nAssembling full feature vectors...")
        for s in seasons:
            feat_df = assemble_player_features(s)
            if not feat_df.empty:
                season_features[s] = feat_df
                n_cols = len(get_player_feature_columns(feat_df))
                print(f"  Season {s}: {len(feat_df):,} rows, {n_cols} features")
            else:
                print(f"  Season {s}: no features assembled")
        print()

    # Defensive strength table for the matchup factor — properly lagged
    # (trailing window with shift(1)), so one table serves every week.
    try:
        opp_rankings = compute_defensive_strength(
            weekly_df, schedules_df, scoring_format=scoring_format
        )
    except Exception as e:
        logger.warning("Defensive strength computation failed: %s", e)
        opp_rankings = pd.DataFrame()

    results = []
    total_weeks = 0

    for season in seasons:
        season_weeks = weeks or list(
            range(3, 19)
        )  # Start week 3 (need 2 weeks of history)

        for week in season_weeks:
            print(f"  Backtesting {season} Week {week}...", end=" ", flush=True)

            # Build features from data available before this week
            silver_df = build_silver_features(weekly_df, season, up_to_week=week)
            if silver_df.empty:
                print("SKIP (insufficient history)")
                continue

            # Compute implied totals whenever schedule lines are available.
            # EVAL-VALIDITY FIX (2026-06-12): this was previously gated on
            # apply_constraints, so every standard backtest ran with the
            # Vegas multiplier silently DISABLED (vegas_multiplier == 1.0 on
            # all rows) while production applied it — the backtest was not
            # measuring the production system. Constraints remain gated on
            # apply_constraints inside the projection call.
            implied_totals = None
            sched_for_week = None
            if not schedules_df.empty:
                week_sched = (
                    schedules_df[
                        schedules_df.get("season", pd.Series(dtype=int)).eq(season)
                    ]
                    if "season" in schedules_df.columns
                    else schedules_df
                )
                implied_totals = _compute_week_implied_totals(week_sched, week)
                if implied_totals:
                    sched_for_week = week_sched

            # Generate projections
            try:
                if use_ml and HAS_ML_ROUTER:
                    # Pass full features if available
                    feat_df = season_features.get(season) if full_features else None
                    projections = generate_ml_projections(
                        silver_df,
                        opp_rankings,
                        season=season,
                        week=week,
                        scoring_format=scoring_format,
                        schedules_df=(
                            sched_for_week
                            if sched_for_week is not None
                            else (schedules_df if not schedules_df.empty else None)
                        ),
                        implied_totals=implied_totals,
                        apply_constraints=apply_constraints,
                        feature_df=feat_df,
                        # Same data the default heuristic path passes — the
                        # --ml and heuristic backtests must measure the SAME
                        # underlying heuristic baseline.
                        weekly_df=weekly_df,
                        snap_counts_df=snap_counts_df,
                    )
                else:
                    projections = generate_weekly_projections(
                        silver_df,
                        opp_rankings,
                        season=season,
                        week=week,
                        scoring_format=scoring_format,
                        schedules_df=(
                            sched_for_week
                            if sched_for_week is not None
                            else (schedules_df if not schedules_df.empty else None)
                        ),
                        implied_totals=implied_totals,
                        apply_constraints=apply_constraints,
                        weekly_df=weekly_df,
                        snap_counts_df=snap_counts_df,
                        route_df=route_df,
                    )
            except Exception as e:
                print(f"FAIL ({e})")
                continue

            if projections.empty:
                print("SKIP (no projections)")
                continue

            # Compute actuals
            actuals = compute_actuals(weekly_df, season, week, scoring_format)
            if actuals.empty:
                print("SKIP (no actuals)")
                continue

            # Merge projected vs actual using player_id when available on both
            # sides.  A name-only join fans out when two players share an
            # abbreviated name (e.g. T.Hill = Tyreek Hill + Taysom Hill),
            # producing duplicate rows with different actual_points for the
            # same projection — which corrupts MAE and consensus benchmarks.
            has_pid_proj = "player_id" in projections.columns
            has_pid_act = "player_id" in actuals.columns

            if has_pid_proj and has_pid_act:
                proj_copy = projections.copy()
                act_copy = actuals.copy()
                proj_copy["player_id"] = proj_copy["player_id"].astype(str).str.strip()
                act_copy["player_id"] = act_copy["player_id"].astype(str).str.strip()
                # Deduplicate actuals on player_id — keep highest-scoring row
                # for the rare case of two identical IDs in the same week.
                act_copy = act_copy.sort_values(
                    "actual_points", ascending=False
                ).drop_duplicates(subset=["player_id"], keep="first")
                merged = proj_copy.merge(
                    act_copy[["player_id", "actual_points"]],
                    on="player_id",
                    how="inner",
                )
            else:
                # Fallback: name join with explicit dedup on player_name to
                # prevent fan-out.  The merge key is player_name, so we must
                # dedup on player_name — not on (player_name, recent_team),
                # which would still leave multiple rows per name.  Keep the
                # row with the highest actual_points for each name.
                act_copy = actuals.copy()
                act_copy = act_copy.sort_values(
                    "actual_points", ascending=False
                ).drop_duplicates(subset=["player_name"], keep="first")
                merged = projections.merge(
                    act_copy[["player_name", "actual_points"]],
                    on="player_name",
                    how="inner",
                )
            if merged.empty:
                print("SKIP (no matches)")
                continue

            merged["season"] = season
            merged["week"] = week
            merged["error"] = merged["projected_points"] - merged["actual_points"]
            merged["abs_error"] = merged["error"].abs()
            results.append(merged)
            total_weeks += 1
            print(f"OK ({len(merged)} players)")

    if not results:
        return pd.DataFrame()

    print(f"\nBacktest complete: {total_weeks} weeks processed")
    return pd.concat(results, ignore_index=True)


def print_summary(results_df: pd.DataFrame, scoring_format: str):
    """Print backtesting summary statistics."""
    if results_df.empty:
        print("No results to summarize.")
        return

    print(f"\n{'=' * 70}")
    print(f"BACKTEST RESULTS — {scoring_format.upper()}")
    print(f"{'=' * 70}")

    # Overall metrics
    mae = results_df["abs_error"].mean()
    rmse = np.sqrt((results_df["error"] ** 2).mean())
    corr = results_df[["projected_points", "actual_points"]].corr().iloc[0, 1]
    bias = results_df["error"].mean()
    n_players = len(results_df)
    n_weeks = results_df[["season", "week"]].drop_duplicates().shape[0]

    print(f"\nOverall ({n_players:,} player-weeks across {n_weeks} weeks):")
    print(f"  MAE:         {mae:.2f} pts")
    print(f"  RMSE:        {rmse:.2f} pts")
    print(f"  Correlation: {corr:.3f}")
    print(
        f"  Avg Bias:    {bias:+.2f} pts {'(over-projects)' if bias > 0 else '(under-projects)'}"
    )

    # Per-position breakdown
    print(f"\nPer-Position Breakdown:")
    print(
        f"  {'Position':<10} {'MAE':>8} {'RMSE':>8} {'Corr':>8} {'Bias':>8} {'Count':>8}"
    )
    print(f"  {'-' * 50}")

    for pos in ["QB", "RB", "WR", "TE"]:
        pos_data = results_df[results_df["position"] == pos]
        if pos_data.empty:
            continue
        p_mae = pos_data["abs_error"].mean()
        p_rmse = np.sqrt((pos_data["error"] ** 2).mean())
        p_corr = pos_data[["projected_points", "actual_points"]].corr().iloc[0, 1]
        p_bias = pos_data["error"].mean()
        print(
            f"  {pos:<10} {p_mae:>8.2f} {p_rmse:>8.2f} {p_corr:>8.3f} {p_bias:>+8.2f} {len(pos_data):>8,}"
        )

    # ML vs heuristic breakdown (if projection_source column exists)
    if "projection_source" in results_df.columns:
        print(f"\nBy Projection Source:")
        print(f"  {'Source':<12} {'MAE':>8} {'RMSE':>8} {'Bias':>8} {'Count':>8}")
        print(f"  {'-' * 44}")
        for src in sorted(results_df["projection_source"].unique()):
            src_data = results_df[results_df["projection_source"] == src]
            s_mae = src_data["abs_error"].mean()
            s_rmse = np.sqrt((src_data["error"] ** 2).mean())
            s_bias = src_data["error"].mean()
            print(
                f"  {src:<12} {s_mae:>8.2f} {s_rmse:>8.2f} {s_bias:>+8.2f} {len(src_data):>8,}"
            )

    # Biggest misses
    print(f"\nTop 10 Biggest Misses:")
    top_misses = results_df.nlargest(10, "abs_error")
    for _, row in top_misses.iterrows():
        name = row.get("player_name", "Unknown")[:20]
        print(
            f"  {name:<22} {row['position']:<4} S{int(row['season'])} W{int(row['week']):>2}  "
            f"Proj: {row['projected_points']:>6.1f}  Actual: {row['actual_points']:>6.1f}  "
            f"Error: {row['error']:>+7.1f}"
        )


def main():
    formats = list_scoring_formats()
    parser = argparse.ArgumentParser(description="Backtest NFL Fantasy Projections")
    parser.add_argument(
        "--seasons",
        type=str,
        default="2023,2024",
        help="Comma-separated seasons to backtest (default: 2023,2024)",
    )
    parser.add_argument(
        "--weeks",
        type=str,
        default=None,
        help='Week range: "3-18" or "1,5,10" (default: 3-18)',
    )
    parser.add_argument(
        "--scoring",
        choices=formats,
        default="half_ppr",
        help="Scoring format (default: half_ppr)",
    )
    parser.add_argument(
        "--ml",
        action="store_true",
        help="Use ML router: QB/RB via XGB, WR/TE via hybrid residual",
    )
    parser.add_argument(
        "--constrain",
        action="store_true",
        help="Apply team-level constraints so player totals align with implied team totals",
    )
    parser.add_argument(
        "--full-features",
        action="store_true",
        help="Assemble full 466-col feature vector for ML residual correction (requires Silver data)",
    )
    parser.add_argument(
        "--output-dir",
        default="output/backtest",
        help="Output directory for results CSV",
    )
    parser.add_argument(
        "--vs-consensus",
        action="store_true",
        help=(
            "Join Sleeper consensus projections and print head-to-head "
            "benchmark: MAE, Spearman rank corr, Top-N hit rate per position. "
            "Requires Silver external_projections data (run silver "
            "transformation first). Filters to consensus_proj >= 5 pts, "
            "weeks 3-18, positions QB/RB/WR/TE."
        ),
    )
    parser.add_argument(
        "--silver-root",
        default=None,
        help=(
            "Root path for Silver external projections "
            "(default: data/silver/external_projections relative to repo root)."
        ),
    )
    args = parser.parse_args()

    seasons = [int(s) for s in args.seasons.split(",")]
    weeks = parse_weeks(args.weeks) if args.weeks else None

    full_features = getattr(args, "full_features", False)
    vs_consensus = getattr(args, "vs_consensus", False)

    print(f"\nNFL Fantasy Projection Backtester")
    mode = "ML (QB/RB→XGB, WR/TE→Hybrid Residual)" if args.ml else "Heuristic"
    constrain_label = " | Constraints: ON" if args.constrain else ""
    features_label = " | Full Features: ON" if full_features else ""
    consensus_label = " | vs-Consensus: ON" if vs_consensus else ""
    print(
        f"Seasons: {seasons} | Scoring: {args.scoring.upper()} | Mode: {mode}"
        f"{constrain_label}{features_label}{consensus_label}"
    )
    if args.ml and not HAS_ML_ROUTER:
        print(
            "WARNING: --ml flag set but ml_projection_router not available; using heuristic"
        )
    if full_features and not HAS_FEATURE_ENGINEERING:
        print(
            "WARNING: --full-features flag set but player_feature_engineering not available"
        )
    if weeks:
        print(f"Weeks: {weeks}")
    print("=" * 60)

    # For consensus mode we always use weeks 3-18.
    backtest_weeks = weeks if not vs_consensus else (weeks or list(range(3, 19)))

    results = run_backtest(
        seasons,
        backtest_weeks,
        args.scoring,
        use_ml=args.ml,
        apply_constraints=args.constrain,
        full_features=full_features,
    )

    if results.empty:
        print("\nERROR: No backtest results generated.")
        return 1

    print_summary(results, args.scoring)

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ml_tag = "_ml" if args.ml else ""
    constrain_tag = "_constrained" if args.constrain else ""
    features_tag = "_fullfeatures" if full_features else ""
    consensus_tag = "_consensus" if vs_consensus else ""
    csv_path = os.path.join(
        args.output_dir,
        f"backtest_{args.scoring}{ml_tag}{constrain_tag}{features_tag}{consensus_tag}_{ts}.csv",
    )
    results.to_csv(csv_path, index=False)
    print(f"\nDetailed results saved to: {csv_path}")

    # --vs-consensus: load Silver consensus, join, report.
    if vs_consensus:
        project_root = os.path.join(os.path.dirname(__file__), "..")
        silver_root = args.silver_root or os.path.join(
            project_root, "data", "silver", "external_projections"
        )

        print(f"\nLoading Sleeper consensus from Silver: {silver_root}")
        consensus_df = load_consensus_for_seasons(
            seasons=seasons,
            weeks=backtest_weeks,
            scoring_format=args.scoring,
            silver_root=silver_root,
            source=_CONSENSUS_SOURCE,
        )

        if consensus_df.empty:
            print(
                "WARNING: No consensus data loaded from Silver. "
                "Run silver_external_projections_transformation.py first."
            )
        else:
            print(
                f"Loaded {len(consensus_df):,} consensus rows "
                f"({consensus_df['season'].nunique()} seasons, "
                f"{consensus_df[['season','week']].drop_duplicates().shape[0]} weeks)"
            )

            # Filter results to W3-18, skill positions only, before joining
            results_filtered = results[
                (results["week"] >= 3)
                & (results["week"] <= 18)
                & (results["position"].isin(_CONSENSUS_POSITIONS))
            ].copy()

            matched = join_consensus(results_filtered, consensus_df)

            if matched.empty:
                print(
                    "WARNING: No player-weeks matched between our results and "
                    "Sleeper consensus. Check that player_id formats align."
                )
            else:
                print_consensus_report(matched, args.scoring)

                # Save the matched frame too
                cons_csv = os.path.join(
                    args.output_dir,
                    f"consensus_matched_{args.scoring}_{ts}.csv",
                )
                matched.to_csv(cons_csv, index=False)
                print(f"\nConsensus-matched results saved to: {cons_csv}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
