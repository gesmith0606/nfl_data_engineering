"""
Unit tests for the WR near-tie ordinal tie-break lever
(.planning/WR_ORDERING_DIAGNOSIS.md finding #2).
"""

import os
import sys
import unittest

import pandas as pd

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from wr_tiebreak import (  # noqa: E402
    EPSILON,
    NUDGE,
    PRIOR_N,
    RECENT_N,
    apply_wr_tiebreak,
    compute_wr_target_share_slope,
)


def _weekly_row(player_id, week, target_share, position="WR", season=2024):
    return {
        "player_id": player_id,
        "season": season,
        "week": week,
        "position": position,
        "target_share": target_share,
    }


def _rising_weekly(player_id="P_LOW", season=2024):
    # prior window (weeks 1,2): 0.10 avg; recent window (weeks 3,4): 0.30 avg
    # -> slope = +0.20
    return pd.DataFrame(
        [
            _weekly_row(player_id, 1, 0.10, season=season),
            _weekly_row(player_id, 2, 0.10, season=season),
            _weekly_row(player_id, 3, 0.30, season=season),
            _weekly_row(player_id, 4, 0.30, season=season),
        ]
    )


def _flat_weekly(player_id="P_HI", season=2024):
    return pd.DataFrame(
        [_weekly_row(player_id, w, 0.20, season=season) for w in range(1, 5)]
    )


class TestComputeWrTargetShareSlope(unittest.TestCase):
    def test_computes_slope_strictly_prior(self):
        rows = pd.concat(
            [
                _rising_weekly("P1"),
                pd.DataFrame([_weekly_row("P1", 5, 999.0)]),  # must NOT leak
            ],
            ignore_index=True,
        )
        out = compute_wr_target_share_slope(rows, season=2024, week=5)
        self.assertEqual(len(out), 1)
        self.assertAlmostEqual(out.iloc[0]["target_share_slope"], 0.20, places=6)

    def test_window_defaults_to_2_and_2(self):
        self.assertEqual(RECENT_N, 2)
        self.assertEqual(PRIOR_N, 2)

    def test_flat_share_yields_zero_slope(self):
        out = compute_wr_target_share_slope(_flat_weekly("P1"), season=2024, week=5)
        self.assertAlmostEqual(out.iloc[0]["target_share_slope"], 0.0, places=6)

    def test_ignores_other_seasons(self):
        rows = _rising_weekly("P1", season=2023)
        out = compute_wr_target_share_slope(rows, season=2024, week=5)
        self.assertTrue(out.empty)

    def test_ignores_non_wr(self):
        rows = pd.DataFrame(
            [_weekly_row("P1", w, 0.30, position="RB") for w in range(1, 5)]
        )
        out = compute_wr_target_share_slope(rows, season=2024, week=5)
        self.assertTrue(out.empty)

    def test_no_prior_window_returns_empty(self):
        rows = pd.DataFrame([_weekly_row("P1", 4, 0.30)])
        out = compute_wr_target_share_slope(rows, season=2024, week=5)
        self.assertTrue(out.empty)

    def test_empty_input_returns_empty_with_columns(self):
        out = compute_wr_target_share_slope(pd.DataFrame(), season=2024, week=5)
        self.assertTrue(out.empty)
        self.assertEqual(list(out.columns), ["player_id", "target_share_slope"])

    def test_missing_target_share_column_returns_empty(self):
        rows = pd.DataFrame(
            [{"player_id": "P1", "season": 2024, "week": 3, "position": "WR"}]
        )
        out = compute_wr_target_share_slope(rows, season=2024, week=5)
        self.assertTrue(out.empty)


class TestApplyWrTiebreak(unittest.TestCase):
    @staticmethod
    def _proj(rows):
        return pd.DataFrame(rows)

    def test_nudges_apart_when_signal_disagrees(self):
        # P_HI projected higher but P_LOW has the rising target-share trend
        # -> signal disagrees with our order -> nudge apart.
        proj = self._proj(
            [
                {"player_id": "P_HI", "position": "WR", "projected_points": 11.0},
                {"player_id": "P_LOW", "position": "WR", "projected_points": 10.0},
            ]
        )
        weekly = pd.concat([_flat_weekly("P_HI"), _rising_weekly("P_LOW")], ignore_index=True)
        out = apply_wr_tiebreak(proj, weekly, season=2024, week=5)

        hi = out[out["player_id"] == "P_HI"].iloc[0]
        lo = out[out["player_id"] == "P_LOW"].iloc[0]
        self.assertTrue(hi["wr_tiebreak_flag"])
        self.assertTrue(lo["wr_tiebreak_flag"])
        self.assertAlmostEqual(hi["projected_points"], 11.0 - NUDGE, places=2)
        self.assertAlmostEqual(lo["projected_points"], 10.0 + NUDGE, places=2)

    def test_no_nudge_when_signal_agrees(self):
        # P_HI projected higher AND has the rising trend -> order already
        # agrees with the signal -> untouched.
        proj = self._proj(
            [
                {"player_id": "P_HI", "position": "WR", "projected_points": 11.0},
                {"player_id": "P_LOW", "position": "WR", "projected_points": 10.0},
            ]
        )
        weekly = pd.concat([_rising_weekly("P_HI"), _flat_weekly("P_LOW")], ignore_index=True)
        out = apply_wr_tiebreak(proj, weekly, season=2024, week=5)

        self.assertFalse(out["wr_tiebreak_flag"].any())
        self.assertAlmostEqual(out.loc[out["player_id"] == "P_HI", "projected_points"].iloc[0], 11.0, places=2)
        self.assertAlmostEqual(out.loc[out["player_id"] == "P_LOW", "projected_points"].iloc[0], 10.0, places=2)

    def test_no_nudge_when_gap_exceeds_epsilon(self):
        proj = self._proj(
            [
                {"player_id": "P_HI", "position": "WR", "projected_points": 20.0},
                {"player_id": "P_LOW", "position": "WR", "projected_points": 10.0},
            ]
        )
        self.assertGreater(20.0 - 10.0, EPSILON)
        weekly = pd.concat([_flat_weekly("P_HI"), _rising_weekly("P_LOW")], ignore_index=True)
        out = apply_wr_tiebreak(proj, weekly, season=2024, week=5)
        self.assertFalse(out["wr_tiebreak_flag"].any())
        self.assertAlmostEqual(out.loc[out["player_id"] == "P_HI", "projected_points"].iloc[0], 20.0, places=2)

    def test_no_nudge_without_signal_data(self):
        proj = self._proj(
            [
                {"player_id": "P_HI", "position": "WR", "projected_points": 11.0},
                {"player_id": "P_LOW", "position": "WR", "projected_points": 10.0},
            ]
        )
        out = apply_wr_tiebreak(proj, pd.DataFrame(), season=2024, week=5)
        self.assertFalse(out["wr_tiebreak_flag"].any())
        self.assertAlmostEqual(out.loc[out["player_id"] == "P_HI", "projected_points"].iloc[0], 11.0, places=2)

    def test_non_wr_untouched(self):
        proj = self._proj(
            [
                {"player_id": "P1", "position": "RB", "projected_points": 11.0},
                {"player_id": "P2", "position": "QB", "projected_points": 10.5},
            ]
        )
        weekly = pd.concat([_flat_weekly("P1"), _rising_weekly("P2")], ignore_index=True)
        out = apply_wr_tiebreak(proj, weekly, season=2024, week=5)
        self.assertFalse(out["wr_tiebreak_flag"].any())
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 11.0, places=2)
        self.assertAlmostEqual(out.iloc[1]["projected_points"], 10.5, places=2)

    def test_single_wr_row_is_noop(self):
        proj = self._proj(
            [{"player_id": "P1", "position": "WR", "projected_points": 11.0}]
        )
        out = apply_wr_tiebreak(proj, _rising_weekly("P1"), season=2024, week=5)
        self.assertFalse(out["wr_tiebreak_flag"].any())
        self.assertAlmostEqual(out.iloc[0]["projected_points"], 11.0, places=2)

    def test_empty_proj_df_returns_provenance_column(self):
        out = apply_wr_tiebreak(pd.DataFrame(), pd.DataFrame(), season=2024, week=5)
        self.assertIn("wr_tiebreak_flag", out.columns)
        self.assertTrue(out.empty)

    def test_nudge_capped_at_half_epsilon(self):
        self.assertLessEqual(NUDGE, EPSILON / 2)

    def test_result_never_negative(self):
        proj = self._proj(
            [
                {"player_id": "P_HI", "position": "WR", "projected_points": 0.2},
                {"player_id": "P_LOW", "position": "WR", "projected_points": 0.1},
            ]
        )
        weekly = pd.concat([_flat_weekly("P_HI"), _rising_weekly("P_LOW")], ignore_index=True)
        out = apply_wr_tiebreak(proj, weekly, season=2024, week=5)
        self.assertTrue((out["projected_points"] >= 0).all())

    def test_chained_adjacent_pairs_accumulate(self):
        # Three WRs within epsilon of each other, each adjacent pair
        # disagreeing -> the middle player is adjusted by both pairs.
        proj = self._proj(
            [
                {"player_id": "A", "position": "WR", "projected_points": 12.0},
                {"player_id": "B", "position": "WR", "projected_points": 11.0},
                {"player_id": "C", "position": "WR", "projected_points": 10.0},
            ]
        )
        # A flat, B rising (disagrees with A>B), C rising even more (disagrees with B>C)
        weekly = pd.concat(
            [
                _flat_weekly("A"),
                pd.DataFrame(
                    [
                        _weekly_row("B", 1, 0.10), _weekly_row("B", 2, 0.10),
                        _weekly_row("B", 3, 0.25), _weekly_row("B", 4, 0.25),
                    ]
                ),
                pd.DataFrame(
                    [
                        _weekly_row("C", 1, 0.10), _weekly_row("C", 2, 0.10),
                        _weekly_row("C", 3, 0.40), _weekly_row("C", 4, 0.40),
                    ]
                ),
            ],
            ignore_index=True,
        )
        out = apply_wr_tiebreak(proj, weekly, season=2024, week=5)
        b_row = out[out["player_id"] == "B"].iloc[0]
        # B loses NUDGE to A's pair, gains NUDGE from C's pair -> net 0 change,
        # but still flagged as fired.
        self.assertTrue(b_row["wr_tiebreak_flag"])
        self.assertAlmostEqual(b_row["projected_points"], 11.0, places=2)


class TestConstants(unittest.TestCase):
    def test_epsilon(self):
        self.assertEqual(EPSILON, 1.5)

    def test_nudge(self):
        self.assertEqual(NUDGE, 0.5)

    def test_windows(self):
        self.assertEqual(RECENT_N, 2)
        self.assertEqual(PRIOR_N, 2)


if __name__ == "__main__":
    unittest.main()
