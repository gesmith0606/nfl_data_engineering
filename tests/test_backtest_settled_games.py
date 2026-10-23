"""The prediction backtester must score only games that have been played.

`assemble_multiyear_features` returns every schedule row, including fixtures
with no result, and the outcome comparisons are written as
``actual_total > total_line``. On a NaN actual that evaluates to ``False``
rather than raising, so an unplayed game is silently scored as an "Under"
outcome — one the model usually "wins".

For completed historical seasons (this harness's only prior use) every row is
settled and the omission is invisible. Run it on an in-progress season and it
fabricates a triumph. 2026 through week 6:

    272 assembled rows, 93 played
    reported: 206-66, 75.7% O/U accuracy, +44.6% ROI   <- 179 phantom games
    actual:    41-52,  44.1% O/U accuracy, -15.8% ROI

Break-even is 52.38%. The first set is the kind of number someone bets real
money on, which makes this worse than a crash.

See `.planning/PREDICTION_BACKTEST_PHANTOM_GAMES.md`.
"""

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__), "..", "src"))
sys.path.append(os.path.join(os.path.dirname(__file__), "..", "scripts"))

from backtest_predictions import (  # noqa: E402
    _SETTLED_COLS,
    drop_unsettled_games,
)

BACKTEST_SRC = os.path.join(
    os.path.dirname(__file__), "..", "scripts", "backtest_predictions.py"
)


def _games(n_played=3, n_unplayed=2):
    rows = []
    for i in range(n_played):
        rows.append(
            {
                "game_id": f"p{i}",
                "actual_margin": 3.0 + i,
                "actual_total": 44.0 + i,
                "total_line": 45.0,
                "spread_line": -2.5,
            }
        )
    for i in range(n_unplayed):
        rows.append(
            {
                "game_id": f"u{i}",
                "actual_margin": np.nan,
                "actual_total": np.nan,
                "total_line": 45.0,
                "spread_line": -2.5,
            }
        )
    return pd.DataFrame(rows)


class TestDropUnsettledGames:
    def test_unplayed_games_are_dropped(self):
        out = drop_unsettled_games(_games(3, 2))
        assert len(out) == 3
        assert set(out.game_id) == {"p0", "p1", "p2"}

    def test_all_played_is_a_no_op(self):
        df = _games(4, 0)
        out = drop_unsettled_games(df)
        assert len(out) == 4

    def test_all_unplayed_returns_empty(self):
        out = drop_unsettled_games(_games(0, 3))
        assert out.empty

    def test_a_row_missing_either_target_is_dropped(self):
        """Both targets matter: ATS needs actual_margin, O/U needs
        actual_total, and the harness scores both in one pass."""
        df = _games(1, 0)
        df.loc[len(df)] = {
            "game_id": "half",
            "actual_margin": 3.0,
            "actual_total": np.nan,
            "total_line": 45.0,
            "spread_line": -2.5,
        }
        out = drop_unsettled_games(df)
        assert set(out.game_id) == {"p0"}

    def test_does_not_mutate_the_caller(self):
        df = _games(2, 2)
        drop_unsettled_games(df)
        assert len(df) == 4

    def test_frames_without_the_target_columns_pass_through(self):
        """Some callers hand in frames that never carried the labels; this
        must not silently empty them."""
        df = pd.DataFrame({"game_id": ["a", "b"]})
        out = drop_unsettled_games(df)
        assert len(out) == 2

    def test_settled_cols_are_the_outcome_targets(self):
        assert set(_SETTLED_COLS) == {"actual_margin", "actual_total"}


class TestTheFabricationItPrevents:
    def test_nan_actuals_silently_score_as_under(self):
        """Pins the exact mechanism, so nobody 'simplifies' the filter away.

        This is the comparison the harness performs; on a NaN it yields
        False, which reads as an Under outcome rather than as missing data.
        """
        unplayed = pd.DataFrame(
            {"actual_total": [np.nan] * 5, "total_line": [45.0] * 5}
        )
        actual_over = unplayed["actual_total"] > unplayed["total_line"]
        assert not actual_over.any()
        assert actual_over.notna().all()  # no NaN propagates to flag the problem

    def test_phantom_games_inflate_a_losing_record_into_a_winning_one(self):
        """The 2026 shape: a losing real sample plus phantom Unders reads as a
        75% hit rate."""
        real_wins, real_losses, phantom = 41, 52, 179
        reported = (real_wins + phantom) / (real_wins + real_losses + phantom)
        actual = real_wins / (real_wins + real_losses)
        assert reported > 0.75
        assert actual < 0.45
        assert reported > actual


class TestEveryPathIsFiltered:
    """Patching call sites individually is how this was missed: --ensemble
    runs through run_comparison_backtest, not run_ensemble_backtest."""

    def test_no_unfiltered_assembly_call_remains(self):
        src = open(BACKTEST_SRC, encoding="utf-8").read()
        # the only permitted reference is inside the wrapper itself
        body = src.replace(
            "return drop_unsettled_games(assemble_multiyear_features(seasons), label)",
            "",
        )
        assert "= assemble_multiyear_features(" not in body

    def test_the_wrapper_exists_and_filters(self):
        src = open(BACKTEST_SRC, encoding="utf-8").read()
        assert "def _assemble_settled(" in src
        assert (
            "return drop_unsettled_games(assemble_multiyear_features(seasons), label)"
            in src
        )

    def test_all_entry_points_use_the_wrapper(self):
        src = open(BACKTEST_SRC, encoding="utf-8").read()
        assert src.count("_assemble_settled(") >= 5
