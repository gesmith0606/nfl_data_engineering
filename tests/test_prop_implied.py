"""
Unit tests for prop-implied projections (.planning/PROP_IMPLIED_DECISION.md).
"""

import math
import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from prop_implied import (  # noqa: E402
    PROPS_BLEND_LAMBDAS,
    american_to_prob,
    apply_props_blend,
    compute_prop_implied_points,
    devig_two_way,
    implied_mean_from_line,
    implied_td_mean,
)


def _prop_row(
    player, market, line, over, under, book="fanduel", ts="2026-09-13T12:00:00Z"
):
    return {
        "snapshot_ts": ts,
        "event_id": "ev1",
        "commence_time": "2026-09-13T17:00:00Z",
        "home_team": "Chiefs",
        "away_team": "Bills",
        "home_team_nfl": "KC",
        "away_team_nfl": "BUF",
        "bookmaker": book,
        "market": market,
        "player_name": player,
        "line": line,
        "price_over": over,
        "price_under": under,
        "season": 2026,
    }


class TestOddsMath(unittest.TestCase):
    def test_american_to_prob(self):
        self.assertAlmostEqual(american_to_prob(-110), 110 / 210, places=6)
        self.assertAlmostEqual(american_to_prob(+150), 100 / 250, places=6)
        self.assertTrue(math.isnan(american_to_prob(None)))
        self.assertTrue(math.isnan(american_to_prob(0)))

    def test_devig_balanced_juice_is_half(self):
        self.assertAlmostEqual(devig_two_way(-110, -110), 0.5, places=6)

    def test_devig_shaded_over(self):
        # Over -130 / Under +100 -> fair P(over) > 0.5
        self.assertGreater(devig_two_way(-130, 100), 0.5)

    def test_devig_one_sided_is_nan(self):
        self.assertTrue(math.isnan(devig_two_way(-110, None)))

    def test_implied_mean_balanced_juice_equals_line(self):
        self.assertAlmostEqual(
            implied_mean_from_line(62.5, 0.5, cv=0.55), 62.5, places=6
        )

    def test_implied_mean_over_shading_raises_mean(self):
        base = implied_mean_from_line(62.5, 0.5, cv=0.55)
        shaded = implied_mean_from_line(62.5, 0.55, cv=0.55)
        self.assertGreater(shaded, base)

    def test_implied_td_mean_poisson(self):
        # P(>=1 TD) = 1 - e^-lambda; p=0.3934 -> lambda ~ 0.5
        self.assertAlmostEqual(implied_td_mean(1 - math.exp(-0.5)), 0.5, places=6)
        self.assertTrue(math.isnan(implied_td_mean(float("nan"))))


class TestComputePropImpliedPoints(unittest.TestCase):
    def test_balanced_rb_props_score_expected_points(self):
        props = pd.DataFrame(
            [
                _prop_row("Jonathan Taylor", "player_rush_yds", 85.5, -110, -110),
                _prop_row("Jonathan Taylor", "player_receptions", 2.5, -110, -110),
                _prop_row("Jonathan Taylor", "player_reception_yds", 18.5, -110, -110),
            ]
        )
        out = compute_prop_implied_points(props, scoring_format="half_ppr")
        self.assertEqual(len(out), 1)
        row = out.iloc[0]
        # 85.5*0.1 + 18.5*0.1 + 2.5*0.5 = 8.55 + 1.85 + 1.25 = 11.65
        self.assertAlmostEqual(row["prop_implied_points"], 11.65, places=2)
        self.assertEqual(row["prop_market_count"], 3)

    def test_median_across_books(self):
        props = pd.DataFrame(
            [
                _prop_row(
                    "A Back", "player_rush_yds", 80.5, -110, -110, book="fanduel"
                ),
                _prop_row("A Back", "player_rush_yds", 84.5, -110, -110, book="dk"),
                _prop_row("A Back", "player_rush_yds", 88.5, -110, -110, book="mgm"),
            ]
        )
        out = compute_prop_implied_points(props)
        # median of the three balanced lines
        self.assertAlmostEqual(out.iloc[0]["rushing_yards"], 84.5, places=2)

    def test_latest_snapshot_wins_per_book(self):
        props = pd.DataFrame(
            [
                _prop_row(
                    "A Back",
                    "player_rush_yds",
                    70.5,
                    -110,
                    -110,
                    ts="2026-09-13T08:00:00Z",
                ),
                _prop_row(
                    "A Back",
                    "player_rush_yds",
                    90.5,
                    -110,
                    -110,
                    ts="2026-09-13T12:00:00Z",
                ),
            ]
        )
        out = compute_prop_implied_points(props)
        self.assertAlmostEqual(out.iloc[0]["rushing_yards"], 90.5, places=2)

    def test_anytime_td_contributes_six_points_per_expected_td(self):
        p_yes = 1 - math.exp(-0.5)  # lambda = 0.5
        # invert the 7% vig haircut so the fair prob lands on p_yes
        vigged_prob = p_yes / 0.93
        odds = -100 * vigged_prob / (1 - vigged_prob)  # negative american
        props = pd.DataFrame(
            [
                _prop_row("A Back", "player_anytime_td", None, round(odds), None),
            ]
        )
        out = compute_prop_implied_points(props)
        self.assertAlmostEqual(out.iloc[0]["prop_implied_points"], 3.0, places=1)

    def test_empty_and_missing_columns_return_empty(self):
        self.assertTrue(compute_prop_implied_points(pd.DataFrame()).empty)
        self.assertTrue(compute_prop_implied_points(pd.DataFrame([{"foo": 1}])).empty)


class TestApplyPropsBlend(unittest.TestCase):
    @staticmethod
    def _implied(name="Jonathan Taylor", pts=15.0, markets=None):
        return pd.DataFrame(
            [
                {
                    "name_key": (
                        "jonathan taylor" if name == "Jonathan Taylor" else name.lower()
                    ),
                    "player_name": name,
                    "prop_markets": (
                        markets if markets is not None else {"player_rush_yds"}
                    ),
                    "prop_market_count": 1,
                    "prop_implied_points": pts,
                }
            ]
        )

    @staticmethod
    def _proj(name="Jonathan Taylor", pos="RB", pts=19.0):
        return pd.DataFrame(
            [
                {
                    "player_name": name,
                    "position": pos,
                    "projected_points": pts,
                }
            ]
        )

    def test_rb_blend_and_anchor_gap(self):
        out = apply_props_blend(
            self._proj(pts=19.0), self._implied(pts=15.0), lambdas={"RB": 0.5}
        )
        row = out.iloc[0]
        self.assertAlmostEqual(row["projected_points"], 17.0, places=2)
        # anchor gap computed pre-blend: 19 - 15
        self.assertAlmostEqual(row["prop_anchor_gap"], 4.0, places=2)
        self.assertAlmostEqual(row["prop_implied_points"], 15.0, places=2)

    def test_position_without_lambda_untouched(self):
        out = apply_props_blend(
            self._proj(pos="TE", pts=19.0),
            self._implied(pts=15.0),
            lambdas={"RB": 0.5},
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 19.0, places=2)
        # provenance still recorded even when not blended
        self.assertAlmostEqual(out.iloc[0]["prop_implied_points"], 15.0, places=2)

    def test_missing_core_market_blocks_blend(self):
        implied = self._implied(pts=15.0, markets={"player_receptions"})
        out = apply_props_blend(self._proj(pts=19.0), implied, lambdas={"RB": 0.5})
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 19.0, places=2)

    def test_player_without_props_untouched(self):
        out = apply_props_blend(
            self._proj(name="Deep Bench", pts=6.0),
            self._implied(name="Jonathan Taylor", pts=15.0),
            lambdas={"RB": 1.0},
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 6.0, places=2)
        self.assertTrue(pd.isna(out.iloc[0]["prop_implied_points"]))

    def test_empty_implied_is_noop_with_provenance_columns(self):
        out = apply_props_blend(self._proj(), pd.DataFrame(), lambdas={"RB": 0.5})
        self.assertIn("prop_implied_points", out.columns)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 19.0, places=2)

    def test_default_lambdas_are_pre_gate_provisional(self):
        # QB/TE must stay 0 until the pre-registered gate shows no regression
        self.assertEqual(PROPS_BLEND_LAMBDAS["QB"], 0.0)
        self.assertEqual(PROPS_BLEND_LAMBDAS["TE"], 0.0)
        self.assertGreater(PROPS_BLEND_LAMBDAS["RB"], 0.0)


if __name__ == "__main__":
    unittest.main()
