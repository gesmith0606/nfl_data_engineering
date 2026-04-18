#!/usr/bin/env python3
"""
RotoWire Sentiment Ingestion -- Bronze Layer

Fetches NFL news from RotoWire's public RSS feed and writes Bronze JSON
envelopes that match the shape produced by scripts/ingest_sentiment_reddit.py.
No authentication required.  Free source, orthogonal to ANTHROPIC_API_KEY.

Per Phase 61-01 D-01 (Locked Decisions): RotoWire is one of the new sources
added to the rule-first sentiment pipeline.  The daily cron MUST NEVER be
blocked by upstream flakes, so any network failure is logged and results in
exit 0 with zero items written (D-06).

Storage format mirrors the existing Bronze sentiment pattern:
  data/bronze/sentiment/rotowire/season=YYYY/rotowire_{YYYYMMDD_HHMMSS}.json

Each output file is a JSON envelope:
  {
    "fetch_run_id": "<uuid>",
    "source": "rotowire",
    "fetched_at": "2026-04-18T00:00:00Z",
    "season": 2026,
    "week": null,
    "item_count": 12,
    "items": [ ... ]
  }

Usage
-----
  python scripts/ingest_sentiment_rotowire.py --verbose
  python scripts/ingest_sentiment_rotowire.py --limit 25
  python scripts/ingest_sentiment_rotowire.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# ---------------------------------------------------------------------------
# Bootstrap: add project root to sys.path
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
    format="%(asctime)s [%(levelname)s] %(name)s -- %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ingest_sentiment_rotowire")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Public RotoWire NFL news feed.  No auth, no API key required.
_ROTOWIRE_FEED_URL = "https://www.rotowire.com/rss/news.php?sport=nfl"

_SOURCE_NAME = "rotowire"

_DEFAULT_LIMIT = 50

# User agent: same pattern as the Reddit ingestion script.
_USER_AGENT = SENTIMENT_CONFIG.get("reddit_user_agent", "NFLDataEngineering/1.0")

# HTTP timeout and between-request sleep for good-citizen behaviour.
_HTTP_TIMEOUT_SEC = 15
_REQUEST_DELAY_SEC = 1.0

# Player name candidate regex -- identical to the Reddit ingestion script per
# the plan convention of keeping each ingestor's regex module-local.
_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]{1,15}(?:\.[A-Z]\.?)?\s[A-Z][a-z]{2,20}"
    r"(?:\s(?:Jr|Sr|II|III|IV|V)\.?)?)\b"
)

# NFL team mentions -- identical to scripts/ingest_sentiment_reddit.py.
_TEAM_MENTIONS: Dict[str, str] = {
    "Chiefs": "KC",
    "Bills": "BUF",
    "Eagles": "PHI",
    "Cowboys": "DAL",
    "Patriots": "NE",
    "Packers": "GB",
    "Bears": "CHI",
    "Lions": "DET",
    "Vikings": "MIN",
    "49ers": "SF",
    "Rams": "LA",
    "Seahawks": "SEA",
    "Cardinals": "ARI",
    "Saints": "NO",
    "Buccaneers": "TB",
    "Falcons": "ATL",
    "Panthers": "CAR",
    "Steelers": "PIT",
    "Ravens": "BAL",
    "Browns": "CLE",
    "Bengals": "CIN",
    "Broncos": "DEN",
    "Raiders": "LV",
    "Chargers": "LAC",
    "Dolphins": "MIA",
    "Jets": "NYJ",
    "Giants": "NYG",
    "Commanders": "WAS",
    "Colts": "IND",
    "Texans": "HOU",
    "Jaguars": "JAX",
    "Titans": "TEN",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_nfl_season() -> int:
    """Return the current NFL season year.

    Returns:
        Integer year (e.g. 2026).  The NFL season year is the year the
        regular season starts (September); anything before June is treated
        as the prior season.
    """
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


def _extract_team_hint(text: str) -> Optional[str]:
    """Scan text for an NFL team mention and return its abbreviation.

    Args:
        text: Article title or body string.

    Returns:
        2-3 character NFL team abbreviation or None if no match.
    """
    for long_name, abbr in _TEAM_MENTIONS.items():
        if long_name in text:
            return abbr
    return None


def _extract_candidate_names(text: str) -> List[str]:
    """Return Title-Case two-word sequences that look like player names.

    Args:
        text: Article title or body string.

    Returns:
        Deduplicated list of candidate name strings (order preserved).
    """
    found = _NAME_PATTERN.findall(text)
    seen: set = set()
    result: List[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _strip_html(text: str) -> str:
    """Return the string with HTML tags stripped and whitespace collapsed.

    RotoWire descriptions occasionally include lightweight markup; we treat
    the body as plain text downstream so remove tags here.

    Args:
        text: Potentially HTML-bearing string.

    Returns:
        Plain-text version of the input.
    """
    if not text:
        return ""
    stripped = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", stripped).strip()


def _parse_pubdate(pubdate: Optional[str]) -> str:
    """Convert an RFC-822 RSS pubDate to ISO-8601 UTC.

    Args:
        pubdate: RFC-822 formatted date string (e.g. "Tue, 01 Oct 2024
            15:00:00 GMT") or None.

    Returns:
        ISO-8601 UTC timestamp string.  Falls back to "now" UTC if the
        input cannot be parsed.
    """
    if not pubdate:
        return datetime.now(timezone.utc).isoformat()
    try:
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError) as exc:  # pragma: no cover -- defensive
        logger.debug("Unparseable pubDate '%s': %s", pubdate, exc)
        return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Feed fetch & parse
# ---------------------------------------------------------------------------


def _fetch_rotowire_xml(url: str = _ROTOWIRE_FEED_URL) -> str:
    """Fetch the RotoWire RSS XML payload over HTTPS.

    Args:
        url: RSS feed URL (defaults to the public NFL news feed).

    Returns:
        Raw XML string.

    Raises:
        HTTPError: On non-2xx responses.
        URLError: On network errors (DNS, connection refused, timeout).
    """
    req = Request(url)
    req.add_header("User-Agent", _USER_AGENT)
    logger.info("Fetching %s", url)
    with urlopen(req, timeout=_HTTP_TIMEOUT_SEC) as resp:
        return resp.read().decode("utf-8", errors="replace")


def _parse_rotowire_feed(xml_text: str) -> List[Dict[str, Any]]:
    """Parse RotoWire's RSS 2.0 XML into a list of item dicts.

    Args:
        xml_text: Raw XML payload from the RSS feed.

    Returns:
        List of dicts with keys: title, url, body_text, published_at,
        external_id, author.  Returns an empty list on parse errors so
        the caller (daily cron) can continue gracefully (D-06).
    """
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        logger.warning("Failed to parse RotoWire XML: %s", exc)
        return []

    channel = root.find("channel")
    if channel is None:
        logger.warning("RotoWire XML missing <channel> element")
        return []

    items: List[Dict[str, Any]] = []
    for entry in channel.findall("item"):
        title = (entry.findtext("title") or "").strip()
        link = (entry.findtext("link") or "").strip()
        description = _strip_html(entry.findtext("description") or "")
        pub_date = entry.findtext("pubDate")
        guid = (entry.findtext("guid") or "").strip() or link
        author = (entry.findtext("author") or "").strip()

        items.append(
            {
                "title": title,
                "url": link,
                "body_text": description,
                "published_at": _parse_pubdate(pub_date),
                "external_id": guid,
                "author": author,
            }
        )

    return items


# ---------------------------------------------------------------------------
# Bronze envelope construction
# ---------------------------------------------------------------------------


def _item_to_bronze(
    parsed: Dict[str, Any], resolver: PlayerNameResolver
) -> Dict[str, Any]:
    """Convert a parsed RotoWire feed entry to the canonical Bronze item.

    The output shape matches scripts/ingest_sentiment_reddit.py::_post_to_item
    exactly so downstream rule extraction works without source-specific code.

    Args:
        parsed: Dict produced by _parse_rotowire_feed (one item).
        resolver: PlayerNameResolver used to map candidate names to
            canonical player_ids.

    Returns:
        Dict with all Bronze item fields populated.
    """
    title = parsed.get("title", "") or ""
    body_text = parsed.get("body_text", "") or ""
    combined = f"{title} {body_text}"

    team_hint = _extract_team_hint(combined)
    candidate_names = _extract_candidate_names(combined)

    resolved_ids: List[str] = []
    for name in candidate_names:
        pid = resolver.resolve(name, team=team_hint)
        if pid:
            resolved_ids.append(pid)
            logger.debug("  Resolved '%s' -> %s (team hint: %s)", name, pid, team_hint)

    return {
        "external_id": parsed.get("external_id", "") or parsed.get("url", ""),
        "url": parsed.get("url", ""),
        "permalink": "",
        "title": title,
        "body_text": body_text,
        "author": parsed.get("author", "") or "",
        "published_at": parsed.get(
            "published_at", datetime.now(timezone.utc).isoformat()
        ),
        "source": _SOURCE_NAME,
        "score": 0,
        "num_comments": 0,
        "candidate_names": candidate_names,
        "resolved_player_ids": list(dict.fromkeys(resolved_ids)),
        "team_hint": team_hint,
    }


def _save_items(
    items: List[Dict[str, Any]],
    season: int,
    output_dir: Path,
    run_id: str,
) -> Path:
    """Write the canonical Bronze JSON envelope to disk.

    Args:
        items: Processed Bronze item dicts.
        season: NFL season year.
        output_dir: Base directory for rotowire Bronze output.
        run_id: UUID string for this ingestion run.

    Returns:
        Path to the written JSON file.
    """
    season_dir = output_dir / f"season={season}"
    season_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"rotowire_{timestamp}.json"
    out_path = season_dir / filename

    envelope: Dict[str, Any] = {
        "fetch_run_id": run_id,
        "source": _SOURCE_NAME,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "week": None,
        "item_count": len(items),
        "items": items,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, ensure_ascii=False)

    logger.info("Saved %d items -> %s", len(items), out_path)
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the RotoWire ingestion CLI.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        description=(
            "Ingest NFL news from RotoWire's public RSS feed into the "
            "Bronze sentiment layer."
        ),
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
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"Max items to process from the feed (default: {_DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse items but do not write any files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the RotoWire sentiment ingestion script.

    Args:
        argv: Argument list (uses sys.argv when None).

    Returns:
        Exit code (always 0 unless the user-supplied arguments are invalid;
        all network/parsing failures are logged and still return 0 per
        D-06 to keep the daily cron unblocked).
    """
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    season = args.season or _current_nfl_season()
    output_dir = _PROJECT_ROOT / SENTIMENT_LOCAL_DIRS["rotowire"]
    run_id = str(uuid.uuid4())

    logger.info(
        "RotoWire ingestion run=%s | season=%d | dry_run=%s",
        run_id[:8],
        season,
        args.dry_run,
    )

    # Fetch feed -- any failure is logged and results in exit 0 (D-06).
    try:
        xml_text = _fetch_rotowire_xml()
    except HTTPError as exc:
        logger.warning(
            "HTTP error fetching RotoWire feed (status=%s): %s; exiting 0.",
            exc.code,
            exc,
        )
        return 0
    except URLError as exc:
        logger.warning("Network error fetching RotoWire feed: %s; exiting 0.", exc)
        return 0
    except Exception as exc:  # pragma: no cover -- defensive catch-all
        logger.warning("Unexpected error fetching RotoWire feed: %s; exiting 0.", exc)
        return 0

    # Good-citizen delay before any downstream work
    time.sleep(_REQUEST_DELAY_SEC)

    parsed = _parse_rotowire_feed(xml_text)
    logger.info("RotoWire: parsed %d raw items", len(parsed))

    parsed = parsed[: args.limit]

    # Build resolver once
    logger.info("Building player name resolver...")
    try:
        resolver = PlayerNameResolver(bronze_root=_PROJECT_ROOT / "data/bronze")
    except Exception as exc:  # pragma: no cover -- defensive
        logger.warning(
            "Failed to build PlayerNameResolver (%s); continuing with "
            "empty resolver.",
            exc,
        )
        resolver = _NullResolver()  # type: ignore[assignment]

    items: List[Dict[str, Any]] = []
    resolved_count = 0
    for entry in parsed:
        item = _item_to_bronze(entry, resolver)
        items.append(item)
        if item["resolved_player_ids"]:
            resolved_count += 1

    logger.info(
        "RotoWire: %d items processed, %d with resolved player IDs",
        len(items),
        resolved_count,
    )

    if args.dry_run:
        logger.info("[DRY RUN] Would write %d items", len(items))
        if args.verbose and items:
            sample = items[0]
            logger.info(
                "Sample item -- title='%s' | team_hint=%s | resolved_ids=%s",
                sample["title"][:80],
                sample["team_hint"],
                sample["resolved_player_ids"],
            )
        return 0

    if items:
        _save_items(items, season, output_dir, run_id)

    return 0


class _NullResolver:
    """Fallback resolver used when the real resolver fails to build.

    Keeps ingestion flowing (D-06) rather than aborting the cron when the
    Bronze layer is empty or unreadable (e.g. first-run bootstrap).
    """

    def resolve(
        self,
        name: str,
        team: Optional[str] = None,
        position: Optional[str] = None,
    ) -> Optional[str]:
        """Return None for every name (no-op stand-in resolver).

        Args:
            name: Ignored.
            team: Ignored.
            position: Ignored.

        Returns:
            None.
        """
        return None


if __name__ == "__main__":
    sys.exit(main())
