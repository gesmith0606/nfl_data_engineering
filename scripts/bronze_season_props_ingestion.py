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

Schema (one row per market = one player × one season stat; rookie
milestone ladders emit one row per threshold rung instead):
    snapshot_ts   — UTC ISO-8601 string when this snapshot was taken
    bookmaker     — "draftkings" or "fanduel"
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

#: Rookie "Milestones" markets (category 1801): one-sided ladders of
#: "750+ / 1000+ / ..." threshold prices instead of Over/Under pairs.
#: One output row per threshold: line=threshold, price_over=price,
#: price_under=None. Inversion to an implied mean lives in
#: ``src/season_prop_implied.py`` (distribution fit through the ladder).
#: Valuable despite tiny counts: these cover rookie-only names with no
#: NFL history — exactly where preseason projections are weakest.
ROOKIE_MILESTONE_MARKETS: Dict[str, Tuple[int, int]] = {
    "rookie_pass_yds": (1801, 17729),
    "rookie_pass_tds": (1801, 17730),
    "rookie_rec_yds": (1801, 17732),
    "rookie_rec_tds": (1801, 17733),
    "rookie_rush_yds": (1801, 17734),
    "rookie_rush_tds": (1801, 17735),
}

#: FanDuel's content-managed NFL page — one request returns every posted
#: "Regular Season <stat> YYYY-YY" player market (145 at first capture).
#: The ``_ak`` value is FanDuel's own public web-app key (embedded in
#: their site JS, shared by all anonymous visitors).
FANDUEL_NFL_URL = (
    "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
    "?page=CUSTOM&customPageId=nfl&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx"
    "&timezone=America%2FNew_York"
)

#: FanDuel market-name stat phrase -> canonical market key.
FANDUEL_STAT_TO_MARKET: Dict[str, str] = {
    "Passing Yards": "season_pass_yds",
    "Passing TDs": "season_pass_tds",
    "Rushing Yards": "season_rush_yds",
    "Rushing TDs": "season_rush_tds",
    "Receiving Yards": "season_rec_yds",
    "Receiving TDs": "season_rec_tds",
    "Receptions": "season_receptions",
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
_MILESTONE_LABEL_RE = re.compile(r"^([\d,]+)\+$")
_FANDUEL_MARKET_RE = re.compile(
    r"^(?P<player>.+?)\s+Regular Season\s+(?P<stat>Passing Yards|Passing TDs|"
    r"Rushing Yards|Rushing TDs|Receiving Yards|Receiving TDs|Receptions)"
    r"\s+(?P<season>\d{4})-\d{2}$"
)
_FANDUEL_RUNNER_RE = re.compile(r"\b(Over|Under)\s+([\d,]+(?:\.\d+)?)$")


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


def parse_milestone_threshold(label: str) -> Optional[float]:
    """Extract the threshold from a milestone label like ``"1000+"``.

    Args:
        label: Selection label string.

    Returns:
        The threshold as float, or None when the label is not a milestone.
    """
    match = _MILESTONE_LABEL_RE.match((label or "").strip())
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


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


def normalize_milestone_response(
    data: dict,
    market_key: str,
    snapshot_ts: str,
) -> List[dict]:
    """Normalise a rookie Milestones subcategory response into ladder rows.

    Each market is a ladder of one-sided "N+" selections. Emits one row per
    threshold with ``line`` = threshold and ``price_over`` = the single
    price (``price_under`` stays None) so the schema matches the O/U rows.

    Args:
        data: Parsed JSON response with ``events``/``markets``/``selections``.
        market_key: Canonical rookie market key (ROOKIE_MILESTONE_MARKETS).
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        List of flat dicts matching SEASON_PROPS_SCHEMA_COLS.
    """
    events = {e.get("id"): e for e in data.get("events", [])}
    markets = {m.get("id"): m for m in data.get("markets", [])}

    rows: List[dict] = []
    for sel in data.get("selections", []):
        threshold = parse_milestone_threshold(sel.get("label", ""))
        if threshold is None:
            continue
        market = markets.get(sel.get("marketId"), {})
        event = events.get(market.get("eventId"), {})
        season, player_name = parse_event_name(event.get("name", ""))
        if not player_name:
            logger.warning(
                "Unparseable event name %r for milestone market %s — skipping",
                event.get("name"),
                market.get("name"),
            )
            continue
        price = parse_american_odds((sel.get("displayOdds") or {}).get("american"))
        if price is None:
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
                "line": threshold,
                "price_over": price,
                "price_under": None,
                "season": season,
            }
        )
    return rows


def normalize_fanduel_response(
    data: dict,
    snapshot_ts: str,
) -> List[dict]:
    """Normalise FanDuel's NFL page payload into season-prop rows.

    Scans ``attachments.markets`` for two-runner "Regular Season <stat>
    YYYY-YY" player markets. Line parses from the runner name (``"Aaron
    Rodgers Over 3050.5"``); a missing side is left as None (the
    downstream de-vig skips one-sided quotes).

    Args:
        data: Parsed content-managed-page JSON.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        List of flat dicts matching SEASON_PROPS_SCHEMA_COLS with
        ``bookmaker="fanduel"``.
    """
    markets = (data.get("attachments") or {}).get("markets") or {}
    rows: List[dict] = []
    for market in markets.values():
        match = _FANDUEL_MARKET_RE.match(market.get("marketName", ""))
        if not match:
            continue
        market_key = FANDUEL_STAT_TO_MARKET[match.group("stat")]
        sides: Dict[str, dict] = {}
        line = None
        for runner in market.get("runners", []):
            rmatch = _FANDUEL_RUNNER_RE.search(runner.get("runnerName", ""))
            if not rmatch:
                continue
            sides[rmatch.group(1)] = runner
            if line is None:
                line = float(rmatch.group(2).replace(",", ""))
        if line is None:
            continue

        def _price(runner: Optional[dict]) -> Optional[int]:
            if not runner:
                return None
            odds = (
                (runner.get("winRunnerOdds") or {})
                .get("americanDisplayOdds", {})
                .get("americanOdds")
            )
            return int(odds) if odds is not None else None

        rows.append(
            {
                "snapshot_ts": snapshot_ts,
                "bookmaker": "fanduel",
                "market": market_key,
                "market_name": market.get("marketName", ""),
                "event_id": str(market.get("eventId", "")),
                "player_name": match.group("player").strip(),
                "team_nfl": None,  # FD futures events carry no team info
                "line": line,
                "price_over": _price(sides.get("Over")),
                "price_under": _price(sides.get("Under")),
                "season": int(match.group("season")),
            }
        )
    return rows


def fetch_fanduel() -> dict:
    """Fetch FanDuel's NFL content page payload.

    Returns:
        Parsed JSON dict.

    Raises:
        RuntimeError: On non-200 HTTP status.
        Exception: Propagates curl_cffi network errors.
    """
    from curl_cffi import requests as cffi_requests

    response = cffi_requests.get(FANDUEL_NFL_URL, impersonate="chrome110", timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for FanDuel NFL page")
    return response.json()


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
    skip_fanduel: bool = False,
) -> int:
    """Fetch, normalise, and persist a season-props snapshot.

    Fail-open by design (mirrors the weekly props cron): any per-market
    fetch error logs a warning and moves on; a run that collects zero rows
    exits 0 without writing.

    Args:
        markets: Canonical market keys to fetch (default: all markets in
            SEASON_MARKETS + ROOKIE_MILESTONE_MARKETS).
        dry_run: When True, fetch and report but do not write Parquet.
        skip_fanduel: When True, capture DraftKings only.

    Returns:
        Exit code (0 = success or graceful skip, 1 = bad arguments).
    """
    all_markets = {**SEASON_MARKETS, **ROOKIE_MILESTONE_MARKETS}
    if markets is None:
        markets = list(all_markets)
    unknown = [m for m in markets if m not in all_markets]
    if unknown:
        logger.error("Unknown market keys %s. Valid: %s", unknown, sorted(all_markets))
        return 1

    snapshot_ts = datetime.now(timezone.utc).isoformat()
    all_rows: List[dict] = []

    for idx, market_key in enumerate(markets):
        category_id, subcategory_id = all_markets[market_key]
        try:
            data = fetch_subcategory(category_id, subcategory_id)
        except Exception as exc:  # network/HTTP — fail-open per market
            logger.warning("Fetch failed for %s (skipping): %s", market_key, exc)
            continue
        if market_key in ROOKIE_MILESTONE_MARKETS:
            rows = normalize_milestone_response(data, market_key, snapshot_ts)
        else:
            rows = normalize_subcategory_response(data, market_key, snapshot_ts)
        logger.info("%s: %d rows", market_key, len(rows))
        all_rows.extend(rows)
        if idx < len(markets) - 1:
            time.sleep(REQUEST_DELAY_S)

    # ------------------------------------------------------------------
    # FanDuel (second book): one request covers every posted season
    # market. Cross-book coverage lets the implied computation take the
    # median across books instead of trusting DraftKings alone. Rows for
    # markets outside the requested set are filtered for CLI parity.
    # ------------------------------------------------------------------
    if not skip_fanduel:
        try:
            fd_rows = normalize_fanduel_response(fetch_fanduel(), snapshot_ts)
        except Exception as exc:  # network/HTTP — fail-open
            logger.warning("FanDuel fetch failed (skipping): %s", exc)
            fd_rows = []
        fd_rows = [r for r in fd_rows if r["market"] in markets]
        logger.info(
            "fanduel: %d season lines (%d players)",
            len(fd_rows),
            len({r["player_name"] for r in fd_rows}),
        )
        all_rows.extend(fd_rows)

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
            f"Default: {' '.join(list(SEASON_MARKETS) + list(ROOKIE_MILESTONE_MARKETS))}"
        ),
    )
    parser.add_argument(
        "--skip-fanduel",
        action="store_true",
        help="Capture DraftKings only (skip the FanDuel second-book fetch).",
    )
    args = parser.parse_args()
    sys.exit(
        run_season_props(
            markets=args.markets,
            dry_run=args.dry_run,
            skip_fanduel=args.skip_fanduel,
        )
    )


if __name__ == "__main__":
    main()
