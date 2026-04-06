"""
Tests for college prospect features and college data adapter.

Covers:
- Conference adjustment computation (static + data-driven)
- Prospect similarity with synthetic data
- Scheme familiarity scoring
- College production features
- Graceful degradation when CFBD API unavailable
- Integration with preseason projections (college features as input)
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

# Add project root to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from college_prospect_features import (
    DEFAULT_CONFERENCE_MULTIPLIERS,
    COLLEGE_SCHEME_MAP,
    NFL_SCHEME_MAP,
    _DEFAULT_CONFERENCE_MULT,
    build_prospect_profile,
    compute_college_production_features,
    compute_conference_adjustment,
    compute_prospect_similarity,
    compute_scheme_familiarity,
)
from college_data_adapter import CollegeDataAdapter, pivot_player_stats


# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def college_stats_df():
    """Synthetic college stats DataFrame (wide form)."""
    return pd.DataFrame(
        {
            "player_name": ["Player A", "Player B", "Player C", "Player D"],
            "college_team": ["Alabama", "Ohio State", "Navy", "Stanford"],
            "conference": ["SEC", "Big Ten", "AAC", "ACC"],
            "position": ["WR", "RB", "RB", "TE"],
            "season": [2024, 2024, 2024, 2024],
            "receiving_yards": [1200, 300, 50, 800],
            "receiving_tds": [12, 2, 0, 6],
            "rushing_yards": [50, 1400, 900, 30],
            "rushing_tds": [0, 15, 10, 0],
            "receptions": [80, 20, 5, 55],
            "games": [13, 13, 12, 13],
        }
    )


@pytest.fixture
def prospect_df():
    """Synthetic prospect DataFrame for similarity testing."""
    return pd.DataFrame(
        {
            "player_name": ["Rookie WR", "Rookie RB"],
            "player_id": ["rk_wr_01", "rk_rb_01"],
            "position": ["WR", "RB"],
            "pick": [10, 35],
            "conference": ["SEC", "Big Ten"],
            "college_team": ["Alabama", "Ohio State"],
            "recent_team": ["DAL", "SF"],
            "forty": [4.38, 4.45],
            "wt": [195, 215],
            "ht": ["6-1", "5-11"],
        }
    )


@pytest.fixture
def historical_df():
    """Synthetic historical players with combine + draft + NFL outcomes."""
    return pd.DataFrame(
        {
            "player_name": [
                "Hist WR A",
                "Hist WR B",
                "Hist WR C",
                "Hist WR D",
                "Hist WR E",
                "Hist WR F",
                "Hist RB A",
                "Hist RB B",
                "Hist RB C",
                "Hist RB D",
                "Hist RB E",
            ],
            "position": [
                "WR",
                "WR",
                "WR",
                "WR",
                "WR",
                "WR",
                "RB",
                "RB",
                "RB",
                "RB",
                "RB",
            ],
            "pick": [5, 12, 20, 32, 8, 15, 10, 25, 40, 50, 30],
            "conference": [
                "SEC",
                "Big Ten",
                "ACC",
                "SEC",
                "Big Ten",
                "Pac-12",
                "Big Ten",
                "SEC",
                "ACC",
                "Big 12",
                "SEC",
            ],
            "forty": [4.35, 4.42, 4.48, 4.40, 4.38, 4.50, 4.40, 4.48, 4.55, 4.50, 4.42],
            "wt": [190, 200, 205, 195, 192, 210, 210, 220, 225, 215, 218],
            "ht": [
                "6-0",
                "6-2",
                "6-1",
                "6-0",
                "6-1",
                "6-3",
                "5-10",
                "5-11",
                "6-0",
                "5-11",
                "6-0",
            ],
            "nfl_season1_pts": [
                180,
                150,
                120,
                200,
                170,
                100,
                160,
                130,
                90,
                110,
                145,
            ],
        }
    )


# ── Conference Adjustment Tests ───────────────────────────────────────────


class TestConferenceAdjustment:
    def test_static_defaults_returned_without_nfl_data(self, college_stats_df):
        """Without NFL career data, static defaults are returned."""
        result = compute_conference_adjustment(college_stats_df)
        assert isinstance(result, dict)
        assert result["SEC"] == 1.10
        assert result["Big Ten"] == 1.05
        assert result["AAC"] == 0.90

    def test_includes_all_conferences_in_data(self, college_stats_df):
        """Result includes every conference present in the college data."""
        result = compute_conference_adjustment(college_stats_df)
        for conf in college_stats_df["conference"].unique():
            assert conf in result

    def test_unknown_conference_gets_default(self):
        """A conference not in the static map gets the fallback multiplier."""
        df = pd.DataFrame({"conference": ["Galactic Conference"]})
        result = compute_conference_adjustment(df)
        assert result["Galactic Conference"] == _DEFAULT_CONFERENCE_MULT

    def test_data_driven_with_nfl_career(self):
        """When NFL career data is provided, data-driven multipliers are computed."""
        college_df = pd.DataFrame({"conference": ["SEC", "AAC"]})
        nfl_df = pd.DataFrame(
            {
                "conference": ["SEC", "SEC", "AAC", "AAC"],
                "season": [2020, 2021, 2020, 2021],
                "draft_year": [2020, 2020, 2020, 2020],
                "fantasy_points": [200, 220, 100, 110],
            }
        )
        result = compute_conference_adjustment(college_df, nfl_df)
        assert isinstance(result, dict)
        # SEC should be higher than AAC
        assert result["SEC"] > result["AAC"]

    def test_empty_college_data(self):
        """Empty college data returns static defaults for known conferences."""
        result = compute_conference_adjustment(pd.DataFrame())
        assert "SEC" in result
        assert result["SEC"] == 1.10


# ── Prospect Similarity Tests ────────────────────────────────────────────


class TestProspectSimilarity:
    def test_returns_comp_columns(self, prospect_df, historical_df):
        """Result contains median, ceiling, floor, and comp_names."""
        result = compute_prospect_similarity(prospect_df, historical_df, k=3)
        assert not result.empty
        for col in [
            "prospect_comp_median",
            "prospect_comp_ceiling",
            "prospect_comp_floor",
            "comp_names",
        ]:
            assert col in result.columns

    def test_k_comps_respected(self, prospect_df, historical_df):
        """Number of comps does not exceed k."""
        result = compute_prospect_similarity(prospect_df, historical_df, k=3)
        for _, row in result.iterrows():
            n_names = len(row["comp_names"].split(", ")) if row["comp_names"] else 0
            assert n_names <= 3

    def test_position_filtering(self, prospect_df, historical_df):
        """Comps are filtered to the same position."""
        result = compute_prospect_similarity(prospect_df, historical_df, k=5)
        # WR prospect should get WR comps, not RB
        wr_row = result[result["position"] == "WR"]
        if not wr_row.empty:
            comp_names = wr_row.iloc[0]["comp_names"]
            # All comps should be from the historical WR set
            for name in comp_names.split(", "):
                assert "WR" in name or name.startswith("Hist WR")

    def test_empty_prospect_returns_empty(self, historical_df):
        """Empty prospect DataFrame returns empty result."""
        result = compute_prospect_similarity(pd.DataFrame(), historical_df, k=5)
        assert result.empty

    def test_empty_historical_returns_empty(self, prospect_df):
        """Empty historical DataFrame returns empty result."""
        result = compute_prospect_similarity(prospect_df, pd.DataFrame(), k=5)
        assert result.empty

    def test_comp_values_are_numeric(self, prospect_df, historical_df):
        """Floor, median, ceiling are numeric (not NaN when comps exist)."""
        result = compute_prospect_similarity(prospect_df, historical_df, k=3)
        for col in [
            "prospect_comp_median",
            "prospect_comp_ceiling",
            "prospect_comp_floor",
        ]:
            values = result[col].dropna()
            assert len(values) > 0
            assert all(isinstance(v, (int, float, np.floating)) for v in values)

    def test_ceiling_gte_median_gte_floor(self, prospect_df, historical_df):
        """Ceiling >= median >= floor for each prospect."""
        result = compute_prospect_similarity(prospect_df, historical_df, k=5)
        for _, row in result.iterrows():
            if pd.notna(row["prospect_comp_ceiling"]):
                assert row["prospect_comp_ceiling"] >= row["prospect_comp_median"]
                assert row["prospect_comp_median"] >= row["prospect_comp_floor"]


# ── Scheme Familiarity Tests ─────────────────────────────────────────────


class TestSchemeFamiliarity:
    def test_same_scheme_gets_max_score(self):
        """A prospect whose college and NFL team share a scheme gets 1.0."""
        df = pd.DataFrame(
            {
                "college_team": ["Alabama"],  # spread
                "recent_team": ["DAL"],  # spread
            }
        )
        result = compute_scheme_familiarity(df)
        assert result["scheme_familiarity_score"].iloc[0] == 1.0

    def test_different_scheme_gets_lower_score(self):
        """Different scheme families get a score < 1.0."""
        df = pd.DataFrame(
            {
                "college_team": ["Navy"],  # option
                "recent_team": ["KC"],  # spread
            }
        )
        result = compute_scheme_familiarity(df)
        assert result["scheme_familiarity_score"].iloc[0] < 1.0

    def test_unknown_college_gets_neutral(self):
        """Unknown college team gets a neutral 0.5 score."""
        df = pd.DataFrame(
            {
                "college_team": ["Unknown University"],
                "recent_team": ["KC"],
            }
        )
        result = compute_scheme_familiarity(df)
        assert result["scheme_familiarity_score"].iloc[0] == 0.5

    def test_missing_columns_gets_neutral(self):
        """Missing college_team column produces neutral 0.5."""
        df = pd.DataFrame({"recent_team": ["KC"]})
        result = compute_scheme_familiarity(df)
        assert result["scheme_familiarity_score"].iloc[0] == 0.5

    def test_adjacent_schemes_intermediate_score(self):
        """Adjacent scheme families get a score between 0.5 and 1.0."""
        df = pd.DataFrame(
            {
                "college_team": ["Stanford"],  # pro_style
                "recent_team": ["SF"],  # west_coast
            }
        )
        result = compute_scheme_familiarity(df)
        score = result["scheme_familiarity_score"].iloc[0]
        assert 0.5 < score < 1.0


# ── College Production Features Tests ────────────────────────────────────


class TestCollegeProductionFeatures:
    def test_conference_adjusted_yards(self, college_stats_df):
        """Conference-adjusted yards reflect the conference multiplier."""
        result = compute_college_production_features(college_stats_df)
        # SEC player A: 1250 total yards * 1.10 = 1375.0
        player_a = result[result["player_name"] == "Player A"].iloc[0]
        expected_total = 1200 + 50  # receiving + rushing
        expected_adj = round(expected_total * 1.10, 1)
        assert player_a["conference_adjusted_yards"] == expected_adj

    def test_per_game_rates(self, college_stats_df):
        """Per-game rates are computed correctly."""
        result = compute_college_production_features(college_stats_df)
        player_b = result[result["player_name"] == "Player B"].iloc[0]
        total_yards = 300 + 1400  # receiving + rushing
        total_tds = 2 + 15
        assert player_b["college_yards_per_game"] == round(total_yards / 13, 1)
        assert player_b["college_tds_per_game"] == round(total_tds / 13, 2)

    def test_market_share(self, college_stats_df):
        """Market share represents player's % of team total yards."""
        result = compute_college_production_features(college_stats_df)
        # Each player is on a different team, so each has 100% market share
        for _, row in result.iterrows():
            assert row["college_market_share"] == 100.0

    def test_empty_dataframe(self):
        """Empty input returns empty output."""
        result = compute_college_production_features(pd.DataFrame())
        assert result.empty

    def test_missing_yards_columns(self):
        """Gracefully handles missing yard columns."""
        df = pd.DataFrame(
            {
                "player_name": ["X"],
                "conference": ["SEC"],
                "games": [12],
            }
        )
        result = compute_college_production_features(df)
        assert "conference_adjusted_yards" in result.columns
        assert result["conference_adjusted_yards"].iloc[0] == 0.0

    def test_custom_conference_adjustment(self, college_stats_df):
        """Custom conference multipliers override defaults."""
        custom = {"SEC": 1.50, "Big Ten": 0.80, "AAC": 0.60, "ACC": 0.90}
        result = compute_college_production_features(
            college_stats_df, conference_adj=custom
        )
        player_a = result[result["player_name"] == "Player A"].iloc[0]
        total_yards = 1200 + 50
        assert player_a["conference_adjusted_yards"] == round(total_yards * 1.50, 1)


# ── College Data Adapter Tests ───────────────────────────────────────────


class TestCollegeDataAdapter:
    def test_unavailable_without_api_key(self, monkeypatch):
        """Adapter reports unavailable when CFBD_API_KEY is not set."""
        monkeypatch.delenv("CFBD_API_KEY", raising=False)
        adapter = CollegeDataAdapter()
        assert not adapter.is_available

    def test_all_methods_return_empty_without_key(self, monkeypatch):
        """All fetch methods return empty DataFrames when API key is missing."""
        monkeypatch.delenv("CFBD_API_KEY", raising=False)
        adapter = CollegeDataAdapter()
        assert adapter.fetch_player_season_stats(2024).empty
        assert adapter.fetch_player_usage(2024).empty
        assert adapter.fetch_team_info().empty
        assert adapter.fetch_draft_picks(2024).empty

    def test_available_with_api_key(self, monkeypatch):
        """Adapter reports available when CFBD_API_KEY is set."""
        monkeypatch.setenv("CFBD_API_KEY", "test-key-12345")
        adapter = CollegeDataAdapter()
        assert adapter.is_available


class TestPivotPlayerStats:
    def test_empty_input(self):
        """Pivot of empty DataFrame returns empty."""
        assert pivot_player_stats(pd.DataFrame()).empty

    def test_pivot_produces_wide_format(self):
        """Long-form stats are pivoted to one row per player."""
        raw = pd.DataFrame(
            {
                "player_name": ["A", "A", "A"],
                "college_team": ["T1", "T1", "T1"],
                "conference": ["SEC", "SEC", "SEC"],
                "position": ["WR", "WR", "WR"],
                "season": [2024, 2024, 2024],
                "category": ["receiving", "receiving", "rushing"],
                "stat_type": ["YDS", "TD", "YDS"],
                "stat_value": ["800", "6", "50"],
            }
        )
        result = pivot_player_stats(raw)
        assert len(result) == 1
        assert "receiving_yards" in result.columns
        assert "receiving_tds" in result.columns
        assert "rushing_yards" in result.columns
        assert result["receiving_yards"].iloc[0] == 800
        assert result["receiving_tds"].iloc[0] == 6
        assert result["rushing_yards"].iloc[0] == 50


# ── Integration: Build Prospect Profile ──────────────────────────────────


class TestBuildProspectProfile:
    def test_full_profile_has_all_columns(
        self, prospect_df, historical_df, college_stats_df
    ):
        """build_prospect_profile returns a DataFrame with all feature groups."""
        result = build_prospect_profile(prospect_df, historical_df, college_stats_df)
        assert not result.empty
        expected_cols = [
            "prospect_comp_median",
            "prospect_comp_ceiling",
            "prospect_comp_floor",
            "scheme_familiarity_score",
        ]
        for col in expected_cols:
            assert col in result.columns

    def test_empty_prospect_returns_empty(self, historical_df):
        """Empty prospect input returns empty result."""
        result = build_prospect_profile(pd.DataFrame(), historical_df)
        assert result.empty


# ── Integration: Preseason Projections with College Features ─────────────


class TestPreseasonWithCollegeFeatures:
    def test_college_features_override_draft_boost(self):
        """When college features are provided, they take priority over draft capital."""
        from projection_engine import generate_preseason_projections

        seasonal = pd.DataFrame(
            {
                "player_id": ["p1", "p1", "p2", "p2"],
                "player_name": ["Vet QB", "Vet QB", "Rookie WR", "Rookie WR"],
                "position": ["QB", "QB", "WR", "WR"],
                "season": [2024, 2025, 2025, 2025],
                "passing_yards": [4000, 4200, 0, 0],
                "passing_tds": [30, 32, 0, 0],
                "interceptions": [10, 8, 0, 0],
                "rushing_yards": [200, 250, 0, 0],
                "rushing_tds": [2, 3, 0, 0],
                "receiving_yards": [0, 0, 800, 800],
                "receiving_tds": [0, 0, 5, 5],
                "receptions": [0, 0, 50, 50],
                "targets": [0, 0, 70, 70],
                "carries": [30, 35, 0, 0],
            }
        )

        college_features = pd.DataFrame(
            {
                "player_id": ["p2"],
                "position": ["WR"],
                "prospect_comp_median": [150.0],
                "prospect_comp_ceiling": [220.0],
                "prospect_comp_floor": [90.0],
                "scheme_familiarity_score": [0.85],
            }
        )

        result = generate_preseason_projections(
            seasonal,
            scoring_format="half_ppr",
            target_season=2026,
            college_features_df=college_features,
        )

        assert not result.empty
        rookie_row = result[result["player_id"] == "p2"]
        assert not rookie_row.empty
        # Projection should be based on comp median (150) * scheme factor
        # scheme_factor = 0.90 + 0.85 * 0.15 = 1.0275
        # projected ≈ 150 * 1.0275 ≈ 154.1
        proj_pts = rookie_row["projected_season_points"].iloc[0]
        assert 140 < proj_pts < 170  # reasonable range around comp median

    def test_draft_boost_fallback_without_college(self):
        """Without college features, draft capital boost still applies."""
        from projection_engine import generate_preseason_projections

        seasonal = pd.DataFrame(
            {
                "player_id": ["p1", "p1"],
                "player_name": ["Rookie QB", "Rookie QB"],
                "position": ["QB", "QB"],
                "season": [2025, 2025],
                "passing_yards": [3500, 3500],
                "passing_tds": [22, 22],
                "interceptions": [12, 12],
                "rushing_yards": [100, 100],
                "rushing_tds": [1, 1],
                "receiving_yards": [0, 0],
                "receiving_tds": [0, 0],
                "receptions": [0, 0],
                "targets": [0, 0],
                "carries": [20, 20],
            }
        )

        historical = pd.DataFrame(
            {
                "gsis_id": ["p1"],
                "draft_ovr": [1],
                "draft_year": [2025],
            }
        )

        result_with_boost = generate_preseason_projections(
            seasonal,
            scoring_format="half_ppr",
            target_season=2026,
            historical_df=historical,
        )
        result_no_boost = generate_preseason_projections(
            seasonal,
            scoring_format="half_ppr",
            target_season=2026,
        )

        assert not result_with_boost.empty
        assert not result_no_boost.empty

        boosted = result_with_boost["projected_season_points"].iloc[0]
        unboosted = result_no_boost["projected_season_points"].iloc[0]
        # Pick 1 gets 1.20x boost
        assert boosted > unboosted
