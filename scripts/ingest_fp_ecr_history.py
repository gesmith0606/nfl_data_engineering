#!/usr/bin/env python3
"""
Bronze/Silver — DynastyProcess FantasyPros ECR (Expert Consensus Ranking) archive.

One-time historical backfill of *in-season weekly* FantasyPros consensus
rankings, 2020-2024, for the pre-registered WR-ordinal experiment (that
experiment's projection/backtest machinery is owned elsewhere — this script
only builds the ingestion layer it will read from).

LEGAL / PROVENANCE (read before running):
    Source: github.com/dynastyprocess/data, files/db_fpecr.csv.gz (GitHub
    Action-refreshed scrape of FantasyPros.com rankings pages) + files/
    db_playerids.csv (id crosswalk). The repo is GPL-3.0, and the underlying
    rankings are themselves scraped from FantasyPros.com (a commercial site
    whose own ToS restricts redistribution/scraping) — so this output is
    LOCAL-ONLY, PRIVATE RESEARCH USE. Never commit the data rows (see the
    .gitignore entries added alongside this script) and never redistribute.
    Code, tests, and the coverage doc are fine to commit; the parquet is not.

ARCHIVE REALITY CHECK (2026-08-18 ingestion session — read before assuming
the schema matches the task's original assumptions):
    1. Only ONE scoring variant exists per position for *weekly* rankings:
       RB/WR/TE weekly pages are PPR-only (fp_page ends in ppr-rb.php /
       ppr-wr.php / ppr-te.php); QB weekly is scoring-agnostic (qb.php, no
       PPR/standard split — passing/rushing points don't depend on
       receptions). There is NO half-ppr-*.php or standard-*.php weekly
       page in this archive. The `scoring` column is still derived
       generically from fp_page (so it would pick up other variants for
       free if DynastyProcess ever adds them), but today it is 100% "ppr"
       (RB/WR/TE) or "standard" (QB) — there is no half-PPR weekly ECR to
       ingest. Document this in the coverage report; don't silently assume
       half-PPR coverage exists.
    2. No January rows exist in the weekly-{qb,rb,wr,te} page types for any
       season 2020-2024 (verified by scanning the full archive) — FP's own
       weekly-position scrape cadence stops once the majority of fantasy
       leagues finish their regular season+playoffs (~week 15-17), before
       the NFL's own Weeks 18-22. The season/week mapper below still
       handles January dates correctly (mapped to the *previous* season,
       per NFL convention) for robustness and is tested against that case,
       but it will never fire against the real archive.
    3. 2020 is missing early-season weeks (first scrape 2020-10-16, i.e.
       missing weeks 1-5ish) and 2023 is missing week 1 (first scrape
       2023-09-15, after week 1's window closes 2023-09-11) — the archive's
       own scrape cadence didn't start from week 1 every season. Documented
       honestly per-season in the coverage report, not silently backfilled.
    4. Last automated GitHub Action commit touching db_fpecr.csv.gz was
       2025-08-08 (verified via the GitHub commits API at ingestion time,
       2026-08-18) — over a year stale. There is NO 2025 in-season weekly
       data in the archive; the automated scrape did not resume.

SEASON/WEEK MAPPING (the leakage boundary):
    FantasyPros scrapes its weekly consensus rankings a few times *before*
    that week's games conclude (Tue-Mon), including after that week's
    Thursday game has already been played. We map a scrape_date to the
    smallest NFL week (per that season's Bronze schedules, REG games only)
    whose game window has NOT yet fully concluded as of scrape_date — i.e.
    the first week where `scrape_date <= week_max_gameday`. This is a
    conservative "what did we know as of this date" rule: a scrape on the
    Monday of week 5 still maps to week 5 (that week's MNF hasn't happened
    yet), and a scrape any time after week 18 ends maps to no week (dropped
    — this archive doesn't cover playoff-week rankings anyway, see #2
    above). Season is derived from the calendar month: Jan/Feb dates belong
    to the *previous* season (NFL convention — a week 18/19 game in early
    January is still part of the prior season), Mar-Dec dates belong to the
    same-year season.

Output:
    data/bronze/fp_ecr_history/season=YYYY/fp_ecr_history_YYYY.parquet
        Raw filtered rows (page_type in weekly-{qb,rb,wr,te}, scrape_date
        mapped to a season/week) plus a derived `scoring` column. Not
        joined to our player IDs yet — that's the Silver step.
    data/silver/fp_ecr/season=YYYY/fp_ecr_YYYY.parquet
        Tidy table: season, week, scrape_date, scoring, position,
        player_name, fantasypros_id, gsis_id, sleeper_id, ecr, pos_rank,
        sd, best, worst.

Usage:
    python scripts/ingest_fp_ecr_history.py --local-file path/to/db_fpecr.csv.gz
    python scripts/ingest_fp_ecr_history.py                      # downloads both files fresh
    python scripts/ingest_fp_ecr_history.py --seasons 2023 2024
"""

import argparse
import glob
import io
import logging
import os
import sys
from datetime import date
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

PROJECT_ROOT = os.path.join(os.path.dirname(__file__), "..")
BRONZE_DIR = os.path.join(PROJECT_ROOT, "data", "bronze")
SILVER_DIR = os.path.join(PROJECT_ROOT, "data", "silver")
BRONZE_OUT_DIR = os.path.join(BRONZE_DIR, "fp_ecr_history")
SILVER_OUT_DIR = os.path.join(SILVER_DIR, "fp_ecr")
SCHEDULES_GLOB = os.path.join(BRONZE_DIR, "schedules", "season={season}", "*.parquet")

RAW_BASE = "https://raw.githubusercontent.com/dynastyprocess/data/master/files"
FPECR_URL = f"{RAW_BASE}/db_fpecr.csv.gz"
PLAYERIDS_URL = f"{RAW_BASE}/db_playerids.csv"

WEEKLY_PAGE_TYPES = ["weekly-qb", "weekly-rb", "weekly-wr", "weekly-te"]
DEFAULT_SEASONS = [2020, 2021, 2022, 2023, 2024]

# Columns kept from the raw archive for the Bronze layer (traceability), plus
# derived season/week/scoring appended by add_season_week_scoring().
BRONZE_RAW_COLS = [
    "fp_page", "page_type", "player", "id", "pos", "team",
    "ecr", "sd", "best", "worst", "mergename", "tm", "scrape_date",
]

SILVER_COLUMNS = [
    "season", "week", "scrape_date", "scoring", "position", "player_name",
    "fantasypros_id", "gsis_id", "sleeper_id", "ecr", "pos_rank", "sd",
    "best", "worst",
]


def fetch_fp_ecr_csv(local_file: Optional[str] = None) -> pd.DataFrame:
    """Load the DynastyProcess FP-ECR archive (local file or fresh download)."""
    if local_file:
        logger.info("Reading local FP-ECR archive: %s", local_file)
        return pd.read_csv(local_file)
    logger.info("Downloading FP-ECR archive from %s", FPECR_URL)
    resp = requests.get(FPECR_URL, timeout=120)
    resp.raise_for_status()
    return pd.read_csv(io.BytesIO(resp.content), compression="gzip")


def fetch_playerid_crosswalk(local_file: Optional[str] = None) -> pd.DataFrame:
    """Load the DynastyProcess player-ID crosswalk (local file or fresh download)."""
    if local_file:
        logger.info("Reading local player-ID crosswalk: %s", local_file)
        return pd.read_csv(local_file)
    logger.info("Downloading player-ID crosswalk from %s", PLAYERIDS_URL)
    resp = requests.get(PLAYERIDS_URL, timeout=30)
    resp.raise_for_status()
    return pd.read_csv(io.StringIO(resp.text))


def filter_weekly_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Filter to in-season weekly position rankings (weekly-qb/rb/wr/te)."""
    return df[df["page_type"].isin(WEEKLY_PAGE_TYPES)].copy()


def scoring_from_fp_page(fp_page: str) -> str:
    """Derive scoring format from the FantasyPros rankings page URL.

    Generic on purpose: today the weekly archive only ever produces "ppr"
    (RB/WR/TE) or "standard" (QB, scoring-agnostic), but this also picks up
    half-ppr-*.php should DynastyProcess ever add that variant.
    """
    page = str(fp_page).lower()
    if "half-ppr" in page:
        return "half_ppr"
    if "ppr" in page:
        return "ppr"
    return "standard"


def load_schedule_reg_windows(season: int) -> Dict[int, Tuple[date, date]]:
    """Load min/max gameday per REG week for a season from Bronze schedules.

    Mirrors the read pattern in src/feature_engineering.py::_read_bronze_schedules
    (glob season dir, take the lexicographically-last timestamped file, filter
    game_type == "REG").

    Returns:
        {week: (min_gameday, max_gameday)}, empty dict if no schedule found.
    """
    pattern = SCHEDULES_GLOB.format(season=season)
    files = sorted(glob.glob(pattern))
    if not files:
        return {}
    sched = pd.read_parquet(files[-1])
    sched = sched[sched["game_type"] == "REG"].copy()
    sched["gameday"] = pd.to_datetime(sched["gameday"]).dt.date
    windows: Dict[int, Tuple[date, date]] = {}
    for week, g in sched.groupby("week"):
        windows[int(week)] = (g["gameday"].min(), g["gameday"].max())
    return windows


def derive_season(scrape_date: date) -> int:
    """NFL season for a calendar date: Jan/Feb dates belong to the prior season."""
    return scrape_date.year if scrape_date.month >= 3 else scrape_date.year - 1


def map_scrape_date_to_week(
    scrape_date: date, windows: Dict[int, Tuple[date, date]]
) -> Optional[int]:
    """Map a scrape_date to the earliest NFL week not yet fully concluded.

    Returns the smallest week whose max_gameday >= scrape_date, or None if
    scrape_date is after every known week's max_gameday (post-season, not
    covered by this archive's weekly-position pages) or no schedule exists.
    """
    if not windows:
        return None
    for week in sorted(windows):
        _, max_gameday = windows[week]
        if scrape_date <= max_gameday:
            return week
    return None


_SCHEDULE_CACHE: Dict[int, Dict[int, Tuple[date, date]]] = {}


def _windows_for(season: int) -> Dict[int, Tuple[date, date]]:
    if season not in _SCHEDULE_CACHE:
        _SCHEDULE_CACHE[season] = load_schedule_reg_windows(season)
    return _SCHEDULE_CACHE[season]


def add_season_week_scoring(df: pd.DataFrame) -> pd.DataFrame:
    """Derive season, week, and scoring columns; drops rows with no week mapping."""
    df = df.copy()
    df["scrape_date"] = pd.to_datetime(df["scrape_date"]).dt.date
    df["scoring"] = df["fp_page"].map(scoring_from_fp_page)
    df["season"] = df["scrape_date"].map(derive_season)

    weeks = []
    for season, sdate in zip(df["season"], df["scrape_date"]):
        weeks.append(map_scrape_date_to_week(sdate, _windows_for(int(season))))
    df["week"] = weeks

    unmapped = df["week"].isna().sum()
    if unmapped:
        logger.warning(
            "%d/%d rows dropped: scrape_date has no REG-week mapping "
            "(post-season or missing schedule)",
            unmapped,
            len(df),
        )
    df = df[df["week"].notna()].copy()
    df["week"] = df["week"].astype(int)
    return df


def join_crosswalk(df: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Join fantasypros_id -> gsis_id, sleeper_id via the DynastyProcess crosswalk."""
    df = df.copy()
    df["fantasypros_id"] = pd.to_numeric(df["id"], errors="coerce").astype("Int64")

    cw = crosswalk[["fantasypros_id", "gsis_id", "sleeper_id"]].copy()
    cw = cw.dropna(subset=["fantasypros_id"])
    cw["fantasypros_id"] = cw["fantasypros_id"].astype("Int64")
    cw = cw.drop_duplicates(subset=["fantasypros_id"])

    out = df.merge(cw, on="fantasypros_id", how="left")
    join_rate = out["gsis_id"].notna().mean() if len(out) else 0.0
    logger.info("gsis_id join rate: %.1f%% (%d rows)", join_rate * 100, len(out))
    return out


def derive_pos_rank(df: pd.DataFrame) -> pd.DataFrame:
    """Rank ecr ascending within (season, week, scoring, position)."""
    df = df.copy()
    df["pos_rank"] = (
        df.groupby(["season", "week", "scoring", "position"])["ecr"]
        .rank(method="min")
        .astype(int)
    )
    return df


def build_bronze(raw: pd.DataFrame) -> pd.DataFrame:
    """Filter + derive season/week/scoring; keep original archive columns."""
    weekly = filter_weekly_rows(raw)
    missing = [c for c in BRONZE_RAW_COLS if c not in weekly.columns]
    if missing:
        raise ValueError(f"FP-ECR archive missing expected columns: {missing}")
    weekly = weekly[BRONZE_RAW_COLS].copy()
    return add_season_week_scoring(weekly)


def build_silver(bronze: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Join crosswalk, derive pos_rank, tidy to the Silver schema."""
    df = bronze.rename(columns={"player": "player_name", "pos": "position"})
    df = join_crosswalk(df, crosswalk)
    df = derive_pos_rank(df)
    return df[SILVER_COLUMNS].copy()


def validate_fail_loud(df: pd.DataFrame, seasons: List[int]) -> None:
    """Raise loudly if any requested season in 2020-2024 has zero rows.

    This is the WR-ordinal experiment's leakage boundary — a silently empty
    season is worse than a crash, since a downstream backtest would just
    treat it as "no ECR signal" rather than "ingestion broke."
    """
    counts = df.groupby("season").size().to_dict()
    for season in seasons:
        n = counts.get(season, 0)
        if n == 0:
            raise RuntimeError(
                f"FP-ECR ingestion produced ZERO rows for season {season} "
                f"(requested seasons: {seasons}). Failing loud rather than "
                "silently shipping a gap in the WR-ordinal experiment's "
                "input data."
            )


def write_parquet(df: pd.DataFrame, out_dir: str, prefix: str, seasons: List[int]) -> List[str]:
    written = []
    for season in seasons:
        season_df = df[df["season"] == season]
        if season_df.empty:
            continue
        season_dir = os.path.join(out_dir, f"season={season}")
        os.makedirs(season_dir, exist_ok=True)
        out_path = os.path.join(season_dir, f"{prefix}_{season}.parquet")
        season_df.to_parquet(out_path, index=False)
        written.append(out_path)
        logger.info("Wrote %d rows -> %s", len(season_df), out_path)
    return written


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--local-file", help="Path to a pre-downloaded db_fpecr.csv.gz (saves bandwidth on the 100MB archive)")
    parser.add_argument("--playerids-file", help="Path to a pre-downloaded db_playerids.csv (optional; small file, downloads fine)")
    parser.add_argument("--seasons", type=int, nargs="+", default=DEFAULT_SEASONS)
    parser.add_argument("--bronze-dir", default=BRONZE_OUT_DIR)
    parser.add_argument("--silver-dir", default=SILVER_OUT_DIR)
    args = parser.parse_args()

    raw = fetch_fp_ecr_csv(args.local_file)
    logger.info("Loaded %d raw archive rows", len(raw))

    bronze = build_bronze(raw)
    logger.info("Bronze (weekly-qb/rb/wr/te, season/week mapped): %d rows", len(bronze))

    crosswalk = fetch_playerid_crosswalk(args.playerids_file)
    silver = build_silver(bronze, crosswalk)

    validate_fail_loud(silver, args.seasons)

    write_parquet(bronze, args.bronze_dir, "fp_ecr_history", args.seasons)
    write_parquet(silver, args.silver_dir, "fp_ecr", args.seasons)

    print("\n=== Rows + gsis join-rate per season/position ===")
    summary = silver.groupby(["season", "position"]).agg(
        rows=("ecr", "size"),
        weeks=("week", "nunique"),
        gsis_join_rate=("gsis_id", lambda s: s.notna().mean()),
    )
    print(summary.to_string())

    print(
        "\nPROVENANCE: github.com/dynastyprocess/data (GPL-3.0), underlying "
        "rankings scraped from FantasyPros.com. Local-only, private research "
        "use — do not commit the parquet output or redistribute."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
