"""Tests for the per-position dispersion shrinkage lever.

Lever shipped 2026-10-21 (``.planning/SEASON_2026_MIDSEASON_RETRO.md``):
our 2026 w1-6 board over-projected the top of each position and
under-projected the bottom, so every position's rows are pulled toward that
position's own startable-pool mean at k=0.8.

This file covers the lever's math and — more importantly — its safety
invariants: it must never resurrect a bye-week or injury-zeroed row, never
reorder a position, and never go negative.  CLI wiring lives in
``test_dispersion_shrink_cli.py``.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))

from dispersion_shrink import (  # noqa: E402
    FLAG_COL,
    INTERVAL_COLS,
    MIN_CENTRE_PTS,
    MIN_CENTRE_ROWS,
    MIN_SHRINK_PTS,
    SHRINK_FACTOR,
    SUPPORTED_POSITIONS,
    apply_dispersion_shrink,
    compute_position_centres,
)


def _board(rows):
    """Build a projection board; rows are (player_id, position, points)."""
    return pd.DataFrame(
        [
            {
                "player_id": pid,
                "player_name": pid,
                "position": pos,
                "projected_points": pts,
            }
            for pid, pos, pts in rows
        ]
    )


def _wr_board(points):
    return _board([(f"W{i}", "WR", p) for i, p in enumerate(points)])


class TestShippedConstants:
    def test_shipped_factor_is_conservative_prior(self):
        """0.8 sits above the 2026 w3-6 per-week fitted optimum (0.65-0.75)
        deliberately — a fixed prior, not a tuned knob."""
        assert SHRINK_FACTOR == 0.8

    def test_centre_threshold_matches_consensus_population(self):
        """The centre is the mean of the STARTABLE pool; the threshold is the
        repo's canonical cons>=5 cutoff so board composition in the
        deep-bench tail cannot move it."""
        from consensus_metrics import CONSENSUS_MIN_PTS

        assert MIN_CENTRE_PTS == CONSENSUS_MIN_PTS

    def test_adjust_floor_equals_the_centre_threshold(self):
        """The lever calibrates exactly the population the retro measured."""
        assert MIN_SHRINK_PTS == MIN_CENTRE_PTS

    def test_kickers_and_defenses_out_of_scope(self):
        assert set(SUPPORTED_POSITIONS) == {"QB", "RB", "WR", "TE"}


class TestComputePositionCentres:
    def test_centre_is_mean_of_startable_rows_only(self):
        """A deep-bench row below the threshold must not drag the centre."""
        board = _wr_board([20.0, 10.0, 6.0, 0.5, 0.5, 0.5])
        centres = compute_position_centres(board, min_centre_rows=3)
        assert centres["WR"] == pytest.approx(12.0)

    def test_position_with_too_few_startable_rows_is_omitted(self):
        board = _wr_board([20.0, 10.0] + [1.0] * 10)
        assert compute_position_centres(board, min_centre_rows=5) == {}

    def test_each_position_gets_its_own_centre(self):
        board = _board(
            [
                ("Q1", "QB", 20.0),
                ("Q2", "QB", 12.0),
                ("W1", "WR", 10.0),
                ("W2", "WR", 6.0),
            ]
        )
        centres = compute_position_centres(board, min_centre_rows=2)
        assert centres["QB"] == pytest.approx(16.0)
        assert centres["WR"] == pytest.approx(8.0)

    def test_empty_or_malformed_input_returns_empty(self):
        assert compute_position_centres(pd.DataFrame()) == {}
        assert compute_position_centres(pd.DataFrame({"position": ["WR"]})) == {}


class TestShrinkMath:
    def test_pulls_high_down_and_low_up_toward_centre(self):
        board = _wr_board([20.0, 10.0, 6.0])  # centre 12.0
        out, stats = apply_dispersion_shrink(board, k=0.5, min_centre_rows=3)
        # centre + k*(x - centre)
        assert out["projected_points"].tolist() == [16.0, 11.0, 9.0]
        assert stats[0]["centre"] == 12.0
        assert stats[0]["sd_after"] < stats[0]["sd_before"]

    def test_k_of_one_is_an_explicit_no_op(self):
        board = _wr_board([20.0, 10.0, 6.0])
        out, stats = apply_dispersion_shrink(board, k=1.0, min_centre_rows=3)
        assert out["projected_points"].tolist() == [20.0, 10.0, 6.0]
        assert stats == []
        assert not out[FLAG_COL].any()

    def test_row_at_the_centre_is_unmoved(self):
        board = _wr_board([20.0, 12.0, 4.0, 12.0])  # startable mean 14.666
        out, _ = apply_dispersion_shrink(
            board, k=0.5, min_centre_pts=12.0, min_centre_rows=3
        )
        # centre = mean(20, 12, 12) = 14.666; the 4.0 row is still eligible
        # (shrunk) even though it does not contribute to the centre.
        assert out.loc[1, "projected_points"] == pytest.approx(13.33, abs=0.01)

    def test_never_returns_negative_points(self):
        board = _board(
            [(f"W{i}", "WR", p) for i, p in enumerate([30.0, 20.0, 15.0, 0.1])]
        )
        out, _ = apply_dispersion_shrink(board, k=1.0, min_centre_rows=3)
        assert (out["projected_points"] >= 0).all()

    def test_rejects_out_of_range_k(self):
        board = _wr_board([20.0, 10.0, 6.0])
        for bad in (0.0, -0.5, 1.5):
            with pytest.raises(ValueError, match="must be in"):
                apply_dispersion_shrink(board, k=bad)

    def test_does_not_mutate_the_caller_frame(self):
        board = _wr_board([20.0, 10.0, 6.0])
        before = board["projected_points"].tolist()
        apply_dispersion_shrink(board, k=0.5, min_centre_rows=3)
        assert board["projected_points"].tolist() == before
        assert FLAG_COL not in board.columns


class TestOrderingInvariant:
    def test_position_ordering_is_preserved(self):
        """The transform is affine and monotone within a position, so it can
        only change magnitudes — never start/sit ordering. This is why the
        retro credits it with MAE but no Spearman gain."""
        board = _wr_board([25.0, 18.0, 14.0, 11.0, 9.0, 7.0, 5.5])
        out, _ = apply_dispersion_shrink(board, k=0.6)
        ranks_before = board["projected_points"].rank(ascending=False).tolist()
        ranks_after = out["projected_points"].rank(ascending=False).tolist()
        assert ranks_before == ranks_after

    def test_shrink_reduces_spread_at_every_position(self):
        board = _board(
            [(f"Q{i}", "QB", p) for i, p in enumerate([26.0, 20.0, 16.0, 12.0, 8.0])]
            + [(f"T{i}", "TE", p) for i, p in enumerate([16.0, 12.0, 9.0, 7.0, 5.0])]
        )
        out, stats = apply_dispersion_shrink(board, k=0.7)
        assert {st["position"] for st in stats} == {"QB", "TE"}
        for pos in ("QB", "TE"):
            sd_before = board.loc[board.position == pos, "projected_points"].std(ddof=0)
            sd_after = out.loc[out.position == pos, "projected_points"].std(ddof=0)
            assert sd_after < sd_before


class TestSafetyInvariants:
    """The lever RAISES low projections, so anything deliberately zeroed must
    be out of scope — otherwise a player who is not playing lands back on the
    board at a couple of points."""

    def test_bye_week_rows_are_never_touched(self):
        board = _wr_board([20.0, 12.0, 10.0, 6.0, 5.5, 0.0])
        board["is_bye_week"] = [False] * 5 + [True]
        out, stats = apply_dispersion_shrink(board, k=0.5)
        assert stats, "lever did not fire — test would be vacuous"
        assert out.loc[5, "projected_points"] == 0.0
        assert not out.loc[5, FLAG_COL]
        # ...while the non-bye rows around it WERE calibrated
        assert out.loc[0, "projected_points"] < 20.0

    def test_injury_zeroed_rows_are_never_resurrected(self):
        """apply_injury_adjustments zeroes Out/IR/PUP players before this
        stage runs (injury_multiplier == 0.0 -> projected_points 0.0)."""
        board = _wr_board([20.0, 12.0, 10.0, 6.0, 5.5, 0.0])
        board["injury_multiplier"] = [1.0] * 5 + [0.0]
        out, stats = apply_dispersion_shrink(board, k=0.5)
        assert stats, "lever did not fire — test would be vacuous"
        assert out.loc[5, "projected_points"] == 0.0
        assert not out.loc[5, FLAG_COL]
        assert out.loc[0, "projected_points"] < 20.0

    def test_zeroed_rows_do_not_drag_the_centre(self):
        live = _wr_board([20.0, 12.0, 10.0, 6.0])
        with_zeros = _wr_board([20.0, 12.0, 10.0, 6.0, 0.0, 0.0, 0.0])
        c_live = compute_position_centres(live, min_centre_rows=4)
        c_zeros = compute_position_centres(with_zeros, min_centre_rows=4)
        assert c_live["WR"] == pytest.approx(c_zeros["WR"])

    def test_unsupported_positions_pass_through_untouched(self):
        board = _board(
            [(f"W{i}", "WR", p) for i, p in enumerate([20.0, 12.0, 10.0, 6.0, 5.0])]
            + [("K1", "K", 9.0), ("D1", "DST", 14.0)]
        )
        out, stats = apply_dispersion_shrink(board, k=0.5)
        assert out.loc[out.position == "K", "projected_points"].tolist() == [9.0]
        assert out.loc[out.position == "DST", "projected_points"].tolist() == [14.0]
        assert {st["position"] for st in stats} == {"WR"}

    def test_empty_board_is_a_safe_no_op(self):
        out, stats = apply_dispersion_shrink(pd.DataFrame(), k=0.8)
        assert out.empty and stats == []
        assert FLAG_COL in out.columns

    def test_thin_board_is_a_no_op_rather_than_a_wild_centre(self):
        board = _wr_board([20.0, 6.0])
        out, stats = apply_dispersion_shrink(board, k=0.5)
        assert stats == []
        assert out["projected_points"].tolist() == [20.0, 6.0]
        assert MIN_CENTRE_ROWS > 2


class TestStats:
    def test_stats_report_coverage_and_effect(self):
        board = _wr_board([20.0, 12.0, 10.0, 6.0, 5.5, 1.0])
        out, stats = apply_dispersion_shrink(board, k=0.5)
        assert len(stats) == 1
        st = stats[0]
        assert st["position"] == "WR"
        assert st["k"] == 0.5
        # 5 rows clear the >=5 adjust floor; the 1.0-pt bench row is left
        # alone (and contributes to neither the centre nor the count)
        assert st["n_rows"] == 5
        assert st["n_centre_rows"] == 5
        assert st["mean_abs_change"] > 0
        assert int(out[FLAG_COL].sum()) == 5

    def test_flag_marks_exactly_the_adjusted_rows(self):
        board = _wr_board([20.0, 12.0, 10.0, 6.0, 5.5, 0.0])
        out, _ = apply_dispersion_shrink(board, k=0.5)
        changed = out["projected_points"] != board["projected_points"]
        assert changed.any(), "lever did not fire — test would be vacuous"
        # every changed row is flagged (a row landing exactly on the centre
        # is flagged but unchanged, so flags are a superset of changes)
        assert (out.loc[changed, FLAG_COL]).all()
        assert (
            not out.loc[~out[FLAG_COL], "projected_points"]
            .ne(board.loc[~out[FLAG_COL], "projected_points"])
            .any()
        )


class TestDeepBenchFloor:
    """The lever pulls low rows UP, and the sub-5 tail is most of the board,
    so adjusting it would inflate the whole board (+11.2% of total projected
    points on 2026 w3-6; 2069 -> 2266 on the live week-7 board) for rows the
    retro never measured. MIN_SHRINK_PTS confines it to the startable pool."""

    def test_sub_floor_rows_are_left_alone(self):
        board = _wr_board([20.0, 12.0, 10.0, 6.0, 5.5, 4.9, 1.0])
        out, _ = apply_dispersion_shrink(board, k=0.5)
        assert out["projected_points"].iloc[5] == 4.9
        assert out["projected_points"].iloc[6] == 1.0
        assert not out[FLAG_COL].iloc[5]
        assert not out[FLAG_COL].iloc[6]

    def test_board_total_is_roughly_conserved(self):
        """Contrast with the wider rule: confining the lever to the startable
        pool keeps the board's total points near-flat instead of inflating
        it, because the shrink now moves roughly as much down as up."""
        board = _wr_board([24.0, 18.0, 14.0, 11.0, 9.0, 7.0, 5.5] + [1.0] * 20)
        out, _ = apply_dispersion_shrink(board, k=0.8)
        before = board["projected_points"].sum()
        after = out["projected_points"].sum()
        assert abs(after - before) < 0.05 * before

        wider, _ = apply_dispersion_shrink(board, k=0.8, min_shrink_pts=0.0)
        assert wider["projected_points"].sum() > 1.15 * before

    def test_floor_does_not_invert_ordering_at_the_boundary(self):
        """A row just above the floor is pulled up; it must still outrank the
        untouched row just below it."""
        board = _wr_board([20.0, 15.0, 12.0, 10.0, 5.0, 4.99])
        out, _ = apply_dispersion_shrink(board, k=0.8)
        assert out["projected_points"].iloc[4] > out["projected_points"].iloc[5]
        assert out["projected_points"].iloc[4] > 5.0

    def test_sub_floor_rows_still_inform_nothing_but_are_not_dropped(self):
        board = _wr_board([20.0, 12.0, 10.0, 6.0, 5.5, 1.0])
        out, _ = apply_dispersion_shrink(board, k=0.5)
        assert len(out) == len(board)


class TestPredictiveInterval:
    """With --ml the router attaches floor/ceiling BEFORE this stage, so the
    lever must carry the band with it. Calibrating the point alone produced
    21 rows with point > ceiling on the live week-7 board (0 in control)."""

    def _banded(self):
        board = _wr_board([20.0, 14.0, 11.0, 8.0, 6.0, 5.2])
        board["projected_floor"] = board["projected_points"] * 0.6
        board["projected_ceiling"] = board["projected_points"] * 1.4
        return board

    def test_band_still_brackets_the_calibrated_point(self):
        board = self._banded()
        out, _ = apply_dispersion_shrink(board, k=0.8)
        assert (out["projected_floor"] <= out["projected_points"] + 1e-6).all()
        assert (out["projected_points"] <= out["projected_ceiling"] + 1e-6).all()

    def test_interval_width_is_preserved_not_narrowed(self):
        """Width carries the conformal coverage property — shrinking it by k
        would silently under-cover, so the band is translated instead."""
        board = self._banded()
        out, _ = apply_dispersion_shrink(board, k=0.8)
        w_before = board["projected_ceiling"] - board["projected_floor"]
        w_after = out["projected_ceiling"] - out["projected_floor"]
        assert (w_after - w_before).abs().max() < 0.05

    def test_band_moves_in_the_same_direction_as_the_point(self):
        board = self._banded()
        out, _ = apply_dispersion_shrink(board, k=0.8)
        d_pt = out["projected_points"] - board["projected_points"]
        d_ceil = out["projected_ceiling"] - board["projected_ceiling"]
        assert (d_pt * d_ceil >= -1e-6).all()
        assert d_pt.iloc[0] < 0  # top row pulled down
        assert d_pt.iloc[-1] > 0  # bottom startable row pulled up

    def test_floor_never_goes_negative(self):
        board = self._banded()
        board["projected_floor"] = 0.1
        out, _ = apply_dispersion_shrink(board, k=0.5)
        assert (out["projected_floor"] >= 0).all()

    def test_board_without_band_columns_is_unaffected(self):
        board = _wr_board([20.0, 14.0, 11.0, 8.0, 6.0])
        out, _ = apply_dispersion_shrink(board, k=0.8)
        for col in INTERVAL_COLS:
            assert col not in out.columns


class TestRegressionAgainstTheMeasuredDefect:
    """The retro's measurement: our top tiers over-projected and our bottom
    tiers under-projected. A correct lever must move both toward truth."""

    def test_corrects_both_tails_of_the_measured_bias(self):
        # Our board, deliberately over-dispersed around a centre of 12.
        ours = [24.0, 18.0, 12.0, 8.0, 4.0]
        # Actuals: the top came in low, the bottom came in high.
        actual = [17.0, 15.0, 12.0, 10.0, 8.0]
        board = _board([(f"W{i}", "WR", p) for i, p in enumerate(ours)])
        out, _ = apply_dispersion_shrink(board, k=0.6, min_centre_rows=3)
        mae_before = sum(abs(o - a) for o, a in zip(ours, actual)) / len(ours)
        mae_after = sum(
            abs(o - a) for o, a in zip(out["projected_points"], actual)
        ) / len(actual)
        assert mae_after < mae_before
