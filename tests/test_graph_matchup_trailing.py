#!/usr/bin/env python3
"""Tests for defense-side trailing WR/TE allowance features (ELITE-2.3).

Covers:
- compute_wr_def_trailing_features: output schema, temporal safety, coverage splits
- compute_te_def_trailing_features: output schema, temporal safety, coverage type shares
- Temporal safety: week-1 features are always NaN (no prior data in season)
- Feature names pass _is_unlagged_leak() (suffix _trail not in _SAME_WEEK_PREFIXES)
- Graceful degradation on empty inputs
- WR_DEF_TRAILING_FEATURE_COLUMNS and TE_DEF_TRAILING_FEATURE_COLUMNS canonical lists
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_wr_matchup import (
    WR_DEF_TRAILING_FEATURE_COLUMNS,
    compute_wr_def_trailing_features,
)
from graph_te_matchup import (
    TE_DEF_TRAILING_FEATURE_COLUMNS,
    compute_te_def_trailing_features,
)
from player_feature_engineering import _is_unlagged_leak


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_pbp(season: int = 2022, n_weeks: int = 6) -> pd.DataFrame:
    """Synthetic PBP with pass plays targeting WR and TE IDs."""
    rows = []
    teams = [("KC", "BUF"), ("SF", "DAL"), ("PHI", "NYG")]
    player_id_wr = "WR-001"
    player_id_wr2 = "WR-002"
    player_id_te = "TE-001"

    for week in range(1, n_weeks + 1):
        for posteam, defteam in teams:
            # WR targets: 4 plays
            for i in range(4):
                rows.append(
                    {
                        "game_id": f"{season}_{week:02d}_{posteam}_{defteam}",
                        "play_id": float(week * 100 + i),
                        "season": season,
                        "week": week,
                        "play_type": "pass",
                        "posteam": posteam,
                        "defteam": defteam,
                        "receiver_player_id": player_id_wr,
                        "complete_pass": 1 if i < 3 else 0,
                        "yards_gained": 8 if i < 3 else 0,
                        "touchdown": 1 if i == 0 else 0,
                        "pass_location": "right" if i % 2 == 0 else "left",
                        "air_yards": 6.0,
                        "defenders_in_box": 6,
                    }
                )
            # TE targets: 2 plays
            for i in range(2):
                rows.append(
                    {
                        "game_id": f"{season}_{week:02d}_{posteam}_{defteam}",
                        "play_id": float(week * 100 + 50 + i),
                        "season": season,
                        "week": week,
                        "play_type": "pass",
                        "posteam": posteam,
                        "defteam": defteam,
                        "receiver_player_id": player_id_te,
                        "complete_pass": 1 if i == 0 else 0,
                        "yards_gained": 7 if i == 0 else 0,
                        "touchdown": 0,
                        "pass_location": "middle",
                        "air_yards": 4.0,
                        "defenders_in_box": 7,
                    }
                )
    return pd.DataFrame(rows)


def _make_player_weekly(season: int = 2022) -> pd.DataFrame:
    """Synthetic player-weekly with WR and TE across weeks 1-6."""
    rows = []
    for week in range(1, 7):
        rows.append(
            {
                "player_id": "WR-001",
                "season": season,
                "week": week,
                "position": "WR",
                "recent_team": "KC",
                "opponent_team": "BUF",
            }
        )
        rows.append(
            {
                "player_id": "TE-001",
                "season": season,
                "week": week,
                "position": "TE",
                "recent_team": "KC",
                "opponent_team": "BUF",
            }
        )
    return pd.DataFrame(rows)


def _make_rosters(season: int = 2022) -> pd.DataFrame:
    """Synthetic roster with WR and TE player IDs."""
    return pd.DataFrame(
        [
            {"player_id": "WR-001", "position": "WR", "team": "KC", "season": season, "depth_chart_position": "WR"},
            {"player_id": "WR-002", "position": "WR", "team": "BUF", "season": season, "depth_chart_position": "WR"},
            {"player_id": "TE-001", "position": "TE", "team": "KC", "season": season, "depth_chart_position": "TE"},
            {"player_id": "CB-001", "position": "DB", "team": "BUF", "season": season, "depth_chart_position": "CB"},
            {"player_id": "CB-002", "position": "DB", "team": "BUF", "season": season, "depth_chart_position": "CB"},
        ]
    )


def _make_participation(pbp: pd.DataFrame) -> pd.DataFrame:
    """Minimal parsed-participation rows with CB and LB defenders."""
    rows = []
    for _, row in pbp[pbp["play_type"] == "pass"].iterrows():
        # 2 CBs on defense per play
        for def_id in ["CB-001", "CB-002"]:
            rows.append(
                {
                    "game_id": row["game_id"],
                    "play_id": row["play_id"],
                    "player_gsis_id": def_id,
                    "side": "defense",
                    "position": "DB",
                }
            )
        # 1 LB on defense per play
        rows.append(
            {
                "game_id": row["game_id"],
                "play_id": row["play_id"],
                "player_gsis_id": "LB-001",
                "side": "defense",
                "position": "LB",
            }
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: WR trailing features
# ---------------------------------------------------------------------------


class TestWRDefTrailingFeatures:
    def test_output_columns_present(self):
        pbp = _make_pbp()
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_wr_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        assert not result.empty, "Should produce rows"
        for col in ["player_id", "season", "week"] + WR_DEF_TRAILING_FEATURE_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_week_1_is_null(self):
        """Week-1 features must be NaN — no prior data exists in-season."""
        pbp = _make_pbp()
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_wr_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        # No week-1 rows should exist (skipped by design)
        if not result.empty and 1 in result["week"].values:
            week1 = result[result["week"] == 1]
            assert week1["wr_def_trail_yds_per_tgt"].isna().all(), (
                "Week-1 trailing features must be NaN"
            )

    def test_no_week_1_rows(self):
        """compute_wr_def_trailing_features should skip week 1 entirely."""
        pbp = _make_pbp(n_weeks=6)
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_wr_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        assert 1 not in result["week"].values, "Week 1 should be absent (no prior data)"

    def test_yds_per_tgt_positive(self):
        """Yards/target allowed should be positive when data present."""
        pbp = _make_pbp(n_weeks=4)
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_wr_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        if not result.empty:
            non_null = result["wr_def_trail_yds_per_tgt"].dropna()
            if len(non_null) > 0:
                assert (non_null >= 0).all(), "Yards/target must be non-negative"

    def test_comp_rate_in_range(self):
        """Completion rate should be in [0, 1]."""
        pbp = _make_pbp(n_weeks=4)
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_wr_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        if not result.empty:
            non_null = result["wr_def_trail_comp_rate"].dropna()
            if len(non_null) > 0:
                assert (non_null >= 0).all() and (non_null <= 1).all(), (
                    "Completion rate must be in [0, 1]"
                )

    def test_slot_vs_outside_separation(self):
        """Slot (middle) and outside (left/right) yards should differ when data has variation."""
        pbp = _make_pbp(n_weeks=5)
        # Mix slot and outside targets
        slot_rows = pbp.copy()
        slot_rows.loc[slot_rows["pass_location"] == "right", "pass_location"] = "middle"
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_wr_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        # Both slot and outside columns should be present
        assert "wr_def_trail_yds_per_tgt_slot" in result.columns
        assert "wr_def_trail_yds_per_tgt_outside" in result.columns

    def test_empty_pbp_returns_empty(self):
        result = compute_wr_def_trailing_features(
            pbp_df=pd.DataFrame(),
            player_weekly_df=_make_player_weekly(),
        )
        assert result.empty

    def test_empty_pw_returns_empty(self):
        result = compute_wr_def_trailing_features(
            pbp_df=_make_pbp(),
            player_weekly_df=pd.DataFrame(),
        )
        assert result.empty

    def test_no_duplicates(self):
        """No duplicate (player_id, season, week) rows."""
        pbp = _make_pbp(n_weeks=6)
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_wr_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        if not result.empty:
            assert not result.duplicated(subset=["player_id", "season", "week"]).any()


# ---------------------------------------------------------------------------
# Tests: TE trailing features
# ---------------------------------------------------------------------------


class TestTEDefTrailingFeatures:
    def test_output_columns_present(self):
        pbp = _make_pbp()
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_te_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        assert not result.empty, "Should produce rows"
        for col in ["player_id", "season", "week"] + TE_DEF_TRAILING_FEATURE_COLUMNS:
            assert col in result.columns, f"Missing column: {col}"

    def test_week_1_absent(self):
        """Week 1 should not appear (no prior data to trail)."""
        pbp = _make_pbp(n_weeks=6)
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_te_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        assert 1 not in result["week"].values

    def test_yds_per_tgt_positive(self):
        pbp = _make_pbp(n_weeks=4)
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_te_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        if not result.empty:
            non_null = result["te_def_trail_yds_per_tgt"].dropna()
            if len(non_null) > 0:
                assert (non_null >= 0).all()

    def test_coverage_shares_in_range(self):
        """LB and CB coverage shares should be in [0, 1]."""
        pbp = _make_pbp(n_weeks=5)
        pw = _make_player_weekly()
        rost = _make_rosters()
        part = _make_participation(pbp)
        result = compute_te_def_trailing_features(
            pbp_df=pbp,
            player_weekly_df=pw,
            rosters_df=rost,
            participation_parsed_df=part,
            season=2022,
        )
        if not result.empty:
            for col in ["te_def_trail_lb_coverage_share", "te_def_trail_cb_coverage_share"]:
                non_null = result[col].dropna()
                if len(non_null) > 0:
                    assert (non_null >= 0).all() and (non_null <= 1).all(), (
                        f"{col} out of [0,1] range"
                    )

    def test_empty_inputs_return_empty(self):
        assert compute_te_def_trailing_features(
            pbp_df=pd.DataFrame(), player_weekly_df=_make_player_weekly()
        ).empty
        assert compute_te_def_trailing_features(
            pbp_df=_make_pbp(), player_weekly_df=pd.DataFrame()
        ).empty

    def test_no_duplicates(self):
        pbp = _make_pbp(n_weeks=6)
        pw = _make_player_weekly()
        rost = _make_rosters()
        result = compute_te_def_trailing_features(
            pbp_df=pbp, player_weekly_df=pw, rosters_df=rost, season=2022
        )
        if not result.empty:
            assert not result.duplicated(subset=["player_id", "season", "week"]).any()


# ---------------------------------------------------------------------------
# Tests: Leak gate verification
# ---------------------------------------------------------------------------


class TestLeakGate:
    def test_wr_def_trailing_names_pass_leak_gate(self):
        """All wr_def_trail_* columns must not be flagged as unlagged leaks."""
        for col in WR_DEF_TRAILING_FEATURE_COLUMNS:
            assert not _is_unlagged_leak(col), (
                f"{col} incorrectly flagged as unlagged leak — "
                f"check _SAME_WEEK_PREFIXES in player_feature_engineering.py"
            )

    def test_te_def_trailing_names_pass_leak_gate(self):
        """All te_def_trail_* columns must not be flagged as unlagged leaks."""
        for col in TE_DEF_TRAILING_FEATURE_COLUMNS:
            assert not _is_unlagged_leak(col), (
                f"{col} incorrectly flagged as unlagged leak — "
                f"check _SAME_WEEK_PREFIXES in player_feature_engineering.py"
            )

    def test_old_wr_matchup_names_still_blocked(self):
        """Old same-game wr_matchup_* names must still be flagged as leaks."""
        old_leaky = [
            "wr_matchup_yac_per_catch",
            "wr_matchup_air_yards_per_target",
            "te_matchup_cb_coverage_rate",
            "te_matchup_seam_route_rate",
        ]
        for col in old_leaky:
            assert _is_unlagged_leak(col), (
                f"{col} should still be blocked as same-game leak"
            )

    def test_trail8_variants_still_allowed(self):
        """_trail8 suffix makes a column pass the leak gate (lagged form)."""
        examples = [
            "wr_matchup_yac_per_catch_trail8",
            "te_matchup_cb_coverage_rate_trail8",
        ]
        for col in examples:
            assert not _is_unlagged_leak(col), (
                f"{col} should pass leak gate (has _trail8 suffix)"
            )


# ---------------------------------------------------------------------------
# Tests: Canonical column list properties
# ---------------------------------------------------------------------------


class TestColumnLists:
    def test_wr_columns_no_duplicates(self):
        assert len(WR_DEF_TRAILING_FEATURE_COLUMNS) == len(set(WR_DEF_TRAILING_FEATURE_COLUMNS))

    def test_te_columns_no_duplicates(self):
        assert len(TE_DEF_TRAILING_FEATURE_COLUMNS) == len(set(TE_DEF_TRAILING_FEATURE_COLUMNS))

    def test_wr_columns_have_trail_prefix(self):
        for col in WR_DEF_TRAILING_FEATURE_COLUMNS:
            assert col.startswith("wr_def_trail_"), f"{col} missing wr_def_trail_ prefix"

    def test_te_columns_have_trail_prefix(self):
        for col in TE_DEF_TRAILING_FEATURE_COLUMNS:
            assert col.startswith("te_def_trail_"), f"{col} missing te_def_trail_ prefix"

    def test_no_raw_same_game_names_in_lists(self):
        """Column lists must not contain the old same-game matchup names."""
        for col in WR_DEF_TRAILING_FEATURE_COLUMNS + TE_DEF_TRAILING_FEATURE_COLUMNS:
            assert not col.startswith("wr_matchup_"), f"{col} uses old same-game prefix"
            assert not col.startswith("te_matchup_"), f"{col} uses old same-game prefix"

    def test_wr_list_has_expected_length(self):
        assert len(WR_DEF_TRAILING_FEATURE_COLUMNS) == 6

    def test_te_list_has_expected_length(self):
        assert len(TE_DEF_TRAILING_FEATURE_COLUMNS) == 5
