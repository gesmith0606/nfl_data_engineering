"""
Unit tests for season prop-implied projections (season futures → blend).
"""

import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from season_prop_implied import (  # noqa: E402
    MILESTONE_VIG_HAIRCUT,
    ROOKIE_TO_SEASON_MARKET,
    SEASON_CORE_MARKETS_BY_POS,
    SEASON_MARKET_CV,
    SEASON_MARKET_TO_STAT,
    SEASON_PROPS_BLEND_LAMBDAS,
    apply_season_props_blend,
    attach_market_columns,
    compute_rookie_milestone_implied,
    compute_season_prop_implied_points,
    invert_milestone_ladder,
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


def _milestone_row(player, market, threshold, price):
    row = _season_prop_row(player, market, threshold, over=price, under=None)
    return row


class TestMilestoneInversion(unittest.TestCase):
    def test_recovers_normal_mean_from_exact_ladder(self):
        # Build a ladder from a known Normal(900, 0.30*900) and check the
        # fit recovers the mean.
        from scipy.stats import norm as _norm

        mu, cv = 900.0, 0.30
        thresholds = [750.0, 1000.0, 1250.0, 1500.0]
        probs = [float(_norm.sf(t, loc=mu, scale=cv * mu)) for t in thresholds]
        fitted = invert_milestone_ladder(thresholds, probs, cv=cv)
        self.assertAlmostEqual(fitted, mu, delta=5.0)

    def test_recovers_poisson_mean_from_exact_ladder(self):
        from scipy.stats import poisson as _poisson

        lam = 7.0
        thresholds = [4.0, 6.0, 8.0, 10.0]
        probs = [float(_poisson.sf(t - 1, lam)) for t in thresholds]
        fitted = invert_milestone_ladder(thresholds, probs, cv=0.4, count=True)
        self.assertAlmostEqual(fitted, lam, delta=0.3)

    def test_unusable_rungs_return_none(self):
        self.assertIsNone(invert_milestone_ladder([], [], cv=0.3))
        self.assertIsNone(invert_milestone_ladder([750.0], [float("nan")], cv=0.3))

    def test_compute_rookie_milestone_implied(self):
        # Jeremiyah Love-style ladder: -210 / +200 / +700 / +2000.
        rows = [
            _milestone_row("Jeremiyah Love", "rookie_rush_yds", t, p)
            for t, p in [(750, -210), (1000, 200), (1250, 700), (1500, 2000)]
        ]
        out = compute_rookie_milestone_implied(pd.DataFrame(rows))
        self.assertEqual(len(out), 1)
        row = out.iloc[0]
        # Market key is mapped to the season equivalent.
        self.assertEqual(row["market"], "season_rush_yds")
        self.assertEqual(row["stat"], "rushing_yards")
        # ~63% fair at 750+, ~31% at 1000+ -> mean lands in the 800s.
        self.assertGreater(row["implied"], 700)
        self.assertLess(row["implied"], 1000)

    def test_vig_haircut_constant_sane(self):
        self.assertGreater(MILESTONE_VIG_HAIRCUT, 0.85)
        self.assertLessEqual(MILESTONE_VIG_HAIRCUT, 1.0)

    def test_rookie_market_map_targets_exist(self):
        for season_key in ROOKIE_TO_SEASON_MARKET.values():
            self.assertIn(season_key, SEASON_MARKET_TO_STAT)


class TestMilestoneMerge(unittest.TestCase):
    def test_rookie_only_player_added(self):
        props = pd.DataFrame(
            [_season_prop_row("David Montgomery", "season_rush_yds", 824.5)]
            + [
                _milestone_row("Jeremiyah Love", "rookie_rush_yds", t, p)
                for t, p in [(750, -210), (1000, 200), (1250, 700)]
            ]
        )
        implied = compute_season_prop_implied_points(props, "half_ppr")
        self.assertEqual(len(implied), 2)
        love = implied[implied["player_name"] == "Jeremiyah Love"].iloc[0]
        self.assertIn("season_rush_yds", love["prop_markets"])
        self.assertGreater(love["prop_implied_points"], 0)

    def test_ou_wins_stat_overlap(self):
        # Player priced by BOTH the O/U market (sharp) and a milestone
        # ladder (coarse): the O/U implied stat must win.
        props = pd.DataFrame(
            [_season_prop_row("Fernando Mendoza", "season_pass_yds", 1260.5)]
            + [
                _milestone_row("Fernando Mendoza", "rookie_pass_yds", t, p)
                for t, p in [(3000, 200), (3500, 350), (4000, 900)]
            ]
        )
        implied = compute_season_prop_implied_points(props, "half_ppr")
        self.assertEqual(len(implied), 1)
        row = implied.iloc[0]
        # Balanced -110/-110 juice on the O/U -> implied == line, NOT the
        # milestone fit (which would land near 3000).
        self.assertAlmostEqual(row["passing_yards"], 1260.5, places=1)
        # Markets set is the union of both sources' keys.
        self.assertIn("season_pass_yds", row["prop_markets"])

    def test_rookie_blend_coverage_gate_passes(self):
        # A rookie priced only via milestones must still blend (mapped
        # market key satisfies the RB core gate).
        props = pd.DataFrame(
            [
                _milestone_row("Jeremiyah Love", "rookie_rush_yds", t, p)
                for t, p in [(750, -210), (1000, 200), (1250, 700)]
            ]
        )
        implied = compute_season_prop_implied_points(props, "half_ppr")
        proj = pd.DataFrame(
            [
                {
                    "player_name": "Jeremiyah Love",
                    "position": "RB",
                    "projected_season_points": 150.0,
                }
            ]
        )
        out = apply_season_props_blend(proj, implied)
        self.assertNotEqual(out.iloc[0]["projected_season_points"], 150.0)


class TestAttachMarketColumns(unittest.TestCase):
    def test_no_snapshot_returns_unchanged_with_nan_columns(self):
        import tempfile

        proj = pd.DataFrame(
            [
                {
                    "player_name": "David Montgomery",
                    "position": "RB",
                    "projected_season_points": 200.0,
                }
            ]
        )
        with tempfile.TemporaryDirectory() as empty_root:
            out, matched = attach_market_columns(
                proj, season=2026, project_root=empty_root
            )
        self.assertEqual(matched, 0)
        self.assertEqual(out.iloc[0]["projected_season_points"], 200.0)
        self.assertTrue(pd.isna(out.iloc[0]["prop_implied_points"]))

    def test_attach_from_snapshot_without_blending(self):
        import os
        import tempfile

        props = pd.DataFrame(
            [_season_prop_row("David Montgomery", "season_rush_yds", 824.5)]
        )
        proj = pd.DataFrame(
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
        with tempfile.TemporaryDirectory() as root:
            snap_dir = os.path.join(
                root, "data", "bronze", "dk", "season_props", "season=2026"
            )
            os.makedirs(snap_dir)
            props.to_parquet(
                os.path.join(snap_dir, "season_props_20260802_120000.parquet"),
                index=False,
            )
            out, matched = attach_market_columns(proj, season=2026, project_root=root)
        self.assertEqual(matched, 1)
        covered = out[out["player_name"] == "David Montgomery"].iloc[0]
        # Projections untouched; only provenance columns added.
        self.assertEqual(covered["projected_season_points"], 200.0)
        self.assertGreater(covered["prop_implied_points"], 0)
        self.assertAlmostEqual(
            covered["prop_anchor_gap"],
            round(200.0 - covered["prop_implied_points"], 2),
            places=2,
        )


if __name__ == "__main__":
    unittest.main()
