#!/usr/bin/env python3
"""
Bronze Weekly Player Props Ingestion — DraftKings + FanDuel, no API key.

DIY redundancy for ``scripts/bronze_props_ingestion.py`` (The Odds API): pulls
the same six weekly player markets (pass yds, pass TDs, rush yds, rec yds,
receptions, anytime TD) directly from the DraftKings and FanDuel public JSON
APIs, mirroring the anti-bot pattern proven in
``scripts/bronze_season_props_ingestion.py`` (curl_cffi Chrome impersonation,
no key, works from GHA runner IPs). Purpose (``.planning/PROPS_DATA_PLAN.md``
Phase 2): (a) forward-capture redundancy if free Odds-API credits run dry
mid-season, (b) two extra books for cross-book medians.

DraftKings discovery is dynamic, not hardcoded: unlike the season-futures
script (whose category/subcategory ids are stable, always-on futures
markets), weekly per-game player prop categories do not exist in DK's league
catalog until the book posts them (confirmed empirically 2026-08-16, four
weeks before Week 1: DK had live Week 1 "Anytime TD Scorer" markets but zero
Passing/Rushing/Receiving Yards markets yet). ``discover_dk_weekly_category_ids``
walks whatever categories the league object currently reports and treats any
id NOT in the known season/futures/specials set as a per-game candidate, then
matches subcategory *names* (not ids) to the target markets. This self-heals
once DK posts the yardage markets — no id to guess or re-hardcode.

FanDuel discovery reuses the season script's NFL content-managed-page (game
catalog + eventIds), then fetches each game's ``/api/event-page`` for
per-market data, matching market names/types the same way the live "Total
Match Points" / "Anytime TD Scorer" blurb catalog already documents.

Output path (per .planning/PROPS_DATA_PLAN.md Phase 2, task item 2):
    data/bronze/odds_api/props/season=YYYY/week=WW/props_dk_YYYYMMDD_HHMMSS.parquet
    data/bronze/odds_api/props/season=YYYY/week=WW/props_fd_YYYYMMDD_HHMMSS.parquet

Deliberately a *separate* filename convention (``props_dk_*`` / ``props_fd_*``
under a ``week=WW`` subdirectory) from the Odds API's own
``props/season=YYYY/props_<timestamp>.parquet`` (season-level, no week dir):
``generate_projections.py --props-blend`` globs only
``props/season={season}/props_*.parquet`` (non-recursive) and reads a single
latest file — writing into that same flat directory under a numeric-first
filename would make DK/FD snapshots silently win or lose the "latest file"
selection based on filename sort order rather than actual data completeness.
Keeping this capture in its own ``week=WW`` subdirectory avoids that
collision; wiring it into the ``--props-blend`` multi-book read path is a
separate follow-up, not done here.

Columns exactly match ``scripts/bronze_props_ingestion.py::PROPS_SCHEMA_COLS``
(re-imported, not redefined) so ``src/prop_implied.py`` can consume either
source unmodified. Market keys reuse the Odds-API vocabulary
(``player_pass_yds`` etc.) for the same reason.

Usage:
    python scripts/bronze_weekly_props_ingestion.py
    python scripts/bronze_weekly_props_ingestion.py --dry-run
    python scripts/bronze_weekly_props_ingestion.py --days-ahead 10
    python scripts/bronze_weekly_props_ingestion.py --skip-fanduel
"""

import argparse
import logging
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.dirname(__file__))

from bronze_odds_api_ingestion import (  # noqa: E402
    ODDS_API_TO_NFLVERSE,
    infer_nfl_season,
)
from bronze_props_ingestion import PROPS_SCHEMA_COLS  # noqa: E402

logging.basicConfig(
    format="%(asctime)s %(levelname)s %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%dT%H:%M:%SZ",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DraftKings constants
# ---------------------------------------------------------------------------
DK_LEAGUE_URL = (
    "https://sportsbook-nash.draftkings.com/api/sportscontent/dkusoh/v1/leagues/88808"
)

#: Category ids confirmed (2026-08-16 live probe) to be season-long
#: futures/specials/team markets — NEVER per-game weekly player props.
#: Any category id the league object reports that is NOT in this set is a
#: per-game weekly candidate (see module docstring: dynamic, not hardcoded).
DK_NON_WEEKLY_CATEGORY_IDS = frozenset(
    {
        492,  # Game Lines (moneyline/spread/total, team-level)
        528,  # Game Props (team-level)
        529,  # Futures (championship/conference/division)
        530,  # Team Props (team win totals)
        786,  # Season Specials
        787,  # Awards
        820,  # Division Specials
        863,  # Team Specials
        994,  # Player Matchups (season H2H specials, not weekly O/U)
        1076,  # Playoffs
        1228,  # Milestones (season)
        1286,  # Wins
        1287,  # Scoring Specials
        1595,  # Stat Leaders (season)
        1627,  # Season High Totals
        1643,  # Next Player To Record (season)
        1759,  # Player Futures (season O/U — bronze_season_props_ingestion.py)
        1801,  # Rookie Watch (season milestones)
        1872,  # Fast Futures
    }
)

#: DK subcategory *name* -> canonical (Odds-API-style) market key. Matched by
#: name, not id, because the weekly category/subcategory ids don't exist in
#: DK's system yet (see module docstring).
DK_SUBCATEGORY_NAME_TO_MARKET: Dict[str, str] = {
    "Passing Yards": "player_pass_yds",
    "Passing TDs": "player_pass_tds",
    "Rushing Yards": "player_rush_yds",
    "Receiving Yards": "player_reception_yds",
    "Receptions": "player_receptions",
}

#: Anytime-TD is a binary (yes-only) market matched by market *name* — live
#: and verified against real Week 1 2026 DK data (category 1003, "TD Scorers").
DK_ANYTIME_TD_MARKET_NAME = "Anytime TD Scorer"
ANYTIME_TD_MARKET = "player_anytime_td"

_LABEL_LINE_RE = re.compile(r"^(?:Over|Under)\s+([\d,]+(?:\.\d+)?)$")

#: DK's team ``shortName`` metadata mostly matches nflverse abbreviations
#: directly, EXCEPT the Rams: DK reports "LAR", nflverse uses "LA" (verified
#: live 2026-08-16 — 22/78 real Week 1 rows silently failed week resolution
#: before this fixup was added). Extend if future live captures surface more.
DK_TEAM_ABBR_FIXUPS: Dict[str, str] = {"LAR": "LA"}

# ---------------------------------------------------------------------------
# FanDuel constants
# ---------------------------------------------------------------------------
#: Same content-managed NFL page as bronze_season_props_ingestion.py — one
#: request returns every posted NFL event (games + futures placeholders).
FANDUEL_NFL_URL = (
    "https://sbapi.nj.sportsbook.fanduel.com/api/content-managed-page"
    "?page=CUSTOM&customPageId=nfl&pbHorizontal=false&_ak=FhMFpcPWXMeyZxOx"
    "&timezone=America%2FNew_York"
)
FANDUEL_EVENT_PAGE_URL_TMPL = (
    "https://sbapi.nj.sportsbook.fanduel.com/api/event-page"
    "?eventId={event_id}&_ak=FhMFpcPWXMeyZxOx&timezone=America%2FNew_York"
)

#: FanDuel market-name stat suffix -> canonical market key (weekly per-game
#: naming; no "Regular Season ... YYYY-YY" suffix, unlike season futures).
FANDUEL_WEEKLY_STAT_TO_MARKET: Dict[str, str] = {
    "Passing Yards": "player_pass_yds",
    "Passing Touchdowns": "player_pass_tds",
    "Rushing Yards": "player_rush_yds",
    "Receiving Yards": "player_reception_yds",
    "Receptions": "player_receptions",
}
_FD_WEEKLY_MARKET_RE = re.compile(
    r"^(?P<player>.+?)\s+(?P<stat>Passing Yards|Passing Touchdowns|"
    r"Rushing Yards|Receiving Yards|Receptions)$"
)
#: Confirmed present in FanDuel's live market-blurb catalog for a real Week 1
#: 2026 event (2026-08-16 probe) — the market type exists even though no
#: event currently has it posted as a live tab this far from kickoff.
FANDUEL_ANYTIME_TD_MARKET_TYPE = "ANY_TIME_TOUCHDOWN_SCORER"

#: Non-game placeholder events on FanDuel's NFL page (futures/specials/draft)
#: to exclude from the weekly game-event discovery.
_FD_NON_GAME_EVENT_RE = re.compile(r"^NFL (Draft|Futures|Specials|Player Awards)$")
_FD_GAME_EVENT_RE = re.compile(r"^(?P<away>.+?)\s+@\s+(?P<home>.+)$")

REQUEST_DELAY_S = 1.0

BRONZE_WEEKLY_PROPS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "bronze",
    "odds_api",
    "props",
)

SCHEDULES_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "data",
    "bronze",
    "schedules",
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def parse_american_odds(display) -> Optional[int]:
    """Parse an American odds value (DK unicode-minus string, or plain int).

    Args:
        display: Odds as a DK display string (e.g. ``"−110"``, ``"+150"``)
            or an already-numeric value.

    Returns:
        Integer American odds, or None when missing/unparseable.
    """
    if display is None:
        return None
    if isinstance(display, (int, float)):
        return int(display)
    cleaned = str(display).replace("−", "-").replace("+", "").strip()
    try:
        return int(cleaned)
    except ValueError:
        return None


def parse_line_from_label(label: str) -> Optional[float]:
    """Extract a numeric line from a plain ``"Over 74.5"`` style label.

    Fallback only — DK's per-market O/U selections normally carry the line
    in a dedicated ``points`` field (see ``normalize_dk_category``).

    Args:
        label: Selection label string.

    Returns:
        The line as float, or None when unparseable.
    """
    match = _LABEL_LINE_RE.match((label or "").strip())
    if not match:
        return None
    return float(match.group(1).replace(",", ""))


def load_schedule_lookup(season: int) -> pd.DataFrame:
    """Load the local nflverse schedule for a season (team-pair -> week).

    Args:
        season: NFL season year.

    Returns:
        DataFrame with columns week/gameday/home_team/away_team, or an empty
        DataFrame if no local schedule Bronze file exists for this season
        (week resolution then fails open — rows are dropped with a warning,
        never mis-partitioned).
    """
    import glob as _glob

    files = sorted(
        _glob.glob(os.path.join(SCHEDULES_DIR, f"season={season}", "*.parquet"))
    )
    if not files:
        logger.warning(
            "No local schedule Bronze file for season %d — week resolution "
            "will fail open (rows dropped, not mis-partitioned).",
            season,
        )
        return pd.DataFrame(columns=["week", "gameday", "home_team", "away_team"])
    return pd.read_parquet(files[-1])[["week", "gameday", "home_team", "away_team"]]


def resolve_week(
    schedule_df: pd.DataFrame,
    home_nfl: Optional[str],
    away_nfl: Optional[str],
    commence_time: str,
) -> Optional[int]:
    """Resolve the NFL week for a game from the local schedule.

    Matches on the unordered team pair (home/away can differ between the
    sportsbook and nflverse labeling) and disambiguates divisional rematches
    (same two teams meet twice in a season) by nearest ``gameday``.

    Args:
        schedule_df: Output of :func:`load_schedule_lookup`.
        home_nfl: nflverse home team abbreviation (may be None).
        away_nfl: nflverse away team abbreviation (may be None).
        commence_time: ISO-8601 kickoff timestamp string.

    Returns:
        Week number, or None when unresolvable (missing team, no schedule
        match, or unparseable commence_time).
    """
    if not home_nfl or not away_nfl or schedule_df.empty:
        return None
    candidates = schedule_df[
        (
            (schedule_df["home_team"] == home_nfl)
            & (schedule_df["away_team"] == away_nfl)
        )
        | (
            (schedule_df["home_team"] == away_nfl)
            & (schedule_df["away_team"] == home_nfl)
        )
    ]
    if candidates.empty:
        return None
    if len(candidates) == 1:
        return int(candidates.iloc[0]["week"])
    try:
        commence_date = datetime.fromisoformat(
            commence_time.replace("Z", "+00:00")
        ).date()
    except ValueError:
        return int(candidates.iloc[0]["week"])
    diffs = candidates["gameday"].map(
        lambda d: abs((pd.Timestamp(d).date() - commence_date).days)
    )
    return int(candidates.loc[diffs.idxmin(), "week"])


# ---------------------------------------------------------------------------
# DraftKings — fetch
# ---------------------------------------------------------------------------


def fetch_dk_league() -> dict:
    """Fetch the DK NFL league document (events + currently-live categories).

    Returns:
        Parsed JSON dict.

    Raises:
        RuntimeError: On non-200 HTTP status.
    """
    from curl_cffi import requests as cffi_requests

    response = cffi_requests.get(DK_LEAGUE_URL, impersonate="chrome110", timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for {DK_LEAGUE_URL}")
    return response.json()


def fetch_dk_category(category_id: int) -> dict:
    """Fetch one DK category's markets/selections/events (league-wide).

    Args:
        category_id: DK category id.

    Returns:
        Parsed JSON dict.

    Raises:
        RuntimeError: On non-200 HTTP status.
    """
    from curl_cffi import requests as cffi_requests

    url = f"{DK_LEAGUE_URL}/categories/{category_id}"
    response = cffi_requests.get(url, impersonate="chrome110", timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for {url}")
    return response.json()


def discover_dk_weekly_category_ids(league_doc: dict) -> List[int]:
    """Return DK category ids that are plausible per-game weekly markets.

    Args:
        league_doc: Response of :func:`fetch_dk_league`.

    Returns:
        Category ids present in the league doc's ``categories`` list that
        are NOT in :data:`DK_NON_WEEKLY_CATEGORY_IDS`.
    """
    return [
        c["id"]
        for c in league_doc.get("categories", [])
        if c.get("id") not in DK_NON_WEEKLY_CATEGORY_IDS
    ]


# ---------------------------------------------------------------------------
# DraftKings — normalize
# ---------------------------------------------------------------------------


def _dk_event_team_info(
    event: dict,
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str]]:
    """Extract (home_team, away_team, home_nfl, away_nfl) from a DK event.

    Args:
        event: DK event dict with a ``participants`` list.

    Returns:
        4-tuple of team names/abbreviations; None entries when not found.
    """
    home_team = away_team = home_nfl = away_nfl = None
    for p in event.get("participants", []):
        role = p.get("venueRole")
        short = (p.get("metadata") or {}).get("shortName")
        short = DK_TEAM_ABBR_FIXUPS.get(short, short)
        if role == "Home":
            home_team, home_nfl = p.get("name"), short
        elif role == "Away":
            away_team, away_nfl = p.get("name"), short
    return home_team, away_team, home_nfl, away_nfl


def normalize_dk_category(
    data: dict,
    snapshot_ts: str,
) -> List[dict]:
    """Normalize one DK category response into weekly prop rows.

    Handles two market shapes:

    * **Binary** — market name == ``DK_ANYTIME_TD_MARKET_NAME``: one row per
      selection (``price_over`` = single price, ``price_under`` = None,
      ``line`` = None).
    * **Over/under** — market's subcategory name matches
      :data:`DK_SUBCATEGORY_NAME_TO_MARKET`: selections grouped by
      (marketId, participant) into Over/Under pairs; ``line`` prefers the
      selection's ``points`` field, falling back to label parsing.

    Any market whose name/subcategory doesn't match either shape is skipped
    (e.g. "First TD Scorer", "2+ TDs" living alongside "Anytime TD Scorer"
    in category 1003).

    Args:
        data: Parsed JSON from :func:`fetch_dk_category`.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        List of flat dicts matching ``PROPS_SCHEMA_COLS`` (plus a transient
        ``_season``/``_home_nfl``/``_away_nfl`` not part of the public
        schema — callers use :func:`build_dk_rows` instead of this function
        directly when they need final schema rows).
    """
    events = {e["id"]: e for e in data.get("events", [])}
    subcats = {s["id"]: s.get("name") for s in data.get("subcategories", [])}
    markets = {m["id"]: m for m in data.get("markets", [])}

    selections_by_market: Dict[str, List[dict]] = {}
    for sel in data.get("selections", []):
        selections_by_market.setdefault(sel.get("marketId", ""), []).append(sel)

    rows: List[dict] = []
    for market_id, market in markets.items():
        sels = selections_by_market.get(market_id, [])
        if not sels:
            continue
        event = events.get(market.get("eventId"), {})
        home_team, away_team, home_nfl, away_nfl = _dk_event_team_info(event)
        commence_time = event.get("startEventDate", "")
        base = {
            "snapshot_ts": snapshot_ts,
            "event_id": str(market.get("eventId", "")),
            "commence_time": commence_time,
            "home_team": home_team,
            "away_team": away_team,
            "home_team_nfl": home_nfl,
            "away_team_nfl": away_nfl,
            "bookmaker": "draftkings",
        }

        if market.get("name") == DK_ANYTIME_TD_MARKET_NAME:
            for sel in sels:
                participants = sel.get("participants") or []
                player_name = participants[0].get("name") if participants else None
                if not player_name:
                    continue
                rows.append(
                    {
                        **base,
                        "market": ANYTIME_TD_MARKET,
                        "player_name": player_name,
                        "line": None,
                        "price_over": parse_american_odds(
                            (sel.get("displayOdds") or {}).get("american")
                        ),
                        "price_under": None,
                    }
                )
            continue

        subcat_name = subcats.get(market.get("subcategoryId"))
        market_key = DK_SUBCATEGORY_NAME_TO_MARKET.get(subcat_name)
        if market_key is None:
            continue

        by_player: Dict[str, Dict[str, dict]] = {}
        for sel in sels:
            outcome = sel.get("outcomeType")
            if outcome not in ("Over", "Under"):
                continue
            participants = sel.get("participants") or []
            player_name = participants[0].get("name") if participants else None
            if not player_name:
                continue
            by_player.setdefault(player_name, {})[outcome] = sel

        for player_name, sides in by_player.items():
            over = sides.get("Over", {})
            under = sides.get("Under", {})
            line = over.get("points")
            if line is None:
                line = under.get("points")
            if line is None:
                line = parse_line_from_label(
                    over.get("label", "")
                ) or parse_line_from_label(under.get("label", ""))
            rows.append(
                {
                    **base,
                    "market": market_key,
                    "player_name": player_name,
                    "line": line,
                    "price_over": parse_american_odds(
                        (over.get("displayOdds") or {}).get("american")
                    ),
                    "price_under": parse_american_odds(
                        (under.get("displayOdds") or {}).get("american")
                    ),
                }
            )
    return rows


# ---------------------------------------------------------------------------
# FanDuel — fetch
# ---------------------------------------------------------------------------


def fetch_fanduel_nfl_page() -> dict:
    """Fetch FanDuel's NFL content page (game catalog + eventIds).

    Returns:
        Parsed JSON dict.

    Raises:
        RuntimeError: On non-200 HTTP status.
    """
    from curl_cffi import requests as cffi_requests

    response = cffi_requests.get(FANDUEL_NFL_URL, impersonate="chrome110", timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for FanDuel NFL page")
    return response.json()


def fetch_fanduel_event_page(event_id) -> dict:
    """Fetch FanDuel's per-event market page.

    Args:
        event_id: FanDuel event id.

    Returns:
        Parsed JSON dict.

    Raises:
        RuntimeError: On non-200 HTTP status.
    """
    from curl_cffi import requests as cffi_requests

    url = FANDUEL_EVENT_PAGE_URL_TMPL.format(event_id=event_id)
    response = cffi_requests.get(url, impersonate="chrome110", timeout=30)
    if response.status_code != 200:
        raise RuntimeError(f"HTTP {response.status_code} for {url}")
    return response.json()


def discover_fanduel_game_events(
    nfl_page_data: dict,
    days_ahead: int,
    now: Optional[datetime] = None,
) -> List[dict]:
    """Filter FanDuel's NFL page events to real games within the window.

    Excludes futures/specials/draft placeholder entries and events outside
    the ``[now, now + days_ahead]`` window.

    Args:
        nfl_page_data: Response of :func:`fetch_fanduel_nfl_page`.
        days_ahead: Only include events commencing within this many days.
        now: Reference UTC datetime (defaults to utcnow; injected for tests).

    Returns:
        List of dicts: ``{event_id, name, open_date, home_nfl, away_nfl}``.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    events = (nfl_page_data.get("attachments") or {}).get("events") or {}
    out: List[dict] = []
    for event_id, event in events.items():
        name = event.get("name", "")
        if _FD_NON_GAME_EVENT_RE.match(name):
            continue
        match = _FD_GAME_EVENT_RE.match(name)
        if not match:
            continue
        open_date = event.get("openDate", "")
        try:
            event_dt = datetime.fromisoformat(open_date.replace("Z", "+00:00"))
        except ValueError:
            continue
        if not (now <= event_dt <= cutoff):
            continue
        out.append(
            {
                "event_id": event_id,
                "away_team": match.group("away").strip(),
                "home_team": match.group("home").strip(),
                "away_nfl": ODDS_API_TO_NFLVERSE.get(match.group("away").strip()),
                "home_nfl": ODDS_API_TO_NFLVERSE.get(match.group("home").strip()),
                "commence_time": open_date,
            }
        )
    out.sort(key=lambda e: e["commence_time"])
    return out


# ---------------------------------------------------------------------------
# FanDuel — normalize
# ---------------------------------------------------------------------------


def _fd_price(runner: dict) -> Optional[int]:
    """Extract American odds from a FanDuel runner dict."""
    odds = (
        (runner.get("winRunnerOdds") or {})
        .get("americanDisplayOdds", {})
        .get("americanOdds")
    )
    return int(odds) if odds is not None else None


def normalize_fanduel_event_markets(
    event_page_data: dict,
    game: dict,
    snapshot_ts: str,
) -> List[dict]:
    """Normalize one FanDuel event-page response into weekly prop rows.

    Handles two market shapes, mirroring :func:`normalize_dk_category`:

    * **Binary** — ``marketType == FANDUEL_ANYTIME_TD_MARKET_TYPE``: one row
      per runner (player), ``price_over`` = the runner's price,
      ``price_under`` = None, ``line`` = None.
    * **Over/under** — ``marketName`` matches ``"<player> <stat>"`` via
      :data:`_FD_WEEKLY_MARKET_RE`: runners are ``"Over"``/``"Under"`` with
      the line on ``handicap``.

    Args:
        event_page_data: Response of :func:`fetch_fanduel_event_page`.
        game: One entry from :func:`discover_fanduel_game_events`.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        List of flat dicts matching ``PROPS_SCHEMA_COLS``.
    """
    markets = (event_page_data.get("attachments") or {}).get("markets") or {}
    base = {
        "snapshot_ts": snapshot_ts,
        "event_id": str(game["event_id"]),
        "commence_time": game["commence_time"],
        "home_team": game["home_team"],
        "away_team": game["away_team"],
        "home_team_nfl": game["home_nfl"],
        "away_team_nfl": game["away_nfl"],
        "bookmaker": "fanduel",
    }

    rows: List[dict] = []
    for market in markets.values():
        market_type = market.get("marketType", "")
        market_name = market.get("marketName", "")

        if market_type == FANDUEL_ANYTIME_TD_MARKET_TYPE:
            for runner in market.get("runners", []):
                player_name = runner.get("runnerName")
                if not player_name:
                    continue
                rows.append(
                    {
                        **base,
                        "market": ANYTIME_TD_MARKET,
                        "player_name": player_name,
                        "line": None,
                        "price_over": _fd_price(runner),
                        "price_under": None,
                    }
                )
            continue

        match = _FD_WEEKLY_MARKET_RE.match(market_name)
        if not match:
            continue
        market_key = FANDUEL_WEEKLY_STAT_TO_MARKET[match.group("stat")]
        sides: Dict[str, dict] = {}
        line = None
        for runner in market.get("runners", []):
            name = runner.get("runnerName")
            if name in ("Over", "Under"):
                sides[name] = runner
                if line is None:
                    line = runner.get("handicap")
        if not sides:
            continue
        rows.append(
            {
                **base,
                "market": market_key,
                "player_name": match.group("player").strip(),
                "line": line,
                "price_over": _fd_price(sides.get("Over", {})),
                "price_under": _fd_price(sides.get("Under", {})),
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Row -> schema finishing (season/week resolution, filtering)
# ---------------------------------------------------------------------------


def finish_rows(
    rows: List[dict],
    days_ahead: int,
    now: Optional[datetime] = None,
) -> pd.DataFrame:
    """Filter rows to the capture window and attach season/week.

    Args:
        rows: Flat dicts with all ``PROPS_SCHEMA_COLS`` fields except
            ``season`` (added here from ``commence_time``).
        days_ahead: Only keep rows whose event commences within this many
            days of ``now``.
        now: Reference UTC datetime (defaults to utcnow; injected for tests).

    Returns:
        DataFrame with an extra transient ``week`` column (dropped by
        callers before write — ``PROPS_SCHEMA_COLS`` has no week column,
        it's a partition directory only) and column order matching
        ``PROPS_SCHEMA_COLS``. Empty (correctly-columned) frame on no input.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    cutoff = now + timedelta(days=days_ahead)

    kept: List[dict] = []
    for row in rows:
        commence = row.get("commence_time", "")
        try:
            event_dt = datetime.fromisoformat(commence.replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            continue
        if not (now <= event_dt <= cutoff):
            continue
        try:
            season = infer_nfl_season(commence)
        except ValueError:
            continue
        row = dict(row)
        row["season"] = season
        kept.append(row)

    if not kept:
        return pd.DataFrame(columns=PROPS_SCHEMA_COLS + ["week"])

    df = pd.DataFrame(kept)
    schedule_cache: Dict[int, pd.DataFrame] = {}
    weeks = []
    for _, r in df.iterrows():
        season = int(r["season"])
        if season not in schedule_cache:
            schedule_cache[season] = load_schedule_lookup(season)
        weeks.append(
            resolve_week(
                schedule_cache[season],
                r["home_team_nfl"],
                r["away_team_nfl"],
                r["commence_time"],
            )
        )
    df["week"] = weeks
    unresolved = df["week"].isna().sum()
    if unresolved:
        logger.warning(
            "%d/%d rows dropped — could not resolve NFL week from local "
            "schedule (no schedule file, or unmapped team abbreviation).",
            unresolved,
            len(df),
        )
    df = df.dropna(subset=["week"])
    if df.empty:
        return pd.DataFrame(columns=PROPS_SCHEMA_COLS + ["week"])
    df["week"] = df["week"].astype(int)
    return df[PROPS_SCHEMA_COLS + ["week"]]


# ---------------------------------------------------------------------------
# Write
# ---------------------------------------------------------------------------


def write_weekly_props_parquet(
    df: pd.DataFrame,
    season: int,
    week: int,
    book_tag: str,
    dry_run: bool = False,
) -> str:
    """Write one (season, week, book) weekly-props DataFrame to Bronze Parquet.

    Args:
        df: Rows for exactly this (season, week), in ``PROPS_SCHEMA_COLS``
            order (the transient ``week`` column already dropped).
        season: NFL season year.
        week: NFL week number.
        book_tag: Short book tag for the filename (``"dk"`` or ``"fd"``) —
            deliberately does NOT start with a digit so it can never collide
            with the Odds API's own numeric-timestamp ``props_<ts>.parquet``
            sort order (see module docstring), and does not match the
            gitignored ``props_archive_*`` pattern.
        dry_run: When True, skip all file I/O.

    Returns:
        Absolute output path (whether or not the file was written).
    """
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    out_dir = os.path.join(BRONZE_WEEKLY_PROPS_DIR, f"season={season}", f"week={week}")
    out_path = os.path.join(out_dir, f"props_{book_tag}_{timestamp}.parquet")

    if dry_run:
        logger.info("[DRY RUN] Would write %d rows to %s", len(df), out_path)
        return out_path

    os.makedirs(out_dir, exist_ok=True)
    df.to_parquet(out_path, index=False)
    logger.info("Wrote %d rows to %s", len(df), out_path)
    return out_path


def write_all(df: pd.DataFrame, book_tag: str, dry_run: bool = False) -> List[str]:
    """Split a finished frame by (season, week) and write one file each.

    Args:
        df: Output of :func:`finish_rows` (has the transient ``week`` col).
        book_tag: ``"dk"`` or ``"fd"``.
        dry_run: Forwarded to :func:`write_weekly_props_parquet`.

    Returns:
        List of output paths written (or that would be written, dry-run).
    """
    if df.empty:
        return []
    paths = []
    for (season, week), group in df.groupby(["season", "week"]):
        paths.append(
            write_weekly_props_parquet(
                group.drop(columns=["week"]),
                int(season),
                int(week),
                book_tag,
                dry_run=dry_run,
            )
        )
    return paths


# ---------------------------------------------------------------------------
# Per-book runners (fail-open)
# ---------------------------------------------------------------------------


def run_draftkings(days_ahead: int, snapshot_ts: str) -> List[dict]:
    """Fetch + normalize DK weekly props across all discovered categories.

    Fail-open: any single category fetch/normalize error is logged and
    skipped so one bad category can't blank the whole DK capture.

    Args:
        days_ahead: Window for event discovery (informational here — the
            actual window filter happens in :func:`finish_rows`; DK ignores
            the ``eventIds`` query param, so all currently-posted markets
            are fetched regardless and filtered post-hoc).
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        Flat row dicts (pre :func:`finish_rows`). Empty list on total
        failure (network down) or when nothing is posted yet.
    """
    try:
        league_doc = fetch_dk_league()
    except Exception as exc:  # network/HTTP — fail-open
        logger.warning("DraftKings league fetch failed (skipping DK): %s", exc)
        return []

    category_ids = discover_dk_weekly_category_ids(league_doc)
    logger.info(
        "DraftKings: %d candidate weekly categories to check.", len(category_ids)
    )

    rows: List[dict] = []
    for idx, category_id in enumerate(category_ids):
        try:
            data = fetch_dk_category(category_id)
        except Exception as exc:  # network/HTTP — fail-open per category
            logger.warning(
                "DraftKings category %s fetch failed (skipping): %s", category_id, exc
            )
            continue
        try:
            cat_rows = normalize_dk_category(data, snapshot_ts)
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "DraftKings category %s normalize failed (skipping): %s",
                category_id,
                exc,
            )
            continue
        if cat_rows:
            logger.info(
                "DraftKings category %s: %d rows across markets %s",
                category_id,
                len(cat_rows),
                sorted({r["market"] for r in cat_rows}),
            )
        rows.extend(cat_rows)
        if idx < len(category_ids) - 1:
            time.sleep(REQUEST_DELAY_S)
    return rows


def run_fanduel(days_ahead: int, snapshot_ts: str) -> List[dict]:
    """Fetch + normalize FanDuel weekly props for in-window games.

    Fail-open: any single event fetch/normalize error is logged and skipped.

    Args:
        days_ahead: Only fetch games commencing within this many days.
        snapshot_ts: UTC ISO-8601 snapshot timestamp string.

    Returns:
        Flat row dicts (pre :func:`finish_rows`). Empty list on total
        failure or when no games are posted in-window.
    """
    try:
        nfl_page_data = fetch_fanduel_nfl_page()
    except Exception as exc:  # network/HTTP — fail-open
        logger.warning("FanDuel NFL page fetch failed (skipping FanDuel): %s", exc)
        return []

    games = discover_fanduel_game_events(nfl_page_data, days_ahead=days_ahead)
    logger.info("FanDuel: %d games in the %d-day window.", len(games), days_ahead)

    rows: List[dict] = []
    for idx, game in enumerate(games):
        try:
            event_page_data = fetch_fanduel_event_page(game["event_id"])
        except Exception as exc:  # network/HTTP — fail-open per event
            logger.warning(
                "FanDuel event %s fetch failed (skipping): %s", game["event_id"], exc
            )
            continue
        try:
            event_rows = normalize_fanduel_event_markets(
                event_page_data, game, snapshot_ts
            )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "FanDuel event %s normalize failed (skipping): %s",
                game["event_id"],
                exc,
            )
            continue
        if event_rows:
            logger.info(
                "FanDuel event %s (%s @ %s): %d rows across markets %s",
                game["event_id"],
                game["away_team"],
                game["home_team"],
                len(event_rows),
                sorted({r["market"] for r in event_rows}),
            )
        rows.extend(event_rows)
        if idx < len(games) - 1:
            time.sleep(REQUEST_DELAY_S)
    return rows


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def run_weekly_props(
    days_ahead: int = 8,
    dry_run: bool = False,
    skip_draftkings: bool = False,
    skip_fanduel: bool = False,
) -> int:
    """Fetch, normalize, and persist a weekly player-props snapshot.

    Fail-open per book (one book blocked/erroring does not fail the run) and
    honest on the overall exit code: exits 1 only when BOTH books combined
    produced zero rows across the whole run, so a silently-dead capture
    (e.g. both anti-bot fingerprints started failing) surfaces in CI/cron
    logs instead of looking like a quiet off-week.

    Args:
        days_ahead: Only capture games commencing within this many days.
        dry_run: When True, fetch/normalize but do not write Parquet.
        skip_draftkings: When True, skip the DraftKings capture.
        skip_fanduel: When True, skip the FanDuel capture.

    Returns:
        Exit code (0 = at least one row captured; 1 = zero rows overall).
    """
    snapshot_ts = datetime.now(timezone.utc).isoformat()
    per_book_counts: Dict[str, int] = {}
    total_paths: List[str] = []

    if not skip_draftkings:
        dk_rows = run_draftkings(days_ahead, snapshot_ts)
        dk_df = finish_rows(dk_rows, days_ahead=days_ahead)
        per_book_counts["draftkings"] = len(dk_df)
        total_paths.extend(write_all(dk_df, "dk", dry_run=dry_run))
    else:
        per_book_counts["draftkings"] = 0

    if not skip_fanduel:
        fd_rows = run_fanduel(days_ahead, snapshot_ts)
        fd_df = finish_rows(fd_rows, days_ahead=days_ahead)
        per_book_counts["fanduel"] = len(fd_df)
        total_paths.extend(write_all(fd_df, "fd", dry_run=dry_run))
    else:
        per_book_counts["fanduel"] = 0

    total_rows = sum(per_book_counts.values())
    logger.info(
        "Weekly props capture complete: %s (total %d rows, %d files%s)",
        ", ".join(f"{book}={n}" for book, n in per_book_counts.items()),
        total_rows,
        len(total_paths),
        " — DRY RUN" if dry_run else "",
    )

    if total_rows == 0:
        logger.error(
            "Zero rows captured across all books — either both books are "
            "blocking this run's fingerprint, or no weekly markets are "
            "posted yet for any in-window game. Exiting 1 (honest failure, "
            "not a silent no-op)."
        )
        return 1
    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point for the Bronze weekly player props ingestion script."""
    parser = argparse.ArgumentParser(
        description=(
            "Fetch NFL weekly player-prop lines directly from DraftKings and "
            "FanDuel (no API key) and write Bronze Parquet snapshots. "
            "Fail-open per book; exits 1 only if BOTH books return zero rows."
        )
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and normalise but do not write Parquet files.",
    )
    parser.add_argument(
        "--days-ahead",
        type=int,
        default=8,
        metavar="N",
        help="Only capture games commencing within the next N days (default: 8).",
    )
    parser.add_argument(
        "--skip-draftkings",
        action="store_true",
        help="Capture FanDuel only.",
    )
    parser.add_argument(
        "--skip-fanduel",
        action="store_true",
        help="Capture DraftKings only.",
    )
    args = parser.parse_args()
    sys.exit(
        run_weekly_props(
            days_ahead=args.days_ahead,
            dry_run=args.dry_run,
            skip_draftkings=args.skip_draftkings,
            skip_fanduel=args.skip_fanduel,
        )
    )


if __name__ == "__main__":
    main()
