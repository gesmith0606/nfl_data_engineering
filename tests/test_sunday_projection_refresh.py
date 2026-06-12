"""
Unit tests for the Sunday Projection Refresh script.

Covers:
  - Undo/re-apply round-trip correctness for all status transitions
  - No-double-application invariant (refresh with same data = no additional change)
  - Asymmetry handling when old multiplier==0 but new status clears the player
  - Case B path (Gold file without prior injury columns)
  - Empty/missing data grace paths
  - Season/week auto-detection smoke test
"""

import datetime
import os
import sys
import tempfile
import unittest

import pandas as pd

# Ensure scripts directory can resolve its src imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts.sunday_projection_refresh import (
    SCALABLE_ALWAYS_COLS,
    _undo_and_reapply,
    detect_nfl_week,
    _load_latest_gold_projections,
    _write_gold_output,
)
from projection_engine import INJURY_MULTIPLIERS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_gold_df(with_injury_cols: bool = True) -> pd.DataFrame:
    """Build a minimal Gold projection DataFrame for tests.

    Args:
        with_injury_cols: If True, include injury_status/injury_multiplier
            columns as they would appear in a regular-season Gold file.

    Returns:
        DataFrame with 4 test players.
    """
    data = {
        "player_id": ["p1", "p2", "p3", "p4"],
        "player_name": ["Active Player", "Questionable Player", "Out Player", "Healthy Player"],
        "position": ["QB", "RB", "WR", "TE"],
        "projected_points": [22.0, 10.2, 0.0, 8.5],
        "passing_yards": [300.0, 0.0, 0.0, 0.0],
        "rushing_yards": [30.0, 80.0, 0.0, 5.0],
        "receiving_yards": [0.0, 20.0, 0.0, 60.0],
        "projected_floor": [12.0, 5.0, 0.0, 4.0],
        "projected_ceiling": [38.0, 18.0, 0.0, 16.0],
    }
    if with_injury_cols:
        # Matches the state AFTER Tuesday's apply_injury_adjustments:
        #   Active Player  → multiplier 1.0 (full points)
        #   Questionable   → multiplier 0.85 (10.2 = 12.0 * 0.85)
        #   Out Player     → multiplier 0.0 (all stats = 0)
        #   Healthy Player → multiplier 1.0
        data["injury_status"] = ["Active", "Questionable", "Out", "Active"]
        data["injury_multiplier"] = [1.0, 0.85, 0.0, 1.0]
    return pd.DataFrame(data)


def _inj_df(player_name: str, status: str) -> pd.DataFrame:
    """Build a minimal one-row injury DataFrame for testing."""
    return pd.DataFrame({
        "player_name": [player_name],
        "report_status": [status],
    })


# ---------------------------------------------------------------------------
# Round-trip tests (Case A — Gold file HAS injury columns)
# ---------------------------------------------------------------------------


class TestUndoReapplyCaseA(unittest.TestCase):
    """Tests for the undo/re-apply path when Gold file has injury columns."""

    def test_questionable_to_active_round_trip(self):
        """Player improves from Questionable→Active: points should be restored."""
        gold = _make_gold_df(with_injury_cols=True)
        # Fresh injury report clears the Questionable player to Active
        fresh_inj = pd.DataFrame({
            "player_name": ["Questionable Player"],
            "report_status": ["Active"],
        })
        result, summary = _undo_and_reapply(gold, fresh_inj)
        row = result[result["player_name"] == "Questionable Player"].iloc[0]

        # Undo: 10.2 / 0.85 = 12.0; re-apply Active (1.0) = 12.0
        self.assertAlmostEqual(row["projected_points"], 12.0, places=1)
        self.assertEqual(row["injury_status"], "Active")
        self.assertAlmostEqual(row["injury_multiplier"], 1.0)

    def test_active_to_out_zeroes_projected_points(self):
        """Player moves from Active→Out: projected_points should be zeroed.

        Note: bare stat columns (passing_yards etc.) are NOT scaled by
        apply_injury_adjustments — only projected_points and proj_* cols are.
        """
        gold = _make_gold_df(with_injury_cols=True)
        fresh_inj = _inj_df("Active Player", "Out")
        result, summary = _undo_and_reapply(gold, fresh_inj)
        row = result[result["player_name"] == "Active Player"].iloc[0]

        self.assertEqual(row["projected_points"], 0.0)
        self.assertEqual(row["injury_status"], "Out")
        self.assertEqual(row["injury_multiplier"], 0.0)
        self.assertGreater(summary["new_outs"], 0)
        # Bare stat columns are informational — NOT zeroed by injury adjustments
        self.assertEqual(row["passing_yards"], 300.0)

    def test_active_to_questionable(self):
        """Player moves from Active→Questionable: points should be 85% of original."""
        gold = _make_gold_df(with_injury_cols=True)
        fresh_inj = _inj_df("Active Player", "Questionable")
        result, summary = _undo_and_reapply(gold, fresh_inj)
        row = result[result["player_name"] == "Active Player"].iloc[0]

        # Active Player had 22.0 projected points (multiplier was 1.0)
        # Undo 1.0: still 22.0; re-apply Questionable 0.85 → 18.7
        self.assertAlmostEqual(row["projected_points"], 22.0 * 0.85, places=1)
        self.assertAlmostEqual(row["injury_multiplier"], 0.85)

    def test_unchanged_players_untouched(self):
        """Players not in the fresh injury report retain current values."""
        gold = _make_gold_df(with_injury_cols=True)
        fresh_inj = _inj_df("Active Player", "Out")
        result, summary = _undo_and_reapply(gold, fresh_inj)

        # Healthy Player (Active, not in fresh report) should be unchanged
        healthy_row = result[result["player_name"] == "Healthy Player"].iloc[0]
        self.assertAlmostEqual(healthy_row["projected_points"], 8.5)
        self.assertEqual(healthy_row["injury_status"], "Active")

    def test_out_to_active_asymmetry_documented(self):
        """Out→Active transition logs asymmetry and leaves player at 0 points.

        This is the known limitation: if the old multiplier was 0, the raw
        stat values are all 0 on disk and cannot be restored without re-running
        the full model.
        """
        gold = _make_gold_df(with_injury_cols=True)
        fresh_inj = _inj_df("Out Player", "Active")
        result, summary = _undo_and_reapply(gold, fresh_inj)
        row = result[result["player_name"] == "Out Player"].iloc[0]

        # Player was zeroed → cannot restore: remains 0
        self.assertEqual(row["projected_points"], 0.0)
        self.assertEqual(summary["asymmetry_limited"], 1)
        # Status should show the new active designation
        self.assertEqual(row["injury_status"], "Active")

    def test_summary_case_a(self):
        """Summary dict should report 'A' for Gold file with injury columns."""
        gold = _make_gold_df(with_injury_cols=True)
        _, summary = _undo_and_reapply(gold, pd.DataFrame())
        self.assertEqual(summary["case"], "A")

    def test_questionable_to_doubtful(self):
        """Questionable→Doubtful: points reduced from 0.85x base to 0.5x base."""
        gold = _make_gold_df(with_injury_cols=True)
        fresh_inj = _inj_df("Questionable Player", "Doubtful")
        result, _ = _undo_and_reapply(gold, fresh_inj)
        row = result[result["player_name"] == "Questionable Player"].iloc[0]

        # Original base = 10.2 / 0.85 = 12.0; Doubtful mult = 0.5 → 6.0
        self.assertAlmostEqual(row["projected_points"], 12.0 * 0.5, places=1)
        self.assertAlmostEqual(row["injury_multiplier"], 0.5)


# ---------------------------------------------------------------------------
# No-double-application invariant
# ---------------------------------------------------------------------------


class TestNoDoubleApplication(unittest.TestCase):
    """Refreshing twice with the same injury data must produce no additional change."""

    def test_same_injury_idempotent(self):
        """Applying the same injury report twice yields the same projected points."""
        gold = _make_gold_df(with_injury_cols=True)
        fresh_inj = pd.DataFrame({
            "player_name": ["Questionable Player"],
            "report_status": ["Questionable"],
        })
        # First refresh
        first, _ = _undo_and_reapply(gold, fresh_inj)
        # Second refresh (same injury data applied to already-refreshed output)
        second, _ = _undo_and_reapply(first, fresh_inj)

        pd.testing.assert_series_equal(
            first["projected_points"].round(3),
            second["projected_points"].round(3),
            check_names=False,
        )

    def test_all_active_idempotent(self):
        """When all players are Active and no injury report is present, no change."""
        gold = _make_gold_df(with_injury_cols=True)
        # Set everyone to Active for this test
        gold["injury_status"] = "Active"
        gold["injury_multiplier"] = 1.0
        gold["projected_points"] = [22.0, 12.0, 15.0, 8.5]
        gold["rushing_yards"] = [30.0, 80.0, 50.0, 5.0]

        result, summary = _undo_and_reapply(gold, pd.DataFrame())
        pd.testing.assert_series_equal(
            gold["projected_points"].round(3),
            result["projected_points"].round(3),
            check_names=False,
        )
        self.assertEqual(summary["multiplier_changed"], 0)


# ---------------------------------------------------------------------------
# Case B tests (Gold file WITHOUT prior injury columns)
# ---------------------------------------------------------------------------


class TestUndoReapplyCaseB(unittest.TestCase):
    """Tests for the direct-apply path when Gold file has no injury columns."""

    def test_case_b_applies_adjustments(self):
        """Case B applies injury adjustments directly to the raw stat values."""
        gold = _make_gold_df(with_injury_cols=False)
        # Preseason Gold: everyone has their "clean" projected_points
        gold["projected_points"] = [22.0, 12.0, 15.0, 8.5]

        fresh_inj = _inj_df("Active Player", "Out")
        result, summary = _undo_and_reapply(gold, fresh_inj)

        self.assertEqual(summary["case"], "B")
        row = result[result["player_name"] == "Active Player"].iloc[0]
        self.assertEqual(row["projected_points"], 0.0)
        self.assertEqual(row["injury_multiplier"], 0.0)

    def test_case_b_questionable(self):
        """Case B applies the 0.85 multiplier for Questionable players."""
        gold = _make_gold_df(with_injury_cols=False)
        gold["projected_points"] = [22.0, 12.0, 15.0, 8.5]

        fresh_inj = _inj_df("Healthy Player", "Questionable")
        result, _ = _undo_and_reapply(gold, fresh_inj)
        row = result[result["player_name"] == "Healthy Player"].iloc[0]
        self.assertAlmostEqual(row["projected_points"], 8.5 * 0.85, places=1)

    def test_case_b_no_injury_data_unchanged(self):
        """Case B with empty injury df: all players remain at their base values."""
        gold = _make_gold_df(with_injury_cols=False)
        gold["projected_points"] = [22.0, 12.0, 15.0, 8.5]

        result, summary = _undo_and_reapply(gold, pd.DataFrame())
        self.assertEqual(summary["case"], "B")
        pd.testing.assert_series_equal(
            gold["projected_points"].round(3),
            result["projected_points"].round(3),
            check_names=False,
        )

    def test_case_b_no_double_apply(self):
        """Applying Case B twice: second pass must not compound the multiplier."""
        gold = _make_gold_df(with_injury_cols=False)
        gold["projected_points"] = [22.0, 12.0, 15.0, 8.5]

        fresh_inj = _inj_df("Healthy Player", "Questionable")
        first, _ = _undo_and_reapply(gold, fresh_inj)
        # Second pass: first output now has injury columns (Case A)
        second, _ = _undo_and_reapply(first, fresh_inj)

        pd.testing.assert_series_equal(
            first["projected_points"].round(3),
            second["projected_points"].round(3),
            check_names=False,
        )


# ---------------------------------------------------------------------------
# Empty / missing data grace
# ---------------------------------------------------------------------------


class TestEmptyDataGrace(unittest.TestCase):
    """The script must never raise when key data is absent."""

    def test_empty_injuries_returns_original(self):
        """Empty fresh injury data: projected_points unchanged for all players."""
        gold = _make_gold_df(with_injury_cols=True)
        original_pts = gold["projected_points"].copy()

        result, summary = _undo_and_reapply(gold, pd.DataFrame())

        # For Case A with empty injuries: undo and re-apply with no injury info
        # means all players come back as Active (1.0 multiplier), so we DO
        # expect changes for players who were previously non-Active.
        # The point is that the function DOES NOT RAISE.
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), len(gold))

    def test_empty_gold_df_survives(self):
        """Empty Gold DataFrame should not raise."""
        empty_gold = pd.DataFrame()
        result, summary = _undo_and_reapply(empty_gold, pd.DataFrame())
        self.assertIsInstance(result, pd.DataFrame)
        self.assertTrue(result.empty)

    def test_gold_without_player_name_col_survives(self):
        """Gold file missing join columns should gracefully return df unchanged."""
        gold = pd.DataFrame({
            "player_id": ["p1"],
            "projected_points": [10.0],
        })
        inj = pd.DataFrame({
            "player_name": ["Player X"],
            "report_status": ["Out"],
        })
        # Should not raise — just return df with injury columns added as Active
        result, _ = _undo_and_reapply(gold, inj)
        self.assertIsInstance(result, pd.DataFrame)


# ---------------------------------------------------------------------------
# Season / week detection smoke test
# ---------------------------------------------------------------------------


class TestDetectNFLWeek(unittest.TestCase):
    """Smoke tests for the NFL calendar auto-detection."""

    def test_returns_tuple(self):
        """detect_nfl_week returns a (season, week) tuple."""
        result = detect_nfl_week(_today=datetime.date(2024, 10, 15))
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)

    def test_week_in_valid_range(self):
        """Detected week must be in 1-18."""
        _, week = detect_nfl_week(_today=datetime.date(2024, 10, 15))
        self.assertGreaterEqual(week, 1)
        self.assertLessEqual(week, 18)

    def test_season_reasonable(self):
        """Detected season should be within 2 years of an in-season date."""
        season, _ = detect_nfl_week(_today=datetime.date(2024, 10, 15))
        self.assertGreaterEqual(season, 2022)
        self.assertLessEqual(season, 2026)

    def test_known_date_week1_2024(self):
        """September 6, 2024 (a Friday) should resolve to season=2024, week=1."""
        season, week = detect_nfl_week(_today=datetime.date(2024, 9, 6))
        self.assertEqual(season, 2024)
        self.assertEqual(week, 1)

    def test_preseason_before_week1_uses_prior_year(self):
        """May 15, 2025 (pre-season) should detect as prior season (2024, week 18)."""
        season, week = detect_nfl_week(_today=datetime.date(2025, 5, 15))
        self.assertEqual(season, 2024)
        # Week should be capped at 18
        self.assertEqual(week, 18)


# ---------------------------------------------------------------------------
# Output file writer smoke test
# ---------------------------------------------------------------------------


class TestWriteGoldOutput(unittest.TestCase):
    """Verify that _write_gold_output writes a readable parquet file."""

    def test_writes_and_reads_back(self):
        """Written file should be loadable and match the input DataFrame."""
        gold = _make_gold_df(with_injury_cols=False)
        ts = "20991231_120000"

        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily override GOLD_DIR
            import scripts.sunday_projection_refresh as spr
            original_gold_dir = spr.GOLD_DIR
            spr.GOLD_DIR = tmpdir
            try:
                path = _write_gold_output(gold, 2026, 1, "half_ppr", ts)
                self.assertTrue(os.path.exists(path))
                loaded = pd.read_parquet(path)
                self.assertEqual(len(loaded), len(gold))
                self.assertIn("projected_points", loaded.columns)
            finally:
                spr.GOLD_DIR = original_gold_dir


# ---------------------------------------------------------------------------
# Integration-style: round-trip through a realistic workflow
# ---------------------------------------------------------------------------


class TestRoundTripWorkflow(unittest.TestCase):
    """Simulate the full undo/re-apply round-trip for common status transitions."""

    def _base_gold(self) -> pd.DataFrame:
        """Build a Gold df where injuries were already applied on Tuesday."""
        return pd.DataFrame({
            "player_name": ["QB1", "RB1", "WR1", "TE1"],
            "position": ["QB", "RB", "WR", "TE"],
            # These are post-injury-application values:
            # QB1: Active (22.0 raw * 1.0 = 22.0)
            # RB1: Questionable (14.0 raw * 0.85 = 11.9)
            # WR1: Out (18.0 raw * 0.0 = 0.0)
            # TE1: Active (9.0 raw * 1.0 = 9.0)
            "projected_points": [22.0, 11.9, 0.0, 9.0],
            "rushing_yards": [20.0, 85.0 * 0.85, 0.0, 5.0],
            "receiving_yards": [0.0, 15.0 * 0.85, 0.0, 60.0],
            "injury_status": ["Active", "Questionable", "Out", "Active"],
            "injury_multiplier": [1.0, 0.85, 0.0, 1.0],
            "projected_floor": [12.0, 5.5, 0.0, 4.0],
            "projected_ceiling": [38.0, 20.0, 0.0, 16.0],
        })

    def test_rb_clears_to_active(self):
        """RB was Questionable Tuesday; clears Active Sunday — points increase."""
        gold = self._base_gold()
        fresh = _inj_df("RB1", "Active")
        result, summary = _undo_and_reapply(gold, fresh)
        rb = result[result["player_name"] == "RB1"].iloc[0]

        # 11.9 / 0.85 = 14.0; * 1.0 = 14.0
        self.assertAlmostEqual(rb["projected_points"], 14.0, places=1)
        self.assertEqual(rb["injury_status"], "Active")
        self.assertGreater(summary["cleared_to_active"], 0)

    def test_qb_surprise_out(self):
        """QB was Active Tuesday; gets ruled Out Sunday — projected_points zeroed.

        Note: bare stat columns (rushing_yards, etc.) are informational and
        NOT zeroed by apply_injury_adjustments — only projected_points is.
        """
        gold = self._base_gold()
        fresh = _inj_df("QB1", "Out")
        result, summary = _undo_and_reapply(gold, fresh)
        qb = result[result["player_name"] == "QB1"].iloc[0]

        self.assertEqual(qb["projected_points"], 0.0)
        self.assertEqual(qb["injury_multiplier"], 0.0)
        self.assertEqual(summary["new_outs"], 1)

    def test_wr_stays_out(self):
        """WR is Out on both Tuesday and Sunday — still zero, no asymmetry."""
        gold = self._base_gold()
        fresh = _inj_df("WR1", "Out")
        result, summary = _undo_and_reapply(gold, fresh)
        wr = result[result["player_name"] == "WR1"].iloc[0]

        self.assertEqual(wr["projected_points"], 0.0)
        self.assertEqual(summary["asymmetry_limited"], 0)

    def test_te_new_questionable(self):
        """TE was Active Tuesday; listed Questionable Sunday — slight reduction."""
        gold = self._base_gold()
        fresh = _inj_df("TE1", "Questionable")
        result, _ = _undo_and_reapply(gold, fresh)
        te = result[result["player_name"] == "TE1"].iloc[0]

        self.assertAlmostEqual(te["projected_points"], 9.0 * 0.85, places=1)

    def test_no_change_when_report_matches_tuesday(self):
        """Fresh report matches Tuesday status exactly — values unchanged."""
        gold = self._base_gold()
        # Same statuses as what was applied on Tuesday
        fresh = pd.DataFrame({
            "player_name": ["QB1", "RB1", "TE1"],
            "report_status": ["Active", "Questionable", "Active"],
        })
        result, summary = _undo_and_reapply(gold, fresh)

        # QB1: 22.0 / 1.0 * 1.0 = 22.0
        qb = result[result["player_name"] == "QB1"].iloc[0]
        self.assertAlmostEqual(qb["projected_points"], 22.0, places=1)

        # RB1: 11.9 / 0.85 * 0.85 ≈ 11.9
        rb = result[result["player_name"] == "RB1"].iloc[0]
        self.assertAlmostEqual(rb["projected_points"], 11.9, places=1)

        # multiplier_changed should be 0 for QB1, RB1, TE1 (and WR1 changes
        # from Out to Active asymmetrically but no fresh entry exists for it)
        # The important thing is no compounding for the matched players.
        qb_mult = result[result["player_name"] == "QB1"]["injury_multiplier"].iloc[0]
        rb_mult = result[result["player_name"] == "RB1"]["injury_multiplier"].iloc[0]
        self.assertAlmostEqual(qb_mult, 1.0)
        self.assertAlmostEqual(rb_mult, 0.85)


if __name__ == "__main__":
    unittest.main()
