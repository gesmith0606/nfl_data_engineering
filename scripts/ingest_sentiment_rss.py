#!/usr/bin/env python3
"""
RSS Sentiment Ingestion — Bronze Layer

Fetches NFL news from free RSS feeds (ESPN, NFL.com, Rotoworld/NBC Sports Edge,
Pro Football Talk, FantasyPros) and writes the raw articles as JSON to
data/bronze/sentiment/rss/.

Storage format mirrors the existing Bronze S3 key pattern:
  data/bronze/sentiment/rss/season=YYYY/rss_{source}_{YYYYMMDD_HHMMSS}.json

Each output file is a JSON envelope:
  {
    "fetch_run_id": "<uuid>",
    "source": "rss_espn",
    "fetched_at": "2026-04-07T09:00:00Z",
    "season": 2026,
    "week": null,
    "items": [ ... ]
  }

Each item in "items" preserves the full feedparser entry dict plus a
"resolved_player_ids" list populated by PlayerNameResolver.

Usage
-----
  # Dry-run preview (no files written)
  python scripts/ingest_sentiment_rss.py --dry-run

  # Full ingest for current season
  python scripts/ingest_sentiment_rss.py --season 2026

  # Single feed only
  python scripts/ingest_sentiment_rss.py --season 2026 --feed espn_news

  # Ingest and print player resolution stats
  python scripts/ingest_sentiment_rss.py --season 2026 --verbose
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Bootstrap: add project root to sys.path so `src.*` imports work whether
# this script is run as `python scripts/...` or via the CLAUDE.md helpers.
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_ROOT))

try:
    import feedparser  # type: ignore
except ImportError:
    print(
        "ERROR: feedparser is not installed.  "
        "Run: pip install feedparser",
        file=sys.stderr,
    )
    sys.exit(1)

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
logger = logging.getLogger("ingest_sentiment_rss")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Regex patterns used to extract player name candidates from article text.
# These are intentionally broad; false positives are acceptable because the
# downstream PlayerNameResolver will filter unresolvable names.
_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]{1,15}(?:\.[A-Z]\.?)?\s[A-Z][a-z]{2,20}(?:\s(?:Jr|Sr|II|III|IV|V)\.?)?)\b"
)

# NFL team abbreviations and their common long-form names — used as team-hint
# context when a team name appears close to a player name in text.
_TEAM_MENTIONS: Dict[str, str] = {
    "Chiefs": "KC", "Bills": "BUF", "Eagles": "PHI", "Cowboys": "DAL",
    "Patriots": "NE", "Packers": "GB", "Bears": "CHI", "Lions": "DET",
    "Vikings": "MIN", "49ers": "SF", "Rams": "LA", "Seahawks": "SEA",
    "Cardinals": "ARI", "Saints": "NO", "Buccaneers": "TB", "Falcons": "ATL",
    "Panthers": "CAR", "Steelers": "PIT", "Ravens": "BAL", "Browns": "CLE",
    "Bengals": "CIN", "Broncos": "DEN", "Raiders": "LV", "Chargers": "LAC",
    "Dolphins": "MIA", "Jets": "NYJ", "Giants": "NYG", "Commanders": "WAS",
    "Colts": "IND", "Texans": "HOU", "Jaguars": "JAX", "Titans": "TEN",
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _current_nfl_season() -> int:
    """Return the current NFL season year.

    The NFL season spans two calendar years; the season year is the year in
    which the regular season *starts* (September).  Anything before June is
    treated as the prior season (off-season).

    Returns:
        Integer year (e.g. 2026).
    """
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


def _extract_team_hint(text: str) -> Optional[str]:
    """Scan text for an NFL team mention and return its abbreviation.

    Args:
        text: Article title or description string.

    Returns:
        2-3 character team abbreviation or None.
    """
    for long_name, abbr in _TEAM_MENTIONS.items():
        if long_name in text:
            return abbr
    return None


def _extract_candidate_names(text: str) -> List[str]:
    """Return all Title-Case two-word sequences that look like player names.

    Args:
        text: Article title or description string.

    Returns:
        Deduplicated list of candidate name strings.
    """
    found = _NAME_PATTERN.findall(text)
    # Deduplicate while preserving order
    seen: set = set()
    result: List[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


def _entry_to_item(
    entry: Any,
    source_key: str,
    resolver: PlayerNameResolver,
) -> Dict[str, Any]:
    """Convert a feedparser entry to the canonical Bronze item dict.

    Args:
        entry: feedparser.FeedParserDict entry object.
        source_key: Source identifier string (e.g. "espn_news").
        resolver: Initialised PlayerNameResolver instance.

    Returns:
        Dict with all preserved entry fields plus "resolved_player_ids".
    """
    title = getattr(entry, "title", "") or ""
    summary = getattr(entry, "summary", "") or ""
    # Strip HTML tags from summary
    summary_text = re.sub(r"<[^>]+>", " ", summary).strip()

    combined_text = f"{title} {summary_text}"
    team_hint = _extract_team_hint(combined_text)
    candidate_names = _extract_candidate_names(combined_text)

    resolved_ids: List[str] = []
    for name in candidate_names:
        pid = resolver.resolve(name, team=team_hint)
        if pid:
            resolved_ids.append(pid)
            logger.debug("  Resolved '%s' → %s (team hint: %s)", name, pid, team_hint)

    # Parse published timestamp
    published_struct = getattr(entry, "published_parsed", None)
    if published_struct:
        published_at = datetime(*published_struct[:6], tzinfo=timezone.utc).isoformat()
    else:
        published_at = datetime.now(timezone.utc).isoformat()

    return {
        "external_id": getattr(entry, "id", None) or getattr(entry, "link", None),
        "url": getattr(entry, "link", None),
        "title": title,
        "body_text": summary_text,
        "author": getattr(entry, "author", None),
        "published_at": published_at,
        "source": f"rss_{source_key}",
        "candidate_names": candidate_names,
        "resolved_player_ids": list(dict.fromkeys(resolved_ids)),  # deduplicated
        "team_hint": team_hint,
    }


def _fetch_feed(
    feed_key: str,
    feed_url: str,
    resolver: PlayerNameResolver,
    max_entries: int,
) -> Tuple[List[Dict[str, Any]], int, int]:
    """Fetch a single RSS feed and return processed items.

    Args:
        feed_key: Short source identifier (e.g. "espn_news").
        feed_url: Full RSS feed URL.
        resolver: Initialised PlayerNameResolver.
        max_entries: Maximum number of feed entries to process.

    Returns:
        Tuple of (items, total_fetched, resolved_count) where items is the
        list of processed item dicts, total_fetched is the raw entry count,
        and resolved_count is the number of items with at least one resolved
        player ID.
    """
    logger.info("Fetching feed '%s' from %s", feed_key, feed_url)

    try:
        parsed = feedparser.parse(feed_url)
    except Exception as exc:
        logger.error("Failed to fetch feed '%s': %s", feed_key, exc)
        return [], 0, 0

    if parsed.bozo and not parsed.entries:
        logger.warning(
            "Feed '%s' returned a malformed response (bozo=%s): %s",
            feed_key,
            parsed.bozo,
            getattr(parsed, "bozo_exception", "unknown"),
        )
        return [], 0, 0

    entries = parsed.entries[:max_entries]
    total = len(entries)
    items: List[Dict[str, Any]] = []
    resolved_count = 0

    for entry in entries:
        item = _entry_to_item(entry, feed_key, resolver)
        items.append(item)
        if item["resolved_player_ids"]:
            resolved_count += 1

    logger.info(
        "Feed '%s': %d entries fetched, %d with resolved player IDs",
        feed_key,
        total,
        resolved_count,
    )
    return items, total, resolved_count


def _save_items(
    items: List[Dict[str, Any]],
    feed_key: str,
    season: int,
    output_dir: Path,
    run_id: str,
) -> Path:
    """Write the canonical Bronze JSON envelope to disk.

    Args:
        items: Processed item dicts from _fetch_feed.
        feed_key: Source identifier (e.g. "espn_news").
        season: NFL season year.
        output_dir: Base directory for sentiment RSS output.
        run_id: UUID string for this ingestion run.

    Returns:
        Path to the written file.
    """
    season_dir = output_dir / f"season={season}"
    season_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"rss_{feed_key}_{timestamp}.json"
    out_path = season_dir / filename

    envelope: Dict[str, Any] = {
        "fetch_run_id": run_id,
        "source": f"rss_{feed_key}",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "season": season,
        "week": None,  # RSS articles are not week-scoped
        "item_count": len(items),
        "items": items,
    }

    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(envelope, fh, indent=2, ensure_ascii=False)

    logger.info("Saved %d items → %s", len(items), out_path)
    return out_path


# ---------------------------------------------------------------------------
# Main CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Ingest NFL news from free RSS feeds into the Bronze sentiment layer.",
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
        "--feed",
        type=str,
        default=None,
        help=(
            "Only ingest this specific feed key "
            "(e.g. espn_news, nfl_news, rotoworld, pro_football_talk, fantasypros). "
            "Default: all feeds."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse feeds but do not write any files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    parser.add_argument(
        "--max-entries",
        type=int,
        default=None,
        help=(
            "Maximum entries to process per feed "
            f"(default: {SENTIMENT_CONFIG['max_entries_per_feed']})."
        ),
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the RSS sentiment ingestion script.

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
    max_entries = args.max_entries or SENTIMENT_CONFIG["max_entries_per_feed"]
    output_dir = _PROJECT_ROOT / SENTIMENT_LOCAL_DIRS["rss"]
    run_id = str(uuid.uuid4())

    logger.info(
        "RSS ingestion run=%s | season=%d | dry_run=%s",
        run_id[:8],
        season,
        args.dry_run,
    )

    # Build player resolver once (reused across all feeds)
    logger.info("Building player name resolver…")
    resolver = PlayerNameResolver(bronze_root=_PROJECT_ROOT / "data/bronze")

    feeds: Dict[str, str] = SENTIMENT_CONFIG["rss_feeds"]
    if args.feed:
        if args.feed not in feeds:
            logger.error(
                "Unknown feed '%s'. Available: %s", args.feed, list(feeds.keys())
            )
            return 1
        feeds = {args.feed: feeds[args.feed]}

    total_items = 0
    total_resolved = 0
    files_written: List[Path] = []

    for feed_key, feed_url in feeds.items():
        items, fetched, resolved = _fetch_feed(
            feed_key, feed_url, resolver, max_entries
        )
        total_items += fetched
        total_resolved += resolved

        if args.dry_run:
            logger.info(
                "[DRY RUN] Would write %d items for feed '%s'", len(items), feed_key
            )
            if args.verbose and items:
                sample = items[0]
                print(
                    f"\n--- Sample item from {feed_key} ---\n"
                    f"Title: {sample['title']}\n"
                    f"Player IDs: {sample['resolved_player_ids']}\n"
                )
        else:
            if items:
                out_path = _save_items(items, feed_key, season, output_dir, run_id)
                files_written.append(out_path)

    logger.info(
        "Ingestion complete: %d total entries, %d with player IDs, %d files written.",
        total_items,
        total_resolved,
        len(files_written),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
