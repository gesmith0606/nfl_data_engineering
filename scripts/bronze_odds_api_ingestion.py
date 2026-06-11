#!/usr/bin/env python3
"""
Bronze Odds API Ingestion — The Odds API v4

Fetches live NFL spread and total lines from api.the-odds-api.com and writes
timestamped Bronze Parquet snapshots.  Each run appends a new file so the
first snapshot of the day serves as an opener proxy and the last as a close
proxy (full open/close history accumulates over the season).

Output path:
    data/bronze/odds_api/snapshots/season=YYYY/odds_YYYYMMDD_HHMMSS.parquet

Schema (one row per game × bookmaker × market):
    snapshot_ts       — UTC ISO-8601 string when this snapshot was taken
    game_id_ext       — The Odds API game id (opaque string)
    commence_time     — ISO-8601 UTC kick-off time
    home_team         — full team name (API canonical)
    away_team         — full team name (API canonical)
    home_team_nfl     — nflverse abbreviation (e.g. "KC")
    away_team_nfl     — nflverse abbreviation
    bookmaker         — bookmaker key (e.g. "fanduel")
    market            — "spreads" or "totals"
    home_spread       — home point spread (negative = home favored, sportsbook sign)
    total_points      — over/under total (totals market only, else NaN)
    price_home        — American odds for home side / over
    price_away        — American odds for away side / under
    season            — inferred NFL season year

Usage:
    python scripts/bronze_odds_api_ingestion.py
    python scripts/bronze_odds_api_ingestion.py --dry-run
    python scripts/bronze_odds_api_ingestion.py --bookmakers fanduel draftkings

Environment:
    ODDS_API_KEY — required (get a free key at https://the-odds-api.com)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, List, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project root on sys.path so src.* imports work
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

load_dotenv()

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_BASE_URL = "https://api.the-odds-api.com"
ODDS_ENDPOINT = (
    "/v4/sports/americanfootball_nfl/odds"
    "?regions=us&markets=spreads,totals&oddsFormat=american"
)
BRONZE_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "bronze",
    "odds_api",
    "snapshots",
)

# The Odds API uses full team names; map them to nflverse abbreviations.
# Covers all 32 current franchises plus recent relocations / renames.
ODDS_API_TO_NFLVERSE: dict = {
    # AFC East
    "Buffalo Bills": "BUF",
    "Miami Dolphins": "MIA",
    "New England Patriots": "NE",
    "New York Jets": "NYJ",
    # AFC North
    "Baltimore Ravens": "BAL",
    "Cincinnati Bengals": "CIN",
    "Cleveland Browns": "CLE",
    "Pittsburgh Steelers": "PIT",
    # AFC South
    "Houston Texans": "HOU",
    "Indianapolis Colts": "IND",
    "Jacksonville Jaguars": "JAX",
    "Tennessee Titans": "TEN",
    # AFC West
    "Kansas City Chiefs": "KC",
    "Las Vegas Raiders": "LV",
    "Los Angeles Chargers": "LAC",
    "Denver Broncos": "DEN",
    # NFC East
    "Dallas Cowboys": "DAL",
    "New York Giants": "NYG",
    "Philadelphia Eagles": "PHI",
    "Washington Commanders": "WAS",
    # NFC North
    "Chicago Bears": "CHI",
    "Detroit Lions": "DET",
    "Green Bay Packers": "GB",
    "Minnesota Vikings": "MIN",
    # NFC South
    "Atlanta Falcons": "ATL",
    "Carolina Panthers": "CAR",
    "New Orleans Saints": "NO",
    "Tampa Bay Buccaneers": "TB",
    # NFC West
    "Arizona Cardinals": "ARI",
    "Los Angeles Rams": "LA",
    "San Francisco 49ers": "SF",
    "Seattle Seahawks": "SEA",
    # Historical / pre-move names (may appear for future seasons)
    "Oakland Raiders": "OAK",
    "San Diego Chargers": "SD",
    "Washington Redskins": "WAS",
    "Washington Football Team": "WAS",
    "St. Louis Rams": "LA",
}


# ---------------------------------------------------------------------------
# Season inference
# ---------------------------------------------------------------------------


def infer_nfl_season(commence_time: str) -> int:
    """Return the NFL season year for a given game commence_time.

    The NFL season runs September through January/February.  Games in
    January or February belong to the season that started the prior year.

    Args:
        commence_time: ISO-8601 UTC string, e.g. "2026-01-11T18:00:00Z".

    Returns:
        Four-digit season year (e.g. 2025 for a January 2026 game).

    Examples:
        >>> infer_nfl_season("2026-09-05T17:00:00Z")
        2026
        >>> infer_nfl_season("2027-01-11T18:00:00Z")
        2026
    """
    dt = datetime.fromisoformat(commence_time.replace("Z", "+00:00"))
    season = dt.year - 1 if dt.month <= 2 else dt.year
    # Guard against malformed API timestamps producing out-of-range season
    # partitions that would be committed to git by the capture cron.
    if not 1999 <= season <= 2100:
        raise ValueError(
            f"Inferred season {season} outside valid range for "
            f"commence_time={commence_time!r}"
        )
    return season


# ---------------------------------------------------------------------------
# API fetch
# ---------------------------------------------------------------------------


def fetch_odds(
    api_key: str, bookmakers: Optional[List[str]] = None
) -> Tuple[List[dict], dict]:
    """Fetch current NFL odds from The Odds API.

    Args:
        api_key: The Odds API key.
        bookmakers: Optional list of bookmaker keys to filter (e.g.
            ["fanduel", "draftkings"]).  When None, the API returns all
            available US bookmakers.

    Returns:
        Tuple of (games list, headers dict).  On network or HTTP error,
        raises requests.RequestException so the caller can handle fail-open.

    Raises:
        requests.RequestException: On network or non-2xx HTTP response.
    """
    url = f"{API_BASE_URL}{ODDS_ENDPOINT}&apiKey={api_key}"
    if bookmakers:
        url += f"&bookmakers={','.join(bookmakers)}"

    logger.info("Fetching odds from The Odds API...")
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json(), dict(response.headers)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalize_game(
    game: dict,
    snapshot_ts: str,
) -> List[dict]:
    """Expand a single game dict into per-(bookmaker, market) rows.

    Args:
        game: A single game object from The Odds API response.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        List of flat dicts, one per (bookmaker, market).  Empty list if
        the game has no bookmaker data.
    """
    game_id_ext = game.get("id", "")
    commence_time = game.get("commence_time", "")
    home_team_raw = game.get("home_team", "")
    away_team_raw = game.get("away_team", "")

    home_team_nfl = ODDS_API_TO_NFLVERSE.get(home_team_raw)
    away_team_nfl = ODDS_API_TO_NFLVERSE.get(away_team_raw)

    if home_team_nfl is None:
        logger.warning("Unmapped home team: %s", home_team_raw)
    if away_team_nfl is None:
        logger.warning("Unmapped away team: %s", away_team_raw)

    season = infer_nfl_season(commence_time) if commence_time else None
    rows: List[dict] = []

    for bm in game.get("bookmakers", []):
        bookmaker = bm.get("key", "")
        for market_obj in bm.get("markets", []):
            market = market_obj.get("key", "")
            outcomes = {o["name"]: o for o in market_obj.get("outcomes", [])}

            home_spread: Optional[float] = None
            total_points: Optional[float] = None
            price_home: Optional[float] = None
            price_away: Optional[float] = None

            if market == "spreads":
                home_out = outcomes.get(home_team_raw, {})
                away_out = outcomes.get(away_team_raw, {})
                home_spread = home_out.get("point")
                price_home = home_out.get("price")
                price_away = away_out.get("price")

            elif market == "totals":
                over_out = outcomes.get("Over", {})
                under_out = outcomes.get("Under", {})
                total_points = over_out.get("point")
                price_home = over_out.get("price")  # over
                price_away = under_out.get("price")  # under

            rows.append(
                {
                    "snapshot_ts": snapshot_ts,
                    "game_id_ext": game_id_ext,
                    "commence_time": commence_time,
                    "home_team": home_team_raw,
                    "away_team": away_team_raw,
                    "home_team_nfl": home_team_nfl,
                    "away_team_nfl": away_team_nfl,
                    "bookmaker": bookmaker,
                    "market": market,
                    "home_spread": home_spread,
                    "total_points": total_points,
                    "price_home": price_home,
                    "price_away": price_away,
                    "season": season,
                }
            )

    return rows


def normalize_response(
    games: List[dict],
    snapshot_ts: str,
) -> pd.DataFrame:
    """Normalise the full API response into a tidy DataFrame.

    Args:
        games: List of game dicts returned by the API.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        DataFrame with one row per (game, bookmaker, market).
        Returns an empty DataFrame (with correct columns) when games is empty.
    """
    schema_cols = [
        "snapshot_ts",
        "game_id_ext",
        "commence_time",
        "home_team",
        "away_team",
        "home_team_nfl",
        "away_team_nfl",
        "bookmaker",
        "market",
        "home_spread",
        "total_points",
        "price_home",
        "price_away",
        "season",
    ]

    if not games:
        logger.info("API returned 0 games (off-season or no data).")
        return pd.DataFrame(columns=schema_cols)

    rows: List[dict] = []
    for game in games:
        rows.extend(normalize_game(game, snapshot_ts))

    df = pd.DataFrame(rows, columns=schema_cols)

    # Log any remaining unmapped teams
    unmapped_home = df.loc[df["home_team_nfl"].isna(), "home_team"].unique()
    unmapped_away = df.loc[df["away_team_nfl"].isna(), "away_team"].unique()
    if len(unmapped_home):
        logger.warning(
            "Unmapped home teams (no nflverse abbr): %s", list(unmapped_home)
        )
    if len(unmapped_away):
        logger.warning(
            "Unmapped away teams (no nflverse abbr): %s", list(unmapped_away)
        )

    return df


# ---------------------------------------------------------------------------
# Parquet output
# ---------------------------------------------------------------------------


def write_parquet(df: pd.DataFrame, season: int, dry_run: bool = False) -> str:
    """Write snapshot DataFrame to Bronze Parquet.

    Args:
        df: Normalised odds DataFrame.
        season: NFL season year (used for partition directory).
        dry_run: When True, skip all file I/O.

    Returns:
        Absolute output path (whether or not the file was written).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BRONZE_DIR, f"season={season}")
    out_path = os.path.join(out_dir, f"odds_{timestamp}.parquet")

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to %s", len(df), out_path)
        return out_path

    os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(df), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Quota logging
# ---------------------------------------------------------------------------


def log_quota(headers: dict[str, str]) -> None:
    """Log The Odds API request quota from response headers.

    Args:
        headers: Response headers dict (case-insensitive dict or plain dict).
    """
    # Header names are case-insensitive; normalise to lower-case for lookup.
    lower = {k.lower(): v for k, v in headers.items()}
    remaining = lower.get("x-requests-remaining", "unknown")
    used = lower.get("x-requests-used", "unknown")
    logger.info(
        "The Odds API quota — requests used: %s, requests remaining: %s",
        used,
        remaining,
    )


# ---------------------------------------------------------------------------
# Config validation (used by --dry-run)
# ---------------------------------------------------------------------------


def validate_config() -> bool:
    """Check that ODDS_API_KEY is present and BRONZE_DIR is writable.

    Returns:
        True when config is valid.
    """
    key = os.environ.get("ODDS_API_KEY")
    if not key:
        logger.error(
            "ODDS_API_KEY not set. "
            "Register for a free key at https://the-odds-api.com and add it to .env."
        )
        return False
    logger.info("ODDS_API_KEY found (length %d).", len(key))
    logger.info("Output directory: %s", BRONZE_DIR)
    return True


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run(
    api_key: str,
    bookmakers: Optional[List[str]] = None,
    dry_run: bool = False,
) -> int:
    """Fetch, normalise, and persist a single odds snapshot.

    Args:
        api_key: The Odds API key.
        bookmakers: Optional bookmaker filter list.
        dry_run: When True, fetch API data but write nothing.

    Returns:
        Exit code (0 = success or graceful skip, 1 = hard error).
    """
    snapshot_ts = datetime.now(timezone.utc).isoformat()

    try:
        games, headers = fetch_odds(api_key, bookmakers=bookmakers)
    except requests.RequestException as exc:
        # HTTPError messages embed the request URL, which carries the API
        # key as a query parameter — redact it before it reaches (public)
        # GHA logs.
        sanitized = str(exc).replace(api_key, "***") if api_key else str(exc)
        logger.warning(
            "The Odds API request failed (fail-open): %s. "
            "No parquet written; cron will retry next run.",
            sanitized,
        )
        return 0

    log_quota(headers)

    # Fail-open on normalization too: a malformed API payload (e.g. a
    # semantically bad commence_time tripping the season bounds guard)
    # must log-and-skip, not crash the cron run.
    try:
        df = normalize_response(games, snapshot_ts)
    except (ValueError, KeyError, TypeError) as exc:
        logger.warning(
            "Odds payload normalization failed (fail-open): %s. "
            "No parquet written; cron will retry next run.",
            exc,
        )
        return 0
    logger.info("Normalised %d rows from %d games.", len(df), len(games))

    if df.empty:
        logger.info("No odds data to write (off-season or no NFL games listed).")
        return 0

    # Determine which season(s) are present and write one file per season.
    # In practice all pre-season / regular-season games share one season value,
    # but we handle the boundary week (Jan games for prior season) cleanly.
    seasons = df["season"].dropna().unique()
    if len(seasons) == 0:
        logger.warning("Could not infer season from any game; skipping write.")
        return 0

    for season in sorted(seasons):
        season_df = df[df["season"] == season].copy()
        if season_df.empty:
            continue
        write_parquet(season_df, int(season), dry_run=dry_run)

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the Bronze Odds API ingestion script."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch live NFL odds from The Odds API and write Bronze Parquet snapshots. "
            "Designed for 2×/day cron execution; exits 0 on any network error "
            "(fail-open) to prevent cron spam."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Validate config and (if an API key exists) fetch data, but do NOT "
            "write any Parquet files. Useful for CI verification."
        ),
    )
    parser.add_argument(
        "--bookmakers",
        nargs="+",
        metavar="BOOK",
        default=None,
        help=(
            "Filter to specific bookmaker keys, e.g. --bookmakers fanduel draftkings. "
            "Defaults to all available US bookmakers."
        ),
    )
    args = parser.parse_args()

    # --dry-run with no key: validate config only, no network call.
    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        if args.dry_run:
            logger.info("[DRY RUN] No ODDS_API_KEY — config validation only.")
            logger.info(
                "Register for a free key at https://the-odds-api.com, "
                "then add ODDS_API_KEY=<key> to .env and to the GitHub repo secrets."
            )
            logger.info("Output directory would be: %s", BRONZE_DIR)
            sys.exit(0)
        else:
            logger.error(
                "ODDS_API_KEY not set. "
                "Register at https://the-odds-api.com and add ODDS_API_KEY to .env."
            )
            # Fail-open: exit 0 so cron doesn't page on a missing key.
            sys.exit(0)

    if args.dry_run:
        logger.info("[DRY RUN] Config valid. Would fetch odds and write parquet.")
        validate_config()

    exit_code = run(api_key=api_key, bookmakers=args.bookmakers, dry_run=args.dry_run)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
