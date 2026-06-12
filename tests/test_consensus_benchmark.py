"""Unit tests for the Phase 1.1 consensus benchmark join and metric logic.

All tests use synthetic data — no network calls, no file I/O on real data.
The tests validate:
  - join_consensus: player_id path, player_name fallback, no match case
  - compute_spearman_rank_corr: basic correctness, degenerate cases
  - compute_top_n_hit_rate: perfect / zero hit rates, edge cases
  - load_consensus_for_seasons: reads from a tmp Silver directory
  - print_consensus_report: runs without error on synthetic data
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import List
from unittest import mock

import numpy as np
import pandas as pd
import pytest

# Bootstrap project root so imports resolve.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))
if str(_PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

# Import the module under test.
import importlib

_bp = importlib.import_module("scripts.backtest_projections")

join_consensus = _bp.join_consensus
compute_spearman_rank_corr = _bp.compute_spearman_rank_corr
compute_top_n_hit_rate = _bp.compute_top_n_hit_rate
load_consensus_for_seasons = _bp.load_consensus_for_seasons
print_consensus_report = _bp.print_consensus_report
_CONSENSUS_POSITIONS = _bp._CONSENSUS_POSITIONS
_CONSENSUS_MIN_PTS = _bp._CONSENSUS_MIN_PTS
from consensus_metrics import TOP_N as _TOP_N  # canonical (ELITE 3.1)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _make_results(
    n_players: int = 20,
    season: int = 2023,
    week: int = 5,
    position: str = "WR",
    use_player_id: bool = True,
) -> pd.DataFrame:
    """Build a synthetic backtest results DataFrame."""
    rng = np.random.default_rng(42)
    rows = []
    for i in range(n_players):
        pid = f"00-00{10000 + i}"
        name = f"Player{i:02d}"
        actual = float(rng.uniform(0, 25))
        projected = actual + float(rng.normal(0, 4))
        projected = max(0.0, projected)
        row = {
            "player_name": name,
            "position": position,
            "season": season,
            "week": week,
            "projected_points": projected,
            "actual_points": actual,
        }
        if use_player_id:
            row["player_id"] = pid
        rows.append(row)
    return pd.DataFrame(rows)


def _make_consensus(
    results_df: pd.DataFrame,
    bias: float = 0.5,
    noise_std: float = 3.0,
) -> pd.DataFrame:
    """Build a synthetic consensus DataFrame matched to a results frame."""
    rng = np.random.default_rng(99)
    rows = []
    for _, r in results_df.iterrows():
        rows.append(
            {
                "player_id": r.get("player_id", ""),
                "player_name": r["player_name"],
                "season": r["season"],
                "week": r["week"],
                "consensus_proj": max(
                    0.0, r["actual_points"] + bias + float(rng.normal(0, noise_std))
                ),
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: join_consensus
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_join_consensus_by_player_id() -> None:
    """join_consensus matches on (player_id, season, week)."""
    results = _make_results(n_players=15, season=2023, week=5, use_player_id=True)
    consensus = _make_consensus(results)

    merged = join_consensus(results, consensus)

    assert not merged.empty, "Expected non-empty merged frame"
    assert "consensus_proj" in merged.columns
    # All rows should have valid consensus projections
    assert (merged["consensus_proj"] >= 0).all()
    # Should have matched all 15 players
    assert len(merged) == 15


@pytest.mark.unit
def test_join_consensus_fallback_to_name() -> None:
    """join_consensus falls back to player_name when player_id is absent in results."""
    results = _make_results(n_players=10, season=2023, week=5, use_player_id=False)
    consensus = _make_consensus(results)
    # Give consensus a player_id so it doesn't auto-trigger the name path
    # (the name-fallback triggers when there's a player_id mismatch)
    consensus["player_id"] = ""

    merged = join_consensus(results, consensus)

    assert not merged.empty, "Expected fallback name join to succeed"
    assert "consensus_proj" in merged.columns
    assert len(merged) == 10


@pytest.mark.unit
def test_join_consensus_partial_match() -> None:
    """join_consensus returns only matched rows when partial overlap exists."""
    results = _make_results(n_players=20, season=2023, week=5, use_player_id=True)
    # Keep only first 10 players in consensus
    consensus = _make_consensus(results.head(10))

    merged = join_consensus(results, consensus)

    assert len(merged) == 10, f"Expected 10 matched rows, got {len(merged)}"


@pytest.mark.unit
def test_join_consensus_empty_consensus() -> None:
    """join_consensus returns empty DataFrame when consensus is empty."""
    results = _make_results(n_players=10)
    merged = join_consensus(results, pd.DataFrame())

    assert merged.empty


@pytest.mark.unit
def test_join_consensus_empty_results() -> None:
    """join_consensus returns empty DataFrame when results is empty."""
    consensus = pd.DataFrame(
        {
            "player_id": ["x"],
            "player_name": ["A"],
            "season": [2023],
            "week": [5],
            "consensus_proj": [10.0],
        }
    )
    merged = join_consensus(pd.DataFrame(), consensus)

    assert merged.empty


@pytest.mark.unit
def test_join_consensus_no_overlap() -> None:
    """join_consensus returns empty DataFrame when player_ids don't overlap."""
    results = _make_results(n_players=5, season=2023, week=5, use_player_id=True)
    consensus = _make_consensus(results)
    # Corrupt all player IDs in consensus so nothing matches
    consensus["player_id"] = "ZZZZ"
    consensus["player_name"] = "NoMatchPlayer"

    merged = join_consensus(results, consensus)

    assert merged.empty, "Expected no matches when IDs and names differ"


@pytest.mark.unit
def test_join_consensus_no_leak_from_actuals() -> None:
    """Consensus side must never contribute actual_points to the merged frame.

    The leak rule: consensus_df contains only projected values (consensus_proj).
    Verify that 'actual_points' in the merged frame comes exclusively from
    the results (ours) side.
    """
    results = _make_results(n_players=10, season=2023, week=5)
    consensus = _make_consensus(results)

    # Poison the consensus with an 'actual_points' column — it should NOT
    # survive into the merged result (join only takes consensus_proj).
    consensus["actual_points"] = 999.0

    merged = join_consensus(results, consensus)

    # actual_points in merged should come from results (never 999.0)
    assert "actual_points" in merged.columns
    assert (
        merged["actual_points"] != 999.0
    ).all(), "Leak detected: consensus actual_points contaminated merged frame"


# ---------------------------------------------------------------------------
# Tests: compute_spearman_rank_corr
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_spearman_rank_corr_perfect_positive() -> None:
    """Perfect rank correlation returns 1.0."""
    n_weeks = 5
    rows = []
    for week in range(1, n_weeks + 1):
        for i in range(12):
            val = float(i * 3)
            rows.append({"season": 2023, "week": week, "proj": val, "actual": val})
    df = pd.DataFrame(rows)
    rho = compute_spearman_rank_corr(df, "proj", "actual", "WR")
    assert abs(rho - 1.0) < 1e-6, f"Expected ~1.0, got {rho}"


@pytest.mark.unit
def test_spearman_rank_corr_perfect_negative() -> None:
    """Perfect inverse rank correlation returns -1.0."""
    rows = []
    for week in range(1, 4):
        for i in range(12):
            rows.append(
                {"season": 2023, "week": week, "proj": float(i), "actual": float(11 - i)}
            )
    df = pd.DataFrame(rows)
    rho = compute_spearman_rank_corr(df, "proj", "actual", "WR")
    assert abs(rho + 1.0) < 1e-6, f"Expected ~-1.0, got {rho}"


@pytest.mark.unit
def test_spearman_rank_corr_insufficient_data() -> None:
    """Groups with fewer than 10 rows are skipped; returns NaN if no valid groups."""
    df = pd.DataFrame(
        {
            "season": [2023, 2023],
            "week": [1, 1],
            "proj": [5.0, 10.0],
            "actual": [5.0, 10.0],
        }
    )
    rho = compute_spearman_rank_corr(df, "proj", "actual", "QB")
    assert np.isnan(rho), "Expected NaN for insufficient data"


@pytest.mark.unit
def test_spearman_rank_corr_multi_week_average() -> None:
    """Mean is computed across weeks, not across all rows jointly."""
    # Week 1: perfect positive, Week 2: perfect negative -> mean ~0
    rows = []
    for i in range(12):
        rows.append({"season": 2023, "week": 1, "proj": float(i), "actual": float(i)})
    for i in range(12):
        rows.append(
            {"season": 2023, "week": 2, "proj": float(i), "actual": float(11 - i)}
        )
    df = pd.DataFrame(rows)
    rho = compute_spearman_rank_corr(df, "proj", "actual", "RB")
    assert abs(rho) < 0.1, f"Expected ~0.0, got {rho}"


# ---------------------------------------------------------------------------
# Tests: compute_top_n_hit_rate
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_top_n_hit_rate_perfect() -> None:
    """When projected ranking matches actual ranking exactly, hit rate = 1.0."""
    n = _TOP_N["WR"]  # 24
    rows = []
    for week in range(3, 6):
        for i in range(n + 5):  # more players than top-N
            val = float(n + 5 - i)  # descending so top-n is consistent
            rows.append({"season": 2023, "week": week, "proj": val, "actual": val})
    df = pd.DataFrame(rows)
    hr = compute_top_n_hit_rate(df, "proj", "actual", "WR")
    assert abs(hr - 1.0) < 1e-6, f"Expected 1.0, got {hr}"


@pytest.mark.unit
def test_top_n_hit_rate_no_overlap() -> None:
    """When projected top-N and actual top-N are disjoint, hit rate = 0.0."""
    n = _TOP_N["QB"]  # 12
    n_players = n * 2
    rows = []
    for week in range(3, 5):
        for i in range(n_players):
            # proj orders first half high, actual orders second half high
            proj_val = float(n_players - i) if i < n else float(i - n)
            actual_val = float(i) if i >= n else float(-i)
            rows.append(
                {"season": 2023, "week": week, "proj": proj_val, "actual": actual_val}
            )
    df = pd.DataFrame(rows)
    hr = compute_top_n_hit_rate(df, "proj", "actual", "QB")
    assert abs(hr) < 1e-6, f"Expected 0.0, got {hr}"


@pytest.mark.unit
def test_top_n_hit_rate_insufficient_players() -> None:
    """Weeks with fewer players than N are skipped; returns NaN if all skipped."""
    df = pd.DataFrame(
        {
            "season": [2023] * 5,
            "week": [3] * 5,
            "proj": [10.0, 9.0, 8.0, 7.0, 6.0],
            "actual": [10.0, 9.0, 8.0, 7.0, 6.0],
        }
    )
    # QB top-N is 12 but we only have 5 players -> skip -> NaN
    hr = compute_top_n_hit_rate(df, "proj", "actual", "QB")
    assert np.isnan(hr), f"Expected NaN for insufficient players, got {hr}"


# ---------------------------------------------------------------------------
# Tests: load_consensus_for_seasons
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_load_consensus_reads_silver_parquet(tmp_path: Path) -> None:
    """load_consensus_for_seasons reads parquet files from the Silver layout."""
    # Write a synthetic Silver parquet
    week_dir = tmp_path / "season=2023" / "week=05"
    week_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "player_id": ["00-001", "00-002"],
            "player_name": ["Alice", "Bob"],
            "source": ["sleeper", "sleeper"],
            "scoring_format": ["half_ppr", "half_ppr"],
            "projected_points": [12.5, 8.3],
            "season": [2023, 2023],
            "week": [5, 5],
        }
    )
    df.to_parquet(week_dir / "external_projections_test.parquet", index=False)

    result = load_consensus_for_seasons(
        seasons=[2023],
        weeks=[5],
        scoring_format="half_ppr",
        silver_root=str(tmp_path),
        source="sleeper",
    )

    assert not result.empty
    assert "consensus_proj" in result.columns
    assert len(result) == 2
    assert set(result["player_id"]) == {"00-001", "00-002"}


@pytest.mark.unit
def test_load_consensus_skips_missing_season(tmp_path: Path) -> None:
    """load_consensus_for_seasons returns empty for non-existent seasons."""
    result = load_consensus_for_seasons(
        seasons=[1990],
        weeks=[5],
        scoring_format="half_ppr",
        silver_root=str(tmp_path),
    )
    assert result.empty


@pytest.mark.unit
def test_load_consensus_filters_source(tmp_path: Path) -> None:
    """load_consensus_for_seasons filters to the requested source."""
    week_dir = tmp_path / "season=2023" / "week=05"
    week_dir.mkdir(parents=True)
    df = pd.DataFrame(
        {
            "player_id": ["00-001", "00-002"],
            "player_name": ["Alice", "Bob"],
            "source": ["espn", "sleeper"],
            "scoring_format": ["half_ppr", "half_ppr"],
            "projected_points": [12.5, 8.3],
            "season": [2023, 2023],
            "week": [5, 5],
        }
    )
    df.to_parquet(week_dir / "test.parquet", index=False)

    result = load_consensus_for_seasons(
        seasons=[2023],
        weeks=[5],
        scoring_format="half_ppr",
        silver_root=str(tmp_path),
        source="sleeper",
    )

    assert len(result) == 1
    assert result.iloc[0]["player_id"] == "00-002"


# ---------------------------------------------------------------------------
# Tests: print_consensus_report (smoke test)
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_print_consensus_report_runs_without_error(
    capsys: pytest.CaptureFixture,
) -> None:
    """print_consensus_report should complete without raising on valid input."""
    # Build synthetic matched DataFrame with 3 weeks, multiple positions
    rng = np.random.default_rng(7)
    rows = []
    for week in range(3, 6):
        for pos, n in [("QB", 15), ("RB", 30), ("WR", 30), ("TE", 15)]:
            for i in range(n):
                actual = float(rng.uniform(2, 28))
                rows.append(
                    {
                        "player_name": f"{pos}_{i}",
                        "player_id": f"00-{pos}{i:03d}",
                        "position": pos,
                        "season": 2023,
                        "week": week,
                        "projected_points": max(0.0, actual + float(rng.normal(0, 4))),
                        "actual_points": actual,
                        # consensus_proj at >= 5 for most players
                        "consensus_proj": max(5.0, actual + float(rng.normal(0, 4))),
                    }
                )
    matched = pd.DataFrame(rows)

    # Should not raise
    print_consensus_report(matched, "half_ppr")

    captured = capsys.readouterr()
    assert "BEAT-THE-CONSENSUS" in captured.out
    assert "VERDICT" in captured.out


@pytest.mark.unit
def test_print_consensus_report_empty_input(capsys: pytest.CaptureFixture) -> None:
    """print_consensus_report handles empty input gracefully."""
    print_consensus_report(pd.DataFrame(), "half_ppr")
    captured = capsys.readouterr()
    assert "No matched" in captured.out


@pytest.mark.unit
def test_print_consensus_report_all_below_threshold(
    capsys: pytest.CaptureFixture,
) -> None:
    """print_consensus_report handles case where all consensus_proj < threshold."""
    df = pd.DataFrame(
        {
            "player_name": ["A", "B"],
            "position": ["WR", "WR"],
            "season": [2023, 2023],
            "week": [5, 5],
            "projected_points": [3.0, 2.0],
            "actual_points": [3.0, 2.0],
            "consensus_proj": [1.0, 2.0],  # both below 5.0 threshold
        }
    )
    print_consensus_report(df, "half_ppr")
    captured = capsys.readouterr()
    assert "No player-weeks" in captured.out
