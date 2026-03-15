"""Unit tests for historical_profiles combine/draft compute functions."""

import math
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, "src")

from historical_profiles import (
    parse_height_to_inches,
    compute_speed_score,
    compute_composite_scores,
    compute_position_percentiles,
    build_jimmy_johnson_chart,
    dedup_combine,
    join_combine_draft,
    build_combine_draft_profiles,
)


# ---------------------------------------------------------------------------
# parse_height_to_inches
# ---------------------------------------------------------------------------
class TestParseHeight:
    def test_parse_height_valid(self):
        assert parse_height_to_inches("5-11") == 71.0
        assert parse_height_to_inches("6-4") == 76.0
        assert parse_height_to_inches("5-0") == 60.0

    def test_parse_height_invalid(self):
        assert parse_height_to_inches(None) is None
        assert parse_height_to_inches("") is None
        assert parse_height_to_inches("abc") is None
        assert parse_height_to_inches(float("nan")) is None


# ---------------------------------------------------------------------------
# compute_speed_score
# ---------------------------------------------------------------------------
class TestSpeedScore:
    def test_compute_speed_score(self):
        wt = pd.Series([200.0])
        forty = pd.Series([4.5])
        result = compute_speed_score(wt, forty)
        expected = (200 * 200) / (4.5 ** 4)
        assert abs(result.iloc[0] - expected) < 0.01

    def test_compute_speed_score_nan(self):
        wt = pd.Series([200.0])
        forty = pd.Series([float("nan")])
        result = compute_speed_score(wt, forty)
        assert pd.isna(result.iloc[0])


# ---------------------------------------------------------------------------
# compute_composite_scores
# ---------------------------------------------------------------------------
class TestCompositeScores:
    def _make_df(self, **overrides):
        row = {
            "ht": "6-0",
            "wt": 220.0,
            "forty": 4.5,
            "vertical": 36.0,
            "broad_jump": 120.0,
            "pos": "WR",
        }
        row.update(overrides)
        return pd.DataFrame([row])

    def test_all_composite_cols_present(self):
        df = self._make_df()
        result = compute_composite_scores(df)
        for col in ["height_inches", "speed_score", "bmi", "burst_score", "catch_radius"]:
            assert col in result.columns, f"Missing column: {col}"
        assert result["height_inches"].iloc[0] == 72.0
        assert result["burst_score"].iloc[0] == 156.0  # 36 + 120
        assert result["catch_radius"].iloc[0] == 72.0

    def test_nan_propagation(self):
        """Missing forty -> speed_score is NaN, other composites still computed."""
        df = self._make_df(forty=float("nan"))
        result = compute_composite_scores(df)
        assert pd.isna(result["speed_score"].iloc[0])
        # height_inches should still be computed
        assert result["height_inches"].iloc[0] == 72.0
        # burst_score should still be computed
        assert result["burst_score"].iloc[0] == 156.0


# ---------------------------------------------------------------------------
# compute_position_percentiles
# ---------------------------------------------------------------------------
class TestPositionPercentiles:
    def test_percentiles_within_position(self):
        df = pd.DataFrame({
            "pos": ["WR", "WR", "WR"],
            "speed_score": [90.0, 100.0, 110.0],
        })
        result = compute_position_percentiles(df, ["speed_score"])
        assert "speed_score_pos_pctl" in result.columns
        pctls = result["speed_score_pos_pctl"].tolist()
        # rank(pct=True) for 3 values: 1/3, 2/3, 3/3
        assert pctls == pytest.approx([1 / 3, 2 / 3, 1.0], abs=0.01)


# ---------------------------------------------------------------------------
# build_jimmy_johnson_chart
# ---------------------------------------------------------------------------
class TestJimmyJohnsonChart:
    def test_completeness(self):
        chart = build_jimmy_johnson_chart()
        assert len(chart) == 262
        assert chart[1] == 3000
        assert chart[32] == 590
        assert chart[262] >= 0.4

    def test_monotonic_decreasing(self):
        chart = build_jimmy_johnson_chart()
        for n in range(1, 262):
            assert chart[n] >= chart[n + 1], (
                f"Not monotonic at pick {n}: {chart[n]} < {chart[n + 1]}"
            )


# ---------------------------------------------------------------------------
# dedup_combine
# ---------------------------------------------------------------------------
class TestDedupCombine:
    def test_dedup_keeps_correct_row(self):
        """Two rows share pfr_id; one matches draft_year -> keep that one."""
        df = pd.DataFrame({
            "pfr_id": ["A001", "A001"],
            "season": [2020, 2021],
            "draft_year": [2021, 2021],
            "ht": ["6-0", "6-1"],
            "wt": [200.0, 210.0],
        })
        result = dedup_combine(df)
        assert len(result) == 1
        # Should keep the row where season == draft_year (2021)
        assert result["ht"].iloc[0] == "6-1"

    def test_dedup_null_pfr_id_preserved(self):
        """Rows with null pfr_id are all preserved."""
        df = pd.DataFrame({
            "pfr_id": [None, None, "B001"],
            "season": [2020, 2021, 2022],
            "draft_year": [2020, 2021, 2022],
            "ht": ["5-10", "5-11", "6-2"],
            "wt": [180.0, 190.0, 230.0],
        })
        result = dedup_combine(df)
        assert len(result) == 3  # 2 nulls + 1 non-null


# ---------------------------------------------------------------------------
# join_combine_draft
# ---------------------------------------------------------------------------
class TestJoinCombineDraft:
    def _make_combine(self, n=5):
        return pd.DataFrame({
            "pfr_id": ["C01", "C02", "C03", None, None][:n],
            "season": [2020, 2020, 2021, 2020, 2021][:n],
            "pos": ["WR", "RB", "QB", "TE", "WR"][:n],
            "ht": ["6-0", "5-10", "6-3", "6-4", "5-11"][:n],
            "wt": [200.0, 210.0, 225.0, 250.0, 185.0][:n],
            "forty": [4.4, 4.5, 4.7, 4.8, 4.55][:n],
            "vertical": [38.0, 35.0, 33.0, 30.0, 36.0][:n],
            "broad_jump": [125.0, 118.0, 115.0, 110.0, 120.0][:n],
        })

    def _make_draft(self, n=5):
        return pd.DataFrame({
            "pfr_player_id": ["C01", "C02", "C03", "D01", "D02"][:n],
            "gsis_id": ["G01", "G02", "G03", "G04", "G05"][:n],
            "season": [2020, 2020, 2021, 2022, 2023][:n],
            "position": ["WR", "RB", "QB", "LB", "CB"][:n],
            "pick": [10, 50, 1, 200, 100][:n],
        })

    def test_join_no_explosion(self):
        """combine(5 rows) + draft(5 rows) with 3 overlapping -> 7 rows."""
        combine = self._make_combine(5)
        draft = self._make_draft(5)
        result = join_combine_draft(combine, draft)
        # 3 matched + 2 combine-only (null pfr_id) + 2 draft-only = 7
        assert len(result) == 7

    def test_join_preserves_undrafted(self):
        """Combine-only player has NaN draft_value."""
        combine = self._make_combine(5)
        draft = self._make_draft(3)  # Only C01, C02, C03
        result = join_combine_draft(combine, draft)
        # Null pfr_id rows should have NaN draft_value
        null_pfr_rows = result[result["has_pfr_id"] == False]
        assert null_pfr_rows["draft_value"].isna().all()

    def test_join_preserves_drafted_no_combine(self):
        """Draft-only player has NaN measurables."""
        combine = self._make_combine(3)  # C01, C02, C03 only
        draft = self._make_draft(5)  # Includes D01, D02 (no combine)
        result = join_combine_draft(combine, draft)
        draft_only = result[result["pfr_id"] == "D01"]
        assert len(draft_only) == 1
        assert pd.isna(draft_only["ht"].iloc[0])


# ---------------------------------------------------------------------------
# build_combine_draft_profiles (end-to-end)
# ---------------------------------------------------------------------------
class TestBuildProfiles:
    def test_end_to_end(self):
        """Full pipeline with synthetic data produces valid output."""
        combine_df = pd.DataFrame({
            "pfr_id": ["P01", "P02", "P03", None, None],
            "season": [2020, 2020, 2021, 2020, 2021],
            "draft_year": [2020, 2020, 2021, 2020, 2021],
            "pos": ["WR", "RB", "QB", "TE", "WR"],
            "ht": ["6-0", "5-10", "6-3", "6-4", "5-11"],
            "wt": [200.0, 210.0, 225.0, 250.0, 185.0],
            "forty": [4.4, 4.5, 4.7, 4.8, 4.55],
            "vertical": [38.0, 35.0, 33.0, 30.0, 36.0],
            "broad_jump": [125.0, 118.0, 115.0, 110.0, 120.0],
        })
        draft_df = pd.DataFrame({
            "pfr_player_id": ["P01", "P02", "P03", "D01"],
            "gsis_id": ["G01", "G02", "G03", "G04"],
            "season": [2020, 2020, 2021, 2022],
            "position": ["WR", "RB", "QB", "LB"],
            "pick": [10, 50, 1, 200],
        })

        result = build_combine_draft_profiles(combine_df, draft_df)

        # 3 matched + 2 combine-only (null pfr_id) + 1 draft-only = 6
        assert len(result) == 6

        # Check composite score columns exist
        for col in ["speed_score", "bmi", "burst_score", "catch_radius"]:
            assert col in result.columns

        # Check percentile columns exist
        for col in ["speed_score_pos_pctl", "bmi_pos_pctl", "burst_score_pos_pctl", "catch_radius_pos_pctl"]:
            assert col in result.columns

        # Check draft_value column
        assert "draft_value" in result.columns

        # Verify no _x/_y suffix columns remain
        suffix_cols = [c for c in result.columns if c.endswith("_x") or c.endswith("_y")]
        assert suffix_cols == [], f"Unexpected suffix columns: {suffix_cols}"

        # Draft-only player should have NaN measurables
        draft_only = result[result["pfr_id"] == "D01"]
        if len(draft_only) > 0:
            assert pd.isna(draft_only["speed_score"].iloc[0])
