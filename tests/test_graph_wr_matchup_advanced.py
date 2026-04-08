#!/usr/bin/env python3
"""Tests for advanced WR matchup features in graph_wr_matchup.py.

Covers:
- build_wr_advanced_matchup_features output schema and column presence
- Target concentration computation (WR share of team targets)
- Air yards per target aggregation
- Completed air yards per target (zero on incompletions)
- YAC per catch (only on completions; NaN when no catches)
- Coverage shell EPA: light box (defenders_in_box <= 6) vs heavy box (>= 7)
- Short-pass completion rate (air_yards < 5) as press-coverage proxy
- Middle-of-field target rate and middle EPA as slot alignment proxy
- Empty DataFrame handling for each input edge case
- Strict NaN on division-by-zero paths (no catches, no seam targets, etc.)
- ingest_wr_matchup_graph accepts advanced_features_df parameter
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

ADVANCED_WR_COLUMNS = [
    "wr_matchup_target_concentration",
    "wr_matchup_air_yards_per_target",
    "wr_matchup_completed_air_yards_per_target",
    "wr_matchup_yac_per_catch",
    "wr_matchup_light_box_epa",
    "wr_matchup_heavy_box_epa",
    "wr_matchup_short_pass_completion_rate",
    "wr_matchup_middle_target_rate",
    "wr_matchup_middle_epa",
]

KEY_COLUMNS = ["receiver_player_id", "defteam", "season", "week"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def pbp_df():
    """Synthetic PBP with two WRs facing BUF in week 1.

    WR01 gets 4 of 6 team targets (concentration = 2/3).
    WR02 gets 2 of 6 team targets (concentration = 1/3).

    air_yards / pass_location / defenders_in_box carefully chosen so each
    feature assertion can be verified independently.
    """
    return pd.DataFrame(
        {
            "game_id": ["2024_01_KC_BUF"] * 6,
            "play_id": [1, 2, 3, 4, 5, 6],
            "season": [2024] * 6,
            "week": [1] * 6,
            "play_type": ["pass"] * 6,
            "posteam": ["KC"] * 6,
            "defteam": ["BUF"] * 6,
            # WR01: plays 1,2,3,4  WR02: plays 5,6
            "receiver_player_id": ["WR01", "WR01", "WR01", "WR01", "WR02", "WR02"],
            "complete_pass": [1, 0, 1, 1, 1, 0],
            "yards_gained": [15, 0, 20, 6, 8, 0],
            "touchdown": [0, 0, 0, 0, 0, 0],
            "epa": [0.5, -0.3, 0.8, 0.4, 0.2, -0.1],
            # air_yards: play1=12(deep), play2=3(short), play3=8(mid), play4=4(short)
            # WR02: play5=6, play6=4(short)
            "air_yards": [12.0, 3.0, 8.0, 4.0, 6.0, 4.0],
            # yac only on completions
            "yards_after_catch": [3.0, np.nan, 12.0, 2.0, 2.0, np.nan],
            # pass_location: middle on plays 2,4 for WR01; middle on play 5 for WR02
            "pass_location": ["left", "middle", "right", "middle", "middle", "left"],
            # defenders_in_box: light (<=6) on plays 1,2,5,6; heavy (>=7) on 3,4
            "defenders_in_box": [5, 6, 7, 8, 6, 5],
        }
    )


@pytest.fixture
def multi_week_pbp_df():
    """PBP spanning two weeks to verify grouping by week."""
    return pd.DataFrame(
        {
            "game_id": ["2024_01_KC_BUF", "2024_02_KC_DEN"],
            "play_id": [1, 2],
            "season": [2024, 2024],
            "week": [1, 2],
            "play_type": ["pass", "pass"],
            "posteam": ["KC", "KC"],
            "defteam": ["BUF", "DEN"],
            "receiver_player_id": ["WR01", "WR01"],
            "complete_pass": [1, 0],
            "yards_gained": [10, 0],
            "touchdown": [0, 0],
            "epa": [0.4, -0.2],
            "air_yards": [8.0, 5.0],
            "yards_after_catch": [2.0, np.nan],
            "pass_location": ["left", "right"],
            "defenders_in_box": [6, 7],
        }
    )


# ---------------------------------------------------------------------------
# Tests: output schema
# ---------------------------------------------------------------------------


class TestBuildWrAdvancedMatchupFeaturesSchema:
    """Verify output columns and key identifiers."""

    def test_output_contains_key_columns(self, pbp_df):
        """Output must contain receiver_player_id, defteam, season, week."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())

        for col in KEY_COLUMNS:
            assert col in result.columns, f"Missing key column: {col}"

    def test_output_contains_all_advanced_columns(self, pbp_df):
        """All wr_matchup_* feature columns must be present."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())

        for col in ADVANCED_WR_COLUMNS:
            assert col in result.columns, f"Missing feature column: {col}"

    def test_one_row_per_wr_defteam_season_week(self, pbp_df):
        """Each (WR, defteam, season, week) combination is a single row."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())

        assert result.duplicated(subset=KEY_COLUMNS).sum() == 0

    def test_feature_columns_are_numeric(self, pbp_df):
        """All wr_matchup_* columns must be float dtype."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())

        for col in ADVANCED_WR_COLUMNS:
            assert pd.api.types.is_float_dtype(
                result[col]
            ), f"{col} should be float, got {result[col].dtype}"

    def test_empty_pbp_returns_empty(self):
        """Empty PBP input returns empty DataFrame without raising."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pd.DataFrame(), pd.DataFrame())

        assert result.empty

    def test_no_pass_plays_returns_empty(self):
        """PBP with only run plays returns empty DataFrame."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        pbp = pd.DataFrame(
            {
                "game_id": ["g1"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["run"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": [None],
            }
        )
        result = build_wr_advanced_matchup_features(pbp, pd.DataFrame())

        assert result.empty


# ---------------------------------------------------------------------------
# Tests: target concentration
# ---------------------------------------------------------------------------


class TestTargetConcentration:
    """wr_matchup_target_concentration = WR targets / team pass targets."""

    def test_wr01_concentration(self, pbp_df):
        """WR01 gets 4 of 6 KC targets vs BUF = 2/3."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        assert abs(wr01["wr_matchup_target_concentration"] - 4 / 6) < 1e-6

    def test_wr02_concentration(self, pbp_df):
        """WR02 gets 2 of 6 KC targets vs BUF = 1/3."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr02 = result[result["receiver_player_id"] == "WR02"].iloc[0]

        assert abs(wr02["wr_matchup_target_concentration"] - 2 / 6) < 1e-6

    def test_concentration_sums_to_one_across_wrs(self, pbp_df):
        """Sum of concentrations across all WRs facing same defense == 1."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        buf_week1 = result[(result["defteam"] == "BUF") & (result["week"] == 1)]
        total = buf_week1["wr_matchup_target_concentration"].sum()

        assert abs(total - 1.0) < 1e-6

    def test_separate_concentration_per_week(self, multi_week_pbp_df):
        """Concentration is computed per (week, defteam) group independently."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(multi_week_pbp_df, pd.DataFrame())

        # Each week has only 1 WR, so concentration must be 1.0 in each
        for _, row in result.iterrows():
            assert abs(row["wr_matchup_target_concentration"] - 1.0) < 1e-6


# ---------------------------------------------------------------------------
# Tests: air yards per target
# ---------------------------------------------------------------------------


class TestAirYardsPerTarget:
    """wr_matchup_air_yards_per_target = sum(air_yards) / targets."""

    def test_wr01_air_yards_per_target(self, pbp_df):
        """WR01: (12+3+8+4) / 4 = 6.75."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        expected = (12.0 + 3.0 + 8.0 + 4.0) / 4
        assert abs(wr01["wr_matchup_air_yards_per_target"] - expected) < 1e-6

    def test_completed_air_yards_only_on_completions(self, pbp_df):
        """Completed air yards should be zero on incompletions."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        # WR01 completions: plays 1(ay=12), 3(ay=8), 4(ay=4) -> sum=24; play 2 incomplete
        expected_comp_ay = (12.0 + 8.0 + 4.0) / 4  # per target
        assert (
            abs(wr01["wr_matchup_completed_air_yards_per_target"] - expected_comp_ay)
            < 1e-6
        )


# ---------------------------------------------------------------------------
# Tests: YAC per catch
# ---------------------------------------------------------------------------


class TestYacPerCatch:
    """wr_matchup_yac_per_catch = sum(yac on completions) / catches."""

    def test_wr01_yac_per_catch(self, pbp_df):
        """WR01 catches: plays 1(yac=3), 3(yac=12), 4(yac=2) -> mean=17/3."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        # catches = 3, yac sum = 3+12+2 = 17
        expected = 17.0 / 3.0
        assert abs(wr01["wr_matchup_yac_per_catch"] - expected) < 1e-6

    def test_no_catches_yac_is_nan(self):
        """When a WR has zero catches, yac_per_catch should be NaN."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        pbp = pd.DataFrame(
            {
                "game_id": ["g1"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["pass"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": ["WR01"],
                "complete_pass": [0],
                "yards_gained": [0],
                "touchdown": [0],
                "epa": [-0.3],
                "air_yards": [10.0],
                "yards_after_catch": [np.nan],
                "pass_location": ["left"],
                "defenders_in_box": [6],
            }
        )
        result = build_wr_advanced_matchup_features(pbp, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        assert pd.isna(wr01["wr_matchup_yac_per_catch"])


# ---------------------------------------------------------------------------
# Tests: coverage shell EPA (defenders_in_box)
# ---------------------------------------------------------------------------


class TestCoverageShellEpa:
    """light_box_epa uses plays with defenders_in_box <= 6; heavy_box >= 7."""

    def test_wr01_light_box_epa(self, pbp_df):
        """WR01 light-box plays: play1(dib=5,epa=0.5) play2(dib=6,epa=-0.3)."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        # light: plays 1,2 -> epa average = (0.5 + -0.3) / 2 = 0.1
        assert abs(wr01["wr_matchup_light_box_epa"] - 0.1) < 1e-6

    def test_wr01_heavy_box_epa(self, pbp_df):
        """WR01 heavy-box plays: play3(dib=7,epa=0.8) play4(dib=8,epa=0.4)."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        # heavy: plays 3,4 -> epa average = (0.8 + 0.4) / 2 = 0.6
        assert abs(wr01["wr_matchup_heavy_box_epa"] - 0.6) < 1e-6

    def test_no_heavy_box_plays_gives_nan(self):
        """WR with no heavy-box targets gets NaN for heavy_box_epa."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        pbp = pd.DataFrame(
            {
                "game_id": ["g1", "g1"],
                "play_id": [1, 2],
                "season": [2024, 2024],
                "week": [1, 1],
                "play_type": ["pass", "pass"],
                "posteam": ["KC", "KC"],
                "defteam": ["BUF", "BUF"],
                "receiver_player_id": ["WR01", "WR01"],
                "complete_pass": [1, 0],
                "yards_gained": [10, 0],
                "touchdown": [0, 0],
                "epa": [0.5, -0.2],
                "air_yards": [8.0, 5.0],
                "yards_after_catch": [2.0, np.nan],
                "pass_location": ["left", "right"],
                "defenders_in_box": [5, 6],  # all light box
            }
        )
        result = build_wr_advanced_matchup_features(pbp, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        assert pd.isna(wr01["wr_matchup_heavy_box_epa"])


# ---------------------------------------------------------------------------
# Tests: short-pass completion rate (press proxy)
# ---------------------------------------------------------------------------


class TestShortPassCompletionRate:
    """Short pass = air_yards < 5. Rate = completions / short-pass attempts."""

    def test_wr01_short_pass_completion_rate(self, pbp_df):
        """WR01 short passes: play2(ay=3,comp=0) play4(ay=4,comp=1) -> 1/2=0.5."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        assert abs(wr01["wr_matchup_short_pass_completion_rate"] - 0.5) < 1e-6

    def test_no_short_passes_is_nan(self):
        """WR with no short-pass targets gets NaN."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        pbp = pd.DataFrame(
            {
                "game_id": ["g1"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["pass"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": ["WR01"],
                "complete_pass": [1],
                "yards_gained": [20],
                "touchdown": [0],
                "epa": [1.0],
                "air_yards": [15.0],  # deep, not short
                "yards_after_catch": [5.0],
                "pass_location": ["left"],
                "defenders_in_box": [6],
            }
        )
        result = build_wr_advanced_matchup_features(pbp, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        assert pd.isna(wr01["wr_matchup_short_pass_completion_rate"])


# ---------------------------------------------------------------------------
# Tests: middle target rate and middle EPA (slot proxy)
# ---------------------------------------------------------------------------


class TestMiddleTargetRate:
    """Middle-of-field target rate and EPA as slot alignment proxy."""

    def test_wr01_middle_target_rate(self, pbp_df):
        """WR01: plays 2,4 are middle -> 2/4 = 0.5."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        assert abs(wr01["wr_matchup_middle_target_rate"] - 0.5) < 1e-6

    def test_wr01_middle_epa(self, pbp_df):
        """WR01 middle plays: play2(epa=-0.3) play4(epa=0.4) -> mean=0.05."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        expected = (-0.3 + 0.4) / 2
        assert abs(wr01["wr_matchup_middle_epa"] - expected) < 1e-6

    def test_no_middle_targets_gives_nan_epa(self):
        """WR with no middle targets gets NaN for middle_epa."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        pbp = pd.DataFrame(
            {
                "game_id": ["g1", "g1"],
                "play_id": [1, 2],
                "season": [2024, 2024],
                "week": [1, 1],
                "play_type": ["pass", "pass"],
                "posteam": ["KC", "KC"],
                "defteam": ["BUF", "BUF"],
                "receiver_player_id": ["WR01", "WR01"],
                "complete_pass": [1, 0],
                "yards_gained": [10, 0],
                "touchdown": [0, 0],
                "epa": [0.5, -0.2],
                "air_yards": [8.0, 5.0],
                "yards_after_catch": [2.0, np.nan],
                "pass_location": ["left", "right"],  # no middle
                "defenders_in_box": [5, 6],
            }
        )
        result = build_wr_advanced_matchup_features(pbp, pd.DataFrame())
        wr01 = result[result["receiver_player_id"] == "WR01"].iloc[0]

        assert pd.isna(wr01["wr_matchup_middle_epa"])
        assert abs(wr01["wr_matchup_middle_target_rate"] - 0.0) < 1e-6


# ---------------------------------------------------------------------------
# Tests: grouping correctness
# ---------------------------------------------------------------------------


class TestGroupingCorrectness:
    """Features are computed per (receiver, defteam, season, week) group."""

    def test_separate_rows_per_defteam(self, multi_week_pbp_df):
        """Two different defteam values produce two separate rows."""
        from graph_wr_matchup import build_wr_advanced_matchup_features

        result = build_wr_advanced_matchup_features(multi_week_pbp_df, pd.DataFrame())

        assert len(result) == 2
        assert set(result["defteam"].unique()) == {"BUF", "DEN"}

    def test_missing_optional_columns_handled_gracefully(self):
        """PBP missing air_yards or yac columns should not raise errors.

        When air_yards is absent the column is filled with np.nan, and
        pandas sums NaN as 0 before dividing — so the result is 0.0 (not NaN).
        The important guarantee is that the function does not raise and still
        returns a non-empty result with all expected feature columns present.
        """
        from graph_wr_matchup import build_wr_advanced_matchup_features

        pbp = pd.DataFrame(
            {
                "game_id": ["g1"],
                "play_id": [1],
                "season": [2024],
                "week": [1],
                "play_type": ["pass"],
                "posteam": ["KC"],
                "defteam": ["BUF"],
                "receiver_player_id": ["WR01"],
                "complete_pass": [1],
                "yards_gained": [10],
                "touchdown": [0],
                "epa": [0.5],
                # air_yards, yards_after_catch, defenders_in_box intentionally omitted
            }
        )
        result = build_wr_advanced_matchup_features(pbp, pd.DataFrame())

        assert not result.empty
        # All advanced feature columns must still be present (NaN or 0 are both OK)
        for col in ADVANCED_WR_COLUMNS:
            assert (
                col in result.columns
            ), f"Missing column when optional cols absent: {col}"


# ---------------------------------------------------------------------------
# Tests: ingest_wr_matchup_graph accepts advanced_features_df
# ---------------------------------------------------------------------------


class TestIngestWrMatchupGraphAdvanced:
    """ingest_wr_matchup_graph must accept optional advanced_features_df."""

    def test_ingestion_with_advanced_features(self, pbp_df):
        """Should merge advanced features and write combined edges."""
        from graph_wr_matchup import (
            build_targeted_against_edges,
            build_wr_advanced_matchup_features,
            ingest_wr_matchup_graph,
        )

        targeted = build_targeted_against_edges(pbp_df, pd.DataFrame())
        advanced = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_wr_matchup_graph(
            mock_db, targeted, advanced_features_df=advanced
        )

        assert total > 0
        assert mock_db.run_write.called

    def test_ingestion_without_advanced_features_still_works(self, pbp_df):
        """Omitting advanced_features_df preserves backward compatibility."""
        from graph_wr_matchup import (
            build_targeted_against_edges,
            ingest_wr_matchup_graph,
        )

        targeted = build_targeted_against_edges(pbp_df, pd.DataFrame())

        mock_db = MagicMock()
        mock_db.is_connected = True

        total = ingest_wr_matchup_graph(mock_db, targeted)

        assert total == len(targeted)

    def test_ingestion_disconnected_returns_zero(self, pbp_df):
        """Should return 0 without writing when Neo4j is disconnected."""
        from graph_wr_matchup import (
            build_targeted_against_edges,
            build_wr_advanced_matchup_features,
            ingest_wr_matchup_graph,
        )

        targeted = build_targeted_against_edges(pbp_df, pd.DataFrame())
        advanced = build_wr_advanced_matchup_features(pbp_df, pd.DataFrame())

        mock_db = MagicMock()
        mock_db.is_connected = False

        total = ingest_wr_matchup_graph(
            mock_db, targeted, advanced_features_df=advanced
        )

        assert total == 0
        assert not mock_db.run_write.called
