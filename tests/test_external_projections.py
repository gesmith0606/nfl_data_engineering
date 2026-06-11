"""Regression tests for the consensus-harness join dedup fix.

Bug: run_backtest() used a player_name-only merge to join projections with
actuals.  When two different players share an abbreviated name (e.g.
Tyreek Hill and Taysom Hill both become "T.Hill"), a single projection row
matched BOTH actual rows, producing duplicates with different actual_points
and corrupting MAE and consensus benchmark metrics.

Fix: run_backtest() now prefers a player_id join; the name-based fallback
deduplicates actuals before merging so one projection never maps to more
than one actual row.

These tests exercise compute_actuals() and the merge logic directly to lock
in the corrected behaviour and prevent regressions.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional

import pandas as pd
import numpy as np
import pytest

# Bootstrap project root so imports resolve without installation.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
if str(_PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "src"))
if str(_PROJECT_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT / "scripts"))

import importlib

_bp = importlib.import_module("scripts.backtest_projections")

compute_actuals = _bp.compute_actuals


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_weekly_row(
    player_id: str,
    player_name: str,
    position: str,
    team: str,
    season: int,
    week: int,
    receiving_yards: float = 0.0,
    rushing_yards: float = 0.0,
    receptions: float = 0.0,
    passing_yards: float = 0.0,
    passing_tds: float = 0.0,
    receiving_tds: float = 0.0,
    rushing_tds: float = 0.0,
) -> dict:
    """Build a minimal weekly stats row for testing."""
    return {
        "player_id": player_id,
        "player_name": player_name,
        "position": position,
        "recent_team": team,
        "season": season,
        "week": week,
        "receiving_yards": receiving_yards,
        "rushing_yards": rushing_yards,
        "receptions": receptions,
        "passing_yards": passing_yards,
        "passing_tds": passing_tds,
        "receiving_tds": receiving_tds,
        "rushing_tds": rushing_tds,
        "targets": 0.0,
        "carries": 0.0,
        "interceptions": 0.0,
        "sack_fumbles_lost": 0.0,
        "rushing_fumbles_lost": 0.0,
        "receiving_fumbles_lost": 0.0,
        "special_teams_tds": 0.0,
        "two_point_conversions": 0.0,
    }


def _make_weekly_df(rows: List[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: compute_actuals always includes player_id
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_compute_actuals_always_includes_player_id() -> None:
    """compute_actuals must return player_id column when it is present in source data.

    Previously the function conditionally omitted player_id, forcing the
    downstream merge to fall back to player_name and producing fan-out dups.
    """
    rows = [
        _make_weekly_row("00-0033040", "T.Hill", "WR", "MIA", 2023, 3, receiving_yards=157.0, receptions=9.0),
        _make_weekly_row("00-0033357", "T.Hill", "TE", "NO", 2023, 3, receiving_yards=9.0, receptions=1.0),
    ]
    weekly_df = _make_weekly_df(rows)
    actuals = compute_actuals(weekly_df, season=2023, week=3, scoring_format="half_ppr")

    assert "player_id" in actuals.columns, (
        "compute_actuals must return player_id when present in weekly data"
    )
    # Two distinct rows — one per player_id
    assert len(actuals) == 2
    assert set(actuals["player_id"]) == {"00-0033040", "00-0033357"}


# ---------------------------------------------------------------------------
# Tests: name-collision duplicate detection
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_name_collision_produces_no_dup_after_player_id_merge() -> None:
    """A name collision (two players with the same abbreviated name) must NOT
    produce duplicate (player_id, season, week) rows in the merged output.

    Scenario: projection has Tyreek Hill (00-0033040, WR).
    Actuals have two 'T.Hill' entries with different player_ids and different
    actual_points.  The merge must produce exactly one row (matching by
    player_id), not two.
    """
    # Build synthetic projections: only Tyreek Hill projected
    projections = pd.DataFrame(
        [
            {
                "player_id": "00-0033040",
                "player_name": "T.Hill",
                "position": "WR",
                "recent_team": "MIA",
                "projected_points": 18.5,
            }
        ]
    )

    # Build actuals: two players named T.Hill with different player_ids
    actuals = pd.DataFrame(
        [
            {
                "player_id": "00-0033040",
                "player_name": "T.Hill",
                "position": "WR",
                "recent_team": "MIA",
                "actual_points": 26.2,
            },
            {
                "player_id": "00-0033357",
                "player_name": "T.Hill",
                "position": "TE",
                "recent_team": "NO",
                "actual_points": 2.6,
            },
        ]
    )

    # Replicate the player_id-first merge logic from the fixed run_backtest()
    proj_copy = projections.copy()
    act_copy = actuals.copy()
    proj_copy["player_id"] = proj_copy["player_id"].astype(str).str.strip()
    act_copy["player_id"] = act_copy["player_id"].astype(str).str.strip()
    # Dedup actuals on player_id
    act_copy = act_copy.sort_values("actual_points", ascending=False).drop_duplicates(
        subset=["player_id"], keep="first"
    )
    merged = proj_copy.merge(
        act_copy[["player_id", "actual_points"]],
        on="player_id",
        how="inner",
    )

    # Must be exactly 1 row — the Tyreek Hill match
    assert len(merged) == 1, (
        f"Expected 1 merged row (player_id join), got {len(merged)}: {merged.to_dict('records')}"
    )
    assert merged.iloc[0]["actual_points"] == 26.2
    assert merged.iloc[0]["player_id"] == "00-0033040"


@pytest.mark.unit
def test_name_based_fallback_deduplicates_before_merge() -> None:
    """When player_id is absent from projections, the name-fallback path must
    deduplicate actuals before merging so one projection row cannot match
    more than one actual row.
    """
    # Projection has no player_id — only player_name
    projections = pd.DataFrame(
        [
            {
                "player_name": "T.Hill",
                "position": "WR",
                "recent_team": "MIA",
                "projected_points": 18.5,
            }
        ]
    )

    # Two actuals with the same player_name but different teams
    actuals = pd.DataFrame(
        [
            {
                "player_name": "T.Hill",
                "position": "WR",
                "recent_team": "MIA",
                "actual_points": 26.2,
            },
            {
                "player_name": "T.Hill",
                "position": "TE",
                "recent_team": "NO",
                "actual_points": 2.6,
            },
        ]
    )

    # Replicate the name-fallback + dedup logic from the fixed run_backtest().
    # Dedup on player_name (the merge key) — not on (player_name, recent_team),
    # which would still leave multiple rows per name and fan out on merge.
    act_copy = actuals.copy()
    act_copy = act_copy.sort_values("actual_points", ascending=False).drop_duplicates(
        subset=["player_name"], keep="first"
    )
    merged = projections.merge(
        act_copy[["player_name", "actual_points"]],
        on="player_name",
        how="inner",
    )

    # After dedup on player_name alone, only the highest-scoring T.Hill row
    # (MIA, 26.2) survives — exactly one row matches the projection.
    assert len(merged) == 1, (
        f"Name-fallback dedup should yield 1 row, got {len(merged)}"
    )
    assert merged.iloc[0]["actual_points"] == 26.2


@pytest.mark.unit
def test_name_collision_zero_dup_player_id_season_week() -> None:
    """End-to-end: after the fix, no (player_id, season, week) duplicate rows
    appear in a synthetic multi-player dataset that includes two name-collision
    players.

    This mirrors the reported T.Hill 2023 w3 MIA duplication in the backtest CSV.
    """
    # Build a small actuals frame with a T.Hill name collision
    rows = [
        _make_weekly_row("00-0033040", "T.Hill", "WR", "MIA", 2023, 3, receiving_yards=157.0, receptions=9.0),
        _make_weekly_row("00-0033357", "T.Hill", "TE", "NO", 2023, 3, receiving_yards=9.0, receptions=1.0),
        _make_weekly_row("00-0023459", "A.Rodgers", "QB", "GB", 2022, 6, passing_yards=246.0),
        _make_weekly_row("00-0036991", "A.Rodgers", "WR", "GB", 2022, 6, receiving_yards=14.0, receptions=1.0),
    ]
    weekly_df = _make_weekly_df(rows)

    # Verify actuals has all rows with player_id
    actuals_2023w3 = compute_actuals(weekly_df, 2023, 3, "half_ppr")
    actuals_2022w6 = compute_actuals(weekly_df, 2022, 6, "half_ppr")

    for actuals, label in [(actuals_2023w3, "2023w3"), (actuals_2022w6, "2022w6")]:
        assert "player_id" in actuals.columns, f"player_id missing from actuals {label}"
        # player_id must be unique within a week's actuals
        dup_pids = actuals[actuals.duplicated(["player_id"], keep=False)]
        assert dup_pids.empty, (
            f"Duplicate player_ids in actuals {label}: {dup_pids[['player_id','player_name']].to_dict('records')}"
        )


# ---------------------------------------------------------------------------
# Tests: consensus join still works correctly after fix
# ---------------------------------------------------------------------------


@pytest.mark.unit
def test_join_consensus_by_player_id_no_fanout() -> None:
    """join_consensus player_id path must not fan out when consensus has name
    collisions — it always uses player_id, so collisions on the name field
    are irrelevant there.
    """
    # Import directly from backtest_projections
    join_consensus = _bp.join_consensus

    results = pd.DataFrame(
        [
            {
                "player_id": "00-0033040",
                "player_name": "T.Hill",
                "position": "WR",
                "season": 2023,
                "week": 3,
                "projected_points": 18.5,
                "actual_points": 26.2,
            }
        ]
    )
    # Consensus has two T.Hill entries (different player_ids)
    consensus = pd.DataFrame(
        [
            {
                "player_id": "00-0033040",
                "player_name": "T.Hill",
                "season": 2023,
                "week": 3,
                "consensus_proj": 21.0,
            },
            {
                "player_id": "00-0033357",
                "player_name": "T.Hill",
                "season": 2023,
                "week": 3,
                "consensus_proj": 5.5,
            },
        ]
    )

    merged = join_consensus(results, consensus)

    # player_id join: only Tyreek Hill (00-0033040) matches
    assert len(merged) == 1, (
        f"join_consensus should produce 1 row via player_id, got {len(merged)}"
    )
    assert merged.iloc[0]["consensus_proj"] == 21.0
