"""
End-to-end Silver processing pipeline for the NFL Sentiment Pipeline.

Reads Bronze JSON documents from ``data/bronze/sentiment/{source}/``,
filters to unprocessed documents, runs Claude extraction, resolves
player names to canonical IDs, and writes Silver signals to
``data/silver/sentiment/signals/``.

Processed document IDs are tracked in ``data/silver/sentiment/processed_ids.json``
to avoid redundant API calls across pipeline runs.

Public API
----------
>>> pipeline = SentimentPipeline()
>>> result = pipeline.run(season=2026, week=1)
>>> result.processed_count, result.signal_count
(12, 47)
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from src.config import SENTIMENT_CONFIG, SENTIMENT_LOCAL_DIRS
from src.player_name_resolver import PlayerNameResolver
from src.sentiment.processing.extractor import ClaudeExtractor, PlayerSignal
from src.sentiment.processing.rule_extractor import RuleExtractor

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent

_SILVER_SIGNALS_DIR = _PROJECT_ROOT / "data" / "silver" / "sentiment" / "signals"
_PROCESSED_IDS_FILE = (
    _PROJECT_ROOT / "data" / "silver" / "sentiment" / "processed_ids.json"
)


# ---------------------------------------------------------------------------
# Result data class
# ---------------------------------------------------------------------------


@dataclass
class PipelineResult:
    """Summary of a single pipeline run.

    Attributes:
        processed_count: Number of documents passed to Claude.
        skipped_count: Documents skipped because they were already processed.
        signal_count: Total PlayerSignal objects written to Silver.
        failed_count: Documents that raised an error during extraction.
        output_files: Paths to the Silver JSON files written.

    Claude-primary extensions (Plan 71-01, additive only — safe
    defaults preserve prior PipelineResult() call sites):
        claude_failed_count: Incremented when a claude_primary call
            raises or returns malformed JSON and the pipeline falls
            back to RuleExtractor for that single document.
        unresolved_player_count: Incremented when PlayerNameResolver
            returns None for a Claude-extracted player name.
        non_player_count: Number of items Claude returned with
            ``player_name = null`` (team-only or non-player signals).
        non_player_items: Captured non-player items for the Phase 72
            attribution logic (logged under
            ``data/silver/sentiment/non_player_pending/``).
        is_claude_primary: True when the active extractor mode is
            ``claude_primary``; consumed by ``enrich_silver_records``
            as an early-return signal.
        cost_usd_total: Running USD cost total for the batched calls
            in this run (written by Plan 71-03).
    """

    processed_count: int = 0
    skipped_count: int = 0
    signal_count: int = 0
    failed_count: int = 0
    output_files: List[Path] = field(default_factory=list)
    # Plan 71-01 additive fields (safe defaults — zero-like / empty).
    claude_failed_count: int = 0
    unresolved_player_count: int = 0
    non_player_count: int = 0
    non_player_items: List[Dict[str, Any]] = field(default_factory=list)
    is_claude_primary: bool = False
    cost_usd_total: float = 0.0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class SentimentPipeline:
    """End-to-end Bronze → Silver sentiment extraction pipeline.

    Reads all Bronze JSON files from the local sentiment directories,
    runs extraction on each unprocessed document, resolves player names
    via ``PlayerNameResolver``, and writes Silver signal files.

    Supports three extractor modes:
    - ``"auto"`` (default): Uses Claude if ``ANTHROPIC_API_KEY`` is set,
      otherwise falls back to the rule-based extractor.
    - ``"rule"``: Always uses the rule-based extractor.
    - ``"claude"``: Always uses the Claude extractor (fails if no API key).

    Attributes:
        _extractor: The active extractor instance (Claude or rule-based).
        resolver: ``PlayerNameResolver`` instance for name → player_id mapping.
        _processed_ids: Set of document IDs already processed in prior runs.

    Example:
        >>> pipeline = SentimentPipeline()
        >>> result = pipeline.run(season=2026, week=1)
        >>> print(result.signal_count)
        42
    """

    def __init__(
        self,
        extractor: Optional[Any] = None,
        resolver: Optional[PlayerNameResolver] = None,
        extractor_mode: str = "auto",
    ) -> None:
        """Initialise the pipeline with optional dependency injection.

        Args:
            extractor: Pre-built extractor instance.  If provided,
                ``extractor_mode`` is ignored.
            resolver: PlayerNameResolver instance.  A new one is created if
                not provided.
            extractor_mode: One of ``"auto"``, ``"rule"``, ``"claude"``.
                Controls which extractor is used when ``extractor`` is None.
        """
        if extractor is not None:
            self._extractor = extractor
        else:
            self._extractor = self._build_extractor(extractor_mode)
        # Keep backward-compatible attribute name
        self.extractor = self._extractor
        self.resolver = resolver or PlayerNameResolver()
        self._processed_ids: Set[str] = self._load_processed_ids()

    @staticmethod
    def _build_extractor(mode: str) -> Any:
        """Instantiate the appropriate extractor based on mode.

        Args:
            mode: ``"auto"``, ``"rule"``, or ``"claude"``.

        Returns:
            An extractor instance with ``.extract()`` and ``.is_available``.
        """
        if mode == "rule":
            logger.info("Using rule-based extractor (forced by mode='rule')")
            return RuleExtractor()
        elif mode == "claude":
            # Opt-in override for legacy callers / comparison tests.
            # Production code paths should use the default (auto) mode.
            logger.info("Using Claude extractor (forced by mode='claude')")
            return ClaudeExtractor()
        else:
            # Auto mode: always use rules per Phase 61 D-02.
            # The rule-based path is the authoritative model-facing
            # extractor; Claude stays in the repo only as the optional
            # website enrichment path (see src.sentiment.enrichment).
            logger.info(
                "Using rule-based extractor in auto mode "
                "(Phase 61 D-02: rules are primary, LLM is optional enrichment "
                "via src.sentiment.enrichment)."
            )
            return RuleExtractor()

    # ------------------------------------------------------------------
    # ID tracking
    # ------------------------------------------------------------------

    def _load_processed_ids(self) -> Set[str]:
        """Load the set of already-processed document IDs from disk.

        Returns:
            Set of string document IDs.  Empty set if the file does not
            exist yet.
        """
        if not _PROCESSED_IDS_FILE.exists():
            return set()
        try:
            data = json.loads(_PROCESSED_IDS_FILE.read_text(encoding="utf-8"))
            return set(data if isinstance(data, list) else [])
        except Exception as exc:
            logger.warning("Could not load processed IDs file: %s", exc)
            return set()

    def _save_processed_ids(self) -> None:
        """Persist the current processed-IDs set to disk.

        Creates the parent directory if it does not exist.
        """
        _PROCESSED_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
        _PROCESSED_IDS_FILE.write_text(
            json.dumps(sorted(self._processed_ids), indent=2),
            encoding="utf-8",
        )

    # ------------------------------------------------------------------
    # Bronze document loading
    # ------------------------------------------------------------------

    def _find_bronze_files(self, season: int, week: Optional[int]) -> List[Path]:
        """Discover all Bronze sentiment JSON files for a given season/week.

        Searches every source directory under ``data/bronze/sentiment/``.
        Files are sorted by modification time so that newer sources are
        processed first.

        Args:
            season: NFL season year (e.g. 2026).
            week: Optional week number.  If None, all weeks for the season
                are included.

        Returns:
            Sorted list of Path objects pointing to Bronze JSON files.
        """
        files: List[Path] = []

        for source, dir_str in SENTIMENT_LOCAL_DIRS.items():
            base_dir = _PROJECT_ROOT / dir_str
            if not base_dir.exists():
                logger.debug("Bronze dir not found, skipping: %s", base_dir)
                continue

            season_dir = base_dir / f"season={season}"
            if not season_dir.exists():
                logger.debug("Season dir not found: %s", season_dir)
                continue

            if week is not None:
                # Week-specific directory (e.g. season=2026/week=01/)
                week_dir = season_dir / f"week={week:02d}"
                if week_dir.exists():
                    files.extend(week_dir.glob("*.json"))
                # Also check flat season-level files (some sources use season= only)
                files.extend(season_dir.glob("*.json"))
            else:
                # Collect all JSON files under the season directory
                files.extend(season_dir.rglob("*.json"))

        return sorted(set(files), key=lambda p: p.stat().st_mtime, reverse=True)

    def _load_bronze_file(self, path: Path) -> List[Dict[str, Any]]:
        """Load and parse a Bronze JSON file, returning the list of items.

        Supports both envelope format ``{"items": [...]}`` and bare array
        ``[...]``.

        Args:
            path: Path to the Bronze JSON file.

        Returns:
            List of document dicts.  Empty list on parse error.
        """
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.error("Failed to read Bronze file %s: %s", path, exc)
            return []

        if isinstance(raw, list):
            return raw
        if isinstance(raw, dict):
            items = raw.get("items", [])
            if isinstance(items, list):
                return items
            logger.warning("Bronze file %s has unexpected structure", path)
            return []

        logger.warning("Bronze file %s: top-level type is %s", path, type(raw).__name__)
        return []

    # ------------------------------------------------------------------
    # Silver output writing
    # ------------------------------------------------------------------

    def _build_silver_record(
        self,
        doc: Dict[str, Any],
        signal: PlayerSignal,
        player_id: Optional[str],
        season: int,
        week: Optional[int],
        source: str,
    ) -> Dict[str, Any]:
        """Assemble a Silver signal record for a single player mention.

        Args:
            doc: The original Bronze document dict.
            signal: Extracted ``PlayerSignal`` from Claude.
            player_id: Resolved canonical player ID, or None if unresolved.
            season: NFL season year.
            week: NFL week number, or None for season-level signals.
            source: Source identifier string (e.g. "rss_espn").

        Returns:
            Dict ready for JSON serialisation.
        """
        return {
            "signal_id": str(uuid.uuid4()),
            "doc_id": doc.get("external_id") or doc.get("id", ""),
            "source": source or doc.get("source", ""),
            "season": season,
            "week": week,
            "player_name": signal.player_name,
            "player_id": player_id,
            "sentiment_score": round(signal.sentiment, 4),
            "sentiment_confidence": round(signal.confidence, 4),
            "category": signal.category,
            "events": {
                # Injury events
                "is_ruled_out": signal.is_ruled_out,
                "is_inactive": signal.is_inactive,
                "is_questionable": signal.is_questionable,
                "is_suspended": signal.is_suspended,
                "is_returning": signal.is_returning,
                # Transaction events (Plan 61-02)
                "is_traded": signal.is_traded,
                "is_released": signal.is_released,
                "is_signed": signal.is_signed,
                "is_activated": signal.is_activated,
                # Usage events (Plan 61-02)
                "is_usage_boost": signal.is_usage_boost,
                "is_usage_drop": signal.is_usage_drop,
                # Weather events (Plan 61-02)
                "is_weather_risk": signal.is_weather_risk,
            },
            "published_at": doc.get("published_at"),
            "extracted_at": datetime.now(timezone.utc).isoformat(),
            "model_version": type(self._extractor).__name__,
            "raw_excerpt": signal.raw_excerpt,
            # Plan 71-01 additive top-level keys. ``extractor`` defaults
            # to "rule" via PlayerSignal, so existing rule-based runs
            # emit the field without behavioural change. Downstream
            # consumers (enrich_silver_records, WeeklyAggregator) may
            # ignore these keys; they are purely additive.
            "extractor": signal.extractor,
            "summary": signal.summary,
        }

    def _write_silver_file(
        self,
        records: List[Dict[str, Any]],
        season: int,
        week: Optional[int],
        batch_id: str,
    ) -> Optional[Path]:
        """Write Silver signal records to a JSON file.

        The file is stored under ``data/silver/sentiment/signals/season=YYYY/``
        (and ``week=WW/`` if week is given).

        Args:
            records: List of Silver signal dicts to write.
            season: NFL season year (used for directory partitioning).
            week: Optional week number (used for sub-directory).
            batch_id: Unique run identifier used in the filename.

        Returns:
            Path to the written file, or None if records is empty.
        """
        if not records:
            return None

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        season_dir = _SILVER_SIGNALS_DIR / f"season={season}"
        if week is not None:
            output_dir = season_dir / f"week={week:02d}"
        else:
            output_dir = season_dir

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"signals_{batch_id}_{ts}.json"

        envelope = {
            "batch_id": batch_id,
            "season": season,
            "week": week,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "signal_count": len(records),
            "records": records,
        }
        output_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        logger.info("Wrote %d Silver signals → %s", len(records), output_path)
        return output_path

    # ------------------------------------------------------------------
    # Core processing
    # ------------------------------------------------------------------

    def _process_doc(
        self,
        doc: Dict[str, Any],
        season: int,
        week: Optional[int],
        source: str,
    ) -> List[Dict[str, Any]]:
        """Extract signals from a single Bronze document and resolve player IDs.

        Args:
            doc: Bronze document dict.
            season: NFL season year.
            week: Optional NFL week number.
            source: Source identifier (e.g. "rss_espn").

        Returns:
            List of Silver record dicts (one per resolved player mention).
        """
        signals = self.extractor.extract(doc)
        if not signals:
            return []

        records: List[Dict[str, Any]] = []
        for signal in signals:
            player_id = self.resolver.resolve(signal.player_name)
            if player_id is None:
                logger.debug(
                    "Could not resolve player '%s' — signal included without ID",
                    signal.player_name,
                )
            record = self._build_silver_record(
                doc=doc,
                signal=signal,
                player_id=player_id,
                season=season,
                week=week,
                source=source,
            )
            records.append(record)

        return records

    def _get_doc_id(self, doc: Dict[str, Any]) -> str:
        """Extract a stable deduplication ID from a Bronze document.

        Args:
            doc: Bronze document dict.

        Returns:
            String ID suitable for tracking in the processed-IDs set.
        """
        return str(
            doc.get("external_id")
            or doc.get("id")
            or f"{doc.get('source','')}:{doc.get('url','')}"
        )

    # ------------------------------------------------------------------
    # Public run method
    # ------------------------------------------------------------------

    def run(
        self,
        season: int,
        week: Optional[int] = None,
        dry_run: bool = False,
    ) -> PipelineResult:
        """Execute the full Bronze → Silver extraction pipeline.

        Steps:
        1. Discover all Bronze JSON files for the given season/week.
        2. Load documents from each file.
        3. Skip documents whose IDs are in the processed-IDs set.
        4. Run Claude extraction on each unprocessed document.
        5. Resolve player names to canonical IDs.
        6. Write Silver signal records to disk (unless ``dry_run``).
        7. Update the processed-IDs tracking file.

        Args:
            season: NFL season year (e.g. 2026).
            week: Optional NFL week number.  If None, all weeks for the
                season are processed.
            dry_run: If True, extraction and resolution run normally but
                no files are written to disk.

        Returns:
            ``PipelineResult`` summarising the run.
        """
        result = PipelineResult()
        batch_id = str(uuid.uuid4())[:8]
        all_records: List[Dict[str, Any]] = []

        logger.info(
            "SentimentPipeline: starting season=%d week=%s batch=%s (dry_run=%s)",
            season,
            week,
            batch_id,
            dry_run,
        )

        bronze_files = self._find_bronze_files(season, week)
        logger.info("Found %d Bronze files to scan", len(bronze_files))

        for bronze_file in bronze_files:
            docs = self._load_bronze_file(bronze_file)
            if not docs:
                continue

            # Infer source from file path
            source = self._infer_source(bronze_file)

            for doc in docs:
                doc_id = self._get_doc_id(doc)

                if doc_id in self._processed_ids:
                    result.skipped_count += 1
                    logger.debug("Skipping already-processed doc: %s", doc_id)
                    continue

                try:
                    records = self._process_doc(doc, season, week, source)
                    all_records.extend(records)
                    result.processed_count += 1
                    result.signal_count += len(records)
                    self._processed_ids.add(doc_id)
                except Exception as exc:
                    logger.error(
                        "Error processing doc %s: %s", doc_id, exc, exc_info=True
                    )
                    result.failed_count += 1

        logger.info(
            "Extraction complete: %d processed, %d skipped, %d failed, %d signals",
            result.processed_count,
            result.skipped_count,
            result.failed_count,
            result.signal_count,
        )

        if not dry_run and all_records:
            output_path = self._write_silver_file(all_records, season, week, batch_id)
            if output_path:
                result.output_files.append(output_path)
            self._save_processed_ids()
        elif dry_run:
            logger.info("Dry run: %d records would be written", len(all_records))
        else:
            logger.info("No new signals to write")

        return result

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _infer_source(self, path: Path) -> str:
        """Infer a source identifier string from a Bronze file path.

        Args:
            path: Path to the Bronze JSON file.

        Returns:
            Source string (e.g. "rss", "sleeper", "official").
        """
        for part in path.parts:
            if part in SENTIMENT_LOCAL_DIRS:
                return part
        # Fallback: use the immediate parent directory name
        return path.parent.name
