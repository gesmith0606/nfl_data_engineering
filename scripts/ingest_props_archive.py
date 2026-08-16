#!/usr/bin/env python3
"""
Bronze Player Props — one-time archive backfill from github.com/firstandthirty/nfl-tools

Historical prop lines cannot be scraped (sportsbooks only serve live/current
lines) — see .planning/PROPS_DATA_PLAN.md. This script fetches the one free,
real, machine-parseable archive found by the Phase 1 scout (2026-08-16) and
normalizes it into the same Bronze schema ``bronze_props_ingestion.py``
writes, so the existing ``prop_implied.py`` machinery (``compute_prop_implied_points``,
``apply_props_blend``) can consume it unmodified.

LEGAL / PROVENANCE (read before running):
    Source: github.com/firstandthirty/nfl-tools (public repo, no LICENSE file
    -> default all-rights-reserved on the repo owner's derived work; the
    underlying odds are themselves sourced from The Odds API, a commercial
    provider, via the owner's own capture scripts). Redistribution rights are
    AMBIGUOUS. Reading a public GitHub file for private research is treated
    the same as reading any other public repo's committed data (low risk),
    but the output of this script is PRIVATE RESEARCH USE ONLY — never
    redistribute, publish, or commit it. The output path is explicitly
    re-excluded in .gitignore (see the "THIRD-PARTY ARCHIVE DATA" block)
    despite the broader data/bronze/odds_api/** allowlist used for our own
    forward-captured data.

VALIDATION FINDINGS baked into the normalization below (2026-08-16 session):
    1. fanduel_pass_yds_history.csv / fanduel_receptions_history.csv only
       carry a *guessed* week column (``week_guess_numeric``) — verified
       against real nflverse actuals (Mahomes/Goff Week 1 2023 opener, KC's
       2023 bye week) that this guess is OFF BY +1 for season 2023 only
       (2024/2025 rows are correct as-is). Corrected below.
    2. Those same two files store odds as DECIMAL, not American, despite the
       downstream schema/``prop_implied.american_to_prob`` expecting
       American — converted below.
    3. rush_yds_market_analysis_rows.csv / reception_yds_market_analysis_rows.csv
       already carry correct season/week (spot-checked: Najee Harris
       PIT@BAL 2024-11-17 wk11, line 51.5, actual 63.0) and American odds,
       but have a handful of duplicate (player, event_id) rows across two
       capture snapshots — deduped to the LATEST ``requested_snapshot_time``
       (closing line) per the task's "prefer closing/latest" instruction.
    4. The scout's row-count note ("player_pass_yds ... 6,901 rows") does not
       match the live file (1,538 rows) — the 6,901/6,902 pair both belong to
       fanduel_receptions_history.csv (6,901 data rows). pass_yds coverage is
       still genuine and continuous (~25-32 QBs/week, 2023 wk2-2025 wk18) —
       this is a scout transcription error, not a bad archive.
    5. Per PROP_IMPLIED_DECISION.md ("2025 stays sealed"), season 2025 rows
       are fetched for completeness/validation printing but DROPPED before
       write — this backfill only ever writes 2023 + 2024.

Output: data/bronze/odds_api/props/season=YYYY/props_archive_YYYY.parquet
        (one row per player-market-book-week snapshot; schema matches
        PROPS_SCHEMA_COLS in scripts/bronze_props_ingestion.py, plus a
        research-only ``week`` column consumers may use to join by week.)

Usage:
    python scripts/ingest_props_archive.py
    python scripts/ingest_props_archive.py --seasons 2023 2024
"""

import argparse
import io
import logging
import os
import sys
from typing import List

import pandas as pd
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.bronze_odds_api_ingestion import ODDS_API_TO_NFLVERSE  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.join(PROJECT_ROOT, "data", "bronze", "odds_api", "props")

RAW_BASE = "https://raw.githubusercontent.com/firstandthirty/nfl-tools/main/player_props/data"

# (local filename hint, repo-relative path, market key)
SOURCES = [
    ("fanduel_pass_yds_history", "processed/fanduel_pass_yds_history.csv", "player_pass_yds"),
    ("fanduel_receptions_history", "processed/fanduel_receptions_history.csv", "player_receptions"),
    ("rush_yds_market_analysis_rows", "analysis/rush_yds_market_analysis_rows.csv", "player_rush_yds"),
    ("reception_yds_market_analysis_rows", "analysis/reception_yds_market_analysis_rows.csv", "player_reception_yds"),
]

PROPS_SCHEMA_COLS: List[str] = [
    "snapshot_ts",
    "event_id",
    "commence_time",
    "home_team",
    "away_team",
    "home_team_nfl",
    "away_team_nfl",
    "bookmaker",
    "market",
    "player_name",
    "line",
    "price_over",
    "price_under",
    "season",
]
# Research-only extra column (not part of the live-capture schema, but every
# consumer of this archive needs to join by week — the live schema doesn't
# need it because each live snapshot file IS a single week).
EXTRA_COLS = ["week"]

# Season 2023 rows in the fanduel_*_history.csv files carry a week_guess that
# is off by +1 vs real nflverse week (verified against known bye weeks / the
# 2023 Week 1 Thursday opener). 2024/2025 rows need no correction.
WEEK_GUESS_OFFSET_BY_SEASON = {2023: -1}


def fetch_csv(rel_path: str) -> pd.DataFrame:
    """Download one archive CSV from raw.githubusercontent.com into memory."""
    url = f"{RAW_BASE}/{rel_path}"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text))


def decimal_to_american(dec: float) -> float:
    """Convert decimal odds (e.g. 1.91) to American odds (e.g. -110)."""
    if pd.isna(dec) or dec <= 1.0:
        return float("nan")
    if dec >= 2.0:
        return round((dec - 1.0) * 100.0, 1)
    return round(-100.0 / (dec - 1.0), 1)


def _map_teams(df: pd.DataFrame) -> pd.DataFrame:
    df["home_team_nfl"] = df["home_team"].map(ODDS_API_TO_NFLVERSE)
    df["away_team_nfl"] = df["away_team"].map(ODDS_API_TO_NFLVERSE)
    unmapped = set(df.loc[df["home_team_nfl"].isna(), "home_team"]) | set(
        df.loc[df["away_team_nfl"].isna(), "away_team"]
    )
    if unmapped:
        logger.warning("Unmapped team names: %s", sorted(unmapped))
    return df


def normalize_fanduel_history(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Normalize a decimal-odds / week-guess archive file to the Bronze schema."""
    df = df.copy()
    df["season"] = df["season_guess"].astype(int)
    offset = df["season"].map(WEEK_GUESS_OFFSET_BY_SEASON).fillna(0).astype(int)
    df["week"] = df["week_guess_numeric"].astype(int) + offset
    df["price_over"] = df["over_price"].map(decimal_to_american)
    df["price_under"] = df["under_price"].map(decimal_to_american)
    df["bookmaker"] = "fanduel"
    df["market"] = market
    df["player_name"] = df["player"]
    df["snapshot_ts"] = df["requested_snapshot_time"]
    df = _map_teams(df)
    return df[PROPS_SCHEMA_COLS + EXTRA_COLS]


def normalize_market_analysis(df: pd.DataFrame, market: str) -> pd.DataFrame:
    """Normalize an already-American-odds, already-graded archive file.

    Dedupes multiple snapshots for the same (player, event) to the latest
    ``requested_snapshot_time`` — prefers the closing/most-recent line, per
    the task instruction.
    """
    df = df.copy()
    before = len(df)
    df = df.sort_values("requested_snapshot_time").drop_duplicates(
        subset=["player", "event_id"], keep="last"
    )
    deduped = before - len(df)
    if deduped:
        logger.info(
            "%s: deduped %d/%d rows to latest snapshot per (player, event_id)",
            market,
            deduped,
            before,
        )
    df["season"] = df["season"].astype(int)
    df["week"] = df["week"].astype(int)
    df["price_over"] = df["over_price"]
    df["price_under"] = df["under_price"]
    df["bookmaker"] = df["bookmaker_key"]
    df["market"] = market
    df["player_name"] = df["player"]
    df["snapshot_ts"] = df["requested_snapshot_time"]
    df = _map_teams(df)
    return df[PROPS_SCHEMA_COLS + EXTRA_COLS]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--seasons",
        type=int,
        nargs="+",
        default=[2023, 2024],
        help="Seasons to WRITE (archive also covers 2025, sealed per "
        "PROP_IMPLIED_DECISION.md — fetched for validation only, never written).",
    )
    parser.add_argument("--out-dir", default=OUT_DIR)
    args = parser.parse_args()

    frames = []
    for name, rel_path, market in SOURCES:
        logger.info("Fetching %s (%s)...", name, market)
        raw = fetch_csv(rel_path)
        logger.info("  %d raw rows", len(raw))
        if "week_guess_numeric" in raw.columns:
            norm = normalize_fanduel_history(raw, market)
        else:
            norm = normalize_market_analysis(raw, market)
        logger.info(
            "  normalized: %d rows, seasons=%s, weeks=%s-%s",
            len(norm),
            sorted(norm["season"].unique()),
            norm["week"].min(),
            norm["week"].max(),
        )
        frames.append(norm)

    combined = pd.concat(frames, ignore_index=True)

    # Sanity: line distributions per market (printed for the report, not
    # enforced — this is a research backfill, not a Bronze validate_data() gate).
    print("\n=== Line distribution sanity per market (all fetched seasons) ===")
    print(combined.groupby("market")["line"].describe()[["count", "mean", "std", "min", "max"]])

    os.makedirs(args.out_dir, exist_ok=True)
    for season in args.seasons:
        season_df = combined[combined["season"] == season]
        if season_df.empty:
            logger.warning("No rows for season %d — skipping write", season)
            continue
        season_dir = os.path.join(args.out_dir, f"season={season}")
        os.makedirs(season_dir, exist_ok=True)
        out_path = os.path.join(season_dir, f"props_archive_{season}.parquet")
        season_df.to_parquet(out_path, index=False)
        print(f"Wrote {len(season_df)} rows -> {out_path}")

    dropped_seasons = sorted(set(combined["season"].unique()) - set(args.seasons))
    if dropped_seasons:
        print(
            f"NOTE: fetched but did NOT write seasons {dropped_seasons} "
            "(2025 stays sealed per PROP_IMPLIED_DECISION.md; pass --seasons "
            "to override)."
        )
    print(
        "\nPROVENANCE: github.com/firstandthirty/nfl-tools, ambiguous "
        "redistribution rights (no LICENSE, underlying data from The Odds "
        "API commercial feed). Private research use only — do not "
        "redistribute or commit this output."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
