"""Parquet cost-log sink for Claude Haiku batched extraction (LLM-04).

Phase 71 Plan 03 introduces a batched primary Claude extractor with
Anthropic prompt caching. Every ``messages.create`` call is tracked
here as a ``CostRecord`` and written to a partitioned Parquet file at

    data/ops/llm_costs/season=YYYY/week=WW/llm_costs_YYYYMMDD_HHMMSS.parquet

The schema mirrors Anthropic's Messages API ``usage`` object 1-to-1
so downstream dashboards can aggregate without field renames:

* ``input_tokens``              -- non-cached prompt tokens
* ``output_tokens``             -- completion tokens
* ``cache_read_input_tokens``   -- warm-cache hits (read @ $0.10/M)
* ``cache_creation_input_tokens`` -- cold writes (creation @ $1.25/M)

Design guarantees
-----------------
* **Fail-open** (D-06): if ``pyarrow`` is missing or the write fails
  for any reason, ``write_record`` logs a warning and returns ``None``
  without raising. The daily cron must never be killed by cost
  accounting.
* **Deterministic paths**: partition layout matches the NFL Bronze/Silver
  convention (``season=YYYY/week=WW/``). Tests pass
  ``CostLog(base_dir=tmp_path)`` to keep writes hermetic.
* **Additive schema**: any future column lands at the end with a safe
  default. No existing field renamed or removed.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module constants
# ---------------------------------------------------------------------------

# USD per 1M tokens for Claude Haiku 4.5 as of 2026-04. Keep in lockstep
# with Anthropic pricing; Plan 71-05 imports this dict for the weekly
# cost summary that lands in 71-SUMMARY.md.
HAIKU_4_5_RATES = {
    "input": 1.00,
    "output": 5.00,
    "cache_read": 0.10,       # cached-input tokens cost ~10% of normal input
    "cache_creation": 1.25,   # cache-write costs ~1.25x normal input
}

# Project root anchoring follows the ``llm_enrichment.py`` convention —
# ``src/sentiment/processing/cost_log.py`` ⇒ 4 parents = repo root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_BASE_DIR = _PROJECT_ROOT / "data" / "ops" / "llm_costs"


# ---------------------------------------------------------------------------
# Cost record
# ---------------------------------------------------------------------------


@dataclass
class CostRecord:
    """Single-call cost accounting row.

    One ``CostRecord`` is produced per ``messages.create`` invocation by
    the batched Claude extractor and persisted via ``CostLog.write_record``.

    Attributes:
        call_id: Short opaque identifier (UUID hex[:8]) for tracing.
        doc_count: Number of Bronze docs included in the batched prompt.
        input_tokens: Non-cached prompt tokens billed at ``HAIKU_4_5_RATES["input"]``.
        output_tokens: Completion tokens billed at ``HAIKU_4_5_RATES["output"]``.
        cache_read_input_tokens: Warm-cache hits billed at
            ``HAIKU_4_5_RATES["cache_read"]``.
        cache_creation_input_tokens: Cold-cache writes billed at
            ``HAIKU_4_5_RATES["cache_creation"]``.
        cost_usd: Dollar cost for this call, computed via ``compute_cost_usd``.
        ts: ISO-8601 UTC timestamp string.
        season: NFL season year (partition column).
        week: NFL week number 1-22 (partition column).
    """

    call_id: str
    doc_count: int
    input_tokens: int
    output_tokens: int
    cache_read_input_tokens: int
    cache_creation_input_tokens: int
    cost_usd: float
    ts: str
    season: int
    week: int


# ---------------------------------------------------------------------------
# Cost math
# ---------------------------------------------------------------------------


def compute_cost_usd(
    input_tokens: int,
    output_tokens: int,
    cache_read_input_tokens: int = 0,
    cache_creation_input_tokens: int = 0,
) -> float:
    """Compute the USD cost for a single Claude Haiku 4.5 call.

    Math is additive across four token classes, each priced per 1M tokens
    per ``HAIKU_4_5_RATES``. Result is rounded to 6 decimals so tests can
    assert exact equality against hand-computed expectations.

    Args:
        input_tokens: Non-cached input tokens (paid at ``input`` rate).
        output_tokens: Completion tokens (paid at ``output`` rate).
        cache_read_input_tokens: Cached input tokens read (cheap).
        cache_creation_input_tokens: Cache write tokens (surcharge).

    Returns:
        USD cost, rounded to 6 decimal places.
    """
    cost = (
        (input_tokens / 1e6) * HAIKU_4_5_RATES["input"]
        + (output_tokens / 1e6) * HAIKU_4_5_RATES["output"]
        + (cache_read_input_tokens / 1e6) * HAIKU_4_5_RATES["cache_read"]
        + (cache_creation_input_tokens / 1e6) * HAIKU_4_5_RATES["cache_creation"]
    )
    return round(cost, 6)


# ---------------------------------------------------------------------------
# Parquet sink
# ---------------------------------------------------------------------------


class CostLog:
    """Parquet-backed cost-log writer and aggregator.

    Writes one row per ``CostRecord`` into
    ``{base_dir}/season=YYYY/week=WW/llm_costs_{ts}.parquet`` and offers
    ``running_total_usd(season, week)`` for weekly budget observation.

    The class takes an optional ``base_dir`` so tests can redirect writes
    to a ``tmp_path`` without touching the real ``data/ops/`` tree.

    Example:
        >>> from src.sentiment.processing.cost_log import CostLog, CostRecord
        >>> log = CostLog()
        >>> rec = CostRecord(...)  # populated from Claude response.usage
        >>> log.write_record(rec)
    """

    def __init__(self, base_dir: Optional[Path] = None) -> None:
        """Initialise with an optional override for the partition root.

        Args:
            base_dir: Directory that holds the ``season=YYYY/week=WW/``
                partitions. Defaults to ``data/ops/llm_costs/`` under the
                project root.
        """
        self.base_dir = Path(base_dir) if base_dir is not None else _DEFAULT_BASE_DIR

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _partition_dir(self, season: int, week: int) -> Path:
        """Compute the partition directory for a given season/week."""
        return self.base_dir / f"season={season}" / f"week={week:02d}"

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def write_record(self, record: CostRecord) -> Optional[Path]:
        """Append a single ``CostRecord`` as a new Parquet file.

        The filename embeds a UTC timestamp plus the ``call_id`` suffix
        so two writes landing in the same wall-clock second still produce
        distinct files. Parent directories are created on demand.

        Fail-open: any exception raised by ``pandas.DataFrame.to_parquet``
        (most commonly ``ImportError`` when PyArrow is missing) is logged
        at WARNING level and swallowed — the daily cron must never be
        killed by cost accounting.

        Args:
            record: Populated ``CostRecord``.

        Returns:
            Path to the newly written Parquet file, or ``None`` when the
            write was skipped due to a recoverable error.
        """
        partition = self._partition_dir(record.season, record.week)
        try:
            partition.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            logger.warning(
                "CostLog: unable to create partition dir %s (%s); skipping write",
                partition,
                exc,
            )
            return None

        ts_file = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        # Append the call_id so concurrent writes within one second don't collide.
        output_path = partition / f"llm_costs_{ts_file}_{record.call_id}.parquet"

        df = pd.DataFrame(
            [
                {
                    "call_id": record.call_id,
                    "doc_count": int(record.doc_count),
                    "input_tokens": int(record.input_tokens),
                    "output_tokens": int(record.output_tokens),
                    "cache_read_input_tokens": int(record.cache_read_input_tokens),
                    "cache_creation_input_tokens": int(
                        record.cache_creation_input_tokens
                    ),
                    "cost_usd": float(record.cost_usd),
                    "ts": record.ts,
                    "season": int(record.season),
                    "week": int(record.week),
                }
            ]
        )

        try:
            df.to_parquet(output_path, index=False)
        except (ImportError, Exception) as exc:  # noqa: BLE001 — fail-open
            logger.warning(
                "CostLog: write_record failed for %s (%s); returning None",
                output_path,
                exc,
            )
            return None

        logger.debug(
            "CostLog: wrote %s (doc_count=%d cost_usd=%.6f)",
            output_path.name,
            record.doc_count,
            record.cost_usd,
        )
        return output_path

    def running_total_usd(self, season: int, week: int) -> float:
        """Sum the ``cost_usd`` column across every Parquet in a partition.

        Returns ``0.0`` on a missing or empty partition (never raises) so
        callers can safely inspect budget before the first call lands.

        Args:
            season: NFL season year.
            week: NFL week number.

        Returns:
            Total USD cost across all calls recorded for the partition.
        """
        partition = self._partition_dir(season, week)
        if not partition.exists():
            return 0.0

        files = sorted(partition.glob("llm_costs_*.parquet"))
        if not files:
            return 0.0

        total = 0.0
        for path in files:
            try:
                df = pd.read_parquet(path, columns=["cost_usd"])
            except Exception as exc:  # noqa: BLE001 — fail-open on read too
                logger.warning(
                    "CostLog: failed to read %s (%s); skipping",
                    path,
                    exc,
                )
                continue
            if "cost_usd" in df.columns and len(df) > 0:
                total += float(df["cost_usd"].sum())

        return total


# ---------------------------------------------------------------------------
# Module helpers
# ---------------------------------------------------------------------------


def new_call_id() -> str:
    """Generate a short opaque call identifier (UUID hex[:8])."""
    return uuid.uuid4().hex[:8]


__all__ = [
    "HAIKU_4_5_RATES",
    "CostLog",
    "CostRecord",
    "compute_cost_usd",
    "new_call_id",
]
