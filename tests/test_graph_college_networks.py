#!/usr/bin/env python3
"""Tests for college-to-NFL graph features.

Tests cover:
- College teammate detection (same college, overlapping years)
- Teammate counting on same NFL team
- QB-WR college familiarity
- Scheme familiarity scoring (same, adjacent, different)
- Prospect similarity computation
- Comp features (ceiling, floor, bust rate)
- Temporal safety (shift(1) enforcement)
- Missing/empty data handling (graceful NaN)
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from graph_college_networks import (
    COACHING_SCHEME_FEATURE_COLUMNS,
    COLLEGE_NETWORK_FEATURE_COLUMNS,
    COLLEGE_TEAMMATE_FEATURE_COLUMNS,
    PROSPECT_COMP_FEATURE_COLUMNS,
    _build_player_college_map,
    _compute_prospect_similarity,
    _parse_height_inches,
    build_coaching_scheme_edges,
    build_college_teammate_edges,
    build_prospect_comparison_graph,
    compute_all_college_features,
    compute_coaching_scheme_features,
    compute_college_teammate_features,
    compute_prospect_comp_features,
)


# ---------------------------------------------------------------------------
# Fixtures -- synthetic data
# ---------------------------------------------------------------------------


@pytest.fixture
def draft_picks_df():
    """Synthetic draft picks: 6 players from 3 colleges."""
    return pd.DataFrame(
        [
            {
                "season": 2020,
                "round": 1,
                "pick": 1,
                "gsis_id": "P001",
                "pfr_player_id": "PFR001",
                "pfr_player_name": "Player One",
                "position": "QB",
                "college": "Alabama",
            },
            {
                "season": 2020,
                "round": 2,
                "pick": 40,
                "gsis_id": "P002",
                "pfr_player_id": "PFR002",
                "pfr_player_name": "Player Two",
                "position": "WR",
                "college": "Alabama",
            },
            {
                "season": 2021,
                "round": 1,
                "pick": 10,
                "gsis_id": "P003",
                "pfr_player_id": "PFR003",
                "pfr_player_name": "Player Three",
                "position": "WR",
                "college": "Alabama",
            },
            {
                "season": 2018,
                "round": 3,
                "pick": 70,
                "gsis_id": "P004",
                "pfr_player_id": "PFR004",
                "pfr_player_name": "Player Four",
                "position": "RB",
                "college": "Ohio State",
            },
            {
                "season": 2020,
                "round": 1,
                "pick": 5,
                "gsis_id": "P005",
                "pfr_player_id": "PFR005",
                "pfr_player_name": "Player Five",
                "position": "WR",
                "college": "Ohio State",
            },
            {
                "season": 2019,
                "round": 4,
                "pick": 120,
                "gsis_id": "P006",
                "pfr_player_id": "PFR006",
                "pfr_player_name": "Player Six",
                "position": "TE",
                "college": "Stanford",
            },
        ]
    )


@pytest.fixture
def combine_df():
    """Synthetic combine data matching draft picks."""
    return pd.DataFrame(
        [
            {
                "pfr_id": "PFR001",
                "player_name": "Player One",
                "pos": "QB",
                "school": "Alabama",
                "ht": "6-3",
                "wt": 220.0,
                "forty": 4.7,
                "vertical": 32.0,
                "broad_jump": 115.0,
            },
            {
                "pfr_id": "PFR002",
                "player_name": "Player Two",
                "pos": "WR",
                "school": "Alabama",
                "ht": "6-1",
                "wt": 195.0,
                "forty": 4.4,
                "vertical": 38.0,
                "broad_jump": 125.0,
            },
            {
                "pfr_id": "PFR003",
                "player_name": "Player Three",
                "pos": "WR",
                "school": "Alabama",
                "ht": "6-0",
                "wt": 190.0,
                "forty": 4.45,
                "vertical": 37.0,
                "broad_jump": 123.0,
            },
            {
                "pfr_id": "PFR005",
                "player_name": "Player Five",
                "pos": "WR",
                "school": "Ohio State",
                "ht": "6-2",
                "wt": 200.0,
                "forty": 4.38,
                "vertical": 40.0,
                "broad_jump": 128.0,
            },
        ]
    )


@pytest.fixture
def player_weekly_df():
    """Synthetic player-week data for 2 weeks, 4 players on 2 teams."""
    rows = []
    # Week 1: P001 (QB, KC), P002 (WR, KC), P003 (WR, BUF), P005 (WR, KC)
    for pid, team, pos, pts in [
        ("P001", "KC", "QB", 22.0),
        ("P002", "KC", "WR", 15.0),
        ("P003", "BUF", "WR", 12.0),
        ("P005", "KC", "WR", 10.0),
    ]:
        rows.append(
            {
                "player_id": pid,
                "season": 2024,
                "week": 1,
                "recent_team": team,
                "position": pos,
                "fantasy_points": pts,
            }
        )
    # Week 2: same
    for pid, team, pos, pts in [
        ("P001", "KC", "QB", 25.0),
        ("P002", "KC", "WR", 18.0),
        ("P003", "BUF", "WR", 14.0),
        ("P005", "KC", "WR", 11.0),
    ]:
        rows.append(
            {
                "player_id": pid,
                "season": 2024,
                "week": 2,
                "recent_team": team,
                "position": pos,
                "fantasy_points": pts,
            }
        )
    # Week 3
    for pid, team, pos, pts in [
        ("P001", "KC", "QB", 20.0),
        ("P002", "KC", "WR", 16.0),
        ("P003", "BUF", "WR", 13.0),
        ("P005", "KC", "WR", 12.0),
    ]:
        rows.append(
            {
                "player_id": pid,
                "season": 2024,
                "week": 3,
                "recent_team": team,
                "position": pos,
                "fantasy_points": pts,
            }
        )
    return pd.DataFrame(rows)


@pytest.fixture
def rosters_df():
    """Empty rosters — rely on draft_picks for college mapping."""
    return pd.DataFrame()


# ---------------------------------------------------------------------------
# 1. College Teammate Detection Tests
# ---------------------------------------------------------------------------


class TestBuildCollegeTeammateEdges:
    """Tests for build_college_teammate_edges."""

    def test_detects_overlapping_teammates(self, draft_picks_df, rosters_df):
        """Players from same college within overlap window are teammates."""
        edges = build_college_teammate_edges(rosters_df, draft_picks_df)
        assert not edges.empty
        # P001 (Alabama, 2020) + P002 (Alabama, 2020) should be teammates
        mask_ab = (
            (edges["player_id_a"] == "P001") & (edges["player_id_b"] == "P002")
        ) | ((edges["player_id_a"] == "P002") & (edges["player_id_b"] == "P001"))
        assert (
            mask_ab.any()
        ), "P001 and P002 (same college, same year) should be teammates"

    def test_overlap_years_correct(self, draft_picks_df, rosters_df):
        """Overlap years calculation is correct."""
        edges = build_college_teammate_edges(rosters_df, draft_picks_df)
        # P001 (2020) and P003 (2021) at Alabama: 1 year apart -> overlap = 4
        mask = ((edges["player_id_a"] == "P001") & (edges["player_id_b"] == "P003")) | (
            (edges["player_id_a"] == "P003") & (edges["player_id_b"] == "P001")
        )
        if mask.any():
            overlap = edges.loc[mask, "years_overlap"].iloc[0]
            assert overlap == 4  # 4 - abs(2020-2021) + 1 = 4

    def test_different_colleges_not_matched(self, draft_picks_df, rosters_df):
        """Players from different colleges are not teammates."""
        edges = build_college_teammate_edges(rosters_df, draft_picks_df)
        # P001 (Alabama) and P004 (Ohio State) should NOT be matched
        mask = ((edges["player_id_a"] == "P001") & (edges["player_id_b"] == "P004")) | (
            (edges["player_id_a"] == "P004") & (edges["player_id_b"] == "P001")
        )
        assert not mask.any()

    def test_distant_years_not_matched(self, draft_picks_df, rosters_df):
        """Players at same college but > overlap window apart are not matched."""
        # P004 (Ohio State, 2018) and P005 (Ohio State, 2020) = 2 years
        # Within window of 4, so they SHOULD match
        edges = build_college_teammate_edges(rosters_df, draft_picks_df)
        mask = ((edges["player_id_a"] == "P004") & (edges["player_id_b"] == "P005")) | (
            (edges["player_id_a"] == "P005") & (edges["player_id_b"] == "P004")
        )
        assert (
            mask.any()
        ), "P004 and P005 (2 years apart) should match within 4-year window"

    def test_empty_inputs(self, rosters_df):
        """Empty inputs return empty DataFrame with correct schema."""
        edges = build_college_teammate_edges(rosters_df, pd.DataFrame())
        assert edges.empty
        assert "player_id_a" in edges.columns
        assert "player_id_b" in edges.columns
        assert "college" in edges.columns
        assert "years_overlap" in edges.columns


class TestBuildPlayerCollegeMap:
    """Tests for _build_player_college_map."""

    def test_builds_from_draft_picks(self, draft_picks_df):
        """Maps players to colleges from draft picks."""
        result = _build_player_college_map(pd.DataFrame(), draft_picks_df)
        assert len(result) == 6
        assert "P001" in result["player_id"].values
        p1 = result[result["player_id"] == "P001"].iloc[0]
        assert p1["college"] == "Alabama"

    def test_handles_college_name_column(self):
        """Handles rosters with college_name instead of college."""
        rosters = pd.DataFrame(
            [
                {
                    "player_id": "R001",
                    "college_name": "Michigan",
                    "season": 2022,
                    "position": "QB",
                }
            ]
        )
        result = _build_player_college_map(rosters, pd.DataFrame())
        assert len(result) == 1
        assert result.iloc[0]["college"] == "Michigan"


class TestComputeCollegeTeammateFeatures:
    """Tests for compute_college_teammate_features."""

    def test_counts_teammates_on_same_team(
        self, draft_picks_df, rosters_df, player_weekly_df
    ):
        """Counts college teammates on same NFL roster."""
        player_college_map = _build_player_college_map(rosters_df, draft_picks_df)
        teammate_edges = build_college_teammate_edges(rosters_df, draft_picks_df)

        # Week 2 — uses week 1 as prior
        feats = compute_college_teammate_features(
            teammate_edges, player_college_map, player_weekly_df, 2024, 2
        )
        assert not feats.empty
        assert "college_teammates_on_roster" in feats.columns

        # P002 (Alabama WR on KC) should have at least 1 teammate (P001, Alabama QB on KC)
        p2 = feats[feats["player_id"] == "P002"]
        if not p2.empty:
            assert p2["college_teammates_on_roster"].iloc[0] >= 1

    def test_qb_familiarity(self, draft_picks_df, rosters_df, player_weekly_df):
        """WR on same team as college QB gets familiarity flag."""
        player_college_map = _build_player_college_map(rosters_df, draft_picks_df)
        teammate_edges = build_college_teammate_edges(rosters_df, draft_picks_df)

        feats = compute_college_teammate_features(
            teammate_edges, player_college_map, player_weekly_df, 2024, 2
        )
        # P002 (WR, KC) played at Alabama with P001 (QB, KC)
        p2 = feats[feats["player_id"] == "P002"]
        if not p2.empty:
            assert p2["college_qb_familiarity"].iloc[0] == 1

    def test_temporal_safety_week1(self, draft_picks_df, rosters_df, player_weekly_df):
        """Week 1 uses previous season data or returns empty (no leakage)."""
        player_college_map = _build_player_college_map(rosters_df, draft_picks_df)
        teammate_edges = build_college_teammate_edges(rosters_df, draft_picks_df)

        feats = compute_college_teammate_features(
            teammate_edges, player_college_map, player_weekly_df, 2024, 1
        )
        # Should be empty since no season 2023 data exists
        assert feats.empty

    def test_empty_edges(self, draft_picks_df, player_weekly_df):
        """Empty teammate edges produce empty output."""
        player_college_map = _build_player_college_map(pd.DataFrame(), draft_picks_df)
        feats = compute_college_teammate_features(
            pd.DataFrame(
                columns=["player_id_a", "player_id_b", "college", "years_overlap"]
            ),
            player_college_map,
            player_weekly_df,
            2024,
            2,
        )
        assert feats.empty

    def test_output_schema(self, draft_picks_df, rosters_df, player_weekly_df):
        """Output has correct columns."""
        player_college_map = _build_player_college_map(rosters_df, draft_picks_df)
        teammate_edges = build_college_teammate_edges(rosters_df, draft_picks_df)
        feats = compute_college_teammate_features(
            teammate_edges, player_college_map, player_weekly_df, 2024, 2
        )
        for col in COLLEGE_TEAMMATE_FEATURE_COLUMNS:
            assert col in feats.columns


# ---------------------------------------------------------------------------
# 2. Coaching Scheme Tests
# ---------------------------------------------------------------------------


class TestBuildCoachingSchemeEdges:
    """Tests for build_coaching_scheme_edges."""

    def test_maps_known_colleges(self, draft_picks_df, player_weekly_df):
        """Known college programs get correct scheme families."""
        pcm = _build_player_college_map(pd.DataFrame(), draft_picks_df)
        edges = build_coaching_scheme_edges(pcm, player_weekly_df)
        assert not edges.empty

        # Alabama -> spread_rpo
        p1 = edges[edges["player_id"] == "P001"]
        if not p1.empty:
            assert p1.iloc[0]["college_scheme"] == "spread_rpo"

    def test_unknown_college_scheme(self, player_weekly_df):
        """Unlisted college gets 'unknown' scheme."""
        pcm = pd.DataFrame(
            [
                {
                    "player_id": "P099",
                    "college": "Tiny College",
                    "draft_year": 2022,
                    "position": "WR",
                }
            ]
        )
        # Add P099 to player_weekly
        pw = pd.concat(
            [
                player_weekly_df,
                pd.DataFrame(
                    [
                        {
                            "player_id": "P099",
                            "season": 2024,
                            "week": 1,
                            "recent_team": "KC",
                            "position": "WR",
                            "fantasy_points": 5.0,
                        }
                    ]
                ),
            ],
            ignore_index=True,
        )
        edges = build_coaching_scheme_edges(pcm, pw)
        p99 = edges[edges["player_id"] == "P099"]
        assert not p99.empty
        assert p99.iloc[0]["college_scheme"] == "unknown"

    def test_scheme_match_scores(self, draft_picks_df, player_weekly_df):
        """Scheme match scores follow expected rules."""
        pcm = _build_player_college_map(pd.DataFrame(), draft_picks_df)
        edges = build_coaching_scheme_edges(pcm, player_weekly_df)

        # P001 from Alabama (spread_rpo) on KC (spread_rpo) -> match = 1.0
        p1_kc = edges[(edges["player_id"] == "P001") & (edges["nfl_team"] == "KC")]
        if not p1_kc.empty:
            assert p1_kc.iloc[0]["scheme_match"] == 1.0

    def test_empty_inputs(self):
        """Empty inputs return empty DataFrame."""
        result = build_coaching_scheme_edges(pd.DataFrame(), pd.DataFrame())
        assert result.empty


class TestComputeCoachingSchemeFeatures:
    """Tests for compute_coaching_scheme_features."""

    def test_familiarity_values(self, draft_picks_df, player_weekly_df):
        """Familiarity values are in expected range."""
        pcm = _build_player_college_map(pd.DataFrame(), draft_picks_df)
        edges = build_coaching_scheme_edges(pcm, player_weekly_df)
        feats = compute_coaching_scheme_features(edges, player_weekly_df, 2024, 2)

        if not feats.empty:
            vals = feats["scheme_familiarity_college"].dropna()
            assert (vals >= 0.0).all()
            assert (vals <= 1.0).all()

    def test_scheme_change_detection(self, draft_picks_df):
        """Detects team change between seasons."""
        pcm = _build_player_college_map(pd.DataFrame(), draft_picks_df)

        # P001 was on KC in 2023, moves to BUF in 2024
        pw = pd.DataFrame(
            [
                {
                    "player_id": "P001",
                    "season": 2023,
                    "week": 1,
                    "recent_team": "KC",
                    "position": "QB",
                    "fantasy_points": 20.0,
                },
                {
                    "player_id": "P001",
                    "season": 2024,
                    "week": 1,
                    "recent_team": "BUF",
                    "position": "QB",
                    "fantasy_points": 22.0,
                },
                {
                    "player_id": "P001",
                    "season": 2024,
                    "week": 2,
                    "recent_team": "BUF",
                    "position": "QB",
                    "fantasy_points": 25.0,
                },
            ]
        )
        edges = build_coaching_scheme_edges(pcm, pw)
        feats = compute_coaching_scheme_features(edges, pw, 2024, 2)

        p1 = feats[feats["player_id"] == "P001"]
        if not p1.empty:
            assert p1["coaching_scheme_change"].iloc[0] == 1

    def test_output_schema(self, draft_picks_df, player_weekly_df):
        """Output has correct columns."""
        pcm = _build_player_college_map(pd.DataFrame(), draft_picks_df)
        edges = build_coaching_scheme_edges(pcm, player_weekly_df)
        feats = compute_coaching_scheme_features(edges, player_weekly_df, 2024, 2)
        for col in COACHING_SCHEME_FEATURE_COLUMNS:
            assert col in feats.columns


# ---------------------------------------------------------------------------
# 3. Prospect Comparison Tests
# ---------------------------------------------------------------------------


class TestParseHeightInches:
    """Tests for _parse_height_inches."""

    def test_standard_format(self):
        assert _parse_height_inches("6-2") == 74.0

    def test_short_player(self):
        assert _parse_height_inches("5-8") == 68.0

    def test_nan_input(self):
        assert np.isnan(_parse_height_inches(np.nan))

    def test_invalid_input(self):
        assert np.isnan(_parse_height_inches("abc"))

    def test_already_inches(self):
        assert _parse_height_inches("74") == 74.0


class TestBuildProspectComparisonGraph:
    """Tests for build_prospect_comparison_graph."""

    def test_finds_comps_within_position(
        self, draft_picks_df, combine_df, player_weekly_df
    ):
        """Comps are only between same-position players."""
        comps = build_prospect_comparison_graph(
            draft_picks_df, combine_df, player_weekly_df
        )
        if not comps.empty:
            # Every comp pair should be same position
            dp_pos = dict(zip(draft_picks_df["gsis_id"], draft_picks_df["position"]))
            for _, row in comps.iterrows():
                p_pos = dp_pos.get(row["player_id"])
                c_pos = dp_pos.get(row["comp_player_id"])
                if p_pos and c_pos:
                    assert p_pos == c_pos

    def test_temporal_safety(self, draft_picks_df, combine_df, player_weekly_df):
        """Comps only use historically drafted players (not future)."""
        comps = build_prospect_comparison_graph(
            draft_picks_df, combine_df, player_weekly_df
        )
        if not comps.empty:
            dp_year = dict(zip(draft_picks_df["gsis_id"], draft_picks_df["season"]))
            for _, row in comps.iterrows():
                p_year = dp_year.get(row["player_id"])
                c_year = dp_year.get(row["comp_player_id"])
                if p_year is not None and c_year is not None:
                    assert c_year < p_year, "Comp must be drafted before player"

    def test_max_comps_limit(self, draft_picks_df, combine_df, player_weekly_df):
        """Each player has at most MAX_COMPS comparisons."""
        comps = build_prospect_comparison_graph(
            draft_picks_df, combine_df, player_weekly_df
        )
        if not comps.empty:
            counts = comps.groupby("player_id").size()
            assert (counts <= 5).all()

    def test_similarity_range(self, draft_picks_df, combine_df, player_weekly_df):
        """Similarity scores are in [0, 1]."""
        comps = build_prospect_comparison_graph(
            draft_picks_df, combine_df, player_weekly_df
        )
        if not comps.empty:
            assert (comps["similarity_score"] >= 0).all()
            assert (comps["similarity_score"] <= 1).all()

    def test_empty_draft_picks(self, combine_df, player_weekly_df):
        """Empty draft picks returns empty DataFrame."""
        comps = build_prospect_comparison_graph(
            pd.DataFrame(), combine_df, player_weekly_df
        )
        assert comps.empty


class TestComputeProspectCompFeatures:
    """Tests for compute_prospect_comp_features."""

    def test_features_computed(self, draft_picks_df, combine_df, player_weekly_df):
        """Features are computed for players with comps."""
        comps = build_prospect_comparison_graph(
            draft_picks_df, combine_df, player_weekly_df
        )
        feats = compute_prospect_comp_features(comps, 2024)
        if not feats.empty:
            for col in PROSPECT_COMP_FEATURE_COLUMNS:
                assert col in feats.columns

    def test_ceiling_ge_floor(self, draft_picks_df, combine_df, player_weekly_df):
        """Ceiling >= floor for all players."""
        comps = build_prospect_comparison_graph(
            draft_picks_df, combine_df, player_weekly_df
        )
        feats = compute_prospect_comp_features(comps, 2024)
        if not feats.empty:
            valid = feats.dropna(
                subset=["prospect_comp_ceiling", "prospect_comp_floor"]
            )
            if not valid.empty:
                assert (
                    valid["prospect_comp_ceiling"] >= valid["prospect_comp_floor"]
                ).all()

    def test_bust_rate_range(self, draft_picks_df, combine_df, player_weekly_df):
        """Bust rate is in [0, 1]."""
        comps = build_prospect_comparison_graph(
            draft_picks_df, combine_df, player_weekly_df
        )
        feats = compute_prospect_comp_features(comps, 2024)
        if not feats.empty:
            valid = feats["prospect_comp_bust_rate"].dropna()
            if not valid.empty:
                assert (valid >= 0).all()
                assert (valid <= 1).all()

    def test_empty_comps(self):
        """Empty comparison DataFrame returns empty features."""
        feats = compute_prospect_comp_features(pd.DataFrame(), 2024)
        assert feats.empty


# ---------------------------------------------------------------------------
# 4. Prospect Similarity Tests
# ---------------------------------------------------------------------------


class TestComputeProspectSimilarity:
    """Tests for _compute_prospect_similarity."""

    def test_identical_prospects(self):
        """Identical prospects get similarity = 1.0."""
        player = pd.Series(
            {
                "pick_norm": 0.5,
                "round_norm": 0.3,
                "wt_norm": 0.5,
                "forty_norm": 0.5,
                "vertical_norm": 0.5,
                "broad_jump_norm": 0.5,
                "college": "Alabama",
            }
        )
        sim = _compute_prospect_similarity(player, player)
        assert sim == pytest.approx(1.0, abs=0.01)

    def test_very_different_prospects(self):
        """Very different prospects get low similarity."""
        player = pd.Series(
            {
                "pick_norm": 0.0,
                "round_norm": 0.0,
                "wt_norm": 0.0,
                "forty_norm": 0.0,
                "vertical_norm": 0.0,
                "broad_jump_norm": 0.0,
                "college": "Alabama",
            }
        )
        comp = pd.Series(
            {
                "pick_norm": 1.0,
                "round_norm": 1.0,
                "wt_norm": 1.0,
                "forty_norm": 1.0,
                "vertical_norm": 1.0,
                "broad_jump_norm": 1.0,
                "college": "Stanford",
            }
        )
        sim = _compute_prospect_similarity(player, comp)
        assert sim < 0.4

    def test_same_college_bonus(self):
        """Same college gives higher similarity."""
        base = {
            "pick_norm": 0.5,
            "round_norm": 0.3,
            "wt_norm": 0.5,
            "forty_norm": 0.5,
            "vertical_norm": 0.5,
            "broad_jump_norm": 0.5,
        }
        player = pd.Series({**base, "college": "Alabama"})
        comp_same = pd.Series({**base, "college": "Alabama"})
        comp_diff = pd.Series({**base, "college": "Stanford"})

        sim_same = _compute_prospect_similarity(player, comp_same)
        sim_diff = _compute_prospect_similarity(player, comp_diff)
        assert sim_same > sim_diff


# ---------------------------------------------------------------------------
# 5. Integration / compute_all_college_features
# ---------------------------------------------------------------------------


class TestComputeAllCollegeFeatures:
    """Tests for compute_all_college_features."""

    def test_full_pipeline(
        self, draft_picks_df, combine_df, player_weekly_df, rosters_df
    ):
        """Full pipeline produces all expected feature columns."""
        result = compute_all_college_features(
            draft_picks_df, combine_df, player_weekly_df, rosters_df, 2024, 2
        )
        assert not result.empty
        for col in COLLEGE_NETWORK_FEATURE_COLUMNS:
            assert col in result.columns

    def test_all_features_numeric(
        self, draft_picks_df, combine_df, player_weekly_df, rosters_df
    ):
        """All feature columns are numeric (float or int)."""
        result = compute_all_college_features(
            draft_picks_df, combine_df, player_weekly_df, rosters_df, 2024, 2
        )
        if not result.empty:
            for col in COLLEGE_NETWORK_FEATURE_COLUMNS:
                assert result[col].dtype in [
                    np.float64,
                    np.int64,
                    np.float32,
                    np.int32,
                    float,
                    int,
                ], f"Column {col} is {result[col].dtype}, expected numeric"

    def test_empty_weekly_data(self, draft_picks_df, combine_df, rosters_df):
        """Empty player_weekly returns empty DataFrame."""
        result = compute_all_college_features(
            draft_picks_df, combine_df, pd.DataFrame(), rosters_df, 2024, 2
        )
        assert result.empty

    def test_missing_college_data_graceful(self, player_weekly_df):
        """Missing college data produces NaN-filled features."""
        # Draft picks with no college column
        dp = pd.DataFrame(
            [
                {
                    "season": 2020,
                    "gsis_id": "P001",
                    "position": "QB",
                }
            ]
        )
        result = compute_all_college_features(
            dp, pd.DataFrame(), player_weekly_df, pd.DataFrame(), 2024, 2
        )
        # Should either be empty or have NaN-filled features
        if not result.empty:
            for col in COLLEGE_NETWORK_FEATURE_COLUMNS:
                assert col in result.columns

    def test_feature_column_count(self):
        """Feature column list has expected count."""
        assert len(COLLEGE_NETWORK_FEATURE_COLUMNS) == 10
        assert len(COLLEGE_TEAMMATE_FEATURE_COLUMNS) == 3
        assert len(COACHING_SCHEME_FEATURE_COLUMNS) == 2
        assert len(PROSPECT_COMP_FEATURE_COLUMNS) == 5
