#!/usr/bin/env python3
"""
Bronze Player Props Ingestion — The Odds API v4 events/{id}/odds endpoint

Fetches NFL player-prop lines from api.the-odds-api.com and writes timestamped
Bronze Parquet snapshots.  Designed to run once weekly (Sunday ~14:00 UTC) when
prop menus are final and inactive lists are out.

Each run appends a new file so the full pre-game prop history accumulates before
the 2026 season and can later be used as a prop-implied projection signal.

Output path:
    data/bronze/odds_api/props/season=YYYY/props_YYYYMMDD_HHMMSS.parquet

Schema (one row per event × bookmaker × market × player outcome):
    snapshot_ts     — UTC ISO-8601 string when this snapshot was taken
    event_id        — The Odds API event id (opaque string)
    commence_time   — ISO-8601 UTC kick-off time
    home_team       — full team name (API canonical)
    away_team       — full team name (API canonical)
    home_team_nfl   — nflverse abbreviation (e.g. "KC")
    away_team_nfl   — nflverse abbreviation
    bookmaker       — bookmaker key (e.g. "draftkings")
    market          — prop market key (e.g. "player_reception_yds")
    player_name     — player name extracted from outcome description
    line            — point total for over/under markets (NaN for anytime_td)
    price_over      — American odds for Over (or single price for anytime_td)
    price_under     — American odds for Under (None for anytime_td)
    season          — inferred NFL season year

Credit cost:
    - /events fetch:                     0 credits (free endpoint)
    - /events/{id}/odds per call:        #markets × #regions credits
    - Default 5 markets, region=us → 5 credits/event
    - With --days-ahead 7, in-season Sundays see 13-17 events → 65-85 credits/run
      (off-season weekdays often 0-5 events → 0-25 credits)

Usage:
    python scripts/bronze_props_ingestion.py
    python scripts/bronze_props_ingestion.py --dry-run
    python scripts/bronze_props_ingestion.py --days-ahead 14 --max-credits 120
    python scripts/bronze_props_ingestion.py --markets player_anytime_td player_rush_yds
    python scripts/bronze_props_ingestion.py --dry-run --days-ahead 3

Environment:
    ODDS_API_KEY — required (get a free key at https://the-odds-api.com)
"""

import argparse
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd
import requests
from dotenv import load_dotenv

# ---------------------------------------------------------------------------
# Project root on sys.path so src.* imports work
# ---------------------------------------------------------------------------
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# Reuse shared helpers from the spreads script to avoid duplication.
from scripts.bronze_odds_api_ingestion import (
    ODDS_API_TO_NFLVERSE,
    infer_nfl_season,
    log_quota,
)

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
EVENTS_ENDPOINT = "/v4/sports/americanfootball_nfl/events"

#: Default prop markets to fetch; 5 markets × 1 region = 5 credits/event.
DEFAULT_MARKETS: List[str] = [
    "player_reception_yds",
    "player_rush_yds",
    "player_pass_yds",
    "player_receptions",
    "player_anytime_td",
]

#: Markets whose outcome shape is binary (yes/no) rather than over/under.
#: For these, price_over carries the single price and price_under is None.
BINARY_MARKETS = frozenset(["player_anytime_td"])

BRONZE_PROPS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "bronze",
    "odds_api",
    "props",
)

#: Stop mid-run if x-requests-remaining drops to or below this threshold.
#: Reserves headroom for the twice-daily spreads cron (~2 credits/run).
CREDIT_RESERVE_THRESHOLD = 50

# ---------------------------------------------------------------------------
# Schema column order (enforced on every output DataFrame)
# ---------------------------------------------------------------------------
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


# ---------------------------------------------------------------------------
# Credit estimation
# ---------------------------------------------------------------------------


def estimate_credits(
    event_count: int,
    markets: List[str],
    regions: int = 1,
) -> int:
    """Estimate API credit cost for fetching props for a set of events.

    Each per-event props call costs (len(markets) × regions) credits.
    The events-list fetch itself is free (0 credits).

    Args:
        event_count: Number of events that will be fetched.
        markets: List of market keys to request per event.
        regions: Number of region parameters (default 1 = "us").

    Returns:
        Integer estimated credit cost.

    Examples:
        >>> estimate_credits(5, ["player_anytime_td", "player_rush_yds"])
        10
        >>> estimate_credits(0, ["player_anytime_td"])
        0
    """
    return event_count * len(markets) * regions


# ---------------------------------------------------------------------------
# Events list fetch (free endpoint)
# ---------------------------------------------------------------------------


def fetch_events(api_key: str) -> Tuple[List[dict], dict]:
    """Fetch the list of upcoming NFL events from The Odds API.

    This endpoint is free (0 credits).

    Args:
        api_key: The Odds API key.

    Returns:
        Tuple of (events list, response headers dict).

    Raises:
        requests.RequestException: On network or non-2xx HTTP response.
    """
    url = f"{API_BASE_URL}{EVENTS_ENDPOINT}"
    params = {"apiKey": api_key}

    logger.info("Fetching NFL events list (free endpoint)...")
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    events = response.json()
    logger.info("Received %d events from events endpoint.", len(events))
    return events, dict(response.headers)


def filter_events_by_window(
    events: List[dict],
    days_ahead: int,
    now: Optional[datetime] = None,
) -> List[dict]:
    """Filter events to those commencing within the next N days.

    Args:
        events: Raw event dicts from the API, each containing a
            ``commence_time`` ISO-8601 string.
        days_ahead: Maximum days ahead to include. Events commencing
            beyond this window are excluded to avoid burning credits
            on far-future games where props are not yet posted.
        now: Reference UTC datetime (defaults to utcnow). Injected for
            testing.

    Returns:
        Filtered list of event dicts sorted by commence_time ascending.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    cutoff = now + timedelta(days=days_ahead)

    filtered = []
    for event in events:
        raw_ts = event.get("commence_time", "")
        if not raw_ts:
            logger.warning("Event missing commence_time, skipping: %s", event.get("id"))
            continue
        try:
            event_dt = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
        except ValueError:
            logger.warning("Unparseable commence_time %r, skipping.", raw_ts)
            continue
        if now <= event_dt <= cutoff:
            filtered.append(event)

    filtered.sort(key=lambda e: e["commence_time"])
    logger.info(
        "Event window filter: %d of %d events within next %d days.",
        len(filtered),
        len(events),
        days_ahead,
    )
    return filtered


# ---------------------------------------------------------------------------
# Per-event props fetch
# ---------------------------------------------------------------------------


def fetch_event_props(
    api_key: str,
    event_id: str,
    markets: List[str],
    regions: str = "us",
) -> Tuple[dict, dict]:
    """Fetch player-prop odds for a single event.

    Args:
        api_key: The Odds API key.
        event_id: The Odds API event id string.
        markets: List of market keys to request.
        regions: Comma-separated region string (default "us").

    Returns:
        Tuple of (event dict with bookmakers, response headers dict).
        On non-2xx HTTP response, raises requests.RequestException.

    Raises:
        requests.RequestException: On network or non-2xx HTTP response.
    """
    url = f"{API_BASE_URL}/v4/sports/americanfootball_nfl/events/{event_id}/odds"
    params = {
        "apiKey": api_key,
        "regions": regions,
        "markets": ",".join(markets),
        "oddsFormat": "american",
    }

    logger.debug("Fetching props for event %s, markets=%s", event_id, markets)
    response = requests.get(url, params=params, timeout=30)
    response.raise_for_status()
    return response.json(), dict(response.headers)


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------


def normalize_event_props(
    event_data: dict,
    snapshot_ts: str,
) -> List[dict]:
    """Expand a single event's props response into per-player rows.

    Handles two outcome shapes from The Odds API:

    * **Over/under markets** (e.g. ``player_reception_yds``): paired
      ``Over``/``Under`` outcomes keyed by player description.  Yields one
      row per player with ``price_over`` and ``price_under`` populated and
      ``line`` set to the point value.

    * **Binary markets** (e.g. ``player_anytime_td``): ``name="Yes"``,
      ``description=<player>``, single ``price``.  Yields one row per
      player with ``price_over`` set to the single price and
      ``price_under=None``.

    Args:
        event_data: Single event dict from /events/{id}/odds response,
            with keys: id, commence_time, home_team, away_team, bookmakers.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        List of flat dicts, one per (bookmaker, market, player).
        Returns empty list when the event has no bookmaker data.
    """
    event_id = event_data.get("id", "")
    commence_time = event_data.get("commence_time", "")
    home_team_raw = event_data.get("home_team", "")
    away_team_raw = event_data.get("away_team", "")

    home_team_nfl = ODDS_API_TO_NFLVERSE.get(home_team_raw)
    away_team_nfl = ODDS_API_TO_NFLVERSE.get(away_team_raw)

    if home_team_nfl is None and home_team_raw:
        logger.warning("Unmapped home team: %s", home_team_raw)
    if away_team_nfl is None and away_team_raw:
        logger.warning("Unmapped away team: %s", away_team_raw)

    season: Optional[int] = None
    if commence_time:
        try:
            season = infer_nfl_season(commence_time)
        except ValueError as exc:
            logger.warning("Could not infer season for event %s: %s", event_id, exc)

    rows: List[dict] = []

    for bm in event_data.get("bookmakers", []):
        bookmaker = bm.get("key", "")
        for market_obj in bm.get("markets", []):
            market = market_obj.get("key", "")
            outcomes = market_obj.get("outcomes", [])

            if market in BINARY_MARKETS:
                rows.extend(
                    _normalize_binary_outcomes(
                        outcomes=outcomes,
                        event_id=event_id,
                        commence_time=commence_time,
                        home_team_raw=home_team_raw,
                        away_team_raw=away_team_raw,
                        home_team_nfl=home_team_nfl,
                        away_team_nfl=away_team_nfl,
                        bookmaker=bookmaker,
                        market=market,
                        snapshot_ts=snapshot_ts,
                        season=season,
                    )
                )
            else:
                rows.extend(
                    _normalize_over_under_outcomes(
                        outcomes=outcomes,
                        event_id=event_id,
                        commence_time=commence_time,
                        home_team_raw=home_team_raw,
                        away_team_raw=away_team_raw,
                        home_team_nfl=home_team_nfl,
                        away_team_nfl=away_team_nfl,
                        bookmaker=bookmaker,
                        market=market,
                        snapshot_ts=snapshot_ts,
                        season=season,
                    )
                )

    return rows


def _make_base_row(
    event_id: str,
    commence_time: str,
    home_team_raw: str,
    away_team_raw: str,
    home_team_nfl: Optional[str],
    away_team_nfl: Optional[str],
    bookmaker: str,
    market: str,
    snapshot_ts: str,
    season: Optional[int],
) -> Dict:
    """Build the common fields shared by every props row.

    Args:
        event_id: API event identifier.
        commence_time: ISO-8601 game start time string.
        home_team_raw: Home team full name as returned by the API.
        away_team_raw: Away team full name as returned by the API.
        home_team_nfl: nflverse home team abbreviation (may be None).
        away_team_nfl: nflverse away team abbreviation (may be None).
        bookmaker: Bookmaker key string.
        market: Market key string.
        snapshot_ts: UTC ISO-8601 snapshot timestamp.
        season: Inferred NFL season year (may be None).

    Returns:
        Dict with all common fields populated.
    """
    return {
        "snapshot_ts": snapshot_ts,
        "event_id": event_id,
        "commence_time": commence_time,
        "home_team": home_team_raw,
        "away_team": away_team_raw,
        "home_team_nfl": home_team_nfl,
        "away_team_nfl": away_team_nfl,
        "bookmaker": bookmaker,
        "market": market,
        "season": season,
    }


def _normalize_binary_outcomes(
    outcomes: List[dict],
    **base_kwargs,
) -> List[dict]:
    """Normalise binary (yes-only) prop outcomes.

    For markets like ``player_anytime_td`` where each outcome is
    ``{"name": "Yes", "description": "<player>", "price": <int>}``.

    Args:
        outcomes: List of outcome dicts from the market object.
        **base_kwargs: Common row fields forwarded to ``_make_base_row``.

    Returns:
        List of one row per outcome with ``price_over`` set and
        ``price_under=None``.
    """
    rows = []
    for outcome in outcomes:
        player_name = outcome.get("description") or outcome.get("name", "")
        if not player_name:
            logger.warning(
                "Outcome with empty player_name in market %s — row kept but "
                "downstream player joins will miss it: %s",
                base_kwargs.get("market", "?"),
                {k: outcome.get(k) for k in ("name", "description", "price")},
            )
        price = outcome.get("price")
        row = _make_base_row(**base_kwargs)
        row.update(
            {
                "player_name": player_name,
                "line": None,
                "price_over": price,
                "price_under": None,
            }
        )
        rows.append(row)
    return rows


def _normalize_over_under_outcomes(
    outcomes: List[dict],
    **base_kwargs,
) -> List[dict]:
    """Normalise over/under prop outcomes into paired player rows.

    For markets like ``player_reception_yds`` where outcomes come in
    ``Over``/``Under`` pairs keyed by player description:
        ``{"name": "Over", "description": "<player>", "point": 74.5, "price": -115}``

    If a player has only an Over or only an Under outcome (data gap),
    the missing side is left as None.

    Args:
        outcomes: List of outcome dicts from the market object.
        **base_kwargs: Common row fields forwarded to ``_make_base_row``.

    Returns:
        List of one row per player.
    """
    # Group outcomes by player description
    players: Dict[str, Dict[str, dict]] = {}
    for outcome in outcomes:
        player = outcome.get("description", "")
        side = outcome.get("name", "")  # "Over" or "Under"
        if not player:
            continue
        if player not in players:
            players[player] = {}
        players[player][side] = outcome

    rows = []
    for player_name, sides in players.items():
        over = sides.get("Over", {})
        under = sides.get("Under", {})
        line = over["point"] if over.get("point") is not None else under.get("point")
        row = _make_base_row(**base_kwargs)
        row.update(
            {
                "player_name": player_name,
                "line": line,
                "price_over": over.get("price"),
                "price_under": under.get("price"),
            }
        )
        rows.append(row)
    return rows


def normalize_props_response(
    event_data: dict,
    snapshot_ts: str,
) -> pd.DataFrame:
    """Normalise a single event's props API response into a tidy DataFrame.

    Args:
        event_data: Single event dict from /events/{id}/odds.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        DataFrame with columns matching PROPS_SCHEMA_COLS.
        Returns an empty DataFrame with correct columns when no rows are
        produced (event has no bookmakers or no matching markets).
    """
    rows = normalize_event_props(event_data, snapshot_ts)
    if not rows:
        return pd.DataFrame(columns=PROPS_SCHEMA_COLS)
    df = pd.DataFrame(rows, columns=PROPS_SCHEMA_COLS)

    unmapped_home = df.loc[df["home_team_nfl"].isna(), "home_team"].unique()
    unmapped_away = df.loc[df["away_team_nfl"].isna(), "away_team"].unique()
    if len(unmapped_home):
        logger.warning("Unmapped home teams: %s", list(unmapped_home))
    if len(unmapped_away):
        logger.warning("Unmapped away teams: %s", list(unmapped_away))

    return df


# ---------------------------------------------------------------------------
# Parquet output
# ---------------------------------------------------------------------------


def write_props_parquet(
    df: pd.DataFrame,
    season: int,
    dry_run: bool = False,
) -> str:
    """Write props snapshot DataFrame to Bronze Parquet.

    Args:
        df: Normalised props DataFrame.
        season: NFL season year (used for partition directory).
        dry_run: When True, skip all file I/O.

    Returns:
        Absolute output path (whether or not the file was written).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BRONZE_PROPS_DIR, f"season={season}")
    out_path = os.path.join(out_dir, f"props_{timestamp}.parquet")

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to %s", len(df), out_path)
        return out_path

    os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(df), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_props(
    api_key: str,
    markets: Optional[List[str]] = None,
    days_ahead: int = 7,
    max_credits: int = 100,
    dry_run: bool = False,
) -> int:
    """Fetch, normalise, and persist a single player-props snapshot.

    Fetches the free events list, filters to games within the next
    ``days_ahead`` days, estimates credit cost, aborts if over
    ``max_credits``, then fetches props per event while monitoring the
    remaining quota header.

    Args:
        api_key: The Odds API key.
        markets: Prop markets to fetch per event. Defaults to
            DEFAULT_MARKETS when None.
        days_ahead: Only fetch events commencing within this many days.
            Avoids wasting credits on far-future events without posted
            props.
        max_credits: Hard cap on credits to spend in this run. If the
            estimated cost exceeds this, the run aborts before any
            per-event calls.
        dry_run: When True, fetch events and estimate credits but do not
            make any per-event props API calls or write Parquet files.

    Returns:
        Exit code (0 = success or graceful skip, 1 = hard error).
    """
    if markets is None:
        markets = DEFAULT_MARKETS

    snapshot_ts = datetime.now(timezone.utc).isoformat()

    # ------------------------------------------------------------------
    # 1. Fetch events list (free endpoint)
    # ------------------------------------------------------------------
    try:
        all_events, events_headers = fetch_events(api_key)
    except requests.RequestException as exc:
        sanitized = str(exc).replace(api_key, "***") if api_key else str(exc)
        logger.warning(
            "Events fetch failed (fail-open): %s. No parquet written.", sanitized
        )
        return 0

    log_quota(events_headers)

    # ------------------------------------------------------------------
    # 2. Filter to events within the time window
    # ------------------------------------------------------------------
    events_in_window = filter_events_by_window(all_events, days_ahead=days_ahead)

    if not events_in_window:
        logger.info(
            "No events within %d-day window. Off-season or no games scheduled.",
            days_ahead,
        )
        return 0

    # ------------------------------------------------------------------
    # 3. Credit budget guard — abort before spending anything
    # ------------------------------------------------------------------
    estimated = estimate_credits(
        event_count=len(events_in_window),
        markets=markets,
        regions=1,
    )
    logger.info(
        "Credit estimate: %d events × %d markets = %d credits (limit: %d).",
        len(events_in_window),
        len(markets),
        estimated,
        max_credits,
    )
    if estimated > max_credits:
        logger.error(
            "Estimated cost %d credits exceeds --max-credits %d. "
            "Aborting to protect quota. "
            "Reduce --days-ahead, --markets, or raise --max-credits.",
            estimated,
            max_credits,
        )
        return 1

    if dry_run:
        logger.info(
            "[DRY RUN] Would fetch props for %d events (%d estimated credits). "
            "No API calls or parquet writes.",
            len(events_in_window),
            estimated,
        )
        return 0

    # ------------------------------------------------------------------
    # 4. Per-event props fetch
    # ------------------------------------------------------------------
    all_rows: List[dict] = []
    events_ok = 0
    events_skipped = 0

    for event in events_in_window:
        event_id = event.get("id", "")
        commence = event.get("commence_time", "")
        logger.info(
            "Fetching props for event %s (%s %s vs %s)...",
            event_id,
            commence[:10],
            event.get("home_team", "?"),
            event.get("away_team", "?"),
        )

        try:
            event_data, prop_headers = fetch_event_props(
                api_key=api_key,
                event_id=event_id,
                markets=markets,
            )
        except requests.RequestException as exc:
            sanitized = str(exc).replace(api_key, "***") if api_key else str(exc)
            logger.warning("Props fetch failed for event %s (skipping): %s", event_id, sanitized)
            events_skipped += 1
            continue

        log_quota(prop_headers)

        try:
            rows = normalize_event_props(event_data, snapshot_ts)
        except (ValueError, KeyError, TypeError) as exc:
            logger.warning(
                "Props normalisation failed for event %s (skipping): %s", event_id, exc
            )
            events_skipped += 1
        else:
            all_rows.extend(rows)
            events_ok += 1
            logger.debug("Event %s: %d prop rows.", event_id, len(rows))

        # ------------------------------------------------------------------
        # Mid-run credit reserve guard: stop before we drain the quota
        # shared by the spreads cron. Checked AFTER collecting the event we
        # just paid credits for (never discard purchased data) and runs even
        # when normalisation failed — a string of bad events at low quota
        # must not keep spending credits.
        # ------------------------------------------------------------------
        lower_headers = {k.lower(): v for k, v in prop_headers.items()}
        remaining_str = lower_headers.get("x-requests-remaining", "")
        if remaining_str.isdigit() and int(remaining_str) <= CREDIT_RESERVE_THRESHOLD:
            logger.warning(
                "x-requests-remaining=%s is at or below reserve threshold %d. "
                "Stopping mid-run to protect spreads cron quota. "
                "%d events fetched, %d remaining skipped.",
                remaining_str,
                CREDIT_RESERVE_THRESHOLD,
                events_ok,
                len(events_in_window) - events_ok - events_skipped,
            )
            break

    logger.info(
        "Props fetch complete: %d events ok, %d skipped, %d total rows.",
        events_ok,
        events_skipped,
        len(all_rows),
    )

    if not all_rows:
        logger.info("No props rows to write (no bookmakers posting props yet).")
        return 0

    # ------------------------------------------------------------------
    # 5. Write Parquet — one file per season (handles week-17/Jan boundary)
    # ------------------------------------------------------------------
    df_all = pd.DataFrame(all_rows, columns=PROPS_SCHEMA_COLS)

    seasons = df_all["season"].dropna().unique()
    if len(seasons) == 0:
        logger.warning("Could not infer season from any event; skipping write.")
        return 0

    for season in sorted(seasons):
        season_df = df_all[df_all["season"] == season].copy()
        if season_df.empty:
            continue
        write_props_parquet(season_df, int(season), dry_run=False)

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the Bronze Player Props ingestion script."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch NFL player-prop lines from The Odds API and write Bronze Parquet "
            "snapshots. Designed for weekly cron execution on Sunday ~14:00 UTC "
            "when prop menus are final. Exits 0 on any network error (fail-open)."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help=(
            "Fetch the events list and estimate credits, but do NOT make any "
            "per-event props API calls or write Parquet files."
        ),
    )
    parser.add_argument(
        "--markets",
        nargs="+",
        metavar="MARKET",
        default=None,
        help=(
            "Prop markets to fetch per event (space-separated). "
            f"Default: {' '.join(DEFAULT_MARKETS)}"
        ),
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=7,
        metavar="N",
        help=(
            "Only fetch events commencing within the next N days (default: 7). "
            "Prevents spending credits on far-future events with no props posted."
        ),
    )
    parser.add_argument(
        "--max-credits",
        type=int,
        default=100,
        metavar="N",
        help=(
            "Abort the run if the estimated credit cost exceeds N (default: 100). "
            "The run halts before any per-event call if the estimate is over budget."
        ),
    )

    args = parser.parse_args()

    api_key = os.environ.get("ODDS_API_KEY")
    if not api_key:
        if args.dry_run:
            logger.info(
                "[DRY RUN] No ODDS_API_KEY — cannot fetch events. "
                "Register at https://the-odds-api.com and add ODDS_API_KEY to .env."
            )
            sys.exit(0)
        else:
            logger.error(
                "ODDS_API_KEY not set. "
                "Register at https://the-odds-api.com and add ODDS_API_KEY to .env."
            )
            # Fail-open: exit 0 so cron does not page on a missing key.
            sys.exit(0)

    exit_code = run_props(
        api_key=api_key,
        markets=args.markets,
        days_ahead=args.days_ahead,
        max_credits=args.max_credits,
        dry_run=args.dry_run,
    )
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
