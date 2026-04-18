"""
Service layer for reading player news and sentiment data.

Supports three data tiers:
  1. Gold sentiment Parquet  -- aggregated per-player-week multipliers
  2. Silver signals JSON     -- individual news items with extracted fields
  3. Bronze documents JSON   -- raw documents (title, body, URL) from RSS/Reddit/Sleeper

The news feed is built primarily from Bronze documents (which carry titles, URLs,
and body text) enriched with Silver signal data (sentiment scores, event flags).
This approach gives the frontend rich, readable news items rather than the sparse
signal records in Silver.

All reads fall back gracefully to empty results when files do not exist.
This is intentional: the pipeline may not have ingested sentiment data yet.
"""

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from ..config import BRONZE_SENTIMENT_DIR, GOLD_SENTIMENT_DIR, SILVER_SENTIMENT_DIR

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data path constants
# ---------------------------------------------------------------------------

_GOLD_SENTIMENT_DIR = GOLD_SENTIMENT_DIR
_SILVER_SIGNALS_DIR = SILVER_SENTIMENT_DIR / "signals"
_BRONZE_SENTIMENT_DIR = BRONZE_SENTIMENT_DIR


# ---------------------------------------------------------------------------
# Parquet helpers
# ---------------------------------------------------------------------------


def _latest_parquet(directory: Path) -> Optional[Path]:
    """Return the most-recently modified Parquet file in *directory*, or None."""
    if not directory.exists():
        return None
    parquets = sorted(directory.glob("*.parquet"), key=lambda p: p.stat().st_mtime)
    return parquets[-1] if parquets else None


def _load_gold_sentiment(season: int, week: int) -> pd.DataFrame:
    """Load Gold aggregated sentiment for a season/week.

    Args:
        season: NFL season year.
        week: NFL week number (1-18).

    Returns:
        DataFrame with one row per player, or empty DataFrame if unavailable.
    """
    week_dir = _GOLD_SENTIMENT_DIR / f"season={season}" / f"week={week:02d}"
    parquet_path = _latest_parquet(week_dir)
    if parquet_path is None:
        logger.debug(
            "No Gold sentiment parquet found for season=%d week=%d", season, week
        )
        return pd.DataFrame()

    try:
        df = pd.read_parquet(parquet_path)
        logger.debug("Loaded %d Gold sentiment rows from %s", len(df), parquet_path)
        return df
    except Exception as exc:
        logger.warning(
            "Could not read Gold sentiment parquet %s: %s", parquet_path, exc
        )
        return pd.DataFrame()


# ---------------------------------------------------------------------------
# Silver signal helpers
# ---------------------------------------------------------------------------


def _find_silver_files(season: int, week: int) -> List[Path]:
    """Find all Silver signal JSON files for a season/week.

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        List of Path objects sorted by modification time, newest first.
    """
    season_dir = _SILVER_SIGNALS_DIR / f"season={season}"
    week_dir = season_dir / f"week={week:02d}"

    files: List[Path] = []
    if week_dir.exists():
        files.extend(week_dir.glob("*.json"))
    if season_dir.exists():
        files.extend(f for f in season_dir.glob("*.json") if f.is_file())

    return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)


def _find_silver_files_all_weeks(season: int) -> List[Path]:
    """Find all Silver signal JSON files for every week in a season.

    Args:
        season: NFL season year.

    Returns:
        List of Path objects sorted by modification time, newest first.
    """
    season_dir = _SILVER_SIGNALS_DIR / f"season={season}"
    if not season_dir.exists():
        return []

    files: List[Path] = []
    for week_dir in season_dir.iterdir():
        if week_dir.is_dir() and week_dir.name.startswith("week="):
            files.extend(week_dir.glob("*.json"))
    # Also pick up any JSON files directly in the season dir
    files.extend(f for f in season_dir.glob("*.json") if f.is_file())

    return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)


def _load_silver_records(files: List[Path]) -> List[Dict[str, Any]]:
    """Load all signal records from a list of Silver JSON files.

    Args:
        files: List of paths to Silver signal JSON files.

    Returns:
        Flat list of signal record dicts.
    """
    records: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read Silver file %s: %s", path, exc)
            continue

        if isinstance(data, dict):
            batch = data.get("records", [])
        elif isinstance(data, list):
            batch = data
        else:
            continue

        records.extend(r for r in batch if isinstance(r, dict))

    return records


def _build_silver_index(
    records: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a doc_id -> silver record lookup for enrichment.

    Args:
        records: List of Silver signal record dicts.

    Returns:
        Dict mapping doc_id to the silver record with highest sentiment confidence.
    """
    index: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        doc_id = rec.get("doc_id") or rec.get("external_id")
        if doc_id is None:
            continue
        key = str(doc_id)
        existing = index.get(key)
        if existing is None or (
            rec.get("sentiment_confidence", 0) > existing.get("sentiment_confidence", 0)
        ):
            index[key] = rec
    return index


# ---------------------------------------------------------------------------
# Bronze document helpers
# ---------------------------------------------------------------------------


def _find_bronze_files_for_season(season: int) -> List[Path]:
    """Find all Bronze document JSON files for a season across all sources.

    The bronze directory structure is:
        data/bronze/sentiment/{source}/season=YYYY/{files}.json

    where source is rss, reddit, sleeper, etc.

    Args:
        season: NFL season year.

    Returns:
        List of Path objects, newest first.
    """
    files: List[Path] = []

    if not _BRONZE_SENTIMENT_DIR.exists():
        return files

    # Walk source-level directories: rss/, reddit/, sleeper/
    for source_dir in _BRONZE_SENTIMENT_DIR.iterdir():
        if not source_dir.is_dir():
            continue
        # Check for season subdirectory within each source
        season_dir = source_dir / f"season={season}"
        if season_dir.exists():
            files.extend(season_dir.glob("*.json"))

    return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)


def _load_bronze_records(files: List[Path]) -> List[Dict[str, Any]]:
    """Load Bronze document records from a list of JSON files.

    Handles both the ``items`` key (current pipeline format) and the legacy
    ``documents`` key.

    Args:
        files: List of paths to Bronze JSON files.

    Returns:
        Flat list of document dicts.
    """
    records: List[Dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read Bronze file %s: %s", path, exc)
            continue

        if isinstance(data, list):
            records.extend(r for r in data if isinstance(r, dict))
        elif isinstance(data, dict):
            # Current pipeline uses "items"; legacy uses "documents"
            items = data.get("items") or data.get("documents") or []
            if items:
                records.extend(r for r in items if isinstance(r, dict))
            elif "external_id" in data or "title" in data:
                records.append(data)

    return records


def _build_bronze_index(
    records: List[Dict[str, Any]],
) -> Dict[str, Dict[str, Any]]:
    """Build a lookup of external_id -> bronze record for enrichment.

    Args:
        records: List of bronze document dicts.

    Returns:
        Dict mapping external_id to the full bronze record.
    """
    index: Dict[str, Dict[str, Any]] = {}
    for rec in records:
        ext_id = rec.get("external_id") or rec.get("id")
        if ext_id:
            index[str(ext_id)] = rec
    return index


# ---------------------------------------------------------------------------
# Unified news item builder
# ---------------------------------------------------------------------------


def _build_news_item_from_bronze(
    bronze_rec: Dict[str, Any],
    silver_rec: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build a unified NewsItem dict from a bronze record, optionally
    enriched with silver signal data (sentiment, events).

    Args:
        bronze_rec: Raw bronze document record.
        silver_rec: Optional matching silver signal record.

    Returns:
        Dict matching the NewsItem schema.
    """
    ext_id = bronze_rec.get("external_id") or bronze_rec.get("id")
    source_raw = bronze_rec.get("source", "unknown")

    # Normalize source names for display
    source = source_raw

    # Extract body snippet
    body = (
        bronze_rec.get("body_text")
        or bronze_rec.get("body")
        or bronze_rec.get("news_body")
        or ""
    )
    body_snippet = body[:200] if body else None

    # Get player info from silver first, then bronze
    player_id = None
    player_name = None
    team = None

    if silver_rec:
        player_id = silver_rec.get("player_id")
        player_name = silver_rec.get("player_name")

    if not player_name:
        player_name = bronze_rec.get("player_name")
    if not player_id:
        # Bronze RSS has resolved_player_ids list
        resolved_ids = bronze_rec.get("resolved_player_ids") or []
        if resolved_ids:
            player_id = resolved_ids[0]
        player_id = player_id or bronze_rec.get("resolved_player_id")

    team = bronze_rec.get("team") or bronze_rec.get("team_hint")

    # Sentiment from silver
    sentiment = None
    category = None
    events: Dict[str, Any] = {}
    if silver_rec:
        sentiment = silver_rec.get("sentiment_score")
        category = silver_rec.get("category")
        events = silver_rec.get("events") or {}

    # Published date
    published_at = bronze_rec.get("published_at") or bronze_rec.get("news_date")

    return {
        "doc_id": str(ext_id) if ext_id else None,
        "title": bronze_rec.get("title"),
        "source": source,
        "url": bronze_rec.get("url") or bronze_rec.get("permalink"),
        "published_at": published_at,
        "sentiment": sentiment,
        "category": category,
        "player_id": player_id,
        "player_name": player_name,
        "team": team,
        "is_ruled_out": bool(events.get("is_ruled_out", False)),
        "is_inactive": bool(events.get("is_inactive", False)),
        "is_questionable": bool(events.get("is_questionable", False)),
        "is_suspended": bool(events.get("is_suspended", False)),
        "is_returning": bool(events.get("is_returning", False)),
        "body_snippet": body_snippet,
    }


def _build_news_item_from_silver(
    silver_rec: Dict[str, Any],
) -> Dict[str, Any]:
    """Build a NewsItem from a silver record when no matching bronze exists.

    Uses the raw_excerpt field as the body snippet.

    Args:
        silver_rec: Silver signal record dict.

    Returns:
        Dict matching the NewsItem schema.
    """
    events: Dict[str, Any] = silver_rec.get("events") or {}
    doc_id = silver_rec.get("doc_id") or silver_rec.get("signal_id")
    raw_excerpt = silver_rec.get("raw_excerpt") or ""

    return {
        "doc_id": str(doc_id) if doc_id else None,
        "title": None,
        "source": silver_rec.get("source", "unknown"),
        "url": None,
        "published_at": silver_rec.get("published_at"),
        "sentiment": silver_rec.get("sentiment_score"),
        "category": silver_rec.get("category"),
        "player_id": silver_rec.get("player_id"),
        "player_name": silver_rec.get("player_name"),
        "team": None,
        "is_ruled_out": bool(events.get("is_ruled_out", False)),
        "is_inactive": bool(events.get("is_inactive", False)),
        "is_questionable": bool(events.get("is_questionable", False)),
        "is_suspended": bool(events.get("is_suspended", False)),
        "is_returning": bool(events.get("is_returning", False)),
        "body_snippet": raw_excerpt[:200] if raw_excerpt else None,
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_player_news(
    player_id: str,
    season: int,
    week: int,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return recent news items for a specific player.

    Merges Bronze documents (titles, URLs) with Silver signals (sentiment)
    and filters to those referencing *player_id*.

    Args:
        player_id: Canonical player ID.
        season: NFL season year.
        week: NFL week number.
        limit: Maximum number of items to return.

    Returns:
        List of news item dicts ordered newest first.
    """
    # Load silver signals for enrichment
    silver_files = _find_silver_files(season, week)
    silver_records = _load_silver_records(silver_files) if silver_files else []
    silver_index = _build_silver_index(silver_records)

    # Load bronze documents
    bronze_files = _find_bronze_files_for_season(season)
    bronze_records = _load_bronze_records(bronze_files)

    items: List[Dict[str, Any]] = []

    # Build items from bronze, enriched with silver
    for bronze_rec in bronze_records:
        ext_id = str(bronze_rec.get("external_id") or bronze_rec.get("id") or "")
        silver_rec = silver_index.get(ext_id)
        item = _build_news_item_from_bronze(bronze_rec, silver_rec)

        if item.get("player_id") == player_id:
            items.append(item)

    # Also add silver-only records that have no bronze match
    bronze_ids = {
        str(r.get("external_id") or r.get("id") or "") for r in bronze_records
    }
    for rec in silver_records:
        doc_id = str(rec.get("doc_id") or "")
        if doc_id not in bronze_ids and rec.get("player_id") == player_id:
            items.append(_build_news_item_from_silver(rec))

    # Sort newest first and paginate
    items.sort(key=lambda r: r.get("published_at") or "", reverse=True)
    return items[:limit]


def get_active_alerts(season: int, week: int) -> List[Dict[str, Any]]:
    """Return all active alerts for a season/week from Gold sentiment data.

    An alert is triggered when a player has any of: is_ruled_out, is_inactive,
    is_questionable, is_suspended, or a major sentiment shift
    (sentiment_multiplier < 0.85 or > 1.10).

    Falls back gracefully to empty list when Gold data is unavailable.

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        List of alert dicts ordered by severity (ruled_out first).
    """
    df = _load_gold_sentiment(season, week)
    if df.empty:
        return []

    alerts: List[Dict[str, Any]] = []

    for _, row in df.iterrows():
        player_id = str(row.get("player_id", ""))
        player_name = str(row.get("player_name", ""))
        sentiment_mult = float(row.get("sentiment_multiplier", 1.0))
        latest_signal = row.get("latest_signal_at")
        doc_count = int(row.get("doc_count", 0))

        # Determine alert type (highest severity first)
        alert_type: Optional[str] = None
        if row.get("is_ruled_out"):
            alert_type = "ruled_out"
        elif row.get("is_inactive"):
            alert_type = "inactive"
        elif row.get("is_suspended"):
            alert_type = "suspended"
        elif row.get("is_questionable"):
            alert_type = "questionable"
        elif sentiment_mult <= 0.85:
            alert_type = "major_negative"
        elif sentiment_mult >= 1.10:
            alert_type = "major_positive"

        if alert_type is None:
            continue

        alerts.append(
            {
                "player_id": player_id,
                "player_name": player_name,
                "team": str(row.get("team", "")) if "team" in row.index else None,
                "position": (
                    str(row.get("position", "")) if "position" in row.index else None
                ),
                "alert_type": alert_type,
                "sentiment_multiplier": sentiment_mult,
                "latest_signal_at": str(latest_signal) if latest_signal else None,
                "doc_count": doc_count,
            }
        )

    # Sort: ruled_out / inactive first, then by sentiment extremity
    _severity = {
        "ruled_out": 0,
        "inactive": 1,
        "suspended": 2,
        "major_negative": 3,
        "questionable": 4,
        "major_positive": 5,
    }
    alerts.sort(key=lambda a: _severity.get(a["alert_type"], 99))

    return alerts


def get_news_feed(
    season: int,
    week: Optional[int],
    source: Optional[str],
    team: Optional[str],
    player_id: Optional[str],
    limit: int = 50,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    """Return paginated news items from all sources for a season.

    Builds the feed primarily from Bronze documents (which carry titles and
    URLs) and enriches them with Silver signal data (sentiment scores, event
    flags). This gives the frontend rich, readable news items.

    When no Silver data is available, Bronze items are still returned with
    null sentiment values.

    Args:
        season: NFL season year.
        week: NFL week number (1-18). When None, returns news across all weeks.
        source: Optional source filter (e.g. ``"reddit"``, ``"rss_espn_news"``).
        team: Optional 3-letter team code filter.
        player_id: Optional player ID filter.
        limit: Maximum number of items to return (default 50).
        offset: Number of items to skip for pagination (default 0).

    Returns:
        List of news item dicts ordered newest first.
    """
    # Load silver signals for enrichment
    if week is not None:
        silver_files = _find_silver_files(season, week)
    else:
        silver_files = _find_silver_files_all_weeks(season)

    silver_records = _load_silver_records(silver_files) if silver_files else []
    silver_index = _build_silver_index(silver_records)

    # Load bronze documents (always load full season for richest feed)
    bronze_files = _find_bronze_files_for_season(season)
    bronze_records = _load_bronze_records(bronze_files)

    items: List[Dict[str, Any]] = []

    # Deduplicate bronze by external_id (multiple ingestion runs)
    seen_ids: set = set()

    for bronze_rec in bronze_records:
        ext_id = str(bronze_rec.get("external_id") or bronze_rec.get("id") or "")
        if ext_id in seen_ids:
            continue
        seen_ids.add(ext_id)

        silver_rec = silver_index.get(ext_id)
        item = _build_news_item_from_bronze(bronze_rec, silver_rec)
        items.append(item)

    # Also add silver-only records that have no bronze match
    for rec in silver_records:
        doc_id = str(rec.get("doc_id") or "")
        if doc_id and doc_id not in seen_ids:
            seen_ids.add(doc_id)
            items.append(_build_news_item_from_silver(rec))

    # Apply filters
    if source:
        items = [r for r in items if source in (r.get("source") or "")]
    if team:
        items = [r for r in items if r.get("team", "") == team]
    if player_id:
        items = [
            r
            for r in items
            if r.get("player_id") == player_id
            or player_id in (r.get("player_name") or "")
        ]

    # Sort newest first
    items.sort(key=lambda r: r.get("published_at") or "", reverse=True)

    # Paginate
    return items[offset : offset + limit]


def get_team_sentiment(season: int, week: int) -> List[Dict[str, Any]]:
    """Return aggregated sentiment summary for all teams in a season/week.

    When the Gold data lacks a ``team`` column, this function falls back to
    building team sentiment from Silver signal records, grouping by player
    team hints derived from bronze data.

    Args:
        season: NFL season year.
        week: NFL week number (1-18).

    Returns:
        List of team sentiment dicts, one per team, ordered by team abbreviation.
    """
    df = _load_gold_sentiment(season, week)

    # Try Gold data first if it has a team column
    if not df.empty and "team" in df.columns:
        return _team_sentiment_from_gold(df, season, week)

    # Fall back: build team sentiment from Silver signals + Bronze team hints
    return _team_sentiment_from_signals(season, week)


def _team_sentiment_from_gold(
    df: pd.DataFrame, season: int, week: int
) -> List[Dict[str, Any]]:
    """Build team sentiment from Gold data with team column."""
    sentiment_col = (
        "sentiment_score_avg" if "sentiment_score_avg" in df.columns else None
    )
    mult_col = "sentiment_multiplier" if "sentiment_multiplier" in df.columns else None

    results: List[Dict[str, Any]] = []
    for team_name, group in df.groupby("team"):
        avg_score = (
            float(group[sentiment_col].dropna().mean())
            if sentiment_col and not group[sentiment_col].dropna().empty
            else 0.0
        )
        avg_mult = (
            float(group[mult_col].dropna().mean())
            if mult_col and not group[mult_col].dropna().empty
            else 1.0
        )
        signal_count = (
            int(group["doc_count"].sum())
            if "doc_count" in group.columns
            else len(group)
        )

        if avg_score > 0.1:
            label = "positive"
        elif avg_score < -0.1:
            label = "negative"
        else:
            label = "neutral"

        results.append(
            {
                "team": str(team_name),
                "season": season,
                "week": week,
                "sentiment_score": round(avg_score, 4),
                "sentiment_label": label,
                "signal_count": signal_count,
                "sentiment_multiplier": round(avg_mult, 4),
            }
        )

    results.sort(key=lambda r: r["team"])
    return results


def _team_sentiment_from_signals(season: int, week: int) -> List[Dict[str, Any]]:
    """Build team sentiment from Silver signals + Bronze team hints.

    Falls back to this when Gold data lacks a team column. Collects team
    info from bronze Sleeper items (which have team fields) and groups
    sentiment scores from silver signals by team.

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        List of team sentiment dicts.
    """
    # Load bronze to get team mapping (Sleeper items have team field)
    bronze_files = _find_bronze_files_for_season(season)
    bronze_records = _load_bronze_records(bronze_files)

    # Build player_name -> team mapping from bronze
    name_to_team: Dict[str, str] = {}
    for rec in bronze_records:
        name = rec.get("player_name")
        team = rec.get("team") or rec.get("team_hint")
        if name and team:
            name_to_team[name] = team

    # Load silver signals
    silver_files = _find_silver_files(season, week)
    if not silver_files:
        silver_files = _find_silver_files_all_weeks(season)
    silver_records = _load_silver_records(silver_files)

    # Group signals by team
    team_scores: Dict[str, List[float]] = {}
    team_counts: Dict[str, int] = {}

    for rec in silver_records:
        player_name = rec.get("player_name", "")
        team = name_to_team.get(player_name)
        if not team:
            continue

        score = rec.get("sentiment_score")
        if score is not None:
            team_scores.setdefault(team, []).append(float(score))
        team_counts[team] = team_counts.get(team, 0) + 1

    results: List[Dict[str, Any]] = []
    for team in sorted(set(list(team_scores.keys()) + list(team_counts.keys()))):
        scores = team_scores.get(team, [])
        avg_score = sum(scores) / len(scores) if scores else 0.0
        signal_count = team_counts.get(team, 0)

        # Derive multiplier from average score
        if avg_score > 0.1:
            label = "positive"
            mult = 1.0 + min(avg_score * 0.15, 0.15)
        elif avg_score < -0.1:
            label = "negative"
            mult = 1.0 + max(avg_score * 0.15, -0.30)
        else:
            label = "neutral"
            mult = 1.0

        results.append(
            {
                "team": team,
                "season": season,
                "week": week,
                "sentiment_score": round(avg_score, 4),
                "sentiment_label": label,
                "signal_count": signal_count,
                "sentiment_multiplier": round(mult, 4),
            }
        )

    return results


def get_player_sentiment(
    player_id: str,
    season: int,
    week: int,
) -> Optional[Dict[str, Any]]:
    """Return aggregated Gold sentiment for a single player-week.

    Args:
        player_id: Canonical player ID.
        season: NFL season year.
        week: NFL week number.

    Returns:
        Dict of aggregated features, or None if no data found for this player.
    """
    df = _load_gold_sentiment(season, week)
    if df.empty:
        return None

    mask = df["player_id"].astype(str) == player_id
    matching = df[mask]

    if matching.empty:
        return None

    row = matching.iloc[0]

    def _safe_float(val: Any) -> Optional[float]:
        if val is None:
            return None
        try:
            f = float(val)
            return None if f != f else f  # NaN guard
        except (TypeError, ValueError):
            return None

    def _safe_int(val: Any) -> int:
        try:
            return int(float(val))
        except (TypeError, ValueError):
            return 0

    staleness = row.get("signal_staleness_hours")

    return {
        "player_id": player_id,
        "player_name": str(row.get("player_name", "")),
        "season": season,
        "week": week,
        "sentiment_multiplier": float(row.get("sentiment_multiplier", 1.0)),
        "sentiment_score_avg": _safe_float(row.get("sentiment_score_avg")),
        "doc_count": _safe_int(row.get("doc_count", 0)),
        "is_ruled_out": bool(row.get("is_ruled_out", False)),
        "is_inactive": bool(row.get("is_inactive", False)),
        "is_questionable": bool(row.get("is_questionable", False)),
        "is_suspended": bool(row.get("is_suspended", False)),
        "is_returning": bool(row.get("is_returning", False)),
        "latest_signal_at": (
            str(row.get("latest_signal_at")) if row.get("latest_signal_at") else None
        ),
        "signal_staleness_hours": _safe_float(staleness),
    }


def get_sentiment_summary(season: int, week: int) -> Dict[str, Any]:
    """Return a summary of sentiment data for dashboard display.

    Carries two sets of keys so both the existing news-feed page and the
    AI advisor ``getSentimentSummary`` tool stay happy:

    * Legacy (news-feed.tsx): ``total_docs``, ``total_players``,
      ``top_positive``, ``top_negative``, ``sentiment_distribution``.
    * Advisor (chat/route.ts): ``total_articles``, ``bullish_players``,
      ``bearish_players``, ``average_sentiment``, and ``sources`` as an
      array of ``{source, count}`` objects.

    Both views reflect the same underlying Gold Parquet slice.

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        Dict with the union of legacy + advisor summary fields.
    """
    df = _load_gold_sentiment(season, week)

    summary: Dict[str, Any] = {
        "season": season,
        "week": week,
        # Legacy (kept for news-feed.tsx)
        "total_players": 0,
        "total_docs": 0,
        "top_positive": [],
        "top_negative": [],
        "sentiment_distribution": {"positive": 0, "neutral": 0, "negative": 0},
        # Advisor contract (chat/route.ts)
        "total_articles": 0,
        "sources": [],
        "bullish_players": [],
        "bearish_players": [],
        "average_sentiment": 0.0,
    }

    if df.empty:
        return summary

    total_docs = int(df["doc_count"].sum()) if "doc_count" in df.columns else 0
    summary["total_players"] = len(df)
    summary["total_docs"] = total_docs
    # Advisor alias — articles == documents for the purposes of the chat tool
    summary["total_articles"] = total_docs

    # Source breakdown -- emitted as an array of {source, count} objects so
    # the advisor contract sees a list. news-feed.tsx does not read .sources,
    # so reshaping here is safe.
    sources: List[Dict[str, Any]] = []
    for col in [
        "rss_doc_count",
        "sleeper_doc_count",
        "official_report_count",
        "twitter_doc_count",
    ]:
        if col in df.columns:
            name = col.replace("_doc_count", "").replace("_count", "")
            count = int(df[col].sum())
            if count > 0 or col == "rss_doc_count":
                sources.append({"source": name, "count": count})
    summary["sources"] = sources

    # Sentiment distribution + average
    if "sentiment_score_avg" in df.columns:
        scores = df["sentiment_score_avg"].dropna()
        summary["sentiment_distribution"]["positive"] = int((scores > 0.1).sum())
        summary["sentiment_distribution"]["neutral"] = int(
            ((scores >= -0.1) & (scores <= 0.1)).sum()
        )
        summary["sentiment_distribution"]["negative"] = int((scores < -0.1).sum())
        if not scores.empty:
            summary["average_sentiment"] = round(float(scores.mean()), 4)

    # Top positive and negative players
    if "sentiment_multiplier" in df.columns and "player_name" in df.columns:
        sorted_df = df.sort_values("sentiment_multiplier", ascending=False)
        for _, row in sorted_df.head(5).iterrows():
            mult = float(row.get("sentiment_multiplier", 1.0))
            if mult > 1.0:
                summary["top_positive"].append(
                    {
                        "player_id": str(row.get("player_id", "")),
                        "player_name": str(row.get("player_name", "")),
                        "sentiment_multiplier": mult,
                        "doc_count": int(row.get("doc_count", 0)),
                    }
                )

        sorted_df_neg = df.sort_values("sentiment_multiplier", ascending=True)
        for _, row in sorted_df_neg.head(5).iterrows():
            mult = float(row.get("sentiment_multiplier", 1.0))
            if mult < 1.0:
                summary["top_negative"].append(
                    {
                        "player_id": str(row.get("player_id", "")),
                        "player_name": str(row.get("player_name", "")),
                        "sentiment_multiplier": mult,
                        "doc_count": int(row.get("doc_count", 0)),
                    }
                )

    # Advisor bullish/bearish lists — sorted by sentiment_score (not multiplier)
    # and use the simpler {player_name, team, sentiment_score} shape the
    # chat tool expects.
    if "sentiment_score_avg" in df.columns and "player_name" in df.columns:
        score_df = df.dropna(subset=["sentiment_score_avg"]).copy()
        if not score_df.empty:
            team_col = "team" if "team" in score_df.columns else None

            bullish_sorted = score_df.sort_values(
                "sentiment_score_avg", ascending=False
            ).head(5)
            for _, row in bullish_sorted.iterrows():
                score = float(row["sentiment_score_avg"])
                if score <= 0:
                    continue
                summary["bullish_players"].append(
                    {
                        "player_name": str(row.get("player_name", "")),
                        "team": (
                            str(row.get(team_col, ""))
                            if team_col and pd.notna(row.get(team_col))
                            else ""
                        ),
                        "sentiment_score": round(score, 4),
                    }
                )

            bearish_sorted = score_df.sort_values(
                "sentiment_score_avg", ascending=True
            ).head(5)
            for _, row in bearish_sorted.iterrows():
                score = float(row["sentiment_score_avg"])
                if score >= 0:
                    continue
                summary["bearish_players"].append(
                    {
                        "player_name": str(row.get("player_name", "")),
                        "team": (
                            str(row.get(team_col, ""))
                            if team_col and pd.notna(row.get(team_col))
                            else ""
                        ),
                        "sentiment_score": round(score, 4),
                    }
                )

    return summary
