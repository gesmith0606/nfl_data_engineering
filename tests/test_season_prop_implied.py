"""
Unit tests for season prop-implied projections (season futures → blend).
"""

import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from season_prop_implied import (  # noqa: E402
    SEASON_CORE_MARKETS_BY_POS,
    SEASON_MARKET_CV,
    SEASON_MARKET_TO_STAT,
    SEASON_PROPS_BLEND_LAMBDAS,
    apply_season_props_blend,
    compute_season_prop_implied_points,
)


def _season_prop_row(player, market, line, over=-110, under=-110):
    return {
        "snapshot_ts": "2026-08-02T12:00:00+00:00",
        "bookmaker": "draftkings",
        "market": market,
        "market_name": f"NFL 2026/27 - {player} X",
        "event_id": "ev1",
        "player_name": player,
        "team_nfl": "DET",
        "line": line,
        "price_over": over,
        "price_under": under,
        "season": 2026,
    }


class TestRegistries(unittest.TestCase):
    def test_every_market_has_cv(self):
        self.assertEqual(set(SEASON_MARKET_TO_STAT), set(SEASON_MARKET_CV))

    def test_core_markets_exist_in_registry(self):
        for pos, markets in SEASON_CORE_MARKETS_BY_POS.items():
            for market in markets:
                self.assertIn(market, SEASON_MARKET_TO_STAT, pos)

    def test_lambda_positions(self):
        self.assertEqual(set(SEASON_PROPS_BLEND_LAMBDAS), {"QB", "RB", "WR", "TE"})
        for lam in SEASON_PROPS_BLEND_LAMBDAS.values():
            self.assertGreaterEqual(lam, 0.0)
            self.assertLessEqual(lam, 1.0)


class TestComputeSeasonImplied(unittest.TestCase):
    def test_balanced_juice_implied_equals_line(self):
        props = pd.DataFrame(
            [
                _season_prop_row("David Montgomery", "season_rush_yds", 824.5),
                _season_prop_row("David Montgomery", "season_rush_tds", 8.5),
                _season_prop_row("David Montgomery", "season_receptions", 30.5),
            ]
        )
        implied = compute_season_prop_implied_points(props, "half_ppr")
        self.assertEqual(len(implied), 1)
        row = implied.iloc[0]
        # Balanced -110/-110 juice → implied mean == the line exactly.
        self.assertAlmostEqual(row["rushing_yards"], 824.5, places=1)
        self.assertAlmostEqual(row["rushing_tds"], 8.5, places=1)
        self.assertAlmostEqual(row["receptions"], 30.5, places=1)
        # half_ppr season points: 824.5*0.1 + 8.5*6 + 30.5*0.5 = 148.7
        self.assertAlmostEqual(row["prop_implied_points"], 148.7, places=1)

    def test_season_scale_qb(self):
        props = pd.DataFrame(
            [
                _season_prop_row("Matthew Stafford", "season_pass_yds", 3949.5),
                _season_prop_row("Matthew Stafford", "season_pass_tds", 26.5),
            ]
        )
        implied = compute_season_prop_implied_points(props, "half_ppr")
        row = implied.iloc[0]
        # 3949.5*0.04 + 26.5*4 = 264.0 — a season-total number, not weekly.
        self.assertAlmostEqual(row["prop_implied_points"], 264.0, places=1)

    def test_empty_frame(self):
        implied = compute_season_prop_implied_points(pd.DataFrame(), "ppr")
        self.assertTrue(implied.empty)


class TestSeasonBlend(unittest.TestCase):
    def _proj(self):
        return pd.DataFrame(
            [
                {
                    "player_name": "David Montgomery",
                    "position": "RB",
                    "projected_season_points": 200.0,
                },
                {
                    "player_name": "Deep Bench",
                    "position": "RB",
                    "projected_season_points": 40.0,
                },
            ]
        )

    def test_blend_moves_covered_player_only(self):
        props = pd.DataFrame(
            [
                _season_prop_row("David Montgomery", "season_rush_yds", 824.5),
            ]
        )
        implied = compute_season_prop_implied_points(props, "half_ppr")
        out = apply_season_props_blend(self._proj(), implied)

        covered = out[out["player_name"] == "David Montgomery"].iloc[0]
        uncovered = out[out["player_name"] == "Deep Bench"].iloc[0]

        lam = SEASON_PROPS_BLEND_LAMBDAS["RB"]
        expected = (1 - lam) * 200.0 + lam * covered["prop_implied_points"]
        self.assertAlmostEqual(
            covered["projected_season_points"], round(expected, 2), places=2
        )
        # Gap is model − market, computed pre-blend.
        self.assertAlmostEqual(
            covered["prop_anchor_gap"],
            round(200.0 - covered["prop_implied_points"], 2),
            places=2,
        )
        self.assertEqual(uncovered["projected_season_points"], 40.0)
        self.assertTrue(pd.isna(uncovered["prop_implied_points"]))

    def test_coverage_gate_blocks_partial_stat_line(self):
        # RB with ONLY a receptions future must not be blended — the
        # implied points would omit all rushing production.
        props = pd.DataFrame(
            [
                _season_prop_row("David Montgomery", "season_receptions", 30.5),
            ]
        )
        implied = compute_season_prop_implied_points(props, "half_ppr")
        out = apply_season_props_blend(self._proj(), implied)
        covered = out[out["player_name"] == "David Montgomery"].iloc[0]
        self.assertEqual(covered["projected_season_points"], 200.0)

    def test_empty_implied_is_noop(self):
        out = apply_season_props_blend(self._proj(), pd.DataFrame())
        self.assertEqual(list(out["projected_season_points"]), [200.0, 40.0])
        self.assertIn("prop_implied_points", out.columns)


if __name__ == "__main__":
    unittest.main()
