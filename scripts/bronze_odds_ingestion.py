#!/usr/bin/env python3
"""
Bronze Odds Ingestion -- Download FinnedAI JSON, map team names to nflverse
abbreviations, join to nflverse schedules for game_id, validate sign conventions
and cross-correlations, write per-season Parquet files.

Primary source: FinnedAI/sportsbookreview-scraper JSON (2016-2021)
Fallback: Direct SBRO XLSX download (D-03)
Output: data/bronze/odds/season=YYYY/odds_YYYYMMDD_HHMMSS.parquet
"""

import argparse
import json
import os
import sys
from datetime import datetime

import nfl_data_py as nfl
import pandas as pd
import requests
from scipy.stats import pearsonr

# Add project root to path so src.* imports work
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

try:
    from src.config import validate_season_for_type
except ImportError:
    # Graceful fallback if config doesn't have odds registered yet (Plan 32-02)
    def validate_season_for_type(data_type: str, season: int) -> bool:
        if data_type == "odds":
            return 2016 <= season <= 2021
        raise ValueError(f"Unknown data type '{data_type}'")

# Optional openpyxl for SBRO XLSX fallback (D-03)
try:
    import openpyxl  # noqa: F401

    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

# ── Constants ────────────────────────────────────────────────────────────

RAW_DIR = "data/raw/sbro"
BRONZE_DIR = "data/bronze/odds"
JSON_URL = (
    "https://raw.githubusercontent.com/FinnedAI/"
    "sportsbookreview-scraper/main/data/nfl_archive_10Y.json"
)
SBRO_XLSX_URL = (
    "https://www.sportsbookreviewsonline.com/"
    "scoresoddsarchives/nfl/nfl%20odds%20{start}-{end}.xlsx"
)
SEASONS = list(range(2016, 2022))  # 2016-2021 inclusive

# ── Team Name Mapping (44 FinnedAI nicknames -> 32 nflverse abbreviations) ───

FINNEDAI_TO_NFLVERSE = {
    # Standard nicknames (32 current + historical)
    "Cardinals": "ARI",
    "Falcons": "ATL",
    "Ravens": "BAL",
    "Bills": "BUF",
    "Panthers": "CAR",
    "Bears": "CHI",
    "Bengals": "CIN",
    "Browns": "CLE",
    "Cowboys": "DAL",
    "Broncos": "DEN",
    "Lions": "DET",
    "Packers": "GB",
    "Texans": "HOU",
    "Colts": "IND",
    "Jaguars": "JAX",
    "Chiefs": "KC",
    "Chargers": "LAC",
    "Rams": "LA",
    "Dolphins": "MIA",
    "Vikings": "MIN",
    "Patriots": "NE",
    "Saints": "NO",
    "Giants": "NYG",
    "Jets": "NYJ",
    "Eagles": "PHI",
    "Steelers": "PIT",
    "Seahawks": "SEA",
    "Buccaneers": "TB",
    "Titans": "TEN",
    # San Francisco variants
    "Fortyniners": "SF",
    "49ers": "SF",
    # Relocated teams (appear in earlier seasons)
    "Oakland": "OAK",  # 2016-2019
    "Raiders": "LV",  # 2020-2021
    "SanDiego": "SD",  # 2016 only
    "LosAngeles": "LA",  # 2016 only
    # Washington variants
    "Commanders": "WAS",
    "Washington": "WAS",
    "Washingtom": "WAS",  # Typo in 2020 data
    "Redskins": "WAS",
    # Inconsistent multi-word names (2020 data quality issues)
    "KCChiefs": "KC",
    "Kansas": "KC",  # Truncated "Kansas City"
    "LVRaiders": "LV",
    "Tampa": "TB",  # Truncated "Tampa Bay"
    "BuffaloBills": "BUF",
    # Ambiguous -- resolved by resolve_newyork()
    "NewYork": None,
}


# ── Download Functions ───────────────────────────────────────────────────


def download_finnedai(force: bool = False) -> str:
    """Download FinnedAI JSON to staging area. Skip if exists (D-04).

    Args:
        force: Re-download even if file exists.

    Returns:
        Local file path to the downloaded JSON.
    """
    os.makedirs(RAW_DIR, exist_ok=True)
    local_path = os.path.join(RAW_DIR, "nfl_archive_10Y.json")
    if os.path.exists(local_path) and not force:
        print(f"  Already downloaded: {local_path}")
        return local_path
    r = requests.get(JSON_URL, timeout=30)
    r.raise_for_status()
    with open(local_path, "w") as f:
        f.write(r.text)
    print(f"  Downloaded: {local_path} ({len(r.text):,} bytes)")
    return local_path


def download_sbro_xlsx(
    season_start: int, season_end: int, force: bool = False
) -> str:
    """Download SBRO XLSX archive as fallback (D-03).

    Args:
        season_start: First season year (e.g., 2020).
        season_end: Second season year (e.g., 2021).
        force: Re-download even if file exists.

    Returns:
        Local file path to the downloaded XLSX.

    Raises:
        ImportError: If openpyxl is not installed.
    """
    if not HAS_OPENPYXL:
        raise ImportError(
            "openpyxl required for SBRO XLSX fallback: pip install openpyxl"
        )
    os.makedirs(RAW_DIR, exist_ok=True)
    # Build URL: two-digit end year
    end_short = str(season_end)[-2:]
    url = SBRO_XLSX_URL.format(start=season_start, end=end_short)
    out_path = os.path.join(RAW_DIR, f"nfl_odds_{season_start}_{season_end}.xlsx")
    if os.path.exists(out_path) and not force:
        print(f"  Already downloaded: {out_path}")
        return out_path
    r = requests.get(url, timeout=60)
    r.raise_for_status()
    with open(out_path, "wb") as f:
        f.write(r.content)
    print(f"  Downloaded: {out_path} ({len(r.content):,} bytes)")
    return out_path


# ── Parse Functions ──────────────────────────────────────────────────────


def parse_finnedai(json_path: str, seasons: list) -> pd.DataFrame:
    """Parse FinnedAI JSON into DataFrame for specified seasons.

    Drops corrupt team=0 entries, filters to requested seasons,
    maps team names to nflverse abbreviations, parses date floats.

    D-11: Missing opening lines preserved as NaN (never zero, never dropped).
    D-12: Postponed games with no final score are excluded.

    Args:
        json_path: Path to the downloaded JSON file.
        seasons: List of season ints to include.

    Returns:
        DataFrame with columns: season, gameday, home_team, away_team,
        home_team_nfl, away_team_nfl, and all odds fields.
    """
    with open(json_path) as f:
        data = json.load(f)

    # Filter to requested seasons, drop corrupt entries
    records = []
    dropped_corrupt = 0
    dropped_postponed = 0
    for entry in data:
        season = int(entry.get("season", 0))
        if season not in seasons:
            continue
        # Drop corrupt team=0 entries
        if str(entry.get("home_team", "")) == "0" or str(entry.get("away_team", "")) == "0":
            dropped_corrupt += 1
            continue
        # D-12: Exclude postponed/cancelled games with no final score
        home_final = entry.get("home_final")
        if home_final is None or (isinstance(home_final, float) and pd.isna(home_final)):
            dropped_postponed += 1
            continue
        # Also check for empty string final scores
        if isinstance(home_final, str) and home_final.strip() == "":
            dropped_postponed += 1
            continue
        records.append(entry)

    if dropped_corrupt:
        print(f"  Dropped {dropped_corrupt} corrupt entries (team=0)")
    if dropped_postponed:
        print(f"  Dropped {dropped_postponed} postponed games (no final score)")

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)
    df["season"] = df["season"].astype(int)

    # D-11: opening lines are preserved as-is (NaN for missing, never zero-filled)

    # Map team names to nflverse abbreviations
    df["home_team_nfl"] = df["home_team"].map(FINNEDAI_TO_NFLVERSE)
    df["away_team_nfl"] = df["away_team"].map(FINNEDAI_TO_NFLVERSE)

    # Check for unmapped teams (not in dict at all)
    unmapped_home = df[~df["home_team"].isin(FINNEDAI_TO_NFLVERSE.keys())]
    unmapped_away = df[~df["away_team"].isin(FINNEDAI_TO_NFLVERSE.keys())]
    if len(unmapped_home) > 0:
        unique_unmapped = unmapped_home["home_team"].unique()
        print(f"  WARNING: Unmapped home teams: {unique_unmapped}")
    if len(unmapped_away) > 0:
        unique_unmapped = unmapped_away["away_team"].unique()
        print(f"  WARNING: Unmapped away teams: {unique_unmapped}")

    # Parse dates: float YYYYMMDD -> datetime.date
    df["gameday"] = pd.to_datetime(
        df["date"].astype(int).astype(str), format="%Y%m%d"
    ).dt.date

    return df


# ── NewYork Disambiguation ──────────────────────────────────────────────


def resolve_newyork(
    odds_df: pd.DataFrame, schedules: dict
) -> pd.DataFrame:
    """Resolve ambiguous 'NewYork' entries to NYG or NYJ.

    Matches by (season, gameday, opponent) against nflverse schedule
    to determine which NY team is correct.

    Args:
        odds_df: DataFrame with home_team_nfl and away_team_nfl columns.
        schedules: Dict mapping season -> nflverse schedule DataFrame.

    Returns:
        Updated DataFrame with NewYork resolved to NYG or NYJ.
    """
    df = odds_df.copy()

    # Find rows where home or away is None (unmapped "NewYork")
    ny_home = df["home_team_nfl"].isna()
    ny_away = df["away_team_nfl"].isna()
    ny_mask = ny_home | ny_away

    if ny_mask.sum() == 0:
        return df

    for idx in df[ny_mask].index:
        row = df.loc[idx]
        season = int(row["season"])
        gameday = row["gameday"]

        if season not in schedules:
            print(f"  WARNING: No schedule for season {season}, cannot resolve NewYork")
            continue

        sched = schedules[season].copy()
        sched["gameday_date"] = pd.to_datetime(sched["gameday"]).dt.date

        if ny_home[idx]:
            # NewYork is home team -- find which NY team is home on this date
            opponent_nfl = row["away_team_nfl"]
            matches = sched[
                (sched["gameday_date"] == gameday)
                & (sched["home_team"].isin(["NYG", "NYJ"]))
            ]
            if opponent_nfl is not None:
                # Further filter by away team matching the opponent
                matches = matches[matches["away_team"] == opponent_nfl]

            if len(matches) == 1:
                df.at[idx, "home_team_nfl"] = matches.iloc[0]["home_team"]
            elif len(matches) > 1:
                # Multiple matches -- take the first, log warning
                df.at[idx, "home_team_nfl"] = matches.iloc[0]["home_team"]
                print(
                    f"  WARNING: Multiple NYG/NYJ home matches on {gameday}, "
                    f"using {matches.iloc[0]['home_team']}"
                )
            else:
                print(
                    f"  WARNING: Could not resolve NewYork home team on {gameday}"
                )

        if ny_away[idx]:
            # NewYork is away team -- find which NY team is away on this date
            opponent_nfl = row["home_team_nfl"]
            matches = sched[
                (sched["gameday_date"] == gameday)
                & (sched["away_team"].isin(["NYG", "NYJ"]))
            ]
            if opponent_nfl is not None:
                matches = matches[matches["home_team"] == opponent_nfl]

            if len(matches) == 1:
                df.at[idx, "away_team_nfl"] = matches.iloc[0]["away_team"]
            elif len(matches) > 1:
                df.at[idx, "away_team_nfl"] = matches.iloc[0]["away_team"]
                print(
                    f"  WARNING: Multiple NYG/NYJ away matches on {gameday}, "
                    f"using {matches.iloc[0]['away_team']}"
                )
            else:
                print(
                    f"  WARNING: Could not resolve NewYork away team on {gameday}"
                )

    resolved = ny_mask.sum() - df["home_team_nfl"].isna().sum() - df["away_team_nfl"].isna().sum()
    if resolved > 0:
        print(f"  Resolved {resolved} NewYork entries")

    return df


# ── Spread Alignment ────────────────────────────────────────────────────


def align_spreads(df: pd.DataFrame) -> pd.DataFrame:
    """Negate FinnedAI spreads to match nflverse convention (positive = home favored).

    FinnedAI: negative = home favored (standard sportsbook).
    nflverse: positive = home favored.
    Action: negate FinnedAI spreads.

    Args:
        df: DataFrame with FinnedAI spread/total/moneyline columns.

    Returns:
        DataFrame with opening_spread, closing_spread, opening_total,
        closing_total, home_moneyline, away_moneyline columns added.
    """
    df["opening_spread"] = -df["home_open_spread"]
    df["closing_spread"] = -df["home_close_spread"]
    df["opening_total"] = df["open_over_under"]
    df["closing_total"] = df["close_over_under"]
    df["home_moneyline"] = df["home_close_ml"]
    df["away_moneyline"] = df["away_close_ml"]

    # Data quality: flag rows where spread exceeds plausible range (|spread| > 25).
    # FinnedAI has ~24 entries per season where totals are swapped into spread columns.
    corrupt_mask = (df["closing_spread"].abs() > 25) | (df["opening_spread"].abs() > 25)
    n_corrupt = corrupt_mask.sum()
    if n_corrupt > 0:
        print(f"  Dropped {n_corrupt} rows with implausible spreads (|spread| > 25)")
        df = df[~corrupt_mask].reset_index(drop=True)

    return df


# ── Join to nflverse ────────────────────────────────────────────────────


def join_to_nflverse(odds_df: pd.DataFrame, season: int) -> pd.DataFrame:
    """Join odds to nflverse schedules to inherit game_id.

    Merges on (season, home_team, gameday) to get game_id, week, game_type,
    and nflverse spread_line/total_line for inline cross-validation (D-17).

    Args:
        odds_df: DataFrame with home_team_nfl and gameday columns.
        season: NFL season year.

    Returns:
        Merged DataFrame with game_id, week, game_type, and nflverse lines.
    """
    sched = nfl.import_schedules([season])
    sched["gameday_date"] = pd.to_datetime(sched["gameday"]).dt.date

    merged = odds_df.merge(
        sched[
            [
                "game_id",
                "season",
                "week",
                "game_type",
                "home_team",
                "away_team",
                "gameday_date",
                "spread_line",
                "total_line",
            ]
        ],
        left_on=["season", "home_team_nfl", "gameday"],
        right_on=["season", "home_team", "gameday_date"],
        how="left",
        suffixes=("_sbro", ""),
    )

    # Rename nflverse fields for inline cross-validation (D-17)
    merged.rename(
        columns={
            "spread_line": "nflverse_spread_line",
            "total_line": "nflverse_total_line",
        },
        inplace=True,
    )

    # Log orphans (D-13)
    orphan_count = merged["game_id"].isna().sum()
    if orphan_count > 0:
        print(f"  WARNING: {orphan_count} odds rows with no nflverse match (season {season})")

    return merged


# ── Validation Functions ─────────────────────────────────────────────────


def validate_cross_correlation(df: pd.DataFrame) -> bool:
    """Assert closing line agreement between SBRO and nflverse (D-19).

    Checks: Pearson r > 0.95 AND >95% of games within 1.0 point.

    Args:
        df: DataFrame with closing_spread and nflverse_spread_line columns.

    Returns:
        True if both thresholds pass.

    Raises:
        ValueError: If either threshold fails.
    """
    valid = df.dropna(subset=["closing_spread", "nflverse_spread_line"])
    if len(valid) < 10:
        print("  WARNING: Too few rows for cross-validation, skipping")
        return True

    r, _ = pearsonr(valid["closing_spread"], valid["nflverse_spread_line"])
    within_1pt = (
        (valid["closing_spread"] - valid["nflverse_spread_line"]).abs() <= 1.0
    ).mean()

    print(f"  Cross-validation: r={r:.4f}, within 1pt={within_1pt:.1%}")

    if r < 0.95:
        raise ValueError(f"Pearson r={r:.4f} < 0.95 threshold")
    if within_1pt < 0.95:
        raise ValueError(f"Within 1pt={within_1pt:.1%} < 95% threshold")

    return True


def validate_sign_convention(df: pd.DataFrame) -> bool:
    """Validate spread sign convention matches nflverse (D-21).

    For games where nflverse spread_line > 7 (clear home favorites),
    assert opening_spread > 0 after negation.

    Args:
        df: DataFrame with opening_spread and nflverse_spread_line.

    Returns:
        True if all sign conventions match.

    Raises:
        ValueError: If any sign flip found.
    """
    valid = df.dropna(subset=["opening_spread", "nflverse_spread_line"])
    home_favorites = valid[valid["nflverse_spread_line"] > 7]

    if len(home_favorites) == 0:
        print("  WARNING: No clear home favorites for sign convention check")
        return True

    sign_flips = home_favorites[home_favorites["opening_spread"] < 0]
    if len(sign_flips) > 0:
        print(f"  FAIL: {len(sign_flips)} sign flips found in home favorites")
        raise ValueError(
            f"Sign convention mismatch: {len(sign_flips)} games where "
            f"nflverse_spread_line > 7 but opening_spread <= 0"
        )

    print(f"  Sign convention check passed ({len(home_favorites)} home favorites)")
    return True


def validate_odds_schema(df: pd.DataFrame) -> bool:
    """Validate required columns exist in the output DataFrame (D-08).

    Args:
        df: DataFrame to validate.

    Returns:
        True if all required columns present.

    Raises:
        ValueError: If any required columns are missing.
    """
    required = [
        "game_id",
        "season",
        "week",
        "game_type",
        "home_team",
        "away_team",
        "opening_spread",
        "closing_spread",
        "opening_total",
        "closing_total",
        "home_moneyline",
        "away_moneyline",
        "nflverse_spread_line",
        "nflverse_total_line",
    ]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")
    return True


def validate_row_counts(df: pd.DataFrame, season: int) -> None:
    """Warn if game count deviates significantly from expected (D-20).

    Args:
        df: DataFrame for a single season.
        season: NFL season year.
    """
    # Expected regular season: 256 pre-2021, 272 post-2021, plus ~11 playoffs
    if season >= 2021:
        expected_reg = 272
    else:
        expected_reg = 256
    expected_total = expected_reg + 11  # approximate with playoffs

    actual = len(df)
    deviation = abs(actual - expected_total) / expected_total
    if deviation > 0.05:
        print(
            f"  WARNING: Season {season} has {actual} games "
            f"(expected ~{expected_total}, deviation {deviation:.1%})"
        )
    else:
        print(f"  Row count: {actual} games for season {season} (within expected range)")


# ── nflverse Bridge Functions ──────────────────────────────────────────


def validate_nflverse_coverage(df: pd.DataFrame, season: int) -> None:
    """Validate nflverse-derived odds coverage (D-10, D-11).

    Checks NaN rate for spread_line and total_line (< 5%),
    and warns if playoff game count is low.

    Args:
        df: DataFrame with opening_spread, opening_total, week columns.
        season: NFL season year.

    Raises:
        ValueError: If no games found or NaN rate exceeds 5%.
    """
    total_games = len(df)
    if total_games == 0:
        raise ValueError(f"No games found for season {season}")
    spread_nan_rate = 1 - (df["opening_spread"].notna().sum() / total_games)
    total_nan_rate = 1 - (df["opening_total"].notna().sum() / total_games)
    if spread_nan_rate > 0.05:
        raise ValueError(
            f"Season {season}: spread NaN rate {spread_nan_rate:.1%} exceeds 5%"
        )
    if total_nan_rate > 0.05:
        raise ValueError(
            f"Season {season}: total NaN rate {total_nan_rate:.1%} exceeds 5%"
        )
    playoff_games = df[df["week"] >= 19]
    if len(playoff_games) < 10:
        print(
            f"  WARNING: Season {season} has only {len(playoff_games)} "
            f"playoff games (expected >= 10)"
        )
    print(
        f"  Coverage: {df['opening_spread'].notna().sum()}/{total_games} "
        f"games with spread, NaN rate={spread_nan_rate:.1%}, "
        f"playoffs={len(playoff_games)}"
    )


def derive_odds_from_nflverse(season: int, dry_run: bool = False) -> str:
    """Extract closing-line odds from nflverse schedules for seasons without FinnedAI.

    For 2022+, nflverse closing lines serve as opening-line proxies (D-05).
    Opening == Closing, so spread_shift/total_shift will be zero downstream.

    Args:
        season: NFL season year (2022+).
        dry_run: If True, skip writing Parquet.

    Returns:
        Output file path.

    Raises:
        ValueError: If season < 2022.
    """
    if season < 2022:
        raise ValueError(
            f"nflverse bridge only valid for seasons 2022+, got {season}"
        )
    print(f"Deriving odds from nflverse schedules for season {season}...")
    sched = nfl.import_schedules([season])
    df = pd.DataFrame(
        {
            "game_id": sched["game_id"],
            "season": sched["season"],
            "week": sched["week"],
            "game_type": sched["game_type"],
            "home_team": sched["home_team"],
            "away_team": sched["away_team"],
            "opening_spread": sched["spread_line"],  # D-05: closing as opening proxy
            "closing_spread": sched["spread_line"],
            "opening_total": sched["total_line"],
            "closing_total": sched["total_line"],
            "home_moneyline": sched["home_moneyline"],
            "away_moneyline": sched["away_moneyline"],
            "nflverse_spread_line": sched["spread_line"],
            "nflverse_total_line": sched["total_line"],
            "line_source": "nflverse",
        }
    )
    # D-04: preserve NaN rows (never drop, never zero-fill)
    # Cast moneylines to match FinnedAI dtype where non-null
    ml_cols = ["home_moneyline", "away_moneyline"]
    for col in ml_cols:
        non_null = df[col].notna()
        if non_null.any():
            df.loc[non_null, col] = df.loc[non_null, col].astype(int)
    validate_nflverse_coverage(df, season)
    return write_parquet(df, season, dry_run=dry_run)


# ── Parquet Output ──────────────────────────────────────────────────────


FINAL_COLUMNS = [
    "game_id",
    "season",
    "week",
    "game_type",
    "home_team",
    "away_team",
    "opening_spread",
    "closing_spread",
    "opening_total",
    "closing_total",
    "home_moneyline",
    "away_moneyline",
    "nflverse_spread_line",
    "nflverse_total_line",
    "line_source",
]


def write_parquet(df: pd.DataFrame, season: int, dry_run: bool = False) -> str:
    """Write per-season Parquet file to Bronze odds directory.

    Args:
        df: DataFrame with final columns.
        season: NFL season year.
        dry_run: If True, skip writing.

    Returns:
        Output file path.
    """
    # Select final columns only
    available = [c for c in FINAL_COLUMNS if c in df.columns]
    out_df = df[available].copy()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BRONZE_DIR, f"season={season}")
    out_path = os.path.join(out_dir, f"odds_{timestamp}.parquet")

    if dry_run:
        print(f"  [DRY RUN] Would write {len(out_df)} rows to {out_path}")
        return out_path

    os.makedirs(out_dir, exist_ok=True)
    out_df.to_parquet(out_path, index=False)
    print(f"  Wrote {len(out_df)} rows to {out_path}")
    return out_path


# ── Main Pipeline ───────────────────────────────────────────────────────


def main():
    """Run the Bronze odds ingestion pipeline."""
    parser = argparse.ArgumentParser(
        description="Bronze Odds Ingestion -- FinnedAI JSON to Parquet"
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="Process single season (default: all 2016-2021)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and validate but don't write Parquet",
    )
    parser.add_argument(
        "--force-download",
        action="store_true",
        help="Re-download JSON even if exists",
    )
    parser.add_argument(
        "--source",
        choices=["finnedai", "sbro", "nflverse"],
        default="finnedai",
        help="Data source: 'finnedai' (2016-2021), 'nflverse' (2022+), or 'sbro' XLSX fallback",
    )
    args = parser.parse_args()

    # Determine seasons to process
    if args.season is not None:
        # Season validation guard
        try:
            valid = validate_season_for_type("odds", args.season)
            if not valid:
                raise ValueError(
                    f"Season {args.season} is not valid for odds data type (valid: 2016-2021)"
                )
        except ValueError as e:
            if "Unknown data type" in str(e):
                # odds not yet registered in config.py (Plan 32-02)
                if not (2016 <= args.season <= 2021):
                    raise ValueError(
                        f"Season {args.season} is not valid for odds data type (valid: 2016-2021)"
                    )
            else:
                raise
        seasons = [args.season]
    else:
        seasons = SEASONS

    print(f"Bronze Odds Ingestion -- seasons: {seasons}")
    print(f"  Source: {args.source}")

    # Handle nflverse source separately (no download, no FinnedAI pipeline)
    if args.source == "nflverse":
        if args.season is not None:
            derive_odds_from_nflverse(args.season, dry_run=args.dry_run)
        else:
            # Default: all nflverse seasons (2022+)
            for s in range(2022, datetime.now().year + 1):
                derive_odds_from_nflverse(s, dry_run=args.dry_run)
        return

    # Step 1: Download
    if args.source == "finnedai":
        json_path = download_finnedai(force=args.force_download)
    else:
        # SBRO XLSX fallback -- minimal implementation (D-03)
        print("  SBRO XLSX fallback not fully implemented; use --source finnedai")
        return

    # Step 2: Parse
    print("Parsing FinnedAI JSON...")
    odds_df = parse_finnedai(json_path, seasons=seasons)
    if odds_df.empty:
        print("  No data found for requested seasons")
        return
    print(f"  Parsed {len(odds_df)} games")

    # Step 3: Load nflverse schedules for all seasons (for NewYork resolution)
    print("Loading nflverse schedules...")
    nflverse_schedules = {}
    for s in seasons:
        try:
            nflverse_schedules[s] = nfl.import_schedules([s])
        except Exception as e:
            print(f"  WARNING: Could not load schedule for {s}: {e}")

    # Step 4: Resolve NewYork ambiguity
    print("Resolving NewYork ambiguity...")
    odds_df = resolve_newyork(odds_df, nflverse_schedules)

    # Step 5: Align spreads (negate for nflverse convention)
    print("Aligning spread conventions...")
    odds_df = align_spreads(odds_df)

    # Step 6: Join to nflverse per season, validate, write
    total_games = 0
    total_orphans = 0
    written_paths = []

    for season in seasons:
        print(f"\n--- Season {season} ---")
        season_df = odds_df[odds_df["season"] == season].copy()
        if season_df.empty:
            print(f"  No data for season {season}")
            continue

        # Join to nflverse
        merged = join_to_nflverse(season_df, season)

        # Track orphans
        orphans = merged["game_id"].isna().sum()
        total_orphans += orphans

        # Drop orphan rows (they have no game_id)
        if orphans > 0:
            merged = merged.dropna(subset=["game_id"])

        # Validate
        try:
            validate_cross_correlation(merged)
            validate_sign_convention(merged)
            validate_odds_schema(merged)
            validate_row_counts(merged, season)
        except ValueError as e:
            print(f"  VALIDATION FAILED for season {season}: {e}")
            continue

        total_games += len(merged)

        # Add provenance column (D-03)
        merged["line_source"] = "finnedai"

        # Write Parquet
        path = write_parquet(merged, season, dry_run=args.dry_run)
        written_paths.append(path)

    # Summary
    print(f"\n{'='*60}")
    print(f"Summary: {total_games} games processed across {len(seasons)} seasons")
    print(f"  Orphans: {total_orphans}")
    print(f"  Files written: {len(written_paths)}")
    if args.dry_run:
        print("  [DRY RUN -- no files were written]")


if __name__ == "__main__":
    main()
