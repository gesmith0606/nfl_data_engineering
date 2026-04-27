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

Plan 71-04 extensions:
- ``extractor_mode="claude_primary"`` activates the batched primary
  Claude extractor (`extract_batch_primary`) with per-doc soft fallback
  to RuleExtractor on API errors. EXTRACTOR_MODE env can drive the
  same selection when the constructor arg defaults to ``"auto"``;
  explicit constructor args win over the env. Roster names are loaded
  lazily from the latest ``data/bronze/players/rosters/season=YYYY/``
  parquet for prompt-cache injection. Non-player items and Claude-named
  unresolved players are persisted to dedicated Silver sinks.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

from src.config import SENTIMENT_CONFIG, SENTIMENT_LOCAL_DIRS
from src.player_name_resolver import PlayerNameResolver
from src.sentiment.processing.cost_log import CostLog
from src.sentiment.processing.extractor import (
    BATCH_SIZE,
    ClaudeClient,
    ClaudeExtractor,
    PlayerSignal,
    _EXTRACTOR_NAME_CLAUDE_PRIMARY,
)
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
# New sinks introduced by Plan 71-04 (Task 2). Tests monkeypatch these
# alongside ``_SILVER_SIGNALS_DIR`` for hermetic tmp-tree runs.
_UNRESOLVED_DIR = (
    _PROJECT_ROOT / "data" / "silver" / "sentiment" / "unresolved_names"
)
_NON_PLAYER_DIR = (
    _PROJECT_ROOT / "data" / "silver" / "sentiment" / "non_player_pending"
)
# Plan 72-03 Task 1 — new Silver sink for hybrid attribution per CONTEXT D-02.
# Non-player items routed by ``_route_non_player_items`` whose ``subject_type``
# is in ``_NEWS_CHANNEL_SUBJECT_TYPES`` land here; the team aggregator merges
# the counts into ``coach_news_count`` / ``team_news_count`` columns.
_NON_PLAYER_NEWS_DIR = (
    _PROJECT_ROOT / "data" / "silver" / "sentiment" / "non_player_news"
)

# Plan 72-03 Task 1 — locked routing buckets per CONTEXT D-02:
# * Coach + team subjects roll up to the team rollup table (coach/team
#   news counts surfaced by ``TeamWeeklyAggregator``).
# * Coach + team + reporter subjects all write to the new
#   ``non_player_news`` Silver sink so the news-feed surface (Wave 4)
#   can show them. Reporters skip the team rollup because reporters
#   cover multiple teams and would inflate per-team news counts.
_TEAM_ROLLUP_SUBJECT_TYPES = frozenset({"coach", "team"})
_NEWS_CHANNEL_SUBJECT_TYPES = frozenset({"coach", "team", "reporter"})

# Valid extractor mode strings accepted by ``SentimentPipeline``. EXTRACTOR_MODE
# env values outside this set fall through to ``auto`` with an INFO log
# (CONTEXT.md T-71-04-01 mitigation: tampering with the env yields the safe
# default rather than an exception).
_VALID_MODES = frozenset(
    {"auto", "rule", "claude", _EXTRACTOR_NAME_CLAUDE_PRIMARY}
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
    # Plan 72-03 Task 1 additive fields — hybrid routing counters.
    # ``non_player_routed_count`` = items routed to the team rollup
    # (subject_type in {coach, team}). ``non_player_news_count`` = items
    # routed to the new ``non_player_news`` Silver sink (subject_type in
    # {coach, team, reporter}). Both ACCUMULATE via += across the
    # ``_run_claude_primary_loop`` per-batch body — see Test 7
    # (test_routing_counters_accumulate_across_batches).
    non_player_routed_count: int = 0
    non_player_news_count: int = 0
    # Plan 72-03 Task 2 additive field — null-player aggregator counter
    # surfaced via ``WeeklyAggregator.last_null_player_count`` and
    # plumbed here for ops dashboards. Defaults 0 — populated by the
    # caller when running aggregation in the same flow as the pipeline.
    null_player_count: int = 0


# ---------------------------------------------------------------------------
# Pipeline
# ---------------------------------------------------------------------------


class SentimentPipeline:
    """End-to-end Bronze → Silver sentiment extraction pipeline.

    Reads all Bronze JSON files from the local sentiment directories,
    runs extraction on each unprocessed document, resolves player names
    via ``PlayerNameResolver``, and writes Silver signal files.

    Supports four extractor modes:
    - ``"auto"`` (default): Uses the rule-based extractor (Phase 61 D-02).
      EXTRACTOR_MODE env var can override this default to ``claude_primary``
      when set; explicit constructor args always win over env.
    - ``"rule"``: Always uses the rule-based extractor.
    - ``"claude"``: Always uses the legacy single-doc Claude extractor.
    - ``"claude_primary"``: Plan 71-04 — batched Claude primary path with
      per-doc soft fallback to RuleExtractor on API errors.

    Attributes:
        _extractor: The active extractor instance (Claude or rule-based).
        _rule_fallback: RuleExtractor used when claude_primary batches
            raise. Constructed only when ``_is_claude_primary`` is True.
        _is_claude_primary: True when the effective mode is ``claude_primary``.
            Drives the ``run()`` control flow and the Silver envelope flag.
        _claude_client: Injected ``ClaudeClient`` (or None for env-driven
            client construction inside ``ClaudeExtractor``).
        _cost_log: ``CostLog`` instance used by claude_primary calls. Always
            non-None — defaults to ``CostLog()`` (real partition path).
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
        cost_log: Optional[CostLog] = None,
        claude_client: Optional[ClaudeClient] = None,
    ) -> None:
        """Initialise the pipeline with optional dependency injection.

        Args:
            extractor: Pre-built extractor instance.  If provided,
                ``extractor_mode`` is ignored.
            resolver: PlayerNameResolver instance.  A new one is created if
                not provided.
            extractor_mode: One of ``"auto"``, ``"rule"``, ``"claude"``,
                ``"claude_primary"``. Controls which extractor is used when
                ``extractor`` is None.
            cost_log: Optional ``CostLog`` instance for claude_primary cost
                accounting. When ``None``, a default ``CostLog()`` is built
                (writes to the real ``data/ops/llm_costs/`` partition).
            claude_client: Optional ``ClaudeClient``-Protocol-compatible
                object (real ``anthropic.Anthropic`` instance, or a test
                double like ``FakeClaudeClient``). Wins over env-driven
                client construction inside ``ClaudeExtractor``.
        """
        self._claude_client: Optional[ClaudeClient] = claude_client
        self._cost_log: CostLog = cost_log if cost_log is not None else CostLog()

        # Resolve the effective mode before building the extractor so the
        # env-precedence logic is consolidated in one place.
        effective_mode = self._resolve_extractor_mode(extractor_mode)
        self._is_claude_primary = (
            effective_mode == _EXTRACTOR_NAME_CLAUDE_PRIMARY
        )

        if extractor is not None:
            self._extractor = extractor
        else:
            self._extractor = self._build_extractor(effective_mode)
        # Keep backward-compatible attribute name
        self.extractor = self._extractor

        # Per-doc soft fallback companion (Task 2). Always RuleExtractor —
        # cheap to instantiate, no API key required.
        self._rule_fallback: Optional[RuleExtractor] = (
            RuleExtractor() if self._is_claude_primary else None
        )

        self.resolver = resolver or PlayerNameResolver()
        self._processed_ids: Set[str] = self._load_processed_ids()

    # ------------------------------------------------------------------
    # Mode resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_extractor_mode(arg_mode: str) -> str:
        """Resolve the effective extractor mode from arg + EXTRACTOR_MODE env.

        Precedence:
            1. Explicit constructor arg (anything other than ``"auto"``)
               wins over env.
            2. When constructor arg is the default ``"auto"``, the
               EXTRACTOR_MODE env var (if set to a valid mode string)
               takes effect.
            3. Otherwise, ``"auto"`` is used.

        Unknown env values fall back to ``"auto"`` with an INFO log
        (T-71-04-01 — tampering mitigation).

        Args:
            arg_mode: The constructor argument value.

        Returns:
            The effective mode string used to build the extractor.
        """
        if arg_mode != "auto":
            if arg_mode in _VALID_MODES:
                return arg_mode
            logger.info(
                "SentimentPipeline: extractor_mode=%r unknown; "
                "falling back to 'auto'.",
                arg_mode,
            )
            return "auto"

        env_mode = os.environ.get("EXTRACTOR_MODE", "").strip()
        if env_mode and env_mode in _VALID_MODES:
            logger.info(
                "SentimentPipeline: EXTRACTOR_MODE env override active: %s",
                env_mode,
            )
            return env_mode
        if env_mode:
            logger.info(
                "SentimentPipeline: EXTRACTOR_MODE=%r is not a valid mode; "
                "falling back to 'auto'.",
                env_mode,
            )
        return "auto"

    def _build_extractor(self, mode: str) -> Any:
        """Instantiate the appropriate extractor based on mode.

        Args:
            mode: ``"auto"``, ``"rule"``, ``"claude"``, or ``"claude_primary"``.

        Returns:
            An extractor instance. For ``"claude_primary"``, a
            ``ClaudeExtractor`` configured with the DI'd client, cost log,
            roster provider, and ``BATCH_SIZE``. When the claude_primary
            path is requested but no client is available (no DI'd client
            and no ``ANTHROPIC_API_KEY``), the pipeline falls back to
            ``RuleExtractor`` (fail-open per CONTEXT D-02) and clears
            ``_is_claude_primary`` so the run loop uses the legacy path.
        """
        if mode == "rule":
            logger.info("Using rule-based extractor (forced by mode='rule')")
            return RuleExtractor()
        elif mode == "claude":
            # Opt-in override for legacy callers / comparison tests.
            # Production code paths should use the default (auto) mode.
            logger.info("Using Claude extractor (forced by mode='claude')")
            return ClaudeExtractor(client=self._claude_client)
        elif mode == _EXTRACTOR_NAME_CLAUDE_PRIMARY:
            roster_provider = self._roster_provider_factory(
                season=datetime.now().year
            )
            extractor = ClaudeExtractor(
                client=self._claude_client,
                roster_provider=roster_provider,
                cost_log=self._cost_log,
                batch_size=BATCH_SIZE,
            )
            # H-02 fix: use the public is_available property instead of
            # crossing the class boundary to inspect ._client.
            if not extractor.is_available:
                logger.warning(
                    "claude_primary requested but no client available "
                    "(no ANTHROPIC_API_KEY and no DI'd client). "
                    "Falling back to RuleExtractor for this run."
                )
                # Clear the flag so the run loop takes the legacy path.
                self._is_claude_primary = False
                return RuleExtractor()
            logger.info("Using claude_primary extractor (batched, cached)")
            return extractor
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
    # Roster provider (Plan 71-04)
    # ------------------------------------------------------------------

    def _roster_provider_factory(
        self, season: int
    ) -> Callable[[], List[str]]:
        """Build a lazy callable that loads active roster names for a season.

        Reads the most recent parquet under
        ``data/bronze/players/rosters/season=YYYY/`` (resolved relative to
        ``_PROJECT_ROOT`` so tests can monkeypatch the project root).
        Fails open on every error — missing dir, missing file, missing
        column, parquet read error — by returning ``[]`` and logging a
        WARNING. The pipeline must NEVER raise from roster loading.

        Args:
            season: NFL season year.

        Returns:
            Zero-arg callable returning a list of player names (capped at
            1500 entries, sorted, deduplicated).
        """
        rosters_dir = (
            _PROJECT_ROOT
            / "data"
            / "bronze"
            / "players"
            / "rosters"
            / f"season={season}"
        )

        def _load() -> List[str]:
            try:
                if not rosters_dir.exists():
                    logger.warning(
                        "Roster dir not found: %s; claude_primary will run "
                        "without player hints.",
                        rosters_dir,
                    )
                    return []
                files = sorted(
                    rosters_dir.glob("*.parquet"),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                )
                if not files:
                    return []
                import pandas as pd

                df = pd.read_parquet(files[0])
                col: Optional[str]
                if "player_name" in df.columns:
                    col = "player_name"
                elif "full_name" in df.columns:
                    col = "full_name"
                else:
                    col = None
                if col is None:
                    logger.warning(
                        "Roster parquet has no player_name/full_name column; "
                        "returning []."
                    )
                    return []
                return sorted(
                    df[col].dropna().astype(str).unique().tolist()
                )[:1500]
            except Exception as exc:  # noqa: BLE001 — fail-open
                logger.warning(
                    "roster_provider: failed to load rosters (%s); returning [].",
                    exc,
                )
                return []

        return _load

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
        is_claude_primary: bool = False,
    ) -> Optional[Path]:
        """Write Silver signal records to a JSON file.

        The file is stored under ``data/silver/sentiment/signals/season=YYYY/``
        (and ``week=WW/`` if week is given).

        Args:
            records: List of Silver signal dicts to write.
            season: NFL season year (used for directory partitioning).
            week: Optional week number (used for sub-directory).
            batch_id: Unique run identifier used in the filename.
            is_claude_primary: When True, the envelope JSON gains an
                ``"is_claude_primary": true`` top-level key. Consumed by
                ``enrich_silver_records`` to skip already-summarised
                envelopes (Plan 71-04).

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

        envelope: Dict[str, Any] = {
            "batch_id": batch_id,
            "season": season,
            "week": week,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "signal_count": len(records),
            "records": records,
        }
        if is_claude_primary:
            envelope["is_claude_primary"] = True
        output_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        logger.info("Wrote %d Silver signals → %s", len(records), output_path)
        return output_path

    def _write_envelope(
        self,
        records: List[Dict[str, Any]],
        base_dir: Path,
        prefix: str,
        season: int,
        week: Optional[int],
        batch_id: str,
    ) -> Optional[Path]:
        """Write a generic JSON envelope to a partitioned directory.

        Used by the new unresolved-names and non-player-pending sinks
        introduced by Plan 71-04. Mirrors ``_write_silver_file`` layout
        (``season=YYYY/week=WW/`` partition + timestamped filename) but
        stays separate so the Silver signals envelope stays focused on
        player-attributed records.

        Args:
            records: List of dicts to write into ``records``.
            base_dir: Partition root (e.g. ``_NON_PLAYER_DIR``).
            prefix: Filename prefix (e.g. ``"non_player"``).
            season: NFL season year (partition).
            week: Optional NFL week number (partition).
            batch_id: Unique run identifier embedded in the filename.

        Returns:
            Path to the written file, or None when ``records`` is empty.
        """
        if not records:
            return None

        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        season_dir = base_dir / f"season={season}"
        if week is not None:
            output_dir = season_dir / f"week={week:02d}"
        else:
            output_dir = season_dir

        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = output_dir / f"{prefix}_{batch_id}_{ts}.json"

        envelope = {
            "batch_id": batch_id,
            "season": season,
            "week": week,
            "computed_at": datetime.now(timezone.utc).isoformat(),
            "record_count": len(records),
            "records": records,
        }
        output_path.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        logger.info(
            "Wrote %d %s records → %s", len(records), prefix, output_path
        )
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
        4. Run extraction (per-doc legacy path OR batched claude_primary path).
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
        result.is_claude_primary = self._is_claude_primary
        batch_id = str(uuid.uuid4())[:8]

        logger.info(
            "SentimentPipeline: starting season=%d week=%s batch=%s "
            "mode=%s (dry_run=%s)",
            season,
            week,
            batch_id,
            "claude_primary" if self._is_claude_primary else "legacy",
            dry_run,
        )

        bronze_files = self._find_bronze_files(season, week)
        logger.info("Found %d Bronze files to scan", len(bronze_files))

        if self._is_claude_primary:
            all_records, unresolved_records = self._run_claude_primary_loop(
                bronze_files, season, week, batch_id, result, dry_run
            )
        else:
            all_records = self._run_legacy_loop(
                bronze_files, season, week, result
            )
            unresolved_records = []

        logger.info(
            "Extraction complete: %d processed, %d skipped, %d failed, %d signals",
            result.processed_count,
            result.skipped_count,
            result.failed_count,
            result.signal_count,
        )

        if not dry_run and all_records:
            output_path = self._write_silver_file(
                all_records,
                season,
                week,
                batch_id,
                is_claude_primary=self._is_claude_primary,
            )
            if output_path:
                result.output_files.append(output_path)
            self._save_processed_ids()
        elif dry_run:
            logger.info("Dry run: %d records would be written", len(all_records))
        else:
            logger.info("No new signals to write")

        # Persist the unresolved-names sink (Task 2). Only the
        # claude_primary path populates this list; the legacy path leaves
        # it empty.
        if not dry_run and unresolved_records:
            self._write_envelope(
                unresolved_records,
                _UNRESOLVED_DIR,
                prefix="unresolved",
                season=season,
                week=week,
                batch_id=batch_id,
            )

        # Pull the running cost total from the cost log when claude_primary
        # was active. The cost log itself is the source of truth (the
        # extractor wrote one record per call).
        if self._is_claude_primary and week is not None:
            try:
                result.cost_usd_total = self._cost_log.running_total_usd(
                    season, week
                )
            except Exception as exc:  # noqa: BLE001 — never crash on accounting
                logger.warning(
                    "SentimentPipeline: cost_log.running_total_usd failed (%s)",
                    exc,
                )

        return result

    # ------------------------------------------------------------------
    # Run-loop branches
    # ------------------------------------------------------------------

    def _run_legacy_loop(
        self,
        bronze_files: List[Path],
        season: int,
        week: Optional[int],
        result: PipelineResult,
    ) -> List[Dict[str, Any]]:
        """Per-doc extraction loop preserved verbatim from pre-Plan-71-04.

        This is the path taken for ``"auto"`` / ``"rule"`` / ``"claude"``
        modes. Behaviour is byte-identical to the prior implementation —
        any change here MUST be reflected in
        ``test_daily_pipeline_resilience.py`` and other regression tests.

        Args:
            bronze_files: List of Bronze JSON paths.
            season: NFL season year.
            week: Optional NFL week.
            result: ``PipelineResult`` mutated in place.

        Returns:
            List of Silver record dicts ready for ``_write_silver_file``.
        """
        all_records: List[Dict[str, Any]] = []

        for bronze_file in bronze_files:
            docs = self._load_bronze_file(bronze_file)
            if not docs:
                continue

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
                        "Error processing doc %s: %s",
                        doc_id,
                        exc,
                        exc_info=True,
                    )
                    result.failed_count += 1

        return all_records

    def _run_claude_primary_loop(
        self,
        bronze_files: List[Path],
        season: int,
        week: Optional[int],
        batch_id: str,
        result: PipelineResult,
        dry_run: bool,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Batched Claude-primary extraction loop with per-doc soft fallback.

        Steps:
        1. Collect all unprocessed docs across every Bronze file.
        2. Slice into ``BATCH_SIZE`` chunks.
        3. For each batch, call ``extract_batch_primary``.
            * On success: convert each item via ``_build_silver_record``.
            * On API error: fall back to ``RuleExtractor`` per doc and bump
              ``result.claude_failed_count`` by the batch size.
        4. After all batches, persist the non-player-pending envelope.

        Args:
            bronze_files: List of Bronze JSON paths.
            season: NFL season year.
            week: Optional NFL week (used for cost-log partition; passed
                as ``0`` to ``extract_batch_primary`` when ``None``).
            batch_id: Run-level batch identifier (passed to envelope writes).
            result: ``PipelineResult`` mutated in place.
            dry_run: If True, no envelopes are written for any sink.

        Returns:
            Tuple ``(all_records, unresolved_records)`` ready for
            ``_write_silver_file`` and the unresolved-names sink writer.
        """
        # Collect every unprocessed doc, capturing the source per file so
        # the Silver record carries the correct origin.
        unprocessed: List[Tuple[Dict[str, Any], str]] = []
        for bronze_file in bronze_files:
            docs = self._load_bronze_file(bronze_file)
            if not docs:
                continue
            source = self._infer_source(bronze_file)
            for doc in docs:
                doc_id = self._get_doc_id(doc)
                if doc_id in self._processed_ids:
                    result.skipped_count += 1
                    continue
                unprocessed.append((doc, source))

        if not unprocessed:
            return [], []

        all_records: List[Dict[str, Any]] = []
        unresolved_records: List[Dict[str, Any]] = []
        # Plan 72-03 Task 1: per-batch routing accumulators. We collect
        # the routed buckets across batches so we can write a single
        # envelope per sink at the end of the loop, but the COUNTERS on
        # ``result`` accumulate via ``+=`` per batch (Test 7 contract).
        batch_non_player_total: List[Dict[str, Any]] = []
        batch_news_total: List[Dict[str, Any]] = []
        batch_leftover_total: List[Dict[str, Any]] = []

        # Chunk by extractor batch size — typically BATCH_SIZE=8.
        step = max(1, int(getattr(self._extractor, "batch_size", BATCH_SIZE)))
        for start in range(0, len(unprocessed), step):
            batch = unprocessed[start : start + step]
            batch_docs = [doc for doc, _src in batch]

            try:
                by_doc_id, non_player_items = (
                    self._extractor.extract_batch_primary(
                        batch_docs,
                        season=int(season),
                        week=int(week or 0),
                    )
                )
            except Exception as exc:  # noqa: BLE001 — D-02 soft fallback
                logger.error(
                    "claude_primary batch failed (%s); falling back to "
                    "RuleExtractor for %d docs.",
                    exc,
                    len(batch),
                )
                result.claude_failed_count += len(batch)
                for doc, src in batch:
                    fallback_records = self._fallback_per_doc(
                        doc, src, season, week
                    )
                    all_records.extend(fallback_records)
                    result.signal_count += len(fallback_records)
                    result.processed_count += 1
                    self._processed_ids.add(self._get_doc_id(doc))
                continue

            # Successful batch — merge per-doc signals + non-player items.
            for doc, src in batch:
                external_id = self._get_doc_id(doc)
                signals = by_doc_id.get(
                    str(doc.get("external_id", "")), []
                )
                # Resolve names + build records.
                doc_records = self._build_records_for_signals(
                    doc, signals, season, week, src, result, unresolved_records
                )
                all_records.extend(doc_records)
                result.signal_count += len(doc_records)
                result.processed_count += 1
                self._processed_ids.add(external_id)

            # Accumulate non-player items at the run level.
            batch_non_player_total.extend(non_player_items)

            # Plan 72-03 Task 1 — hybrid routing per CONTEXT D-02.
            # Split this batch's non-player items into 3 buckets and
            # ACCUMULATE the counts on ``result`` via ``+=``. Using ``=``
            # here would silently drop earlier batches' counts (Test 7
            # ``test_routing_counters_accumulate_across_batches`` locks
            # this contract — see threat T-72-03-06).
            rollup_items, news_items, leftover_items = (
                self._route_non_player_items(non_player_items)
            )
            result.non_player_routed_count += len(rollup_items)
            result.non_player_news_count += len(news_items)
            batch_news_total.extend(news_items)
            batch_leftover_total.extend(leftover_items)

        # Update result-level non-player accounting (single source of truth).
        result.non_player_items.extend(batch_non_player_total)
        result.non_player_count = len(result.non_player_items)

        # Persist leftover non-player items (subject_type='player' or
        # team_abbr missing) into the existing review queue.
        if not dry_run and batch_leftover_total:
            self._write_envelope(
                batch_leftover_total,
                _NON_PLAYER_DIR,
                prefix="non_player",
                season=season,
                week=week,
                batch_id=batch_id,
            )

        # Persist routable items (coach + team + reporter) into the new
        # ``non_player_news`` Silver sink consumed by the team aggregator
        # and the news-feed API surface (Wave 4).
        if not dry_run and batch_news_total:
            self._write_envelope(
                batch_news_total,
                _NON_PLAYER_NEWS_DIR,
                prefix="non_player_news",
                season=season,
                week=week,
                batch_id=batch_id,
            )

        return all_records, unresolved_records

    # ------------------------------------------------------------------
    # Plan 72-03 Task 1 — hybrid attribution routing helper
    # ------------------------------------------------------------------

    def _route_non_player_items(
        self,
        items: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]]]:
        """Split non-player items per CONTEXT D-02 hybrid attribution.

        Routing rules:

        * ``rollup_items``: ``subject_type`` in ``{coach, team}`` AND
          ``team_abbr`` is non-empty. These contribute to the team
          rollup ``coach_news_count`` / ``team_news_count`` columns
          surfaced by ``TeamWeeklyAggregator`` (Plan 72-03 Task 2).
        * ``news_items``: ``subject_type`` in ``{coach, team, reporter}``
          AND ``team_abbr`` is non-empty. These are written to the
          ``non_player_news`` Silver sink and surfaced by the news-feed
          API (Wave 4). Reporters skip the team rollup because reporters
          cover multiple teams across docs and would inflate per-team
          news counts (CONTEXT specifics: "subject_team" preserved per
          article, not a fixed affiliation).
        * ``leftover_items``: ``subject_type == "player"`` OR
          ``team_abbr`` missing. Kept in ``non_player_pending`` for
          human review — these are the records the resolver couldn't
          attribute and the routing rule can't fix automatically.

        Threat T-72-03-01 mitigation: relies on
        ``_coerce_subject_type`` (in ``extractor.py``) to have
        normalised any unknown ``subject_type`` to ``"player"`` before
        this routing logic runs. Defensively defaults to ``"player"``
        when the key is absent (back-compat with pre-72-03 fixtures).

        Args:
            items: List of non-player item dicts from
                ``ClaudeExtractor._parse_batch_response``.

        Returns:
            Tuple ``(rollup_items, news_items, leftover_items)``.
        """
        rollup_items: List[Dict[str, Any]] = []
        news_items: List[Dict[str, Any]] = []
        leftover_items: List[Dict[str, Any]] = []

        for item in items:
            subject_type = item.get("subject_type", "player")
            team_abbr = item.get("team_abbr")
            # Treat empty string as missing (matches CONTEXT D-06 fail-open).
            has_team = bool(team_abbr) and (
                not isinstance(team_abbr, str) or team_abbr.strip()
            )

            if not has_team or subject_type not in _NEWS_CHANNEL_SUBJECT_TYPES:
                # Either the subject is a player (default) or we can't
                # attribute the news to a team. Keep for review.
                leftover_items.append(item)
                continue

            # Attributable item: always emit to news channel.
            news_items.append(item)
            # Coach + team also contribute to the team rollup; reporters
            # do NOT (they cover multiple teams).
            if subject_type in _TEAM_ROLLUP_SUBJECT_TYPES:
                rollup_items.append(item)

        return rollup_items, news_items, leftover_items

    def _build_records_for_signals(
        self,
        doc: Dict[str, Any],
        signals: List[PlayerSignal],
        season: int,
        week: Optional[int],
        source: str,
        result: PipelineResult,
        unresolved_records: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """Resolve player names + build Silver records for one doc's signals.

        Side effect: when the resolver returns ``None`` for a Claude-named
        player, increments ``result.unresolved_player_count`` and appends
        a JSON envelope-friendly dict to ``unresolved_records`` for the
        unresolved-names sink. The Silver record is still built (the name
        is preserved as ``player_name`` with ``player_id=None``).

        Args:
            doc: Bronze doc dict.
            signals: List of ``PlayerSignal`` objects from the extractor.
            season: NFL season year.
            week: Optional NFL week.
            source: Inferred source string (e.g. ``"rss"``).
            result: PipelineResult mutated for the unresolved counter.
            unresolved_records: List mutated for the sink writer.

        Returns:
            List of Silver record dicts for this doc.
        """
        records: List[Dict[str, Any]] = []
        for signal in signals:
            player_id = self.resolver.resolve(signal.player_name)
            if player_id is None and signal.player_name:
                result.unresolved_player_count += 1
                unresolved_records.append(
                    {
                        "doc_id": doc.get("external_id")
                        or doc.get("id", ""),
                        "player_name": signal.player_name,
                        "team_abbr": signal.team_abbr,
                        "category": signal.category,
                        "summary": signal.summary,
                        "source_excerpt": signal.source_excerpt,
                        "extractor": signal.extractor,
                    }
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

    def _fallback_per_doc(
        self,
        doc: Dict[str, Any],
        source: str,
        season: int,
        week: Optional[int],
    ) -> List[Dict[str, Any]]:
        """Run RuleExtractor on one doc when the parent batch failed.

        Used by the per-doc soft-fallback path in
        ``_run_claude_primary_loop``. The fallback signals carry
        ``extractor="rule"`` (PlayerSignal default) so downstream
        consumers can distinguish them from claude_primary signals.

        Args:
            doc: Bronze doc dict.
            source: Inferred source string.
            season: NFL season year.
            week: Optional NFL week.

        Returns:
            List of Silver record dicts produced by RuleExtractor for the
            single doc. Empty when the rule extractor finds no signals
            (which is common on offseason content).
        """
        if self._rule_fallback is None:
            # Defensive: should never happen because _is_claude_primary
            # implies _rule_fallback was constructed in __init__.
            self._rule_fallback = RuleExtractor()

        try:
            signals = self._rule_fallback.extract(doc)
        except Exception as exc:  # noqa: BLE001 — D-06 fail-open
            logger.warning(
                "Rule fallback extract() raised on doc %s (%s); "
                "returning no records.",
                doc.get("external_id", "?"),
                exc,
            )
            return []

        records: List[Dict[str, Any]] = []
        for signal in signals:
            player_id = self.resolver.resolve(signal.player_name)
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
