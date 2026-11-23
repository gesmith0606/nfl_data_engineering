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
    assert round(compute_cost_usd(0, 0, cache_read_input_tokens=1_000_000), 6) == 0.10


def test_compute_cost_cache_creation_only() -> None:
    assert (
        round(compute_cost_usd(0, 0, cache_creation_input_tokens=1_000_000), 6) == 1.25
    )


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


def test_default_ledger_is_redirected_under_pytest(tmp_path, monkeypatch) -> None:
    """The suite-wide fixture must keep CostLog() out of the repo's ledger."""
    from src.sentiment.processing import cost_log as cl

    assert cl.CostLog().base_dir != cl._DEFAULT_BASE_DIR
    assert cl._PROJECT_ROOT not in cl.CostLog().base_dir.parents

    monkeypatch.setenv(cl.COST_LOG_DIR_ENV, str(tmp_path))
    assert cl.CostLog().base_dir == tmp_path

    # Unset -> the production default; an explicit base_dir always wins.
    monkeypatch.delenv(cl.COST_LOG_DIR_ENV)
    assert cl.CostLog().base_dir == cl._DEFAULT_BASE_DIR
    monkeypatch.setenv(cl.COST_LOG_DIR_ENV, "/nonexistent")
    assert cl.CostLog(base_dir=tmp_path).base_dir == tmp_path


# ---------------------------------------------------------------------------
# Compaction (one file per run, exactly-once)
# ---------------------------------------------------------------------------


def _write_calls(
    log: CostLog, n: int, season: int = 2026, week: int = 12, tag: str = "call"
):
    """Write n per-call files with distinct ids; return their paths."""
    paths = []
    for i in range(n):
        rec = _sample_record(season=season, week=week)
        rec.call_id = f"{tag}{i:04d}"
        rec.cost_usd = 0.01 * (i + 1)
        rec.input_tokens = 100 * (i + 1)
        paths.append(log.write_record(rec))
    return paths


def _ledger_files(tmp_path, season=2026, week=12):
    part = tmp_path / f"season={season}" / f"week={week:02d}"
    return sorted(part.glob("*.parquet"))


def test_compact_folds_n_files_into_one_with_same_totals(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)
    _write_calls(log, 5)
    before = log.running_total_usd(2026, 12)

    out = log.compact_partition(2026, 12, run_id="r1")

    assert out is not None and out.name.startswith("llm_costs_run_")
    assert _ledger_files(tmp_path) == [out]
    df = pd.read_parquet(out)
    assert len(df) == 5
    assert set(df.columns) >= {"call_id", "cost_usd", "source_file"}
    assert log.running_total_usd(2026, 12) == pytest.approx(before)
    assert df["input_tokens"].sum() == 100 * (1 + 2 + 3 + 4 + 5)


def test_compact_is_idempotent_and_never_refolds(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)
    _write_calls(log, 3)
    first = log.compact_partition(2026, 12)
    total = log.running_total_usd(2026, 12)

    assert log.compact_partition(2026, 12) is None  # nothing new
    assert _ledger_files(tmp_path) == [first]
    assert log.running_total_usd(2026, 12) == pytest.approx(total)

    # New calls later fold into a second compacted file; first is untouched.
    _write_calls(log, 2, tag="late")
    second = log.compact_partition(2026, 12)
    assert second is not None and second != first
    assert len(pd.read_parquet(first)) == 3
    assert len(pd.read_parquet(second)) == 2


def test_compact_empty_or_absent_partition_is_noop(tmp_path) -> None:
    log = CostLog(base_dir=tmp_path)
    assert log.compact_partition(2026, 12) is None
    (tmp_path / "season=2026" / "week=12").mkdir(parents=True)
    assert log.compact_partition(2026, 12) is None


def test_crash_after_rename_before_delete_does_not_double_count(
    tmp_path, monkeypatch
) -> None:
    from pathlib import Path

    log = CostLog(base_dir=tmp_path)
    paths = _write_calls(log, 4)
    expected = log.running_total_usd(2026, 12)

    # Simulate the crash: deleting sources fails after the rename succeeded.
    real_unlink = Path.unlink

    def boom(self, *a, **k):
        if self.name.startswith("llm_costs_2"):
            raise OSError("simulated crash")
        return real_unlink(self, *a, **k)

    monkeypatch.setattr(Path, "unlink", boom)
    assert log.compact_partition(2026, 12) is None  # fail-open
    monkeypatch.setattr(Path, "unlink", real_unlink)

    # Compacted file AND all 4 sources are on disk, yet the total is unchanged.
    assert len(_ledger_files(tmp_path)) == 5
    assert all(p.exists() for p in paths)
    assert log.running_total_usd(2026, 12) == pytest.approx(expected)
    assert len(log.read_partition(2026, 12)) == 4

    # Next run cleans the leftovers without folding them again.
    assert log.compact_partition(2026, 12) is None
    files = _ledger_files(tmp_path)
    assert len(files) == 1 and files[0].name.startswith("llm_costs_run_")
    assert log.running_total_usd(2026, 12) == pytest.approx(expected)
    assert len(log.read_partition(2026, 12)) == 4


def test_compact_write_failure_keeps_sources_and_leaves_no_temp(
    tmp_path, monkeypatch
) -> None:
    log = CostLog(base_dir=tmp_path)
    paths = _write_calls(log, 2)

    def bad_to_parquet(self, *a, **k):
        raise RuntimeError("disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", bad_to_parquet)
    assert log.compact_partition(2026, 12) is None
    monkeypatch.undo()
    assert all(p.exists() for p in paths)
    assert not list((tmp_path / "season=2026" / "week=12").glob(".*tmp"))


def test_cli_summary_line_and_all_partitions(tmp_path, capsys, monkeypatch) -> None:
    from src.sentiment.processing import cost_log as cl

    log = CostLog(base_dir=tmp_path)
    _write_calls(log, 3, week=11)
    _write_calls(log, 2, week=12)
    _write_calls(log, 1, season=2025, week=3)
    monkeypatch.setenv(cl.COST_LOG_DIR_ENV, str(tmp_path))

    assert cl.main(["--season", "2026", "--week", "12"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 1
    assert out[0].startswith("season=2026 week=12 calls=2 input_tokens=300 ")
    assert "usd=0.030000" in out[0]

    assert cl.main([]) == 0  # remaining partitions only
    assert len(capsys.readouterr().out.strip().splitlines()) == 2
    assert cl.main([]) == 0
    assert capsys.readouterr().out == ""  # idempotent: nothing left to fold


def test_dashboard_llm_cost_block(tmp_path) -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
    import build_pipeline_status as bps

    assert bps.llm_cost_summary(tmp_path) is None  # empty ledger

    log = CostLog(base_dir=tmp_path)
    _write_calls(log, 2, week=11)
    _write_calls(log, 3, week=12)
    _write_calls(log, 4, season=2025, week=18)
    log.compact_partition(2026, 12)

    block = bps.llm_cost_summary(tmp_path)
    assert block["latest_week"]["season"] == 2026
    assert block["latest_week"]["week"] == 12
    assert block["latest_week"]["calls"] == 3
    assert block["latest_week"]["usd"] == pytest.approx(0.06)
    assert block["season_to_date"]["calls"] == 5
    assert block["season_to_date"]["season"] == 2026
