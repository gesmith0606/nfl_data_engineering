#!/usr/bin/env python3
"""
Silver Layer - Advanced Player Profile Transformation Script

Reads Bronze NGS, PFR, and QBR data, joins onto a master player roster,
applies compute functions from player_advanced_analytics, merges into a
single wide DataFrame, and writes to the local Silver layer.

Usage:
    python scripts/silver_advanced_transformation.py --seasons 2023
    python scripts/silver_advanced_transformation.py --seasons 2020 2021 2022 2023 2024
"""

import sys
import os
import argparse
import glob as globmod
import logging
from datetime import datetime
from typing import List, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv

# Project root on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from player_advanced_analytics import (
    compute_ngs_receiving_profile,
    compute_ngs_passing_profile,
    compute_ngs_rushing_profile,
    compute_pfr_pressure_rate,
    compute_pfr_team_blitz_rate,
    compute_qbr_profile,
    log_nan_coverage,
)
from config import PLAYER_DATA_SEASONS, SILVER_PLAYER_S3_KEYS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")

# Team abbreviation normalization: map variant forms to canonical
TEAM_ABBR_NORM = {"LAR": "LA", "WSH": "WAS"}


# ---------------------------------------------------------------------------
# Local file helpers
# ---------------------------------------------------------------------------


def _read_local_bronze(subdir: str, season: int, prefix: str = "") -> pd.DataFrame:
    """Read the latest parquet file from a Bronze subdirectory.

    Args:
        subdir: Relative path within BRONZE_DIR (e.g., 'ngs/receiving').
        season: NFL season year.
        prefix: Optional filename prefix filter (e.g., 'qbr_weekly_').

    Returns:
        DataFrame with Bronze data, or empty DataFrame if not found.
    """
    pattern = os.path.join(
        BRONZE_DIR, subdir, f"season={season}", f"{prefix}*.parquet"
    )
    files = sorted(globmod.glob(pattern))
    if not files:
        return pd.DataFrame()
    return pd.read_parquet(files[-1])


def _normalize_team(df: pd.DataFrame, col: str = "team") -> pd.DataFrame:
    """Normalize team abbreviations (e.g., LAR -> LA, WSH -> WAS).

    Args:
        df: DataFrame with a team column.
        col: Name of the team column to normalize.

    Returns:
        DataFrame with normalized team abbreviations.
    """
    if col in df.columns:
        df[col] = df[col].replace(TEAM_ABBR_NORM)
    return df


def _normalize_name(df: pd.DataFrame, col: str) -> pd.DataFrame:
    """Add a normalized name column for join matching.

    Applies .str.strip().str.lower() and stores result as {col}_norm.

    Args:
        df: DataFrame with a name column.
        col: Name column to normalize.

    Returns:
        DataFrame with added {col}_norm column.
    """
    if col in df.columns:
        df[f"{col}_norm"] = df[col].str.strip().str.lower()
    return df


def _save_local_silver(df: pd.DataFrame, key: str, ts: str) -> str:
    """Save a DataFrame to the local Silver directory.

    Args:
        df: DataFrame to save.
        key: Relative path within the Silver directory.
        ts: Timestamp string (unused but kept for API compatibility).

    Returns:
        Absolute path to the saved file.
    """
    path = os.path.join(SILVER_DIR, key)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    df.to_parquet(path, index=False)
    print(f"    Saved -> data/silver/{key}")
    return path


def _try_s3_upload(df: pd.DataFrame, bucket: str, key: str) -> bool:
    """Attempt to upload to S3. Returns True on success, False on failure.

    Args:
        df: DataFrame to upload.
        bucket: S3 bucket name.
        key: S3 object key.

    Returns:
        True if upload succeeded, False otherwise.
    """
    try:
        import boto3

        s3 = boto3.client("s3", region_name="us-east-2")
        s3.head_bucket(Bucket=bucket)
        tmp = f"/tmp/{key.replace('/', '_')}.parquet"
        df.to_parquet(tmp, index=False)
        s3.upload_file(tmp, bucket, key)
        os.remove(tmp)
        print(f"    Uploaded -> s3://{bucket}/{key}")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# NGS join helper
# ---------------------------------------------------------------------------


def _merge_ngs_source(
    master: pd.DataFrame,
    ngs_df: pd.DataFrame,
    compute_fn,
    source_name: str,
) -> pd.DataFrame:
    """Compute NGS profile and left-merge onto master by GSIS ID + season + week.

    Args:
        master: Master roster DataFrame.
        ngs_df: Raw NGS Bronze DataFrame.
        compute_fn: One of compute_ngs_{receiving,passing,rushing}_profile.
        source_name: Label for logging (e.g., 'NGS receiving').

    Returns:
        Updated master with NGS columns merged.
    """
    if ngs_df.empty:
        logger.warning("No %s data found; columns will be NaN", source_name)
        return master

    profile = compute_fn(ngs_df)
    if profile.empty:
        logger.warning("%s profile produced no rows", source_name)
        return master

    # Drop non-key/non-metric columns before merge to avoid clashes
    merge_keys = ["player_gsis_id", "season", "week"]
    profile_cols = merge_keys + [
        c for c in profile.columns if c not in merge_keys
    ]
    profile = profile[profile_cols]

    # De-duplicate profile on merge keys (take first occurrence)
    profile = profile.drop_duplicates(subset=merge_keys, keep="first")

    # Drop columns that already exist in master to avoid _x/_y suffixes
    existing = set(master.columns) - set(merge_keys)
    overlap = [c for c in profile.columns if c in existing]
    if overlap:
        logger.info(
            "%s: dropping %d overlapping columns before merge: %s",
            source_name,
            len(overlap),
            overlap,
        )
        profile = profile.drop(columns=overlap)

    before = len(master)
    master = master.merge(profile, on=merge_keys, how="left")
    assert len(master) == before, (
        f"{source_name} merge changed row count: {before} -> {len(master)}"
    )
    logger.info(
        "%s merged: %d profile rows onto %d master rows",
        source_name,
        len(profile),
        before,
    )
    return master


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------


def process_season(season: int) -> Optional[pd.DataFrame]:
    """Process a single season: read Bronze, join, merge, return wide DataFrame.

    Args:
        season: NFL season year.

    Returns:
        Merged DataFrame with all advanced columns, or None if no roster data.
    """
    print(f"\n{'=' * 60}")
    print(f"Processing Season {season}")
    print("=" * 60)

    # -----------------------------------------------------------------------
    # 1. Read master player roster
    # -----------------------------------------------------------------------
    print("  Loading player roster...")
    roster_df = _read_local_bronze("players/weekly", season)
    if roster_df.empty:
        logger.error("No player roster data for season %d; skipping", season)
        return None

    # Keep relevant columns and rename player_id -> player_gsis_id
    keep_cols = [
        "player_id",
        "player_display_name",
        "position",
        "recent_team",
        "season",
        "week",
    ]
    available_keep = [c for c in keep_cols if c in roster_df.columns]
    master = roster_df[available_keep].copy()

    if "player_id" in master.columns:
        master = master.rename(columns={"player_id": "player_gsis_id"})

    master_rows = len(master)
    print(f"    Roster: {master_rows:,} player-weeks")

    # Normalize master for name+team joins
    master = _normalize_name(master, "player_display_name")
    master = _normalize_team(master, "recent_team")

    # -----------------------------------------------------------------------
    # 2. Merge NGS data (join by player_gsis_id + season + week)
    # -----------------------------------------------------------------------
    print("  Processing NGS data...")

    ngs_recv = _read_local_bronze("ngs/receiving", season)
    master = _merge_ngs_source(
        master, ngs_recv, compute_ngs_receiving_profile, "NGS receiving"
    )

    ngs_pass = _read_local_bronze("ngs/passing", season)
    master = _merge_ngs_source(
        master, ngs_pass, compute_ngs_passing_profile, "NGS passing"
    )

    ngs_rush = _read_local_bronze("ngs/rushing", season)
    master = _merge_ngs_source(
        master, ngs_rush, compute_ngs_rushing_profile, "NGS rushing"
    )

    # -----------------------------------------------------------------------
    # 3. Merge PFR pressure rate (name+team join)
    # -----------------------------------------------------------------------
    print("  Processing PFR pressure data...")
    pfr_pass = _read_local_bronze("pfr/weekly/pass", season)
    if not pfr_pass.empty:
        # Rename pfr_player_name -> player for compute function compatibility
        if "pfr_player_name" in pfr_pass.columns:
            pfr_pass = pfr_pass.rename(columns={"pfr_player_name": "player"})

        # PFR has no player_gsis_id -- create synthetic ID from name+team
        # so that apply_player_rolling can group correctly
        if "player_gsis_id" not in pfr_pass.columns:
            pfr_pass["player_gsis_id"] = (
                pfr_pass["player"].str.strip().str.lower()
                + "_"
                + pfr_pass["team"].str.strip().str.lower()
            )

        _normalize_team(pfr_pass, "team")

        pfr_profile = compute_pfr_pressure_rate(pfr_pass)
        if not pfr_profile.empty:
            # Name-based join: normalize names on both sides
            pfr_profile = _normalize_name(pfr_profile, "player")
            pfr_profile = _normalize_team(pfr_profile, "team")

            # Build join keys
            pfr_merge_cols = [
                c for c in pfr_profile.columns
                if c.startswith("pfr_") or c in [
                    "player_norm", "team", "season", "week"
                ]
            ]
            pfr_join = pfr_profile[pfr_merge_cols].copy()
            pfr_join = pfr_join.rename(columns={
                "player_norm": "player_display_name_norm",
                "team": "recent_team",
            })
            pfr_join = pfr_join.drop_duplicates(
                subset=["player_display_name_norm", "recent_team", "season", "week"],
                keep="first",
            )

            before = len(master)
            master = master.merge(
                pfr_join,
                on=["player_display_name_norm", "recent_team", "season", "week"],
                how="left",
            )
            assert len(master) == before, (
                f"PFR pressure merge changed row count: {before} -> {len(master)}"
            )

            matched = master[
                master[[c for c in pfr_join.columns if c.startswith("pfr_")][0]].notna()
            ].shape[0] if any(c.startswith("pfr_") for c in pfr_join.columns) else 0
            match_pct = (matched / before) * 100
            logger.info(
                "PFR pressure match rate: %.1f%% (%d/%d player-weeks)",
                match_pct,
                matched,
                before,
            )
            if match_pct < 50:
                logger.warning(
                    "PFR pressure match rate below 50%% -- check name normalization"
                )
    else:
        logger.warning("No PFR pass data for season %d; pfr_ columns will be NaN", season)

    # -----------------------------------------------------------------------
    # 4. Merge PFR team blitz rate (team-level join)
    # -----------------------------------------------------------------------
    print("  Processing PFR team blitz data...")
    pfr_def = _read_local_bronze("pfr/weekly/def", season)
    if not pfr_def.empty:
        _normalize_team(pfr_def, "team")
        blitz_profile = compute_pfr_team_blitz_rate(pfr_def)

        if not blitz_profile.empty:
            # Team-level join: rename team -> recent_team for merge
            blitz_merge = blitz_profile.rename(columns={"team": "recent_team"})
            blitz_cols = ["recent_team", "season", "week"] + [
                c for c in blitz_merge.columns if c.startswith("pfr_def_")
            ]
            blitz_merge = blitz_merge[blitz_cols].drop_duplicates(
                subset=["recent_team", "season", "week"], keep="first"
            )

            before = len(master)
            master = master.merge(
                blitz_merge,
                on=["recent_team", "season", "week"],
                how="left",
            )
            assert len(master) == before, (
                f"PFR blitz merge changed row count: {before} -> {len(master)}"
            )
            logger.info(
                "PFR team blitz merged: %d team-weeks onto %d master rows",
                len(blitz_merge),
                before,
            )
    else:
        logger.warning(
            "No PFR def data for season %d; pfr_def_ columns will be NaN", season
        )

    # -----------------------------------------------------------------------
    # 5. Merge QBR (name+team join, QB-only)
    # -----------------------------------------------------------------------
    print("  Processing QBR data...")
    qbr_df = _read_local_bronze("qbr", season, prefix="qbr_weekly_")
    if not qbr_df.empty:
        # QBR raw data has both 'team' (full name) and 'team_abb' (abbreviation).
        # Drop the full-name 'team' column before renaming team_abb -> team
        # to avoid duplicate 'team' columns.
        if "team_abb" in qbr_df.columns and "team" in qbr_df.columns:
            qbr_df = qbr_df.drop(columns=["team"])

        # Rename columns for compute function compatibility
        rename_map = {}
        if "name_display" in qbr_df.columns:
            rename_map["name_display"] = "player"
        if "team_abb" in qbr_df.columns:
            rename_map["team_abb"] = "team"
        if "game_week" in qbr_df.columns:
            rename_map["game_week"] = "week"
        if rename_map:
            qbr_df = qbr_df.rename(columns=rename_map)

        # Create synthetic player_gsis_id from name+team for rolling groupby
        if "player_gsis_id" not in qbr_df.columns:
            qbr_df["player_gsis_id"] = (
                qbr_df["player"].str.strip().str.lower()
                + "_"
                + qbr_df["team"].str.strip().str.lower()
            )

        _normalize_team(qbr_df, "team")

        qbr_profile = compute_qbr_profile(qbr_df)
        if not qbr_profile.empty:
            qbr_profile = _normalize_name(qbr_profile, "player")
            qbr_profile = _normalize_team(qbr_profile, "team")

            qbr_metric_cols = [
                c for c in qbr_profile.columns if c.startswith("qbr_")
            ]
            qbr_merge_cols = [
                "player_norm", "team", "season", "week"
            ] + qbr_metric_cols
            qbr_join = qbr_profile[[
                c for c in qbr_merge_cols if c in qbr_profile.columns
            ]].copy()
            qbr_join = qbr_join.rename(columns={
                "player_norm": "player_display_name_norm",
                "team": "recent_team",
            })
            qbr_join = qbr_join.drop_duplicates(
                subset=["player_display_name_norm", "recent_team", "season", "week"],
                keep="first",
            )

            before = len(master)
            master = master.merge(
                qbr_join,
                on=["player_display_name_norm", "recent_team", "season", "week"],
                how="left",
            )
            assert len(master) == before, (
                f"QBR merge changed row count: {before} -> {len(master)}"
            )

            # Set QBR columns to NaN for non-QB rows
            if "position" in master.columns and qbr_metric_cols:
                # Find all qbr_ columns in master (including rolling)
                all_qbr_cols = [
                    c for c in master.columns if c.startswith("qbr_")
                ]
                master.loc[master["position"] != "QB", all_qbr_cols] = np.nan

            logger.info(
                "QBR merged: %d QB-weeks onto %d master rows (QB-only)",
                len(qbr_join),
                before,
            )
    else:
        logger.warning(
            "No QBR weekly data for season %d; qbr_ columns will be NaN", season
        )

    # -----------------------------------------------------------------------
    # 6. Log NaN coverage and validate
    # -----------------------------------------------------------------------
    advanced_cols = [
        c for c in master.columns
        if c.startswith(("ngs_", "pfr_", "qbr_"))
        and "_norm" not in c
    ]
    log_nan_coverage(master, advanced_cols)

    # Verify row count preservation
    assert len(master) == master_rows, (
        f"Row count mismatch: expected {master_rows}, got {len(master)}"
    )
    print(f"    Output: {len(master):,} rows, {len(advanced_cols)} advanced columns")
    print(f"    Row count verified: {len(master)} == {master_rows} (no drops)")

    return master


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """Parse CLI arguments and run Silver advanced player transformation."""
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="NFL Silver Layer - Advanced Player Profile Transformation"
    )
    parser.add_argument("--season", type=int, help="Single NFL season to transform")
    parser.add_argument(
        "--seasons", type=int, nargs="+", help="Multiple seasons to transform"
    )
    parser.add_argument(
        "--no-s3",
        action="store_true",
        help="Skip S3 upload even if credentials are available",
    )
    args = parser.parse_args()

    seasons: List[int] = args.seasons or (
        [args.season] if args.season else PLAYER_DATA_SEASONS
    )

    # Try S3 only if credentials are available and --no-s3 not set
    s3_bucket: Optional[str] = None
    if not args.no_s3:
        try:
            import config as cfg

            access_key = os.getenv("AWS_ACCESS_KEY_ID")
            secret_key = os.getenv("AWS_SECRET_ACCESS_KEY")
            if access_key and secret_key:
                s3_bucket = os.getenv("S3_BUCKET_SILVER", cfg.S3_BUCKET_SILVER)
        except Exception:
            pass

    print("NFL Silver Layer - Advanced Player Profile Transformation")
    print(f"Seasons: {seasons}")
    print(f"Storage: local" + (f" + S3 ({s3_bucket})" if s3_bucket else ""))

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results: List[str] = []
    warnings: List[str] = []

    for season in seasons:
        result = process_season(season)
        if result is not None:
            key = SILVER_PLAYER_S3_KEYS["advanced_profiles"].format(
                season=season, ts=ts
            )
            _save_local_silver(result, key, ts)
            if s3_bucket:
                _try_s3_upload(result, s3_bucket, key)
            results.append(f"  season={season}: {len(result):,} rows")
        else:
            warnings.append(f"  season={season}: skipped (no roster data)")

    print(f"\n{'=' * 60}")
    print("Summary")
    print("=" * 60)
    print(f"Seasons processed: {len(results)}")
    for r in results:
        print(r)
    if warnings:
        print(f"Warnings ({len(warnings)}):")
        for w in warnings:
            print(w)
    print("\nSilver advanced player transformation complete.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
