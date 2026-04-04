#!/usr/bin/env python3
"""Compute all graph-derived features from PBP participation data.

Loads Bronze PBP participation, PBP, rosters, depth charts, injuries,
player_weekly, PFR defensive, and schedules data. Computes WR matchup,
OL/RB, TE, scheme, and injury cascade features per season. Outputs
individual and combined Silver parquet files under
data/silver/graph_features/season=YYYY/.

Usage:
    python scripts/compute_graph_features.py --seasons 2020 2021 2022 2023 2024 2025
"""

import argparse
import datetime
import glob
import logging
import os
import sys
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Ensure src/ is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_feature_extraction import (
    GRAPH_FEATURE_COLUMNS,
    OL_RB_FEATURE_COLUMNS,
    SCHEME_FEATURE_COLUMNS,
    TE_FEATURE_COLUMNS,
    WR_MATCHUP_FEATURE_COLUMNS,
    compute_graph_features_from_data,
    compute_ol_rb_features,
    compute_scheme_features,
    compute_te_features,
    compute_wr_matchup_features,
)
from graph_qb_wr_chemistry import (
    QB_WR_CHEMISTRY_FEATURE_COLUMNS,
    build_qb_wr_chemistry,
    compute_chemistry_features,
)
from graph_participation import (
    identify_cbs_on_field,
    identify_ol_on_field,
    parse_participation_players,
)
from graph_game_script import (
    GAME_SCRIPT_FEATURE_COLUMNS,
    compute_game_script_features,
    compute_game_script_usage,
)
from graph_red_zone import (
    RED_ZONE_FEATURE_COLUMNS,
    compute_red_zone_features,
    compute_red_zone_usage,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BRONZE_DIR = os.path.join(BASE_DIR, "data", "bronze")
SILVER_DIR = os.path.join(BASE_DIR, "data", "silver")
GRAPH_FEATURES_DIR = os.path.join(SILVER_DIR, "graph_features")


# ---------------------------------------------------------------------------
# Bronze data loaders
# ---------------------------------------------------------------------------


def _load_bronze(subdir: str, season: int) -> pd.DataFrame:
    """Load latest Bronze parquet for a subdirectory and season.

    Args:
        subdir: Relative path under data/bronze/ (e.g. 'pbp', 'players/weekly').
        season: NFL season year.

    Returns:
        DataFrame or empty DataFrame if not found.
    """
    pattern = os.path.join(BRONZE_DIR, subdir, f"season={season}", "*.parquet")
    files = sorted(glob.glob(pattern))
    if not files:
        # Try week-partitioned layout
        pattern_w = os.path.join(
            BRONZE_DIR, subdir, f"season={season}", "week=*", "*.parquet"
        )
        files_w = sorted(glob.glob(pattern_w))
        if files_w:
            return pd.concat([pd.read_parquet(f) for f in files_w], ignore_index=True)
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _load_multi_season(subdir: str, seasons: List[int]) -> pd.DataFrame:
    """Load and concatenate Bronze data across multiple seasons.

    Args:
        subdir: Relative path under data/bronze/.
        seasons: List of season years.

    Returns:
        Concatenated DataFrame.
    """
    dfs = []
    for s in seasons:
        df = _load_bronze(subdir, s)
        if not df.empty:
            if "season" not in df.columns:
                df["season"] = s
            dfs.append(df)
    return pd.concat(dfs, ignore_index=True) if dfs else pd.DataFrame()


# ---------------------------------------------------------------------------
# Per-season feature computation
# ---------------------------------------------------------------------------


def compute_season_features(
    season: int,
    all_seasons: List[int],
) -> Dict[str, pd.DataFrame]:
    """Compute all graph features for a single season.

    Returns a dict mapping feature group name to its DataFrame:
        'wr_matchup', 'ol_rb', 'te', 'scheme', 'injury_cascade'.

    Args:
        season: Target season.
        all_seasons: All seasons being processed (for historical context).

    Returns:
        Dict of feature DataFrames.
    """
    logger.info("=" * 60)
    logger.info("Computing graph features for season %d", season)
    logger.info("=" * 60)

    # Load data for this season
    participation_df = _load_bronze("pbp_participation", season)
    pbp_df = _load_bronze("pbp", season)
    rosters_df = _load_bronze("players/rosters", season)
    depth_charts_df = _load_bronze("depth_charts", season)
    injuries_df = _load_bronze("players/injuries", season)
    player_weekly_df = _load_bronze("players/weekly", season)
    pfr_def_df = _load_bronze("pfr/weekly/def", season)
    schedules_df = _load_bronze("schedules", season)

    logger.info(
        "Loaded data — participation: %d, pbp: %d, rosters: %d, "
        "depth_charts: %d, injuries: %d, weekly: %d, pfr_def: %d, schedules: %d",
        len(participation_df),
        len(pbp_df),
        len(rosters_df),
        len(depth_charts_df),
        len(injuries_df),
        len(player_weekly_df),
        len(pfr_def_df),
        len(schedules_df),
    )

    results: Dict[str, pd.DataFrame] = {}

    # --- Parse participation data ---
    parsed_participation = pd.DataFrame()
    if not participation_df.empty and not rosters_df.empty:
        logger.info("Parsing participation data...")
        parsed_participation = parse_participation_players(participation_df, rosters_df)
        logger.info(
            "Parsed %d participation rows (%d unique players)",
            len(parsed_participation),
            (
                parsed_participation["player_gsis_id"].nunique()
                if not parsed_participation.empty
                else 0
            ),
        )

    # --- 1. WR matchup features ---
    logger.info("Computing WR matchup features...")
    # Need PBP data from prior seasons too for historical EPA
    prior_seasons = [s for s in all_seasons if s <= season]
    pbp_multi = _load_multi_season("pbp", prior_seasons)
    pw_multi = _load_multi_season("players/weekly", prior_seasons)

    wr_dfs = []
    if not pbp_multi.empty and not pw_multi.empty:
        weeks = (
            sorted(player_weekly_df["week"].dropna().unique())
            if not player_weekly_df.empty
            else []
        )
        for week in weeks:
            week_int = int(week)
            if week_int < 2:
                continue
            wr_feat = compute_wr_matchup_features(pbp_multi, pw_multi, season, week_int)
            if not wr_feat.empty:
                wr_dfs.append(wr_feat)

    results["wr_matchup"] = (
        pd.concat(wr_dfs, ignore_index=True) if wr_dfs else pd.DataFrame()
    )
    logger.info("WR matchup: %d rows", len(results["wr_matchup"]))

    # --- 2. OL/RB features ---
    logger.info("Computing OL/RB features...")
    ol_dfs = []
    if (
        not pbp_df.empty
        and not parsed_participation.empty
        and not player_weekly_df.empty
    ):
        weeks = sorted(player_weekly_df["week"].dropna().unique())
        for week in weeks:
            week_int = int(week)
            if week_int < 2:
                continue
            ol_feat = compute_ol_rb_features(
                pbp_df, parsed_participation, player_weekly_df, season, week_int
            )
            if not ol_feat.empty:
                ol_dfs.append(ol_feat)

    results["ol_rb"] = (
        pd.concat(ol_dfs, ignore_index=True) if ol_dfs else pd.DataFrame()
    )
    logger.info("OL/RB: %d rows", len(results["ol_rb"]))

    # --- 3. TE features ---
    logger.info("Computing TE features...")
    te_df = pd.DataFrame()
    if not pw_multi.empty and not rosters_df.empty:
        te_df = compute_te_features(
            pw_multi,
            rosters_df,
            participation_df=(
                parsed_participation if not parsed_participation.empty else None
            ),
            season=season,
        )
    results["te"] = te_df
    logger.info("TE: %d rows", len(results["te"]))

    # --- 4. Scheme features ---
    logger.info("Computing scheme features...")
    scheme_df = pd.DataFrame()
    if not pbp_df.empty:
        scheme_df = compute_scheme_features(
            pbp_df, pfr_def_df, rosters_df, schedules_df
        )
    results["scheme"] = scheme_df
    logger.info("Scheme: %d rows", len(results["scheme"]))

    # --- 5. Injury cascade features ---
    logger.info("Computing injury cascade features...")
    injury_dfs = []
    if not injuries_df.empty and not player_weekly_df.empty:
        # Load prior seasons for historical absorption
        all_injuries = [injuries_df]
        all_pw = [player_weekly_df]
        for prior_s in range(max(season - 3, min(all_seasons)), season):
            pi = _load_bronze("players/injuries", prior_s)
            pp = _load_bronze("players/weekly", prior_s)
            if not pi.empty:
                all_injuries.append(pi)
            if not pp.empty:
                all_pw.append(pp)

        combined_injuries = pd.concat(all_injuries, ignore_index=True)
        combined_pw = pd.concat(all_pw, ignore_index=True)

        weeks = sorted(player_weekly_df["week"].dropna().unique())
        for week in weeks:
            week_int = int(week)
            if week_int < 2:
                continue
            cascade = compute_graph_features_from_data(
                combined_injuries, combined_pw, season, week_int
            )
            if not cascade.empty:
                injury_dfs.append(cascade)

    results["injury_cascade"] = (
        pd.concat(injury_dfs, ignore_index=True) if injury_dfs else pd.DataFrame()
    )
    logger.info("Injury cascade: %d rows", len(results["injury_cascade"]))

    # --- 6. QB-WR chemistry features ---
    logger.info("Computing QB-WR chemistry features...")
    chem_df = pd.DataFrame()
    if not pbp_multi.empty and not pw_multi.empty:
        pair_stats = build_qb_wr_chemistry(pbp_multi)
        if not pair_stats.empty:
            chem_df = compute_chemistry_features(pair_stats, pw_multi)
            # Filter to target season
            if not chem_df.empty and "season" in chem_df.columns:
                chem_df = chem_df[chem_df["season"] == season].copy()
    results["qb_wr_chemistry"] = chem_df
    logger.info("QB-WR chemistry: %d rows", len(results["qb_wr_chemistry"]))

    # --- 7. Red zone target network features ---
    logger.info("Computing red zone target network features...")
    rz_df = pd.DataFrame()
    if not pbp_multi.empty:
        rosters_for_rz = rosters_df if not rosters_df.empty else pd.DataFrame()
        rz_usage = compute_red_zone_usage(pbp_multi, rosters_for_rz)
        if not rz_usage.empty:
            rz_df = compute_red_zone_features(rz_usage, pw_multi)
            # Filter to target season
            if not rz_df.empty and "season" in rz_df.columns:
                rz_df = rz_df[rz_df["season"] == season].copy()
    results["red_zone"] = rz_df
    logger.info("Red zone: %d rows", len(results["red_zone"]))

    # --- 8. Game script role shift features ---
    logger.info("Computing game script features...")
    gs_df = pd.DataFrame()
    if not pbp_df.empty:
        usage_df = compute_game_script_usage(pbp_df)
        if not usage_df.empty:
            gs_df = compute_game_script_features(usage_df, schedules_df)
    results["game_script"] = gs_df
    logger.info("Game script: %d rows", len(results["game_script"]))

    return results


# ---------------------------------------------------------------------------
# Save to Silver
# ---------------------------------------------------------------------------


def save_features(
    results: Dict[str, pd.DataFrame],
    season: int,
) -> List[str]:
    """Save individual and combined feature files as Silver parquet.

    File naming matches what player_feature_engineering.py expects:
        graph_wr_matchup_TIMESTAMP.parquet
        graph_ol_rb_TIMESTAMP.parquet
        graph_te_matchup_TIMESTAMP.parquet
        graph_scheme_TIMESTAMP.parquet
        graph_injury_cascade_TIMESTAMP.parquet
        graph_all_features_TIMESTAMP.parquet

    Args:
        results: Dict of feature group name to DataFrame.
        season: NFL season year.

    Returns:
        List of saved file paths.
    """
    out_dir = os.path.join(GRAPH_FEATURES_DIR, f"season={season}")
    os.makedirs(out_dir, exist_ok=True)

    ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    saved: List[str] = []

    file_map = {
        "wr_matchup": f"graph_wr_matchup_{ts}.parquet",
        "ol_rb": f"graph_ol_rb_{ts}.parquet",
        "te": f"graph_te_matchup_{ts}.parquet",
        "scheme": f"graph_scheme_{ts}.parquet",
        "injury_cascade": f"graph_injury_cascade_{ts}.parquet",
        "qb_wr_chemistry": f"graph_qb_wr_chemistry_{ts}.parquet",
        "red_zone": f"graph_red_zone_{ts}.parquet",
        "game_script": f"graph_game_script_{ts}.parquet",
    }

    for key, filename in file_map.items():
        df = results.get(key, pd.DataFrame())
        if df.empty:
            logger.warning("No %s features for season %d — skipping", key, season)
            continue

        path = os.path.join(out_dir, filename)
        df.to_parquet(path, index=False)
        saved.append(path)
        logger.info("Saved %s: %d rows → %s", key, len(df), path)

    # Combined file: merge all player-level features
    combined_dfs = []
    join_cols = ["player_id", "season", "week"]

    for key in [
        "injury_cascade",
        "wr_matchup",
        "ol_rb",
        "te",
        "qb_wr_chemistry",
        "red_zone",
        "game_script",
    ]:
        df = results.get(key, pd.DataFrame())
        if not df.empty and all(c in df.columns for c in join_cols):
            combined_dfs.append(df)

    if combined_dfs:
        combined = combined_dfs[0]
        for df in combined_dfs[1:]:
            # Only keep feature columns (not duplicating join cols)
            feat_cols = [c for c in df.columns if c not in join_cols]
            combined = combined.merge(
                df[join_cols + feat_cols],
                on=join_cols,
                how="outer",
                suffixes=("", "_dup"),
            )
            dup_cols = [c for c in combined.columns if c.endswith("_dup")]
            combined = combined.drop(columns=dup_cols, errors="ignore")

        # Scheme features are team-level; join via team if possible
        scheme_df = results.get("scheme", pd.DataFrame())
        if not scheme_df.empty and "team" in scheme_df.columns:
            # We need a player -> team mapping to join scheme features
            # Use the most complete player_weekly for this season
            pw = _load_bronze("players/weekly", season)
            if not pw.empty and "recent_team" in pw.columns:
                player_teams = pw[
                    ["player_id", "recent_team", "season", "week"]
                ].rename(columns={"recent_team": "team"})
                scheme_cols = [
                    c for c in SCHEME_FEATURE_COLUMNS if c in scheme_df.columns
                ]
                if scheme_cols:
                    scheme_for_join = scheme_df[
                        ["team", "season", "week"] + scheme_cols
                    ]
                    player_scheme = player_teams.merge(
                        scheme_for_join,
                        on=["team", "season", "week"],
                        how="left",
                    )
                    player_scheme = player_scheme.drop(columns=["team"])
                    combined = combined.merge(
                        player_scheme,
                        on=join_cols,
                        how="left",
                        suffixes=("", "_scheme"),
                    )
                    dup_cols = [c for c in combined.columns if c.endswith("_scheme")]
                    combined = combined.drop(columns=dup_cols, errors="ignore")

        all_path = os.path.join(out_dir, f"graph_all_features_{ts}.parquet")
        combined.to_parquet(all_path, index=False)
        saved.append(all_path)
        logger.info(
            "Saved combined: %d rows, %d cols → %s",
            len(combined),
            len(combined.columns),
            all_path,
        )

    return saved


# ---------------------------------------------------------------------------
# Quality report
# ---------------------------------------------------------------------------


def report_quality(
    results: Dict[str, pd.DataFrame],
    season: int,
    player_weekly_df: Optional[pd.DataFrame] = None,
) -> None:
    """Print quality metrics for computed features.

    Args:
        results: Dict of feature group name to DataFrame.
        season: NFL season year.
        player_weekly_df: Optional player_weekly for coverage analysis.
    """
    print(f"\n{'='*60}")
    print(f"  Quality Report — Season {season}")
    print(f"{'='*60}")

    for key, df in results.items():
        if df.empty:
            print(f"\n  {key}: EMPTY")
            continue

        print(f"\n  {key}: {len(df)} rows, {len(df.columns)} columns")

        # Non-null rates for feature columns
        feat_cols = [
            c for c in df.columns if c not in ["player_id", "season", "week", "team"]
        ]
        for col in feat_cols:
            if col in df.columns:
                non_null = df[col].notna().sum()
                rate = non_null / len(df) * 100 if len(df) > 0 else 0
                print(f"    {col}: {non_null}/{len(df)} ({rate:.1f}% non-null)")

    # Position-level coverage analysis
    if player_weekly_df is not None and not player_weekly_df.empty:
        pw = player_weekly_df[player_weekly_df["season"] == season]
        if not pw.empty:
            print(f"\n  Position Coverage:")

            # WR coverage
            wr_pw = pw[pw["position"] == "WR"][["player_id", "week"]].drop_duplicates()
            wr_feat = results.get("wr_matchup", pd.DataFrame())
            if not wr_feat.empty and not wr_pw.empty:
                merged = wr_pw.merge(
                    wr_feat[["player_id", "week"]].drop_duplicates(),
                    on=["player_id", "week"],
                    how="left",
                    indicator=True,
                )
                coverage = (merged["_merge"] == "both").mean() * 100
                print(f"    WR player-weeks with features: {coverage:.1f}%")
            else:
                print(f"    WR player-weeks with features: 0.0%")

            # RB coverage
            rb_pw = pw[pw["position"] == "RB"][["player_id", "week"]].drop_duplicates()
            ol_feat = results.get("ol_rb", pd.DataFrame())
            if not ol_feat.empty and not rb_pw.empty:
                merged = rb_pw.merge(
                    ol_feat[["player_id", "week"]].drop_duplicates(),
                    on=["player_id", "week"],
                    how="left",
                    indicator=True,
                )
                coverage = (merged["_merge"] == "both").mean() * 100
                print(f"    RB player-weeks with OL features: {coverage:.1f}%")
            else:
                print(f"    RB player-weeks with OL features: 0.0%")

            # TE coverage
            te_pw = pw[pw["position"] == "TE"][["player_id", "week"]].drop_duplicates()
            te_feat = results.get("te", pd.DataFrame())
            if not te_feat.empty and not te_pw.empty:
                merged = te_pw.merge(
                    te_feat[["player_id", "week"]].drop_duplicates(),
                    on=["player_id", "week"],
                    how="left",
                    indicator=True,
                )
                coverage = (merged["_merge"] == "both").mean() * 100
                print(f"    TE player-weeks with features: {coverage:.1f}%")
            else:
                print(f"    TE player-weeks with features: 0.0%")

    # Temporal safety check: week 1 should have NaN for rolling features
    rolling_features = [
        "def_pass_epa_allowed",
        "def_run_epa_allowed",
        "def_front_quality_vs_run",
        "te_red_zone_target_share",
        "def_te_fantasy_pts_allowed",
    ]
    for key, df in results.items():
        if df.empty or "week" not in df.columns:
            continue
        week1 = df[df["week"] == 1]
        if week1.empty:
            continue
        for col in rolling_features:
            if col in week1.columns:
                non_null_w1 = week1[col].notna().sum()
                if non_null_w1 > 0:
                    print(
                        f"  WARNING: {key}.{col} has {non_null_w1} non-null "
                        f"values in week 1 (possible temporal leak)"
                    )
                else:
                    print(f"  OK: {key}.{col} is all NaN in week 1 (temporal safe)")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point for computing graph features."""
    parser = argparse.ArgumentParser(
        description="Compute graph-derived features from PBP participation data."
    )
    parser.add_argument(
        "--seasons",
        nargs="+",
        type=int,
        required=True,
        help="Seasons to process (e.g. 2020 2021 2022 2023 2024 2025).",
    )
    args = parser.parse_args()

    seasons = sorted(args.seasons)
    logger.info("Computing graph features for seasons: %s", seasons)

    total_files: List[str] = []
    total_start = time.time()

    for season in seasons:
        season_start = time.time()

        results = compute_season_features(season, seasons)
        saved = save_features(results, season)
        total_files.extend(saved)

        # Load player_weekly for quality report
        pw = _load_bronze("players/weekly", season)
        report_quality(results, season, pw)

        elapsed = time.time() - season_start
        logger.info("Season %d completed in %.1f seconds", season, elapsed)

    # Final summary
    total_elapsed = time.time() - total_start
    print(f"\n{'='*60}")
    print(f"  FINAL SUMMARY")
    print(f"{'='*60}")
    print(f"  Seasons processed: {seasons}")
    print(f"  Files created: {len(total_files)}")
    print(f"  Total time: {total_elapsed:.1f} seconds")

    total_size = 0
    for f in total_files:
        if os.path.exists(f):
            size = os.path.getsize(f)
            total_size += size
            print(f"    {os.path.basename(f)}: {size / 1024:.1f} KB")

    print(f"  Total size: {total_size / 1024:.1f} KB")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
