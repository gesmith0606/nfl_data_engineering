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
    build_name_id_crosswalk,
    compute_adp_implied_ppg,
    compute_realized_season_ppg,
    fit_adp_ppg_mapping,
    load_adp_snapshot,
    resolve_adp_player_ids,
)


def _weekly_row(player_id, position, season, week, rushing_yards=0, receiving_yards=0, receptions=0):
    return {
        "player_id": player_id,
        "player_name": "Abbrev.Name",  # deliberately NOT matchable by name — proves the join is by id
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


def _roster_row(player_id, player_name, position):
    return {"player_id": player_id, "player_name": player_name, "position": position}


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


class TestBuildNameIdCrosswalk(unittest.TestCase):
    def test_builds_from_rosters(self):
        rosters = pd.DataFrame(
            [
                _roster_row("P1", "Jonathan Taylor", "RB"),
                _roster_row("P2", "Marvin Harrison Jr.", "WR"),
            ]
        )
        cw = build_name_id_crosswalk(rosters)
        self.assertEqual(len(cw), 2)
        self.assertIn(("jonathan taylor", "RB"), set(zip(cw["name_key"], cw["position"])))
        # suffix-stripping matches early_season_prior/normalize_name convention
        self.assertIn(("marvin harrison", "WR"), set(zip(cw["name_key"], cw["position"])))

    def test_empty_rosters_returns_empty_with_columns(self):
        out = build_name_id_crosswalk(pd.DataFrame())
        self.assertTrue(out.empty)
        self.assertEqual(list(out.columns), ["name_key", "position", "player_id"])

    def test_missing_columns_returns_empty(self):
        out = build_name_id_crosswalk(pd.DataFrame([{"foo": 1}]))
        self.assertTrue(out.empty)


class TestResolveAdpPlayerIds(unittest.TestCase):
    def test_resolves_via_crosswalk(self):
        adp = load_adp_snapshot(2022, scoring_format="ppr")
        crosswalk = pd.DataFrame(
            [{"name_key": "jonathan taylor", "position": "RB", "player_id": "00-0036223"}]
        )
        resolved = resolve_adp_player_ids(adp, crosswalk)
        self.assertEqual(len(resolved), 1)
        self.assertEqual(resolved.iloc[0]["player_id"], "00-0036223")

    def test_empty_crosswalk_returns_empty(self):
        adp = load_adp_snapshot(2022, scoring_format="ppr")
        out = resolve_adp_player_ids(adp, pd.DataFrame())
        self.assertTrue(out.empty)

    def test_no_match_drops_row(self):
        adp = pd.DataFrame([{"player_name": "Nobody Here", "position": "RB", "adp": 50.0, "name_key": "nobody here"}])
        crosswalk = pd.DataFrame([{"name_key": "somebody else", "position": "RB", "player_id": "X1"}])
        out = resolve_adp_player_ids(adp, crosswalk)
        self.assertTrue(out.empty)


class TestComputeRealizedSeasonPpg(unittest.TestCase):
    def test_ppg_averages_across_games(self):
        rows = [_weekly_row("P1", "RB", 2024, w, rushing_yards=10) for w in range(1, 9)]
        out = compute_realized_season_ppg(pd.DataFrame(rows), season=2024, scoring_format="half_ppr")
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out.iloc[0]["realized_ppg"], 1.0, places=2)
        self.assertEqual(out.iloc[0]["player_id"], "P1")

    def test_below_min_games_excluded(self):
        rows = [_weekly_row("P1", "RB", 2024, w, rushing_yards=10) for w in range(1, 6)]
        out = compute_realized_season_ppg(pd.DataFrame(rows), season=2024, scoring_format="half_ppr")
        self.assertTrue(out.empty)

    def test_empty_input_returns_empty_with_columns(self):
        out = compute_realized_season_ppg(pd.DataFrame(), season=2024)
        self.assertTrue(out.empty)
        self.assertEqual(list(out.columns), ["player_id", "position", "realized_ppg", "games"])

    def test_wrong_season_excluded(self):
        rows = [_weekly_row("P1", "RB", 2023, w, rushing_yards=10) for w in range(1, 9)]
        out = compute_realized_season_ppg(pd.DataFrame(rows), season=2024, scoring_format="half_ppr")
        self.assertTrue(out.empty)


class TestFitAdpPpgMapping(unittest.TestCase):
    def test_empty_training_seasons_returns_empty(self):
        out = fit_adp_ppg_mapping([], pd.DataFrame(), pd.DataFrame(), scoring_format="half_ppr")
        self.assertEqual(out, {})

    def test_no_matching_bronze_data_returns_empty(self):
        adp = load_adp_snapshot(2022, scoring_format="half_ppr")
        crosswalk = build_name_id_crosswalk(
            pd.DataFrame([_roster_row(pid, name, "RB") for pid, name in zip(["X1"], ["Jonathan Taylor"])])
        )
        # crosswalk resolves ADP names fine, but weekly_df has no rows -> no realized labels
        out = fit_adp_ppg_mapping([2022], pd.DataFrame(), crosswalk, scoring_format="half_ppr")
        self.assertEqual(out, {})

    def test_fits_on_real_2022_adp_with_synthetic_realized_ppg(self):
        # Use the real committed 2022 ADP snapshot; synthesize a crosswalk +
        # realized PPG for the same players so the joins have hits.
        adp = load_adp_snapshot(2022, scoring_format="ppr")
        rb_rows = adp[adp["position"] == "RB"].head(MIN_TRAINING_ROWS + 2)
        self.assertGreaterEqual(len(rb_rows), MIN_TRAINING_ROWS)

        roster_rows = [
            _roster_row(f"ID{i}", name, "RB") for i, name in enumerate(rb_rows["player_name"])
        ]
        crosswalk = build_name_id_crosswalk(pd.DataFrame(roster_rows))

        weekly_rows = []
        for i in range(len(rb_rows)):
            for w in range(1, 9):
                weekly_rows.append(_weekly_row(f"ID{i}", "RB", 2022, w, rushing_yards=50))

        mapping = fit_adp_ppg_mapping([2022], pd.DataFrame(weekly_rows), crosswalk, scoring_format="ppr")
        self.assertIn("RB", mapping)
        self.assertIn("slope", mapping["RB"])
        self.assertIn("intercept", mapping["RB"])
        self.assertGreaterEqual(mapping["RB"]["n"], MIN_TRAINING_ROWS)

    def test_non_skill_position_never_fit(self):
        adp = load_adp_snapshot(2022, scoring_format="ppr")
        k_rows = adp[adp["position"] == "K"]
        if k_rows.empty:
            self.skipTest("no K rows in fixture ADP file")
        roster_rows = [_roster_row(f"K{i}", name, "K") for i, name in enumerate(k_rows["player_name"])]
        crosswalk = build_name_id_crosswalk(pd.DataFrame(roster_rows))
        weekly_rows = [_weekly_row(f"K{i}", "K", 2022, w) for i in range(len(k_rows)) for w in range(1, 9)]
        mapping = fit_adp_ppg_mapping([2022], pd.DataFrame(weekly_rows), crosswalk, scoring_format="ppr")
        self.assertNotIn("K", mapping)


class TestComputeAdpImpliedPpg(unittest.TestCase):
    def test_empty_mapping_returns_empty(self):
        adp = pd.DataFrame([{"player_name": "A", "position": "RB", "adp": 5.0, "name_key": "a"}])
        crosswalk = pd.DataFrame([{"name_key": "a", "position": "RB", "player_id": "P1"}])
        out = compute_adp_implied_ppg(adp, {}, crosswalk)
        self.assertTrue(out.empty)

    def test_applies_linear_mapping(self):
        adp = pd.DataFrame(
            [
                {"player_name": "Top Pick", "position": "RB", "adp": 1.0, "name_key": "top pick"},
                {"player_name": "Late Pick", "position": "RB", "adp": 100.0, "name_key": "late pick"},
            ]
        )
        crosswalk = pd.DataFrame(
            [
                {"name_key": "top pick", "position": "RB", "player_id": "P1"},
                {"name_key": "late pick", "position": "RB", "player_id": "P2"},
            ]
        )
        mapping = {"RB": {"slope": -5.0, "intercept": 20.0, "n": 10}}
        out = compute_adp_implied_ppg(adp, mapping, crosswalk)
        self.assertEqual(len(out), 2)
        top = out[out["player_id"] == "P1"].iloc[0]["adp_implied_ppg"]
        late = out[out["player_id"] == "P2"].iloc[0]["adp_implied_ppg"]
        # log10(1)=0 -> 20.0; log10(100)=2 -> 20 - 10 = 10.0
        self.assertAlmostEqual(top, 20.0, places=2)
        self.assertAlmostEqual(late, 10.0, places=2)

    def test_negative_implied_clipped_to_zero(self):
        adp = pd.DataFrame([{"player_name": "Deep Sleeper", "position": "WR", "adp": 300.0, "name_key": "deep sleeper"}])
        crosswalk = pd.DataFrame([{"name_key": "deep sleeper", "position": "WR", "player_id": "P1"}])
        mapping = {"WR": {"slope": -50.0, "intercept": 10.0, "n": 10}}
        out = compute_adp_implied_ppg(adp, mapping, crosswalk)
        self.assertAlmostEqual(out.iloc[0]["adp_implied_ppg"], 0.0, places=2)

    def test_position_without_mapping_dropped(self):
        adp = pd.DataFrame([{"player_name": "A", "position": "TE", "adp": 5.0, "name_key": "a"}])
        crosswalk = pd.DataFrame([{"name_key": "a", "position": "TE", "player_id": "P1"}])
        mapping = {"RB": {"slope": -5.0, "intercept": 20.0, "n": 10}}
        out = compute_adp_implied_ppg(adp, mapping, crosswalk)
        self.assertTrue(out.empty)

    def test_unresolved_name_dropped(self):
        adp = pd.DataFrame([{"player_name": "Ghost Player", "position": "RB", "adp": 5.0, "name_key": "ghost player"}])
        mapping = {"RB": {"slope": -5.0, "intercept": 20.0, "n": 10}}
        out = compute_adp_implied_ppg(adp, mapping, pd.DataFrame())
        self.assertTrue(out.empty)


class TestApplyAdpPrior(unittest.TestCase):
    @staticmethod
    def _proj(pid="P1", pos="RB", pts=10.0):
        return pd.DataFrame([{"player_id": pid, "position": pos, "projected_points": pts}])

    @staticmethod
    def _implied(pid="P1", pos="RB", ppg=20.0):
        return pd.DataFrame([{"player_id": pid, "position": pos, "adp_implied_ppg": ppg}])

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

    def test_no_id_match_is_noop(self):
        out = apply_adp_prior(self._proj(pid="UNKNOWN", pts=10.0), self._implied(pid="P1", ppg=20.0), week=1)
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
        empty_proj = pd.DataFrame(columns=["player_id", "position", "projected_points"])
        out = apply_adp_prior(empty_proj, self._implied(ppg=20.0), week=1)
        self.assertTrue(out.empty)
        self.assertIn("adp_implied_ppg", out.columns)

    def test_missing_player_id_column_is_noop(self):
        proj = pd.DataFrame([{"position": "RB", "projected_points": 10.0}])
        out = apply_adp_prior(proj, self._implied(ppg=20.0), week=1)
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)


if __name__ == "__main__":
    unittest.main()
