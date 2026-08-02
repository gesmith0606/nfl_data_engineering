#!/usr/bin/env python3
"""
Bronze Season Player Props Ingestion — DraftKings season-long player futures.

Fetches NFL *season-total* player over/under lines (regular-season passing/
rushing/receiving yards, passing/rushing/receiving TDs, receptions) from the
DraftKings sportsbook JSON API and writes timestamped Bronze Parquet
snapshots. These are the draft-relevant markets: a season rushing-yards O/U
prices the market's full-season expectation for a player, availability
included — the sharpest per-player season consensus available before Week 1.

The Odds API (our weekly-props source) does not carry season-long player
markets, so this script talks to DraftKings directly. No API key is needed,
but DraftKings sits behind Akamai TLS fingerprinting, so plain ``requests``
gets a 403 — ``curl_cffi`` with Chrome impersonation is required.

Output path:
    data/bronze/dk/season_props/season=YYYY/season_props_YYYYMMDD_HHMMSS.parquet

Schema (one row per market = one player × one season stat):
    snapshot_ts   — UTC ISO-8601 string when this snapshot was taken
    bookmaker     — always "draftkings"
    market        — canonical key (e.g. "season_rush_yds"; see SEASON_MARKETS)
    market_name   — raw DraftKings market name
    event_id      — DraftKings event id (one event per player)
    player_name   — player name from the event name
    team_nfl      — nflverse team abbreviation (from event participants)
    line          — season-total over/under line (e.g. 824.5)
    price_over    — American odds for Over
    price_under   — American odds for Under
    season        — NFL season year parsed from "NFL 2026/27 - ..." naming

The column names line/price_over/price_under/market/player_name/bookmaker/
snapshot_ts intentionally match the weekly props schema so the de-vig +
line-inversion machinery in ``src/prop_implied.py`` consumes either frame.

Usage:
    python scripts/bronze_season_props_ingestion.py
    python scripts/bronze_season_props_ingestion.py --dry-run
    python scripts/bronze_season_props_ingestion.py --markets season_rush_yds season_rec_yds
"""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
API_BASE_URL = (
    "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/88808"
)

#: Canonical market key -> (categoryId, subcategoryId) on DraftKings.
#: All are two-way over/under markets under the "Player Futures" category
#: (1759). Rookie "Milestones" markets (category 1801) are one-sided
#: threshold bets with different math — deliberately out of scope here.
SEASON_MARKETS: Dict[str, Tuple[int, int]] = {
    "season_pass_yds": (1759, 17147),
    "season_pass_tds": (1759, 17148),
    "season_rush_yds": (1759, 17223),
    "season_rush_tds": (1759, 17224),
    "season_rec_yds": (1759, 17314),
    "season_rec_tds": (1759, 17315),
    "season_receptions": (1759, 18435),
}

BRONZE_SEASON_PROPS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "bronze",
    "dk",
    "season_props",
)

SEASON_PROPS_SCHEMA_COLS: List[str] = [
    "snapshot_ts",
    "bookmaker",
    "market",
    "market_name",
    "event_id",
    "player_name",
    "team_nfl",
    "line",
    "price_over",
    "price_under",
    "season",
]

#: Seconds to sleep between per-subcategory requests (politeness).
REQUEST_DELAY_S = 1.0

_EVENT_NAME_RE = re.compile(r"^NFL\s+(\d{4})/\d{2}\s*-\s*(.+)$")
_LABEL_LINE_RE = re.compile(r"^(Over|Under)\s+([\d,]+(?:\.\d+)?)$")


def parse_american_odds(display: Optional[str]) -> Optional[int]:
    """Parse a DraftKings display odds string into an American odds int.

    DraftKings renders negative odds with a Unicode minus sign (U+2212),
    e.g. ``"−110"``; positive odds carry an explicit ``"+"``.

    Args:
        display: Odds string from ``displayOdds.american`` (may be None).

    Returns:
        Integer American odds, or None when missing/unparseable.
    """
    if not display:
        return None
    cleaned = display.replace("−", "-").replace("+", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_event_name(event_name: str) -> Tuple[Optional[int], Optional[str]]:
    """Split a DraftKings futures event name into (season, player_name).

    Event names look like ``"NFL 2026/27 - Mike Evans"`` — the leading year
    of the split-year label is the NFL season.

    Args:
        event_name: Raw event name string.

    Returns:
        Tuple of (season year, player name); (None, None) when the name
        does not match the expected pattern.
    """
    match = _EVENT_NAME_RE.match(event_name or "")
    if not match:
        return None, None
    return int(match.group(1)), match.group(2).strip()


def parse_line_from_label(label: str) -> Optional[float]:
    """Extract the numeric line from a selection label like ``"Over 824.5"``.

    Args:
        label: Selection label string.

    Returns:
        The line as float, or None when the label has no parseable number.
    """
    match = _LABEL_LINE_RE.match((label or "").strip())
    if not match:
        return None
    return float(match.group(2).replace(",", ""))


def extract_team_nfl(participants: List[dict]) -> Optional[str]:
    """Pull the nflverse team abbreviation from event participants.

    Player futures events list the player and their team both typed
    ``"Team"``; only the real team carries ``metadata.shortName``.

    Args:
        participants: Event ``participants`` list.

    Returns:
        Team abbreviation (e.g. ``"SEA"``) or None.
    """
    for participant in participants or []:
        short = (participant.get("metadata") or {}).get("shortName")
        if short:
            return short
    return None


def normalize_subcategory_response(
    data: dict,
    market_key: str,
    snapshot_ts: str,
) -> List[dict]:
    """Normalise one subcategory API response into season-prop rows.

    Joins ``selections`` (Over/Under pairs) to ``markets`` (one per player)
    to ``events`` (player + team identity). Markets missing either side of
    the two-way price are still emitted with the available side — the
    downstream de-vig skips one-sided quotes.

    Args:
        data: Parsed JSON response with ``events``/``markets``/``selections``.
        market_key: Canonical market key for these rows (SEASON_MARKETS key).
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        List of flat dicts matching SEASON_PROPS_SCHEMA_COLS.
    """
    events = {e.get("id"): e for e in data.get("events", [])}
    selections_by_market: Dict[str, Dict[str, dict]] = {}
    for sel in data.get("selections", []):
        side = sel.get("outcomeType", "")
        if side not in ("Over", "Under"):
            continue
        selections_by_market.setdefault(sel.get("marketId", ""), {})[side] = sel

    rows: List[dict] = []
    for market in data.get("markets", []):
        market_id = market.get("id", "")
        sides = selections_by_market.get(market_id)
        if not sides:
            continue

        event = events.get(market.get("eventId"), {})
        season, player_name = parse_event_name(event.get("name", ""))
        if not player_name:
            logger.warning(
                "Unparseable event name %r for market %s — skipping",
                event.get("name"),
                market.get("name"),
            )
            continue

        over = sides.get("Over", {})
        under = sides.get("Under", {})
        line = parse_line_from_label(over.get("label", "")) or parse_line_from_label(
            under.get("label", "")
        )
        if line is None:
            logger.warning(
                "No parseable line for market %s (labels %r/%r) — skipping",
                market.get("name"),
                over.get("label"),
                under.get("label"),
            )
            continue

        rows.append(
            {
                "snapshot_ts": snapshot_ts,
                "bookmaker": "draftkings",
                "market": market_key,
                "market_name": market.get("name", ""),
                "event_id": market.get("eventId", ""),
                "player_name": player_name,
                "team_nfl": extract_team_nfl(event.get("participants", [])),
                "line": line,
                "price_over": parse_american_odds(
                    (over.get("displayOdds") or {}).get("american")
                ),
                "price_under": parse_american_odds(
                    (under.get("displayOdds") or {}).get("american")
                ),
                "season": season,
            }
        )
    return rows


def fetch_subcategory(category_id: int, subcategory_id: int) -> dict:
    """Fetch one category/subcategory odds payload from DraftKings.

    Args:
        category_id: DraftKings category id (e.g. 1759 = Player Futures).
        subcategory_id: DraftKings subcategory id (e.g. 17223 = Rushing Yards).

    Returns:
        Parsed JSON dict.

    Raises:
        RuntimeError: On non-200 HTTP status.
        Exception: Propagates curl_cffi network errors.
    """
    from curl_cffi import requests as cffi_requests

    url = f"{API_BASE_URL}/categories/{category_id}/subcategories/{subcategory_id}"
    response = cffi_requests.get(url, impersonate="chrome110", timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for {url}")
    return response.json()


def write_season_props_parquet(
    df: pd.DataFrame,
    season: int,
    dry_run: bool = False,
) -> str:
    """Write a season-props snapshot DataFrame to Bronze Parquet.

    Args:
        df: Normalised season props DataFrame.
        season: NFL season year (partition directory).
        dry_run: When True, skip all file I/O.

    Returns:
        Absolute output path (whether or not the file was written).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BRONZE_SEASON_PROPS_DIR, f"season={season}")
    out_path = os.path.join(out_dir, f"season_props_{timestamp}.parquet")

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to %s", len(df), out_path)
        return out_path

    os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(df), out_path)
    return out_path


def run_season_props(
    markets: Optional[List[str]] = None,
    dry_run: bool = False,
) -> int:
    """Fetch, normalise, and persist a season-props snapshot.

    Fail-open by design (mirrors the weekly props cron): any per-market
    fetch error logs a warning and moves on; a run that collects zero rows
    exits 0 without writing.

    Args:
        markets: Canonical market keys to fetch (default: all SEASON_MARKETS).
        dry_run: When True, fetch and report but do not write Parquet.

    Returns:
        Exit code (0 = success or graceful skip, 1 = bad arguments).
    """
    if markets is None:
        markets = list(SEASON_MARKETS)
    unknown = [m for m in markets if m not in SEASON_MARKETS]
    if unknown:
        logger.error(
            "Unknown market keys %s. Valid: %s", unknown, sorted(SEASON_MARKETS)
        )
        return 1

    snapshot_ts = datetime.now(timezone.utc).isoformat()
    all_rows: List[dict] = []

    for idx, market_key in enumerate(markets):
        category_id, subcategory_id = SEASON_MARKETS[market_key]
        try:
            data = fetch_subcategory(category_id, subcategory_id)
        except Exception as exc:  # network/HTTP — fail-open per market
            logger.warning("Fetch failed for %s (skipping): %s", market_key, exc)
            continue
        rows = normalize_subcategory_response(data, market_key, snapshot_ts)
        logger.info("%s: %d player lines", market_key, len(rows))
        all_rows.extend(rows)
        if idx < len(markets) - 1:
            time.sleep(REQUEST_DELAY_S)

    if not all_rows:
        logger.info("No season prop rows collected (offseason menu not posted?).")
        return 0

    df = pd.DataFrame(all_rows, columns=SEASON_PROPS_SCHEMA_COLS)

    seasons = df["season"].dropna().unique()
    for season in sorted(seasons):
        season_df = df[df["season"] == season].copy()
        write_season_props_parquet(season_df, int(season), dry_run=dry_run)

    logger.info(
        "Season props snapshot complete: %d rows, %d players, markets=%s",
        len(df),
        df["player_name"].nunique(),
        sorted(df["market"].unique()),
    )
    return 0


def main() -> None:
    """Entry point for the Bronze season player props ingestion script."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch NFL season-long player futures (season yards/TDs/receptions "
            "over-unders) from DraftKings and write Bronze Parquet snapshots."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and normalise but do not write Parquet files.",
    )
    parser.add_argument(
        "--markets",
        nargs="+",
        metavar="MARKET",
        default=None,
        help=(
            "Canonical market keys to fetch (space-separated). "
            f"Default: {' '.join(SEASON_MARKETS)}"
        ),
    )
    args = parser.parse_args()
    sys.exit(run_season_props(markets=args.markets, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
