"""
Service layer for reading player news and sentiment data.

Supports two data tiers:
  1. Gold sentiment Parquet  -- aggregated per-player-week multipliers
  2. Silver signals JSON     -- individual news items with extracted fields
  3. Bronze documents JSON   -- raw documents for body text snippets

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
        logger.debug(
            "Loaded %d Gold sentiment rows from %s", len(df), parquet_path
        )
        return df
    except Exception as exc:
        logger.warning("Could not read Gold sentiment parquet %s: %s", parquet_path, exc)
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


# ---------------------------------------------------------------------------
# Bronze document helpers
# ---------------------------------------------------------------------------


def _find_bronze_files(season: int, week: int) -> List[Path]:
    """Find Bronze document JSON files for a season/week.

    Searches both the week-scoped directory and common source-level dirs
    (rss/, sleeper/) in the bronze sentiment tree.

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        List of Path objects, newest first.
    """
    files: List[Path] = []
    week_dir = _BRONZE_SENTIMENT_DIR / f"season={season}" / f"week={week:02d}"
    if week_dir.exists():
        files.extend(week_dir.glob("*.json"))

    # Source-level directories (rss, sleeper) may not be week-partitioned
    for source_dir in _BRONZE_SENTIMENT_DIR.glob("*/"):
        if source_dir.is_dir() and source_dir.name not in ("season=*",):
            files.extend(source_dir.glob(f"*season={season}*week={week}*.json"))
            files.extend(source_dir.glob(f"*{season}*{week:02d}*.json"))

    return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)


def _load_bronze_records(files: List[Path]) -> List[Dict[str, Any]]:
    """Load Bronze document records from a list of JSON files.

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
            if "documents" in data:
                records.extend(
                    r for r in data["documents"] if isinstance(r, dict)
                )
            else:
                records.append(data)

    return records


def _bronze_body_index(season: int, week: int) -> Dict[str, str]:
    """Build a mapping of external_id → body_snippet from Bronze documents.

    Args:
        season: NFL season year.
        week: NFL week number.

    Returns:
        Dict mapping external_id to first 200 chars of body_text.
    """
    files = _find_bronze_files(season, week)
    if not files:
        return {}

    index: Dict[str, str] = {}
    for rec in _load_bronze_records(files):
        ext_id = rec.get("external_id") or rec.get("id")
        body = rec.get("body_text") or rec.get("body") or ""
        if ext_id and body:
            index[str(ext_id)] = body[:200]

    return index


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_player_news(
    player_id: str,
    season: int,
    week: int,
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Return recent Silver news items for a specific player.

    Reads Silver signal records and filters to those referencing *player_id*.
    Falls back to an empty list when no data is available.

    Args:
        player_id: Canonical player ID.
        season: NFL season year.
        week: NFL week number.
        limit: Maximum number of items to return.

    Returns:
        List of news item dicts ordered newest first.
    """
    silver_files = _find_silver_files(season, week)
    if not silver_files:
        logger.debug("No Silver signal files for season=%d week=%d", season, week)
        return []

    records = _load_silver_records(silver_files)
    body_index = _bronze_body_index(season, week)

    player_records = [
        r for r in records if r.get("player_id") == player_id
    ]

    # Sort newest first
    player_records.sort(
        key=lambda r: r.get("published_at") or "", reverse=True
    )
    player_records = player_records[:limit]

    items: List[Dict[str, Any]] = []
    for rec in player_records:
        events: Dict[str, Any] = rec.get("events") or {}
        ext_id = rec.get("external_id") or rec.get("doc_id") or rec.get("id")
        body_snippet = body_index.get(str(ext_id)) if ext_id else None

        items.append(
            {
                "doc_id": ext_id,
                "title": rec.get("title"),
                "source": rec.get("source", "unknown"),
                "url": rec.get("url"),
                "published_at": rec.get("published_at"),
                "sentiment": rec.get("sentiment_score"),
                "category": rec.get("category"),
                "player_id": rec.get("player_id"),
                "player_name": rec.get("player_name"),
                "is_ruled_out": bool(events.get("is_ruled_out", False)),
                "is_inactive": bool(events.get("is_inactive", False)),
                "is_questionable": bool(events.get("is_questionable", False)),
                "is_suspended": bool(events.get("is_suspended", False)),
                "is_returning": bool(events.get("is_returning", False)),
                "body_snippet": body_snippet,
            }
        )

    return items


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
                "team": None,
                "position": None,
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
        "latest_signal_at": str(row.get("latest_signal_at"))
        if row.get("latest_signal_at")
        else None,
        "signal_staleness_hours": _safe_float(staleness),
    }
