#!/usr/bin/env python3
"""Tests for advanced TE matchup features in graph_te_matchup.py.

Covers:
- build_te_advanced_matchup_features output schema and column presence
- CB/DB coverage rate computation from participation data
- Seam route rate and seam completion rate (middle + air_yards > 10)
- Red zone personnel LB rate (targets inside yardline_100 <= 20)
- Blocking proxy rate via defenders_in_box >= 7 on targeted plays
- WR receivers excluded (only TE position appears in output)
- Empty/missing data handled gracefully with NaN fallback
- ingest_te_matchup_graph accepts optional advanced_features_df
"""

import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

# ---------------------------------------------------------------------------
# Expected output columns
# ---------------------------------------------------------------------------

ADVANCED_TE_COLUMNS = [
    "te_matchup_cb_coverage_rate",
    "te_matchup_seam_route_rate",
    "te_matchup_seam_completion_rate",
    "te_matchup_rz_personnel_lb_rate",
    "te_matchup_blocking_proxy_rate",
]

KEY_COLUMNS = ["receiver_player_id", "defteam", "season", "week"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def rosters_df():
    """Synthetic roster with two TEs, one WR."""
    return pd.DataFrame(
        {
            "player_id": ["TE01", "TE02", "WR01", "QB01"],
            "team": ["KC", "KC", "KC", "KC"],
            "position": ["TE", "TE", "WR", "QB"],
        }
    )


@pytest.fixture
def pbp_df():
    """Synthetic PBP covering pass plays with diverse TE targeting patterns.

    Plays:
      1: TE01, middle, ay=12 (seam), yardline=50, dib=5 (light)
      2: TE01, left,   ay=4  (short), yardline=50, dib=7 (heavy/blocking proxy)
      3: TE01, middle, ay=15 (seam), yardline=15, dib=6 (light, red zone)
      4: TE02, middle, ay=6  (not seam <10), yardline=40, dib=8 (heavy)
      5: WR01, left,   ay=8,  yardline=30, dib=6 — should be excluded
    """
    return pd.DataFrame(
        {
            "game_id": ["2024_01_KC_BUF"] * 5,
            "play_id": [1, 2, 3, 4, 5],
            "season": [2024] * 5,
            "week": [1] * 5,
            "play_type": ["pass"] * 5,
            "posteam": ["KC"] * 5,
            "defteam": ["BUF"] * 5,
            "receiver_player_id": ["TE01", "TE01", "TE01", "TE02", "WR01"],
            "complete_pass": [1, 0, 1, 1, 1],
            "yards_gained": [18, 0, 5, 8, 20],
            "touchdown": [0, 0, 1, 0, 0],
            "epa": [0.8, -0.3, 1.5, 0.2, 0.9],
            "air_yards": [12.0, 4.0, 15.0, 6.0, 8.0],
            "pass_location": ["middle", "left", "middle", "middle", "left"],
            "yardline_100": [50, 50, 15, 40, 30],
            "defenders_in_box": [5, 7, 6, 8, 6],
        }
    )


@pytest.fixture
def participation_df():
    """Synthetic participation with LBs, safeties, and CBs on defense."""
    rows = []
    # Plays 1-4: 1 LB, 1 safety, 1 CB on defense
    for play_id in [1, 2, 3, 4]:
        rows.extend(
            [
                {
                    "game_id": "2024_01_KC_BUF",
                    "play_id": play_id,
                    "player_gsis_id": "LB01",
                    "side": "defense",
                    "position": "LB",
                },
                {
                    "game_id": "2024_01_KC_BUF",
                    "play_id": play_id,
                    "player_gsis_id": "S01",
                    "side": "defense",
                    "position": "S",
                },
                {
                    "game_id": "2024_01_KC_BUF",
                    "play_id": play_id,
                    "player_gsis_id": "CB01",
                    "side": "defense",
                    "position": "CB",
                },
            ]
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Tests: output schema
# ---------------------------------------------------------------------------


class TestBuildTeAdvancedMatchupFeaturesSchema:
    """Verify output schema of build_te_advanced_matchup_features."""

    def test_output_contains_key_columns(self, pbp_df, participation_df, rosters_df):
        """Output must contain receiver_player_id, defteam, season, week."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        for col in KEY_COLUMNS:
            assert col in result.columns, f"Missing key column: {col}"

    def test_output_contains_all_advanced_columns(
        self, pbp_df, participation_df, rosters_df
    ):
        """All te_matchup_* feature columns must be present."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        for col in ADVANCED_TE_COLUMNS:
            assert col in result.columns, f"Missing feature column: {col}"

    def test_feature_columns_are_numeric(self, pbp_df, participation_df, rosters_df):
        """All te_matchup_* columns must be float dtype."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        for col in ADVANCED_TE_COLUMNS:
            assert pd.api.types.is_float_dtype(
                result[col]
            ), f"{col} should be float, got {result[col].dtype}"

    def test_one_row_per_te_defteam_season_week(
        self, pbp_df, participation_df, rosters_df
    ):
        """Each (TE, defteam, season, week) combination produces a single row."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        assert result.duplicated(subset=KEY_COLUMNS).sum() == 0

    def test_empty_pbp_returns_empty(self, participation_df, rosters_df):
        """Empty PBP returns empty DataFrame without raising."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pd.DataFrame(), participation_df, rosters_df
        )

        assert result.empty

    def test_empty_rosters_returns_empty(self, pbp_df, participation_df):
        """Empty rosters (cannot identify TEs) returns empty DataFrame."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, pd.DataFrame()
        )

        assert result.empty

    def test_no_te_in_rosters_returns_empty(self, pbp_df, participation_df):
        """Roster with no TE position entries returns empty DataFrame."""
        from graph_te_matchup import build_te_advanced_matchup_features

        rosters = pd.DataFrame(
            {"player_id": ["WR01", "QB01"], "position": ["WR", "QB"]}
        )
        result = build_te_advanced_matchup_features(pbp_df, participation_df, rosters)

        assert result.empty


# ---------------------------------------------------------------------------
# Tests: only TE receivers appear in output
# ---------------------------------------------------------------------------


class TestOnlyTeReceiversInOutput:
    """WR01 must be excluded; only TE01 and TE02 appear."""

    def test_wr_excluded(self, pbp_df, participation_df, rosters_df):
        """WR01 must not appear in the output."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        assert "WR01" not in result["receiver_player_id"].values

    def test_both_tes_present(self, pbp_df, participation_df, rosters_df):
        """TE01 and TE02 both have targets and must appear."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        player_ids = set(result["receiver_player_id"].unique())
        assert "TE01" in player_ids
        assert "TE02" in player_ids


# ---------------------------------------------------------------------------
# Tests: CB coverage rate
# ---------------------------------------------------------------------------


class TestCbCoverageRate:
    """te_matchup_cb_coverage_rate = CBs / (LBs + safeties + CBs) on TE targets."""

    def test_te01_cb_coverage_rate(self, pbp_df, participation_df, rosters_df):
        """Each play has 1 LB + 1 S + 1 CB = 3 total; CB rate = 1/3."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        # 3 targeted plays, each with 1 CB / 3 defenders = 1/3 rate overall
        # sum(cb) = 3, sum(lb+s+cb) = 9 -> 3/9 = 1/3
        assert abs(te01["te_matchup_cb_coverage_rate"] - 1.0 / 3.0) < 1e-6

    def test_no_participation_data_gives_nan(self, pbp_df, rosters_df):
        """Without participation data, cb_coverage_rate should be NaN."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(pbp_df, pd.DataFrame(), rosters_df)

        assert result["te_matchup_cb_coverage_rate"].isna().all()


# ---------------------------------------------------------------------------
# Tests: seam route rate and completion rate
# ---------------------------------------------------------------------------


class TestSeamRouteFeatures:
    """Seam route = middle pass_location + air_yards > 10."""

    def test_te01_seam_route_rate(self, pbp_df, participation_df, rosters_df):
        """TE01: plays 1(middle,ay=12->seam) and 3(middle,ay=15->seam) of 3 targets."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        # 2 seam plays of 3 targets = 2/3
        assert abs(te01["te_matchup_seam_route_rate"] - 2.0 / 3.0) < 1e-6

    def test_te01_seam_completion_rate(self, pbp_df, participation_df, rosters_df):
        """TE01 seam plays: play1(complete=1), play3(complete=1) -> 2/2=1.0."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        assert abs(te01["te_matchup_seam_completion_rate"] - 1.0) < 1e-6

    def test_te02_no_seam_routes(self, pbp_df, participation_df, rosters_df):
        """TE02: only target is middle but air_yards=6 (<10) -> not a seam.

        seam_route_rate == 0.0, seam_completion_rate == NaN.
        """
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )
        te02 = result[result["receiver_player_id"] == "TE02"].iloc[0]

        assert abs(te02["te_matchup_seam_route_rate"] - 0.0) < 1e-6
        assert pd.isna(te02["te_matchup_seam_completion_rate"])

    def test_non_middle_deep_pass_not_seam(self):
        """A deep pass on the left side is not counted as a seam route."""
        from graph_te_matchup import build_te_advanced_matchup_features

        rosters = pd.DataFrame({"player_id": ["TE01"], "position": ["TE"]})
        pbp = pd.DataFrame(
            {
                "game_id": ["g1"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["pass"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": ["TE01"],
                "complete_pass": [1],
                "yards_gained": [25],
                "touchdown": [0],
                "epa": [1.2],
                "air_yards": [20.0],
                "pass_location": ["left"],  # NOT middle
                "yardline_100": [40],
                "defenders_in_box": [6],
            }
        )
        result = build_te_advanced_matchup_features(pbp, pd.DataFrame(), rosters)
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        # Deep left pass should not count as seam
        assert abs(te01["te_matchup_seam_route_rate"] - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# Tests: red zone personnel LB rate
# ---------------------------------------------------------------------------


class TestRedZonePersonnelLbRate:
    """te_matchup_rz_personnel_lb_rate = LBs / total_coverage on RZ targets."""

    def test_te01_rz_lb_rate(self, pbp_df, participation_df, rosters_df):
        """TE01 red zone target: play3 (yardline=15). 1 LB / 3 total = 1/3."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        # Play 3 is red zone: 1 LB, 1 S, 1 CB -> lb_rate = 1/3
        assert abs(te01["te_matchup_rz_personnel_lb_rate"] - 1.0 / 3.0) < 1e-6

    def test_no_red_zone_targets_gives_nan(self):
        """TE with no red zone targets gets NaN for rz_personnel_lb_rate."""
        from graph_te_matchup import build_te_advanced_matchup_features

        rosters = pd.DataFrame({"player_id": ["TE01"], "position": ["TE"]})
        pbp = pd.DataFrame(
            {
                "game_id": ["g1"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["pass"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": ["TE01"],
                "complete_pass": [1],
                "yards_gained": [10],
                "touchdown": [0],
                "epa": [0.5],
                "air_yards": [8.0],
                "pass_location": ["left"],
                "yardline_100": [50],  # not red zone
                "defenders_in_box": [6],
            }
        )
        result = build_te_advanced_matchup_features(pbp, pd.DataFrame(), rosters)
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        assert pd.isna(te01["te_matchup_rz_personnel_lb_rate"])


# ---------------------------------------------------------------------------
# Tests: blocking proxy rate
# ---------------------------------------------------------------------------


class TestBlockingProxyRate:
    """te_matchup_blocking_proxy_rate = heavy-box targeted plays / total targets."""

    def test_te01_blocking_proxy_rate(self, pbp_df, participation_df, rosters_df):
        """TE01 targets: plays 1(dib=5), 2(dib=7->heavy), 3(dib=6).

        1 heavy-box play of 3 targeted plays = 1/3.
        """
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        assert abs(te01["te_matchup_blocking_proxy_rate"] - 1.0 / 3.0) < 1e-6

    def test_te02_blocking_proxy_rate(self, pbp_df, participation_df, rosters_df):
        """TE02 has one target with dib=8 (heavy) -> blocking_proxy_rate = 1.0."""
        from graph_te_matchup import build_te_advanced_matchup_features

        result = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )
        te02 = result[result["receiver_player_id"] == "TE02"].iloc[0]

        assert abs(te02["te_matchup_blocking_proxy_rate"] - 1.0) < 1e-6

    def test_no_heavy_box_plays_is_zero(self):
        """TE with only light-box targets should have blocking_proxy_rate == 0."""
        from graph_te_matchup import build_te_advanced_matchup_features

        rosters = pd.DataFrame({"player_id": ["TE01"], "position": ["TE"]})
        pbp = pd.DataFrame(
            {
                "game_id": ["g1", "g1"],
                "play_id": [1, 2],
                "season": [2024, 2024],
                "week": [1, 1],
                "play_type": ["pass", "pass"],
                "posteam": ["KC", "KC"],
                "defteam": ["BUF", "BUF"],
                "receiver_player_id": ["TE01", "TE01"],
                "complete_pass": [1, 0],
                "yards_gained": [10, 0],
                "touchdown": [0, 0],
                "epa": [0.5, -0.2],
                "air_yards": [8.0, 5.0],
                "pass_location": ["middle", "left"],
                "yardline_100": [40, 30],
                "defenders_in_box": [5, 6],  # all light box
            }
        )
        result = build_te_advanced_matchup_features(pbp, pd.DataFrame(), rosters)
        te01 = result[result["receiver_player_id"] == "TE01"].iloc[0]

        assert abs(te01["te_matchup_blocking_proxy_rate"] - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# Tests: ingest_te_matchup_graph accepts advanced_features_df
# ---------------------------------------------------------------------------


class TestIngestTeMatchupGraphAdvanced:
    """ingest_te_matchup_graph must accept optional advanced_features_df."""

    def test_ingestion_with_advanced_features(
        self, pbp_df, participation_df, rosters_df
    ):
        """Should merge advanced features and write combined edges."""
        from graph_te_matchup import (
            build_te_advanced_matchup_features,
            build_te_coverage_edges,
            ingest_te_matchup_graph,
        )

        coverage = build_te_coverage_edges(pbp_df, participation_df, rosters_df)
        advanced = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_te_matchup_graph(
            mock_db, coverage, advanced_features_df=advanced
        )

        assert total > 0
        assert mock_db.run_write.called

    def test_ingestion_without_advanced_features_backward_compatible(
        self, pbp_df, participation_df, rosters_df
    ):
        """Omitting advanced_features_df should preserve existing behavior."""
        from graph_te_matchup import build_te_coverage_edges, ingest_te_matchup_graph

        coverage = build_te_coverage_edges(pbp_df, participation_df, rosters_df)

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_te_matchup_graph(mock_db, coverage)

        assert total == len(coverage)

    def test_ingestion_disconnected_returns_zero(
        self, pbp_df, participation_df, rosters_df
    ):
        """Should return 0 without writing when Neo4j is disconnected."""
        from graph_te_matchup import (
            build_te_advanced_matchup_features,
            build_te_coverage_edges,
            ingest_te_matchup_graph,
        )

        coverage = build_te_coverage_edges(pbp_df, participation_df, rosters_df)
        advanced = build_te_advanced_matchup_features(
            pbp_df, participation_df, rosters_df
        )

        mock_db = MagicMock()
        mock_db.is_connected = False

        total = ingest_te_matchup_graph(
            mock_db, coverage, advanced_features_df=advanced
        )

        assert total == 0
        assert not mock_db.run_write.called

    def test_ingestion_empty_advanced_features(
        self, pbp_df, participation_df, rosters_df
    ):
        """Empty advanced_features_df should not cause merge errors."""
        from graph_te_matchup import build_te_coverage_edges, ingest_te_matchup_graph

        coverage = build_te_coverage_edges(pbp_df, participation_df, rosters_df)

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_te_matchup_graph(
            mock_db, coverage, advanced_features_df=pd.DataFrame()
        )

        assert total == len(coverage)
