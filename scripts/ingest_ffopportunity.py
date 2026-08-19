#!/usr/bin/env python3
"""
Bronze ffopportunity ingestion + player-week Silver feature aggregation.

Downloads the ffverse/ffopportunity `latest-data` GitHub release assets
(``ep_pbp_pass_{season}.parquet`` / ``ep_pbp_rush_{season}.parquet`` —
play-level Expected Fantasy Points model outputs, xgboost-trained on
nflverse play-by-play) and aggregates them into a per-player-week Silver
feature table: expected passing/rushing/receiving yards + fantasy points,
actual-vs-expected residuals, and opportunity counts (targets/carries).

LICENSING (verified against the source README, 2026-08-18 — corrects the
GPL-3.0 assumption in the original task brief): the ffopportunity *R
package code* is GPL-3.0, but the *model outputs / data* (what this script
consumes) are licensed CC BY-SA 4.0
(https://creativecommons.org/licenses/by-sa/4.0/). See
.planning/FFOPPORTUNITY_COVERAGE.md for the full size/licensing decision.

Storage:
    Bronze (LOCAL-ONLY, gitignored): data/bronze/ffopportunity/season=YYYY/
        ep_pbp_pass_{season}.parquet, ep_pbp_rush_{season}.parquet
    Silver (committed, small aggregate): data/silver/ffopportunity_features/season=YYYY/
        ffopportunity_features_{season}.parquet

Usage:
    python scripts/ingest_ffopportunity.py
    python scripts/ingest_ffopportunity.py --seasons 2023 2024 2025
    python scripts/ingest_ffopportunity.py --force-download
"""

import argparse
import logging
import os
import subprocess
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from src.config import PLAYER_DATA_SEASONS, SCORING_CONFIGS  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze", "ffopportunity")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver", "ffopportunity_features")

GH_REPO = "ffverse/ffopportunity"
GH_TAG = "latest-data"

# "Expected fantasy points" is an opportunity/efficiency signal, not a
# league-scoring choice — no PPR reception bonus is baked in here (see
# `receptions` for the raw count so downstream consumers can add their own
# league's reception credit). Standard scoring's non-reception constants
# (yardage/TD/INT) are identical across ppr/half_ppr/standard in
# SCORING_CONFIGS, so "standard" is just a stable source of those shared
# constants, imported read-only from the existing src.config module.
SCORING = SCORING_CONFIGS["standard"]

# Feature column contract for the per-player-week Silver table. Keep this
# list in sync with build_player_week_features() and
# tests/test_ingest_ffopportunity.py::test_feature_column_contract.
FEATURE_COLUMNS = [
    "player_id",
    "season",
    "week",
    "team",
    "position",
    # Opportunity counts
    "pass_attempts",
    "targets",
    "carries",
    # Actual production
    "completions",
    "pass_yards",
    "receptions",
    "rec_yards",
    "rush_yards",
    "interceptions",
    "total_tds",
    # Expected production (ffopportunity model outputs)
    "exp_pass_yards",
    "exp_rec_yards",
    "exp_rush_yards",
    "exp_total_tds",
    # Expected fantasy points (standard scoring constants; no PPR bonus)
    "exp_pass_fantasy_points",
    "exp_rec_fantasy_points",
    "exp_rush_fantasy_points",
    "exp_fantasy_points_total",
    # Actual fantasy points + actual-minus-expected residual
    "actual_fantasy_points_total",
    "fantasy_points_over_expected",
]


def download_season(
    season: int, out_dir: str = BRONZE_DIR, force: bool = False
) -> tuple:
    """Download ep_pbp_pass/ep_pbp_rush parquet assets for one season.

    Uses the authenticated `gh` CLI against the ffverse/ffopportunity
    `latest-data` release (the release is continuously re-tagged with fresh
    data, but individual season files are stable historical snapshots).

    Args:
        season: NFL season year.
        out_dir: Bronze root directory.
        force: Re-download even if both files already exist locally.

    Returns:
        (pass_path, rush_path) tuple of local file paths.

    Raises:
        RuntimeError: If the gh CLI download fails for either asset.
    """
    season_dir = os.path.join(out_dir, f"season={season}")
    os.makedirs(season_dir, exist_ok=True)
    pass_path = os.path.join(season_dir, f"ep_pbp_pass_{season}.parquet")
    rush_path = os.path.join(season_dir, f"ep_pbp_rush_{season}.parquet")

    if not force and os.path.exists(pass_path) and os.path.exists(rush_path):
        logger.info(
            "season=%d: bronze files already present, skipping download", season
        )
        return pass_path, rush_path

    for pattern in (f"ep_pbp_pass_{season}.parquet", f"ep_pbp_rush_{season}.parquet"):
        cmd = [
            "gh",
            "release",
            "download",
            GH_TAG,
            "-R",
            GH_REPO,
            "-p",
            pattern,
            "-D",
            season_dir,
            "--clobber",
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(
                f"gh release download failed for {pattern} (season={season}): "
                f"{result.stderr.strip()}"
            )
    return pass_path, rush_path


def _mode_or_none(s: pd.Series):
    """Most common non-null value in a groupby Series, or None if all null."""
    non_null = s.dropna()
    if non_null.empty:
        return None
    return non_null.mode().iat[0]


def _exp_yards_component(df: pd.DataFrame) -> pd.Series:
    """Expected passing/receiving yards on a single play.

    ffopportunity's ep_pbp_pass file gives per-play expected values
    (pass_completion_exp = completion probability, yards_after_catch_exp =
    expected YAC value, both unconditional model outputs applicable
    regardless of the play's actual outcome) but no single "expected
    passing yards" column — unlike the pre-aggregated ep_weekly release
    asset. We derive it as P(complete) * (air_yards + E[YAC]): the intended
    throw depth is fixed by the target regardless of outcome, weighted by
    the model's completion probability, plus the model's expected YAC.
    This is our own derivation, not an ffopportunity-native column — see
    .planning/FFOPPORTUNITY_COVERAGE.md for the caveat.
    """
    return df["pass_completion_exp"] * (df["air_yards"] + df["yards_after_catch_exp"])


def aggregate_passing(pass_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ep_pbp_pass rows to one row per (passer, season, week)."""
    df = pass_df.copy()
    df["complete_pass_i"] = df["complete_pass"].astype(int)
    df["pass_touchdown_i"] = df["pass_touchdown"].astype(int)
    df["interception_i"] = df["interception"].astype(int)
    df["actual_yards"] = df["receiving_yards"].fillna(0)
    df["exp_yards"] = _exp_yards_component(df)

    grp = df.groupby(["passer_player_id", "season", "week"], as_index=False)
    out = grp.agg(
        team=("posteam", _mode_or_none),
        position=("passer_position", _mode_or_none),
        pass_attempts=("pass_attempt", "sum"),
        completions=("complete_pass_i", "sum"),
        pass_yards=("actual_yards", "sum"),
        pass_tds=("pass_touchdown_i", "sum"),
        interceptions=("interception_i", "sum"),
        exp_pass_yards=("exp_yards", "sum"),
        exp_pass_tds=("pass_touchdown_exp", "sum"),
    )
    return out.rename(columns={"passer_player_id": "player_id"})


def aggregate_receiving(pass_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ep_pbp_pass rows to one row per (receiver, season, week)."""
    df = pass_df[pass_df["receiver_player_id"].notna()].copy()
    df["complete_pass_i"] = df["complete_pass"].astype(int)
    df["pass_touchdown_i"] = df["pass_touchdown"].astype(int)
    df["actual_yards"] = df["receiving_yards"].fillna(0)
    df["exp_yards"] = _exp_yards_component(df)

    grp = df.groupby(["receiver_player_id", "season", "week"], as_index=False)
    out = grp.agg(
        team=("posteam", _mode_or_none),
        position=("receiver_position", _mode_or_none),
        targets=("pass_attempt", "sum"),
        receptions=("complete_pass_i", "sum"),
        rec_yards=("actual_yards", "sum"),
        rec_tds=("pass_touchdown_i", "sum"),
        exp_rec_yards=("exp_yards", "sum"),
        exp_rec_tds=("pass_touchdown_exp", "sum"),
    )
    return out.rename(columns={"receiver_player_id": "player_id"})


def aggregate_rushing(rush_df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate ep_pbp_rush rows to one row per (rusher, season, week)."""
    df = rush_df.copy()
    df["rush_touchdown_i"] = df["rush_touchdown"].astype(int)
    df["actual_yards"] = df["rushing_yards"].fillna(0)

    grp = df.groupby(["rusher_player_id", "season", "week"], as_index=False)
    out = grp.agg(
        team=("posteam", _mode_or_none),
        position=("position", _mode_or_none),
        carries=("rush_attempt", "sum"),
        rush_yards=("actual_yards", "sum"),
        rush_tds=("rush_touchdown_i", "sum"),
        # rushing_yards_exp/rushing_td_exp are the fully-named columns;
        # ep_pbp_rush also carries near-duplicate rush_yards_exp/
        # rush_touchdown_exp from a different model-version pass — we use
        # the fully-named pair for consistency with the pass-file naming.
        exp_rush_yards=("rushing_yards_exp", "sum"),
        exp_rush_tds=("rushing_td_exp", "sum"),
    )
    return out.rename(columns={"rusher_player_id": "player_id"})


def build_player_week_features(
    pass_df: pd.DataFrame, rush_df: pd.DataFrame
) -> pd.DataFrame:
    """Combine passing/receiving/rushing aggregates into one player-week table.

    Args:
        pass_df: Raw ep_pbp_pass rows (one row per pass attempt).
        rush_df: Raw ep_pbp_rush rows (one row per rush attempt).

    Returns:
        DataFrame with columns FEATURE_COLUMNS, one row per
        (player_id, season, week) — a player who both rushed and caught
        passes in a week (e.g. an RB) gets contributions from both roles
        summed onto a single row.

    Raises:
        ValueError: If both inputs are empty (fail loud rather than write
            an empty Silver partition — an empty parquet from a broken
            download would otherwise pass through silently).
    """
    if pass_df is None:
        pass_df = pd.DataFrame()
    if rush_df is None:
        rush_df = pd.DataFrame()
    if pass_df.empty and rush_df.empty:
        raise ValueError(
            "Both pass_df and rush_df are empty — refusing to build an "
            "empty ffopportunity Silver partition"
        )

    passing = aggregate_passing(pass_df)
    receiving = aggregate_receiving(pass_df)
    rushing = aggregate_rushing(rush_df)

    keys = ["player_id", "season", "week"]
    merged = passing.merge(receiving, on=keys, how="outer", suffixes=("_p", "_r"))
    merged["team"] = merged["team_p"].combine_first(merged["team_r"])
    merged["position"] = merged["position_p"].combine_first(merged["position_r"])
    merged = merged.drop(columns=["team_p", "team_r", "position_p", "position_r"])

    merged = merged.merge(rushing, on=keys, how="outer", suffixes=("", "_ru"))
    merged["team"] = merged["team"].combine_first(merged["team_ru"])
    merged["position"] = merged["position"].combine_first(merged["position_ru"])
    merged = merged.drop(columns=["team_ru", "position_ru"])

    numeric_cols = [
        c
        for c in merged.columns
        if c not in ("player_id", "season", "week", "team", "position")
    ]
    merged[numeric_cols] = merged[numeric_cols].fillna(0)

    merged["total_tds"] = merged["pass_tds"] + merged["rec_tds"] + merged["rush_tds"]
    merged["exp_total_tds"] = (
        merged["exp_pass_tds"] + merged["exp_rec_tds"] + merged["exp_rush_tds"]
    )

    pass_yd_pts, pass_td_pts, int_pts = (
        SCORING["pass_yd"],
        SCORING["pass_td"],
        SCORING["interception"],
    )
    rec_yd_pts, rec_td_pts = SCORING["rec_yd"], SCORING["rec_td"]
    rush_yd_pts, rush_td_pts = SCORING["rush_yd"], SCORING["rush_td"]

    merged["exp_pass_fantasy_points"] = (
        merged["exp_pass_yards"] * pass_yd_pts + merged["exp_pass_tds"] * pass_td_pts
    )
    merged["exp_rec_fantasy_points"] = (
        merged["exp_rec_yards"] * rec_yd_pts + merged["exp_rec_tds"] * rec_td_pts
    )
    merged["exp_rush_fantasy_points"] = (
        merged["exp_rush_yards"] * rush_yd_pts + merged["exp_rush_tds"] * rush_td_pts
    )
    merged["exp_fantasy_points_total"] = (
        merged["exp_pass_fantasy_points"]
        + merged["exp_rec_fantasy_points"]
        + merged["exp_rush_fantasy_points"]
    )

    merged["actual_fantasy_points_total"] = (
        merged["pass_yards"] * pass_yd_pts
        + merged["pass_tds"] * pass_td_pts
        + merged["interceptions"] * int_pts
        + merged["rec_yards"] * rec_yd_pts
        + merged["rec_tds"] * rec_td_pts
        + merged["rush_yards"] * rush_yd_pts
        + merged["rush_tds"] * rush_td_pts
    )
    merged["fantasy_points_over_expected"] = (
        merged["actual_fantasy_points_total"] - merged["exp_fantasy_points_total"]
    )

    merged["season"] = merged["season"].astype(int)
    merged["week"] = merged["week"].astype(int)

    return (
        merged[FEATURE_COLUMNS]
        .sort_values(["season", "week", "player_id"])
        .reset_index(drop=True)
    )


def run_season(
    season: int,
    bronze_dir: str = BRONZE_DIR,
    silver_dir: str = SILVER_DIR,
    force_download: bool = False,
) -> pd.DataFrame:
    """Download + aggregate one season end-to-end, writing the Silver parquet."""
    pass_path, rush_path = download_season(season, bronze_dir, force=force_download)
    pass_df = pd.read_parquet(pass_path)
    rush_df = pd.read_parquet(rush_path)

    features = build_player_week_features(pass_df, rush_df)

    out_dir = os.path.join(silver_dir, f"season={season}")
    os.makedirs(out_dir, exist_ok=True)
    out_path = os.path.join(out_dir, f"ffopportunity_features_{season}.parquet")
    features.to_parquet(out_path, index=False)

    logger.info(
        "season=%d: %d pass rows, %d rush rows -> %d player-weeks -> %s",
        season,
        len(pass_df),
        len(rush_df),
        len(features),
        out_path,
    )
    return features


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=PLAYER_DATA_SEASONS,
        help="Seasons to ingest (default: PLAYER_DATA_SEASONS from src/config.py)",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download bronze files even if already present locally",
    )
    args = parser.parse_args()

    total_rows = 0
    for season in args.seasons:
        features = run_season(season, force_download=args.force_download)
        total_rows += len(features)

    print(f"\nDone: {len(args.seasons)} seasons, {total_rows} total player-week rows")
    return 0


if __name__ == "__main__":
    sys.exit(main())
