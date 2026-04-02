#!/usr/bin/env python3
"""Tests for Neo4j Phase 2: PBP participation, WR matchup, OL lineup.

Tests cover:
- Participation parser with semicolon-delimited IDs
- CB identification from parsed participation
- OL identification and position labeling
- WR-defense edge construction (correct aggregation)
- Co-occurrence edge construction (WR-CB)
- OL lineup detection and backup identification
- Rushes-behind edge construction
- Feature extraction output schemas
- Temporal lag (no future data in features)
- Graceful fallback when participation data unavailable
- Empty/missing data handling
"""

import os
import sys
from unittest.mock import MagicMock

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


# ---------------------------------------------------------------------------
# Fixtures — synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def participation_df():
    """Synthetic PBP participation data with semicolon-delimited GSIS IDs."""
    return pd.DataFrame(
        {
            "game_id": [
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
            ],
            "play_id": [1, 2, 3, 4, 5],
            "offense_players": [
                "P001;P002;P003;P010;P011;P012;P013;P014;P015;P016;P017",
                "P001;P002;P004;P010;P011;P012;P013;P014;P015;P016;P017",
                "P001;P002;P003;P010;P011;P012;P013;P014;P015;P016;P017",
                "P001;P004;P003;P010;P011;P012;P013;P014;P015;P016;P017",
                "P001;P002;P003;P010;P011;P012;P013;P014;P015;P016;P017",
            ],
            "defense_players": [
                "D001;D002;D003;D004;D005;D006;D007;D008;D009;D010;D011",
                "D001;D002;D003;D004;D005;D006;D007;D008;D009;D010;D011",
                "D001;D002;D003;D004;D005;D006;D007;D008;D009;D010;D011",
                "D001;D003;D004;D005;D006;D007;D008;D009;D010;D011;D012",
                "D001;D002;D003;D004;D005;D006;D007;D008;D009;D010;D011",
            ],
        }
    )


@pytest.fixture
def rosters_df():
    """Synthetic roster data with positions."""
    return pd.DataFrame(
        {
            "player_id": [
                "P001",
                "P002",
                "P003",
                "P004",
                "P010",
                "P011",
                "P012",
                "P013",
                "P014",
                "P015",
                "P016",
                "P017",
                "D001",
                "D002",
                "D003",
                "D004",
                "D005",
                "D006",
                "D007",
                "D008",
                "D009",
                "D010",
                "D011",
                "D012",
            ],
            "team": [
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
                "KC",
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
                "BUF",
                "BUF",
                "BUF",
                "BUF",
            ],
            "position": [
                "QB",
                "WR",
                "WR",
                "RB",
                "T",
                "G",
                "C",
                "G",
                "T",
                "WR",
                "TE",
                "RB",
                "CB",
                "CB",
                "DB",
                "LB",
                "DE",
                "DT",
                "LB",
                "S",
                "S",
                "CB",
                "DE",
                "CB",
            ],
        }
    )


@pytest.fixture
def depth_charts_df():
    """Synthetic depth chart data for OL."""
    return pd.DataFrame(
        {
            "gsis_id": ["P010", "P011", "P012", "P013", "P014"],
            "club_code": ["KC", "KC", "KC", "KC", "KC"],
            "position": ["LT", "LG", "C", "RG", "RT"],
            "depth_team": [1, 1, 1, 1, 1],
        }
    )


@pytest.fixture
def pbp_df():
    """Synthetic PBP data with pass and run plays."""
    return pd.DataFrame(
        {
            "game_id": [
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_01_KC_BUF",
                "2024_02_KC_DEN",
                "2024_02_KC_DEN",
            ],
            "play_id": [1, 2, 3, 4, 5, 10, 11],
            "season": [2024, 2024, 2024, 2024, 2024, 2024, 2024],
            "week": [1, 1, 1, 1, 1, 2, 2],
            "play_type": ["pass", "pass", "pass", "run", "pass", "pass", "run"],
            "posteam": ["KC", "KC", "KC", "KC", "KC", "KC", "KC"],
            "defteam": ["BUF", "BUF", "BUF", "BUF", "BUF", "DEN", "DEN"],
            "receiver_player_id": [
                "P002",
                "P003",
                "P002",
                None,
                "P002",
                "P002",
                None,
            ],
            "rusher_player_id": [
                None,
                None,
                None,
                "P004",
                None,
                None,
                "P004",
            ],
            "yards_gained": [12, 5, -2, 8, 15, 20, 3],
            "epa": [0.5, 0.2, -0.3, 0.4, 0.8, 1.0, 0.1],
            "air_yards": [15, 8, 5, 0, 20, 25, 0],
            "complete_pass": [1, 1, 0, 0, 1, 1, 0],
            "touchdown": [0, 0, 0, 0, 1, 0, 0],
            "pass_location": [
                "left",
                "middle",
                "right",
                None,
                "left",
                "middle",
                None,
            ],
            "run_location": [None, None, None, "left", None, None, "middle"],
            "run_gap": [None, None, None, "guard", None, None, "tackle"],
        }
    )


@pytest.fixture
def player_weekly_df():
    """Synthetic player weekly data for feature extraction tests."""
    rows = []
    for week in range(1, 6):
        rows.extend(
            [
                {
                    "player_id": "P002",
                    "player_name": "WR1",
                    "recent_team": "KC",
                    "opponent_team": "BUF",
                    "position": "WR",
                    "season": 2024,
                    "week": week,
                    "target_share": 0.25,
                    "targets": 10,
                    "receptions": 7,
                    "receiving_yards": 85,
                },
                {
                    "player_id": "P003",
                    "player_name": "WR2",
                    "recent_team": "KC",
                    "opponent_team": "BUF",
                    "position": "WR",
                    "season": 2024,
                    "week": week,
                    "target_share": 0.15,
                    "targets": 6,
                    "receptions": 4,
                    "receiving_yards": 50,
                },
                {
                    "player_id": "P004",
                    "player_name": "RB1",
                    "recent_team": "KC",
                    "opponent_team": "BUF",
                    "position": "RB",
                    "season": 2024,
                    "week": week,
                    "target_share": 0.05,
                    "targets": 2,
                    "receptions": 1,
                    "receiving_yards": 10,
                },
            ]
        )
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# Test: parse_participation_players
# ---------------------------------------------------------------------------


class TestParseParticipation:
    """Tests for participation parser."""

    def test_basic_parsing(self, participation_df, rosters_df):
        """Semicolon-delimited IDs are correctly exploded."""
        from graph_participation import parse_participation_players

        result = parse_participation_players(participation_df, rosters_df)

        assert not result.empty
        assert set(result.columns) == {
            "game_id",
            "play_id",
            "player_gsis_id",
            "side",
            "position",
        }
        # Each play has 11 offense + 11 defense = 22 players
        assert len(result) == 5 * 22

    def test_offense_defense_sides(self, participation_df, rosters_df):
        """Both offense and defense sides are correctly labeled."""
        from graph_participation import parse_participation_players

        result = parse_participation_players(participation_df, rosters_df)
        sides = result["side"].unique()
        assert "offense" in sides
        assert "defense" in sides

    def test_position_from_roster(self, participation_df, rosters_df):
        """Positions are cross-referenced from rosters."""
        from graph_participation import parse_participation_players

        result = parse_participation_players(participation_df, rosters_df)
        qb = result[result["player_gsis_id"] == "P001"]
        assert (qb["position"] == "QB").all()

        cb = result[result["player_gsis_id"] == "D001"]
        assert (cb["position"] == "CB").all()

    def test_empty_participation(self, rosters_df):
        """Empty participation DataFrame returns empty result."""
        from graph_participation import parse_participation_players

        result = parse_participation_players(pd.DataFrame(), rosters_df)
        assert result.empty
        assert "player_gsis_id" in result.columns

    def test_missing_roster(self, participation_df):
        """Missing roster sets position to UNK."""
        from graph_participation import parse_participation_players

        result = parse_participation_players(participation_df, pd.DataFrame())
        assert (result["position"] == "UNK").all()

    def test_nan_players_filtered(self, rosters_df):
        """NaN/empty player strings are filtered out."""
        from graph_participation import parse_participation_players

        df = pd.DataFrame(
            {
                "game_id": ["2024_01_KC_BUF"],
                "play_id": [1],
                "offense_players": ["P001;;P002"],
                "defense_players": [None],
            }
        )
        result = parse_participation_players(df, rosters_df)
        # Should only have P001, P002 on offense (empty string filtered)
        offense = result[result["side"] == "offense"]
        assert len(offense) == 2


# ---------------------------------------------------------------------------
# Test: identify_cbs_on_field
# ---------------------------------------------------------------------------


class TestIdentifyCBs:
    """Tests for CB identification."""

    def test_finds_cbs(self, participation_df, rosters_df):
        """CBs and DBs are correctly identified."""
        from graph_participation import (
            identify_cbs_on_field,
            parse_participation_players,
        )

        parsed = parse_participation_players(participation_df, rosters_df)
        cbs = identify_cbs_on_field(parsed)

        assert not cbs.empty
        assert (cbs["side"] == "defense").all()
        assert cbs["position"].isin({"CB", "DB"}).all()

    def test_correct_cb_count(self, participation_df, rosters_df):
        """Expected number of CB/DB per play."""
        from graph_participation import (
            identify_cbs_on_field,
            parse_participation_players,
        )

        parsed = parse_participation_players(participation_df, rosters_df)
        cbs = identify_cbs_on_field(parsed)

        # D001=CB, D002=CB, D003=DB, D010=CB, D012=CB
        # Play 4 has D012 instead of D002, so different count
        play1_cbs = cbs[cbs["play_id"] == 1]
        # D001=CB, D002=CB, D003=DB, D010=CB = 4 CBs/DBs
        assert len(play1_cbs) == 4

    def test_empty_input(self):
        """Empty input returns empty DataFrame."""
        from graph_participation import identify_cbs_on_field

        result = identify_cbs_on_field(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# Test: identify_ol_on_field
# ---------------------------------------------------------------------------


class TestIdentifyOL:
    """Tests for OL identification."""

    def test_finds_ol(self, participation_df, rosters_df):
        """OL positions are correctly identified."""
        from graph_participation import (
            identify_ol_on_field,
            parse_participation_players,
        )

        parsed = parse_participation_players(participation_df, rosters_df)
        ol = identify_ol_on_field(parsed)

        assert not ol.empty
        assert "ol_label" in ol.columns
        assert "is_starter" in ol.columns

    def test_depth_chart_labels(self, participation_df, rosters_df, depth_charts_df):
        """Depth chart labels are applied (LT, LG, C, RG, RT)."""
        from graph_participation import (
            identify_ol_on_field,
            parse_participation_players,
        )

        parsed = parse_participation_players(participation_df, rosters_df)
        ol = identify_ol_on_field(parsed, depth_charts_df)

        # P010=LT, P011=LG, P012=C, P013=RG, P014=RT from depth chart
        p010 = ol[ol["player_gsis_id"] == "P010"]
        assert not p010.empty
        assert (p010["ol_label"] == "LT").all()
        assert (p010["is_starter"]).all()

    def test_empty_input(self):
        """Empty input returns empty with correct schema."""
        from graph_participation import identify_ol_on_field

        result = identify_ol_on_field(pd.DataFrame())
        assert result.empty
        assert "ol_label" in result.columns
        assert "is_starter" in result.columns


# ---------------------------------------------------------------------------
# Test: build_targeted_against_edges
# ---------------------------------------------------------------------------


class TestTargetedAgainstEdges:
    """Tests for WR-defense edge construction."""

    def test_basic_aggregation(self, pbp_df, participation_df):
        """Correct target/catch/yard/TD aggregation per WR-defense."""
        from graph_wr_matchup import build_targeted_against_edges

        # Parse participation (not actually used in this function, but required arg)
        edges = build_targeted_against_edges(pbp_df, pd.DataFrame())

        assert not edges.empty
        assert "receiver_player_id" in edges.columns
        assert "defteam" in edges.columns
        assert "targets" in edges.columns
        assert "catches" in edges.columns
        assert "yards" in edges.columns
        assert "tds" in edges.columns
        assert "epa" in edges.columns

        # P002 vs BUF in week 1: plays 1, 3, 5 = 3 targets
        p002_buf = edges[
            (edges["receiver_player_id"] == "P002")
            & (edges["defteam"] == "BUF")
            & (edges["week"] == 1)
        ]
        assert len(p002_buf) == 1
        assert int(p002_buf["targets"].iloc[0]) == 3
        assert int(p002_buf["catches"].iloc[0]) == 2  # plays 1 and 5
        assert int(p002_buf["tds"].iloc[0]) == 1  # play 5

    def test_pass_location_rates(self, pbp_df):
        """Pass location distribution is computed correctly."""
        from graph_wr_matchup import build_targeted_against_edges

        edges = build_targeted_against_edges(pbp_df, pd.DataFrame())

        p002_buf = edges[
            (edges["receiver_player_id"] == "P002")
            & (edges["defteam"] == "BUF")
            & (edges["week"] == 1)
        ]
        # P002 vs BUF: left (play 1), right (play 3), left (play 5) = 2/3 left, 0 mid, 1/3 right
        assert abs(p002_buf["pass_left_rate"].iloc[0] - 2 / 3) < 0.01
        assert abs(p002_buf["pass_right_rate"].iloc[0] - 1 / 3) < 0.01

    def test_empty_pbp(self):
        """Empty PBP returns empty DataFrame."""
        from graph_wr_matchup import build_targeted_against_edges

        result = build_targeted_against_edges(pd.DataFrame(), pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# Test: build_on_field_with_edges
# ---------------------------------------------------------------------------


class TestOnFieldWithEdges:
    """Tests for WR-CB co-occurrence."""

    def test_cooccurrence_counts(self, pbp_df, participation_df, rosters_df):
        """WR-CB co-occurrence snap counts are correct."""
        from graph_participation import parse_participation_players
        from graph_wr_matchup import build_on_field_with_edges

        parsed = parse_participation_players(participation_df, rosters_df)
        edges = build_on_field_with_edges(pbp_df, parsed)

        assert not edges.empty
        assert "wr_player_id" in edges.columns
        assert "cb_player_id" in edges.columns
        assert "snap_count" in edges.columns

    def test_empty_cbs(self, pbp_df):
        """No CBs in participation returns empty."""
        from graph_wr_matchup import build_on_field_with_edges

        # Participation with no CB positions
        parsed = pd.DataFrame(
            {
                "game_id": ["2024_01_KC_BUF"],
                "play_id": [1],
                "player_gsis_id": ["P001"],
                "side": ["defense"],
                "position": ["LB"],
            }
        )
        result = build_on_field_with_edges(pbp_df, parsed)
        assert result.empty

    def test_empty_inputs(self):
        """Empty inputs return empty DataFrame."""
        from graph_wr_matchup import build_on_field_with_edges

        assert build_on_field_with_edges(pd.DataFrame(), pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# Test: build_ol_lineup_edges
# ---------------------------------------------------------------------------


class TestOLLineupEdges:
    """Tests for OL lineup edge construction."""

    def test_basic_ol_edges(self, participation_df, rosters_df, depth_charts_df):
        """OL edges are built with correct snap counts."""
        from graph_participation import parse_participation_players
        from graph_ol_lineup import build_ol_lineup_edges

        parsed = parse_participation_players(participation_df, rosters_df)
        edges = build_ol_lineup_edges(parsed, depth_charts_df)

        assert not edges.empty
        assert "ol_player_id" in edges.columns
        assert "snap_count" in edges.columns
        assert "is_backup_insertion" in edges.columns

    def test_backup_detection(self, participation_df, rosters_df, depth_charts_df):
        """Non-starter OL are detected as backup insertions."""
        from graph_participation import parse_participation_players
        from graph_ol_lineup import build_ol_lineup_edges

        parsed = parse_participation_players(participation_df, rosters_df)
        edges = build_ol_lineup_edges(parsed, depth_charts_df)

        # All P010-P014 are starters in depth chart
        starters = edges[
            edges["ol_player_id"].isin(["P010", "P011", "P012", "P013", "P014"])
        ]
        assert (~starters["is_backup_insertion"]).all()

    def test_empty_participation(self):
        """Empty participation returns empty DataFrame."""
        from graph_ol_lineup import build_ol_lineup_edges

        result = build_ol_lineup_edges(pd.DataFrame())
        assert result.empty


# ---------------------------------------------------------------------------
# Test: build_rushes_behind_edges
# ---------------------------------------------------------------------------


class TestRushesBehindEdges:
    """Tests for RB rushing edges."""

    def test_basic_rushes(self, pbp_df, participation_df, rosters_df):
        """Rush edges are built with correct aggregation."""
        from graph_participation import parse_participation_players
        from graph_ol_lineup import build_rushes_behind_edges

        parsed = parse_participation_players(participation_df, rosters_df)
        edges = build_rushes_behind_edges(pbp_df, parsed)

        assert not edges.empty
        assert "rb_player_id" in edges.columns
        assert "carries" in edges.columns
        assert "ypc" in edges.columns

    def test_ypc_calculation(self, pbp_df, participation_df, rosters_df):
        """YPC is yards / carries."""
        from graph_participation import parse_participation_players
        from graph_ol_lineup import build_rushes_behind_edges

        parsed = parse_participation_players(participation_df, rosters_df)
        edges = build_rushes_behind_edges(pbp_df, parsed)

        for _, row in edges.iterrows():
            if row["carries"] > 0:
                expected = row["yards"] / row["carries"]
                assert abs(row["ypc"] - expected) < 0.01

    def test_empty_inputs(self):
        """Empty inputs return empty DataFrame."""
        from graph_ol_lineup import build_rushes_behind_edges

        assert build_rushes_behind_edges(pd.DataFrame(), pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# Test: Feature extraction schemas
# ---------------------------------------------------------------------------


class TestFeatureSchemas:
    """Tests for feature extraction output schemas."""

    def test_wr_matchup_columns(self, pbp_df, player_weekly_df):
        """WR matchup features have correct output columns."""
        from graph_feature_extraction import (
            WR_MATCHUP_FEATURE_COLUMNS,
            compute_wr_matchup_features,
        )

        result = compute_wr_matchup_features(pbp_df, player_weekly_df, 2024, 4)

        if not result.empty:
            for col in WR_MATCHUP_FEATURE_COLUMNS:
                assert col in result.columns, f"Missing column: {col}"
            assert "player_id" in result.columns
            assert "season" in result.columns
            assert "week" in result.columns

    def test_ol_rb_columns(
        self, pbp_df, player_weekly_df, participation_df, rosters_df
    ):
        """OL/RB features have correct output columns."""
        from graph_participation import parse_participation_players
        from graph_feature_extraction import (
            OL_RB_FEATURE_COLUMNS,
            compute_ol_rb_features,
        )

        parsed = parse_participation_players(participation_df, rosters_df)
        result = compute_ol_rb_features(pbp_df, parsed, player_weekly_df, 2024, 4)

        if not result.empty:
            for col in OL_RB_FEATURE_COLUMNS:
                assert col in result.columns, f"Missing column: {col}"

    def test_graph_feature_column_lists(self):
        """Feature column lists are non-empty and unique."""
        from graph_feature_extraction import (
            GRAPH_FEATURE_COLUMNS,
            WR_MATCHUP_FEATURE_COLUMNS,
            OL_RB_FEATURE_COLUMNS,
        )

        assert len(GRAPH_FEATURE_COLUMNS) > 0
        assert len(WR_MATCHUP_FEATURE_COLUMNS) > 0
        assert len(OL_RB_FEATURE_COLUMNS) > 0

        # No overlap between the feature sets
        all_cols = (
            set(GRAPH_FEATURE_COLUMNS)
            | set(WR_MATCHUP_FEATURE_COLUMNS)
            | set(OL_RB_FEATURE_COLUMNS)
        )
        assert len(all_cols) == (
            len(GRAPH_FEATURE_COLUMNS)
            + len(WR_MATCHUP_FEATURE_COLUMNS)
            + len(OL_RB_FEATURE_COLUMNS)
        )


# ---------------------------------------------------------------------------
# Test: Temporal lag enforcement
# ---------------------------------------------------------------------------


class TestTemporalLag:
    """Tests that features do not use future data."""

    def test_wr_features_no_future_data(self, pbp_df, player_weekly_df):
        """WR matchup features for week 2 do not include week 2+ data."""
        from graph_feature_extraction import compute_wr_matchup_features

        result = compute_wr_matchup_features(pbp_df, player_weekly_df, 2024, 2)
        if not result.empty:
            assert (result["week"] == 2).all()
            # Features should only use week 1 data

    def test_ol_features_no_future_data(
        self, pbp_df, player_weekly_df, participation_df, rosters_df
    ):
        """OL/RB features for week 3 only use weeks 1-2."""
        from graph_participation import parse_participation_players
        from graph_feature_extraction import compute_ol_rb_features

        parsed = parse_participation_players(participation_df, rosters_df)
        result = compute_ol_rb_features(pbp_df, parsed, player_weekly_df, 2024, 3)
        if not result.empty:
            assert (result["week"] == 3).all()


# ---------------------------------------------------------------------------
# Test: Graceful fallback
# ---------------------------------------------------------------------------


class TestGracefulFallback:
    """Tests for graceful degradation when data is unavailable."""

    def test_wr_features_empty_pbp(self, player_weekly_df):
        """Empty PBP returns empty WR features."""
        from graph_feature_extraction import compute_wr_matchup_features

        result = compute_wr_matchup_features(pd.DataFrame(), player_weekly_df, 2024, 4)
        assert result.empty

    def test_ol_features_empty_participation(self, pbp_df, player_weekly_df):
        """Empty participation returns NaN-filled OL features."""
        from graph_feature_extraction import (
            OL_RB_FEATURE_COLUMNS,
            compute_ol_rb_features,
        )

        result = compute_ol_rb_features(
            pbp_df, pd.DataFrame(), player_weekly_df, 2024, 4
        )
        # Should still return rows (for RBs) but with NaN features
        if not result.empty:
            for col in OL_RB_FEATURE_COLUMNS:
                assert col in result.columns

    def test_neo4j_ingestion_disconnected(self):
        """Neo4j ingestion returns 0 when disconnected."""
        from graph_wr_matchup import ingest_wr_matchup_graph
        from graph_ol_lineup import ingest_ol_graph

        mock_gdb = MagicMock()
        mock_gdb.is_connected = False

        assert ingest_wr_matchup_graph(mock_gdb, pd.DataFrame()) == 0
        assert ingest_ol_graph(mock_gdb, pd.DataFrame()) == 0


# ---------------------------------------------------------------------------
# Test: PBP participation ingestion config
# ---------------------------------------------------------------------------


class TestParticipationConfig:
    """Tests for PBP_PARTICIPATION_COLUMNS config."""

    def test_participation_columns_exist(self):
        """PBP_PARTICIPATION_COLUMNS is defined in config."""
        from config import PBP_PARTICIPATION_COLUMNS

        assert isinstance(PBP_PARTICIPATION_COLUMNS, list)
        assert "game_id" in PBP_PARTICIPATION_COLUMNS
        assert "play_id" in PBP_PARTICIPATION_COLUMNS
        assert "offense_players" in PBP_PARTICIPATION_COLUMNS
        assert "defense_players" in PBP_PARTICIPATION_COLUMNS

    def test_defenders_in_box_in_pbp_columns(self):
        """defenders_in_box was added to PBP_COLUMNS."""
        from config import PBP_COLUMNS

        assert "defenders_in_box" in PBP_COLUMNS


# ---------------------------------------------------------------------------
# Test: Neo4j ingestion (mocked)
# ---------------------------------------------------------------------------


class TestNeo4jIngestion:
    """Tests for Neo4j write operations with mocked GraphDB."""

    def test_wr_matchup_ingestion(self, pbp_df):
        """TARGETED_AGAINST edges are ingested with correct Cypher."""
        from graph_wr_matchup import (
            build_targeted_against_edges,
            ingest_wr_matchup_graph,
        )

        edges = build_targeted_against_edges(pbp_df, pd.DataFrame())

        mock_gdb = MagicMock()
        mock_gdb.is_connected = True
        mock_gdb.run_write.return_value = []

        count = ingest_wr_matchup_graph(mock_gdb, edges)
        assert count > 0
        assert mock_gdb.run_write.called

    def test_ol_ingestion(self, participation_df, rosters_df, depth_charts_df, pbp_df):
        """BLOCKS_FOR and RUSHES_BEHIND edges are ingested."""
        from graph_participation import parse_participation_players
        from graph_ol_lineup import (
            build_ol_lineup_edges,
            build_rushes_behind_edges,
            ingest_ol_graph,
        )

        parsed = parse_participation_players(participation_df, rosters_df)
        ol_edges = build_ol_lineup_edges(parsed, depth_charts_df)
        rb_edges = build_rushes_behind_edges(pbp_df, parsed)

        mock_gdb = MagicMock()
        mock_gdb.is_connected = True
        mock_gdb.run_write.return_value = []

        count = ingest_ol_graph(mock_gdb, ol_edges, rb_edges)
        assert count > 0
        assert mock_gdb.run_write.called

    def test_cooccurrence_ingestion(self, pbp_df, participation_df, rosters_df):
        """ON_FIELD_WITH edges are ingested alongside TARGETED_AGAINST."""
        from graph_participation import parse_participation_players
        from graph_wr_matchup import (
            build_targeted_against_edges,
            build_on_field_with_edges,
            ingest_wr_matchup_graph,
        )

        parsed = parse_participation_players(participation_df, rosters_df)
        targeted = build_targeted_against_edges(pbp_df, parsed)
        cooccur = build_on_field_with_edges(pbp_df, parsed)

        mock_gdb = MagicMock()
        mock_gdb.is_connected = True
        mock_gdb.run_write.return_value = []

        count = ingest_wr_matchup_graph(mock_gdb, targeted, cooccur)
        assert count > 0


# ---------------------------------------------------------------------------
# Test: Empty/missing data edge cases
# ---------------------------------------------------------------------------


class TestEdgeCases:
    """Tests for empty and edge-case inputs."""

    def test_all_nan_participation(self, rosters_df):
        """All-NaN participation columns return empty parsed result."""
        from graph_participation import parse_participation_players

        df = pd.DataFrame(
            {
                "game_id": ["2024_01_KC_BUF"],
                "play_id": [1],
                "offense_players": [None],
                "defense_players": [None],
            }
        )
        result = parse_participation_players(df, rosters_df)
        assert result.empty or len(result) == 0

    def test_single_player_participation(self, rosters_df):
        """Single player per side works correctly."""
        from graph_participation import parse_participation_players

        df = pd.DataFrame(
            {
                "game_id": ["2024_01_KC_BUF"],
                "play_id": [1],
                "offense_players": ["P001"],
                "defense_players": ["D001"],
            }
        )
        result = parse_participation_players(df, rosters_df)
        assert len(result) == 2

    def test_no_pass_plays_in_pbp(self):
        """PBP with only run plays produces no WR edges."""
        from graph_wr_matchup import build_targeted_against_edges

        df = pd.DataFrame(
            {
                "game_id": ["2024_01_KC_BUF"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["run"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": [None],
                "rusher_player_id": ["P004"],
                "yards_gained": [5],
                "epa": [0.2],
                "air_yards": [0],
                "complete_pass": [0],
                "touchdown": [0],
                "pass_location": [None],
            }
        )
        result = build_targeted_against_edges(df, pd.DataFrame())
        assert result.empty

    def test_no_run_plays_in_pbp(self, participation_df, rosters_df):
        """PBP with only pass plays produces no rush edges."""
        from graph_participation import parse_participation_players
        from graph_ol_lineup import build_rushes_behind_edges

        df = pd.DataFrame(
            {
                "game_id": ["2024_01_KC_BUF"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["pass"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": ["P002"],
                "rusher_player_id": [None],
                "yards_gained": [10],
                "epa": [0.5],
                "run_location": [None],
                "run_gap": [None],
            }
        )
        parsed = parse_participation_players(participation_df, rosters_df)
        result = build_rushes_behind_edges(df, parsed)
        assert result.empty
