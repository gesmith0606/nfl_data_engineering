"""Tests for the Parquet cost-log sink (Plan 71-03 Task 1).

Covers ``src/sentiment/processing/cost_log.py`` — the LLM-04 cost-tracking
surface that writes one Parquet row per Claude ``messages.create`` call.

Determinism notes:
    - All tests use ``tmp_path`` and pass ``CostLog(base_dir=tmp_path)`` so no
      writes touch the real ``data/ops/`` tree.
    - Float comparisons round to 6 decimals — matches ``compute_cost_usd``'s
      internal rounding.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.sentiment.processing.cost_log import (
    HAIKU_4_5_RATES,
    CostLog,
    CostRecord,
    compute_cost_usd,
)


# ---------------------------------------------------------------------------
# Rate table + math
# ---------------------------------------------------------------------------


class HaikuRatesTests:
    """The exported rate table must match the 2026-04 Haiku 4.5 pricing."""


def test_rate_table_exposes_four_keys() -> None:
    assert set(HAIKU_4_5_RATES.keys()) == {
        "input",
        "output",
        "cache_read",
        "cache_creation",
    }


def test_rate_table_values_match_haiku_4_5_pricing() -> None:
    assert HAIKU_4_5_RATES["input"] == 1.00
    assert HAIKU_4_5_RATES["output"] == 5.00
    assert HAIKU_4_5_RATES["cache_read"] == 0.10
    assert HAIKU_4_5_RATES["cache_creation"] == 1.25


def test_compute_cost_input_only() -> None:
    assert round(compute_cost_usd(1_000_000, 0), 6) == 1.00


def test_compute_cost_output_only() -> None:
    assert round(compute_cost_usd(0, 1_000_000), 6) == 5.00


def test_compute_cost_cache_read_only() -> None:
    assert round(
        compute_cost_usd(0, 0, cache_read_input_tokens=1_000_000), 6
    ) == 0.10


def test_compute_cost_cache_creation_only() -> None:
    assert round(
        compute_cost_usd(0, 0, cache_creation_input_tokens=1_000_000), 6
    ) == 1.25


def test_compute_cost_mixed_usage_additive() -> None:
    # 1000 input @ $1/M + 500 output @ $5/M + 500 cache_read @ $0.10/M
    # + 100 cache_creation @ $1.25/M
    expected = (
        (1000 / 1e6) * 1.00
        + (500 / 1e6) * 5.00
        + (500 / 1e6) * 0.10
        + (100 / 1e6) * 1.25
    )
    actual = compute_cost_usd(1000, 500, 500, 100)
    assert round(actual, 6) == round(expected, 6)


# ---------------------------------------------------------------------------
# CostLog write_record
# ---------------------------------------------------------------------------


def _sample_record(season: int = 2025, week: int = 17) -> CostRecord:
    return CostRecord(
        call_id="abc12345",
        doc_count=8,
        input_tokens=1500,
        output_tokens=600,
        cache_read_input_tokens=1100,
        cache_creation_input_tokens=0,
        cost_usd=compute_cost_usd(1500, 600, 1100, 0),
        ts="2026-04-24T20:30:00+00:00",
        season=season,
        week=week,
    )


def test_write_record_creates_partitioned_parquet(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)
    record = _sample_record(season=2025, week=17)

    path = log.write_record(record)

    assert path is not None
    assert path.exists()
    # Partition layout matches the S3 key convention
    assert "season=2025" in str(path)
    assert "week=17" in str(path)
    assert path.name.startswith("llm_costs_")
    assert path.suffix == ".parquet"


def test_write_record_writes_all_ten_columns(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)
    record = _sample_record()

    path = log.write_record(record)
    df = pd.read_parquet(path)

    assert len(df) == 1
    expected_columns = {
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
    }
    assert set(df.columns) == expected_columns
    row = df.iloc[0]
    assert row["call_id"] == "abc12345"
    assert row["doc_count"] == 8
    assert row["season"] == 2025
    assert row["week"] == 17


def test_write_record_pads_week_to_two_digits(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)
    record = _sample_record(season=2025, week=3)

    path = log.write_record(record)

    assert "week=03" in str(path)


def test_write_record_returns_none_on_missing_pyarrow(tmp_path, monkeypatch) -> None:
    """Fail-open: if pyarrow is missing the cron must not hard-fail (D-06)."""
    from src.sentiment.processing import cost_log

    def _raise_import_error(*args, **kwargs):
        raise ImportError("pyarrow not installed")

    monkeypatch.setattr(
        cost_log.pd.DataFrame,
        "to_parquet",
        _raise_import_error,
        raising=True,
    )

    log = cost_log.CostLog(base_dir=tmp_path)
    result = log.write_record(_sample_record())

    assert result is None  # fail-open, no raise


# ---------------------------------------------------------------------------
# CostLog running_total_usd
# ---------------------------------------------------------------------------


def test_running_total_zero_for_missing_partition(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)
    assert log.running_total_usd(season=2099, week=99) == 0.0


def test_running_total_sums_three_records(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)

    # Write 3 records with deterministic cost values
    r1 = _sample_record()
    r1.cost_usd = 0.0025
    r2 = _sample_record()
    r2.cost_usd = 0.0031
    r3 = _sample_record()
    r3.cost_usd = 0.0047

    # ``write_record`` uses ``datetime.now`` for the filename timestamp;
    # add a ``call_id`` suffix to guarantee filename uniqueness even when
    # two writes land in the same wall-clock second.
    r1.call_id = "call0001"
    r2.call_id = "call0002"
    r3.call_id = "call0003"

    for rec in (r1, r2, r3):
        log.write_record(rec)

    total = log.running_total_usd(season=2025, week=17)
    assert round(total, 6) == round(0.0025 + 0.0031 + 0.0047, 6)


def test_running_total_respects_base_dir_override(tmp_path) -> None:
    """Two isolated CostLog instances MUST NOT see each other's records."""
    log_a = CostLog(base_dir=tmp_path / "a")
    log_b = CostLog(base_dir=tmp_path / "b")

    rec_a = _sample_record()
    rec_a.cost_usd = 0.05
    rec_a.call_id = "only_a"

    log_a.write_record(rec_a)

    assert log_a.running_total_usd(2025, 17) == pytest.approx(0.05)
    assert log_b.running_total_usd(2025, 17) == 0.0
