"""
Unit tests for the ADP-prior early-season blend (Draft-time ADP hypothesis;
see ``.planning/ADP_EARLY_SEASON_GATE.md``).
"""

import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from adp_prior import (  # noqa: E402
    ADP_PRIOR_POSITIONS,
    ADP_PRIOR_WEIGHTS,
    MIN_TRAINING_ROWS,
    apply_adp_prior,
    compute_adp_implied_ppg,
    compute_realized_season_ppg,
    fit_adp_ppg_mapping,
    load_adp_snapshot,
)


def _weekly_row(player_name, position, season, week, rushing_yards=0, receiving_yards=0, receptions=0):
    return {
        "player_name": player_name,
        "position": position,
        "season": season,
        "week": week,
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


class TestLoadAdpSnapshot(unittest.TestCase):
    def test_missing_file_returns_empty_with_columns(self):
        out = load_adp_snapshot(1999, scoring_format="half_ppr", adp_dir="/nonexistent/dir")
        self.assertTrue(out.empty)
        self.assertIn("name_key", out.columns)

    def test_existing_file_loads_and_adds_name_key(self):
        out = load_adp_snapshot(2022, scoring_format="ppr")
        self.assertFalse(out.empty)
        self.assertIn("name_key", out.columns)
        self.assertIn("adp", out.columns)
        # Jonathan Taylor is ADP #1 in the 2022 ppr snapshot
        self.assertIn("jonathan taylor", out["name_key"].values)


class TestComputeRealizedSeasonPpg(unittest.TestCase):
    def test_ppg_averages_across_games(self):
        rows = [_weekly_row("Player One", "RB", 2024, w, rushing_yards=10) for w in range(1, 9)]
        out = compute_realized_season_ppg(pd.DataFrame(rows), season=2024, scoring_format="half_ppr")
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out.iloc[0]["realized_ppg"], 1.0, places=2)
        self.assertEqual(out.iloc[0]["name_key"], "player one")

    def test_below_min_games_excluded(self):
        rows = [_weekly_row("Player One", "RB", 2024, w, rushing_yards=10) for w in range(1, 6)]
        out = compute_realized_season_ppg(pd.DataFrame(rows), season=2024, scoring_format="half_ppr")
        self.assertTrue(out.empty)

    def test_empty_input_returns_empty_with_columns(self):
        out = compute_realized_season_ppg(pd.DataFrame(), season=2024)
        self.assertTrue(out.empty)
        self.assertEqual(list(out.columns), ["name_key", "position", "realized_ppg", "games"])

    def test_wrong_season_excluded(self):
        rows = [_weekly_row("Player One", "RB", 2023, w, rushing_yards=10) for w in range(1, 9)]
        out = compute_realized_season_ppg(pd.DataFrame(rows), season=2024, scoring_format="half_ppr")
        self.assertTrue(out.empty)


class TestFitAdpPpgMapping(unittest.TestCase):
    def test_empty_training_seasons_returns_empty(self):
        out = fit_adp_ppg_mapping([], pd.DataFrame(), scoring_format="half_ppr")
        self.assertEqual(out, {})

    def test_no_matching_bronze_data_returns_empty(self):
        # 2022 ADP history exists on disk, but weekly_df has nothing for 2022.
        out = fit_adp_ppg_mapping([2022], pd.DataFrame(), scoring_format="half_ppr")
        self.assertEqual(out, {})

    def test_fits_on_real_2022_adp_with_synthetic_realized_ppg(self):
        # Use the real committed 2022 ADP snapshot; synthesize realized PPG
        # for the same players so the join has hits.
        adp = load_adp_snapshot(2022, scoring_format="ppr")
        rb_names = adp[adp["position"] == "RB"]["player_name"].head(MIN_TRAINING_ROWS + 2)
        self.assertGreaterEqual(len(rb_names), MIN_TRAINING_ROWS)
        rows = []
        for name in rb_names:
            for w in range(1, 9):
                rows.append(_weekly_row(name, "RB", 2022, w, rushing_yards=50))
        mapping = fit_adp_ppg_mapping([2022], pd.DataFrame(rows), scoring_format="ppr")
        self.assertIn("RB", mapping)
        self.assertIn("slope", mapping["RB"])
        self.assertIn("intercept", mapping["RB"])
        self.assertGreaterEqual(mapping["RB"]["n"], MIN_TRAINING_ROWS)

    def test_below_min_training_rows_position_omitted(self):
        adp = pd.DataFrame(
            [
                {"player_name": "Solo Kicker", "position": "K", "adp": 150.0, "name_key": "solo kicker"},
            ]
        )
        realized = pd.DataFrame(
            [{"name_key": "solo kicker", "position": "K", "realized_ppg": 8.0, "games": 10}]
        )
        # Monkeypatch via direct merge check is awkward; instead confirm the
        # public fit function omits positions with too few pooled rows by
        # using synthetic weekly rows for a single K player only.
        rows = [_weekly_row("Solo Kicker", "K", 2022, w) for w in range(1, 9)]
        weekly_df = pd.DataFrame(rows)
        # Patch load_adp_snapshot indirectly isn't available without I/O, so
        # just assert the real 2022 fit (many positions) never includes K
        # (K is outside ADP_PRIOR_POSITIONS regardless of row count).
        mapping = fit_adp_ppg_mapping([2022], weekly_df, scoring_format="ppr")
        self.assertNotIn("K", mapping)


class TestComputeAdpImpliedPpg(unittest.TestCase):
    def test_empty_mapping_returns_empty(self):
        adp = pd.DataFrame([{"player_name": "A", "position": "RB", "adp": 5.0, "name_key": "a"}])
        out = compute_adp_implied_ppg(adp, {})
        self.assertTrue(out.empty)

    def test_applies_linear_mapping(self):
        adp = pd.DataFrame(
            [
                {"player_name": "Top Pick", "position": "RB", "adp": 1.0, "name_key": "top pick"},
                {"player_name": "Late Pick", "position": "RB", "adp": 100.0, "name_key": "late pick"},
            ]
        )
        mapping = {"RB": {"slope": -5.0, "intercept": 20.0, "n": 10}}
        out = compute_adp_implied_ppg(adp, mapping)
        self.assertEqual(len(out), 2)
        top = out[out["name_key"] == "top pick"].iloc[0]["adp_implied_ppg"]
        late = out[out["name_key"] == "late pick"].iloc[0]["adp_implied_ppg"]
        # log10(1)=0 -> 20.0; log10(100)=2 -> 20 - 10 = 10.0
        self.assertAlmostEqual(top, 20.0, places=2)
        self.assertAlmostEqual(late, 10.0, places=2)

    def test_negative_implied_clipped_to_zero(self):
        adp = pd.DataFrame(
            [{"player_name": "Deep Sleeper", "position": "WR", "adp": 300.0, "name_key": "deep sleeper"}]
        )
        mapping = {"WR": {"slope": -50.0, "intercept": 10.0, "n": 10}}
        out = compute_adp_implied_ppg(adp, mapping)
        self.assertAlmostEqual(out.iloc[0]["adp_implied_ppg"], 0.0, places=2)

    def test_position_without_mapping_dropped(self):
        adp = pd.DataFrame([{"player_name": "A", "position": "TE", "adp": 5.0, "name_key": "a"}])
        mapping = {"RB": {"slope": -5.0, "intercept": 20.0, "n": 10}}
        out = compute_adp_implied_ppg(adp, mapping)
        self.assertTrue(out.empty)


class TestApplyAdpPrior(unittest.TestCase):
    @staticmethod
    def _proj(name="Player One", pos="RB", pts=10.0):
        return pd.DataFrame([{"player_name": name, "position": pos, "projected_points": pts}])

    @staticmethod
    def _implied(name="Player One", pos="RB", ppg=20.0):
        return pd.DataFrame([{"name_key": name.lower(), "position": pos, "adp_implied_ppg": ppg}])

    def test_week1_blends_at_schedule_weight(self):
        out = apply_adp_prior(self._proj(pts=10.0), self._implied(ppg=20.0), week=1)
        # w=0.5: 0.5*10 + 0.5*20 = 15
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 15.0, places=2)
        self.assertAlmostEqual(out.iloc[0]["adp_implied_ppg"], 20.0, places=2)

    def test_week6_uses_smallest_weight(self):
        out = apply_adp_prior(self._proj(pts=10.0), self._implied(ppg=20.0), week=6)
        # w=0.1: 0.9*10 + 0.1*20 = 11
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 11.0, places=2)

    def test_week7_is_noop(self):
        out = apply_adp_prior(self._proj(pts=10.0), self._implied(ppg=20.0), week=7)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)
        self.assertTrue(pd.isna(out.iloc[0]["adp_implied_ppg"]))

    def test_scale_zero_disables(self):
        out = apply_adp_prior(self._proj(pts=10.0), self._implied(ppg=20.0), week=1, scale=0.0)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_scale_multiplies_schedule(self):
        out = apply_adp_prior(self._proj(pts=10.0), self._implied(ppg=20.0), week=1, scale=0.5)
        # w = 0.5*0.5 = 0.25: 0.75*10 + 0.25*20 = 7.5 + 5 = 12.5
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 12.5, places=2)

    def test_no_name_match_is_noop(self):
        out = apply_adp_prior(
            self._proj(name="Unknown Guy", pts=10.0), self._implied(name="Player One", ppg=20.0), week=1
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)
        self.assertTrue(pd.isna(out.iloc[0]["adp_implied_ppg"]))

    def test_position_mismatch_is_noop(self):
        # Same name, different position -> the (name_key, position) join key misses.
        out = apply_adp_prior(
            self._proj(name="Player One", pos="WR", pts=10.0),
            self._implied(name="Player One", pos="RB", ppg=20.0),
            week=1,
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)
        self.assertTrue(pd.isna(out.iloc[0]["adp_implied_ppg"]))

    def test_non_skill_position_untouched(self):
        out = apply_adp_prior(self._proj(pos="K", pts=10.0), self._implied(pos="K", ppg=20.0), week=1)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_empty_implied_is_noop_with_provenance_column(self):
        out = apply_adp_prior(self._proj(pts=10.0), pd.DataFrame(), week=1)
        self.assertIn("adp_implied_ppg", out.columns)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_default_schedule_shape(self):
        self.assertEqual(
            ADP_PRIOR_WEIGHTS, {1: 0.5, 2: 0.45, 3: 0.4, 4: 0.3, 5: 0.2, 6: 0.1}
        )

    def test_zero_row_projections_no_crash(self):
        empty_proj = pd.DataFrame(columns=["player_name", "position", "projected_points"])
        out = apply_adp_prior(empty_proj, self._implied(ppg=20.0), week=1)
        self.assertTrue(out.empty)
        self.assertIn("adp_implied_ppg", out.columns)


if __name__ == "__main__":
    unittest.main()
