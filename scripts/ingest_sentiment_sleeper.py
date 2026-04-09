#!/usr/bin/env python3
"""
Sleeper Sentiment Ingestion — Bronze Layer

Fetches player news from the Sleeper public API (no key required) and writes
the raw items as JSON to data/bronze/sentiment/sleeper/.

Two Sleeper endpoints are used:
  1. /v1/players/nfl/trending/add — top trending players (last 24 hours).
  2. /v1/players/nfl              — full player registry with metadata.

The Sleeper API returns its own ``player_id`` (a numeric string, e.g. "4046").
This script maps those IDs to nfl-data-py gsis_id format using
PlayerNameResolver (name + team + position hint).

Storage format:
  data/bronze/sentiment/sleeper/season=YYYY/sleeper_news_{YYYYMMDD_HHMMSS}.json

Each output file is a JSON envelope:
  {
    "fetch_run_id": "<uuid>",
    "source": "sleeper",
    "fetched_at": "2026-04-07T10:00:00Z",
    "season": 2026,
    "week": null,
    "item_count": 25,
    "items": [ ... ]
  }

Each item includes:
  - sleeper_player_id  (original Sleeper numeric ID)
  - resolved_player_id (nfl-data-py gsis_id, or null)
  - player_name, team, position, news_body, news_date

Usage
-----
  # Dry-run preview
  python scripts/ingest_sentiment_sleeper.py --dry-run

  # Full ingest for current season
  python scripts/ingest_sentiment_sleeper.py --season 2026

  # Fetch more trending players than the default 25
  python scripts/ingest_sentiment_sleeper.py --count 50
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import SENTIMENT_CONFIG, SENTIMENT_LOCAL_DIRS
from src.player_name_resolver import PlayerNameResolver

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_sentiment_sleeper")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_REQUEST_TIMEOUT_S = 15
_USER_AGENT = "NFLDataEngineering/1.0 (sentiment-pipeline)"


# ---------------------------------------------------------------------------
# Sleeper API helpers
# ---------------------------------------------------------------------------


def _http_get_json(url: str) -> Any:
    """Perform a GET request and return the parsed JSON response.

    Args:
        url: Full URL to request.

    Returns:
        Parsed JSON value (dict, list, etc.).

    Raises:
        RuntimeError: If the HTTP request fails or the response is not valid JSON.
    """
    req = Request(url, headers={"User-Agent": _USER_AGENT})
    try:
        with urlopen(req, timeout=_REQUEST_TIMEOUT_S) as resp:
            raw = resp.read()
    except HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.code} fetching {url}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error fetching {url}: {exc.reason}") from exc

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from {url}: {exc}") from exc


def _fetch_trending(count: int) -> List[Dict[str, Any]]:
    """Fetch the list of trending player dicts from Sleeper.

    Sleeper's trending endpoint returns objects of the form:
      {"player_id": "4046", "count": 312}

    Args:
        count: Number of trending players to fetch.

    Returns:
        List of raw Sleeper trending-player dicts.
    """
    url = f"{SENTIMENT_CONFIG['sleeper_trending_url']}?lookback_hours=24&limit={count}"
    logger.info("Fetching %d trending players from %s", count, url)
    try:
        data = _http_get_json(url)
    except RuntimeError as exc:
        logger.error("Could not fetch trending players: %s", exc)
        return []

    if not isinstance(data, list):
        logger.error("Unexpected trending response type: %s", type(data))
        return []

    logger.info("Received %d trending player records", len(data))
    return data


def _fetch_player_registry() -> Dict[str, Dict[str, Any]]:
    """Fetch the full Sleeper player registry (player_id → metadata).

    The registry is large (~5 MB JSON). It is fetched once per run and kept
    in memory to enrich trending player records with name/team/position.

    Returns:
        Dict mapping Sleeper player_id string → player metadata dict.
        Returns an empty dict if the fetch fails.
    """
    url = SENTIMENT_CONFIG["sleeper_players_url"]
    logger.info("Fetching Sleeper player registry from %s", url)
    try:
        data = _http_get_json(url)
    except RuntimeError as exc:
        logger.error("Could not fetch player registry: %s", exc)
        return {}

    if not isinstance(data, dict):
        logger.error("Unexpected registry response type: %s", type(data))
        return {}

    logger.info("Registry loaded: %d players", len(data))
    return data


def _enrich_trending(
    trending: List[Dict[str, Any]],
    registry: Dict[str, Dict[str, Any]],
    resolver: PlayerNameResolver,
    skill_positions: set,
) -> List[Dict[str, Any]]:
    """Merge trending records with registry metadata and resolve player IDs.

    Args:
        trending: Raw trending dicts from the Sleeper API.
        registry: Full player registry from _fetch_player_registry.
        resolver: Initialised PlayerNameResolver.
        skill_positions: Set of position strings to keep (e.g. {"QB", "RB"}).

    Returns:
        List of enriched item dicts ready for Bronze storage.
    """
    items: List[Dict[str, Any]] = []

    for record in trending:
        sleeper_id = str(record.get("player_id", ""))
        if not sleeper_id:
            continue

        meta = registry.get(sleeper_id, {})

        # Build candidate fields from registry metadata
        first = meta.get("first_name", "")
        last = meta.get("last_name", "")
        full_name = f"{first} {last}".strip()
        team = (meta.get("team") or "").upper()
        position = (meta.get("position") or "").upper()
        news_body = meta.get("news", "") or ""
        news_date = meta.get("news_updated") or ""

        # Filter to skill positions only
        if position and skill_positions and position not in skill_positions:
            logger.debug("Skipping non-skill position: %s (%s)", full_name, position)
            continue

        if not full_name.strip():
            logger.debug("Skipping Sleeper player %s — no name in registry", sleeper_id)
            continue

        # Resolve to nfl-data-py player_id via name + team + position hints
        resolved_id = resolver.resolve(full_name, team=team or None, position=position or None)
        if resolved_id:
            logger.debug(
                "Resolved Sleeper %s '%s' → %s", sleeper_id, full_name, resolved_id
            )
        else:
            logger.debug(
                "Could not resolve Sleeper %s '%s' (team=%s pos=%s)",
                sleeper_id,
                full_name,
                team,
                position,
            )

        # Convert news_date from Sleeper's epoch-ms to ISO 8601
        published_at: Optional[str] = None
        if news_date:
            try:
                epoch_s = int(news_date) / 1000
                published_at = datetime.fromtimestamp(epoch_s, tz=timezone.utc).isoformat()
            except (ValueError, TypeError):
                published_at = None

        item: Dict[str, Any] = {
            "sleeper_player_id": sleeper_id,
            "resolved_player_id": resolved_id,
            "player_name": full_name,
            "team": team or None,
            "position": position or None,
            "news_body": news_body,
            "news_date": published_at,
            "trending_count": record.get("count", 0),
            "source": "sleeper",
        }
        items.append(item)

    return items


def _save_items(
    items: List[Dict[str, Any]],
    season: int,
    output_dir: Path,
    run_id: str,
) -> Path:
    """Write the Bronze JSON envelope to disk.

    Args:
        items: Enriched item dicts from _enrich_trending.
        season: NFL season year.
        output_dir: Base directory for sentiment Sleeper output.
        run_id: UUID string for this ingestion run.

    Returns:
        Path to the written file.
    """
    season_dir = output_dir / f"season={season}"
    season_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"sleeper_news_{timestamp}.json"
    out_path = season_dir / filename

    envelope: Dict[str, Any] = {
        "fetch_run_id": run_id,
        "source": "sleeper",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "week": None,
        "item_count": len(items),
        "items": items,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, ensure_ascii=False)

    logger.info("Saved %d items → %s", len(items), out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest NFL player news from the Sleeper API into the Bronze sentiment layer.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--season",
        type=int,
        default=None,
        help="NFL season year (default: auto-detected from calendar).",
    )
    parser.add_argument(
        "--count",
        type=int,
        default=None,
        help=(
            "Number of trending players to fetch "
            f"(default: {SENTIMENT_CONFIG['sleeper_trending_count']})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse data but do not write any files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def _current_nfl_season() -> int:
    """Return the current NFL season year (season starts in September)."""
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the Sleeper sentiment ingestion script.

    Args:
        argv: Argument list (uses sys.argv if None).

    Returns:
        Exit code (0 = success, 1 = error).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    season = args.season or _current_nfl_season()
    count = args.count or SENTIMENT_CONFIG["sleeper_trending_count"]
    output_dir = _PROJECT_ROOT / SENTIMENT_LOCAL_DIRS["sleeper"]
    run_id = str(uuid.uuid4())
    skill_positions = SENTIMENT_CONFIG.get("skill_positions", set())

    logger.info(
        "Sleeper ingestion run=%s | season=%d | count=%d | dry_run=%s",
        run_id[:8],
        season,
        count,
        args.dry_run,
    )

    # Build player resolver
    logger.info("Building player name resolver…")
    resolver = PlayerNameResolver(bronze_root=_PROJECT_ROOT / "data/bronze")

    # Fetch trending players
    trending = _fetch_trending(count)
    if not trending:
        logger.warning("No trending players returned from Sleeper. Exiting.")
        return 0

    # Fetch registry (needed to get names/teams from Sleeper IDs)
    registry = _fetch_player_registry()

    # Enrich and resolve
    items = _enrich_trending(trending, registry, resolver, skill_positions)

    resolved_count = sum(1 for item in items if item["resolved_player_id"])
    logger.info(
        "Enriched %d items, %d resolved to nfl-data-py player IDs",
        len(items),
        resolved_count,
    )

    if args.dry_run:
        logger.info("[DRY RUN] Would write %d items. Sample:", len(items))
        if items and args.verbose:
            sample = items[0]
            print(json.dumps(sample, indent=2))
        return 0

    if not items:
        logger.info("No items to write.")
        return 0

    _save_items(items, season, output_dir, run_id)
    logger.info("Sleeper ingestion complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
