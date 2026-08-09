"""
Unit tests for the early-season prior blend (lever #1 from
.planning/CONSENSUS_ERROR_DECOMPOSITION.md).
"""

import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from early_season_prior import (  # noqa: E402
    EARLY_SEASON_PRIOR_WEIGHTS,
    MIN_PRIOR_GAMES,
    apply_early_season_prior,
    compute_prior_season_ppg,
)


def _weekly_row(player_id, week, rushing_yards=0, receiving_yards=0, receptions=0):
    return {
        "player_id": player_id,
        "week": week,
        "season": 2024,
        "rushing_yards": rushing_yards,
        "rushing_tds": 0,
        "receiving_yards": receiving_yards,
        "receiving_tds": 0,
        "receptions": receptions,
        "passing_yards": 0,
        "passing_tds": 0,
        "interceptions": 0,
        "fumbles_lost": 0,
    }


class TestComputePriorSeasonPpg(unittest.TestCase):
    def test_ppg_averages_across_games(self):
        # 8 games at 10 rushing yards (half-PPR rush_yd=0.1 -> 1.0 pt/gm)
        rows = [_weekly_row("P1", w, rushing_yards=10) for w in range(1, 9)]
        out = compute_prior_season_ppg(pd.DataFrame(rows), scoring_format="half_ppr")
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out.iloc[0]["prior_ppg"], 1.0, places=2)
        self.assertEqual(out.iloc[0]["prior_games"], 8)

    def test_below_min_games_excluded(self):
        rows = [_weekly_row("P1", w, rushing_yards=10) for w in range(1, MIN_PRIOR_GAMES)]
        out = compute_prior_season_ppg(pd.DataFrame(rows), scoring_format="half_ppr")
        self.assertTrue(out.empty)

    def test_exactly_min_games_included(self):
        rows = [_weekly_row("P1", w, rushing_yards=10) for w in range(1, MIN_PRIOR_GAMES + 1)]
        out = compute_prior_season_ppg(pd.DataFrame(rows), scoring_format="half_ppr")
        self.assertEqual(len(out), 1)

    def test_empty_input_returns_empty_with_columns(self):
        out = compute_prior_season_ppg(pd.DataFrame())
        self.assertTrue(out.empty)
        self.assertEqual(
            list(out.columns), ["player_id", "prior_ppg", "prior_games"]
        )

    def test_missing_player_id_returns_empty(self):
        out = compute_prior_season_ppg(pd.DataFrame([{"week": 1, "rushing_yards": 10}]))
        self.assertTrue(out.empty)


class TestApplyEarlySeasonPrior(unittest.TestCase):
    @staticmethod
    def _proj(player_id="P1", pos="RB", pts=10.0):
        return pd.DataFrame(
            [{"player_id": player_id, "position": pos, "projected_points": pts}]
        )

    @staticmethod
    def _prior(player_id="P1", ppg=20.0, games=10):
        return pd.DataFrame(
            [{"player_id": player_id, "prior_ppg": ppg, "prior_games": games}]
        )

    def test_week3_blends_at_schedule_weight(self):
        out = apply_early_season_prior(self._proj(pts=10.0), self._prior(ppg=20.0), week=3)
        # w=0.4: 0.6*10 + 0.4*20 = 6 + 8 = 14
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 14.0, places=2)
        self.assertAlmostEqual(out.iloc[0]["prior_season_ppg"], 20.0, places=2)

    def test_week6_uses_smallest_weight(self):
        out = apply_early_season_prior(self._proj(pts=10.0), self._prior(ppg=20.0), week=6)
        # w=0.1: 0.9*10 + 0.1*20 = 9 + 2 = 11
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 11.0, places=2)

    def test_week7_is_noop(self):
        out = apply_early_season_prior(self._proj(pts=10.0), self._prior(ppg=20.0), week=7)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)
        self.assertTrue(pd.isna(out.iloc[0]["prior_season_ppg"]))

    def test_week2_is_noop(self):
        out = apply_early_season_prior(self._proj(pts=10.0), self._prior(ppg=20.0), week=2)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_scale_zero_disables(self):
        out = apply_early_season_prior(
            self._proj(pts=10.0), self._prior(ppg=20.0), week=3, scale=0.0
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_scale_multiplies_schedule(self):
        out = apply_early_season_prior(
            self._proj(pts=10.0), self._prior(ppg=20.0), week=3, scale=0.5
        )
        # w = 0.4*0.5 = 0.2: 0.8*10 + 0.2*20 = 8 + 4 = 12
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 12.0, places=2)

    def test_player_without_prior_untouched(self):
        out = apply_early_season_prior(
            self._proj(player_id="P2", pts=10.0), self._prior(player_id="P1", ppg=20.0),
            week=3,
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)
        self.assertTrue(pd.isna(out.iloc[0]["prior_season_ppg"]))

    def test_non_skill_position_untouched(self):
        out = apply_early_season_prior(
            self._proj(pos="K", pts=10.0), self._prior(ppg=20.0), week=3
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_empty_prior_is_noop_with_provenance_column(self):
        out = apply_early_season_prior(self._proj(pts=10.0), pd.DataFrame(), week=3)
        self.assertIn("prior_season_ppg", out.columns)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_default_schedule_shape(self):
        self.assertEqual(
            EARLY_SEASON_PRIOR_WEIGHTS, {3: 0.4, 4: 0.3, 5: 0.2, 6: 0.1}
        )


if __name__ == "__main__":
    unittest.main()
