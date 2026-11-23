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

import argparse
import logging
import os
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set

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
    "cache_read": 0.10,  # cached-input tokens cost ~10% of normal input
    "cache_creation": 1.25,  # cache-write costs ~1.25x normal input
}

# Project root anchoring follows the ``llm_enrichment.py`` convention —
# ``src/sentiment/processing/cost_log.py`` ⇒ 4 parents = repo root.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
_DEFAULT_BASE_DIR = _PROJECT_ROOT / "data" / "ops" / "llm_costs"

# Overrides the default ledger directory. The test suite sets it (see
# tests/conftest.py) so a pipeline built without an explicit ``cost_log``
# cannot write fake records into the tracked production ledger.
COST_LOG_DIR_ENV = "LLM_COST_LOG_DIR"


# Per-call files are ``llm_costs_<YYYYMMDD>_<HHMMSS>_<callid>.parquet``; the
# compacted per-run ledger files are ``llm_costs_run_<...>.parquet`` and carry a
# ``source_file`` column naming every per-call file folded into them.
COMPACT_PREFIX = "llm_costs_run_"
_LEDGER_GLOB = "llm_costs_*.parquet"
_COLS = [
    "call_id",
    "doc_count",
    "input_tokens",
    "output_tokens",
    "cache_read_input_tokens",
    "cache_creation_input_tokens",
    "cost_usd",
    "ts",
    "season",
    "week",
]


def _is_compacted(path: Path) -> bool:
    return path.name.startswith(COMPACT_PREFIX)


def default_base_dir() -> Path:
    """Ledger root: ``$LLM_COST_LOG_DIR`` when set, else ``data/ops/llm_costs``."""
    override = os.environ.get(COST_LOG_DIR_ENV)
    return Path(override) if override else _DEFAULT_BASE_DIR


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
                partitions. Defaults to ``$LLM_COST_LOG_DIR`` when set, else
                ``data/ops/llm_costs/`` under the project root.
        """
        self.base_dir = Path(base_dir) if base_dir is not None else default_base_dir()

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
        df = self.read_partition(season, week)
        return float(df["cost_usd"].sum()) if len(df) else 0.0

    # ------------------------------------------------------------------
    # Reading (exactly-once view over per-call + compacted files)
    # ------------------------------------------------------------------

    def _covered_sources(self, files: List[Path]) -> Set[str]:
        """Per-call filenames already folded into some compacted file."""
        covered: Set[str] = set()
        for path in files:
            if not _is_compacted(path):
                continue
            try:
                df = pd.read_parquet(path, columns=["source_file"])
            except Exception as exc:  # noqa: BLE001 — fail-open
                logger.warning("CostLog: cannot read %s (%s)", path, exc)
                continue
            covered.update(df["source_file"].astype(str))
        return covered

    def read_partition(self, season: int, week: int) -> pd.DataFrame:
        """Every call row in a partition, each call counted exactly once.

        Reads compacted and per-call files alike. A per-call file that a
        compacted file already lists in ``source_file`` is skipped, so the
        window between "compacted file renamed in" and "sources deleted"
        (or a crash inside it) never double counts.

        Returns:
            DataFrame with the ledger columns (empty when nothing is there).
        """
        return self._read_dir(self._partition_dir(season, week))

    def _read_dir(self, partition: Path) -> pd.DataFrame:
        if not partition.exists():
            return pd.DataFrame(columns=_COLS)
        files = sorted(partition.glob(_LEDGER_GLOB))
        covered = self._covered_sources(files)
        frames = []
        for path in files:
            if not _is_compacted(path) and path.name in covered:
                continue
            try:
                df = pd.read_parquet(path)
            except Exception as exc:  # noqa: BLE001 — fail-open on read too
                logger.warning("CostLog: failed to read %s (%s); skipping", path, exc)
                continue
            if len(df):
                frames.append(df[[c for c in _COLS if c in df.columns]])
        if not frames:
            return pd.DataFrame(columns=_COLS)
        return pd.concat(frames, ignore_index=True)

    def partitions(self) -> List[Path]:
        """Every ``season=*/week=*`` directory under the ledger root."""
        if not self.base_dir.exists():
            return []
        return sorted(p for p in self.base_dir.glob("season=*/week=*") if p.is_dir())

    # ------------------------------------------------------------------
    # Compaction
    # ------------------------------------------------------------------

    def compact_partition(
        self, season: int, week: int, run_id: Optional[str] = None
    ) -> Optional[Path]:
        """Fold a partition's per-call files into ONE compacted parquet.

        Exactly-once mechanism: the compacted file lists each folded
        per-call filename in ``source_file`` and readers skip any per-call
        file so listed. Order of operations is (1) write temp file, fsync,
        (2) atomic rename into place, (3) delete sources. A crash after (2)
        leaves both on disk but ``read_partition`` counts each call once,
        and the next compaction just deletes the already-covered leftovers
        without folding them again. Compacted files are never re-folded.

        Fail-open: any error logs a warning and leaves the per-call files.

        Returns:
            Path of the new compacted file, or ``None`` if there was
            nothing to fold (or compaction failed).
        """
        return self._compact_dir(self._partition_dir(season, week), run_id)

    def _compact_dir(self, partition: Path, run_id: Optional[str]) -> Optional[Path]:
        tmp: Optional[Path] = None
        try:
            if not partition.exists():
                return None
            files = sorted(partition.glob(_LEDGER_GLOB))
            covered = self._covered_sources(files)
            per_call = [f for f in files if not _is_compacted(f)]
            for f in per_call:  # crash remnants: already inside a compacted file
                if f.name in covered:
                    f.unlink()
            to_fold = [f for f in per_call if f.name not in covered]

            frames = []
            folded: List[Path] = []
            for f in to_fold:
                try:
                    df = pd.read_parquet(f)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("CostLog: skip unreadable %s (%s)", f, exc)
                    continue
                df = df[[c for c in _COLS if c in df.columns]].copy()
                df["source_file"] = f.name
                frames.append(df)
                folded.append(f)
            if not frames:
                return None

            out_df = pd.concat(frames, ignore_index=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
            suffix = run_id or uuid.uuid4().hex[:6]
            final = partition / f"{COMPACT_PREFIX}{stamp}_{suffix}.parquet"
            tmp = partition / f".{final.name}.tmp"  # not matched by the ledger glob
            out_df.to_parquet(tmp, index=False)
            with open(tmp, "rb") as fh:
                os.fsync(fh.fileno())
            os.replace(tmp, final)
            tmp = None
            for f in folded:
                f.unlink()
            return final
        except Exception as exc:  # noqa: BLE001 — fail-open
            logger.warning("CostLog: compaction of %s failed (%s)", partition, exc)
            if tmp is not None:
                try:
                    tmp.unlink()
                except OSError:
                    pass
            return None

    def summarize_partition(self, partition: Path) -> Dict[str, float]:
        """Call count and token/USD totals for one partition directory."""
        df = self._read_dir(partition)
        out: Dict[str, float] = {"calls": int(len(df))}
        for col in ("input_tokens", "output_tokens", "cost_usd"):
            out[col] = float(df[col].sum()) if len(df) else 0.0
        return out


def compact_all(
    base_dir: Optional[Path] = None,
    season: Optional[int] = None,
    week: Optional[int] = None,
) -> List[str]:
    """Compact the selected partitions; return one summary line per partition.

    With neither ``season`` nor ``week``, every partition holding per-call
    files is compacted. Each line reports the calls folded in THIS run.
    """
    log = CostLog(base_dir=base_dir)
    lines: List[str] = []
    for part in log.partitions():
        s = int(part.parent.name.split("=")[1])
        w = int(part.name.split("=")[1])
        if (season is not None and s != season) or (week is not None and w != week):
            continue
        out = log._compact_dir(part, None)
        if out is None:
            continue
        df = pd.read_parquet(out)
        lines.append(
            f"season={s} week={w:02d} calls={len(df)} "
            f"input_tokens={int(df['input_tokens'].sum())} "
            f"output_tokens={int(df['output_tokens'].sum())} "
            f"usd={float(df['cost_usd'].sum()):.6f} "
            f"week_total_usd={log.running_total_usd(s, w):.6f}"
        )
    return lines


def main(argv: Optional[List[str]] = None) -> int:
    """CLI: ``python -m src.sentiment.processing.cost_log [--season Y] [--week W]``."""
    ap = argparse.ArgumentParser(description="Compact the LLM cost ledger.")
    ap.add_argument("--season", type=int)
    ap.add_argument("--week", type=int)
    args = ap.parse_args(argv)
    for line in compact_all(season=args.season, week=args.week):
        print(line)
    return 0


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
    "compact_all",
    "compute_cost_usd",
    "main",
    "new_call_id",
]


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
