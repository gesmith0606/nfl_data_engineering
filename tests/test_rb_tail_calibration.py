"""
Unit tests for the RB magnitude-tail calibration (lever #2 from
.planning/CONSENSUS_ERROR_DECOMPOSITION.md finding #2/#4).
"""

import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from rb_tail_calibration import (  # noqa: E402
    HIGH_BAND_MIN,
    HIGH_SHRINK_FACTOR,
    LOW_BAND_MAX,
    LOW_BAND_WEIGHT,
    RISE_THRESHOLD,
    apply_rb_tail_calibration,
    compute_rb_rising_ids,
    compute_rb_trailing_opportunity_ppg,
)


def _snap_row(team, player, season, week, offense_pct):
    return {
        "season": season,
        "week": float(week),
        "team": team,
        "player": player,
        "position": "RB",
        "offense_pct": offense_pct,
    }


def _weekly_row(
    player_id, week, rushing_yards=0.0, position="RB", season=2024,
    player_name="Zack Moss", team="IND",
):
    return {
        "player_id": player_id,
        "player_name": player_name,
        "recent_team": team,
        "season": season,
        "week": week,
        "position": position,
        "rushing_yards": rushing_yards,
    }


def _rising_snaps(team="IND", player="Zack Moss", season=2024):
    # recent window (weeks 3,4) high, prior window (weeks 1,2) low -> slope
    # 0.575 - 0.10 = 0.475, well above RISE_THRESHOLD (0.15). A week=5 row
    # is included so a signal row exists AT week=5 (compute_snap_trend_signals
    # only emits a row for weeks present in the input; the week-5 offense_pct
    # value itself is never used in the slope, which only reads weeks < 5 --
    # same lag contract as projection_engine._apply_rb_snap_collapse).
    return pd.DataFrame(
        [
            _snap_row(team, player, season, 1, 0.10),
            _snap_row(team, player, season, 2, 0.10),
            _snap_row(team, player, season, 3, 0.55),
            _snap_row(team, player, season, 4, 0.60),
            _snap_row(team, player, season, 5, 0.60),
        ]
    )


def _flat_snaps(team="IND", player="Zack Moss", season=2024):
    return pd.DataFrame(
        [_snap_row(team, player, season, w, 0.30) for w in range(1, 6)]
    )


def _id_map_weekly(player_id="P1", player_name="Zack Moss", team="IND", season=2024):
    # A single week=1 row is enough for the display-name -> player_id map
    # (_cached_rb_name_map only needs one row per player/team/season). Week
    # 1 sits outside the default trailing-opportunity window (weeks 3,4 for
    # a week=5 projection), so it never pollutes trailing-PPG tests.
    return pd.DataFrame(
        [_weekly_row(player_id, 1, player_name=player_name, team=team, season=season)]
    )


class TestComputeRbTrailingOpportunityPpg(unittest.TestCase):
    def test_averages_trailing_window_strictly_prior(self):
        rows = [
            _weekly_row("P1", 3, rushing_yards=80.0),  # 8.0 pts half-ppr
            _weekly_row("P1", 4, rushing_yards=60.0),  # 6.0 pts
            _weekly_row("P1", 5, rushing_yards=999.0),  # must NOT leak (week==5)
        ]
        out = compute_rb_trailing_opportunity_ppg(
            pd.DataFrame(rows), season=2024, week=5, scoring_format="half_ppr"
        )
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out.iloc[0]["trailing_opp_ppg"], 7.0, places=2)
        self.assertEqual(out.iloc[0]["trailing_opp_games"], 2)

    def test_window_defaults_to_2_weeks(self):
        rows = [
            _weekly_row("P1", 1, rushing_yards=100.0),  # outside default window=2
            _weekly_row("P1", 3, rushing_yards=80.0),
            _weekly_row("P1", 4, rushing_yards=60.0),
        ]
        out = compute_rb_trailing_opportunity_ppg(
            pd.DataFrame(rows), season=2024, week=5, scoring_format="half_ppr"
        )
        self.assertAlmostEqual(out.iloc[0]["trailing_opp_ppg"], 7.0, places=2)
        self.assertEqual(out.iloc[0]["trailing_opp_games"], 2)

    def test_ignores_other_seasons(self):
        rows = [_weekly_row("P1", 4, rushing_yards=100.0, season=2023)]
        out = compute_rb_trailing_opportunity_ppg(
            pd.DataFrame(rows), season=2024, week=5
        )
        self.assertTrue(out.empty)

    def test_ignores_non_rb(self):
        rows = [_weekly_row("P1", 4, rushing_yards=100.0, position="WR")]
        out = compute_rb_trailing_opportunity_ppg(
            pd.DataFrame(rows), season=2024, week=5
        )
        self.assertTrue(out.empty)

    def test_no_prior_games_returns_empty(self):
        rows = [_weekly_row("P1", 5, rushing_yards=100.0)]
        out = compute_rb_trailing_opportunity_ppg(
            pd.DataFrame(rows), season=2024, week=5
        )
        self.assertTrue(out.empty)

    def test_empty_input_returns_empty_with_columns(self):
        out = compute_rb_trailing_opportunity_ppg(pd.DataFrame(), season=2024, week=5)
        self.assertTrue(out.empty)
        self.assertEqual(
            list(out.columns),
            ["player_id", "trailing_opp_ppg", "trailing_opp_games"],
        )


class TestComputeRbRisingIds(unittest.TestCase):
    def test_flags_rising_player(self):
        ids = compute_rb_rising_ids(
            _rising_snaps(), _id_map_weekly(), season=2024, week=5
        )
        self.assertEqual(ids, {"P1"})

    def test_flat_snap_share_not_flagged(self):
        ids = compute_rb_rising_ids(
            _flat_snaps(), _id_map_weekly(), season=2024, week=5
        )
        self.assertEqual(ids, set())

    def test_empty_snap_counts_returns_empty_set(self):
        ids = compute_rb_rising_ids(
            pd.DataFrame(), _id_map_weekly(), season=2024, week=5
        )
        self.assertEqual(ids, set())

    def test_none_snap_counts_returns_empty_set(self):
        ids = compute_rb_rising_ids(None, _id_map_weekly(), season=2024, week=5)
        self.assertEqual(ids, set())

    def test_no_weekly_df_cannot_map_to_player_id(self):
        # Without a name->player_id map, the signal can't be attached to a
        # player_id, so it can never fire on a proj_df row keyed by id.
        ids = compute_rb_rising_ids(
            _rising_snaps(), pd.DataFrame(), season=2024, week=5
        )
        self.assertEqual(ids, set())

    def test_custom_threshold(self):
        # slope ~0.475; a threshold above that should not fire.
        ids = compute_rb_rising_ids(
            _rising_snaps(), _id_map_weekly(), season=2024, week=5, threshold=0.9
        )
        self.assertEqual(ids, set())


class TestApplyRbTailCalibration(unittest.TestCase):
    @staticmethod
    def _proj(rows):
        return pd.DataFrame(rows)

    def test_low_band_boosted_when_rising(self):
        proj = self._proj(
            [{"player_id": "P1", "position": "RB", "projected_points": 3.0}]
        )
        weekly = pd.concat(
            [
                _id_map_weekly(),
                pd.DataFrame(
                    [
                        _weekly_row("P1", 3, rushing_yards=80.0),
                        _weekly_row("P1", 4, rushing_yards=60.0),
                    ]
                ),
            ],
            ignore_index=True,
        )
        out = apply_rb_tail_calibration(
            proj, _rising_snaps(), weekly, season=2024, week=5,
            scoring_format="half_ppr",
        )
        # trailing_opp_ppg = 7.0; blended = 0.6*3.0 + 0.4*7.0 = 4.6
        self.assertTrue(out.iloc[0]["rb_tail_low_boost_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 4.6, places=2)

    def test_low_band_not_boosted_when_not_rising(self):
        proj = self._proj(
            [{"player_id": "P1", "position": "RB", "projected_points": 3.0}]
        )
        out = apply_rb_tail_calibration(
            proj, _flat_snaps(), _id_map_weekly(), season=2024, week=5,
            scoring_format="half_ppr",
        )
        self.assertFalse(out.iloc[0]["rb_tail_low_boost_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.0, places=2)

    def test_low_band_not_boosted_without_trailing_data(self):
        # Rising signal fires, but the player has no trailing weekly rows
        # at all -> trailing_opp_ppg is NaN -> no boost.
        proj = self._proj(
            [{"player_id": "P1", "position": "RB", "projected_points": 3.0}]
        )
        out = apply_rb_tail_calibration(
            proj, _rising_snaps(), _id_map_weekly(), season=2024, week=5,
            scoring_format="half_ppr",
        )
        self.assertFalse(out.iloc[0]["rb_tail_low_boost_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.0, places=2)

    def test_mid_band_untouched_regardless_of_signal(self):
        proj = self._proj(
            [{"player_id": "P1", "position": "RB", "projected_points": 10.0}]
        )
        weekly = pd.concat(
            [
                _id_map_weekly(),
                pd.DataFrame([_weekly_row("P1", 3, rushing_yards=80.0),
                              _weekly_row("P1", 4, rushing_yards=60.0)]),
            ],
            ignore_index=True,
        )
        out = apply_rb_tail_calibration(
            proj, _rising_snaps(), weekly, season=2024, week=5,
        )
        self.assertFalse(out.iloc[0]["rb_tail_low_boost_flag"])
        self.assertFalse(out.iloc[0]["rb_tail_high_shrink_flag"])
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 10.0, places=2)

    def test_high_band_shrunk_toward_position_mean(self):
        proj = self._proj(
            [
                {"player_id": "P1", "position": "RB", "projected_points": 20.0},
                {"player_id": "P2", "position": "RB", "projected_points": 10.0},
            ]
        )
        out = apply_rb_tail_calibration(
            proj, pd.DataFrame(), pd.DataFrame(), season=2024, week=5,
        )
        # pos_mean over ALL RB rows = (20+10)/2 = 15.0
        # P1 (>=14): blended = 0.85*20 + 0.15*15 = 17.0+2.25 = 19.25
        row1 = out[out["player_id"] == "P1"].iloc[0]
        self.assertTrue(row1["rb_tail_high_shrink_flag"])
        self.assertAlmostEqual(row1["projected_points"], 19.25, places=2)
        # P2 (<14, >=8): untouched
        row2 = out[out["player_id"] == "P2"].iloc[0]
        self.assertFalse(row2["rb_tail_high_shrink_flag"])
        self.assertAlmostEqual(row2["projected_points"], 10.0, places=2)

    def test_non_rb_untouched(self):
        proj = self._proj(
            [
                {"player_id": "P1", "position": "QB", "projected_points": 3.0},
                {"player_id": "P2", "position": "WR", "projected_points": 20.0},
            ]
        )
        out = apply_rb_tail_calibration(
            proj, _rising_snaps(), _id_map_weekly(), season=2024, week=5,
        )
        self.assertFalse(out["rb_tail_low_boost_flag"].any())
        self.assertFalse(out["rb_tail_high_shrink_flag"].any())
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 3.0, places=2)
        self.assertAlmostEqual(out.iloc[1]["projected_points"], 20.0, places=2)

    def test_boosted_low_band_row_crossing_into_high_band_gets_shrunk_too(self):
        # A large trailing PPG can push a boosted low-band row past 14 --
        # the high-band shrink pass must still see and adjust it.
        proj = self._proj(
            [{"player_id": "P1", "position": "RB", "projected_points": 7.9}]
        )
        weekly = pd.concat(
            [
                _id_map_weekly(),
                pd.DataFrame([_weekly_row("P1", 3, rushing_yards=350.0),
                              _weekly_row("P1", 4, rushing_yards=350.0)]),
            ],
            ignore_index=True,
        )
        out = apply_rb_tail_calibration(
            proj, _rising_snaps(), weekly, season=2024, week=5,
        )
        # trailing_opp_ppg = 35.0; boosted = 0.6*7.9 + 0.4*35.0 = 4.74+14.0=18.74
        # single RB row -> pos_mean == its own (boosted) value -> shrink is a no-op numerically
        self.assertTrue(out.iloc[0]["rb_tail_low_boost_flag"])
        self.assertTrue(out.iloc[0]["rb_tail_high_shrink_flag"])
        self.assertGreaterEqual(out.iloc[0]["projected_points"], HIGH_BAND_MIN)

    def test_empty_proj_df_returns_provenance_columns(self):
        out = apply_rb_tail_calibration(
            pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), season=2024, week=5,
        )
        self.assertIn("rb_tail_low_boost_flag", out.columns)
        self.assertIn("rb_tail_high_shrink_flag", out.columns)
        self.assertTrue(out.empty)

    def test_no_rb_rows_is_noop(self):
        proj = self._proj(
            [{"player_id": "P1", "position": "QB", "projected_points": 20.0}]
        )
        out = apply_rb_tail_calibration(
            proj, pd.DataFrame(), pd.DataFrame(), season=2024, week=5,
        )
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 20.0, places=2)

    def test_custom_weights(self):
        proj = self._proj(
            [{"player_id": "P1", "position": "RB", "projected_points": 20.0}]
        )
        out = apply_rb_tail_calibration(
            proj, pd.DataFrame(), pd.DataFrame(), season=2024, week=5,
            high_shrink=0.5,
        )
        # single row -> pos_mean == 20.0 -> shrink toward itself is a no-op
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 20.0, places=2)


class TestConstants(unittest.TestCase):
    def test_band_boundaries(self):
        self.assertEqual(LOW_BAND_MAX, 8.0)
        self.assertEqual(HIGH_BAND_MIN, 14.0)

    def test_default_weights(self):
        self.assertEqual(LOW_BAND_WEIGHT, 0.4)
        self.assertEqual(HIGH_SHRINK_FACTOR, 0.15)

    def test_rise_threshold(self):
        self.assertEqual(RISE_THRESHOLD, 0.15)


if __name__ == "__main__":
    unittest.main()
