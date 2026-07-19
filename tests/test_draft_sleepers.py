"""Tests for src/draft_sleepers.py -- sleepers tab selection + reason text."""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from draft_sleepers import (  # noqa: E402
    ADP_GAP_THRESHOLD,
    build_sleeper_rows,
)
from projection_engine import (  # noqa: E402
    VACATED_OPPORTUNITY_BETA,
    VACATED_OPPORTUNITY_MULT_MAX,
)


def _available_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            # Big ADP gap only -- should surface via the ADP-gap half.
            {
                "player_id": "P1",
                "player_name": "ADP Faller",
                "position": "WR",
                "recent_team": "KC",
                "model_rank": 40,
                "adp_rank": 90.0,
                "adp_diff": 50.0,  # adp_rank - model_rank
                "projected_season_points": 210.4,
            },
            # Vacated signal only (small ADP gap) -- should surface via UC1.
            {
                "player_id": "P2",
                "player_name": "Vacancy Absorber",
                "position": "RB",
                "recent_team": "SF",
                "model_rank": 60,
                "adp_rank": 65.0,
                "adp_diff": 5.0,
                "projected_season_points": 180.0,
            },
            # Neither signal fires -- excluded.
            {
                "player_id": "P3",
                "player_name": "Fair Value Guy",
                "position": "TE",
                "recent_team": "DET",
                "model_rank": 20,
                "adp_rank": 22.0,
                "adp_diff": 2.0,
                "projected_season_points": 150.0,
            },
            # Kicker with a huge ADP gap -- excluded position.
            {
                "player_id": "P4",
                "player_name": "Sleeper Kicker",
                "position": "K",
                "recent_team": "BAL",
                "model_rank": 5,
                "adp_rank": 300.0,
                "adp_diff": 295.0,
                "projected_season_points": np.nan,
            },
        ]
    )


def _vacated_df() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {"player_id": "P2", "team": "SF", "position": "RB", "vacancy_absorbed_share": 0.30},
        ]
    )


class TestBuildSleeperRows:
    def test_adp_gap_signal_selects_and_labels_reason(self):
        rows = build_sleeper_rows(_available_df(), vacated_df=None)
        names = {r["player_name"] for r in rows}
        assert "ADP Faller" in names
        row = next(r for r in rows if r["player_name"] == "ADP Faller")
        assert row["model_rank"] == 40
        assert row["adp_rank"] == 90.0
        assert row["adp_gap"] == 50.0
        assert row["projected_points"] == pytest.approx(210.4)
        assert "Our rank 40 vs ADP 90 (+50)" in row["reason"]

    def test_vacated_signal_alone_selects_with_honest_reason(self):
        rows = build_sleeper_rows(_available_df(), vacated_df=_vacated_df())
        row = next(r for r in rows if r["player_name"] == "Vacancy Absorber")
        expected_mult = min(
            1.0 + VACATED_OPPORTUNITY_BETA * 0.30, VACATED_OPPORTUNITY_MULT_MAX
        )
        expected_pct = round((expected_mult - 1.0) * 100.0, 1)
        assert f"+{expected_pct:.0f}% boost applied" in row["reason"]
        assert "vacated-opportunity profile" in row["reason"]

    def test_vacated_absent_no_vacated_text_and_not_selected_below_threshold(self):
        rows = build_sleeper_rows(_available_df(), vacated_df=None)
        names = {r["player_name"] for r in rows}
        # Below the ADP-gap threshold and no vacated signal -> excluded.
        assert "Vacancy Absorber" not in names
        for r in rows:
            assert "vacated-opportunity" not in r["reason"]

    def test_fair_value_player_excluded(self):
        rows = build_sleeper_rows(_available_df(), vacated_df=_vacated_df())
        names = {r["player_name"] for r in rows}
        assert "Fair Value Guy" not in names

    def test_kicker_excluded_despite_huge_adp_gap(self):
        rows = build_sleeper_rows(_available_df(), vacated_df=_vacated_df())
        names = {r["player_name"] for r in rows}
        assert "Sleeper Kicker" not in names

    def test_sort_by_blend_descending(self):
        rows = build_sleeper_rows(_available_df(), vacated_df=_vacated_df())
        blends = []
        for r in rows:
            adp_gap = r["adp_gap"] or 0.0
            bonus = 0.0
            if r["player_name"] == "Vacancy Absorber":
                mult = min(
                    1.0 + VACATED_OPPORTUNITY_BETA * 0.30, VACATED_OPPORTUNITY_MULT_MAX
                )
                bonus = round((mult - 1.0) * 100.0, 1)
            blends.append(adp_gap + bonus)
        assert blends == sorted(blends, reverse=True)

    def test_limit_respected(self):
        rows = build_sleeper_rows(_available_df(), limit=1, vacated_df=_vacated_df())
        assert len(rows) == 1

    def test_empty_available_returns_empty(self):
        assert build_sleeper_rows(pd.DataFrame()) == []

    def test_none_available_returns_empty(self):
        assert build_sleeper_rows(None) == []

    def test_vacated_df_missing_columns_fails_open(self):
        bad_vacated = pd.DataFrame([{"player_id": "P2", "team": "SF"}])
        rows = build_sleeper_rows(_available_df(), vacated_df=bad_vacated)
        names = {r["player_name"] for r in rows}
        assert "Vancancy Absorber" not in names  # never crashes; just no boost
        assert "ADP Faller" in names

    def test_threshold_constant(self):
        assert ADP_GAP_THRESHOLD == 15.0
