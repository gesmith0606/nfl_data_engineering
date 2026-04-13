#!/usr/bin/env python3
"""
Reddit Sentiment Ingestion -- Bronze Layer

Scrapes r/fantasyfootball and r/nfl for player/team news using Reddit's
public JSON API.  No authentication required.

Storage format mirrors the existing Bronze RSS pattern:
  data/bronze/sentiment/reddit/season=YYYY/reddit_{subreddit}_{YYYYMMDD_HHMMSS}.json

Each output file is a JSON envelope:
  {
    "fetch_run_id": "<uuid>",
    "source": "reddit_fantasyfootball",
    "fetched_at": "2026-04-07T09:00:00Z",
    "season": 2026,
    "week": null,
    "items": [ ... ]
  }

Usage
-----
  python scripts/ingest_sentiment_reddit.py --verbose
  python scripts/ingest_sentiment_reddit.py --subreddit fantasyfootball --limit 25
  python scripts/ingest_sentiment_reddit.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
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
logger = logging.getLogger("ingest_sentiment_reddit")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_SUBREDDITS = SENTIMENT_CONFIG.get(
    "reddit_subreddits", ["fantasyfootball", "nfl"]
)
_DEFAULT_LIMIT = SENTIMENT_CONFIG.get("reddit_post_limit", 25)
_USER_AGENT = SENTIMENT_CONFIG.get(
    "reddit_user_agent", "NFLDataEngineering/1.0"
)

# Rate limit: 1 second between requests to be a good citizen.
_REQUEST_DELAY_SEC = 1.0

# Regex for player name candidates (same as RSS ingestion).
_NAME_PATTERN = re.compile(
    r"\b([A-Z][a-z]{1,15}(?:\.[A-Z]\.?)?\s[A-Z][a-z]{2,20}"
    r"(?:\s(?:Jr|Sr|II|III|IV|V)\.?)?)\b"
)

# NFL team mentions for team-hint context.
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

    Returns:
        Integer year (e.g. 2026).
    """
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 6 else now.year - 1


def _extract_team_hint(text: str) -> Optional[str]:
    """Scan text for an NFL team mention and return its abbreviation.

    Args:
        text: Post title or body string.

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
        text: Post title or body string.

    Returns:
        Deduplicated list of candidate name strings.
    """
    found = _NAME_PATTERN.findall(text)
    seen: set = set()
    result: List[str] = []
    for name in found:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result


# ---------------------------------------------------------------------------
# Reddit API
# ---------------------------------------------------------------------------


def _fetch_subreddit(
    subreddit: str, limit: int
) -> Dict[str, Any]:
    """Fetch new posts from a subreddit using the public JSON API.

    Args:
        subreddit: Subreddit name (e.g. "fantasyfootball").
        limit: Maximum number of posts to fetch.

    Returns:
        Parsed JSON response dict.

    Raises:
        HTTPError: On rate limiting (429) or other HTTP errors.
        URLError: On network errors.
    """
    url = f"https://www.reddit.com/r/{subreddit}/new.json?limit={limit}"
    req = Request(url)
    req.add_header("User-Agent", _USER_AGENT)

    logger.info("Fetching %s (limit=%d)", url, limit)

    try:
        with urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as exc:
        if exc.code == 429:
            logger.warning(
                "Rate limited by Reddit (429). Consider reducing --limit."
            )
        else:
            logger.error("HTTP error fetching r/%s: %s", subreddit, exc)
        raise
    except URLError as exc:
        logger.error("Network error fetching r/%s: %s", subreddit, exc)
        raise


def _parse_reddit_response(
    response: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Parse Reddit JSON response into a flat list of post dicts.

    Args:
        response: Raw JSON from Reddit's listing endpoint.

    Returns:
        List of post data dicts (may be empty on malformed input).
    """
    try:
        children = response["data"]["children"]
    except (KeyError, TypeError):
        logger.warning("Malformed Reddit response -- missing data.children")
        return []

    posts: List[Dict[str, Any]] = []
    for child in children:
        data = child.get("data", {})
        if data:
            posts.append(data)
    return posts


def _post_to_item(
    post: Dict[str, Any],
    subreddit: str,
    resolver: PlayerNameResolver,
) -> Dict[str, Any]:
    """Convert a Reddit post dict to the canonical Bronze item format.

    Args:
        post: Reddit post data dict (from response.data.children[].data).
        subreddit: Subreddit name.
        resolver: Initialised PlayerNameResolver instance.

    Returns:
        Dict matching the Bronze RSS item format.
    """
    title = post.get("title", "") or ""
    selftext = post.get("selftext", "") or ""
    combined_text = f"{title} {selftext}"

    team_hint = _extract_team_hint(combined_text)
    candidate_names = _extract_candidate_names(combined_text)

    resolved_ids: List[str] = []
    for name in candidate_names:
        pid = resolver.resolve(name, team=team_hint)
        if pid:
            resolved_ids.append(pid)
            logger.debug("  Resolved '%s' -> %s (team hint: %s)", name, pid, team_hint)

    created_utc = post.get("created_utc", 0)
    if created_utc:
        published_at = datetime.fromtimestamp(
            created_utc, tz=timezone.utc
        ).isoformat()
    else:
        published_at = datetime.now(timezone.utc).isoformat()

    return {
        "external_id": post.get("id", ""),
        "url": post.get("url", ""),
        "permalink": post.get("permalink", ""),
        "title": title,
        "body_text": selftext,
        "author": post.get("author", ""),
        "published_at": published_at,
        "source": f"reddit_{subreddit}",
        "score": post.get("score", 0),
        "num_comments": post.get("num_comments", 0),
        "candidate_names": candidate_names,
        "resolved_player_ids": list(dict.fromkeys(resolved_ids)),
        "team_hint": team_hint,
    }


def _save_items(
    items: List[Dict[str, Any]],
    subreddit: str,
    season: int,
    output_dir: Path,
    run_id: str,
) -> Path:
    """Write the canonical Bronze JSON envelope to disk.

    Args:
        items: Processed item dicts.
        subreddit: Subreddit name.
        season: NFL season year.
        output_dir: Base directory for sentiment Reddit output.
        run_id: UUID string for this ingestion run.

    Returns:
        Path to the written file.
    """
    season_dir = output_dir / f"season={season}"
    season_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"reddit_{subreddit}_{timestamp}.json"
    out_path = season_dir / filename

    envelope: Dict[str, Any] = {
        "fetch_run_id": run_id,
        "source": f"reddit_{subreddit}",
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
# Main CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the Reddit ingestion CLI.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        description="Ingest NFL news from Reddit into the Bronze sentiment layer.",
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
        "--subreddit",
        type=str,
        default=None,
        help=(
            "Only scrape this subreddit (e.g. fantasyfootball, nfl). "
            "Default: all configured subreddits."
        ),
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=_DEFAULT_LIMIT,
        help=f"Max posts per subreddit (default: {_DEFAULT_LIMIT}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and parse posts but do not write any files.",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable DEBUG-level logging.",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point for the Reddit sentiment ingestion script.

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
    output_dir = _PROJECT_ROOT / SENTIMENT_LOCAL_DIRS["reddit"]
    run_id = str(uuid.uuid4())

    logger.info(
        "Reddit ingestion run=%s | season=%d | dry_run=%s",
        run_id[:8],
        season,
        args.dry_run,
    )

    # Build player resolver once
    logger.info("Building player name resolver...")
    resolver = PlayerNameResolver(bronze_root=_PROJECT_ROOT / "data/bronze")

    subreddits = (
        [args.subreddit] if args.subreddit else _DEFAULT_SUBREDDITS
    )

    total_items = 0
    total_resolved = 0
    files_written: List[Path] = []

    for idx, subreddit in enumerate(subreddits):
        # Rate limit between requests
        if idx > 0:
            logger.debug("Sleeping %.1fs for rate limiting...", _REQUEST_DELAY_SEC)
            time.sleep(_REQUEST_DELAY_SEC)

        try:
            response = _fetch_subreddit(subreddit, args.limit)
        except Exception as exc:
            logger.error("Failed to fetch r/%s: %s", subreddit, exc)
            continue

        posts = _parse_reddit_response(response)
        logger.info("r/%s: fetched %d posts", subreddit, len(posts))

        items: List[Dict[str, Any]] = []
        resolved_count = 0
        for post in posts:
            item = _post_to_item(post, subreddit, resolver)
            items.append(item)
            if item["resolved_player_ids"]:
                resolved_count += 1

        total_items += len(items)
        total_resolved += resolved_count

        logger.info(
            "r/%s: %d posts, %d with resolved player IDs",
            subreddit,
            len(items),
            resolved_count,
        )

        if args.dry_run:
            logger.info(
                "[DRY RUN] Would write %d items for r/%s", len(items), subreddit
            )
            if args.verbose and items:
                sample = items[0]
                print(
                    f"\n--- Sample post from r/{subreddit} ---\n"
                    f"Title: {sample['title']}\n"
                    f"Score: {sample['score']} | Comments: {sample['num_comments']}\n"
                    f"Player IDs: {sample['resolved_player_ids']}\n"
                )
        else:
            if items:
                out_path = _save_items(items, subreddit, season, output_dir, run_id)
                files_written.append(out_path)

    logger.info(
        "Ingestion complete: %d total posts, %d with player IDs, %d files written.",
        total_items,
        total_resolved,
        len(files_written),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
