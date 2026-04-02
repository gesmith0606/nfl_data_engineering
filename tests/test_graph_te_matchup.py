#!/usr/bin/env python3
"""Tests for Neo4j Phase 2: TE coverage mismatch and red zone features.

Tests cover:
- TE coverage edge construction with LB/safety breakdown
- LB vs safety identification (ILB, OLB, MLB all count as LB)
- Red zone filtering (yardline_100 <= 20)
- Red zone target share computation
- TE feature extraction output schema (correct columns, correct dtypes)
- Temporal lag enforcement (no future data leakage)
- Empty/missing data graceful handling
- Non-TE players get NaN for TE features
- Pandas fallback when participation data unavailable
- Neo4j ingestion (mocked)
"""

import os
import sys
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Fixtures -- synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def rosters_df():
    """Synthetic roster data with TE, WR, LB, safety positions."""
    return pd.DataFrame(
        {
            "player_id": [
                "TE01",
                "TE02",
                "WR01",
                "QB01",
                "RB01",
                "LB01",
                "LB02",
                "LB03",
                "LB04",
                "S01",
                "S02",
                "CB01",
                "DE01",
            ],
            "team": [
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
                "BUF",
                "BUF",
                "BUF",
                "BUF",
                "BUF",
                "BUF",
                "BUF",
                "BUF",
            ],
            "position": [
                "TE",
                "TE",
                "WR",
                "QB",
                "RB",
                "LB",
                "ILB",
                "OLB",
                "MLB",
                "S",
                "FS",
                "CB",
                "DE",
            ],
        }
    )


@pytest.fixture
def pbp_df():
    """Synthetic PBP data with pass plays, some in the red zone."""
    return pd.DataFrame(
        {
            "game_id": [
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_02_KC_DEN",
                "2024_02_KC_DEN",
            ],
            "play_id": [1, 2, 3, 4, 5, 6, 10, 11],
            "season": [2024, 2024, 2024, 2024, 2024, 2024, 2024, 2024],
            "week": [1, 1, 1, 1, 1, 1, 2, 2],
            "play_type": [
                "pass",
                "pass",
                "pass",
                "pass",
                "run",
                "pass",
                "pass",
                "pass",
            ],
            "posteam": ["KC", "KC", "KC", "KC", "KC", "KC", "KC", "KC"],
            "defteam": ["BUF", "BUF", "BUF", "BUF", "BUF", "BUF", "DEN", "DEN"],
            "receiver_player_id": [
                "TE01",
                "TE01",
                "WR01",
                "TE02",
                None,
                "TE01",
                "TE01",
                "TE02",
            ],
            "complete_pass": [1, 0, 1, 1, 0, 1, 1, 0],
            "yards_gained": [15, 0, 20, 8, 5, 3, 12, 0],
            "touchdown": [0, 0, 0, 0, 0, 1, 0, 0],
            "epa": [0.5, -0.3, 0.8, 0.2, 0.1, 1.5, 0.4, -0.2],
            "yardline_100": [50, 40, 30, 15, 10, 8, 45, 18],
        }
    )


@pytest.fixture
def participation_parsed_df():
    """Synthetic parsed participation with LBs and safeties identified."""
    rows = []
    # For plays 1-6 (game 2024_01_KC_BUF), defense has LBs and safeties
    for play_id in [1, 2, 3, 4, 5, 6]:
        # LBs on defense
        for lb_id in ["LB01", "LB02", "LB03"]:
            rows.append(
                {
                    "game_id": "2024_01_KC_BUF",
                    "play_id": play_id,
                    "player_gsis_id": lb_id,
                    "side": "defense",
                    "position": {"LB01": "LB", "LB02": "ILB", "LB03": "OLB"}[lb_id],
                }
            )
        # Safeties on defense
        for s_id in ["S01", "S02"]:
            rows.append(
                {
                    "game_id": "2024_01_KC_BUF",
                    "play_id": play_id,
                    "player_gsis_id": s_id,
                    "side": "defense",
                    "position": {"S01": "S", "S02": "FS"}[s_id],
                }
            )
        # CB and DE on defense (should not count as LB or safety)
        rows.append(
            {
                "game_id": "2024_01_KC_BUF",
                "play_id": play_id,
                "player_gsis_id": "CB01",
                "side": "defense",
                "position": "CB",
            }
        )
        rows.append(
            {
                "game_id": "2024_01_KC_BUF",
                "play_id": play_id,
                "player_gsis_id": "DE01",
                "side": "defense",
                "position": "DE",
            }
        )

    # For plays 10-11 (game 2024_02_KC_DEN), different personnel
    for play_id in [10, 11]:
        # Only 2 LBs, 1 safety
        for lb_id in ["LB01", "LB04"]:
            rows.append(
                {
                    "game_id": "2024_02_KC_DEN",
                    "play_id": play_id,
                    "player_gsis_id": lb_id,
                    "side": "defense",
                    "position": {"LB01": "LB", "LB04": "MLB"}[lb_id],
                }
            )
        rows.append(
            {
                "game_id": "2024_02_KC_DEN",
                "play_id": play_id,
                "player_gsis_id": "S01",
                "side": "defense",
                "position": "S",
            }
        )

    return pd.DataFrame(rows)


@pytest.fixture
def player_weekly_df():
    """Synthetic player_weekly data for TE feature computation."""
    return pd.DataFrame(
        {
            "player_id": [
                "TE01",
                "TE01",
                "TE01",
                "TE01",
                "TE02",
                "TE02",
                "WR01",
                "WR01",
                "QB01",
            ],
            "recent_team": [
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
            ],
            "opponent_team": [
                "BUF",
                "DEN",
                "LV",
                "BUF",
                "BUF",
                "DEN",
                "BUF",
                "DEN",
                "BUF",
            ],
            "season": [2024, 2024, 2024, 2024, 2024, 2024, 2024, 2024, 2024],
            "week": [1, 2, 3, 4, 1, 2, 1, 2, 1],
            "position": [
                "TE",
                "TE",
                "TE",
                "TE",
                "TE",
                "TE",
                "WR",
                "WR",
                "QB",
            ],
            "targets": [5, 4, 6, 5, 3, 2, 8, 7, 0],
            "receptions": [3, 3, 4, 4, 2, 1, 6, 5, 0],
            "receiving_yards": [45, 38, 55, 50, 20, 10, 80, 75, 0],
            "receiving_tds": [1, 0, 0, 1, 0, 0, 1, 0, 0],
            "receiving_epa": [1.5, 0.8, 1.2, 1.8, 0.3, -0.2, 2.1, 1.5, 0.0],
            "fantasy_points": [12.5, 8.8, 9.5, 15.0, 5.0, 2.0, 20.0, 14.5, 15.0],
            "rz_target_share": [0.25, 0.15, 0.20, 0.30, 0.10, 0.05, 0.30, 0.20, 0.0],
        }
    )


# ---------------------------------------------------------------------------
# Tests: TE coverage edge construction
# ---------------------------------------------------------------------------


class TestBuildTeCoverageEdges:
    """Tests for build_te_coverage_edges."""

    def test_basic_coverage_edges(self, pbp_df, participation_parsed_df, rosters_df):
        """Build coverage edges and verify aggregation."""
        from graph_te_matchup import build_te_coverage_edges

        edges = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)

        assert not edges.empty
        assert "receiver_player_id" in edges.columns
        assert "defteam" in edges.columns
        assert "targets" in edges.columns
        assert "catches" in edges.columns
        assert "yards" in edges.columns
        assert "tds" in edges.columns
        assert "epa" in edges.columns
        assert "lb_on_field_count" in edges.columns
        assert "safety_on_field_count" in edges.columns
        assert "lb_coverage_rate" in edges.columns

    def test_only_te_receivers(self, pbp_df, participation_parsed_df, rosters_df):
        """Only TE receivers should appear in edges, not WR."""
        from graph_te_matchup import build_te_coverage_edges

        edges = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)

        receiver_ids = set(edges["receiver_player_id"].unique())
        assert "WR01" not in receiver_ids
        assert "TE01" in receiver_ids

    def test_lb_positions_all_count(self, pbp_df, participation_parsed_df, rosters_df):
        """ILB, OLB, MLB, and LB should all be counted as LBs."""
        from graph_te_matchup import build_te_coverage_edges

        edges = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)

        # For week 1 vs BUF: 3 LBs (LB, ILB, OLB) per play
        te01_buf_w1 = edges[
            (edges["receiver_player_id"] == "TE01")
            & (edges["defteam"] == "BUF")
            & (edges["week"] == 1)
        ]
        assert len(te01_buf_w1) == 1
        # TE01 had 3 targets in week 1 vs BUF (plays 1, 2, 6)
        # Each play had 3 LBs on field
        assert te01_buf_w1.iloc[0]["lb_on_field_count"] == 9  # 3 LBs x 3 plays

    def test_safety_positions_counted(
        self, pbp_df, participation_parsed_df, rosters_df
    ):
        """S, SS, FS should all be counted as safeties."""
        from graph_te_matchup import build_te_coverage_edges

        edges = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)

        te01_buf_w1 = edges[
            (edges["receiver_player_id"] == "TE01")
            & (edges["defteam"] == "BUF")
            & (edges["week"] == 1)
        ]
        assert len(te01_buf_w1) == 1
        # 2 safeties (S, FS) per play x 3 TE01 targets
        assert te01_buf_w1.iloc[0]["safety_on_field_count"] == 6

    def test_lb_coverage_rate_computed(
        self, pbp_df, participation_parsed_df, rosters_df
    ):
        """LB coverage rate should be lb / (lb + safety)."""
        from graph_te_matchup import build_te_coverage_edges

        edges = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)

        te01_buf_w1 = edges[
            (edges["receiver_player_id"] == "TE01")
            & (edges["defteam"] == "BUF")
            & (edges["week"] == 1)
        ]
        lb = te01_buf_w1.iloc[0]["lb_on_field_count"]
        safety = te01_buf_w1.iloc[0]["safety_on_field_count"]
        expected_rate = lb / (lb + safety)
        assert abs(te01_buf_w1.iloc[0]["lb_coverage_rate"] - expected_rate) < 1e-6

    def test_empty_pbp_returns_empty(self, participation_parsed_df, rosters_df):
        """Empty PBP should return empty DataFrame."""
        from graph_te_matchup import build_te_coverage_edges

        result = build_te_coverage_edges(
            pd.DataFrame(), participation_parsed_df, rosters_df
        )
        assert result.empty

    def test_no_te_in_roster_returns_empty(self, pbp_df, participation_parsed_df):
        """If no TE in roster, return empty."""
        from graph_te_matchup import build_te_coverage_edges

        rosters = pd.DataFrame(
            {
                "player_id": ["WR01", "QB01"],
                "team": ["KC", "KC"],
                "position": ["WR", "QB"],
            }
        )
        result = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters)
        assert result.empty

    def test_no_participation_data_defaults_to_zero(self, pbp_df, rosters_df):
        """Without participation data, LB/safety counts default to 0."""
        from graph_te_matchup import build_te_coverage_edges

        edges = build_te_coverage_edges(pbp_df, pd.DataFrame(), rosters_df)

        assert not edges.empty
        assert (edges["lb_on_field_count"] == 0).all()
        assert (edges["safety_on_field_count"] == 0).all()


# ---------------------------------------------------------------------------
# Tests: TE red zone edge construction
# ---------------------------------------------------------------------------


class TestBuildTeRedZoneEdges:
    """Tests for build_te_red_zone_edges."""

    def test_red_zone_filtering(self, pbp_df, rosters_df):
        """Only plays with yardline_100 <= 20 should be included."""
        from graph_te_matchup import build_te_red_zone_edges

        edges = build_te_red_zone_edges(pbp_df, rosters_df)

        # Red zone plays: play_id 4 (yl=15, TE02), 6 (yl=8, TE01), 11 (yl=18, TE02)
        # play_id 5 is a run play (excluded)
        assert not edges.empty

    def test_red_zone_target_share(self, pbp_df, rosters_df):
        """RZ target share should be TE's targets / team total RZ targets."""
        from graph_te_matchup import build_te_red_zone_edges

        edges = build_te_red_zone_edges(pbp_df, rosters_df)

        # Week 1, KC vs BUF: RZ pass plays are play 4 (TE02, yl=15) and play 6 (TE01, yl=8)
        # Total team RZ targets for KC week 1 = 2
        te01_w1 = edges[
            (edges["receiver_player_id"] == "TE01")
            & (edges["season"] == 2024)
            & (edges["week"] == 1)
        ]
        if not te01_w1.empty:
            assert te01_w1.iloc[0]["red_zone_targets"] == 1
            assert te01_w1.iloc[0]["total_team_rz_targets"] == 2
            assert abs(te01_w1.iloc[0]["red_zone_target_share"] - 0.5) < 1e-6

    def test_red_zone_tds_counted(self, pbp_df, rosters_df):
        """Red zone TDs should be counted correctly."""
        from graph_te_matchup import build_te_red_zone_edges

        edges = build_te_red_zone_edges(pbp_df, rosters_df)

        # TE01 had a TD on play 6 (yardline_100=8, red zone)
        te01_w1 = edges[
            (edges["receiver_player_id"] == "TE01")
            & (edges["season"] == 2024)
            & (edges["week"] == 1)
        ]
        if not te01_w1.empty:
            assert te01_w1.iloc[0]["red_zone_tds"] == 1

    def test_empty_pbp_returns_empty(self, rosters_df):
        """Empty PBP returns empty DataFrame."""
        from graph_te_matchup import build_te_red_zone_edges

        result = build_te_red_zone_edges(pd.DataFrame(), rosters_df)
        assert result.empty

    def test_no_yardline_column_returns_empty(self, rosters_df):
        """If yardline_100 is missing, return empty."""
        from graph_te_matchup import build_te_red_zone_edges

        pbp_no_yl = pd.DataFrame(
            {
                "play_type": ["pass"],
                "receiver_player_id": ["TE01"],
                "season": [2024],
                "week": [1],
            }
        )
        result = build_te_red_zone_edges(pbp_no_yl, rosters_df)
        assert result.empty

    def test_output_columns(self, pbp_df, rosters_df):
        """Output should have expected columns."""
        from graph_te_matchup import build_te_red_zone_edges

        edges = build_te_red_zone_edges(pbp_df, rosters_df)

        if not edges.empty:
            expected = {
                "receiver_player_id",
                "posteam",
                "season",
                "week",
                "red_zone_targets",
                "total_team_rz_targets",
                "red_zone_target_share",
                "red_zone_catches",
                "red_zone_tds",
            }
            assert expected.issubset(set(edges.columns))


# ---------------------------------------------------------------------------
# Tests: TE feature extraction
# ---------------------------------------------------------------------------


class TestComputeTeFeatures:
    """Tests for compute_te_features pure-pandas fallback."""

    def test_output_schema(self, player_weekly_df, rosters_df):
        """Output should have player_id, season, week, and TE feature columns."""
        from graph_feature_extraction import TE_FEATURE_COLUMNS, compute_te_features

        result = compute_te_features(player_weekly_df, rosters_df, season=2024)

        assert not result.empty
        expected_cols = {"player_id", "season", "week"} | set(TE_FEATURE_COLUMNS)
        assert expected_cols.issubset(set(result.columns))

    def test_only_te_players(self, player_weekly_df, rosters_df):
        """Only TE-position players should appear in output."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(player_weekly_df, rosters_df, season=2024)

        te_ids = {"TE01", "TE02"}
        assert set(result["player_id"].unique()).issubset(te_ids)
        assert "WR01" not in result["player_id"].values
        assert "QB01" not in result["player_id"].values

    def test_temporal_lag_enforcement(self, player_weekly_df, rosters_df):
        """Features for week N should only use data from weeks < N."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(player_weekly_df, rosters_df, season=2024)

        # Week 2 features for TE01 should use only week 1 data
        te01_w2 = result[(result["player_id"] == "TE01") & (result["week"] == 2)]
        # te_vs_defense_epa_history for TE01 vs DEN in week 2:
        # No prior matchup with DEN, so should be NaN
        if not te01_w2.empty:
            # First encounter with DEN is week 2, so no history
            assert pd.isna(te01_w2.iloc[0]["te_vs_defense_epa_history"])

    def test_week_1_skipped(self, player_weekly_df, rosters_df):
        """Week 1 should be skipped (no prior data available)."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(player_weekly_df, rosters_df, season=2024)

        # No week 1 rows should appear (need at least 1 prior week)
        assert (result["week"] >= 2).all()

    def test_epa_history_uses_prior_matchups_only(self, player_weekly_df, rosters_df):
        """te_vs_defense_epa_history should use prior matchups only."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(player_weekly_df, rosters_df, season=2024)

        # TE01 week 4 vs BUF: should have history from week 1 vs BUF
        te01_w4 = result[(result["player_id"] == "TE01") & (result["week"] == 4)]
        if not te01_w4.empty:
            # Week 1 vs BUF had receiving_epa = 1.5
            assert not pd.isna(te01_w4.iloc[0]["te_vs_defense_epa_history"])
            assert abs(te01_w4.iloc[0]["te_vs_defense_epa_history"] - 1.5) < 1e-6

    def test_empty_player_weekly_returns_empty(self, rosters_df):
        """Empty player_weekly should return empty DataFrame."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(pd.DataFrame(), rosters_df)
        assert result.empty

    def test_participation_fallback_nan(self, player_weekly_df, rosters_df):
        """Without participation data, te_lb_coverage_rate should be NaN."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(
            player_weekly_df, rosters_df, participation_df=None, season=2024
        )

        assert not result.empty
        assert result["te_lb_coverage_rate"].isna().all()

    def test_participation_data_fills_coverage_rate(
        self, player_weekly_df, rosters_df, participation_parsed_df
    ):
        """With participation data, te_lb_coverage_rate should be computed."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(
            player_weekly_df,
            rosters_df,
            participation_df=participation_parsed_df,
            season=2024,
        )

        assert not result.empty
        # At least some rows should have non-NaN coverage rate
        has_coverage = result["te_lb_coverage_rate"].notna()
        assert has_coverage.any()

    def test_correct_dtypes(self, player_weekly_df, rosters_df):
        """Feature columns should be numeric dtype."""
        from graph_feature_extraction import TE_FEATURE_COLUMNS, compute_te_features

        result = compute_te_features(player_weekly_df, rosters_df, season=2024)

        if not result.empty:
            for col in TE_FEATURE_COLUMNS:
                assert result[col].dtype in [
                    np.float64,
                    np.float32,
                    np.int64,
                    np.int32,
                    "float64",
                    "float32",
                ], f"Column {col} has unexpected dtype {result[col].dtype}"

    def test_red_zone_target_share_lagged(self, player_weekly_df, rosters_df):
        """te_red_zone_target_share should use shift(1) rolling."""
        from graph_feature_extraction import compute_te_features

        result = compute_te_features(player_weekly_df, rosters_df, season=2024)

        # TE01 week 3: should use rz_target_share from weeks 1-2 only
        te01_w3 = result[(result["player_id"] == "TE01") & (result["week"] == 3)]
        if not te01_w3.empty:
            rz_ts = te01_w3.iloc[0]["te_red_zone_target_share"]
            if not pd.isna(rz_ts):
                # Average of week 1 (0.25) and week 2 (0.15) = 0.20
                assert abs(rz_ts - 0.20) < 1e-6


# ---------------------------------------------------------------------------
# Tests: Neo4j ingestion (mocked)
# ---------------------------------------------------------------------------


class TestIngestTeMatchupGraph:
    """Tests for ingest_te_matchup_graph with mocked GraphDB."""

    def test_ingestion_with_both_edge_types(
        self, pbp_df, participation_parsed_df, rosters_df
    ):
        """Should ingest both TE_TARGETED_AGAINST and RED_ZONE_ROLE edges."""
        from graph_te_matchup import (
            build_te_coverage_edges,
            build_te_red_zone_edges,
            ingest_te_matchup_graph,
        )

        coverage = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)
        rz = build_te_red_zone_edges(pbp_df, rosters_df)

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_te_matchup_graph(mock_db, coverage, rz)

        assert total > 0
        assert mock_db.run_write.called

    def test_ingestion_skip_when_disconnected(
        self, pbp_df, participation_parsed_df, rosters_df
    ):
        """Should return 0 and not write when Neo4j is disconnected."""
        from graph_te_matchup import (
            build_te_coverage_edges,
            ingest_te_matchup_graph,
        )

        coverage = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)

        mock_db = MagicMock()
        mock_db.is_connected = False

        total = ingest_te_matchup_graph(mock_db, coverage)
        assert total == 0
        assert not mock_db.run_write.called

    def test_ingestion_empty_edges(self):
        """Should return 0 for empty edge DataFrames."""
        from graph_te_matchup import ingest_te_matchup_graph

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_te_matchup_graph(mock_db, pd.DataFrame(), pd.DataFrame())
        assert total == 0

    def test_coverage_only_no_rz(self, pbp_df, participation_parsed_df, rosters_df):
        """Should work with coverage edges only (no red zone)."""
        from graph_te_matchup import (
            build_te_coverage_edges,
            ingest_te_matchup_graph,
        )

        coverage = build_te_coverage_edges(pbp_df, participation_parsed_df, rosters_df)

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_te_matchup_graph(mock_db, coverage, rz_edges_df=None)
        assert total == len(coverage)


# ---------------------------------------------------------------------------
# Tests: Integration with player_feature_engineering
# ---------------------------------------------------------------------------


class TestJoinTeFeatures:
    """Tests for _join_te_features helper."""

    def test_non_te_players_get_nan(self):
        """Non-TE players should get NaN for all TE feature columns."""
        from graph_feature_extraction import TE_FEATURE_COLUMNS
        from player_feature_engineering import _join_te_features

        df = pd.DataFrame(
            {
                "player_id": ["WR01", "QB01", "RB01", "TE01"],
                "season": [2024, 2024, 2024, 2024],
                "week": [1, 1, 1, 1],
                "position": ["WR", "QB", "RB", "TE"],
            }
        )

        result = _join_te_features(df, 2024)

        for col in TE_FEATURE_COLUMNS:
            assert col in result.columns
            # Non-TE rows should have NaN
            non_te = result[result["position"] != "TE"]
            assert non_te[col].isna().all(), f"{col} should be NaN for non-TE"

    def test_schema_consistency_without_cache(self):
        """Should add NaN columns even when no cached data exists."""
        from graph_feature_extraction import TE_FEATURE_COLUMNS
        from player_feature_engineering import _join_te_features

        df = pd.DataFrame(
            {
                "player_id": ["TE01"],
                "season": [2024],
                "week": [1],
                "position": ["TE"],
            }
        )

        result = _join_te_features(df, 9999)  # No data for this season

        for col in TE_FEATURE_COLUMNS:
            assert col in result.columns
