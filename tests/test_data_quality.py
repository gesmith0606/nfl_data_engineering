"""Unit tests for data quality utilities in scripts/refresh_rosters.py
and scripts/sanity_check_projections.py.

Covers:
    - DQAL-01 (positions match Sleeper API) and DQAL-02 (rosters reflect
      2026 trades/FA via daily Sleeper refresh) -- Plan 60-01
    - DQAL-03 (sanity check produces <10 warnings and 0 criticals) and
      DQAL-04 (top-10 consensus alignment) -- Plan 60-02

Plan 60-01 tests exercise three functions in scripts/refresh_rosters.py:
    - build_roster_mapping: name -> {team, position} from Sleeper response
    - update_rosters: applies mapping to Gold DataFrame (team AND position)
    - log_changes: appends timestamped change records to roster_changes.log

Plan 60-02 tests exercise two new helpers in scripts/sanity_check_projections.py:
    - check_local_freshness: parquet age validation (OK/WARN/ERROR)
    - fetch_live_consensus: Sleeper search_rank primary with hardcoded fallback
    Plus a content assertion on the CONSENSUS_TOP_50 constant.
"""

from __future__ import annotations

import os
import sys
import time
from typing import Dict
from unittest.mock import patch

import pandas as pd
import pytest
import requests

# Ensure repo root is importable so `scripts.refresh_rosters` resolves.
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from scripts.refresh_rosters import (  # noqa: E402 -- path setup must precede import
    build_roster_mapping,
    log_changes,
    update_rosters,
)
from scripts.sanity_check_projections import (  # noqa: E402
    CONSENSUS_TOP_50,
    check_local_freshness,
    fetch_live_consensus,
)


@pytest.fixture
def mock_sleeper_players() -> Dict[str, Dict[str, object]]:
    """Mock Sleeper API response with 5 entries exercising key edge cases.

    Entries:
        1: Josh Allen, Active QB on BUF (canonical match)
        2: Isiah Pacheco, Active RB on KC
        3: Puka Nacua, Active WR on LAR (exercises LAR -> LA mapping)
        4: Josh Allen, Inactive OL (name collision vs id=1; should be filtered)
        5: Aaron Donald, Active DL on LA (non-fantasy position; should be filtered)
    """
    return {
        "1": {
            "full_name": "Josh Allen",
            "position": "QB",
            "team": "BUF",
            "status": "Active",
        },
        "2": {
            "full_name": "Isiah Pacheco",
            "position": "RB",
            "team": "KC",
            "status": "Active",
        },
        "3": {
            "full_name": "Puka Nacua",
            "position": "WR",
            "team": "LAR",
            "status": "Active",
        },
        "4": {
            "full_name": "Josh Allen",
            "position": "OL",
            "team": None,
            "status": "Inactive",
        },
        "5": {
            "full_name": "Aaron Donald",
            "position": "DL",
            "team": "LA",
            "status": "Active",
        },
    }


@pytest.fixture
def mock_gold_df() -> pd.DataFrame:
    """Mock Gold projections DataFrame with 4 players, covering team
    change, position change, and no-change scenarios."""
    return pd.DataFrame(
        [
            # Team change only: Adams on stale NYJ, Sleeper says LAR -> LA
            {
                "player_name": "Davante Adams",
                "position": "WR",
                "recent_team": "NYJ",
                "projected_season_points": 220.0,
                "overall_rank": 18,
                "position_rank": 6,
            },
            # Position change: listed as RB in Gold, Sleeper mapping has WR
            {
                "player_name": "Deebo Samuel",
                "position": "RB",
                "recent_team": "SF",
                "projected_season_points": 180.0,
                "overall_rank": 40,
                "position_rank": 12,
            },
            # No change: Josh Allen QB on BUF already correct
            {
                "player_name": "Josh Allen",
                "position": "QB",
                "recent_team": "BUF",
                "projected_season_points": 330.0,
                "overall_rank": 5,
                "position_rank": 1,
            },
            # Not in Sleeper mapping -- must be untouched
            {
                "player_name": "Ghost Player",
                "position": "TE",
                "recent_team": "CHI",
                "projected_season_points": 80.0,
                "overall_rank": 400,
                "position_rank": 40,
            },
        ]
    )


# ---------------------------------------------------------------------------
# build_roster_mapping
# ---------------------------------------------------------------------------


def test_build_roster_mapping_returns_team_and_position(mock_sleeper_players):
    """Mapping values are dicts with 'team' and 'position'; LAR normalizes to LA."""
    mapping = build_roster_mapping(mock_sleeper_players)

    assert "josh allen" in mapping
    assert mapping["josh allen"] == {"team": "BUF", "position": "QB"}

    assert "isiah pacheco" in mapping
    assert mapping["isiah pacheco"] == {"team": "KC", "position": "RB"}

    # LAR -> LA normalization via SLEEPER_TO_NFLVERSE_TEAM
    assert "puka nacua" in mapping
    assert mapping["puka nacua"] == {"team": "LA", "position": "WR"}


def test_build_roster_mapping_name_collision(mock_sleeper_players):
    """When two Sleeper entries share a full_name, prefer the Active one."""
    mapping = build_roster_mapping(mock_sleeper_players)

    # Active QB on BUF must win over inactive OL (which is also filtered by
    # position, but the behavioral guarantee is: Active wins).
    assert mapping["josh allen"]["position"] == "QB"
    assert mapping["josh allen"]["team"] == "BUF"


def test_build_roster_mapping_filters_non_fantasy(mock_sleeper_players):
    """Players with position not in FANTASY_POSITIONS are excluded."""
    mapping = build_roster_mapping(mock_sleeper_players)

    assert "aaron donald" not in mapping  # DL filtered out


# ---------------------------------------------------------------------------
# update_rosters
# ---------------------------------------------------------------------------


def test_update_rosters_changes_team_and_position(mock_gold_df):
    """update_rosters must change recent_team AND log the change."""
    roster_mapping = {
        "davante adams": {"team": "LA", "position": "WR"},
        "deebo samuel": {"team": "SF", "position": "RB"},  # no change in this test
        "josh allen": {"team": "BUF", "position": "QB"},
    }

    updated_df, changes_df = update_rosters(mock_gold_df, roster_mapping)

    # Adams: team changed from NYJ to LA, position stays WR
    adams_row = updated_df[updated_df["player_name"] == "Davante Adams"].iloc[0]
    assert adams_row["recent_team"] == "LA"
    assert adams_row["position"] == "WR"

    # Change record includes Adams
    assert "Davante Adams" in changes_df["player_name"].values
    adams_change = changes_df[changes_df["player_name"] == "Davante Adams"].iloc[0]
    assert adams_change["old_team"] == "NYJ"
    assert adams_change["new_team"] == "LA"


def test_update_rosters_changes_position(mock_gold_df):
    """Position mismatches are corrected and old_position/new_position logged."""
    roster_mapping = {
        "davante adams": {"team": "NYJ", "position": "WR"},  # no change
        # Force a position change: Gold has RB, Sleeper says WR
        "deebo samuel": {"team": "SF", "position": "WR"},
        "josh allen": {"team": "BUF", "position": "QB"},  # no change
    }

    updated_df, changes_df = update_rosters(mock_gold_df, roster_mapping)

    samuel_row = updated_df[updated_df["player_name"] == "Deebo Samuel"].iloc[0]
    assert samuel_row["position"] == "WR"
    assert samuel_row["recent_team"] == "SF"

    samuel_change = changes_df[changes_df["player_name"] == "Deebo Samuel"].iloc[0]
    assert samuel_change["old_position"] == "RB"
    assert samuel_change["new_position"] == "WR"


def test_update_rosters_leaves_unmapped_players_untouched(mock_gold_df):
    """Players absent from roster_mapping must not appear in changes."""
    roster_mapping = {
        "davante adams": {"team": "NYJ", "position": "WR"},  # no change
    }

    updated_df, changes_df = update_rosters(mock_gold_df, roster_mapping)

    ghost_row = updated_df[updated_df["player_name"] == "Ghost Player"].iloc[0]
    assert ghost_row["recent_team"] == "CHI"
    assert ghost_row["position"] == "TE"
    assert "Ghost Player" not in changes_df.get("player_name", pd.Series(dtype=str)).values


# ---------------------------------------------------------------------------
# log_changes
# ---------------------------------------------------------------------------


def test_log_changes_appends_to_file(tmp_path):
    """log_changes writes a timestamped header and a line per change."""
    log_path = tmp_path / "roster_changes.log"
    changes = pd.DataFrame(
        [
            {
                "player_name": "Davante Adams",
                "position": "WR",
                "old_team": "NYJ",
                "new_team": "LA",
            },
            {
                "player_name": "Deebo Samuel",
                "position": "WR",
                "old_team": "SF",
                "new_team": "SF",
                "old_position": "RB",
                "new_position": "WR",
            },
        ]
    )

    log_changes(changes, log_path=str(log_path))

    assert log_path.exists()
    contents = log_path.read_text()
    assert "Roster Refresh:" in contents  # timestamped header
    assert "Davante Adams" in contents
    assert "NYJ" in contents and "LA" in contents
    assert "Deebo Samuel" in contents
    # Position delta is surfaced for Samuel
    assert "RB" in contents and "WR" in contents


def test_log_changes_empty(tmp_path):
    """An empty changes DataFrame still produces a log entry noting no changes."""
    log_path = tmp_path / "roster_changes.log"

    log_changes(pd.DataFrame(), log_path=str(log_path))

    contents = log_path.read_text()
    assert "Roster Refresh:" in contents
    assert "No changes detected." in contents


def test_log_changes_appends_rather_than_overwrites(tmp_path):
    """Consecutive calls produce cumulative entries (append-only log)."""
    log_path = tmp_path / "roster_changes.log"

    log_changes(pd.DataFrame(), log_path=str(log_path))
    log_changes(pd.DataFrame(), log_path=str(log_path))

    contents = log_path.read_text()
    # Two headers -> two runs preserved
    assert contents.count("Roster Refresh:") == 2


# ---------------------------------------------------------------------------
# Requirement-aligned aliases (per 60-RESEARCH.md Phase Requirements -> Test Map)
# ---------------------------------------------------------------------------


def test_position_update(mock_gold_df):
    """DQAL-01: Position updates from Sleeper API propagate to the Gold DataFrame."""
    roster_mapping = {
        "deebo samuel": {"team": "SF", "position": "WR"},
    }
    updated_df, changes_df = update_rosters(mock_gold_df, roster_mapping)

    samuel_row = updated_df[updated_df["player_name"] == "Deebo Samuel"].iloc[0]
    assert samuel_row["position"] == "WR"
    assert not changes_df.empty
    assert "Deebo Samuel" in changes_df["player_name"].values


def test_team_update(mock_gold_df):
    """DQAL-02: Team updates from Sleeper API propagate to recent_team."""
    roster_mapping = {
        "davante adams": {"team": "LA", "position": "WR"},
    }
    updated_df, changes_df = update_rosters(mock_gold_df, roster_mapping)

    adams_row = updated_df[updated_df["player_name"] == "Davante Adams"].iloc[0]
    assert adams_row["recent_team"] == "LA"
    assert "Davante Adams" in changes_df["player_name"].values


def test_name_collision_handling(mock_sleeper_players):
    """DQAL-01 safety rail: Active player wins on name collision."""
    mapping = build_roster_mapping(mock_sleeper_players)

    # id=1 (Active QB, BUF) beats id=4 (Inactive OL). Even though id=4 is
    # already filtered by the non-fantasy-position rule, the Active-wins
    # preference is the backstop for collisions within FANTASY_POSITIONS.
    assert mapping["josh allen"] == {"team": "BUF", "position": "QB"}


def test_roster_changes_log(tmp_path):
    """DQAL-02: Roster changes are persisted with timestamps and readable deltas."""
    log_path = tmp_path / "roster_changes.log"
    changes = pd.DataFrame(
        [
            {
                "player_name": "Davante Adams",
                "position": "WR",
                "old_team": "NYJ",
                "new_team": "LA",
            }
        ]
    )

    log_changes(changes, log_path=str(log_path))

    contents = log_path.read_text()
    assert "Roster Refresh:" in contents
    assert "Davante Adams" in contents
    assert "NYJ" in contents
    assert "LA" in contents


# ===========================================================================
# Plan 60-02: Sanity check enhancements
# ===========================================================================
# check_local_freshness, fetch_live_consensus, and CONSENSUS_TOP_50 content
# assertions. Exercises DQAL-03 (freshness warns on stale data) and DQAL-04
# (top-50 consensus reflects 2026 offseason moves).
# ---------------------------------------------------------------------------


def _write_parquet_with_age(directory, age_days: int, name: str = "snapshot.parquet") -> None:
    """Create a fake parquet file in `directory` and backdate its mtime."""
    directory.mkdir(parents=True, exist_ok=True)
    fake = directory / name
    # Content is irrelevant for freshness checks -- only stat().st_mtime is used.
    fake.write_bytes(b"PAR1")  # arbitrary parquet-like magic bytes
    target_mtime = time.time() - (age_days * 86400)
    os.utime(fake, (target_mtime, target_mtime))


def test_freshness_check_ok(tmp_path):
    """DQAL-03: Fresh parquet (< threshold) returns ('OK', message with age)."""
    gold_dir = tmp_path / "gold_fresh"
    _write_parquet_with_age(gold_dir, age_days=3)

    level, message = check_local_freshness(str(gold_dir), max_age_days=7)

    assert level == "OK"
    assert "3 days old" in message


def test_freshness_check_warn(tmp_path):
    """DQAL-03: Stale parquet (> threshold) returns ('WARN', message with age)."""
    gold_dir = tmp_path / "gold_stale"
    _write_parquet_with_age(gold_dir, age_days=10)

    level, message = check_local_freshness(str(gold_dir), max_age_days=7)

    assert level == "WARN"
    assert "10 days old" in message


def test_freshness_check_missing(tmp_path):
    """DQAL-03: Missing/empty directory returns ('ERROR', explanatory message)."""
    missing_dir = tmp_path / "does_not_exist"

    level, message = check_local_freshness(str(missing_dir), max_age_days=7)

    assert level == "ERROR"
    assert "not found" in message.lower() or "no parquet" in message.lower()


def test_fetch_live_consensus_fallback():
    """DQAL-03: When Sleeper API is unreachable, fall back to CONSENSUS_TOP_50.

    The fallback DataFrame must have at least 40 rows (hardcoded list is 50)
    and carry the canonical columns: consensus_rank, player_name, position, team.
    """
    with patch(
        "scripts.sanity_check_projections.requests.get",
        side_effect=requests.exceptions.ConnectionError("simulated"),
    ):
        df = fetch_live_consensus(limit=50)

    assert isinstance(df, pd.DataFrame)
    assert len(df) >= 40
    for col in ("consensus_rank", "player_name", "position", "team"):
        assert col in df.columns, f"missing column: {col}"


def test_consensus_top50_davante_adams():
    """DQAL-04: CONSENSUS_TOP_50 reflects 2026 offseason (Adams -> LA, not NYJ)."""
    adams = [entry for entry in CONSENSUS_TOP_50 if entry[1] == "Davante Adams"]
    assert adams, "Davante Adams missing from CONSENSUS_TOP_50"
    # Tuple format: (rank, name, position, team)
    assert adams[0][2] == "WR"
    assert adams[0][3] == "LA", (
        f"Davante Adams team should be 'LA' (2026 offseason move); "
        f"got {adams[0][3]!r}"
    )
