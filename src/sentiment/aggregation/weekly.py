"""
Weekly sentiment aggregation — Silver → Gold for the NFL Sentiment Pipeline.

Reads all Silver signal JSON files for a given season/week, computes
per-player weighted-average sentiment with staleness decay, converts
scores to fantasy-projection multipliers, applies event flags, and
writes the result as a Parquet file to
``data/gold/sentiment/season=YYYY/week=WW/``.

The output is consumed directly by ``projection_engine.py`` as a final
adjustment layer on top of existing injury and Vegas multipliers.

Public API
----------
>>> aggregator = WeeklyAggregator()
>>> df = aggregator.aggregate(season=2026, week=1)
>>> df[["player_id", "sentiment_multiplier"]].head()
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.config import SENTIMENT_CONFIG

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_SILVER_SIGNALS_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "signals"
_GOLD_SENTIMENT_DIR = _PROJECT_ROOT / "data" / "gold" / "sentiment"

# Sentiment → multiplier linear mapping boundaries (from SENTIMENT_CONFIG)
_MULT_MIN, _MULT_MAX = SENTIMENT_CONFIG["sentiment_multiplier_range"]  # (0.70, 1.15)
_MULT_NEUTRAL = SENTIMENT_CONFIG["sentiment_multiplier_neutral"]  # 1.000

# Staleness threshold: signals older than this are excluded entirely.
_STALENESS_HOURS: float = SENTIMENT_CONFIG["staleness_hours"]  # 72

# Zero-out multiplier when a player is ruled out or inactive.
_MULTIPLIER_RULED_OUT = 0.0


# ---------------------------------------------------------------------------
# Helpers — score → multiplier conversion
# ---------------------------------------------------------------------------


def sentiment_to_multiplier(sentiment: float) -> float:
    """Convert a raw sentiment score to a projection multiplier.

    Uses a linear mapping:
      - sentiment = -1.0 → multiplier = _MULT_MIN (0.70)
      - sentiment =  0.0 → multiplier = _MULT_NEUTRAL (1.00)
      - sentiment = +1.0 → multiplier = _MULT_MAX (1.15)

    The piecewise approach handles asymmetric bounds gracefully.

    Args:
        sentiment: Float in [-1.0, +1.0].

    Returns:
        Multiplier float clamped to [_MULT_MIN, _MULT_MAX].

    Examples:
        >>> sentiment_to_multiplier(0.0)
        1.0
        >>> sentiment_to_multiplier(-1.0)
        0.7
        >>> sentiment_to_multiplier(1.0)
        1.15
    """
    sentiment = max(-1.0, min(1.0, float(sentiment)))

    if sentiment >= 0.0:
        # Map [0, +1] → [neutral, max]
        multiplier = _MULT_NEUTRAL + sentiment * (_MULT_MAX - _MULT_NEUTRAL)
    else:
        # Map [-1, 0] → [min, neutral]
        multiplier = _MULT_NEUTRAL + sentiment * (_MULT_NEUTRAL - _MULT_MIN)

    return round(max(_MULT_MIN, min(_MULT_MAX, multiplier)), 4)


def compute_staleness_weight(
    published_at: Optional[str],
    reference_time: Optional[datetime] = None,
    staleness_hours: float = _STALENESS_HOURS,
) -> float:
    """Compute a recency weight in [0.0, 1.0] based on signal age.

    Uses an exponential decay so that signals near the staleness boundary
    are weighted close to zero while fresh signals have weight 1.0.
    The decay half-life is set to staleness_hours / 3 so that at the
    boundary the weight is approximately 0.125.

    Signals older than ``staleness_hours`` are excluded entirely (weight 0.0).

    Args:
        published_at: ISO-8601 timestamp string of the signal's publication
            time.  None treated as current time (weight 1.0).
        reference_time: The "now" reference for age calculation.  Defaults
            to the current UTC time.
        staleness_hours: Maximum age in hours before a signal is excluded.

    Returns:
        Float weight in [0.0, 1.0].

    Examples:
        >>> compute_staleness_weight(None)  # fresh signal
        1.0
    """
    import math

    if not published_at:
        return 1.0

    if reference_time is None:
        reference_time = datetime.now(timezone.utc)

    try:
        if published_at.endswith("Z"):
            published_at = published_at[:-1] + "+00:00"
        pub_time = datetime.fromisoformat(published_at)
        if pub_time.tzinfo is None:
            pub_time = pub_time.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        logger.debug("Could not parse published_at '%s', using weight 1.0", published_at)
        return 1.0

    age_hours = (reference_time - pub_time).total_seconds() / 3600.0

    if age_hours >= staleness_hours:
        return 0.0

    # Exponential decay: half-life = staleness_hours / 3
    half_life = staleness_hours / 3.0
    weight = math.exp(-math.log(2) * age_hours / half_life)
    return max(0.0, min(1.0, weight))


# ---------------------------------------------------------------------------
# Aggregator
# ---------------------------------------------------------------------------


class WeeklyAggregator:
    """Aggregates Silver signals into Gold player-week sentiment features.

    Reads all Silver signal files for a season/week, groups by player,
    computes a staleness-decay-weighted average sentiment score, and
    converts it to a ``sentiment_multiplier`` for use in the projection
    engine.

    Event flags (is_ruled_out, is_inactive, etc.) are OR-aggregated across
    all signals: if any signal sets a flag, the aggregated row carries that
    flag.  ``is_ruled_out`` or ``is_inactive`` overrides the sentiment
    multiplier to 0.0.

    Example:
        >>> agg = WeeklyAggregator()
        >>> df = agg.aggregate(season=2026, week=1)
        >>> df.columns.tolist()
        ['player_id', 'player_name', 'sentiment_multiplier', ...]
    """

    def __init__(self) -> None:
        """Initialise the aggregator.

        Attributes:
            last_null_player_count: Count of records with player_id=None
                from the most recent ``aggregate()`` call. Reset to 0 at
                the start of every call (NOT cumulative). Phase 72 EVT-03
                contract — exposes the silent-drop count for telemetry.
        """
        self.last_null_player_count: int = 0

    # ------------------------------------------------------------------
    # Silver data loading
    # ------------------------------------------------------------------

    def _find_silver_files(self, season: int, week: int) -> List[Path]:
        """Find all Silver signal JSON files for a season/week.

        Args:
            season: NFL season year.
            week: NFL week number.

        Returns:
            List of Path objects sorted by modification time.
        """
        season_dir = _SILVER_SIGNALS_DIR / f"season={season}"
        week_dir = season_dir / f"week={week:02d}"

        files: List[Path] = []
        if week_dir.exists():
            files.extend(week_dir.glob("*.json"))
        # Also include flat season-level signal files
        if season_dir.exists():
            files.extend(f for f in season_dir.glob("*.json") if f.is_file())

        return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)

    def _load_silver_records(self, files: List[Path]) -> List[Dict[str, Any]]:
        """Load all signal records from a list of Silver JSON files.

        Args:
            files: List of paths to Silver signal JSON files.

        Returns:
            Flat list of individual signal record dicts.
        """
        all_records: List[Dict[str, Any]] = []

        for path in files:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Could not read Silver file %s: %s", path, exc)
                continue

            # Envelope format: {"records": [...]}
            if isinstance(data, dict):
                records = data.get("records", [])
            elif isinstance(data, list):
                records = data
            else:
                logger.warning("Unexpected format in %s", path)
                continue

            all_records.extend(r for r in records if isinstance(r, dict))

        logger.debug("Loaded %d Silver records from %d files", len(all_records), len(files))
        return all_records

    # ------------------------------------------------------------------
    # Per-player aggregation
    # ------------------------------------------------------------------

    def _aggregate_player_signals(
        self,
        records: List[Dict[str, Any]],
        reference_time: datetime,
    ) -> Dict[str, Dict[str, Any]]:
        """Group records by player_id and compute aggregated signal features.

        Only records with a resolved ``player_id`` contribute to the Gold
        layer.  Records without a ``player_id`` are included in count
        statistics but do not affect multiplier computation.

        Args:
            records: Flat list of Silver signal dicts.
            reference_time: UTC datetime used for staleness weight calculation.

        Returns:
            Dict mapping player_id → aggregated feature dict.
        """
        # Phase 72 EVT-03: count null-player records BEFORE filtering
        # so the silent-drop count is exposed via instance attr + INFO log.
        null_count = sum(1 for rec in records if not rec.get("player_id"))

        # Group by player_id (skip unresolved)
        by_player: Dict[str, List[Dict[str, Any]]] = {}
        for rec in records:
            pid = rec.get("player_id")
            if not pid:
                continue
            by_player.setdefault(pid, []).append(rec)

        # Phase 72: assign instance attr (overwrites prior call's count;
        # reset already happened at the top of aggregate()).
        self.last_null_player_count = null_count
        if null_count > 0:
            logger.info(
                "WeeklyAggregator: skipped %d records with player_id=null", null_count
            )

        result: Dict[str, Dict[str, Any]] = {}

        for player_id, player_records in by_player.items():
            result[player_id] = self._compute_player_aggregate(
                player_id, player_records, reference_time
            )

        return result

    def _compute_player_aggregate(
        self,
        player_id: str,
        records: List[Dict[str, Any]],
        reference_time: datetime,
    ) -> Dict[str, Any]:
        """Compute aggregated features for a single player.

        Args:
            player_id: Canonical player ID string.
            records: All Silver signal records for this player.
            reference_time: UTC datetime for staleness weight calculation.

        Returns:
            Dict of aggregated features including sentiment_multiplier.
        """
        # OR-aggregate event flags
        is_ruled_out = any(
            rec.get("events", {}).get("is_ruled_out", False) for rec in records
        )
        is_inactive = any(
            rec.get("events", {}).get("is_inactive", False) for rec in records
        )
        is_questionable = any(
            rec.get("events", {}).get("is_questionable", False) for rec in records
        )
        is_suspended = any(
            rec.get("events", {}).get("is_suspended", False) for rec in records
        )
        is_returning = any(
            rec.get("events", {}).get("is_returning", False) for rec in records
        )

        # If ruled out or inactive, multiplier is zero — skip score computation
        if is_ruled_out or is_inactive:
            sentiment_score_avg = None
            sentiment_score_max = None
            sentiment_score_min = None
            sentiment_multiplier = _MULTIPLIER_RULED_OUT
            total_weight = 0.0
        else:
            # Weighted average sentiment with confidence × recency weighting
            weighted_sum = 0.0
            total_weight = 0.0
            scores = []

            for rec in records:
                score = rec.get("sentiment_score")
                confidence = rec.get("sentiment_confidence", 0.5)
                published_at = rec.get("published_at")

                if score is None:
                    continue

                try:
                    score = float(score)
                    confidence = float(confidence)
                except (TypeError, ValueError):
                    continue

                staleness_w = compute_staleness_weight(
                    published_at, reference_time, _STALENESS_HOURS
                )
                if staleness_w == 0.0:
                    # Signal is too stale — skip
                    continue

                combined_weight = confidence * staleness_w
                weighted_sum += score * combined_weight
                total_weight += combined_weight
                scores.append(score)

            if total_weight > 0:
                sentiment_score_avg = round(weighted_sum / total_weight, 4)
            else:
                sentiment_score_avg = 0.0

            sentiment_score_max = round(max(scores), 4) if scores else None
            sentiment_score_min = round(min(scores), 4) if scores else None
            sentiment_multiplier = sentiment_to_multiplier(sentiment_score_avg)

        # Source breakdown
        source_counts: Dict[str, int] = {"rss": 0, "sleeper": 0, "official": 0, "twitter": 0}
        for rec in records:
            src = str(rec.get("source", "")).lower()
            for key in source_counts:
                if key in src:
                    source_counts[key] += 1
                    break

        # Latest signal timestamp
        timestamps = [
            rec.get("published_at")
            for rec in records
            if rec.get("published_at")
        ]
        latest_signal_at = max(timestamps) if timestamps else None

        # Player name: use most common occurrence
        names = [rec.get("player_name", "") for rec in records if rec.get("player_name")]
        player_name = max(set(names), key=names.count) if names else ""

        staleness_hours = None
        if latest_signal_at:
            try:
                ts_str = latest_signal_at
                if ts_str.endswith("Z"):
                    ts_str = ts_str[:-1] + "+00:00"
                latest_dt = datetime.fromisoformat(ts_str)
                if latest_dt.tzinfo is None:
                    latest_dt = latest_dt.replace(tzinfo=timezone.utc)
                staleness_hours = round(
                    (reference_time - latest_dt).total_seconds() / 3600.0, 1
                )
            except (ValueError, TypeError):
                pass

        return {
            "player_id": player_id,
            "player_name": player_name,
            "sentiment_multiplier": sentiment_multiplier,
            "sentiment_score_avg": sentiment_score_avg,
            "sentiment_score_max": sentiment_score_max,
            "sentiment_score_min": sentiment_score_min,
            "doc_count": len(records),
            "is_ruled_out": is_ruled_out,
            "is_inactive": is_inactive,
            "is_questionable": is_questionable,
            "is_suspended": is_suspended,
            "is_returning": is_returning,
            "rss_doc_count": source_counts["rss"],
            "sleeper_doc_count": source_counts["sleeper"],
            "official_report_count": source_counts["official"],
            "twitter_doc_count": source_counts["twitter"],
            "latest_signal_at": latest_signal_at,
            "signal_staleness_hours": staleness_hours,
        }

    # ------------------------------------------------------------------
    # Gold output
    # ------------------------------------------------------------------

    def _write_gold_parquet(
        self,
        df: pd.DataFrame,
        season: int,
        week: int,
    ) -> Path:
        """Write the aggregated DataFrame to a Gold Parquet file.

        Args:
            df: Aggregated player-week sentiment DataFrame.
            season: NFL season year.
            week: NFL week number.

        Returns:
            Path to the written Parquet file.
        """
        from datetime import datetime, timezone

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        output_dir = _GOLD_SENTIMENT_DIR / f"season={season}" / f"week={week:02d}"
        output_dir.mkdir(parents=True, exist_ok=True)

        output_path = output_dir / f"sentiment_multipliers_{ts}.parquet"
        df.to_parquet(output_path, index=False)
        logger.info(
            "Wrote Gold sentiment Parquet (%d rows) → %s", len(df), output_path
        )
        return output_path

    # ------------------------------------------------------------------
    # Public aggregate method
    # ------------------------------------------------------------------

    def aggregate(
        self,
        season: int,
        week: int,
        dry_run: bool = False,
        reference_time: Optional[datetime] = None,
    ) -> pd.DataFrame:
        """Aggregate Silver signals into Gold player-week sentiment features.

        Args:
            season: NFL season year (e.g. 2026).
            week: NFL week number (1–18).
            dry_run: If True, the Gold Parquet is not written to disk.
            reference_time: UTC datetime to use as "now" for staleness
                calculation.  Defaults to the current UTC time.

        Returns:
            DataFrame with one row per player.  Columns include:
            ``player_id``, ``player_name``, ``sentiment_multiplier``,
            ``sentiment_score_avg``, ``doc_count``, event flag booleans,
            and source-count columns.  Empty DataFrame if no signals found.
        """
        if reference_time is None:
            reference_time = datetime.now(timezone.utc)

        # Phase 72 EVT-03: reset the per-call null-player counter so it
        # reflects only THIS aggregate() call (not cumulative history).
        self.last_null_player_count = 0

        logger.info(
            "WeeklyAggregator: aggregating season=%d week=%d (dry_run=%s)",
            season,
            week,
            dry_run,
        )

        silver_files = self._find_silver_files(season, week)
        if not silver_files:
            logger.warning(
                "No Silver signal files found for season=%d week=%d", season, week
            )
            return pd.DataFrame()

        records = self._load_silver_records(silver_files)
        if not records:
            logger.warning("No signal records loaded for season=%d week=%d", season, week)
            return pd.DataFrame()

        player_aggregates = self._aggregate_player_signals(records, reference_time)
        if not player_aggregates:
            logger.warning(
                "No resolvable player signals for season=%d week=%d", season, week
            )
            return pd.DataFrame()

        df = pd.DataFrame(list(player_aggregates.values()))

        # Add season/week columns for partitioning context
        df["season"] = season
        df["week"] = week
        df["computed_at"] = datetime.now(timezone.utc).isoformat()

        # Enforce column order
        ordered_cols = [
            "player_id",
            "player_name",
            "season",
            "week",
            "sentiment_multiplier",
            "sentiment_score_avg",
            "sentiment_score_max",
            "sentiment_score_min",
            "doc_count",
            "is_ruled_out",
            "is_inactive",
            "is_questionable",
            "is_suspended",
            "is_returning",
            "rss_doc_count",
            "sleeper_doc_count",
            "official_report_count",
            "twitter_doc_count",
            "latest_signal_at",
            "signal_staleness_hours",
            "computed_at",
        ]
        existing = [c for c in ordered_cols if c in df.columns]
        df = df[existing]

        logger.info(
            "WeeklyAggregator: aggregated %d players, multiplier range [%.3f, %.3f]",
            len(df),
            df["sentiment_multiplier"].min(),
            df["sentiment_multiplier"].max(),
        )

        if not dry_run:
            self._write_gold_parquet(df, season, week)
        else:
            logger.info("Dry run: Gold Parquet not written")

        return df
